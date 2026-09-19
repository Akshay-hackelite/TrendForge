import uuid
from pathlib import Path

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, UploadFile, status

from app import schemas
from app.auth import get_current_user
from app.config import settings
from app.database import (
    append_content_video_posted_url,
    append_content_video_source_url,
    fetch_channel,
    fetch_client_doc,
    fetch_user,
    list_videos_for_channel,
    replace_channel_videos,
    update_video_fields,
)
from app.google_oauth import get_user_google_creds
from app.services.gcs_storage import upload_bytes
from app.services.youtube_api import fetch_channel_analytics, sync_videos_from_youtube

router = APIRouter(tags=["video"])

UPLOADED_VIDEOS_DIR = Path(__file__).resolve().parent.parent.parent / "social_assets" / "uploaded_videos"
VIDEO_MIME_TYPES = {"video/mp4", "video/quicktime", "video/webm"}
VIDEO_EXTS = {".mp4", ".mov", ".webm"}


def _resolve_ids(
    username: str,
    client_id: str | None,
    channel_id: str | None,
) -> tuple[str, str]:
    user = fetch_user(username)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    cid = client_id or user.get("active_client_id")
    chid = channel_id or user.get("active_channel_id")
    if not cid or not chid:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Channel not found.")
    if not fetch_client_doc(cid, username=username):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Client '{cid}' not found.",
        )
    if not fetch_channel(chid, client_id=cid, username=username):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Channel '{chid}' not found.",
        )
    return cid, chid


def _is_http_url(value: str | None) -> bool:
    return bool(value) and str(value).startswith("http")


def _fetch_graph_permalink(url: str, params: dict) -> str:
    import requests

    try:
        resp = requests.get(url, params=params, timeout=20)
        if not resp.ok:
            return ""
        data = resp.json() or {}
        for key in ("permalink", "permalink_url"):
            value = str(data.get(key) or "").strip()
            if _is_http_url(value):
                return value
    except Exception as exc:  # noqa: BLE001
        print(f"Failed to fetch permalink from {url}: {exc}")
    return ""


def _append_content_video_post_urls(
    *,
    client_id: str,
    channel_id: str,
    topic_id: str | None,
    language: str | None,
    video_id: str | None,
    ig_post_id: str | None,
    fb_post_id: str | None,
    drive_link: str | None = None,
    post_to_instagram: bool = False,
    post_to_facebook: bool = False,
    social_source_url: str | None = None,
) -> None:
    """Record watch/permalink URLs and pasted Drive/file source URLs. Skip if topic_id is missing."""
    from datetime import datetime, timezone

    if not topic_id:
        return
    posted_at = datetime.now(timezone.utc).isoformat()
    channel = fetch_channel(channel_id, client_id=client_id) or {}
    lang = language or channel.get("language") or None
    source_url = str(drive_link or "").strip()
    try:
        if source_url:
            if video_id:
                append_content_video_source_url(
                    client_id,
                    topic_id,
                    {
                        "url": source_url,
                        "kind": "youtube",
                        "channel_id": channel_id,
                        "language": lang,
                        "posted_at": posted_at,
                    },
                )
            if post_to_instagram or post_to_facebook:
                social_url = str(social_source_url or source_url or "").strip()
                if social_url:
                    append_content_video_source_url(
                        client_id,
                        topic_id,
                        {
                            "url": social_url,
                            "kind": "social",
                            "posted_at": posted_at,
                        },
                    )
        if video_id:
            append_content_video_posted_url(
                client_id,
                topic_id,
                "youtube",
                {
                    "channel_id": channel_id,
                    "language": lang,
                    "youtube_id": video_id,
                    "url": f"https://www.youtube.com/watch?v={video_id}",
                    "posted_at": posted_at,
                },
            )
        if ig_post_id:
            from app.database import get_instagram_connection

            conn = get_instagram_connection(client_id) or {}
            permalink = _fetch_graph_permalink(
                f"https://graph.instagram.com/{ig_post_id}",
                {"fields": "permalink", "access_token": conn.get("access_token") or ""},
            )
            if permalink:
                append_content_video_posted_url(
                    client_id,
                    topic_id,
                    "instagram",
                    {"url": permalink, "post_id": ig_post_id, "posted_at": posted_at},
                )
        if fb_post_id:
            from app.database import get_facebook_connection

            conn = get_facebook_connection(client_id) or {}
            token = conn.get("page_access_token") or conn.get("access_token") or ""
            permalink = _fetch_graph_permalink(
                f"https://graph.facebook.com/v18.0/{fb_post_id}",
                {"fields": "permalink_url", "access_token": token},
            )
            if permalink:
                append_content_video_posted_url(
                    client_id,
                    topic_id,
                    "facebook",
                    {"url": permalink, "post_id": fb_post_id, "posted_at": posted_at},
                )
    except Exception as exc:  # noqa: BLE001 — posting already succeeded
        print(f"Failed to append content_video URLs topic={topic_id}: {exc}")


def _get_user_videos(
    username: str,
    client_id: str | None = None,
    channel_id: str | None = None,
) -> list[dict]:
    cid, chid = _resolve_ids(username, client_id, channel_id)
    videos = list_videos_for_channel(chid, cid)
    return [v for v in videos if (v.get("privacy_status") or "public").lower() == "public"]


def _to_video_schema(raw: dict) -> schemas.YouTubeVideoInfo:
    return schemas.YouTubeVideoInfo(
        id=raw["id"],
        title=raw["title"],
        published_at=raw["published_at"],
        thumbnail_url=raw.get("thumbnail_url"),
        view_count=raw["view_count"],
        like_count=raw["like_count"],
        comment_count=raw["comment_count"],
        duration=raw.get("duration"),
        duration_seconds=raw.get("duration_seconds", 0),
        duration_type=raw.get("duration_type") or ("short" if raw.get("is_short") else "long"),
        is_short=bool(raw.get("is_short")),
        short_link=raw.get("short_link")
        or (
            f"https://www.youtube.com/shorts/{raw['id']}" if raw.get("is_short") else None
        ),
        privacy_status=(raw.get("privacy_status") or "public").lower(),
        notes=raw.get("notes", ""),
        metadata_fields=raw.get("metadata_fields", {}),
    )


def _is_public_video(raw: dict) -> bool:
    """Hide private/unlisted from the video library UI. Missing status → treat as public (legacy)."""
    status = (raw.get("privacy_status") or "public").lower()
    return status == "public"


@router.post("/video.list", response_model=schemas.YouTubeVideoListResponse)
def video_list(
    body: schemas.VideoListRequest = Body(default_factory=schemas.VideoListRequest),
    current_user: dict = Depends(get_current_user),
):
    videos = [
        _to_video_schema(v)
        for v in _get_user_videos(current_user["username"], body.client_id, body.channel_id)
        if _is_public_video(v)
    ]
    return schemas.YouTubeVideoListResponse(videos=videos)


@router.post("/video.get", response_model=schemas.YouTubeVideoInfo)
def video_get(
    body: schemas.VideoGetRequest,
    current_user: dict = Depends(get_current_user),
):
    for raw in _get_user_videos(current_user["username"], body.client_id, body.channel_id):
        if raw["id"] == body.video_id:
            return _to_video_schema(raw)

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Video '{body.video_id}' not found. Sync videos first.",
    )


@router.post("/video.sync", response_model=schemas.YouTubeVideoListResponse)
def video_sync(
    body: schemas.VideoSyncRequest = Body(default_factory=schemas.VideoSyncRequest),
    current_user: dict = Depends(get_current_user),
):
    username = current_user["username"]
    client_id, channel_id = _resolve_ids(username, body.client_id, body.channel_id)

    creds = get_user_google_creds(username, client_id, channel_id)
    synced_videos = sync_videos_from_youtube(creds, channel_id)

    existing_videos_map = {
        v["id"]: v for v in list_videos_for_channel(channel_id, client_id)
    }
    for v in synced_videos:
        existing = existing_videos_map.get(v.id)
        if existing:
            v.notes = existing.get("notes", "") or ""
            v.metadata_fields = existing.get("metadata_fields", {}) or {}

    rows = [v.model_dump() for v in synced_videos]
    replace_channel_videos(channel_id, client_id, rows)

    return schemas.YouTubeVideoListResponse(videos=synced_videos)


@router.post("/video.update", response_model=schemas.YouTubeVideoInfo)
def video_update(
    body: schemas.VideoUpdateRequest,
    current_user: dict = Depends(get_current_user),
):
    username = current_user["username"]
    client_id, channel_id = _resolve_ids(username, body.client_id, body.channel_id)
    fields: dict = {}
    if body.notes is not None:
        fields["notes"] = body.notes
    if body.metadata_fields is not None:
        fields["metadata_fields"] = body.metadata_fields
    if not fields:
        for raw in list_videos_for_channel(channel_id, client_id):
            if raw["id"] == body.video_id:
                return _to_video_schema(raw)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Video '{body.video_id}' not found.",
        )

    updated = update_video_fields(body.video_id, client_id, fields)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Video '{body.video_id}' not found.",
        )
    return _to_video_schema(updated)


@router.post("/video.analytics", response_model=schemas.YouTubeAnalyticsResponse)
def video_analytics(
    body: schemas.YouTubeAnalyticsRequest,
    current_user: dict = Depends(get_current_user),
):
    username = current_user["username"]
    client_id, channel_id = _resolve_ids(username, body.client_id, body.channel_id)
    creds = get_user_google_creds(username, client_id, channel_id)

    try:
        column_headers, rows = fetch_channel_analytics(
            creds,
            channel_id,
            start_date=body.start_date,
            end_date=body.end_date,
            metrics=body.metrics,
            dimensions=body.dimensions,
            sort=body.sort,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e

    return schemas.YouTubeAnalyticsResponse(column_headers=column_headers, rows=rows)


@router.post("/video.local.upload")
async def video_local_upload(
    client_id: str = Form(...),
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    if not fetch_client_doc(client_id, username=current_user["username"]):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")

    content_type = file.content_type or "application/octet-stream"
    mime = content_type.split(";")[0].strip().lower()
    file_ext = Path(file.filename or "").suffix.lower()
    if mime not in VIDEO_MIME_TYPES and file_ext not in VIDEO_EXTS:
        raise HTTPException(status_code=400, detail="File must be an mp4, mov, or webm video.")

    ext = file_ext if file_ext in VIDEO_EXTS else {
        "video/mp4": ".mp4",
        "video/quicktime": ".mov",
        "video/webm": ".webm",
    }.get(mime, ".mp4")
    stored_type = mime if mime in VIDEO_MIME_TYPES else {
        ".mp4": "video/mp4",
        ".mov": "video/quicktime",
        ".webm": "video/webm",
    }.get(ext, "video/mp4")

    filename = f"{uuid.uuid4().hex}{ext}"
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")

    try:
        public_url = upload_bytes("uploaded_videos", filename, content, content_type=stored_type)
    except Exception as exc:  # noqa: BLE001
        print(f"GCS upload failed: {exc}. Falling back to local disk.", flush=True)
        UPLOADED_VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
        (UPLOADED_VIDEOS_DIR / filename).write_bytes(content)
        base_url = settings.BASE_URL.rstrip("/")
        public_url = f"{base_url}/weekly.tracker.asset/uploaded_videos/{filename}"

    return {
        "url": public_url,
        "name": file.filename or filename,
        "content_type": stored_type,
    }


@router.post("/video.upload", response_model=dict)
def video_upload(
    body: schemas.VideoUploadRequest,
    current_user: dict = Depends(get_current_user),
):
    import gdown
    import os
    import uuid
    import requests
    from app.services.youtube_api import upload_video_to_youtube

    username = current_user["username"]
    client_id, channel_id = _resolve_ids(username, body.client_id, body.channel_id)
    creds = get_user_google_creds(username, client_id, channel_id)

    # 1. Download video
    video_path = f"/tmp/{uuid.uuid4()}.mp4"
    try:
        if "drive.google.com" in body.drive_link:
            # Handle Google Drive links
            gdown.download(body.drive_link, video_path, quiet=False)
        else:
            # Handle standard public video URLs (e.g. S3, direct MP4 link)
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            with requests.get(body.drive_link, stream=True, headers=headers) as r:
                r.raise_for_status()
                with open(video_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192): 
                        f.write(chunk)
                        
        if not os.path.exists(video_path):
            raise ValueError("Failed to download video.")
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to download video: {str(e)}"
        )

    # 2. Handle thumbnail
    thumbnail_path = None
    if body.thumbnail_url:
        if body.thumbnail_url.startswith("/social.asset/"):
            from pathlib import Path
            SOCIAL_ASSETS_DIR = Path(__file__).resolve().parent.parent.parent / "social_assets"
            relative_path = body.thumbnail_url.replace("/social.asset/", "", 1)
            local_file = SOCIAL_ASSETS_DIR / relative_path
            if local_file.exists():
                thumbnail_path = str(local_file)
            else:
                if os.path.exists(video_path):
                    os.remove(video_path)
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Thumbnail not found locally: {body.thumbnail_url}"
                )
        else:
            thumbnail_path = f"/tmp/{uuid.uuid4()}.jpg"
            try:
                resp = requests.get(body.thumbnail_url)
                resp.raise_for_status()
                with open(thumbnail_path, "wb") as f:
                    f.write(resp.content)
            except Exception as e:
                # Clean up video before raising
                if os.path.exists(video_path):
                    os.remove(video_path)
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Failed to download thumbnail: {str(e)}"
                )

    # 3. Upload to YouTube
    video_id = None
    try:
        video_id = upload_video_to_youtube(
            creds=creds,
            channel_id=channel_id,
            video_path=video_path,
            title=body.title,
            description=body.description,
            tags=body.tags,
            thumbnail_path=thumbnail_path
        )
        
        # 4. Social Integration
        ig_post_id = None
        fb_post_id = None
        if body.post_to_instagram or body.post_to_facebook:
            from app.services.gcs_storage import upload_file
            from app.services.youtube_metadata import generate_social_caption
            from app.routes.social import get_instagram_connection, get_facebook_connection
            
            # Upload video to GCS for public URL
            gcs_url = upload_file("social_post_videos", video_path, content_type="video/mp4")
            
            # Generate AI Caption
            social_caption = generate_social_caption(body.title, body.description, body.tags)
            
            if body.post_to_instagram:
                try:
                    conn = get_instagram_connection(body.client_id)
                    ig_user_id = conn["instagram_user_id"]
                    access_token = conn["access_token"]
                    
                    media_resp = requests.post(
                        f"https://graph.instagram.com/{ig_user_id}/media",
                        data={
                            "media_type": "REELS",
                            "video_url": gcs_url,
                            "caption": social_caption,
                            "access_token": access_token,
                        },
                    )
                    media_resp.raise_for_status()
                    creation_id = media_resp.json().get("id")
                    
                    import time
                    for attempt in range(3):
                        time.sleep(5)  # Wait for IG to process the video
                        publish_resp = requests.post(
                            f"https://graph.instagram.com/{ig_user_id}/media_publish",
                            data={
                                "creation_id": creation_id,
                                "access_token": access_token,
                            },
                        )
                        if publish_resp.ok:
                            ig_post_id = publish_resp.json().get("id")
                            break
                except Exception as e:
                    print(f"Failed to post to Instagram: {e}")
                    
            if body.post_to_facebook:
                try:
                    conn = get_facebook_connection(body.client_id)
                    page_id = conn["page_id"]
                    access_token = conn["access_token"]
                    
                    fb_resp = requests.post(
                        f"https://graph.facebook.com/v18.0/{page_id}/videos",
                        data={
                            "file_url": gcs_url,
                            "description": social_caption,
                            "access_token": access_token,
                        },
                    )
                    fb_resp.raise_for_status()
                    fb_post_id = fb_resp.json().get("id")
                except Exception as e:
                    print(f"Failed to post to Facebook: {e}")

        _append_content_video_post_urls(
            client_id=client_id,
            channel_id=channel_id,
            topic_id=body.topic_id,
            language=body.language,
            video_id=video_id,
            ig_post_id=ig_post_id,
            fb_post_id=fb_post_id,
            drive_link=body.drive_link,
            post_to_instagram=body.post_to_instagram,
            post_to_facebook=body.post_to_facebook,
            social_source_url=body.social_source_url,
        )
                    
    finally:
        # 5. Clean up temporary files
        if os.path.exists(video_path):
            os.remove(video_path)
        if thumbnail_path and thumbnail_path.startswith("/tmp/") and os.path.exists(thumbnail_path):
            os.remove(thumbnail_path)

    return {
        "status": "success",
        "video_id": video_id,
        "ig_post_id": ig_post_id if 'ig_post_id' in locals() else None,
        "fb_post_id": fb_post_id if 'fb_post_id' in locals() else None
    }
