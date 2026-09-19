from __future__ import annotations

import base64
import json
import mimetypes
import random
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode

import httpx
import holidays
from fastapi import APIRouter, Depends, HTTPException, Query, status, Request, UploadFile, File, Form
from fastapi.responses import FileResponse, RedirectResponse

from app import schemas
from app.auth import get_current_user
from app.config import settings
from app.database import (
    delete_social_post,
    fetch_client_bundle,
    fetch_social_post,
    fetch_social_posts_for_source,
    fetch_scheduled_posts,
    fetch_all_clients,
    fetch_latest_draft_post,
    fetch_social_schedule,
    save_social_schedule,
    get_instagram_app_config,
    get_instagram_connection,
    mark_social_post_selected,
    pop_instagram_oauth_state,
    save_instagram_oauth_state,
    save_instagram_app_config,
    save_instagram_connection,
    get_facebook_app_config,
    get_facebook_connection,
    pop_facebook_oauth_state,
    save_facebook_app_config,
    save_facebook_connection,
    save_facebook_oauth_state,
    save_social_post,
)
from app.services.gcs_storage import upload_bytes, delete_file

router = APIRouter(tags=["social"])
PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
SOCIAL_ASSETS_DIR = Path(__file__).resolve().parent.parent.parent / "social_assets"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# Extra metadata so the Festive Posts UI can split Auto vs Manual sections
# without parsing topic_id. 9 AM auto-publish still keys off topic_id
# (festival_YYYY-MM-DD), not this field.
ORIGIN_CRON_FESTIVAL = "cron-festival"
ORIGIN_MANUAL_FESTIVAL = "manual-festival"


def _india_festivals(year: int):
    return holidays.country_holidays("IN", years=year, categories=("public", "optional"))


def _festival_origin_for_topic(topic_id: str | None, incoming: str | None = None) -> str:
    # Prefer the origin sent on regenerate so the post stays in the same UI section.
    if incoming in {ORIGIN_CRON_FESTIVAL, ORIGIN_MANUAL_FESTIVAL}:
        return incoming
    tid = topic_id or ""
    if tid.startswith("festival_manual_"):
        return ORIGIN_MANUAL_FESTIVAL
    # Missing origin on old date-based drafts (e.g. Janmashtami) counts as auto.
    return ORIGIN_CRON_FESTIVAL


def _read_prompt(name: str) -> str:
    try:
        return (PROMPTS_DIR / name).read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _require_client(username: str, client_id: str) -> dict:
    client = fetch_client_bundle(client_id, username, with_videos=False)
    if not client:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")
    return client


def _instagram_config_response(client_id: str) -> schemas.InstagramConfigResponse:
    config = get_instagram_app_config(client_id) or {}
    connection = get_instagram_connection(client_id) or {}
    return schemas.InstagramConfigResponse(
        client_id=client_id,
        app_id=config.get("app_id"),
        has_app_secret=bool(config.get("app_secret")),
        redirect_uri=settings.INSTAGRAM_REDIRECT_URI,
        connection=schemas.InstagramConnectionSummary(
            connected=bool(connection.get("access_token") and connection.get("instagram_user_id")),
            instagram_user_id=connection.get("instagram_user_id"),
            instagram_username=connection.get("instagram_username"),
            token_expires_at=connection.get("token_expires_at"),
            connected_at=connection.get("connected_at"),
        ),
    )


def _current_suggestions(client: dict) -> dict:
    coverage = client.get("content_topic_coverage") or {}
    suggestions = client.get("content_suggestions") or {}
    return {
        **suggestions,
        "keyword_analysis": suggestions.get("keyword_analysis")
        or coverage.get("keyword_analysis")
        or [],
    }


def _scripted_items(client: dict) -> list[dict]:
    items = []
    for row in (_current_suggestions(client).get("items") or []):
        if not isinstance(row, dict) or not (row.get("script") or "").strip():
            continue
        items.append(
            {
                "id": row.get("id") or "",
                "topic_id": row.get("topic_id"),
                "topic_text": row.get("topic_text") or row.get("working_title") or "Untitled",
                "recommendation_score": float(row.get("recommendation_score") or 0),
                "format": row.get("format"),
                "video_type": row.get("video_type"),
                "title_en": row.get("title_en"),
                "title_hinglish": row.get("title_hinglish"),
                "working_title": row.get("working_title"),
                "script": row.get("script") or "",
            }
        )
    return items


def _recommended_keywords(client: dict) -> list[dict]:
    out = []
    seen: set[str] = set()
    for row in _current_suggestions(client).get("keyword_analysis") or []:
        if not isinstance(row, dict):
            continue
        topic_id = row.get("topic_id") or ""
        score = float(row.get("recommendation_score") or 0)
        if not topic_id or topic_id in seen or score < 50:
            continue
        seen.add(topic_id)
        out.append(
            {
                "topic_id": topic_id,
                "topic_text": row.get("topic_text") or "",
                "recommendation_score": score,
                "weight": row.get("weight") or "medium",
            }
        )
    out.sort(key=lambda item: item["recommendation_score"], reverse=True)
    return out


def _weighted_sample(items: list[dict], count: int) -> list[dict]:
    count = max(1, min(int(count or 1), len(items)))
    pool = list(items)
    selected = []
    for _ in range(count):
        total = sum(max(0.01, float(item.get("recommendation_score") or 0)) for item in pool)
        pick = random.uniform(0, total)
        upto = 0.0
        chosen_idx = 0
        for idx, item in enumerate(pool):
            upto += max(0.01, float(item.get("recommendation_score") or 0))
            if upto >= pick:
                chosen_idx = idx
                break
        selected.append(pool.pop(chosen_idx))
    return selected


async def _build_brief(
    *,
    client: dict,
    topic_text: str,
    script: str | None = None,
    custom_prompt: str | None = None,
    festive: bool = False,
) -> dict:
    name = client.get("doctor_name") or client.get("name") or ""
    specialty = client.get("specialty") or ""
    
    # Fallback default structure if AI fails
    brief = {
        "headline": topic_text[:46],
        "subheadline": f"A quick {specialty} insight",
        "supporting_text": "A concise educational post.",
        "caption": "",
        "cta": "Save this post and consult a professional.",
    }

    if settings.OPENAI_API_KEY:
        prompt_file = "instagram_festive_brief.txt" if festive else "instagram_post_brief.txt"
        system_prompt = _read_prompt(prompt_file)
        system_prompt += f"\nClient: {name}, Specialty: {specialty}\nTopic: {topic_text}"
        if script:
            system_prompt += f"\nScript/Source Content: {script}"
        
        system_prompt += "\nIMPORTANT: The user may provide custom instructions intended for the IMAGE generation (e.g. 'make the image background blue'). If their instruction is explicitly about creating or editing the image, completely ignore it. Only apply instructions that make sense for writing the text content."
        
        user_prompt = custom_prompt if custom_prompt else "Generate the JSON brief."
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as http_client:
                resp = await http_client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
                    json={
                        "model": "gpt-4o",
                        "response_format": { "type": "json_object" },
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt}
                        ],
                        "max_tokens": 500,
                        "temperature": 0.7
                    }
                )
                if resp.is_success:
                    payload = resp.json()
                    content = payload["choices"][0]["message"]["content"]
                    parsed = json.loads(content)
                    # Merge parsed fields with the fallback structure
                    for key in brief:
                        if key in parsed and isinstance(parsed[key], str):
                            brief[key] = parsed[key].strip()
        except Exception as e:
            print(f"Failed to generate brief via AI: {e}")

    return brief


def _require_instagram_connection(client_id: str) -> dict:
    connection = get_instagram_connection(client_id) or {}
    if not connection.get("instagram_user_id") or not connection.get("access_token"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Please connect Instagram first from Social Media → Instagram Connection, "
                "then generate the post."
            ),
        )
    return connection


def _posts_for_source(body: schemas.SocialPostVersionsRequest) -> list[dict]:
    if body.source_type == "script":
        if not body.content_plan_item_id:
            return []
        return fetch_social_posts_for_source(
            body.client_id,
            content_plan_item_id=body.content_plan_item_id,
        )
    if body.source_type in {"manual_pick", "smart_pick"}:
        if not body.topic_id:
            return []
        return fetch_social_posts_for_source(body.client_id, topic_id=body.topic_id)
    return []


def _current_version(posts: list[dict]) -> dict | None:
    selected = next((post for post in posts if post.get("is_selected")), None)
    return selected or (posts[0] if posts else None)


def _remove_local_social_asset(post: dict) -> None:
    image_url = post.get("image_url") or ""
    
    if image_url.startswith("https://storage.googleapis.com/"):
        blob_path = image_url.split("https://storage.googleapis.com/")[-1].split("/", 1)[-1]
        delete_file(blob_path)
        return

    prefix = "/social.asset/"
    if not image_url.startswith(prefix):
        return
    filename = image_url.removeprefix(prefix)
    if "/" in filename or "\\" in filename:
        return
    path = SOCIAL_ASSETS_DIR / filename
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


async def _refresh_instagram_token_if_needed(client_id: str, connection: dict) -> dict:
    expires_at = _parse_dt(connection.get("token_expires_at"))
    issued_at = _parse_dt(connection.get("token_issued_at") or connection.get("connected_at"))
    now = datetime.now(timezone.utc)
    if not expires_at:
        return connection
    if expires_at <= now:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Instagram token expired. Reconnect Instagram from Social Media → Instagram Connection.",
        )
    if expires_at - now > timedelta(days=7):
        return connection
    if issued_at and now - issued_at < timedelta(hours=24):
        return connection

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                "https://graph.instagram.com/refresh_access_token",
                params={
                    "grant_type": "ig_refresh_token",
                    "access_token": connection["access_token"],
                },
            )
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Instagram token refresh failed. Reconnect Instagram from "
                "Social Media → Instagram Connection."
            ),
        ) from exc

    expires_in = int(data.get("expires_in") or 5184000)
    refreshed = {
        **connection,
        "access_token": data.get("access_token") or connection["access_token"],
        "token_type": data.get("token_type") or connection.get("token_type") or "bearer",
        "token_issued_at": now.isoformat(),
        "token_expires_at": (now + timedelta(seconds=expires_in)).isoformat(),
        "token_refreshed_at": now.isoformat(),
    }
    return save_instagram_connection(client_id, refreshed)


async def _fetch_instagram_media(client_id: str, limit: int = 12, after: str = None) -> tuple[list[dict], list[dict], str | None]:
    connection = await _refresh_instagram_token_if_needed(
        client_id,
        _require_instagram_connection(client_id),
    )
    ig_user_id = connection["instagram_user_id"]
    access_token = connection["access_token"]
    
    media = []
    references = []
    next_cursor = after
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            while len(media) < limit:
                params = {
                    "access_token": access_token,
                    "limit": 50,
                    "fields": "id,media_type,media_url,thumbnail_url,permalink,timestamp,caption",
                }
                if next_cursor:
                    params["after"] = next_cursor
                    
                response = await client.get(
                    f"https://graph.instagram.com/{ig_user_id}/media",
                    params=params,
                )
                response.raise_for_status()
                data = response.json()
                rows = data.get("data") or []
                paging = data.get("paging") or {}
                
                if not rows:
                    break
                    
                next_cursor = paging.get("cursors", {}).get("after")
                
                for row in rows:
                    if row.get("media_type") not in {"IMAGE", "CAROUSEL_ALBUM"}:
                        continue
                        
                    item = {
                        "id": row.get("id") or "",
                        "media_type": row.get("media_type"),
                        "media_url": row.get("media_url"),
                        "thumbnail_url": row.get("thumbnail_url"),
                        "permalink": row.get("permalink"),
                        "timestamp": row.get("timestamp"),
                        "caption": row.get("caption"),
                        "selected_as_reference": False,
                    }
                    if item["id"]:
                        media.append(item)
                    if (
                        len(references) < 3
                        and item["id"]
                        and (item["media_url"] or item["thumbnail_url"])
                    ):
                        references.append({**item, "selected_as_reference": True})
                        
                    if len(media) >= limit:
                        break
                        
                if not next_cursor:
                    break
                    
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to fetch Instagram media: {exc}",
        ) from exc

    return media, references, next_cursor


async def _download_reference_images(references: list[dict]) -> list[tuple[str, tuple[str, bytes, str]]]:
    files: list[tuple[str, tuple[str, bytes, str]]] = []
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        for ref in references:
            url = ref.get("media_url") or ref.get("thumbnail_url")
            if not url:
                continue
            try:
                response = await client.get(url)
                response.raise_for_status()
            except httpx.HTTPError:
                continue
            content_type = response.headers.get("content-type", "image/jpeg").split(";")[0]
            if not content_type.startswith("image/"):
                continue
            ext = mimetypes.guess_extension(content_type) or ".jpg"
            files.append(("image[]", (f"{ref.get('id') or uuid.uuid4()}{ext}", response.content, content_type)))
    return files


def _image_prompt(*, client: dict, brief: dict, references: list[dict], custom_prompt: str = None) -> str:
    reference_lines = "\n".join(
        f"- {ref.get('id')}: {ref.get('media_type')} {ref.get('permalink') or ''}".strip()
        for ref in references
    )
    parts = [
        _read_prompt("instagram_image_generation.txt"),
        "Client profile:",
        f"Name: {client.get('name') or 'Client'}",
        f"Specialty: {client.get('specialty') or ''}",
        f"Designation: {client.get('designation') or ''}",
        "Approved post brief:",
        f"Headline: {brief.get('headline')}",
        f"Subheadline: {brief.get('subheadline')}",
        f"Supporting text: {brief.get('supporting_text')}",
        f"CTA: {brief.get('cta')}",
        "Reference Instagram media:",
        reference_lines or "No reference metadata available.",
        (
            "Create a square Instagram post. Use the supplied reference images as the client's "
            "primary visual identity. Use exactly the approved copy above for any text shown "
            "inside the image."
        ),
    ]
    if custom_prompt:
        parts.extend([
            "User Custom Instructions:",
            custom_prompt
        ])
    return "\n\n".join(part for part in parts if part)


async def _generate_social_image(
    *,
    client: dict,
    brief: dict,
    references: list[dict],
    post_id: str,
    custom_prompt: str = None,
) -> tuple[str, dict]:
    if not settings.OPENAI_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OPENAI_API_KEY is missing, so image generation cannot run.",
        )

    files = await _download_reference_images(references)
    if not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No suitable Instagram reference images could be downloaded.",
        )

    data = {
        "model": settings.OPENAI_IMAGE_MODEL,
        "prompt": _image_prompt(client=client, brief=brief, references=references, custom_prompt=custom_prompt),
        "size": "1024x1024",
        "quality": "medium",
        "n": "1",
        "output_format": "png",
    }
    try:
        async with httpx.AsyncClient(timeout=180.0) as http_client:
            response = await http_client.post(
                "https://api.openai.com/v1/images/edits",
                headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
                data=data,
                files=files,
            )
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text[:500] if exc.response is not None else str(exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"OpenAI image generation failed: {detail}",
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"OpenAI image generation failed: {exc}",
        ) from exc

    image_row = (payload.get("data") or [{}])[0]
    image_bytes = None
    if image_row.get("b64_json"):
        image_bytes = base64.b64decode(image_row["b64_json"])
    elif image_row.get("url"):
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as http_client:
            image_response = await http_client.get(image_row["url"])
            image_response.raise_for_status()
            image_bytes = image_response.content
    if not image_bytes:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="OpenAI did not return image data.",
        )

    filename = f"{post_id.replace(':', '-')}.png"
    try:
        public_url = upload_bytes("generated_images", filename, image_bytes)
        return public_url, payload
    except Exception as e:
        # Fallback to local if GCS fails or isn't configured
        print(f"GCS upload failed: {e}. Falling back to local disk.")
        SOCIAL_ASSETS_DIR.mkdir(parents=True, exist_ok=True)
        path = SOCIAL_ASSETS_DIR / filename
        path.write_bytes(image_bytes)
        return f"/social.asset/{filename}", payload


@router.post("/social.instagram-config.get", response_model=schemas.InstagramConfigResponse)
def instagram_config_get(
    body: schemas.SocialClientRequest,
    current_user: dict = Depends(get_current_user),
):
    _require_client(current_user["username"], body.client_id)
    return _instagram_config_response(body.client_id)


@router.post("/social.instagram-config.save", response_model=schemas.InstagramConfigResponse)
def instagram_config_save(
    body: schemas.InstagramConfigSaveRequest,
    current_user: dict = Depends(get_current_user),
):
    _require_client(current_user["username"], body.client_id)
    app_id = (body.app_id or "").strip()
    app_secret = (body.app_secret or "").strip()
    if not app_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Instagram App ID is required")
    save_instagram_app_config(
        body.client_id,
        app_id=app_id,
        app_secret=app_secret or None,
    )
    return _instagram_config_response(body.client_id)


@router.post("/social.instagram.analytics.get")
async def instagram_analytics_get(
    body: schemas.InstagramAnalyticsRequest,
    current_user: dict = Depends(get_current_user),
):
    _require_client(current_user["username"], body.client_id)
    from app.services.instagram_analytics import (
        MAX_ANALYTICS_DAYS,
        clamp_analytics_window,
        fetch_plug_analytics,
    )

    connection = get_instagram_connection(body.client_id) or {}
    connection = await _refresh_instagram_token_if_needed(body.client_id, connection)
    connected = bool(connection.get("access_token") and connection.get("instagram_user_id"))

    now = datetime.now(timezone.utc)
    try:
        if body.since and body.until:
            since_dt = datetime.strptime(body.since, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            until_dt = datetime.strptime(body.until, "%Y-%m-%d").replace(
                tzinfo=timezone.utc, hour=23, minute=59, second=59
            )
            since_dt, until_dt = clamp_analytics_window(since_dt, until_dt)
        else:
            days = 7
            if isinstance(body.days, int):
                days = max(2, min(MAX_ANALYTICS_DAYS, body.days))
            since_dt = now - timedelta(days=days)
            until_dt = now
            since_dt, until_dt = clamp_analytics_window(since_dt, until_dt)
    except (ValueError, TypeError):
        since_dt = now - timedelta(days=7)
        until_dt = now

    metrics = None
    time_series = None
    views_by_follow_type = None
    views_by_content_type = None
    interactions_by_content_type = None
    reels = []
    reel_summary = None
    if connected:
        try:
            payload = await fetch_plug_analytics(
                ig_id=connection["instagram_user_id"],
                token=connection["access_token"],
                since_dt=since_dt,
                until_dt=until_dt,
            )
            metrics = payload.get("metrics")
            time_series = payload.get("time_series")
            views_by_follow_type = payload.get("views_by_follow_type")
            views_by_content_type = payload.get("views_by_content_type")
            interactions_by_content_type = payload.get("interactions_by_content_type")
            reels = payload.get("reels") or []
            reel_summary = payload.get("reel_summary")
        except Exception as exc:
            print(f"[instagram-analytics] client={body.client_id}: {exc}", flush=True)

        if not metrics:
            metrics = {
                "reach": 0,
                "accounts_engaged": 0,
                "total_interactions": 0,
                "views": 0,
                "saves": 0,
                "likes": 0,
                "comments": 0,
                "shares": 0,
                "profile_views": 0,
                "website_clicks": 0,
                "follows_and_unfollows": 0,
                "profile_links_taps": 0,
            }

    return {
        "instagram_connected": connected,
        "instagram": connection.get("instagram_username") or "",
        "placeholder": not bool(metrics) and connected,
        "since": since_dt.strftime("%Y-%m-%d"),
        "until": until_dt.strftime("%Y-%m-%d"),
        "message": (
            "Instagram insights will show here after the connection is live."
            if connected
            else "Connect Instagram to unlock analytics."
        ),
        "metrics": metrics,
        "time_series": time_series,
        "views_by_follow_type": views_by_follow_type,
        "views_by_content_type": views_by_content_type,
        "interactions_by_content_type": interactions_by_content_type,
        "reels": reels,
        "reel_summary": reel_summary,
    }


@router.post("/social.instagram.connect-url", response_model=schemas.InstagramConnectUrlResponse)
def instagram_connect_url(
    body: schemas.SocialClientRequest,
    current_user: dict = Depends(get_current_user),
):
    _require_client(current_user["username"], body.client_id)
    config = get_instagram_app_config(body.client_id) or {}
    if not config.get("app_id") or not config.get("app_secret"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Save this client's Instagram App ID and App Secret first.",
        )

    state = str(uuid.uuid4())
    save_instagram_oauth_state(
        state,
        {
            "client_id": body.client_id,
            "username": current_user["username"],
            "created_at": _now_iso(),
        },
    )
    params = {
        "client_id": config["app_id"],
        "redirect_uri": settings.INSTAGRAM_REDIRECT_URI,
        "state": state,
        "scope": settings.INSTAGRAM_OAUTH_SCOPES,
        "response_type": "code",
        "force_reauth": "true",
    }
    url = f"https://www.instagram.com/oauth/authorize?{urlencode(params)}"
    return schemas.InstagramConnectUrlResponse(authorization_url=url, state=state)


@router.get("/social.instagram.callback")
async def instagram_callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error_message: str | None = Query(default=None),
):
    if error_message:
        return RedirectResponse(f"{settings.FRONTEND_URL}/clients?instagram_auth=error")
    if not code or not state:
        return RedirectResponse(f"{settings.FRONTEND_URL}/clients?instagram_auth=missing")

    state_row = pop_instagram_oauth_state(state)
    if not state_row:
        return RedirectResponse(f"{settings.FRONTEND_URL}/clients?instagram_auth=state")

    client_id = state_row.get("client_id")
    username = state_row.get("username")
    config = get_instagram_app_config(client_id) or {}
    if not client_id or not username or not config.get("app_id") or not config.get("app_secret"):
        return RedirectResponse(f"{settings.FRONTEND_URL}/clients?instagram_auth=config")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            short_resp = await client.post(
                "https://api.instagram.com/oauth/access_token",
                data={
                    "client_id": config["app_id"],
                    "client_secret": config["app_secret"],
                    "grant_type": "authorization_code",
                    "redirect_uri": settings.INSTAGRAM_REDIRECT_URI,
                    "code": code,
                },
            )
            short_resp.raise_for_status()
            short_data = short_resp.json()
            short_token = short_data.get("access_token")
            if not short_token:
                raise ValueError("Instagram did not return a short-lived access token")

            long_resp = await client.get(
                "https://graph.instagram.com/access_token",
                params={
                    "grant_type": "ig_exchange_token",
                    "client_secret": config["app_secret"],
                    "access_token": short_token,
                },
            )
            long_resp.raise_for_status()
            long_data = long_resp.json()
            access_token = long_data.get("access_token")
            if not access_token:
                raise ValueError("Instagram did not return a long-lived access token")

            account_resp = await client.get(
                "https://graph.instagram.com/me",
                params={
                    "access_token": access_token,
                    "fields": "id,username,account_type",
                },
            )
            account_resp.raise_for_status()
            account = account_resp.json()

        now = datetime.now(timezone.utc)
        expires_in = int(long_data.get("expires_in") or 5184000)
        expires_at = (now + timedelta(seconds=expires_in)).isoformat()

        save_instagram_connection(
            client_id,
            {
                "username": username,
                "instagram_user_id": account.get("id") or str(short_data.get("user_id") or ""),
                "instagram_username": account.get("username"),
                "account_type": account.get("account_type"),
                "access_token": access_token,
                "token_type": long_data.get("token_type") or "bearer",
                "token_issued_at": now.isoformat(),
                "token_expires_at": expires_at,
                "connected_at": now.isoformat(),
                "permissions": short_data.get("permissions") or [],
            },
        )
        return RedirectResponse(
            f"{settings.FRONTEND_URL}/clients/{client_id}/social/instagram?instagram_auth=success"
        )
    except (httpx.HTTPError, ValueError) as exc:
        print(f"[instagram] callback failed client={client_id}: {exc}", flush=True)
        return RedirectResponse(
            f"{settings.FRONTEND_URL}/clients/{client_id}/social/instagram?instagram_auth=error"
        )

def _facebook_config_response(client_id: str) -> schemas.FacebookConfigResponse:
    config = get_facebook_app_config(client_id) or {}
    connection = get_facebook_connection(client_id) or {}
    return schemas.FacebookConfigResponse(
        app_id=config.get("app_id"),
        redirect_uri=settings.FACEBOOK_REDIRECT_URI,
        connection=schemas.FacebookConnectionSummary(
            connected=bool(connection.get("access_token") and connection.get("facebook_user_id")),
            facebook_user_id=connection.get("facebook_user_id"),
            facebook_username=connection.get("facebook_username"),
            selected_page_id=connection.get("selected_page_id"),
            selected_page_name=connection.get("selected_page_name"),
        ),
    )


@router.post("/social.facebook-config.get", response_model=schemas.FacebookConfigResponse)
def facebook_config_get(
    body: schemas.SocialClientRequest,
    current_user: dict = Depends(get_current_user),
):
    _require_client(current_user["username"], body.client_id)
    return _facebook_config_response(body.client_id)


@router.post("/social.facebook-config.save", response_model=schemas.FacebookConfigResponse)
def facebook_config_save(
    body: schemas.FacebookConfigSaveRequest,
    current_user: dict = Depends(get_current_user),
):
    _require_client(current_user["username"], body.client_id)
    app_id = (body.app_id or "").strip()
    app_secret = (body.app_secret or "").strip()
    if not app_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Facebook App ID is required")
    save_facebook_app_config(
        body.client_id,
        {"app_id": app_id, "app_secret": app_secret or None},
    )
    return _facebook_config_response(body.client_id)


@router.post("/social.facebook.connect-url", response_model=schemas.FacebookConnectUrlResponse)
def facebook_connect_url(
    body: schemas.SocialClientRequest,
    current_user: dict = Depends(get_current_user),
):
    _require_client(current_user["username"], body.client_id)
    config = get_facebook_app_config(body.client_id) or {}
    if not config.get("app_id") or not config.get("app_secret"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Save this client's Facebook App ID and App Secret first.",
        )

    state = str(uuid.uuid4())
    save_facebook_oauth_state(
        state,
        {
            "client_id": body.client_id,
            "username": current_user["username"],
            "created_at": _now_iso(),
        },
    )
    params = {
        "client_id": config["app_id"],
        "redirect_uri": settings.FACEBOOK_REDIRECT_URI,
        "state": state,
        "scope": settings.FACEBOOK_OAUTH_SCOPES,
        "response_type": "code",
    }
    url = f"https://www.facebook.com/v18.0/dialog/oauth?{urlencode(params)}"
    return schemas.FacebookConnectUrlResponse(authorization_url=url, state=state)


@router.get("/social.facebook.callback")
async def facebook_callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error_message: str | None = Query(default=None),
):
    if error_message:
        return RedirectResponse(f"{settings.FRONTEND_URL}/clients?facebook_auth=error")
    if not code or not state:
        return RedirectResponse(f"{settings.FRONTEND_URL}/clients?facebook_auth=missing")

    state_row = pop_facebook_oauth_state(state)
    if not state_row:
        return RedirectResponse(f"{settings.FRONTEND_URL}/clients?facebook_auth=state")

    client_id = state_row.get("client_id")
    username = state_row.get("username")
    config = get_facebook_app_config(client_id) or {}
    if not client_id or not username or not config.get("app_id") or not config.get("app_secret"):
        return RedirectResponse(f"{settings.FRONTEND_URL}/clients?facebook_auth=config")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            token_resp = await client.get(
                "https://graph.facebook.com/v18.0/oauth/access_token",
                params={
                    "client_id": config["app_id"],
                    "redirect_uri": settings.FACEBOOK_REDIRECT_URI,
                    "client_secret": config["app_secret"],
                    "code": code,
                },
            )
            token_resp.raise_for_status()
            token_data = token_resp.json()
            short_token = token_data.get("access_token")
            if not short_token:
                raise ValueError("Facebook did not return an access token")

            long_resp = await client.get(
                "https://graph.facebook.com/v18.0/oauth/access_token",
                params={
                    "grant_type": "fb_exchange_token",
                    "client_id": config["app_id"],
                    "client_secret": config["app_secret"],
                    "fb_exchange_token": short_token,
                },
            )
            long_resp.raise_for_status()
            long_data = long_resp.json()
            access_token = long_data.get("access_token") or short_token
            
            me_resp = await client.get(
                "https://graph.facebook.com/me",
                params={
                    "access_token": access_token,
                    "fields": "id,name",
                },
            )
            me_resp.raise_for_status()
            me_data = me_resp.json()

        now = datetime.now(timezone.utc)
        expires_in = int(long_data.get("expires_in") or 5184000)
        expires_at = (now + timedelta(seconds=expires_in)).isoformat()

        save_facebook_connection(
            client_id,
            {
                "username": username,
                "facebook_user_id": me_data.get("id"),
                "facebook_username": me_data.get("name"),
                "selected_page_id": None,
                "selected_page_name": None,
                "access_token": access_token,
                "token_type": "bearer",
                "token_issued_at": now.isoformat(),
                "token_expires_at": expires_at,
                "connected_at": now.isoformat(),
            },
        )
        return RedirectResponse(
            f"{settings.FRONTEND_URL}/clients/{client_id}/social/facebook?facebook_auth=success"
        )
    except (httpx.HTTPError, ValueError) as exc:
        print(f"[facebook] callback failed client={client_id}: {exc}", flush=True)
        return RedirectResponse(
            f"{settings.FRONTEND_URL}/clients/{client_id}/social/facebook?facebook_auth=error"
        )


@router.post("/social.facebook.pages.get")
async def facebook_pages_get(
    body: schemas.SocialClientRequest,
    current_user: dict = Depends(get_current_user),
):
    _require_client(current_user["username"], body.client_id)
    connection = get_facebook_connection(body.client_id) or {}
    access_token = connection.get("access_token")
    if not access_token:
        raise HTTPException(status_code=400, detail="Facebook not connected")

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://graph.facebook.com/v18.0/me/accounts",
                params={"access_token": access_token},
            )
            resp.raise_for_status()
            data = resp.json()
            pages = data.get("data", [])
            return {"pages": pages}
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=500, detail=f"Failed to fetch Facebook pages: {exc}")


@router.post("/social.facebook.page.select", response_model=schemas.FacebookConfigResponse)
def facebook_page_select(
    body: schemas.FacebookPageSelectRequest,
    current_user: dict = Depends(get_current_user),
):
    _require_client(current_user["username"], body.client_id)
    connection = get_facebook_connection(body.client_id) or {}
    if not connection.get("access_token"):
        raise HTTPException(status_code=400, detail="Facebook not connected")

    connection["selected_page_id"] = body.page_id
    connection["selected_page_name"] = body.page_name
    connection["page_access_token"] = body.page_access_token
    save_facebook_connection(body.client_id, connection)

    return _facebook_config_response(body.client_id)


@router.post("/social.facebook.disconnect", response_model=schemas.FacebookConfigResponse)
def facebook_disconnect(
    body: schemas.SocialClientRequest,
    current_user: dict = Depends(get_current_user),
):
    _require_client(current_user["username"], body.client_id)
    save_facebook_connection(body.client_id, {})
    return _facebook_config_response(body.client_id)


@router.post("/social.instagram.media.get", response_model=schemas.InstagramMediaResponse)
async def instagram_media_get(
    body: schemas.SocialInstagramMediaRequest,
    current_user: dict = Depends(get_current_user),
):
    _require_client(current_user["username"], body.client_id)
    media, references, next_cursor = await _fetch_instagram_media(body.client_id, limit=body.limit, after=body.after)
    return schemas.InstagramMediaResponse(
        media=[schemas.InstagramMediaItem(**item) for item in media],
        reference_media=[schemas.InstagramMediaItem(**item) for item in references],
        next_cursor=next_cursor,
    )


@router.post("/social.instagram.media.upload")
async def instagram_media_upload(
    client_id: str = Form(...),
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    _require_client(current_user["username"], client_id)
    
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image.")
        
    ext = mimetypes.guess_extension(file.content_type) or ".jpg"
    # Ensure supported extension
    if ext not in [".png", ".jpg", ".jpeg", ".webp"]:
        ext = ".jpg"
        
    filename = f"upload_{uuid.uuid4().hex}{ext}"
    content = await file.read()
    
    try:
        public_url = upload_bytes("uploads", filename, content, content_type=file.content_type)
        return {"url": public_url}
    except Exception as e:
        print(f"GCS upload failed: {e}. Falling back to local disk.")
        uploads_dir = SOCIAL_ASSETS_DIR / "uploads"
        uploads_dir.mkdir(parents=True, exist_ok=True)
        path = uploads_dir / filename
        with open(path, "wb") as f:
            f.write(content)
        base_url = settings.BASE_URL.rstrip('/')
        return {"url": f"{base_url}/social.asset/uploads/{filename}"}


@router.get("/social.asset/{file_path:path}")
def social_asset(file_path: str):
    allowed_exts = (".png", ".jpg", ".jpeg", ".webp")
    if ".." in file_path or not file_path.lower().endswith(allowed_exts):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")
    path = SOCIAL_ASSETS_DIR / file_path
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")
    
    ext = path.suffix.lower()
    media_type = "image/png" if ext == ".png" else "image/jpeg"
    if ext == ".webp":
        media_type = "image/webp"
        
    return FileResponse(path, media_type=media_type)


@router.post("/social.post-sources.get", response_model=schemas.SocialPostSourcesResponse)
def social_post_sources_get(
    body: schemas.SocialClientRequest,
    current_user: dict = Depends(get_current_user),
):
    client = _require_client(current_user["username"], body.client_id)
    suggestions = _current_suggestions(client)
    return schemas.SocialPostSourcesResponse(
        client_id=body.client_id,
        scripts_generated_at=suggestions.get("scripts_generated_at"),
        scripted_items=[schemas.SocialScriptedItem(**item) for item in _scripted_items(client)],
        recommended_keywords=[
            schemas.SocialKeywordItem(**item) for item in _recommended_keywords(client)
        ],
    )


@router.post("/social.keywords.pick", response_model=schemas.SocialKeywordPickResponse)
def social_keywords_pick(
    body: schemas.SocialKeywordPickRequest,
    current_user: dict = Depends(get_current_user),
):
    client = _require_client(current_user["username"], body.client_id)
    keywords = _recommended_keywords(client)
    if not keywords:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No recommendation keywords found with score >= 50.",
        )
    return schemas.SocialKeywordPickResponse(
        selected_keywords=[
            schemas.SocialKeywordItem(**item) for item in _weighted_sample(keywords, body.count)
        ]
    )


@router.post("/social.posts.source.get", response_model=schemas.SocialPostVersionsResponse)
def social_posts_source_get(
    body: schemas.SocialPostVersionsRequest,
    current_user: dict = Depends(get_current_user),
):
    _require_client(current_user["username"], body.client_id)
    posts = _posts_for_source(body)
    current = _current_version(posts)
    return schemas.SocialPostVersionsResponse(
        posts=[schemas.SocialPostDraft(**post) for post in posts],
        current_post=schemas.SocialPostDraft(**current) if current else None,
    )


@router.post("/social.post.select", response_model=schemas.SocialPostVersionsResponse)
def social_post_select(
    body: schemas.SocialPostActionRequest,
    current_user: dict = Depends(get_current_user),
):
    _require_client(current_user["username"], body.client_id)
    post = fetch_social_post(body.post_id)
    if not post or post.get("client_id") != body.client_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Generated post not found")
    selected = mark_social_post_selected(body.post_id)
    if not selected:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Generated post not found")
    source_body = schemas.SocialPostVersionsRequest(
        client_id=body.client_id,
        source_type=selected.get("source_type") or "manual_pick",
        content_plan_item_id=selected.get("content_plan_item_id"),
        topic_id=selected.get("topic_id"),
    )
    posts = _posts_for_source(source_body)
    current = _current_version(posts)
    return schemas.SocialPostVersionsResponse(
        posts=[schemas.SocialPostDraft(**post) for post in posts],
        current_post=schemas.SocialPostDraft(**current) if current else None,
    )


@router.post("/social.post.delete", response_model=schemas.SocialPostVersionsResponse)
def social_post_delete(
    body: schemas.SocialPostActionRequest,
    current_user: dict = Depends(get_current_user),
):
    _require_client(current_user["username"], body.client_id)
    post = fetch_social_post(body.post_id)
    if not post or post.get("client_id") != body.client_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Generated post not found")
    source_body = schemas.SocialPostVersionsRequest(
        client_id=body.client_id,
        source_type=post.get("source_type") or "manual_pick",
        content_plan_item_id=post.get("content_plan_item_id"),
        topic_id=post.get("topic_id"),
    )
    deleted = delete_social_post(body.post_id)
    if deleted:
        _remove_local_social_asset(deleted)
    posts = _posts_for_source(source_body)
    current = _current_version(posts)
    return schemas.SocialPostVersionsResponse(
        posts=[schemas.SocialPostDraft(**row) for row in posts],
        current_post=schemas.SocialPostDraft(**current) if current else None,
    )


@router.post("/social.post-draft.generate", response_model=schemas.SocialPostDraftResponse)
async def social_post_draft_generate(
    body: schemas.SocialPostDraftGenerateRequest,
    current_user: dict = Depends(get_current_user),
):
    client = _require_client(current_user["username"], body.client_id)
    _require_instagram_connection(body.client_id)
    source_type = (body.source_type or "").strip()
    script = None
    topic_id = None
    topic_text = None
    content_plan_item_id = None
    generation_origin = None
    festive_prompt = body.custom_prompt

    if source_type == "script":
        if not body.content_plan_item_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Select a script first")
        match = next(
            (item for item in _scripted_items(client) if item["id"] == body.content_plan_item_id),
            None,
        )
        if not match:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Script item not found")
        script = match.get("script")
        topic_id = match.get("topic_id")
        topic_text = match.get("topic_text")
        content_plan_item_id = match.get("id")
    elif source_type in {"smart_pick", "manual_pick"}:
        if not body.topic_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Select a keyword first")
        match = next((item for item in _recommended_keywords(client) if item["topic_id"] == body.topic_id), None)
        if not match:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Keyword not found")
        topic_id = match.get("topic_id")
        topic_text = match.get("topic_text")
        scripted_match = next((item for item in _scripted_items(client) if item.get("topic_id") == topic_id), None)
        if scripted_match:
            script = scripted_match.get("script")
            content_plan_item_id = scripted_match.get("id")
    elif source_type == "festival":
        custom_prompt = (body.custom_prompt or "").strip()
        incoming_topic_id = (body.topic_id or "").strip()
        is_regenerate = bool(incoming_topic_id)
        if not is_regenerate and not custom_prompt:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Enter festival instructions first.",
            )
        if is_regenerate:
            topic_id = incoming_topic_id
            topic_text = (body.topic_text or custom_prompt or "Festive Post").strip()
            # Keep origin so regenerate stays in Auto vs Manual section without parsing ids.
            generation_origin = _festival_origin_for_topic(topic_id, body.generation_origin)
        else:
            topic_id = f"festival_manual_{uuid.uuid4()}"
            topic_text = custom_prompt
            generation_origin = ORIGIN_MANUAL_FESTIVAL
        festive_prompt = custom_prompt or f"Create a very engaging and celebratory post for {topic_text}."
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid source type")

    post_id = f"social:{uuid.uuid4()}"
    media, auto_references, _ = await _fetch_instagram_media(body.client_id)
    
    references = []
    if body.reference_media_ids or body.reference_image_urls:
        if body.reference_media_ids:
            for m in media:
                if m["id"] in body.reference_media_ids:
                    references.append({**m, "selected_as_reference": True})
        if body.reference_image_urls:
            urls = [url.strip() for url in body.reference_image_urls.split(",") if url.strip()]
            for url in urls:
                references.append({"id": str(uuid.uuid4()), "media_url": url, "selected_as_reference": True})
    else:
        references = auto_references

    if not references:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No suitable static Instagram posts found for style references.",
        )
    brief = await _build_brief(
        client=client, 
        topic_text=topic_text or "Untitled", 
        script=script, 
        custom_prompt=festive_prompt if source_type == "festival" else body.custom_prompt,
        festive=source_type == "festival",
    )
    image_url, image_payload = await _generate_social_image(
        client=client,
        brief=brief,
        references=references,
        post_id=post_id,
        custom_prompt=festive_prompt if source_type == "festival" else body.custom_prompt,
    )
    payload = {
            "client_id": body.client_id,
            "platform": "instagram",
            "source_type": source_type,
            "topic_id": topic_id,
            "topic_text": topic_text or "Untitled",
            "content_plan_item_id": content_plan_item_id,
            "brief": brief,
            "image_status": "ready",
            "image_model": settings.OPENAI_IMAGE_MODEL,
            "image_url": image_url,
            "reference_media_ids": [ref.get("id") for ref in references if ref.get("id")],
            "reference_media": references,
            "openai_image_usage": image_payload.get("usage"),
            "instagram_media_count": len(media),
            "status": "draft",
            "publish_status": "draft",
            "publish_targets": ["instagram"],
            "queue_order": None,
            "created_at": _now_iso(),
        }
    if generation_origin:
        # Extra metadata for Festive Posts sections (UI does not parse topic_id).
        payload["generation_origin"] = generation_origin
    post = save_social_post(post_id, payload)
    post = mark_social_post_selected(post_id) or post
    return schemas.SocialPostDraftResponse(post=schemas.SocialPostDraft(**post))
@router.post("/social.post.publish")
async def social_post_publish(
    request: Request,
    body: schemas.SocialPostPublishRequest,
    current_user: dict = Depends(get_current_user),
):
    client = _require_client(current_user["username"], body.client_id)
    
    if not body.targets:
        body.targets = ["instagram"]
        
    if "instagram" in body.targets:
        _require_instagram_connection(body.client_id)
    if "facebook" in body.targets:
        conn = get_facebook_connection(body.client_id)
        if not conn or not conn.get("access_token") or not conn.get("selected_page_id"):
            raise HTTPException(status_code=400, detail="Facebook Page is not connected.")
    
    post = fetch_social_post(body.post_id)
    if not post or post.get("client_id") != body.client_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Generated post not found")
        
    image_url_path = post.get("image_url")
    if not image_url_path:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Post does not have an image yet")
        
    conn = get_instagram_connection(body.client_id)
    access_token = conn["access_token"]
    ig_user_id = conn["instagram_user_id"]
    
    # Construct full public URL for the image
    # Use the domain from BASE_URL (which could be an ngrok URL in local testing)
    # If it's already a full URL (like GCS), use it directly
    if image_url_path.startswith("http"):
        full_image_url = image_url_path
    else:
        # Fallback for local assets
        base_url = settings.BASE_URL.rstrip('/')
        if "api" not in image_url_path:
            full_image_url = f"{base_url}/api{image_url_path}"
        else:
            full_image_url = f"{base_url}{image_url_path}"
        
        # Bypass for local development using catbox.moe
        if "ngrok" in base_url or "localhost" in base_url:
            local_path = Path("social_assets") / Path(image_url_path).name
            if local_path.exists():
                async with httpx.AsyncClient() as c:
                    with open(local_path, "rb") as f:
                        up_resp = await c.post(
                            "https://catbox.moe/user/api.php",
                            data={"reqtype": "fileupload"},
                            files={"fileToUpload": f},
                            timeout=30.0
                        )
                        if up_resp.is_success and up_resp.text.startswith("http"):
                            full_image_url = up_resp.text.strip()
        
    async with httpx.AsyncClient(timeout=60.0) as http_client:
        ig_post_id = None
        fb_post_id = None
        ig_permalink = ""
        fb_permalink = ""
        
        if "instagram" in body.targets:
            conn = get_instagram_connection(body.client_id)
            access_token = conn["access_token"]
            ig_user_id = conn["instagram_user_id"]
            
            media_resp = await http_client.post(
                f"https://graph.instagram.com/{ig_user_id}/media",
                data={
                    "image_url": full_image_url,
                    "caption": body.caption,
                    "access_token": access_token,
                },
            )
            if not media_resp.is_success:
                raise HTTPException(status_code=502, detail=f"Instagram media upload failed: {media_resp.text[:500]}")
                
            creation_id = media_resp.json().get("id")
            if not creation_id:
                raise HTTPException(status_code=502, detail="Instagram media upload failed: No creation ID returned.")
                
            import asyncio
            max_retries = 3
            for attempt in range(max_retries):
                publish_resp = await http_client.post(
                    f"https://graph.instagram.com/{ig_user_id}/media_publish",
                    data={
                        "creation_id": creation_id,
                        "access_token": access_token,
                    },
                )
                if publish_resp.is_success:
                    break
                try:
                    err_data = publish_resp.json().get("error", {})
                    if err_data.get("code") == 9007 or err_data.get("error_subcode") == 2207027:
                        if attempt < max_retries - 1:
                            await asyncio.sleep(3)
                            continue
                except Exception:
                    pass
                break
                
            if not publish_resp.is_success:
                raise HTTPException(status_code=502, detail=f"Instagram publish failed: {publish_resp.text[:500]}")
            ig_post_id = publish_resp.json().get("id")
            if ig_post_id:
                permalink_resp = await http_client.get(
                    f"https://graph.instagram.com/{ig_post_id}",
                    params={"fields": "permalink", "access_token": access_token},
                )
                if permalink_resp.is_success:
                    ig_permalink = (permalink_resp.json() or {}).get("permalink") or ""

        if "facebook" in body.targets:
            fb_conn = get_facebook_connection(body.client_id)
            fb_access_token = fb_conn["page_access_token"]
            page_id = fb_conn["selected_page_id"]
            
            fb_resp = await http_client.post(
                f"https://graph.facebook.com/v18.0/{page_id}/photos",
                data={
                    "url": full_image_url,
                    "message": body.caption,
                    "access_token": fb_access_token,
                    "published": "true",
                },
            )
            if not fb_resp.is_success:
                raise HTTPException(status_code=502, detail=f"Facebook publish failed: {fb_resp.text[:500]}")
            fb_post_id = fb_resp.json().get("id")
            if fb_post_id:
                permalink_resp = await http_client.get(
                    f"https://graph.facebook.com/v18.0/{fb_post_id}",
                    params={"fields": "permalink_url", "access_token": fb_access_token},
                )
                if permalink_resp.is_success:
                    fb_permalink = (permalink_resp.json() or {}).get("permalink_url") or ""
                if not fb_permalink:
                    if "_" in str(fb_post_id):
                        fb_permalink = f"https://www.facebook.com/{fb_post_id}"
                    else:
                        fb_permalink = f"https://www.facebook.com/{page_id}_{fb_post_id}"
    
    post["publish_status"] = "published"
    post["publish_targets"] = body.targets
    if ig_post_id:
        post["instagram_post_id"] = ig_post_id
        post["instagram_permalink"] = ig_permalink or post.get("instagram_permalink")
    if fb_post_id:
        post["facebook_post_id"] = fb_post_id
        post["facebook_permalink"] = fb_permalink or post.get("facebook_permalink")
    save_social_post(body.post_id, post)

    from app.routes.tracker import sync_social_publish_to_tracker
    sync_social_publish_to_tracker(
        body.client_id,
        {**post, "id": body.post_id},
        year=body.year,
        month=body.month,
        week=body.week,
    )
    
    schedule = fetch_social_schedule(body.client_id)
    if schedule:
        from datetime import datetime, timezone
        schedule["last_posted_date"] = datetime.now(timezone.utc).isoformat()
        save_social_schedule(body.client_id, schedule)
        
    return {
        "status": "published",
        "instagram_post_id": ig_post_id,
        "facebook_post_id": fb_post_id,
        "instagram_permalink": ig_permalink or None,
        "facebook_permalink": fb_permalink or None,
    }

@router.post("/social.schedule.save", response_model=schemas.SocialScheduleResponse)
async def social_schedule_save(
    body: schemas.SocialScheduleSaveRequest,
    current_user: dict = Depends(get_current_user),
):
    _require_client(current_user["username"], body.client_id)
    existing = fetch_social_schedule(body.client_id) or {}
    doc = {
        "frequency": body.frequency,
        "selected_days": body.selected_days,
        "auto_fallback": body.auto_fallback,
        "facebook_auto_publish": body.facebook_auto_publish,
        "festive_auto_publish": body.festive_auto_publish,
        "festive_facebook_auto_publish": body.festive_facebook_auto_publish,
        "posts_per_day": body.posts_per_day,
    }
    if "last_posted_date" in existing:
        doc["last_posted_date"] = existing["last_posted_date"]
    save_social_schedule(body.client_id, doc)
    return schemas.SocialScheduleResponse(**doc)

@router.post("/social.schedule.get", response_model=schemas.SocialScheduleResponse)
async def social_schedule_get(
    body: schemas.SocialPostActionRequest,
    current_user: dict = Depends(get_current_user),
):
    _require_client(current_user["username"], body.client_id)
    doc = fetch_social_schedule(body.client_id)
    if doc:
        return schemas.SocialScheduleResponse(**doc)
    return schemas.SocialScheduleResponse()

@router.post("/social.post.queue.add", response_model=schemas.SocialPostDraftResponse)
async def social_post_queue_add(
    body: schemas.SocialPostQueueAddRequest,
    current_user: dict = Depends(get_current_user),
):
    _require_client(current_user["username"], body.client_id)
    post = fetch_social_post(body.post_id)
    if not post or post.get("client_id") != body.client_id:
        raise HTTPException(status_code=404, detail="Post not found")
    
    queued_posts = fetch_scheduled_posts(body.client_id)
    max_order = max([p.get("queue_order", 0) for p in queued_posts] + [0])
    
    post["publish_status"] = "scheduled"
    post["publish_targets"] = body.targets
    post["queue_order"] = max_order + 1
    post = save_social_post(body.post_id, post)
    return schemas.SocialPostDraftResponse(post=schemas.SocialPostDraft(**post))


@router.post("/social.post.queue.add_bulk", response_model=schemas.SocialPostVersionsResponse)
async def social_post_queue_add_bulk(
    body: schemas.SocialPostQueueAddBulkRequest,
    current_user: dict = Depends(get_current_user),
):
    _require_client(current_user["username"], body.client_id)
    
    queued_posts = fetch_scheduled_posts(body.client_id)
    max_order = max([p.get("queue_order", 0) for p in queued_posts] + [0])
    
    updated_posts = []
    for post_id in body.post_ids:
        post = fetch_social_post(post_id)
        if not post or post.get("client_id") != body.client_id:
            continue
        max_order += 1
        post["publish_status"] = "scheduled"
        post["publish_targets"] = body.targets
        post["queue_order"] = max_order
        post = save_social_post(post_id, post)
        updated_posts.append(post)
        
    return schemas.SocialPostVersionsResponse(posts=[schemas.SocialPostDraft(**p) for p in updated_posts])


@router.post("/social.post.targets.update", response_model=schemas.SocialPostDraftResponse)
async def social_post_targets_update(
    body: schemas.SocialPostTargetsUpdateRequest,
    current_user: dict = Depends(get_current_user),
):
    _require_client(current_user["username"], body.client_id)
    post = fetch_social_post(body.post_id)
    if not post or post.get("client_id") != body.client_id:
        raise HTTPException(status_code=404, detail="Post not found")
        
    post["publish_targets"] = body.targets
    
    # If no targets are left, we remove it from queue and set to draft
    if not body.targets:
        post["publish_status"] = "draft"
        post["queue_order"] = None
    elif post.get("publish_status") != "scheduled":
        # If adding targets to a draft, ensure it gets a queue_order
        post["publish_status"] = "scheduled"
        if not post.get("queue_order"):
            queued_posts = fetch_scheduled_posts(body.client_id)
            max_order = max([p.get("queue_order", 0) for p in queued_posts] + [0])
            post["queue_order"] = max_order + 1
            
    post = save_social_post(body.post_id, post)
    return schemas.SocialPostDraftResponse(post=schemas.SocialPostDraft(**post))

@router.post("/social.post.queue.list", response_model=schemas.SocialPostVersionsResponse)
async def social_post_queue_list(
    body: schemas.SocialPostActionRequest,
    current_user: dict = Depends(get_current_user),
):
    _require_client(current_user["username"], body.client_id)
    queued = fetch_scheduled_posts(body.client_id)
    return schemas.SocialPostVersionsResponse(posts=[schemas.SocialPostDraft(**p) for p in queued])

@router.post("/social.post.queue.remove", response_model=schemas.SocialPostDraftResponse)
async def social_post_queue_remove(
    body: schemas.SocialPostQueueRemoveRequest,
    current_user: dict = Depends(get_current_user),
):
    _require_client(current_user["username"], body.client_id)
    post = fetch_social_post(body.post_id)
    if not post or post.get("client_id") != body.client_id:
        raise HTTPException(status_code=404, detail="Post not found")
        
    post["publish_status"] = "draft"
    post["queue_order"] = None
    post = save_social_post(body.post_id, post)
    return schemas.SocialPostDraftResponse(post=schemas.SocialPostDraft(**post))

@router.post("/social.post.queue.reorder")
async def social_post_queue_reorder(
    body: schemas.SocialPostQueueReorderRequest,
    current_user: dict = Depends(get_current_user),
):
    _require_client(current_user["username"], body.client_id)
    for index, pid in enumerate(body.ordered_post_ids):
        post = fetch_social_post(pid)
        if post and post.get("client_id") == body.client_id:
            post["queue_order"] = index + 1
            save_social_post(pid, post)
    return {"status": "ok"}

@router.post("/social.post.queue.edit", response_model=schemas.SocialPostDraftResponse)
async def social_post_queue_edit(
    body: schemas.SocialPostQueueEditRequest,
    current_user: dict = Depends(get_current_user),
):
    _require_client(current_user["username"], body.client_id)
    post = fetch_social_post(body.post_id)
    if not post or post.get("client_id") != body.client_id:
        raise HTTPException(status_code=404, detail="Post not found")
        
    if "brief" not in post:
        post["brief"] = {}
    post["brief"]["caption"] = body.caption
    post = save_social_post(body.post_id, post)
    return schemas.SocialPostDraftResponse(post=schemas.SocialPostDraft(**post))

@router.post("/social.festivals.get", response_model=schemas.SocialPostVersionsResponse)
async def social_festivals_get(
    body: schemas.SocialInstagramMediaRequest,
    current_user: dict = Depends(get_current_user),
):
    _require_client(current_user["username"], body.client_id)
    # Fetch all drafts where source_type == 'festival'
    query = {"client_id": body.client_id, "source_type": "festival"}
    from app.database import _use_mongo, _mdb, COL_SOCIAL_POSTS, _strip_mongo_id, _load_file
    posts = []
    if _use_mongo():
        cursor = _mdb()[COL_SOCIAL_POSTS].find(query).sort("created_at", -1)
        for doc in cursor:
            posts.append({"id": doc["_id"], **_strip_mongo_id(doc)})
    else:
        all_posts = (_load_file().get(COL_SOCIAL_POSTS) or {}).values()
        for post in all_posts:
            if isinstance(post, dict) and post.get("client_id") == body.client_id and post.get("source_type") == "festival":
                posts.append({"id": post["id"], **post})
        posts.sort(key=lambda x: x.get("created_at") or "", reverse=True)
        
    return schemas.SocialPostVersionsResponse(
        posts=[schemas.SocialPostDraft(**p) for p in posts],
        current_post=None
    )

@router.post("/cron/social.generate-festivals")
async def cron_social_generate_festivals(request: Request):
    """
    The Generator Cron (1 AM): Its only job is to generate the image/caption and save it as a draft in your database. 
    It never publishes anything. It just prepares the post while everyone is sleeping so it's ready to go.
    """
    secret = request.headers.get("X-Cron-Secret")
    if not secret or secret != "gravity-cron-secret":
        raise HTTPException(status_code=401, detail="Unauthorized cron trigger")

    ist_tz = timezone(timedelta(hours=5, minutes=30))
    tomorrow = datetime.now(ist_tz) + timedelta(days=1)
    
    in_holidays = _india_festivals(tomorrow.year)
    festival_name = in_holidays.get(tomorrow.date())
    print(
        f"[festive-cron] tomorrow={tomorrow.date()} festival={festival_name or 'none'}",
        flush=True,
    )
    
    if not festival_name:
        print("[festive-cron] skipped: not a festival tomorrow", flush=True)
        return {"status": "skipped", "reason": "Not a festival tomorrow"}
        
    generated_count = 0
    clients = fetch_all_clients()
    for client in clients:
        cid = client.get("id")
        if not cid: continue
        
        # Check if we already generated a post for this festival
        topic_id = f"festival_{tomorrow.strftime('%Y-%m-%d')}"
        existing = fetch_social_posts_for_source(cid, topic_id=topic_id)
        if existing:
            continue
            
        try:
            # Generate the festive post
            media, auto_references, _ = await _fetch_instagram_media(cid, limit=3)
            if not auto_references:
                continue
                
            brief = await _build_brief(
                client=client,
                topic_text=f"{festival_name} Festival",
                custom_prompt=f"Create a very engaging and celebratory post for {festival_name}.",
                festive=True,
            )
            post_id = f"social:{uuid.uuid4()}"
            image_url, image_payload = await _generate_social_image(
                client=client,
                brief=brief,
                references=auto_references,
                post_id=post_id,
                custom_prompt=f"Create a very engaging and celebratory post for {festival_name}.",
            )
            
            post = {
                "id": post_id,
                "client_id": cid,
                "platform": "instagram",
                "source_type": "festival",
                "topic_id": topic_id,
                "topic_text": f"{festival_name} Festival",
                "brief": brief,
                "image_url": image_url,
                "image_generation_payload": image_payload,
                "publish_status": "draft",
                "publish_targets": ["instagram"],
                "created_at": _now_iso(),
                # Extra metadata for Festive Posts sections (UI does not parse topic_id).
                "generation_origin": ORIGIN_CRON_FESTIVAL,
            }
            save_social_post(post_id, post)
            generated_count += 1
        except Exception as e:
            print(f"Failed to generate festive post for {cid}: {e}", flush=True)
            
    print(
        f"[festive-cron] generated_count={generated_count} festival={festival_name}",
        flush=True,
    )
    return {"status": "success", "generated_count": generated_count, "festival": festival_name}

async def _publish_post_internal(request: Request, cid: str, target_post: dict) -> bool:
    try:
        targets = target_post.get("publish_targets") or ["instagram"]
        image_url_path = target_post.get("image_url")
        if not image_url_path:
            return False
            
        base_url = str(request.base_url).rstrip("/")
        if "api" not in image_url_path:
            full_image_url = f"{base_url}/api{image_url_path}"
        else:
            full_image_url = f"{base_url}{image_url_path}"
            
        if "ngrok" in base_url or "localhost" in base_url:
            from pathlib import Path
            local_path = Path("social_assets") / Path(image_url_path).name
            if local_path.exists():
                async with httpx.AsyncClient() as c:
                    with open(local_path, "rb") as f:
                        up_resp = await c.post(
                            "https://catbox.moe/user/api.php",
                            data={"reqtype": "fileupload"},
                            files={"fileToUpload": f},
                            timeout=30.0
                        )
                        if up_resp.is_success and up_resp.text.startswith("http"):
                            full_image_url = up_resp.text.strip()

        async with httpx.AsyncClient(timeout=60.0) as http_client:
            success_count = 0
            
            ig_post_id = None
            ig_permalink = ""
            fb_post_id = None
            fb_permalink = ""

            if "instagram" in targets:
                conn = get_instagram_connection(cid)
                if conn and conn.get("access_token"):
                    access_token = conn["access_token"]
                    ig_user_id = conn["instagram_user_id"]
                    
                    media_resp = await http_client.post(
                        f"https://graph.instagram.com/{ig_user_id}/media",
                        data={
                            "image_url": full_image_url,
                            "caption": target_post.get("brief", {}).get("caption", ""),
                            "access_token": access_token,
                        },
                    )
                    if media_resp.is_success:
                        creation_id = media_resp.json().get("id")
                        if creation_id:
                            import asyncio
                            max_retries = 3
                            for attempt in range(max_retries):
                                publish_resp = await http_client.post(
                                    f"https://graph.instagram.com/{ig_user_id}/media_publish",
                                    data={
                                        "creation_id": creation_id,
                                        "access_token": access_token,
                                    },
                                )
                                if publish_resp.is_success:
                                    success_count += 1
                                    ig_post_id = publish_resp.json().get("id")
                                    if ig_post_id:
                                        permalink_resp = await http_client.get(
                                            f"https://graph.instagram.com/{ig_post_id}",
                                            params={"fields": "permalink", "access_token": access_token},
                                        )
                                        if permalink_resp.is_success:
                                            ig_permalink = (permalink_resp.json() or {}).get("permalink") or ""
                                    break
                                try:
                                    err = publish_resp.json().get("error", {})
                                    if err.get("code") == 9007 or err.get("error_subcode") == 2207027:
                                        if attempt < max_retries - 1:
                                            await asyncio.sleep(3)
                                            continue
                                except Exception:
                                    pass
                                break
                                
            if "facebook" in targets:
                fb_conn = get_facebook_connection(cid)
                if fb_conn and fb_conn.get("page_access_token") and fb_conn.get("selected_page_id"):
                    fb_access_token = fb_conn["page_access_token"]
                    page_id = fb_conn["selected_page_id"]
                    
                    fb_resp = await http_client.post(
                        f"https://graph.facebook.com/v18.0/{page_id}/photos",
                        data={
                            "url": full_image_url,
                            "message": target_post.get("brief", {}).get("caption", ""),
                            "access_token": fb_access_token,
                            "published": "true",
                        },
                    )
                    if fb_resp.is_success:
                        success_count += 1
                        fb_post_id = fb_resp.json().get("id")
                        if fb_post_id:
                            permalink_resp = await http_client.get(
                                f"https://graph.facebook.com/v18.0/{fb_post_id}",
                                params={"fields": "permalink_url", "access_token": fb_access_token},
                            )
                            if permalink_resp.is_success:
                                fb_permalink = (permalink_resp.json() or {}).get("permalink_url") or ""
                            if not fb_permalink:
                                if "_" in str(fb_post_id):
                                    fb_permalink = f"https://www.facebook.com/{fb_post_id}"
                                else:
                                    fb_permalink = f"https://www.facebook.com/{page_id}_{fb_post_id}"
            
            if success_count > 0:
                target_post["publish_status"] = "published"
                if ig_post_id:
                    target_post["instagram_post_id"] = ig_post_id
                    target_post["instagram_permalink"] = ig_permalink or target_post.get("instagram_permalink")
                if fb_post_id:
                    target_post["facebook_post_id"] = fb_post_id
                    target_post["facebook_permalink"] = fb_permalink or target_post.get("facebook_permalink")
                save_social_post(target_post["id"], target_post)
                from app.routes.tracker import sync_social_publish_to_tracker
                sync_social_publish_to_tracker(cid, target_post)
                return True
            return False
    except Exception as e:
        print(f"Failed to publish internal {cid}: {e}")
        return False


@router.post("/cron/social.publish-scheduled")
async def cron_social_publish_scheduled(request: Request, force: bool = False):
    """
    If force=true is passed, the cron script deliberately skips the "did we already post today?" check and runs anyway. However, after it successfully finishes publishing, it will still update the last_posted_date to the current timestampThis means the system stays perfectly consistent, but you, the developer, retain full manual override control!.
    """
    secret = request.headers.get("X-Cron-Secret")
    if not secret or secret != "gravity-cron-secret":
        raise HTTPException(status_code=401, detail="Unauthorized cron trigger")

    ist_tz = timezone(timedelta(hours=5, minutes=30))
    today = datetime.now(ist_tz)
    day_name = today.strftime("%A")
    published_count = 0

    clients = fetch_all_clients()
    for client in clients:
        cid = client.get("id")
        if not cid: continue
        
        schedule = fetch_social_schedule(cid)
        if not schedule:
            continue
            
        in_holidays = _india_festivals(today.year)
        festival_name = in_holidays.get(today.date())
        print(
            f"[festive-publish] today={today.date()} festival={festival_name or 'none'} client={cid}",
            flush=True,
        )
        
        # FESTIVE OVERRIDE LOGIC
        if festival_name and (schedule.get("festive_auto_publish") or schedule.get("festive_facebook_auto_publish")):
            # 9 AM publishes by date topic_id only (festival_YYYY-MM-DD).
            # Manual drafts use festival_manual_* so they never match.
            topic_id = f"festival_{today.strftime('%Y-%m-%d')}"
            festive_posts = fetch_social_posts_for_source(cid, topic_id=topic_id)
            target_post = next((p for p in festive_posts if p.get("publish_status") == "draft"), None)
            
            if target_post:
                print(
                    f"[festive-publish] publishing cron draft {target_post.get('id')} for client={cid}",
                    flush=True,
                )
                targets = []
                if schedule.get("festive_auto_publish"): targets.append("instagram")
                if schedule.get("festive_facebook_auto_publish"): targets.append("facebook")
                target_post["publish_targets"] = targets

                success = await _publish_post_internal(request, cid, target_post)
                if success:
                    published_count += 1
                    schedule["last_posted_date"] = today.isoformat()
                    save_social_schedule(cid, schedule)
            else:
                print(
                    f"[festive-publish] no cron draft to auto-publish for client={cid}",
                    flush=True,
                )
                    
        if schedule.get("frequency") in ["off", None]:
            continue
            
        freq = schedule.get("frequency")
        days = schedule.get("selected_days", [])
        
        should_publish = False
        if freq == "daily":
            should_publish = True
        elif freq == "weekdays" and today.weekday() < 5:
            should_publish = True
        elif freq in ["once_a_week", "twice_a_week"] and day_name in days:
            should_publish = True
            
        if not should_publish:
            continue
            
        last_posted = schedule.get("last_posted_date")
        if not force and last_posted and last_posted.startswith(today.strftime("%Y-%m-%d")):
            continue
            
        posts_per_day = int(schedule.get("posts_per_day", 1))
        
        for _ in range(posts_per_day):
            target_post = None
            queued = fetch_scheduled_posts(cid)
            if queued:
                target_post = queued[0]
            elif schedule.get("auto_fallback") or schedule.get("facebook_auto_publish"):
                target_post = fetch_latest_draft_post(cid)
                if target_post:
                    targets = []
                    if schedule.get("auto_fallback"): targets.append("instagram")
                    if schedule.get("facebook_auto_publish"): targets.append("facebook")
                    target_post["publish_targets"] = targets
                
            if not target_post:
                break
                
            success = await _publish_post_internal(request, cid, target_post)
            if success:
                published_count += 1
                schedule["last_posted_date"] = today.isoformat()
                save_social_schedule(cid, schedule)

    return {"status": "success", "published_count": published_count}
