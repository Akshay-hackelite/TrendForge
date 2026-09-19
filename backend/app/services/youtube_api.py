from datetime import date
import re
from typing import Optional

import os
from PIL import Image
import io
from fastapi import HTTPException, status
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials

from app import schemas


def _process_thumbnail_image(file_path: str, max_size_mb: float = 2.0) -> str:
    """
    Checks if a file is larger than max_size_mb. If so, compresses it using Pillow 
    and saves it to a temporary path.
    """
    if os.path.getsize(file_path) <= max_size_mb * 1024 * 1024:
        return file_path
    
    img = Image.open(file_path)
    temp_path = f"{file_path}_compressed.jpg"
    quality = 95
    while quality > 5:
        img.save(temp_path, "JPEG", quality=quality)
        if os.path.getsize(temp_path) <= max_size_mb * 1024 * 1024:
            return temp_path
        quality -= 10
    return temp_path


def _parse_channel_item(channel: dict) -> dict:
    snippet = channel["snippet"]
    stats = channel.get("statistics", {})
    return {
        "id": channel["id"],
        "title": snippet["title"],
        "description": snippet.get("description", ""),
        "custom_url": snippet.get("customUrl"),
        "published_at": snippet.get("publishedAt", ""),
        "view_count": int(stats.get("viewCount", 0)),
        "subscriber_count": int(stats.get("subscriberCount", 0)),
        "video_count": int(stats.get("videoCount", 0)),
    }


def fetch_all_channels(creds) -> list[dict]:
    try:
        youtube = build("youtube", "v3", credentials=creds)
        response = youtube.channels().list(part="snippet,statistics", mine=True).execute()
        items = response.get("items", [])
        if not items:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No YouTube channels found for the authenticated Google account.",
            )
        return [_parse_channel_item(item) for item in items]
    except HTTPException:
        raise
    except HttpError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Google API Error: {e.reason if hasattr(e, 'reason') else str(e)}",
        )


def fetch_channel_info(creds, channel_id: str) -> dict:
    try:
        youtube = build("youtube", "v3", credentials=creds)
        response = youtube.channels().list(
            part="snippet,statistics", id=channel_id
        ).execute()

        if not response.get("items"):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"YouTube channel '{channel_id}' not found.",
            )

        return _parse_channel_item(response["items"][0])
    except HTTPException:
        raise
    except HttpError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Google API Error: {e.reason if hasattr(e, 'reason') else str(e)}",
        )


def fetch_channel_analytics(
    creds,
    channel_id: str,
    *,
    start_date: date,
    end_date: date,
    metrics: str,
    dimensions: Optional[str] = "day",
    sort: Optional[str] = None,
    filters: Optional[str] = None,
    max_results: Optional[int] = None,
) -> tuple[list[str], list]:
    try:
        youtube_analytics = build("youtubeAnalytics", "v2", credentials=creds)

        query_params: dict = {
            "ids": f"channel=={channel_id}",
            "startDate": start_date.strftime("%Y-%m-%d"),
            "endDate": end_date.strftime("%Y-%m-%d"),
            "metrics": metrics,
        }
        if dimensions:
            query_params["dimensions"] = dimensions
        if sort:
            query_params["sort"] = sort
        if filters:
            query_params["filters"] = filters
        if max_results is not None:
            query_params["maxResults"] = max_results

        response = youtube_analytics.reports().query(**query_params).execute()
        column_headers = [col["name"] for col in response.get("columnHeaders", [])]
        rows = response.get("rows", [])
        return column_headers, rows
    except HttpError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Google Analytics API Error: {e.content.decode('utf-8') if hasattr(e, 'content') else str(e)}",
        )


def parse_iso8601_duration_to_seconds(duration_str: str) -> int:
    """
    Parses an ISO 8601 duration string (e.g., PT1H2M3S, PT15M, PT30S) into total seconds.
    """
    if not duration_str:
        return 0
    # YouTube durations are typically of the format: PT[nH][nM][nS]
    pattern = re.compile(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?")
    match = pattern.match(duration_str)
    if not match:
        return 0
    hours = int(match.group(1)) if match.group(1) else 0
    minutes = int(match.group(2)) if match.group(2) else 0
    seconds = int(match.group(3)) if match.group(3) else 0
    return hours * 3600 + minutes * 60 + seconds


def _shorts_playlist_id(channel_id: str) -> str | None:
    """YouTube auto-generates a Shorts playlist by replacing UC with UUSH."""
    if channel_id.startswith("UC") and len(channel_id) > 2:
        return "UUSH" + channel_id[2:]
    return None


def _fetch_playlist_video_ids(youtube, playlist_id: str) -> set[str]:
    """Return all video IDs in a playlist. Empty set if playlist is missing/inaccessible."""
    video_ids: set[str] = set()
    next_page_token = None
    try:
        while True:
            response = youtube.playlistItems().list(
                playlistId=playlist_id,
                part="contentDetails,snippet",
                maxResults=50,
                pageToken=next_page_token,
            ).execute()
            for item in response.get("items", []):
                vid = item.get("contentDetails", {}).get("videoId")
                if not vid:
                    vid = (
                        item.get("snippet", {})
                        .get("resourceId", {})
                        .get("videoId")
                    )
                if vid:
                    video_ids.add(vid)
            next_page_token = response.get("nextPageToken")
            if not next_page_token:
                break
    except HttpError:
        # Channel may have no Shorts playlist yet — treat as empty.
        return set()
    return video_ids


def _fetch_shorts_ids_from_analytics(creds, channel_id: str) -> set[str]:
    """
    Official Shorts IDs via YouTube Analytics creatorContentType==SHORTS.
    Does not use video duration. Best-effort: empty set if Analytics fails.
    """
    shorts_ids: set[str] = set()
    try:
        youtube_analytics = build("youtubeAnalytics", "v2", credentials=creds)
        start_index = 1
        page_size = 200
        while True:
            response = youtube_analytics.reports().query(
                ids=f"channel=={channel_id}",
                startDate="2005-01-01",
                endDate=date.today().strftime("%Y-%m-%d"),
                metrics="views",
                dimensions="video",
                filters="creatorContentType==SHORTS",
                sort="-views",
                maxResults=page_size,
                startIndex=start_index,
            ).execute()
            rows = response.get("rows") or []
            for row in rows:
                if row and row[0]:
                    shorts_ids.add(str(row[0]))
            if len(rows) < page_size:
                break
            start_index += page_size
    except Exception:
        return set()
    return shorts_ids


def _resolve_shorts_ids(creds, youtube, channel_id: str) -> set[str]:
    """
    Classify Shorts without using duration:
    1) Channel Shorts playlist (UUSH…)
    2) Analytics creatorContentType==SHORTS (covers playlist gaps)
    """
    shorts_ids: set[str] = set()
    shorts_pl = _shorts_playlist_id(channel_id)
    if shorts_pl:
        shorts_ids |= _fetch_playlist_video_ids(youtube, shorts_pl)
    shorts_ids |= _fetch_shorts_ids_from_analytics(creds, channel_id)
    return shorts_ids


def sync_videos_from_youtube(creds, channel_id: str) -> list[schemas.YouTubeVideoInfo]:
    try:
        youtube = build("youtube", "v3", credentials=creds)

        channel_response = youtube.channels().list(
            id=channel_id, part="contentDetails"
        ).execute()
        if not channel_response.get("items"):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No YouTube channel found to sync videos.",
            )

        uploads_playlist_id = channel_response["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]

        # Shorts vs long-form: playlist membership + Analytics content type (not duration).
        shorts_ids = _resolve_shorts_ids(creds, youtube, channel_id)

        video_items = []
        next_page_token = None

        while True:
            playlist_response = youtube.playlistItems().list(
                playlistId=uploads_playlist_id,
                part="snippet",
                maxResults=50,
                pageToken=next_page_token,
            ).execute()

            for item in playlist_response.get("items", []):
                snippet = item["snippet"]
                video_items.append(
                    {
                        "id": snippet["resourceId"]["videoId"],
                        "title": snippet["title"],
                        "published_at": snippet["publishedAt"],
                        "thumbnail_url": snippet.get("thumbnails", {}).get("default", {}).get("url"),
                    }
                )

            next_page_token = playlist_response.get("nextPageToken")
            if not next_page_token:
                break

        synced_videos = []
        for i in range(0, len(video_items), 50):
            batch = video_items[i : i + 50]
            batch_ids = [v["id"] for v in batch]

            videos_response = youtube.videos().list(
                id=",".join(batch_ids),
                part="statistics,contentDetails,status",
            ).execute()

            video_data_map = {
                item["id"]: {
                    "statistics": item.get("statistics", {}),
                    "contentDetails": item.get("contentDetails", {}),
                    "status": item.get("status", {}),
                }
                for item in videos_response.get("items", [])
            }

            for video in batch:
                if video["id"] not in video_data_map:
                    continue
                v_data = video_data_map[video["id"]]
                stats = v_data.get("statistics", {})
                content_details = v_data.get("contentDetails", {})
                status_info = v_data.get("status", {})
                privacy_status = (status_info.get("privacyStatus") or "public").lower()

                if privacy_status != "public":
                    continue

                duration = content_details.get("duration", "PT0S")
                duration_seconds = parse_iso8601_duration_to_seconds(duration)

                is_short = video["id"] in shorts_ids
                duration_type = "short" if is_short else "long"
                short_link = (
                    f"https://www.youtube.com/shorts/{video['id']}" if is_short else None
                )

                synced_videos.append(
                    schemas.YouTubeVideoInfo(
                        id=video["id"],
                        title=video["title"],
                        published_at=video["published_at"],
                        thumbnail_url=video["thumbnail_url"],
                        view_count=int(stats.get("viewCount", 0)),
                        like_count=int(stats.get("likeCount", 0)),
                        comment_count=int(stats.get("commentCount", 0)),
                        duration=duration,
                        duration_seconds=duration_seconds,
                        duration_type=duration_type,
                        is_short=is_short,
                        short_link=short_link,
                        privacy_status=privacy_status,
                        notes="",
                        metadata_fields={},
                    )
                )

        return synced_videos
    except HTTPException:
        raise
    except HttpError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Google API Error while syncing videos: {e.reason if hasattr(e, 'reason') else str(e)}",
        )


def fetch_video_snippets(creds, video_ids: list[str]) -> dict[str, dict]:
    """Return id → {title, published_at, is_short?} for missing catalog rows."""
    out: dict[str, dict] = {}
    ids = [vid for vid in video_ids if vid]
    if not ids:
        return out
    try:
        youtube = build("youtube", "v3", credentials=creds)
        for i in range(0, len(ids), 50):
            batch = ids[i : i + 50]
            response = (
                youtube.videos()
                .list(id=",".join(batch), part="snippet,contentDetails")
                .execute()
            )
            for item in response.get("items") or []:
                vid = item.get("id")
                if not vid:
                    continue
                snippet = item.get("snippet") or {}
                out[vid] = {
                    "id": vid,
                    "title": snippet.get("title") or vid,
                    "published_at": snippet.get("publishedAt"),
                }
    except Exception as exc:
        print(f"[youtube] fetch_video_snippets failed: {exc}", flush=True)
    return out

def upload_video_to_youtube(
    creds,
    channel_id: str,
    video_path: str,
    title: str,
    description: str,
    tags: list[str],
    thumbnail_path: str = None
) -> str:
    """
    Uploads a video to YouTube, and sets the thumbnail if provided.
    Returns the uploaded YouTube Video ID.
    """
    try:
        youtube = build("youtube", "v3", credentials=creds)

        body = {
            "snippet": {
                "title": title,
                "description": description,
                "tags": tags,
                "categoryId": "22",  # People & Blogs as default
                "channelId": channel_id
            },
            "status": {
                "privacyStatus": "public",  # Upload as public per user request
                "selfDeclaredMadeForKids": False
            }
        }

        media = MediaFileUpload(video_path, chunksize=-1, resumable=True)
        request = youtube.videos().insert(
            part="snippet,status",
            body=body,
            media_body=media
        )

        response = None
        while response is None:
            status_obj, response = request.next_chunk()

        video_id = response.get("id")

        if video_id and thumbnail_path:
            # Check size and compress if > 2MB
            if os.path.exists(thumbnail_path) and os.path.getsize(thumbnail_path) > 2000000:
                try:
                    from PIL import Image
                    with Image.open(thumbnail_path) as img:
                        # Convert to RGB if PNG with alpha, to save as JPEG
                        if img.mode in ("RGBA", "P"): 
                            img = img.convert("RGB")
                        # Save as compressed JPEG
                        img.save(thumbnail_path, "JPEG", quality=85, optimize=True)
                        
                        # If STILL too big, aggressively resize
                        if os.path.getsize(thumbnail_path) > 2000000:
                            img.thumbnail((1280, 720))
                            img.save(thumbnail_path, "JPEG", quality=75, optimize=True)
                except Exception as e:
                    print(f"Warning: Failed to compress thumbnail: {e}")

            # Set the custom thumbnail
            youtube.thumbnails().set(
                videoId=video_id,
                media_body=MediaFileUpload(thumbnail_path)
            ).execute()

        return video_id
    except HttpError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"YouTube Upload API Error: {e.reason if hasattr(e, 'reason') else str(e)}",
        )
