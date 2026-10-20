"""Publish a video to YouTube, Facebook, and Instagram.

YouTube and Facebook read the local file. Instagram is the only step that copies
the file to Supabase so Meta can download a public URL.
"""

from __future__ import annotations

import json
import os
import queue
import re
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests
from fastapi import HTTPException, status
from fastapi.responses import StreamingResponse

from app import schemas
from app.database import (
    append_content_video_posted_url,
    append_content_video_source_url,
    fetch_channel,
    fetch_client_doc,
    fetch_user,
    get_facebook_connection,
    get_instagram_connection,
)
from app.google_oauth import get_user_google_creds
from app.services.supabase_storage import STORAGE_TIMEOUT_DETAIL, explain_storage_failure
from app.services.youtube_api import fit_social_caption, publish_platforms, upload_video_to_youtube

_INSTAGRAM_REEL_MAX_BYTES = 1000 * 1000 * 1000
_URL_RE = re.compile(r"https?://\S+")
_DOWNLOAD_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}


class _Job:
    def __init__(
        self,
        *,
        channel_id: str = "",
        drive_link: str = "",
        title: str = "",
        description: str = "",
        tags: list | None = None,
        thumbnail_url: str | None = None,
        language: str | None = None,
        topic_id: str | None = None,
    ):
        self.channel_id = channel_id or ""
        self.drive_link = drive_link or ""
        self.title = title or ""
        self.description = description or ""
        self.tags = list(tags or [])
        self.thumbnail_url = thumbnail_url
        self.language = language
        self.topic_id = topic_id


def _clean_url(value: str | None) -> str:
    text = str(value or "").strip()
    match = _URL_RE.search(text)
    if not match:
        return text
    return match.group(0).rstrip(").,]>\"'")


def _jobs_from_body(body: schemas.VideoUploadRequest) -> list[_Job]:
    jobs: list[_Job] = []
    for row in body.channels or []:
        data = row.model_dump() if hasattr(row, "model_dump") else dict(row)
        jobs.append(_Job(**data))
    if jobs:
        return jobs
    if (body.drive_link or "").strip() or (body.channel_id or "").strip():
        jobs.append(
            _Job(
                channel_id=body.channel_id,
                drive_link=body.drive_link,
                title=body.title,
                description=body.description,
                tags=body.tags,
                thumbnail_url=body.thumbnail_url,
                language=body.language,
                topic_id=body.topic_id,
            )
        )
    return jobs


def _require_client(username: str, client_id: str | None) -> str:
    user = fetch_user(username)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    cid = client_id or user.get("active_client_id")
    if not cid or not fetch_client_doc(cid, username=username):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Client '{cid}' not found.",
        )
    return cid


def _file_size(path: str) -> int:
    return os.path.getsize(path)


def _download_one(url: str) -> str:
    import gdown

    cleaned = _clean_url(url)
    if not cleaned:
        raise ValueError("Missing video URL.")
    video_path = f"/tmp/{uuid.uuid4()}.mp4"
    if "drive.google.com" in cleaned or "docs.google.com" in cleaned:
        gdown.download(cleaned, video_path, quiet=False)
    else:
        with requests.get(cleaned, stream=True, headers=_DOWNLOAD_HEADERS, timeout=3600) as response:
            response.raise_for_status()
            with open(video_path, "wb") as handle:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        handle.write(chunk)
    if not os.path.exists(video_path) or _file_size(video_path) <= 0:
        raise ValueError("Failed to download video.")
    if ("drive.google.com" in cleaned or "docs.google.com" in cleaned) and _file_size(video_path) < 1_000_000:
        os.remove(video_path)
        raise ValueError("Drive download was under 1 MB. It is usually the preview page, not the file.")
    return video_path


def _download_all(urls: list[str]) -> tuple[dict[str, str], dict[str, str]]:
    unique: list[str] = []
    for raw in urls:
        cleaned = _clean_url(raw)
        if cleaned and cleaned not in unique:
            unique.append(cleaned)
    found: dict[str, str] = {}
    failed: dict[str, str] = {}
    if not unique:
        return found, failed
    workers = min(4, len(unique))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_download_one, url): url for url in unique}
        for future in as_completed(futures):
            url = futures[future]
            try:
                found[url] = future.result()
            except Exception as exc:  # noqa: BLE001
                failed[url] = str(exc)
    return found, failed


def _download_bytes(url: str, suffix: str) -> str | None:
    cleaned = _clean_url(url)
    if not cleaned:
        return None
    if cleaned.startswith("/social.asset/"):
        assets = Path(__file__).resolve().parent.parent.parent / "social_assets"
        local = assets / cleaned.replace("/social.asset/", "", 1)
        return str(local) if local.exists() else None
    if not cleaned.startswith("http"):
        return cleaned if os.path.exists(cleaned) else None
    path = f"/tmp/{uuid.uuid4()}{suffix}"
    response = requests.get(cleaned, timeout=60)
    response.raise_for_status()
    with open(path, "wb") as handle:
        handle.write(response.content)
    return path


def facebook_connection_fields(conn: dict | None) -> tuple[str, str]:
    row = conn or {}
    page_id = str(row.get("selected_page_id") or row.get("page_id") or "").strip()
    token = str(row.get("page_access_token") or row.get("access_token") or "").strip()
    if not page_id or not token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Facebook is not connected for this client.",
        )
    return page_id, token


def facebook_public_url(video_id: str, page_id: str, permalink: str = "") -> str:
    if permalink.startswith("http"):
        return permalink
    if "_" in str(video_id):
        return f"https://www.facebook.com/{video_id}"
    if page_id:
        return f"https://www.facebook.com/{page_id}/videos/{video_id}"
    return f"https://www.facebook.com/watch/?v={video_id}"


def facebook_is_on_page(payload: dict) -> bool:
    status_obj = payload.get("status") if isinstance(payload.get("status"), dict) else {}
    video_status = str(status_obj.get("video_status") or "").lower()
    processing = status_obj.get("processing_phase") if isinstance(status_obj.get("processing_phase"), dict) else {}
    publishing = status_obj.get("publishing_phase") if isinstance(status_obj.get("publishing_phase"), dict) else {}
    processing_status = str(processing.get("status") or "").lower()
    publishing_status = str(publishing.get("status") or "").lower()
    for phase in (processing_status, publishing_status, video_status):
        if phase == "error":
            return False
    if processing_status in {"", "not_started", "in_progress"}:
        return False
    if publishing_status in {"not_started", "in_progress"}:
        return False
    ready = video_status in {"ready", "complete"} or processing_status in {"complete", "completed"}
    published = publishing_status in {"complete", "completed"} or bool(payload.get("published"))
    return ready and published


def _facebook_phase_error(payload: dict) -> str:
    status_obj = payload.get("status") if isinstance(payload.get("status"), dict) else {}
    for key in ("processing_phase", "publishing_phase"):
        phase = status_obj.get(key) if isinstance(status_obj.get(key), dict) else {}
        if str(phase.get("status") or "").lower() == "error":
            errors = phase.get("errors") or phase.get("error") or status_obj.get("video_status")
            return str(errors or "Facebook reported an error.")
    if str(status_obj.get("video_status") or "").lower() == "error":
        return str(status_obj.get("errors") or "Facebook reported an error.")
    return ""


def _facebook_resumable_session(
    page_id: str,
    token: str,
    video_path: str,
    description: str,
    on_progress,
) -> str:
    """start → transfer the slice Facebook asked for → finish. No file_url."""
    url = f"https://graph-video.facebook.com/v18.0/{page_id}/videos"
    size = _file_size(video_path)
    started = requests.post(
        url,
        data={
            "access_token": token,
            "upload_phase": "start",
            "file_size": size,
            "published": "true",
        },
        timeout=120,
    )
    if not started.ok:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Facebook video upload failed: {started.text[:800]}",
        )
    session = started.json() or {}
    upload_session_id = session.get("upload_session_id")
    video_id = str(session.get("video_id") or session.get("id") or "")
    start_offset = int(session.get("start_offset") or 0)
    end_offset = int(session.get("end_offset") or 0)
    if not upload_session_id or not video_id:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Facebook video upload failed: missing upload session.",
        )
    with open(video_path, "rb") as handle:
        while start_offset != end_offset:
            length = end_offset - start_offset
            if length <= 0:
                break
            handle.seek(start_offset)
            chunk = handle.read(length)
            transferred = requests.post(
                url,
                data={
                    "access_token": token,
                    "upload_phase": "transfer",
                    "upload_session_id": upload_session_id,
                    "start_offset": str(start_offset),
                },
                files={"video_file_chunk": ("chunk.mp4", chunk, "application/octet-stream")},
                timeout=3600,
            )
            if not transferred.ok:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Facebook video upload failed: {transferred.text[:800]}",
                )
            payload = transferred.json() or {}
            new_start = int(payload.get("start_offset") or start_offset)
            new_end = int(payload.get("end_offset") or end_offset)
            if new_start == start_offset and new_start != new_end:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Facebook upload offsets did not advance",
                )
            start_offset, end_offset = new_start, new_end
            if on_progress and size:
                on_progress(min(100, int(min(start_offset, size) * 100 / size)))
    finished = requests.post(
        url,
        data={
            "access_token": token,
            "upload_phase": "finish",
            "upload_session_id": upload_session_id,
            "description": description,
            "published": "true",
        },
        timeout=120,
    )
    if not finished.ok:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Facebook video upload failed: {finished.text[:800]}",
        )
    return str((finished.json() or {}).get("video_id") or (finished.json() or {}).get("id") or video_id)


def _wait_facebook_video_published(video_id: str, token: str, emit) -> dict:
    import time

    deadline = time.time() + 20 * 60
    last = {}
    while time.time() < deadline:
        response = requests.get(
            f"https://graph.facebook.com/v18.0/{video_id}",
            params={"fields": "status,published,permalink_url", "access_token": token},
            timeout=30,
        )
        if not response.ok:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Facebook video status failed: {response.text[:800]}",
            )
        last = response.json() or {}
        phase_error = _facebook_phase_error(last)
        if phase_error:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=phase_error)
        progress = ((last.get("status") or {}).get("processing_phase") or {}).get("processing_progress")
        if progress is not None and emit:
            emit(f"Facebook is processing the video… {progress}%")
        if facebook_is_on_page(last):
            return last
        time.sleep(8)
    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail="Facebook accepted the file but did not finish publishing it in time.",
    )


def _set_facebook_video_thumbnail(video_id: str, token: str, image_path: str) -> None:
    with open(image_path, "rb") as handle:
        response = requests.post(
            f"https://graph.facebook.com/v18.0/{video_id}/thumbnails",
            data={"access_token": token, "is_preferred": "true"},
            files={"source": handle},
            timeout=60,
        )
    if not response.ok:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Facebook thumbnail failed: {response.text[:400]}",
        )


def _publish_facebook_video(
    client_id: str,
    video_path: str,
    caption: str,
    *,
    emit,
    thumbnail_path: str | None = None,
) -> tuple[str, str, list[str]]:
    conn = get_facebook_connection(client_id) or {}
    page_id, token = facebook_connection_fields(conn)
    warnings: list[str] = []
    if not video_path or not os.path.exists(video_path):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Facebook video upload failed: local file is missing.",
        )

    def on_progress(percent: int) -> None:
        emit(f"Posting to Facebook… {percent}%")

    video_id = _facebook_resumable_session(page_id, token, video_path, caption, on_progress)
    payload = _wait_facebook_video_published(video_id, token, emit)
    permalink = str(payload.get("permalink_url") or "").strip()
    if not permalink.startswith("http"):
        permalink = _fetch_permalink(
            f"https://graph.facebook.com/v18.0/{video_id}",
            {"fields": "permalink_url", "access_token": token},
            "permalink_url",
        )
    if not permalink.startswith("http"):
        permalink = facebook_public_url(video_id, page_id, "")
        print(f"[facebook] no permalink_url for {video_id}; using page link", flush=True)
    if thumbnail_path and os.path.exists(thumbnail_path):
        try:
            _set_facebook_video_thumbnail(video_id, token, thumbnail_path)
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"Facebook thumbnail was not set. {exc}")
    return video_id, permalink, warnings


def _fetch_permalink(url: str, params: dict, key: str) -> str:
    try:
        response = requests.get(url, params=params, timeout=20)
        if not response.ok:
            return ""
        value = str((response.json() or {}).get(key) or "").strip()
        return value if value.startswith("http") else ""
    except Exception as exc:  # noqa: BLE001
        print(f"Failed to fetch permalink from {url}: {exc}", flush=True)
        return ""


def _publish_instagram_reel(
    client_id: str,
    video_url: str,
    caption: str,
    *,
    cover_url: str | None,
    emit,
) -> tuple[str, str, list[str]]:
    import time

    conn = get_instagram_connection(client_id) or {}
    ig_user_id = str(conn.get("instagram_user_id") or "").strip()
    access_token = str(conn.get("access_token") or "").strip()
    if not ig_user_id or not access_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Instagram is not connected for this client.",
        )
    warnings: list[str] = []
    data = {
        "media_type": "REELS",
        "video_url": video_url,
        "caption": caption,
        "access_token": access_token,
    }
    if cover_url:
        data["cover_url"] = cover_url
    media_resp = requests.post(f"https://graph.instagram.com/{ig_user_id}/media", data=data, timeout=60)
    if not media_resp.ok and cover_url:
        warnings.append(f"Instagram cover was skipped. {_graph_text(media_resp)}")
        data.pop("cover_url", None)
        media_resp = requests.post(f"https://graph.instagram.com/{ig_user_id}/media", data=data, timeout=60)
    if not media_resp.ok:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Instagram reel upload failed: {_graph_text(media_resp)}",
        )
    creation_id = (media_resp.json() or {}).get("id")
    if not creation_id:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Instagram reel upload failed: {_graph_text(media_resp)}",
        )
    deadline = time.time() + 180
    last_body = ""
    while time.time() < deadline:
        time.sleep(5)
        status_resp = requests.get(
            f"https://graph.instagram.com/{creation_id}",
            params={"fields": "status_code,status", "access_token": access_token},
            timeout=30,
        )
        last_body = _graph_text(status_resp)
        if not status_resp.ok:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Instagram reel status failed: {last_body}",
            )
        code = str((status_resp.json() or {}).get("status_code") or "").upper()
        if code:
            emit(f"Instagram is processing the reel ({code})…")
        if code == "FINISHED":
            break
        if code == "ERROR":
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Instagram reel processing failed: {last_body}",
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Instagram reel was not ready in time: {last_body}",
        )
    publish_resp = requests.post(
        f"https://graph.instagram.com/{ig_user_id}/media_publish",
        data={"creation_id": creation_id, "access_token": access_token},
        timeout=60,
    )
    if not publish_resp.ok:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Instagram reel publish failed: {_graph_text(publish_resp)}",
        )
    ig_post_id = str((publish_resp.json() or {}).get("id") or "")
    if not ig_post_id:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Instagram reel publish failed: {_graph_text(publish_resp)}",
        )
    permalink = _fetch_permalink(
        f"https://graph.instagram.com/{ig_post_id}",
        {"fields": "id,permalink", "access_token": access_token},
        "permalink",
    )
    if not permalink:
        print(f"[instagram] no permalink for {ig_post_id}", flush=True)
    return ig_post_id, permalink, warnings


def _graph_text(response) -> str:
    text = (getattr(response, "text", None) or "")[:800]
    return text or f"HTTP {getattr(response, 'status_code', '')}"


def _detail(exc: Exception) -> str:
    detail = getattr(exc, "detail", None)
    if detail:
        return str(detail)
    return str(exc)


def _storage_error(exc: Exception) -> str:
    text = explain_storage_failure(exc)
    if text == STORAGE_TIMEOUT_DETAIL or "timeout" in text.lower() or "timed out" in text.lower():
        return STORAGE_TIMEOUT_DETAIL
    return _detail(exc) if _detail(exc) else text


def _record(client_id: str, topic_id: str | None, platform: str, entry: dict, source: dict | None = None) -> None:
    if not topic_id:
        return
    try:
        if source:
            append_content_video_source_url(client_id, topic_id, source)
        append_content_video_posted_url(client_id, topic_id, platform, entry)
    except Exception as exc:  # noqa: BLE001
        print(f"Failed to append content_video URLs topic={topic_id}: {exc}", flush=True)


def _copy_to_storage(video_path: str, on_progress) -> str:
    from app.services.storage import upload_file

    return upload_file(
        "social_post_videos",
        video_path,
        content_type="video/mp4",
        on_progress=on_progress,
        allow_large=True,
    )


def _public_cover(local_path: str | None, source_url: str | None) -> str | None:
    if source_url and str(source_url).startswith("http"):
        return source_url
    if not local_path or not os.path.exists(local_path):
        return None
    from app.services.storage import upload_bytes

    filename = f"{uuid.uuid4()}.png"
    return upload_bytes("thumbnails", filename, Path(local_path).read_bytes(), content_type="image/png")


def _start_caption(title: str, description: str, tags: list):
    holder = {"text": fit_social_caption(title or "Untitled")}

    def run() -> None:
        try:
            from app.services.youtube_metadata import generate_social_caption

            holder["text"] = fit_social_caption(generate_social_caption(title, description, tags))
        except Exception as exc:  # noqa: BLE001
            print(f"[publish] caption fallback: {exc}", flush=True)
            holder["text"] = fit_social_caption(title or "Untitled")

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return holder, thread


def _social_url(body: schemas.VideoUploadRequest, jobs: list[_Job]) -> str:
    explicit = _clean_url(body.social_video_url or body.social_source_url or "")
    if explicit:
        return explicit
    hinglish = next((job for job in jobs if str(job.language or "").lower() == "hinglish" and job.drive_link), None)
    if hinglish:
        return _clean_url(hinglish.drive_link)
    if jobs and jobs[0].drive_link:
        return _clean_url(jobs[0].drive_link)
    return _clean_url(body.drive_link)


def _cover_source(body: schemas.VideoUploadRequest, jobs: list[_Job]) -> str:
    hinglish = next(
        (job for job in jobs if str(job.language or "").lower() == "hinglish" and job.thumbnail_url),
        None,
    )
    if hinglish:
        return str(hinglish.thumbnail_url)
    for job in jobs:
        if job.thumbnail_url:
            return str(job.thumbnail_url)
    return str(body.thumbnail_url or "")


def _caption_source(jobs: list[_Job], body: schemas.VideoUploadRequest) -> tuple[str, str, list]:
    hinglish = next((job for job in jobs if str(job.language or "").lower() == "hinglish"), None)
    job = hinglish or (jobs[0] if jobs else None)
    if job is None:
        return body.title, body.description, list(body.tags or [])
    return job.title or body.title, job.description or body.description, list(job.tags or body.tags or [])


def _execute_video_upload(body: schemas.VideoUploadRequest, username: str, *, emit=None) -> dict:
    emit = emit or (lambda stage: print(f"[publish] {stage}", flush=True))
    client_id = _require_client(username, body.client_id)
    post_to_youtube, post_to_instagram, post_to_facebook = publish_platforms(
        post_to_youtube=body.post_to_youtube,
        post_to_instagram=body.post_to_instagram,
        post_to_facebook=body.post_to_facebook,
    )
    jobs = _jobs_from_body(body)
    topic_id = (body.topic_id or (jobs[0].topic_id if jobs else "") or "").strip() or None
    errors: list[str] = []
    video_ids: list[str] = []
    ig_post_id = None
    fb_post_id = None
    downloaded: dict[str, str] = {}
    failed: dict[str, str] = {}
    thumbnails: list[str] = []
    caption_thread = None
    _caption = {"text": ""}

    try:
        social_needed = post_to_instagram or post_to_facebook
        social_link = _social_url(body, jobs) if social_needed else ""
        if social_needed and not social_link:
            errors.append("Please provide a social video URL.")
            social_needed = False
        urls = []
        if post_to_youtube:
            urls.extend(job.drive_link for job in jobs)
        if social_link:
            urls.append(social_link)
        if urls:
            emit("Downloading video…")
            downloaded, failed = _download_all(urls)

        if social_needed:
            title, description, tags = _caption_source(jobs, body)
            _caption, caption_thread = _start_caption(title, description, tags)

        if post_to_youtube:
            for job in jobs:
                channel = fetch_channel(job.channel_id, client_id=client_id) or {}
                language = str(job.language or channel.get("language") or "channel")
                link = _clean_url(job.drive_link)
                path = downloaded.get(link)
                if not path:
                    errors.append(f"{language}: {failed.get(link) or 'Add a video URL.'}")
                    continue
                thumb_path = None
                if job.thumbnail_url:
                    try:
                        thumb_path = _download_bytes(job.thumbnail_url, ".jpg")
                        if thumb_path and thumb_path.startswith("/tmp/"):
                            thumbnails.append(thumb_path)
                    except Exception as exc:  # noqa: BLE001
                        errors.append(f"{language}: thumbnail download failed: {exc}")
                try:
                    creds = get_user_google_creds(username, client_id, job.channel_id)
                    emit(f"Uploading to YouTube ({language})…")

                    def on_progress(percent: int, lang: str = language) -> None:
                        emit(f"Uploading to YouTube ({lang})… {percent}%")

                    def on_processing(lang: str = language) -> None:
                        emit(f"YouTube is processing the video ({lang})…")

                    video_id = upload_video_to_youtube(
                        creds=creds,
                        channel_id=job.channel_id,
                        video_path=path,
                        title=job.title,
                        description=job.description,
                        tags=job.tags,
                        thumbnail_path=thumb_path,
                        on_progress=on_progress,
                        on_processing=on_processing,
                    )
                    video_ids.append(video_id)
                    emit(f"YouTube video is live ({language}).")
                    _record(
                        client_id,
                        job.topic_id or topic_id,
                        "youtube",
                        {
                            "channel_id": job.channel_id,
                            "language": language,
                            "youtube_id": video_id,
                            "url": f"https://www.youtube.com/watch?v={video_id}",
                        },
                        source={
                            "url": link,
                            "kind": "youtube",
                            "channel_id": job.channel_id,
                            "language": language,
                        } if link else None,
                    )
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"{language}: {_detail(exc)}")

        social_path = downloaded.get(social_link) if social_link else None
        if social_needed and not social_path:
            errors.append(failed.get(social_link) or "Please provide a social video URL.")
            social_needed = False

        if caption_thread is not None:
            caption_thread.join()
        caption = _caption["text"] if social_needed else ""

        cover_local = None
        if social_needed:
            try:
                cover_local = _download_bytes(_cover_source(body, jobs), ".jpg")
                if cover_local and cover_local.startswith("/tmp/"):
                    thumbnails.append(cover_local)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"Thumbnail download failed: {exc}")

        if post_to_facebook and social_path:
            emit("Posting to Facebook…")
            try:
                fb_post_id, permalink, warnings = _publish_facebook_video(
                    client_id,
                    social_path,
                    caption,
                    emit=emit,
                    thumbnail_path=cover_local,
                )
                errors.extend(warnings)
                emit("Facebook video posted.")
                _record(
                    client_id,
                    topic_id,
                    "facebook",
                    {"url": permalink, "post_id": fb_post_id, "language": "hinglish"},
                    source={"url": social_link, "kind": "social"} if social_link else None,
                )
            except Exception as exc:  # noqa: BLE001
                errors.append(_detail(exc))

        if post_to_instagram and social_path:
            size = _file_size(social_path)
            if size > _INSTAGRAM_REEL_MAX_BYTES:
                message = (
                    "Instagram reel was not posted. The video is "
                    f"{size / 1_000_000_000:.2f} GB, and Instagram reels must be 1 GB or smaller."
                )
                errors.append(message)
                emit(message)
            else:
                emit("Copying video for Instagram…")
                try:
                    def on_copy(percent: int) -> None:
                        emit(f"Copying video for Instagram… {percent}%")

                    public_url = _copy_to_storage(social_path, on_copy)
                except Exception as exc:  # noqa: BLE001
                    errors.append(_storage_error(exc))
                    public_url = ""
                if public_url:
                    try:
                        cover_url = _public_cover(cover_local, _cover_source(body, jobs))
                        ig_post_id, permalink, warnings = _publish_instagram_reel(
                            client_id,
                            public_url,
                            caption,
                            cover_url=cover_url,
                            emit=emit,
                        )
                        errors.extend(warnings)
                        emit("Instagram reel posted.")
                        if permalink:
                            _record(
                                client_id,
                                topic_id,
                                "instagram",
                                {"url": permalink, "post_id": ig_post_id, "language": "hinglish"},
                                source={"url": social_link, "kind": "social"} if social_link else None,
                            )
                    except Exception as exc:  # noqa: BLE001
                        errors.append(_detail(exc))
    finally:
        for path in list(downloaded.values()) + thumbnails:
            if path and path.startswith("/tmp/") and os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    pass

    return {
        "status": "partial" if errors else "success",
        "errors": errors,
        "video_id": video_ids[0] if video_ids else None,
        "video_ids": video_ids,
        "ig_post_id": ig_post_id,
        "fb_post_id": fb_post_id,
    }


def execute_video_upload(body: schemas.VideoUploadRequest, username: str):
    if not body.stream_progress:
        return _execute_video_upload(body, username)

    events: queue.Queue = queue.Queue()

    def emit(stage: str) -> None:
        print(f"[publish] {stage}", flush=True)
        events.put({"event": "stage", "stage": stage})

    def run() -> None:
        try:
            result = _execute_video_upload(body, username, emit=emit)
            events.put({"event": "done", "result": result})
        except Exception as exc:  # noqa: BLE001
            events.put({"event": "error", "detail": _detail(exc)})
        finally:
            events.put(None)

    threading.Thread(target=run, daemon=True).start()

    def generate():
        while True:
            item = events.get()
            if item is None:
                break
            yield json.dumps(item) + "\n"

    return StreamingResponse(generate(), media_type="application/x-ndjson")
