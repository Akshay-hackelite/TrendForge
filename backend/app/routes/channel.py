from fastapi import APIRouter, Body, Depends, HTTPException, status

from app import schemas
from app.auth import get_current_user
from app.clients import disconnect_channel, set_active_channel
from app.database import (
    fetch_client_doc,
    fetch_user,
    find_client_id_by_channel,
    list_channels_meta,
    update_channel_fields,
)
from app.google_oauth import get_user_google_creds
from app.services.youtube_api import fetch_channel_info

router = APIRouter(tags=["channel"])


def _channel_to_info(channel: dict) -> schemas.YouTubeChannelInfo:
    language = (channel.get("language") or "").strip().lower() or None
    if language not in ("hinglish", "arabic", "russian"):
        language = None
    return schemas.YouTubeChannelInfo(
        id=channel["id"],
        title=channel.get("title") or channel["id"],
        description=channel.get("description", ""),
        custom_url=channel.get("custom_url"),
        published_at=channel.get("published_at") or "",
        view_count=channel.get("view_count", 0),
        subscriber_count=channel.get("subscriber_count", 0),
        video_count=channel.get("video_count", 0),
        language=language,
    )


@router.post("/channel.list", response_model=schemas.YouTubeChannelListResponse)
def channel_list(
    body: schemas.ChannelListRequest = Body(default_factory=schemas.ChannelListRequest),
    current_user: dict = Depends(get_current_user),
):
    username = current_user["username"]
    user = fetch_user(username) or {}
    client_id = body.client_id or user.get("active_client_id")
    if client_id and not fetch_client_doc(client_id, username=username):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Client '{client_id}' not found.",
        )
    channels = [_channel_to_info(c) for c in (list_channels_meta(client_id) if client_id else [])]
    return schemas.YouTubeChannelListResponse(
        channels=channels,
        active_client_id=user.get("active_client_id"),
        active_channel_id=user.get("active_channel_id"),
    )


@router.post("/channel.get", response_model=schemas.YouTubeChannelInfo)
def channel_get(
    body: schemas.ChannelGetRequest = Body(default_factory=schemas.ChannelGetRequest),
    current_user: dict = Depends(get_current_user),
):
    username = current_user["username"]
    user = fetch_user(username) or {}
    client_id = body.client_id or user.get("active_client_id")
    channel_id = body.channel_id or user.get("active_channel_id")
    if not client_id or not channel_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Channel not found.")
    if not fetch_client_doc(client_id, username=username):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Client '{client_id}' not found.",
        )

    channels = {c["id"]: c for c in list_channels_meta(client_id)}
    channel = channels.get(channel_id)
    if not channel:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Channel '{channel_id}' not found.",
        )

    creds = get_user_google_creds(username, client_id, channel_id)
    fresh_info = fetch_channel_info(creds, channel_id)
    update_channel_fields(channel_id, client_id, fresh_info)
    channel.update(fresh_info)
    return _channel_to_info(channel)


@router.post("/channel.select", response_model=schemas.YouTubeChannelListResponse)
def channel_select(
    body: schemas.ChannelSelectRequest,
    current_user: dict = Depends(get_current_user),
):
    username = current_user["username"]
    client_id = body.client_id
    if not client_id:
        client_id = find_client_id_by_channel(username, body.channel_id)
        if not client_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Channel '{body.channel_id}' not found.",
            )

    set_active_channel(username, client_id, body.channel_id)
    user = fetch_user(username) or {}
    channels = [_channel_to_info(c) for c in list_channels_meta(client_id)]
    return schemas.YouTubeChannelListResponse(
        channels=channels,
        active_client_id=user.get("active_client_id"),
        active_channel_id=user.get("active_channel_id"),
    )


@router.post("/channel.disconnect", response_model=schemas.YouTubeChannelListResponse)
def channel_disconnect(
    body: schemas.ChannelDisconnectRequest,
    current_user: dict = Depends(get_current_user),
):
    username = current_user["username"]
    disconnect_channel(username, body.client_id, body.channel_id)
    user = fetch_user(username) or {}
    channels = [_channel_to_info(c) for c in list_channels_meta(body.client_id)]
    return schemas.YouTubeChannelListResponse(
        channels=channels,
        active_client_id=user.get("active_client_id"),
        active_channel_id=user.get("active_channel_id"),
    )


_YT_LANGUAGES = ("hinglish", "arabic", "russian")


@router.post("/channel.set-languages", response_model=schemas.YouTubeChannelListResponse)
def channel_set_languages(
    body: schemas.ChannelSetLanguagesRequest,
    current_user: dict = Depends(get_current_user),
):
    username = current_user["username"]
    client_id = body.client_id
    if not fetch_client_doc(client_id, username=username):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Client '{client_id}' not found.",
        )

    channels = list_channels_meta(client_id)
    known_ids = {c["id"] for c in channels}
    channel_to_lang: dict[str, str] = {}
    for lang in _YT_LANGUAGES:
        for cid in getattr(body.assignments, lang, None) or []:
            if not cid:
                continue
            if cid not in known_ids:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Channel '{cid}' is not linked to this client.",
                )
            previous = channel_to_lang.get(cid)
            if previous and previous != lang:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Channel '{cid}' cannot be assigned to more than one language.",
                )
            channel_to_lang[cid] = lang

    for ch in channels:
        update_channel_fields(
            ch["id"],
            client_id,
            {"language": channel_to_lang.get(ch["id"])},
        )

    user = fetch_user(username) or {}
    return schemas.YouTubeChannelListResponse(
        channels=[_channel_to_info(c) for c in list_channels_meta(client_id)],
        active_client_id=user.get("active_client_id"),
        active_channel_id=user.get("active_channel_id"),
    )
