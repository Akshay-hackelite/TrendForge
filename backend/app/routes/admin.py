"""Internal admin dashboard endpoints — gated by ADMIN_PASSWORD env var."""

from fastapi import APIRouter, HTTPException, status

from app import schemas
from app.auth import get_password_hash
from app.config import settings
from app.database import (
    COL_CHANNELS,
    COL_CLIENTS,
    COL_USERS,
    delete_user,
    fetch_user,
    insert_user,
    list_clients_for_user,
    mongo_db,
    update_user_fields,
    _use_mongo,
)

router = APIRouter(tags=["admin"])


def _require_admin(admin_password: str) -> None:
    expected = (settings.ADMIN_PASSWORD or "").strip()
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ADMIN_PASSWORD is not configured on the server",
        )
    if admin_password != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin password",
        )


def _require_mongo() -> None:
    if not _use_mongo():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MongoDB is required (set MONGODB_URI).",
        )


def _user_summary_from_counts(
    username: str, is_active: bool, client_count: int, channel_count: int
) -> schemas.AdminUserSummary:
    return schemas.AdminUserSummary(
        username=username,
        is_active=is_active,
        client_count=client_count,
        channel_count=channel_count,
    )


def _user_summary(user: dict) -> schemas.AdminUserSummary:
    username = user["username"]
    clients = list_clients_for_user(username, with_topics=False)
    channel_count = sum(int(c.get("channel_count") or 0) for c in clients)
    return _user_summary_from_counts(
        username,
        bool(user.get("is_active", True)),
        len(clients),
        channel_count,
    )


@router.post("/admin.unlock")
def admin_unlock(body: schemas.AdminAuthRequest):
    _require_admin(body.admin_password)
    return {"ok": True}


@router.post("/admin.users.list", response_model=schemas.AdminUserListResponse)
def admin_list_users(body: schemas.AdminAuthRequest):
    _require_admin(body.admin_password)
    _require_mongo()
    mdb = mongo_db()
    users: list[schemas.AdminUserSummary] = []
    for udoc in mdb[COL_USERS].find():
        username = udoc["_id"]
        client_count = mdb[COL_CLIENTS].count_documents({"username": username})
        channel_count = mdb[COL_CHANNELS].count_documents({"username": username})
        users.append(
            _user_summary_from_counts(
                username,
                bool(udoc.get("is_active", True)),
                client_count,
                channel_count,
            )
        )
    users.sort(key=lambda u: u.username.lower())
    return schemas.AdminUserListResponse(users=users)


@router.post("/admin.users.create", response_model=schemas.AdminUserSummary, status_code=status.HTTP_201_CREATED)
def admin_create_user(body: schemas.AdminUserCreateRequest):
    _require_admin(body.admin_password)
    _require_mongo()
    username = (body.username or "").strip()
    password = body.password or ""
    if not username:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username is required")
    if len(password) < 4:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 4 characters",
        )

    if fetch_user(username):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered",
        )

    new_user = {
        "username": username,
        "hashed_password": get_password_hash(password),
        "is_active": True,
        "clients": [],
        "active_client_id": None,
        "active_channel_id": None,
    }
    insert_user(new_user)
    return _user_summary(new_user)


@router.post("/admin.users.delete")
def admin_delete_user(body: schemas.AdminUserDeleteRequest):
    _require_admin(body.admin_password)
    _require_mongo()
    username = (body.username or "").strip()
    if not username:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username is required")

    if not delete_user(username):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return {"ok": True, "username": username}


@router.post("/admin.users.reset-password", response_model=schemas.AdminUserSummary)
def admin_reset_password(body: schemas.AdminUserResetPasswordRequest):
    _require_admin(body.admin_password)
    _require_mongo()
    username = (body.username or "").strip()
    password = body.password or ""
    if not username:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username is required")
    if len(password) < 4:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 4 characters",
        )

    user = fetch_user(username)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    update_user_fields(username, hashed_password=get_password_hash(password))
    return _user_summary(fetch_user(username) or user)


@router.post("/admin.users.set-active", response_model=schemas.AdminUserSummary)
def admin_set_active(body: schemas.AdminUserSetActiveRequest):
    _require_admin(body.admin_password)
    _require_mongo()
    username = (body.username or "").strip()
    if not username:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username is required")

    user = fetch_user(username)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    update_user_fields(username, is_active=bool(body.is_active))
    user = fetch_user(username) or user
    return _user_summary(user)
