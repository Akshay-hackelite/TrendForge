from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt

from app import schemas
from app.config import settings
from app.database import (
    fetch_user,
    insert_user,
    list_channel_summaries,
    list_clients_for_user,
)
from app.services.topics import normalize_topics

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth.login")

router = APIRouter(tags=["auth"])


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception:
        return False


def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


async def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = schemas.TokenData(username=username)
    except JWTError:
        raise credentials_exception

    user = fetch_user(token_data.username)
    if user is None:
        raise credentials_exception
    return user


@router.post("/auth.register", response_model=schemas.UserResponse, status_code=status.HTTP_201_CREATED)
def register(user_in: schemas.UserCreate):
    if fetch_user(user_in.username):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered",
        )

    hashed_pwd = get_password_hash(user_in.password)
    new_user = {
        "username": user_in.username,
        "hashed_password": hashed_pwd,
        "is_active": True,
        "clients": [],
        "active_client_id": None,
        "active_channel_id": None,
    }
    insert_user(new_user)

    return schemas.UserResponse(
        username=new_user["username"],
        is_active=new_user["is_active"],
        has_clients=False,
        active_client_id=None,
        active_channel_id=None,
        clients=[],
        channels=[],
    )


@router.post("/auth.login", response_model=schemas.Token)
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user = fetch_user(form_data.username)
    if not user or not verify_password(form_data.password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect username or password",
        )
    if not user.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled",
        )

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user["username"]}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/auth.me", response_model=schemas.UserResponse)
def read_users_me(current_user: dict = Depends(get_current_user)):
    username = current_user["username"]
    user = fetch_user(username) or current_user
    light_clients = list_clients_for_user(username, with_topics=True)
    clients = [
        schemas.ClientSummary(
            id=c["id"],
            name=c.get("name") or "Google Account",
            channel_count=int(c.get("channel_count") or len(c.get("channels") or [])),
            website_url=c.get("website_url"),
            specialty=c.get("specialty"),
            designation=c.get("designation"),
            description=c.get("description"),
            reference_youtube_channel=c.get("reference_youtube_channel"),
            topics=[schemas.TopicItem(**t) for t in normalize_topics(c.get("topics"))],
        )
        for c in light_clients
    ]
    active_client_id = user.get("active_client_id")
    channels = [
        schemas.ChannelSummary(id=c["id"], title=c.get("title") or c["id"])
        for c in (list_channel_summaries(active_client_id) if active_client_id else [])
    ]
    return schemas.UserResponse(
        username=user["username"],
        is_active=user["is_active"],
        has_clients=len(clients) > 0,
        active_client_id=active_client_id,
        active_channel_id=user.get("active_channel_id"),
        clients=clients,
        channels=channels,
    )
