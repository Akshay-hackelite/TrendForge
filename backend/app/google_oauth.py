import os
from datetime import datetime

os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from jose import JWTError, jwt

from app import schemas
from app.auth import create_access_token, get_current_user
from app.clients import link_channels_to_client
from app.config import settings
from app.database import (
    fetch_channel,
    fetch_client_doc,
    fetch_user,
    find_client_id_by_channel,
    update_channel_fields,
)
from app.services.youtube_api import fetch_all_channels

router = APIRouter(tags=["google-oauth"])

SCOPES = [
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]

_pkce_store: dict = {}


def get_google_flow() -> Flow:
    client_config = {
        "web": {
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }

    flow = Flow.from_client_config(client_config=client_config, scopes=SCOPES)
    flow.redirect_uri = settings.GOOGLE_REDIRECT_URI
    return flow


def _build_credentials(db_creds: dict) -> Credentials:
    return Credentials(
        token=db_creds["token"],
        refresh_token=db_creds.get("refresh_token"),
        token_uri=db_creds["token_uri"],
        client_id=settings.GOOGLE_CLIENT_ID,
        client_secret=settings.GOOGLE_CLIENT_SECRET,
        scopes=db_creds["scopes"],
    )


def _refresh_channel_credentials(
    username: str,
    client_id: str,
    channel: dict,
) -> Credentials:
    channel_id = channel["id"]
    fresh = fetch_channel(channel_id, client_id=client_id, username=username)
    if not fresh:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Channel '{channel_id}' not found.",
        )
    db_creds = dict(fresh.get("google_credentials") or {})

    if not db_creds:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Channel is not linked to Google. Use Link Channel first.",
        )

    needs_refresh = False
    if db_creds.get("expiry"):
        expiry_dt = datetime.fromisoformat(db_creds["expiry"]).replace(tzinfo=None)
        if (expiry_dt - datetime.utcnow()).total_seconds() < 60:
            needs_refresh = True
    else:
        needs_refresh = True

    if not needs_refresh:
        return _build_credentials(db_creds)

    if not db_creds.get("refresh_token"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google session expired. Re-link this channel via YouTube.",
        )

    refresh_creds = Credentials(
        token=None,
        refresh_token=db_creds["refresh_token"],
        token_uri=db_creds["token_uri"],
        client_id=settings.GOOGLE_CLIENT_ID,
        client_secret=settings.GOOGLE_CLIENT_SECRET,
        scopes=db_creds["scopes"],
    )

    try:
        refresh_creds.refresh(Request())
        db_creds["token"] = refresh_creds.token
        if refresh_creds.expiry:
            db_creds["expiry"] = refresh_creds.expiry.replace(tzinfo=None).isoformat()
        update_channel_fields(
            channel_id,
            client_id,
            {"google_credentials": db_creds},
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to refresh Google credentials: {str(e)}",
        )

    return _build_credentials(db_creds)


def get_user_google_creds(
    username: str,
    client_id: str | None = None,
    channel_id: str | None = None,
) -> Credentials:
    user = fetch_user(username)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    cid = client_id or user.get("active_client_id")
    chid = channel_id or user.get("active_channel_id")
    if not chid:
        raise HTTPException(status_code=404, detail="Channel not found")
    if not cid:
        cid = find_client_id_by_channel(username, chid)
    if not cid:
        raise HTTPException(status_code=404, detail="Channel not found")

    channel = fetch_channel(chid, client_id=cid, username=username)
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    return _refresh_channel_credentials(username, cid, channel)


@router.post("/google.login")
def google_login(
    body: schemas.GoogleLoginRequest,
    current_user: dict = Depends(get_current_user),
):
    if not fetch_client_doc(body.client_id, username=current_user["username"]):
        raise HTTPException(status_code=404, detail="Client not found")

    state_token = create_access_token(
        data={
            "sub": current_user["username"],
            "purpose": "google-oauth",
            "client_id": body.client_id,
        }
    )

    flow = get_google_flow()
    authorization_url, state = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        state=state_token,
    )

    code_verifier = (
        getattr(flow, "code_verifier", None)
        or getattr(flow.oauth2session, "code_verifier", None)
        or getattr(flow.oauth2session, "_code_verifier", None)
        or getattr(getattr(flow.oauth2session, "_client", None), "code_verifier", None)
    )

    if code_verifier:
        _pkce_store[state_token] = code_verifier

    return {"authorization_url": authorization_url}


# Google redirects browsers with GET — this cannot be POST.
@router.get("/google.callback")
def google_callback(
    code: str = Query(...),
    state: str = Query(...),
):
    try:
        payload = jwt.decode(state, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        username: str = payload.get("sub")
        purpose: str = payload.get("purpose")
        client_id: str = payload.get("client_id")
        if username is None or purpose != "google-oauth" or not client_id:
            raise HTTPException(status_code=400, detail="Invalid state token parameters")
    except JWTError:
        raise HTTPException(status_code=400, detail="State token validation failed")

    if not fetch_user(username):
        raise HTTPException(status_code=404, detail="User not found")
    if not fetch_client_doc(client_id, username=username):
        raise HTTPException(status_code=404, detail="Client not found")

    code_verifier = _pkce_store.pop(state, None)

    flow = get_google_flow()
    try:
        if code_verifier:
            flow.fetch_token(code=code, code_verifier=code_verifier)
        else:
            flow.fetch_token(code=code)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to fetch token from Google: {str(e)}")

    credentials = flow.credentials
    temp_creds = Credentials(
        token=credentials.token,
        refresh_token=credentials.refresh_token,
        token_uri=credentials.token_uri,
        client_id=settings.GOOGLE_CLIENT_ID,
        client_secret=settings.GOOGLE_CLIENT_SECRET,
        scopes=credentials.scopes,
    )

    channel_infos = fetch_all_channels(temp_creds)

    refresh_token = credentials.refresh_token
    expiry_str = credentials.expiry.isoformat() if credentials.expiry else None

    google_credentials = {
        "token": credentials.token,
        "refresh_token": refresh_token,
        "token_uri": credentials.token_uri,
        "scopes": list(credentials.scopes) if credentials.scopes else SCOPES,
        "expiry": expiry_str,
    }

    link_channels_to_client(username, client_id, channel_infos, google_credentials)

    frontend = settings.FRONTEND_URL.rstrip("/")
    return RedirectResponse(url=f"{frontend}/?google_auth=success")
