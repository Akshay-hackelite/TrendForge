"""Persistence backed by flat Mongo collections, keyed by document ids.

Collections:
  users._id          = username
  clients._id        = client uuid          → username
  channels._id       = YouTube channel id   → client_id, username
  videos._id         = YouTube video id     → channel_id, client_id
  topics._id         = topic uuid           → client_id
  content_plans._id  = client_id            (coverage + suggestions)
  content_videos._id = cv:{client}:{topic}  → client_id, topic_id (produced YT package)
  instagram_app_configs._id = client_id
  instagram_connections._id = client_id
  instagram_oauth_states._id = state uuid
  instagram_style_profiles._id = client_id
  social_posts._id   = social post uuid     → client_id
  weekly_trackers._id = weekly:{client}:{year}:{month}:{week}
  custom_trackers._id = custom:{client}:{year}:{month}:{week}
  tracker_sheet_comments._id = sheet:{client}:{year}:{month}:{week}:weekly:card:{card_id}
  monthly_reports._id = report uuid         → client_id, username

All API paths use collection helpers (fetch_*/update_*/replace_*) with ids.
"""

from __future__ import annotations

import copy
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import bcrypt
import certifi
from pymongo import ASCENDING, DESCENDING, DeleteOne, MongoClient, ReplaceOne
from pymongo.database import Database

from app.config import settings

DB_FILE = Path(__file__).resolve().parent.parent / "db.json"

_mongo_client: MongoClient | None = None
_indexes_ready = False


def _now_iso_for_db() -> str:
    return datetime.now(timezone.utc).isoformat()

COL_USERS = "users"
COL_CLIENTS = "clients"
COL_CHANNELS = "channels"
COL_VIDEOS = "videos"
COL_TOPICS = "topics"
COL_CONTENT_PLANS = "content_plans"
COL_CONTENT_VIDEOS = "content_videos"
COL_INSTAGRAM_APP_CONFIGS = "instagram_app_configs"
COL_INSTAGRAM_CONNECTIONS = "instagram_connections"
COL_INSTAGRAM_OAUTH_STATES = "instagram_oauth_states"
COL_FACEBOOK_APP_CONFIGS = "facebook_app_configs"
COL_FACEBOOK_CONNECTIONS = "facebook_connections"
COL_FACEBOOK_OAUTH_STATES = "facebook_oauth_states"
COL_INSTAGRAM_STYLE_PROFILES = "instagram_style_profiles"
COL_SOCIAL_POSTS = "social_posts"
COL_SOCIAL_SCHEDULES = "social_schedules"
COL_WEEKLY_TRACKERS = "weekly_trackers"
COL_CUSTOM_TRACKERS = "custom_trackers"
COL_TRACKER_SHEET_COMMENTS = "tracker_sheet_comments"
COL_MONTHLY_REPORTS = "monthly_reports"
COL_LEGACY_APP = "app_state"

SOCIAL_FILE_KEYS = (
    COL_INSTAGRAM_APP_CONFIGS,
    COL_INSTAGRAM_CONNECTIONS,
    COL_INSTAGRAM_OAUTH_STATES,
    COL_FACEBOOK_APP_CONFIGS,
    COL_FACEBOOK_CONNECTIONS,
    COL_FACEBOOK_OAUTH_STATES,
    COL_INSTAGRAM_STYLE_PROFILES,
    COL_SOCIAL_POSTS,
    COL_SOCIAL_SCHEDULES,
    COL_WEEKLY_TRACKERS,
    COL_CUSTOM_TRACKERS,
    COL_TRACKER_SHEET_COMMENTS,
    COL_CONTENT_VIDEOS,
)

CLIENT_PROFILE_KEYS = (
    "name",
    "website_url",
    "specialty",
    "designation",
    "description",
    "reference_youtube_channel",
    "ai_videos_started_from",
)

CHANNEL_META_KEYS = (
    "title",
    "description",
    "custom_url",
    "published_at",
    "view_count",
    "subscriber_count",
    "video_count",
    "google_credentials",
    "language",
)


def _use_mongo() -> bool:
    return bool((settings.MONGODB_URI or "").strip())


def _client() -> MongoClient:
    global _mongo_client
    if _mongo_client is None:
        _mongo_client = MongoClient(
            settings.MONGODB_URI.strip(),
            tlsCAFile=certifi.where(),
            serverSelectionTimeoutMS=15000,
        )
    return _mongo_client


def mongo_db() -> Database:
    return _client()[settings.MONGODB_DB_NAME]


def _ensure_indexes(db: Database) -> None:
    global _indexes_ready
    if _indexes_ready:
        return
    db[COL_CLIENTS].create_index([("username", ASCENDING)])
    db[COL_CHANNELS].create_index([("client_id", ASCENDING)])
    db[COL_CHANNELS].create_index([("username", ASCENDING)])
    db[COL_VIDEOS].create_index([("channel_id", ASCENDING)])
    db[COL_VIDEOS].create_index([("client_id", ASCENDING)])
    db[COL_TOPICS].create_index([("client_id", ASCENDING)])
    db[COL_INSTAGRAM_OAUTH_STATES].create_index([("client_id", ASCENDING)])
    db[COL_SOCIAL_POSTS].create_index([("client_id", ASCENDING), ("created_at", ASCENDING)])
    db[COL_WEEKLY_TRACKERS].create_index(
        [("client_id", ASCENDING), ("year", ASCENDING), ("month", ASCENDING), ("week", ASCENDING)],
        unique=True,
    )
    db[COL_CUSTOM_TRACKERS].create_index(
        [("client_id", ASCENDING), ("year", ASCENDING), ("month", ASCENDING), ("week", ASCENDING)],
        unique=True,
    )
    db[COL_TRACKER_SHEET_COMMENTS].create_index(
        [("client_id", ASCENDING), ("year", ASCENDING), ("month", ASCENDING)],
    )
    db[COL_CONTENT_VIDEOS].create_index(
        [("client_id", ASCENDING), ("topic_id", ASCENDING)],
        unique=True,
    )
    db[COL_MONTHLY_REPORTS].create_index([("client_id", ASCENDING), ("report_month", ASCENDING)])
    db[COL_MONTHLY_REPORTS].create_index([("username", ASCENDING)])
    _indexes_ready = True


def _mdb() -> Database:
    db = mongo_db()
    _ensure_indexes(db)
    _migrate_legacy_if_needed(db)
    return db


def _strip_mongo_id(doc: dict | None) -> dict:
    if not doc:
        return {}
    out = dict(doc)
    out.pop("_id", None)
    return out


def _topic_from_doc(doc: dict) -> dict:
    row = _strip_mongo_id(doc)
    row.pop("client_id", None)
    row["id"] = doc["_id"]
    return row


def _video_from_doc(doc: dict) -> dict:
    row = _strip_mongo_id(doc)
    row.pop("client_id", None)
    row.pop("channel_id", None)
    row["id"] = doc["_id"]
    return row


def _channel_from_doc(doc: dict, videos: list[dict]) -> dict:
    language = doc.get("language") or None
    if language:
        language = str(language).strip().lower() or None
    return {
        "id": doc["_id"],
        "title": doc.get("title") or "",
        "description": doc.get("description") or "",
        "custom_url": doc.get("custom_url"),
        "published_at": doc.get("published_at"),
        "view_count": int(doc.get("view_count") or 0),
        "subscriber_count": int(doc.get("subscriber_count") or 0),
        "video_count": int(doc.get("video_count") or 0),
        "google_credentials": doc.get("google_credentials") or {},
        "language": language,
        "videos": videos,
    }


def _client_from_parts(
    doc: dict,
    *,
    topics: list[dict],
    channels: list[dict],
    plan: dict | None,
) -> dict:
    client = {
        "id": doc["_id"],
        "name": doc.get("name") or "Client",
        "website_url": doc.get("website_url"),
        "specialty": doc.get("specialty"),
        "designation": doc.get("designation"),
        "description": doc.get("description"),
        "reference_youtube_channel": doc.get("reference_youtube_channel"),
        "ai_videos_started_from": doc.get("ai_videos_started_from"),
        "topics": topics,
        "channels": channels,
    }
    if plan:
        if plan.get("content_topic_coverage") is not None:
            client["content_topic_coverage"] = plan["content_topic_coverage"]
        if plan.get("content_suggestions") is not None:
            client["content_suggestions"] = plan["content_suggestions"]
    return client


def _cascade_delete_client(db: Database, client_id: str) -> None:
    db[COL_TOPICS].delete_many({"client_id": client_id})
    db[COL_VIDEOS].delete_many({"client_id": client_id})
    db[COL_CHANNELS].delete_many({"client_id": client_id})
    db[COL_CONTENT_PLANS].delete_one({"_id": client_id})
    db[COL_INSTAGRAM_APP_CONFIGS].delete_one({"_id": client_id})
    db[COL_INSTAGRAM_CONNECTIONS].delete_one({"_id": client_id})
    db[COL_INSTAGRAM_OAUTH_STATES].delete_many({"client_id": client_id})
    db[COL_INSTAGRAM_STYLE_PROFILES].delete_one({"_id": client_id})
    db[COL_SOCIAL_POSTS].delete_many({"client_id": client_id})
    db[COL_SOCIAL_SCHEDULES].delete_one({"_id": client_id})
    db[COL_WEEKLY_TRACKERS].delete_many({"client_id": client_id})
    db[COL_CUSTOM_TRACKERS].delete_many({"client_id": client_id})
    db[COL_TRACKER_SHEET_COMMENTS].delete_many({"client_id": client_id})
    db[COL_CONTENT_VIDEOS].delete_many({"client_id": client_id})
    db[COL_MONTHLY_REPORTS].delete_many({"client_id": client_id})
    db[COL_CLIENTS].delete_one({"_id": client_id})


def _cascade_delete_user(db: Database, username: str) -> None:
    for cdoc in db[COL_CLIENTS].find({"username": username}, {"_id": 1}):
        _cascade_delete_client(db, cdoc["_id"])
    db[COL_USERS].delete_one({"_id": username})


def _bulk_replace(collection, ops: list) -> None:
    if ops:
        collection.bulk_write(ops, ordered=False)


def _save_nested_to_mongo(db_data: dict) -> None:
    db = _mdb()
    users = db_data.get("users") if isinstance(db_data, dict) else {}
    if not isinstance(users, dict):
        users = {}

    # Upsert users present in the snapshot only — never delete other users here.
    # Use delete_user() for explicit user removal.

    user_ops: list = []
    client_ops: list = []
    topic_ops: list = []
    plan_ops: list = []
    channel_ops: list = []
    video_ops: list = []

    for username, user in users.items():
        if not isinstance(user, dict):
            continue
        user_ops.append(
            ReplaceOne(
                {"_id": username},
                {
                    "_id": username,
                    "hashed_password": user.get("hashed_password") or "",
                    "is_active": bool(user.get("is_active", True)),
                    "active_client_id": user.get("active_client_id"),
                    "active_channel_id": user.get("active_channel_id"),
                },
                upsert=True,
            )
        )

        clients = user.get("clients") or []
        if not isinstance(clients, list):
            clients = []
        keep_client_ids: set[str] = set()

        for client in clients:
            if not isinstance(client, dict):
                continue
            cid = client.get("id")
            if not cid:
                continue
            keep_client_ids.add(cid)
            profile = {k: client.get(k) for k in CLIENT_PROFILE_KEYS}
            client_ops.append(
                ReplaceOne(
                    {"_id": cid},
                    {"_id": cid, "username": username, **profile},
                    upsert=True,
                )
            )

            topics = client.get("topics") or []
            if not isinstance(topics, list):
                topics = []
            keep_topic_ids: set[str] = set()
            for topic in topics:
                if not isinstance(topic, dict) or not topic.get("id"):
                    continue
                tid = topic["id"]
                keep_topic_ids.add(tid)
                body = {k: v for k, v in topic.items() if k != "id"}
                topic_ops.append(
                    ReplaceOne(
                        {"_id": tid},
                        {"_id": tid, "client_id": cid, **body},
                        upsert=True,
                    )
                )
            db[COL_TOPICS].delete_many(
                {"client_id": cid, "_id": {"$nin": list(keep_topic_ids)}}
            )

            has_coverage = "content_topic_coverage" in client
            has_suggestions = "content_suggestions" in client
            if has_coverage or has_suggestions:
                plan: dict[str, Any] = {"_id": cid}
                if has_coverage:
                    plan["content_topic_coverage"] = client.get("content_topic_coverage")
                if has_suggestions:
                    plan["content_suggestions"] = client.get("content_suggestions")
                plan_ops.append(ReplaceOne({"_id": cid}, plan, upsert=True))
            else:
                plan_ops.append(DeleteOne({"_id": cid}))

            channels = client.get("channels") or []
            if not isinstance(channels, list):
                channels = []
            keep_channel_ids: set[str] = set()
            for channel in channels:
                if not isinstance(channel, dict) or not channel.get("id"):
                    continue
                chid = channel["id"]
                keep_channel_ids.add(chid)
                meta = {k: channel.get(k) for k in CHANNEL_META_KEYS}
                channel_ops.append(
                    ReplaceOne(
                        {"_id": chid},
                        {
                            "_id": chid,
                            "client_id": cid,
                            "username": username,
                            **meta,
                        },
                        upsert=True,
                    )
                )

                videos = channel.get("videos") or []
                if not isinstance(videos, list):
                    videos = []
                keep_video_ids: set[str] = set()
                for video in videos:
                    if not isinstance(video, dict) or not video.get("id"):
                        continue
                    vid = video["id"]
                    keep_video_ids.add(vid)
                    body = {k: v for k, v in video.items() if k != "id"}
                    video_ops.append(
                        ReplaceOne(
                            {"_id": vid},
                            {
                                "_id": vid,
                                "channel_id": chid,
                                "client_id": cid,
                                **body,
                            },
                            upsert=True,
                        )
                    )
                db[COL_VIDEOS].delete_many(
                    {
                        "channel_id": chid,
                        "client_id": cid,
                        "_id": {"$nin": list(keep_video_ids)},
                    }
                )

            for chdoc in db[COL_CHANNELS].find(
                {"client_id": cid, "_id": {"$nin": list(keep_channel_ids)}},
                {"_id": 1},
            ):
                db[COL_VIDEOS].delete_many({"channel_id": chdoc["_id"], "client_id": cid})
            db[COL_CHANNELS].delete_many(
                {"client_id": cid, "_id": {"$nin": list(keep_channel_ids)}}
            )

        for cdoc in db[COL_CLIENTS].find(
            {"username": username, "_id": {"$nin": list(keep_client_ids)}},
            {"_id": 1},
        ):
            _cascade_delete_client(db, cdoc["_id"])

    _bulk_replace(db[COL_USERS], user_ops)
    _bulk_replace(db[COL_CLIENTS], client_ops)
    _bulk_replace(db[COL_TOPICS], topic_ops)
    _bulk_replace(db[COL_CONTENT_PLANS], plan_ops)
    _bulk_replace(db[COL_CHANNELS], channel_ops)
    _bulk_replace(db[COL_VIDEOS], video_ops)


def _migrate_nested_users_dict(db: Database, users: dict) -> int:
    if not users:
        return 0
    _save_nested_to_mongo({"users": users})
    return len(users)


def _migrate_legacy_if_needed(db: Database) -> None:
    if db[COL_USERS].estimated_document_count() > 0:
        return

    legacy = db[COL_LEGACY_APP].find_one({"_id": "app"})
    if legacy and isinstance(legacy.get("users"), dict) and legacy["users"]:
        print(
            f"[db] migrating legacy app_state → collections "
            f"({len(legacy['users'])} users)…",
            flush=True,
        )
        _migrate_nested_users_dict(db, legacy["users"])
        db[COL_LEGACY_APP].delete_one({"_id": "app"})
        print("[db] legacy app_state migration done", flush=True)
        return

    if DB_FILE.exists():
        try:
            raw = json.loads(DB_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raw = {}
        users = raw.get("users") if isinstance(raw, dict) else {}
        if isinstance(users, dict) and users:
            print(
                f"[db] migrating db.json → collections ({len(users)} users)…",
                flush=True,
            )
            _migrate_nested_users_dict(db, users)
            print("[db] db.json migration done", flush=True)


def _load_file(username: str | None = None) -> dict:
    if not DB_FILE.exists():
        return {"users": {}, "monthly_reports": {}, **{k: {} for k in SOCIAL_FILE_KEYS}}
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError:
        return {"users": {}, "monthly_reports": {}}
    users = data.get("users") if isinstance(data, dict) else {}
    if not isinstance(users, dict):
        users = {}
    monthly_reports = data.get("monthly_reports") if isinstance(data, dict) else {}
    if not isinstance(monthly_reports, dict):
        monthly_reports = {}
    social_maps: dict[str, dict] = {}
    for key in SOCIAL_FILE_KEYS:
        value = data.get(key) if isinstance(data, dict) else {}
        social_maps[key] = value if isinstance(value, dict) else {}
    if username is not None:
        user = users.get(username)
        return {
            "users": {username: user} if user else {},
            "monthly_reports": monthly_reports,
            **social_maps,
        }
    return {"users": users, "monthly_reports": monthly_reports, **social_maps}


def _save_file(db_data: dict) -> None:
    users = db_data.get("users") if isinstance(db_data, dict) else {}
    if not isinstance(users, dict):
        users = {}
    monthly_reports = db_data.get("monthly_reports") if isinstance(db_data, dict) else None
    social_maps = {
        key: db_data.get(key)
        for key in SOCIAL_FILE_KEYS
        if isinstance(db_data.get(key), dict)
    }
    # Merge into full file when saving a partial (single-user) snapshot.
    existing_reports: dict = {}
    if DB_FILE.exists():
        try:
            existing = json.loads(DB_FILE.read_text(encoding="utf-8"))
            existing_users = existing.get("users") if isinstance(existing, dict) else {}
            if isinstance(existing_users, dict):
                merged = dict(existing_users)
                merged.update(users)
                users = merged
            er = existing.get("monthly_reports") if isinstance(existing, dict) else {}
            if isinstance(er, dict):
                existing_reports = er
            existing_social = {
                key: existing.get(key)
                for key in SOCIAL_FILE_KEYS
                if isinstance(existing.get(key), dict)
            }
        except (OSError, json.JSONDecodeError):
            existing_social = {}
    else:
        existing_social = {}
    if isinstance(monthly_reports, dict):
        merged_reports = dict(existing_reports)
        merged_reports.update(monthly_reports)
        monthly_reports = merged_reports
    else:
        monthly_reports = existing_reports
    out = {"users": users, "monthly_reports": monthly_reports}
    for key in SOCIAL_FILE_KEYS:
        merged = dict(existing_social.get(key) or {})
        if key in social_maps:
            merged.update(social_maps[key])
        out[key] = merged
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=4)


# ---------------------------------------------------------------------------
# Collection-level API (prefer these in route handlers)
# ---------------------------------------------------------------------------


def fetch_user(username: str) -> dict | None:
    """users collection by username. No clients/channels/videos."""
    if _use_mongo():
        udoc = _mdb()[COL_USERS].find_one({"_id": username})
        if not udoc:
            return None
        return {
            "username": udoc["_id"],
            "hashed_password": udoc.get("hashed_password") or "",
            "is_active": bool(udoc.get("is_active", True)),
            "active_client_id": udoc.get("active_client_id"),
            "active_channel_id": udoc.get("active_channel_id"),
            "clients": [],
        }
    data = _load_file(username)
    user = (data.get("users") or {}).get(username)
    if not user:
        return None
    return {
        "username": user.get("username") or username,
        "hashed_password": user.get("hashed_password") or "",
        "is_active": bool(user.get("is_active", True)),
        "active_client_id": user.get("active_client_id"),
        "active_channel_id": user.get("active_channel_id"),
        "clients": [],
    }


def insert_user(user: dict) -> None:
    username = user["username"]
    if _use_mongo():
        _mdb()[COL_USERS].insert_one(
            {
                "_id": username,
                "hashed_password": user.get("hashed_password") or "",
                "is_active": bool(user.get("is_active", True)),
                "active_client_id": user.get("active_client_id"),
                "active_channel_id": user.get("active_channel_id"),
            }
        )
        return
    data = _load_file()
    data.setdefault("users", {})[username] = {
        **user,
        "clients": user.get("clients") or [],
    }
    _save_file(data)


def update_user_fields(username: str, **fields: Any) -> None:
    allowed = {"hashed_password", "is_active", "active_client_id", "active_channel_id"}
    patch = {k: v for k, v in fields.items() if k in allowed}
    if not patch:
        return
    if _use_mongo():
        _mdb()[COL_USERS].update_one({"_id": username}, {"$set": patch})
        return
    data = _load_file()
    user = (data.get("users") or {}).get(username)
    if not user:
        return
    user.update(patch)
    _save_file(data)


def fetch_client_doc(client_id: str, *, username: str | None = None) -> dict | None:
    """clients collection → nested-shaped client shell (no topics/channels)."""
    if _use_mongo():
        query: dict[str, Any] = {"_id": client_id}
        if username is not None:
            query["username"] = username
        cdoc = _mdb()[COL_CLIENTS].find_one(query)
        if not cdoc:
            return None
        return _client_from_parts(cdoc, topics=[], channels=[], plan=None)

    data = _load_file(username)
    for uname, user in (data.get("users") or {}).items():
        if username is not None and uname != username:
            continue
        for client in user.get("clients") or []:
            if isinstance(client, dict) and client.get("id") == client_id:
                return {
                    "id": client_id,
                    **{k: client.get(k) for k in CLIENT_PROFILE_KEYS},
                    "topics": [],
                    "channels": [],
                }
    return None


def fetch_topics(client_id: str) -> list[dict]:
    if _use_mongo():
        return [_topic_from_doc(t) for t in _mdb()[COL_TOPICS].find({"client_id": client_id})]
    data = _load_file()
    for user in (data.get("users") or {}).values():
        for client in user.get("clients") or []:
            if isinstance(client, dict) and client.get("id") == client_id:
                return list(client.get("topics") or [])
    return []


def replace_topics(client_id: str, topics: list[dict]) -> None:
    """Replace all topics for one client_id in the topics collection."""
    if _use_mongo():
        mdb = _mdb()
        keep_ids: list[str] = []
        ops: list = []
        for topic in topics:
            if not isinstance(topic, dict) or not topic.get("id"):
                continue
            tid = topic["id"]
            keep_ids.append(tid)
            body = {k: v for k, v in topic.items() if k != "id"}
            ops.append(
                ReplaceOne(
                    {"_id": tid},
                    {"_id": tid, "client_id": client_id, **body},
                    upsert=True,
                )
            )
        _bulk_replace(mdb[COL_TOPICS], ops)
        mdb[COL_TOPICS].delete_many({"client_id": client_id, "_id": {"$nin": keep_ids}})
        return

    data = _load_file()
    for user in (data.get("users") or {}).values():
        for client in user.get("clients") or []:
            if isinstance(client, dict) and client.get("id") == client_id:
                client["topics"] = topics
                _save_file(data)
                return


def update_client_fields(client_id: str, username: str, fields: dict[str, Any]) -> dict | None:
    """Update profile fields on clients collection for this client_id + owner."""
    patch = {k: fields[k] for k in CLIENT_PROFILE_KEYS if k in fields}
    if _use_mongo():
        mdb = _mdb()
        if patch:
            result = mdb[COL_CLIENTS].update_one(
                {"_id": client_id, "username": username},
                {"$set": patch},
            )
        else:
            result = mdb[COL_CLIENTS].update_one(
                {"_id": client_id, "username": username},
                {"$set": {"username": username}},
            )
        if result.matched_count == 0:
            return None
        return fetch_client_doc(client_id, username=username)

    data = _load_file(username)
    user = (data.get("users") or {}).get(username)
    if not user:
        return None
    for client in user.get("clients") or []:
        if isinstance(client, dict) and client.get("id") == client_id:
            client.update(patch)
            _save_file(data)
            return {
                "id": client_id,
                **{k: client.get(k) for k in CLIENT_PROFILE_KEYS},
                "topics": list(client.get("topics") or []),
                "channels": [],
            }
    return None


def insert_client(username: str, client: dict) -> None:
    cid = client["id"]
    profile = {k: client.get(k) for k in CLIENT_PROFILE_KEYS}
    if _use_mongo():
        mdb = _mdb()
        mdb[COL_CLIENTS].insert_one({"_id": cid, "username": username, **profile})
        mdb[COL_USERS].update_one(
            {"_id": username},
            {"$set": {"active_client_id": cid, "active_channel_id": None}},
        )
        return
    data = _load_file()
    user = (data.get("users") or {}).get(username)
    if not user:
        return
    user.setdefault("clients", []).append(
        {
            "id": cid,
            **profile,
            "topics": client.get("topics") or [],
            "channels": client.get("channels") or [],
        }
    )
    user["active_client_id"] = cid
    user["active_channel_id"] = None
    _save_file(data)


def delete_client_owned(client_id: str, username: str) -> bool:
    if _use_mongo():
        mdb = _mdb()
        cdoc = mdb[COL_CLIENTS].find_one({"_id": client_id, "username": username}, {"_id": 1})
        if not cdoc:
            return False
        _cascade_delete_client(mdb, client_id)
        udoc = mdb[COL_USERS].find_one({"_id": username})
        if udoc and udoc.get("active_client_id") == client_id:
            next_client = mdb[COL_CLIENTS].find_one({"username": username}, {"_id": 1})
            next_id = next_client["_id"] if next_client else None
            active_ch = None
            if next_id:
                ch = mdb[COL_CHANNELS].find_one({"client_id": next_id}, {"_id": 1})
                active_ch = ch["_id"] if ch else None
            mdb[COL_USERS].update_one(
                {"_id": username},
                {"$set": {"active_client_id": next_id, "active_channel_id": active_ch}},
            )
        return True

    data = _load_file()
    user = (data.get("users") or {}).get(username)
    if not user:
        return False
    clients = user.get("clients") or []
    kept = [c for c in clients if not (isinstance(c, dict) and c.get("id") == client_id)]
    if len(kept) == len(clients):
        return False
    user["clients"] = kept
    if user.get("active_client_id") == client_id:
        user["active_client_id"] = kept[0]["id"] if kept else None
        chans = (kept[0].get("channels") or []) if kept else []
        user["active_channel_id"] = chans[0]["id"] if chans else None
    trackers = data.setdefault(COL_WEEKLY_TRACKERS, {})
    for tid in [k for k, v in trackers.items() if isinstance(v, dict) and v.get("client_id") == client_id]:
        trackers.pop(tid, None)
    custom_trackers = data.setdefault(COL_CUSTOM_TRACKERS, {})
    for tid in [k for k, v in custom_trackers.items() if isinstance(v, dict) and v.get("client_id") == client_id]:
        custom_trackers.pop(tid, None)
    sheet_comments = data.setdefault(COL_TRACKER_SHEET_COMMENTS, {})
    for cid in [k for k, v in sheet_comments.items() if isinstance(v, dict) and v.get("client_id") == client_id]:
        sheet_comments.pop(cid, None)
    packages = data.setdefault(COL_CONTENT_VIDEOS, {})
    for pid in [k for k, v in packages.items() if isinstance(v, dict) and v.get("client_id") == client_id]:
        packages.pop(pid, None)
    _save_file(data)
    return True


def count_channels(client_id: str) -> int:
    if _use_mongo():
        return _mdb()[COL_CHANNELS].count_documents({"client_id": client_id})
    data = _load_file()
    for user in (data.get("users") or {}).values():
        for client in user.get("clients") or []:
            if isinstance(client, dict) and client.get("id") == client_id:
                return len(client.get("channels") or [])
    return 0


def list_channel_ids(client_id: str) -> list[str]:
    if _use_mongo():
        return [
            d["_id"]
            for d in _mdb()[COL_CHANNELS].find({"client_id": client_id}, {"_id": 1})
        ]
    data = _load_file()
    for user in (data.get("users") or {}).values():
        for client in user.get("clients") or []:
            if isinstance(client, dict) and client.get("id") == client_id:
                return [
                    c["id"]
                    for c in (client.get("channels") or [])
                    if isinstance(c, dict) and c.get("id")
                ]
    return []


def list_channel_summaries(client_id: str) -> list[dict]:
    """Channel id/title only (no videos, no credentials dump needed for lists)."""
    if _use_mongo():
        return [
            {"id": d["_id"], "title": d.get("title") or d["_id"]}
            for d in _mdb()[COL_CHANNELS].find(
                {"client_id": client_id}, {"_id": 1, "title": 1}
            )
        ]
    data = _load_file()
    for user in (data.get("users") or {}).values():
        for client in user.get("clients") or []:
            if isinstance(client, dict) and client.get("id") == client_id:
                return [
                    {"id": c["id"], "title": c.get("title") or c["id"]}
                    for c in (client.get("channels") or [])
                    if isinstance(c, dict) and c.get("id")
                ]
    return []


def fetch_channel(
    channel_id: str,
    *,
    client_id: str | None = None,
    username: str | None = None,
) -> dict | None:
    """channels collection by id (optional owner filters). Includes credentials, no videos."""
    if _use_mongo():
        query: dict[str, Any] = {"_id": channel_id}
        if client_id is not None:
            query["client_id"] = client_id
        if username is not None:
            query["username"] = username
        doc = _mdb()[COL_CHANNELS].find_one(query)
        return _channel_from_doc(doc, videos=[]) if doc else None
    data = _load_file(username)
    for uname, user in (data.get("users") or {}).items():
        if username is not None and uname != username:
            continue
        for client in user.get("clients") or []:
            if client_id is not None and client.get("id") != client_id:
                continue
            for channel in client.get("channels") or []:
                if isinstance(channel, dict) and channel.get("id") == channel_id:
                    row = dict(channel)
                    row["videos"] = []
                    return row
    return None


def list_channels_meta(client_id: str) -> list[dict]:
    """Full channel meta for a client_id (no videos)."""
    if _use_mongo():
        return [
            _channel_from_doc(d, videos=[])
            for d in _mdb()[COL_CHANNELS].find({"client_id": client_id})
        ]
    data = _load_file()
    for user in (data.get("users") or {}).values():
        for client in user.get("clients") or []:
            if isinstance(client, dict) and client.get("id") == client_id:
                out = []
                for c in client.get("channels") or []:
                    if isinstance(c, dict) and c.get("id"):
                        row = dict(c)
                        row["videos"] = []
                        out.append(row)
                return out
    return []


def find_client_id_by_channel(username: str, channel_id: str) -> str | None:
    if _use_mongo():
        ch = _mdb()[COL_CHANNELS].find_one(
            {"_id": channel_id, "username": username}, {"client_id": 1}
        )
        return ch.get("client_id") if ch else None
    data = _load_file(username)
    user = (data.get("users") or {}).get(username) or {}
    for client in user.get("clients") or []:
        if not isinstance(client, dict):
            continue
        for c in client.get("channels") or []:
            if isinstance(c, dict) and c.get("id") == channel_id:
                return client.get("id")
    return None


def update_channel_fields(channel_id: str, client_id: str, fields: dict[str, Any]) -> None:
    patch = {k: fields[k] for k in CHANNEL_META_KEYS if k in fields}
    if not patch:
        return
    if _use_mongo():
        _mdb()[COL_CHANNELS].update_one(
            {"_id": channel_id, "client_id": client_id},
            {"$set": patch},
        )
        return
    data = _load_file()
    for user in (data.get("users") or {}).values():
        for client in user.get("clients") or []:
            if not isinstance(client, dict) or client.get("id") != client_id:
                continue
            for channel in client.get("channels") or []:
                if isinstance(channel, dict) and channel.get("id") == channel_id:
                    channel.update(patch)
                    _save_file(data)
                    return


def update_video_fields(video_id: str, client_id: str, fields: dict[str, Any]) -> dict | None:
    if _use_mongo():
        mdb = _mdb()
        mdb[COL_VIDEOS].update_one(
            {"_id": video_id, "client_id": client_id},
            {"$set": fields},
        )
        doc = mdb[COL_VIDEOS].find_one({"_id": video_id, "client_id": client_id})
        return _video_from_doc(doc) if doc else None
    data = _load_file()
    for user in (data.get("users") or {}).values():
        for client in user.get("clients") or []:
            if not isinstance(client, dict) or client.get("id") != client_id:
                continue
            for channel in client.get("channels") or []:
                for video in channel.get("videos") or []:
                    if isinstance(video, dict) and video.get("id") == video_id:
                        video.update(fields)
                        _save_file(data)
                        return dict(video)
    return None


def list_videos_for_channel(channel_id: str, client_id: str) -> list[dict]:
    if _use_mongo():
        return [
            _video_from_doc(v)
            for v in _mdb()[COL_VIDEOS].find(
                {"channel_id": channel_id, "client_id": client_id}
            )
        ]
    data = _load_file()
    for user in (data.get("users") or {}).values():
        for client in user.get("clients") or []:
            if not isinstance(client, dict) or client.get("id") != client_id:
                continue
            for channel in client.get("channels") or []:
                if isinstance(channel, dict) and channel.get("id") == channel_id:
                    return list(channel.get("videos") or [])
    return []


def replace_channel_videos(
    channel_id: str,
    client_id: str,
    videos: list[dict],
) -> None:
    """Replace videos collection rows for one channel_id."""
    if _use_mongo():
        mdb = _mdb()
        keep_ids: list[str] = []
        ops: list = []
        for video in videos:
            if not isinstance(video, dict) or not video.get("id"):
                continue
            vid = video["id"]
            keep_ids.append(vid)
            body = {k: v for k, v in video.items() if k != "id"}
            ops.append(
                ReplaceOne(
                    {"_id": vid},
                    {"_id": vid, "channel_id": channel_id, "client_id": client_id, **body},
                    upsert=True,
                )
            )
        _bulk_replace(mdb[COL_VIDEOS], ops)
        mdb[COL_VIDEOS].delete_many(
            {
                "channel_id": channel_id,
                "client_id": client_id,
                "_id": {"$nin": keep_ids},
            }
        )
        mdb[COL_CHANNELS].update_one(
            {"_id": channel_id, "client_id": client_id},
            {"$set": {"video_count": len(keep_ids)}},
        )
        return

    data = _load_file()
    for user in (data.get("users") or {}).values():
        for client in user.get("clients") or []:
            if not isinstance(client, dict) or client.get("id") != client_id:
                continue
            for channel in client.get("channels") or []:
                if isinstance(channel, dict) and channel.get("id") == channel_id:
                    channel["videos"] = videos
                    channel["video_count"] = len(videos)
                    _save_file(data)
                    return


def list_clients_for_user(username: str, *, with_topics: bool = True) -> list[dict]:
    """Light clients for API list responses — no videos."""
    if _use_mongo():
        mdb = _mdb()
        client_docs = list(mdb[COL_CLIENTS].find({"username": username}))
        client_ids = [c["_id"] for c in client_docs]
        topics_by_client: dict[str, list[dict]] = defaultdict(list)
        if with_topics and client_ids:
            for tdoc in mdb[COL_TOPICS].find({"client_id": {"$in": client_ids}}):
                topics_by_client[tdoc["client_id"]].append(_topic_from_doc(tdoc))
        channel_ids_by_client: dict[str, list[str]] = defaultdict(list)
        if client_ids:
            for ch in mdb[COL_CHANNELS].find({"client_id": {"$in": client_ids}}, {"_id": 1, "client_id": 1}):
                channel_ids_by_client[ch["client_id"]].append(ch["_id"])
        out: list[dict] = []
        for cdoc in client_docs:
            cid = cdoc["_id"]
            ch_ids = channel_ids_by_client.get(cid, [])
            out.append(
                {
                    "id": cid,
                    **{k: cdoc.get(k) for k in CLIENT_PROFILE_KEYS},
                    "topics": topics_by_client.get(cid, []) if with_topics else [],
                    "channels": [{"id": i} for i in ch_ids],
                    "channel_count": len(ch_ids),
                }
            )
        return out

    data = _load_file(username)
    user = (data.get("users") or {}).get(username) or {}
    out = []
    for client in user.get("clients") or []:
        if not isinstance(client, dict) or not client.get("id"):
            continue
        channels = client.get("channels") or []
        out.append(
            {
                "id": client["id"],
                **{k: client.get(k) for k in CLIENT_PROFILE_KEYS},
                "topics": list(client.get("topics") or []) if with_topics else [],
                "channels": [{"id": c["id"]} for c in channels if c.get("id")],
                "channel_count": len(channels),
            }
        )
    return out


def fetch_content_plan(client_id: str) -> dict | None:
    """content_plans collection by client_id."""
    if _use_mongo():
        return _mdb()[COL_CONTENT_PLANS].find_one({"_id": client_id})
    data = _load_file()
    for user in (data.get("users") or {}).values():
        for c in user.get("clients") or []:
            if isinstance(c, dict) and c.get("id") == client_id:
                plan: dict[str, Any] = {"_id": client_id}
                if "content_topic_coverage" in c:
                    plan["content_topic_coverage"] = c.get("content_topic_coverage")
                if "content_suggestions" in c:
                    plan["content_suggestions"] = c.get("content_suggestions")
                return plan if len(plan) > 1 else None
    return None


def replace_content_plan(client_id: str, client: dict) -> None:
    """Write content_plans doc for this client_id only.

    yt_* / yt_locales are stored on content_videos, not on the plan. A deepcopy is
    stripped before persist so in-memory hydrated responses stay intact.
    """
    has_coverage = "content_topic_coverage" in client
    has_suggestions = "content_suggestions" in client
    suggestions = client.get("content_suggestions")
    if has_suggestions and isinstance(suggestions, dict):
        suggestions = copy.deepcopy(suggestions)
        strip_yt_fields_from_suggestions(suggestions)
    if _use_mongo():
        mdb = _mdb()
        if has_coverage or has_suggestions:
            plan: dict[str, Any] = {"_id": client_id}
            if has_coverage:
                plan["content_topic_coverage"] = client.get("content_topic_coverage")
            if has_suggestions:
                plan["content_suggestions"] = suggestions
            mdb[COL_CONTENT_PLANS].replace_one({"_id": client_id}, plan, upsert=True)
        else:
            mdb[COL_CONTENT_PLANS].delete_one({"_id": client_id})
        return

    data = _load_file()
    for user in (data.get("users") or {}).values():
        for c in user.get("clients") or []:
            if isinstance(c, dict) and c.get("id") == client_id:
                if has_coverage:
                    c["content_topic_coverage"] = client.get("content_topic_coverage")
                if has_suggestions:
                    c["content_suggestions"] = suggestions
                _save_file(data)
                return


def get_instagram_app_config(client_id: str) -> dict | None:
    if _use_mongo():
        return _strip_mongo_id(_mdb()[COL_INSTAGRAM_APP_CONFIGS].find_one({"_id": client_id}))
    data = _load_file()
    row = (data.get(COL_INSTAGRAM_APP_CONFIGS) or {}).get(client_id)
    return dict(row) if isinstance(row, dict) else None


def save_instagram_app_config(
    client_id: str,
    *,
    app_id: str,
    app_secret: str | None = None,
) -> dict:
    existing = get_instagram_app_config(client_id) or {}
    row = {
        "client_id": client_id,
        "app_id": app_id,
        "app_secret": app_secret if app_secret is not None else existing.get("app_secret"),
    }
    if _use_mongo():
        _mdb()[COL_INSTAGRAM_APP_CONFIGS].replace_one(
            {"_id": client_id},
            {"_id": client_id, **row},
            upsert=True,
        )
        return row
    data = _load_file()
    data.setdefault(COL_INSTAGRAM_APP_CONFIGS, {})[client_id] = row
    _save_file(data)
    return row


def get_instagram_connection(client_id: str) -> dict | None:
    if _use_mongo():
        return _strip_mongo_id(_mdb()[COL_INSTAGRAM_CONNECTIONS].find_one({"_id": client_id}))
    data = _load_file()
    row = (data.get(COL_INSTAGRAM_CONNECTIONS) or {}).get(client_id)
    return dict(row) if isinstance(row, dict) else None


def save_instagram_connection(client_id: str, connection: dict) -> dict:
    row = {"client_id": client_id, **connection}
    if _use_mongo():
        _mdb()[COL_INSTAGRAM_CONNECTIONS].replace_one(
            {"_id": client_id},
            {"_id": client_id, **row},
            upsert=True,
        )
        return row
    data = _load_file()
    data.setdefault(COL_INSTAGRAM_CONNECTIONS, {})[client_id] = row
    _save_file(data)
    return row


def save_instagram_oauth_state(state: str, payload: dict) -> dict:
    row = {"state": state, **payload}
    if _use_mongo():
        _mdb()[COL_INSTAGRAM_OAUTH_STATES].replace_one(
            {"_id": state},
            {"_id": state, **row},
            upsert=True,
        )
        return row
    data = _load_file()
    data.setdefault(COL_INSTAGRAM_OAUTH_STATES, {})[state] = row
    _save_file(data)
    return row


def pop_instagram_oauth_state(state: str) -> dict | None:
    if _use_mongo():
        doc = _mdb()[COL_INSTAGRAM_OAUTH_STATES].find_one_and_delete({"_id": state})
        return _strip_mongo_id(doc) if doc else None
    data = _load_file()
    states = data.setdefault(COL_INSTAGRAM_OAUTH_STATES, {})
    row = states.pop(state, None)
    _save_file(data)
    return dict(row) if isinstance(row, dict) else None


def get_facebook_app_config(client_id: str) -> dict | None:
    if _use_mongo():
        doc = _mdb()[COL_FACEBOOK_APP_CONFIGS].find_one({"_id": client_id})
        return _strip_mongo_id(doc) if doc else None
    data = _load_file()
    configs = data.setdefault(COL_FACEBOOK_APP_CONFIGS, {})
    row = configs.get(client_id)
    return dict(row) if isinstance(row, dict) else None


def save_facebook_app_config(client_id: str, config: dict) -> dict:
    row = {"client_id": client_id, **config}
    if _use_mongo():
        _mdb()[COL_FACEBOOK_APP_CONFIGS].replace_one(
            {"_id": client_id},
            {"_id": client_id, **row},
            upsert=True,
        )
        return row
    data = _load_file()
    data.setdefault(COL_FACEBOOK_APP_CONFIGS, {})[client_id] = row
    _save_file(data)
    return row


def get_facebook_connection(client_id: str) -> dict | None:
    if _use_mongo():
        doc = _mdb()[COL_FACEBOOK_CONNECTIONS].find_one({"_id": client_id})
        return _strip_mongo_id(doc) if doc else None
    data = _load_file()
    connections = data.setdefault(COL_FACEBOOK_CONNECTIONS, {})
    row = connections.get(client_id)
    return dict(row) if isinstance(row, dict) else None


def save_facebook_connection(client_id: str, payload: dict) -> dict:
    row = {"client_id": client_id, **payload}
    if _use_mongo():
        _mdb()[COL_FACEBOOK_CONNECTIONS].replace_one(
            {"_id": client_id},
            {"_id": client_id, **row},
            upsert=True,
        )
        return row
    data = _load_file()
    data.setdefault(COL_FACEBOOK_CONNECTIONS, {})[client_id] = row
    _save_file(data)
    return row


def save_facebook_oauth_state(state: str, payload: dict) -> dict:
    row = {"state": state, **payload}
    if _use_mongo():
        _mdb()[COL_FACEBOOK_OAUTH_STATES].replace_one(
            {"_id": state},
            {"_id": state, **row},
            upsert=True,
        )
        return row
    data = _load_file()
    data.setdefault(COL_FACEBOOK_OAUTH_STATES, {})[state] = row
    _save_file(data)
    return row


def pop_facebook_oauth_state(state: str) -> dict | None:
    if _use_mongo():
        doc = _mdb()[COL_FACEBOOK_OAUTH_STATES].find_one_and_delete({"_id": state})
        return _strip_mongo_id(doc) if doc else None
    data = _load_file()
    states = data.setdefault(COL_FACEBOOK_OAUTH_STATES, {})
    row = states.pop(state, None)
    _save_file(data)
    return dict(row) if isinstance(row, dict) else None


def save_social_post(post_id: str, post: dict) -> dict:
    row = {"id": post_id, **post}
    if _use_mongo():
        body = {k: v for k, v in row.items() if k != "id"}
        _mdb()[COL_SOCIAL_POSTS].replace_one(
            {"_id": post_id},
            {"_id": post_id, **body},
            upsert=True,
        )
        return row
    data = _load_file()
    data.setdefault(COL_SOCIAL_POSTS, {})[post_id] = row
    _save_file(data)
    return row


def fetch_social_post(post_id: str) -> dict | None:
    if _use_mongo():
        doc = _mdb()[COL_SOCIAL_POSTS].find_one({"_id": post_id})
        if not doc:
            return None
        return {"id": doc["_id"], **_strip_mongo_id(doc)}
    row = (_load_file().get(COL_SOCIAL_POSTS) or {}).get(post_id)
    return dict(row) if isinstance(row, dict) else None

def save_social_schedule(client_id: str, schedule: dict) -> dict:
    row = {"id": client_id, **schedule}
    if _use_mongo():
        body = {k: v for k, v in row.items() if k != "id"}
        _mdb()[COL_SOCIAL_SCHEDULES].replace_one(
            {"_id": client_id},
            {"_id": client_id, **body},
            upsert=True,
        )
        return row
    data = _load_file()
    data.setdefault(COL_SOCIAL_SCHEDULES, {})[client_id] = row
    _save_file(data)
    return row

def fetch_social_schedule(client_id: str) -> dict | None:
    if _use_mongo():
        doc = _mdb()[COL_SOCIAL_SCHEDULES].find_one({"_id": client_id})
        if not doc:
            return None
        return {"id": doc["_id"], **_strip_mongo_id(doc)}
    row = (_load_file().get(COL_SOCIAL_SCHEDULES) or {}).get(client_id)
    return dict(row) if isinstance(row, dict) else None


def fetch_all_clients() -> list[dict]:
    if _use_mongo():
        return [{"id": doc["_id"], **_strip_mongo_id(doc)} for doc in _mdb()[COL_CLIENTS].find()]
    return [{"id": k, **v} for k, v in _load_file().get(COL_CLIENTS, {}).items()]


def fetch_social_posts_for_source(
    client_id: str,
    *,
    content_plan_item_id: str | None = None,
    topic_id: str | None = None,
) -> list[dict]:
    query = {"client_id": client_id, "platform": "instagram"}
    if content_plan_item_id:
        query["content_plan_item_id"] = content_plan_item_id
    elif topic_id:
        query["topic_id"] = topic_id
    else:
        return []

    if _use_mongo():
        rows = []
        cursor = _mdb()[COL_SOCIAL_POSTS].find(query).sort("created_at", DESCENDING)
        for doc in cursor:
            rows.append({"id": doc["_id"], **_strip_mongo_id(doc)})
        return rows

    posts = (_load_file().get(COL_SOCIAL_POSTS) or {}).values()
    rows = []
    for post in posts:
        if not isinstance(post, dict):
            continue
        if any(post.get(key) != value for key, value in query.items()):
            continue
        rows.append({"id": post["id"], **post})
    rows.sort(key=lambda item: item.get("created_at") or "", reverse=True)
    return rows


def fetch_scheduled_posts(client_id: str) -> list[dict]:
    query = {"client_id": client_id, "publish_status": "scheduled"}
    if _use_mongo():
        rows = []
        cursor = _mdb()[COL_SOCIAL_POSTS].find(query).sort("queue_order", 1)
        for doc in cursor:
            rows.append({"id": doc["_id"], **_strip_mongo_id(doc)})
        return rows
    
    posts = (_load_file().get(COL_SOCIAL_POSTS) or {}).values()
    rows = []
    for post in posts:
        if isinstance(post, dict) and post.get("client_id") == client_id and post.get("publish_status") == "scheduled":
            rows.append({"id": post["id"], **post})
    rows.sort(key=lambda x: x.get("queue_order") or 0)
    return rows

def fetch_latest_draft_post(client_id: str) -> dict | None:
    query = {"client_id": client_id, "publish_status": "draft"}
    if _use_mongo():
        doc = _mdb()[COL_SOCIAL_POSTS].find_one(query, sort=[("created_at", -1)])
        if doc:
            return {"id": doc["_id"], **_strip_mongo_id(doc)}
        return None
    
    posts = (_load_file().get(COL_SOCIAL_POSTS) or {}).values()
    drafts = [p for p in posts if isinstance(p, dict) and p.get("client_id") == client_id and p.get("publish_status") in [None, "draft"]]
    if drafts:
        drafts.sort(key=lambda x: x.get("created_at") or "", reverse=True)
        return {"id": drafts[0]["id"], **drafts[0]}
    return None



def mark_social_post_selected(post_id: str) -> dict | None:
    post = fetch_social_post(post_id)
    if not post:
        return None

    source_query = {"client_id": post.get("client_id"), "platform": post.get("platform") or "instagram"}
    if post.get("source_type") == "script" and post.get("content_plan_item_id"):
        source_query["content_plan_item_id"] = post.get("content_plan_item_id")
    elif post.get("topic_id"):
        source_query["topic_id"] = post.get("topic_id")
    else:
        source_query["_id"] = post_id

    if _use_mongo():
        db = _mdb()
        db[COL_SOCIAL_POSTS].update_many(source_query, {"$set": {"is_selected": False}})
        db[COL_SOCIAL_POSTS].update_one(
            {"_id": post_id},
            {"$set": {"is_selected": True, "selected_at": _now_iso_for_db()}},
        )
        return fetch_social_post(post_id)

    data = _load_file()
    posts = data.setdefault(COL_SOCIAL_POSTS, {})
    for row_id, row in posts.items():
        if not isinstance(row, dict):
            continue
        if row.get("client_id") != source_query.get("client_id"):
            continue
        if row.get("platform") != source_query.get("platform"):
            continue
        if source_query.get("content_plan_item_id") and row.get("content_plan_item_id") != source_query.get("content_plan_item_id"):
            continue
        if source_query.get("topic_id") and row.get("topic_id") != source_query.get("topic_id"):
            continue
        if source_query.get("_id") and row_id != source_query.get("_id"):
            continue
        row["is_selected"] = False
    posts[post_id]["is_selected"] = True
    posts[post_id]["selected_at"] = _now_iso_for_db()
    _save_file(data)
    return dict(posts[post_id])


def delete_social_post(post_id: str) -> dict | None:
    post = fetch_social_post(post_id)
    if not post:
        return None
    if _use_mongo():
        _mdb()[COL_SOCIAL_POSTS].delete_one({"_id": post_id})
        return post
    data = _load_file()
    posts = data.setdefault(COL_SOCIAL_POSTS, {})
    posts.pop(post_id, None)
    _save_file(data)
    return post


def weekly_tracker_doc_id(client_id: str, year: int, month: int, week: int) -> str:
    return f"weekly:{client_id}:{int(year)}:{int(month)}:{int(week)}"


def fetch_weekly_tracker(client_id: str, year: int, month: int, week: int) -> dict | None:
    doc_id = weekly_tracker_doc_id(client_id, year, month, week)
    if _use_mongo():
        doc = _mdb()[COL_WEEKLY_TRACKERS].find_one({"_id": doc_id})
        if not doc:
            return None
        return {"id": doc["_id"], **_strip_mongo_id(doc)}
    row = (_load_file().get(COL_WEEKLY_TRACKERS) or {}).get(doc_id)
    return dict(row) if isinstance(row, dict) else None


def save_weekly_tracker(doc: dict) -> dict:
    client_id = doc["client_id"]
    year = int(doc["year"])
    month = int(doc["month"])
    week = int(doc["week"])
    doc_id = doc.get("id") or weekly_tracker_doc_id(client_id, year, month, week)
    row = {**doc, "id": doc_id, "client_id": client_id, "year": year, "month": month, "week": week}
    if _use_mongo():
        body = {k: v for k, v in row.items() if k != "id"}
        _mdb()[COL_WEEKLY_TRACKERS].replace_one(
            {"_id": doc_id},
            {"_id": doc_id, **body},
            upsert=True,
        )
        return row
    data = _load_file()
    data.setdefault(COL_WEEKLY_TRACKERS, {})[doc_id] = row
    _save_file(data)
    return row


def list_weekly_trackers_for_month(client_id: str, year: int, month: int) -> list[dict]:
    year = int(year)
    month = int(month)
    if _use_mongo():
        docs = _mdb()[COL_WEEKLY_TRACKERS].find(
            {"client_id": client_id, "year": year, "month": month}
        )
        return [{"id": doc["_id"], **_strip_mongo_id(doc)} for doc in docs]
    store = _load_file().get(COL_WEEKLY_TRACKERS) or {}
    rows = []
    for row in store.values():
        if not isinstance(row, dict):
            continue
        if row.get("client_id") != client_id:
            continue
        if int(row.get("year") or 0) != year or int(row.get("month") or 0) != month:
            continue
        rows.append(dict(row))
    return rows


def list_weekly_trackers_for_client(client_id: str) -> list[dict]:
    if _use_mongo():
        docs = _mdb()[COL_WEEKLY_TRACKERS].find({"client_id": client_id})
        return [{"id": doc["_id"], **_strip_mongo_id(doc)} for doc in docs]
    store = _load_file().get(COL_WEEKLY_TRACKERS) or {}
    rows = []
    for row in store.values():
        if isinstance(row, dict) and row.get("client_id") == client_id:
            rows.append(dict(row))
    return rows


def custom_tracker_doc_id(client_id: str, year: int, month: int, week: int) -> str:
    return f"custom:{client_id}:{int(year)}:{int(month)}:{int(week)}"


def fetch_custom_tracker(client_id: str, year: int, month: int, week: int) -> dict | None:
    doc_id = custom_tracker_doc_id(client_id, year, month, week)
    if _use_mongo():
        doc = _mdb()[COL_CUSTOM_TRACKERS].find_one({"_id": doc_id})
        if not doc:
            return None
        return {"id": doc["_id"], **_strip_mongo_id(doc)}
    row = (_load_file().get(COL_CUSTOM_TRACKERS) or {}).get(doc_id)
    return dict(row) if isinstance(row, dict) else None


def save_custom_tracker(doc: dict) -> dict:
    client_id = doc["client_id"]
    year = int(doc["year"])
    month = int(doc["month"])
    week = int(doc["week"])
    doc_id = doc.get("id") or custom_tracker_doc_id(client_id, year, month, week)
    row = {**doc, "id": doc_id, "client_id": client_id, "year": year, "month": month, "week": week}
    if _use_mongo():
        body = {k: v for k, v in row.items() if k != "id"}
        _mdb()[COL_CUSTOM_TRACKERS].replace_one(
            {"_id": doc_id},
            {"_id": doc_id, **body},
            upsert=True,
        )
        return row
    data = _load_file()
    data.setdefault(COL_CUSTOM_TRACKERS, {})[doc_id] = row
    _save_file(data)
    return row


def list_custom_trackers_for_month(client_id: str, year: int, month: int) -> list[dict]:
    year = int(year)
    month = int(month)
    if _use_mongo():
        docs = _mdb()[COL_CUSTOM_TRACKERS].find(
            {"client_id": client_id, "year": year, "month": month}
        )
        return [{"id": doc["_id"], **_strip_mongo_id(doc)} for doc in docs]
    store = _load_file().get(COL_CUSTOM_TRACKERS) or {}
    rows = []
    for row in store.values():
        if not isinstance(row, dict):
            continue
        if row.get("client_id") != client_id:
            continue
        if int(row.get("year") or 0) != year or int(row.get("month") or 0) != month:
            continue
        rows.append(dict(row))
    return rows


def sheet_comment_doc_id(
    client_id: str,
    year: int,
    month: int,
    week: int,
    row_key: str,
) -> str:
    return f"sheet:{client_id}:{int(year)}:{int(month)}:{int(week)}:weekly:{row_key}"


def list_sheet_comments_for_month(
    client_id: str,
    year: int,
    month: int,
    tracker: str = "weekly",
) -> list[dict]:
    year = int(year)
    month = int(month)
    if _use_mongo():
        docs = _mdb()[COL_TRACKER_SHEET_COMMENTS].find(
            {"client_id": client_id, "year": year, "month": month, "tracker": tracker}
        )
        return [{"id": doc["_id"], **_strip_mongo_id(doc)} for doc in docs]
    store = _load_file().get(COL_TRACKER_SHEET_COMMENTS) or {}
    rows = []
    for row in store.values():
        if not isinstance(row, dict):
            continue
        if row.get("client_id") != client_id:
            continue
        if int(row.get("year") or 0) != year or int(row.get("month") or 0) != month:
            continue
        if str(row.get("tracker") or "") != tracker:
            continue
        rows.append(dict(row))
    return rows


def save_sheet_comment(doc: dict) -> dict:
    client_id = doc["client_id"]
    year = int(doc["year"])
    month = int(doc["month"])
    week = int(doc["week"])
    row_key = str(doc["row_key"] or "").strip()
    tracker = str(doc.get("tracker") or "weekly").strip() or "weekly"
    doc_id = doc.get("id") or sheet_comment_doc_id(client_id, year, month, week, row_key)
    row = {
        **doc,
        "id": doc_id,
        "client_id": client_id,
        "year": year,
        "month": month,
        "week": week,
        "tracker": tracker,
        "row_key": row_key,
        "comment": str(doc.get("comment") or ""),
    }
    if _use_mongo():
        body = {k: v for k, v in row.items() if k != "id"}
        _mdb()[COL_TRACKER_SHEET_COMMENTS].replace_one(
            {"_id": doc_id},
            {"_id": doc_id, **body},
            upsert=True,
        )
        return row
    data = _load_file()
    data.setdefault(COL_TRACKER_SHEET_COMMENTS, {})[doc_id] = row
    _save_file(data)
    return row


def list_tracker_script_placements(client_id: str) -> list[dict]:
    """Map content-plan item ids to tracker week cards that currently hold them."""
    out = []
    for doc in list_weekly_trackers_for_client(client_id):
        year = int(doc.get("year") or 0)
        month = int(doc.get("month") or 0)
        week = int(doc.get("week") or 0)
        for card in doc.get("cards") or []:
            if not isinstance(card, dict):
                continue
            item_id = str(card.get("content_plan_item_id") or "").strip()
            if not item_id:
                continue
            out.append(
                {
                    "item_id": item_id,
                    "year": year,
                    "month": month,
                    "week": week,
                    "card_id": card.get("id") or "",
                    "card_type": card.get("type") or "",
                }
            )
    return out


def sync_tracker_scripts_for_item(client_id: str, item_id: str, script_text: str) -> int:
    """Copy updated script text onto every tracker card linked to this plan item."""
    item_id = str(item_id or "").strip()
    if not client_id or not item_id:
        return 0
    updated = 0
    for doc in list_weekly_trackers_for_client(client_id):
        changed = False
        for card in doc.get("cards") or []:
            if not isinstance(card, dict):
                continue
            if str(card.get("content_plan_item_id") or "") != item_id:
                continue
            assets = dict(card.get("assets") or {})
            assets["script_text"] = script_text or ""
            assets["script_url"] = ""
            card["assets"] = assets
            changed = True
            updated += 1
        if changed:
            save_weekly_tracker(doc)
    return updated


# ── content_videos (produced package per client + topic) ──────────────────────

CONTENT_VIDEO_YT_KEYS = (
    "yt_title",
    "yt_description",
    "yt_tags",
    "yt_thumbnail_url",
    "yt_thumbnail_prompt",
    "yt_locales",
)


def content_video_doc_id(client_id: str, topic_id: str) -> str:
    return f"cv:{client_id}:{topic_id}"


def _empty_content_video(client_id: str, topic_id: str) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    doc_id = content_video_doc_id(client_id, topic_id)
    return {
        "id": doc_id,
        "client_id": client_id,
        "topic_id": topic_id,
        "topic_text": "",
        "source": "manual",
        "content_plan_item_id": None,
        "yt_locales": {},
        "youtube_urls": [],
        "instagram_urls": [],
        "facebook_urls": [],
        "source_urls": [],
        "created_at": now,
        "updated_at": now,
    }


def _content_video_from_doc(doc: dict | None) -> dict | None:
    if not isinstance(doc, dict):
        return None
    row = _strip_mongo_id(doc)
    row.setdefault("id", doc.get("_id") or content_video_doc_id(row.get("client_id") or "", row.get("topic_id") or ""))
    row.setdefault("yt_locales", {})
    row.setdefault("youtube_urls", [])
    row.setdefault("instagram_urls", [])
    row.setdefault("facebook_urls", [])
    row.setdefault("source_urls", [])
    return row


def _normalize_locale_payload(locale: dict | None) -> dict:
    loc = dict(locale or {})
    tags = loc.get("yt_tags")
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.replace(",", " ").split() if t.strip()]
    elif not isinstance(tags, list):
        tags = []
    return {
        "yt_title": loc.get("yt_title") or "",
        "yt_description": loc.get("yt_description") or "",
        "yt_tags": [str(t).strip() for t in tags if str(t).strip()],
        "yt_thumbnail_url": loc.get("yt_thumbnail_url") or "",
        "yt_thumbnail_prompt": loc.get("yt_thumbnail_prompt") or "",
    }


def _locale_has_title(locale: dict | None) -> bool:
    if not isinstance(locale, dict):
        return False
    return bool(str(locale.get("yt_title") or "").strip())


def _row_has_yt_metadata(row: dict | None) -> bool:
    if not isinstance(row, dict):
        return False
    if str(row.get("yt_title") or "").strip():
        return True
    locales = row.get("yt_locales")
    if not isinstance(locales, dict):
        return False
    return any(_locale_has_title(loc) for loc in locales.values())


def strip_yt_fields_from_row(row: dict | None) -> bool:
    """Remove yt_* keys from a plan item / keyword_analysis row. Returns True if anything changed."""
    if not isinstance(row, dict):
        return False
    changed = False
    for key in CONTENT_VIDEO_YT_KEYS:
        if key in row:
            row.pop(key, None)
            changed = True
    return changed


def strip_yt_fields_from_suggestions(suggestions: dict | None) -> bool:
    if not isinstance(suggestions, dict):
        return False
    changed = False
    for row in suggestions.get("items") or []:
        if isinstance(row, dict) and strip_yt_fields_from_row(row):
            changed = True
    for row in suggestions.get("keyword_analysis") or []:
        if isinstance(row, dict) and strip_yt_fields_from_row(row):
            changed = True
    return changed


def _locales_from_plan_row(row: dict | None) -> dict[str, dict]:
    if not isinstance(row, dict):
        return {}
    out: dict[str, dict] = {}
    nested = row.get("yt_locales")
    if isinstance(nested, dict):
        for lang, loc in nested.items():
            if not isinstance(loc, dict):
                continue
            payload = _normalize_locale_payload(loc)
            if payload.get("yt_title") or payload.get("yt_description") or payload.get("yt_thumbnail_url"):
                out[str(lang)] = payload
    if not out and (row.get("yt_title") or row.get("yt_description") or row.get("yt_thumbnail_url")):
        out["hinglish"] = _normalize_locale_payload(row)
    return out


def _merge_locales(preferred: dict[str, dict], extra: dict[str, dict]) -> dict[str, dict]:
    merged = dict(extra or {})
    for lang, loc in (preferred or {}).items():
        if _locale_has_title(loc) or lang not in merged or not _locale_has_title(merged.get(lang)):
            merged[lang] = loc
    return merged


def _mirror_legacy_yt_fields(row: dict, locales: dict | None) -> dict:
    loc_map = locales if isinstance(locales, dict) else {}
    hinglish = loc_map.get("hinglish") if isinstance(loc_map.get("hinglish"), dict) else {}
    fallback = next((v for v in loc_map.values() if isinstance(v, dict)), {}) or {}
    src = hinglish or fallback
    row["yt_locales"] = loc_map
    row["yt_title"] = src.get("yt_title") or None
    row["yt_description"] = src.get("yt_description") or None
    row["yt_tags"] = src.get("yt_tags") or None
    row["yt_thumbnail_url"] = src.get("yt_thumbnail_url") or None
    row["yt_thumbnail_prompt"] = src.get("yt_thumbnail_prompt") or None
    return row


def fetch_content_video(client_id: str, topic_id: str) -> dict | None:
    if not client_id or not topic_id:
        return None
    doc_id = content_video_doc_id(client_id, topic_id)
    if _use_mongo():
        return _content_video_from_doc(_mdb()[COL_CONTENT_VIDEOS].find_one({"_id": doc_id}))
    row = (_load_file().get(COL_CONTENT_VIDEOS) or {}).get(doc_id)
    return _content_video_from_doc(row) if isinstance(row, dict) else None


def list_content_videos_for_client(client_id: str) -> list[dict]:
    if _use_mongo():
        docs = _mdb()[COL_CONTENT_VIDEOS].find({"client_id": client_id})
        return [row for row in (_content_video_from_doc(doc) for doc in docs) if row]
    store = _load_file().get(COL_CONTENT_VIDEOS) or {}
    rows = []
    for row in store.values():
        if isinstance(row, dict) and row.get("client_id") == client_id:
            packed = _content_video_from_doc(row)
            if packed:
                rows.append(packed)
    return rows


def _persist_content_video(row: dict) -> dict:
    client_id = row["client_id"]
    topic_id = row["topic_id"]
    doc_id = content_video_doc_id(client_id, topic_id)
    now = datetime.now(timezone.utc).isoformat()
    row["id"] = doc_id
    row.setdefault("created_at", now)
    row["updated_at"] = now
    row.setdefault("yt_locales", {})
    row.setdefault("youtube_urls", [])
    row.setdefault("instagram_urls", [])
    row.setdefault("facebook_urls", [])
    row.setdefault("source_urls", [])
    if _use_mongo():
        mongo_row = {k: v for k, v in row.items() if k != "id"}
        mongo_row["_id"] = doc_id
        _mdb()[COL_CONTENT_VIDEOS].replace_one({"_id": doc_id}, mongo_row, upsert=True)
        return row
    data = _load_file()
    data.setdefault(COL_CONTENT_VIDEOS, {})[doc_id] = row
    _save_file(data)
    return row


def upsert_content_video(
    client_id: str,
    topic_id: str,
    *,
    topic_text: str | None = None,
    source: str | None = None,
    content_plan_item_id: str | None = None,
    locales: dict | None = None,
    replace_locales: bool = False,
    merge_missing_locales_only: bool = False,
) -> dict:
    """Create or update the produced-video package for one client+topic.

    replace_locales: overwrite the given language keys (generate/refine).
    merge_missing_locales_only: fill languages that do not already have a title (migrate).
    """
    existing = fetch_content_video(client_id, topic_id)
    row = existing or _empty_content_video(client_id, topic_id)
    if topic_text and not row.get("topic_text"):
        row["topic_text"] = topic_text
    elif topic_text and not merge_missing_locales_only:
        row["topic_text"] = topic_text
    if source:
        if source == "script" or row.get("source") != "script":
            row["source"] = source
    if content_plan_item_id:
        row["content_plan_item_id"] = content_plan_item_id
    incoming = {}
    if isinstance(locales, dict):
        for lang, loc in locales.items():
            if isinstance(loc, dict):
                incoming[str(lang)] = _normalize_locale_payload(loc)
    current = dict(row.get("yt_locales") or {})
    if replace_locales:
        current.update(incoming)
    elif merge_missing_locales_only:
        for lang, loc in incoming.items():
            if lang not in current or not _locale_has_title(current.get(lang)):
                current[lang] = loc
    elif incoming:
        current.update(incoming)
    row["yt_locales"] = current
    return _persist_content_video(row)


def append_content_video_posted_url(
    client_id: str,
    topic_id: str,
    platform: str,
    entry: dict,
) -> dict | None:
    """Append a posted watch/permalink URL. No-op if topic_id is missing or url is empty."""
    if not client_id or not topic_id:
        return None
    url = str((entry or {}).get("url") or "").strip()
    if not url:
        return None
    row = fetch_content_video(client_id, topic_id) or _empty_content_video(client_id, topic_id)
    key = {
        "youtube": "youtube_urls",
        "instagram": "instagram_urls",
        "facebook": "facebook_urls",
    }.get(platform)
    if not key:
        return row
    posted = dict(entry)
    posted["url"] = url
    posted.setdefault("posted_at", datetime.now(timezone.utc).isoformat())
    bucket = list(row.get(key) or [])
    if any(isinstance(item, dict) and item.get("url") == url for item in bucket):
        row[key] = bucket
        return _persist_content_video(row)
    bucket.append(posted)
    row[key] = bucket
    return _persist_content_video(row)


def append_content_video_source_url(
    client_id: str,
    topic_id: str,
    entry: dict,
) -> dict | None:
    """Append a pasted Drive/file URL. Dedupe by url + kind."""
    if not client_id or not topic_id:
        return None
    url = str((entry or {}).get("url") or "").strip()
    kind = str((entry or {}).get("kind") or "").strip()
    if not url or kind not in {"youtube", "social"}:
        return None
    row = fetch_content_video(client_id, topic_id) or _empty_content_video(client_id, topic_id)
    posted = dict(entry)
    posted["url"] = url
    posted["kind"] = kind
    posted.setdefault("posted_at", datetime.now(timezone.utc).isoformat())
    bucket = list(row.get("source_urls") or [])
    if any(
        isinstance(item, dict) and item.get("url") == url and item.get("kind") == kind
        for item in bucket
    ):
        row["source_urls"] = bucket
        return _persist_content_video(row)
    bucket.append(posted)
    row["source_urls"] = bucket
    return _persist_content_video(row)


def list_all_content_plans() -> list[dict]:
    """Return every content_plans document (Mongo or nested db.json clients)."""
    plans: list[dict] = []
    if _use_mongo():
        for doc in _mdb()[COL_CONTENT_PLANS].find({}):
            row = _strip_mongo_id(doc)
            row["_id"] = doc.get("_id")
            plans.append(row)
        return plans
    data = _load_file()
    for user in (data.get("users") or {}).values():
        if not isinstance(user, dict):
            continue
        for client in user.get("clients") or []:
            if not isinstance(client, dict):
                continue
            suggestions = client.get("content_suggestions")
            coverage = client.get("content_topic_coverage")
            if not isinstance(suggestions, dict) and not isinstance(coverage, dict):
                continue
            plans.append({
                "_id": client.get("id"),
                "content_suggestions": suggestions,
                "content_topic_coverage": coverage,
            })
    return plans


def migrate_content_videos_from_plans() -> dict:
    """Copy yt_* / yt_locales off content_plans into content_videos. Idempotent."""
    scanned = 0
    upserted = 0
    stripped = 0
    skipped = 0
    for plan in list_all_content_plans():
        client_id = str(plan.get("_id") or "").strip()
        suggestions = plan.get("content_suggestions")
        if not client_id or not isinstance(suggestions, dict):
            continue
        scanned += 1
        items = [row for row in (suggestions.get("items") or []) if isinstance(row, dict)]
        keywords = [row for row in (suggestions.get("keyword_analysis") or []) if isinstance(row, dict)]
        by_topic: dict[str, dict] = {}

        for item in items:
            topic_id = str(item.get("topic_id") or "").strip()
            if not topic_id or not _row_has_yt_metadata(item):
                continue
            entry = by_topic.setdefault(topic_id, {
                "item": None,
                "keyword": None,
                "topic_text": "",
                "source": "manual",
                "content_plan_item_id": None,
            })
            entry["item"] = item
            entry["topic_text"] = item.get("topic") or item.get("topic_text") or entry["topic_text"]
            entry["content_plan_item_id"] = item.get("id") or entry["content_plan_item_id"]
            if item.get("script"):
                entry["source"] = "script"

        for kw in keywords:
            topic_id = str(kw.get("topic_id") or "").strip()
            if not topic_id or not _row_has_yt_metadata(kw):
                continue
            entry = by_topic.setdefault(topic_id, {
                "item": None,
                "keyword": None,
                "topic_text": "",
                "source": "manual",
                "content_plan_item_id": None,
            })
            entry["keyword"] = kw
            entry["topic_text"] = entry["topic_text"] or kw.get("topic_text") or ""
            matching_item = next((it for it in items if it.get("topic_id") == topic_id), None)
            if matching_item and matching_item.get("script"):
                entry["source"] = "script"
            if matching_item and matching_item.get("id") and not entry["content_plan_item_id"]:
                entry["content_plan_item_id"] = matching_item.get("id")

        if not by_topic:
            skipped += 1
            continue

        did_strip = False
        for topic_id, entry in by_topic.items():
            item_locales = _locales_from_plan_row(entry.get("item"))
            kw_locales = _locales_from_plan_row(entry.get("keyword"))
            locales = _merge_locales(item_locales, kw_locales)
            if not locales:
                continue
            existing = fetch_content_video(client_id, topic_id)
            upsert_content_video(
                client_id,
                topic_id,
                topic_text=entry.get("topic_text") or "",
                source=entry.get("source") or "manual",
                content_plan_item_id=entry.get("content_plan_item_id"),
                locales=locales,
                merge_missing_locales_only=bool(existing),
            )
            upserted += 1
            if strip_yt_fields_from_row(entry.get("item")):
                did_strip = True
            if strip_yt_fields_from_row(entry.get("keyword")):
                did_strip = True

        if did_strip:
            payload = {"content_suggestions": suggestions}
            if "content_topic_coverage" in plan:
                payload["content_topic_coverage"] = plan["content_topic_coverage"]
            replace_content_plan(client_id, payload)
            stripped += 1

    summary = {
        "scanned_plans": scanned,
        "topics_upserted": upserted,
        "plans_stripped": stripped,
        "plans_without_yt": skipped,
    }
    print(f"[db] content_videos migrate {summary}", flush=True)
    return summary


def hydrate_suggestions_from_content_videos(client_id: str, suggestions: dict | None) -> dict:
    """Copy current yt locales onto plan items / keyword_analysis for API responses.

    Lazy-backfills leftover nested yt_* into content_videos, then strips the plan.
    """
    if not isinstance(suggestions, dict):
        return {}
    items = [row for row in (suggestions.get("items") or []) if isinstance(row, dict)]
    keywords = [row for row in (suggestions.get("keyword_analysis") or []) if isinstance(row, dict)]
    packages = {row.get("topic_id"): row for row in list_content_videos_for_client(client_id)}
    dirty = False

    def _ensure_package(topic_id: str, row: dict, *, source_hint: str, item_id: str | None, topic_text: str) -> dict | None:
        nonlocal dirty
        pkg = packages.get(topic_id)
        leftover = _locales_from_plan_row(row) if _row_has_yt_metadata(row) else {}
        if leftover and not pkg:
            pkg = upsert_content_video(
                client_id,
                topic_id,
                topic_text=topic_text,
                source=source_hint,
                content_plan_item_id=item_id,
                locales=leftover,
            )
            packages[topic_id] = pkg
            if strip_yt_fields_from_row(row):
                dirty = True
        elif leftover and pkg:
            missing = False
            current = dict(pkg.get("yt_locales") or {})
            for lang, loc in leftover.items():
                if lang not in current or not _locale_has_title(current.get(lang)):
                    current[lang] = loc
                    missing = True
            if missing:
                pkg = upsert_content_video(
                    client_id,
                    topic_id,
                    topic_text=topic_text or pkg.get("topic_text") or "",
                    source=source_hint,
                    content_plan_item_id=item_id,
                    locales=leftover,
                    merge_missing_locales_only=True,
                )
                packages[topic_id] = pkg
            if strip_yt_fields_from_row(row):
                dirty = True
        elif _row_has_yt_metadata(row):
            if strip_yt_fields_from_row(row):
                dirty = True
        return pkg

    for item in items:
        topic_id = str(item.get("topic_id") or "").strip()
        if not topic_id:
            continue
        source_hint = "script" if item.get("script") else "manual"
        _ensure_package(
            topic_id,
            item,
            source_hint=source_hint,
            item_id=item.get("id"),
            topic_text=item.get("topic") or item.get("topic_text") or item.get("working_title") or "",
        )

    for kw in keywords:
        topic_id = str(kw.get("topic_id") or "").strip()
        if not topic_id:
            continue
        matching_item = next((it for it in items if it.get("topic_id") == topic_id), None)
        source_hint = "script" if matching_item and matching_item.get("script") else "manual"
        _ensure_package(
            topic_id,
            kw,
            source_hint=source_hint,
            item_id=(matching_item or {}).get("id") if matching_item else None,
            topic_text=kw.get("topic_text") or "",
        )

    for item in items:
        topic_id = str(item.get("topic_id") or "").strip()
        pkg = packages.get(topic_id) if topic_id else None
        if pkg:
            _mirror_legacy_yt_fields(item, pkg.get("yt_locales") or {})

    for kw in keywords:
        topic_id = str(kw.get("topic_id") or "").strip()
        pkg = packages.get(topic_id) if topic_id else None
        if pkg:
            _mirror_legacy_yt_fields(kw, pkg.get("yt_locales") or {})

    if dirty:
        payload = {"content_suggestions": suggestions}
        existing = fetch_content_plan(client_id) or {}
        if "content_topic_coverage" in existing:
            payload["content_topic_coverage"] = existing.get("content_topic_coverage")
        replace_content_plan(client_id, payload)
    return suggestions


def fetch_client_bundle(
    client_id: str,
    username: str,
    *,
    with_videos: bool = True,
    with_topics: bool = True,
    with_plan: bool = True,
) -> dict | None:
    """Assemble one client from collections (in-memory only — not a full-DB hydrate)."""
    base = fetch_client_doc(client_id, username=username)
    if not base:
        return None
    topics = fetch_topics(client_id) if with_topics else []
    channels = list_channels_meta(client_id)
    if with_videos:
        channels = [
            {**ch, "videos": list_videos_for_channel(ch["id"], client_id)}
            for ch in channels
        ]
    client = {**base, "topics": topics, "channels": channels}
    if with_plan:
        plan = fetch_content_plan(client_id)
        if plan:
            if plan.get("content_topic_coverage") is not None:
                client["content_topic_coverage"] = plan["content_topic_coverage"]
            if plan.get("content_suggestions") is not None:
                client["content_suggestions"] = plan["content_suggestions"]
    return client


def upsert_channel(
    username: str,
    client_id: str,
    channel: dict,
    *,
    replace_videos: bool = False,
) -> None:
    """Upsert one channels doc by channel id. Optionally replace its videos."""
    chid = channel.get("id")
    if not chid:
        return
    meta = {k: channel.get(k) for k in CHANNEL_META_KEYS}
    incoming_lang = (channel.get("language") or "").strip() or None
    if incoming_lang:
        meta["language"] = incoming_lang
    else:
        meta.pop("language", None)
    if _use_mongo():
        existing = _mdb()[COL_CHANNELS].find_one({"_id": chid}, {"language": 1})
        if "language" not in meta and existing and existing.get("language"):
            meta["language"] = existing.get("language")
        _mdb()[COL_CHANNELS].replace_one(
            {"_id": chid},
            {"_id": chid, "client_id": client_id, "username": username, **meta},
            upsert=True,
        )
        if replace_videos:
            replace_channel_videos(chid, client_id, channel.get("videos") or [])
        return

    data = _load_file()
    user = (data.get("users") or {}).get(username)
    if not user:
        return
    for client in user.get("clients") or []:
        if not isinstance(client, dict) or client.get("id") != client_id:
            continue
        channels = client.setdefault("channels", [])
        for i, existing in enumerate(channels):
            if isinstance(existing, dict) and existing.get("id") == chid:
                videos = (
                    channel.get("videos")
                    if replace_videos
                    else existing.get("videos", [])
                )
                language = meta.get("language") or existing.get("language")
                row = {**existing, **meta, "id": chid, "videos": videos or []}
                if language:
                    row["language"] = language
                channels[i] = row
                _save_file(data)
                return
        channels.append(
            {
                "id": chid,
                **meta,
                "videos": (channel.get("videos") or []) if replace_videos else [],
            }
        )
        _save_file(data)
        return


def delete_channel_owned(channel_id: str, client_id: str, username: str) -> bool:
    """Delete one channel + its videos by ids."""
    if _use_mongo():
        mdb = _mdb()
        ch = mdb[COL_CHANNELS].find_one(
            {"_id": channel_id, "client_id": client_id, "username": username},
            {"_id": 1},
        )
        if not ch:
            return False
        mdb[COL_VIDEOS].delete_many({"channel_id": channel_id, "client_id": client_id})
        mdb[COL_CHANNELS].delete_one({"_id": channel_id, "client_id": client_id})
        return True

    data = _load_file()
    user = (data.get("users") or {}).get(username)
    if not user:
        return False
    for client in user.get("clients") or []:
        if not isinstance(client, dict) or client.get("id") != client_id:
            continue
        before = client.get("channels") or []
        after = [
            c
            for c in before
            if not (isinstance(c, dict) and c.get("id") == channel_id)
        ]
        if len(after) == len(before):
            return False
        client["channels"] = after
        _save_file(data)
        return True
    return False


def sync_client_channels(
    username: str,
    client_id: str,
    channels: list[dict],
    *,
    drop_missing: bool = False,
) -> None:
    """Upsert channel rows for a client. Optionally delete channels not in the list."""
    keep_ids: set[str] = set()
    for channel in channels:
        if not isinstance(channel, dict) or not channel.get("id"):
            continue
        keep_ids.add(channel["id"])
        if _use_mongo():
            # Preserve videos in videos collection (do not rewrite them here).
            upsert_channel(username, client_id, channel, replace_videos=False)
        else:
            row = dict(channel)
            if "videos" not in row:
                row["videos"] = list_videos_for_channel(channel["id"], client_id)
            upsert_channel(username, client_id, row, replace_videos=True)

    if not drop_missing:
        return

    if _use_mongo():
        mdb = _mdb()
        for ch in mdb[COL_CHANNELS].find(
            {
                "client_id": client_id,
                "username": username,
                "_id": {"$nin": list(keep_ids)},
            },
            {"_id": 1},
        ):
            delete_channel_owned(ch["_id"], client_id, username)
        return

    for chid in list_channel_ids(client_id):
        if chid not in keep_ids:
            delete_channel_owned(chid, client_id, username)


def heal_user_pointers(username: str) -> None:
    """Fix stale active_client_id / active_channel_id using collection lookups only."""
    user = fetch_user(username)
    if not user:
        return
    clients = list_clients_for_user(username, with_topics=False)
    client_ids = {c["id"] for c in clients}
    active_cid = user.get("active_client_id")
    patch: dict[str, Any] = {}
    if active_cid and active_cid not in client_ids:
        active_cid = clients[0]["id"] if clients else None
        patch["active_client_id"] = active_cid
    elif not active_cid and clients:
        active_cid = clients[0]["id"]
        patch["active_client_id"] = active_cid

    active_chid = user.get("active_channel_id")
    if active_cid:
        ch_ids = list_channel_ids(active_cid)
        if active_chid and active_chid not in ch_ids:
            patch["active_channel_id"] = ch_ids[0] if ch_ids else None
        elif not active_chid and ch_ids:
            patch["active_channel_id"] = ch_ids[0]
    elif active_chid:
        patch["active_channel_id"] = None

    if patch:
        update_user_fields(username, **patch)


def fetch_video_titles(client_id: str) -> list[str]:
    if _use_mongo():
        titles: list[str] = []
        for v in _mdb()[COL_VIDEOS].find({"client_id": client_id}, {"title": 1}):
            t = (v.get("title") or "").strip()
            if t:
                titles.append(t)
        return titles
    data = _load_file()
    for user in (data.get("users") or {}).values():
        for client in user.get("clients") or []:
            if isinstance(client, dict) and client.get("id") == client_id:
                out: list[str] = []
                for ch in client.get("channels") or []:
                    for video in ch.get("videos") or []:
                        t = (video.get("title") or "").strip()
                        if t:
                            out.append(t)
                return out
    return []


def delete_user(username: str) -> bool:
    """Remove a user and cascade their clients/channels/videos/topics/plans."""
    if _use_mongo():
        mdb = _mdb()
        if not mdb[COL_USERS].find_one({"_id": username}, {"_id": 1}):
            return False
        _cascade_delete_user(mdb, username)
        return True
    data = _load_file()
    users = data.get("users") or {}
    if username not in users:
        return False
    del users[username]
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump({"users": users}, f, indent=4)
    return True


def _report_from_doc(doc: dict) -> dict:
    row = _strip_mongo_id(doc)
    row["id"] = doc["_id"]
    return row


def fetch_monthly_report(report_id: str, *, username: str | None = None) -> dict | None:
    if _use_mongo():
        query: dict[str, Any] = {"_id": report_id}
        if username:
            query["username"] = username
        doc = _mdb()[COL_MONTHLY_REPORTS].find_one(query)
        return _report_from_doc(doc) if doc else None
    data = _load_file()
    reports = data.get("monthly_reports") or {}
    doc = reports.get(report_id)
    if not doc:
        return None
    if username and doc.get("username") != username:
        return None
    return {"id": report_id, **doc}


def fetch_monthly_report_by_month(
    client_id: str,
    report_month: str,
    *,
    username: str | None = None,
) -> dict | None:
    if _use_mongo():
        query: dict[str, Any] = {"client_id": client_id, "report_month": report_month}
        if username:
            query["username"] = username
        doc = _mdb()[COL_MONTHLY_REPORTS].find_one(query)
        return _report_from_doc(doc) if doc else None
    data = _load_file()
    for rid, doc in (data.get("monthly_reports") or {}).items():
        if not isinstance(doc, dict):
            continue
        if doc.get("client_id") != client_id or doc.get("report_month") != report_month:
            continue
        if username and doc.get("username") != username:
            continue
        return {"id": rid, **doc}
    return None


def list_monthly_reports(client_id: str, *, username: str) -> list[dict]:
    """List report summaries (omit heavy metrics/html payloads)."""
    summary_keys = (
        "client_id",
        "username",
        "report_month",
        "previous_month",
        "ai_videos_started_from",
        "channel_ids",
        "status",
        "error",
        "created_at",
        "updated_at",
        "has_metrics_cache",
        "refine_history",
    )
    if _use_mongo():
        cursor = (
            _mdb()[COL_MONTHLY_REPORTS]
            .find({"client_id": client_id, "username": username})
            .sort("report_month", -1)
        )
        out = []
        for doc in cursor:
            row = _report_from_doc(doc)
            slim = {k: row.get(k) for k in summary_keys if k in row or k == "has_metrics_cache"}
            slim["id"] = row["id"]
            # Metrics live on disk, not in DB
            from app.services.monthly_report_render import has_metrics_cache

            slim["has_metrics_cache"] = has_metrics_cache(row["id"])
            slim["refine_history"] = list(row.get("refine_history") or [])[-5:]
            out.append(slim)
        return out

    data = _load_file()
    out = []
    from app.services.monthly_report_render import has_metrics_cache

    for rid, doc in (data.get("monthly_reports") or {}).items():
        if not isinstance(doc, dict):
            continue
        if doc.get("client_id") != client_id or doc.get("username") != username:
            continue
        slim = {k: doc.get(k) for k in summary_keys if k != "has_metrics_cache"}
        slim["id"] = rid
        slim["has_metrics_cache"] = has_metrics_cache(rid)
        slim["refine_history"] = list(doc.get("refine_history") or [])[-5:]
        out.append(slim)
    out.sort(key=lambda r: r.get("report_month") or "", reverse=True)
    return out


def upsert_monthly_report(report: dict) -> dict:
    """Insert or replace a monthly report document. Requires id, client_id, username, report_month.

    Metrics are never stored in DB (local file cache only).
    """
    report_id = report["id"]
    body = {k: v for k, v in report.items() if k not in {"id", "metrics"}}
    if _use_mongo():
        _mdb()[COL_MONTHLY_REPORTS].replace_one(
            {"_id": report_id},
            {"_id": report_id, **body},
            upsert=True,
        )
        return fetch_monthly_report(report_id) or {"id": report_id, **body}

    data = _load_file()
    reports = data.setdefault("monthly_reports", {})
    reports[report_id] = body
    _save_file(data)
    return {"id": report_id, **body}


def update_monthly_report_fields(
    report_id: str,
    fields: dict[str, Any],
    *,
    unset: list[str] | None = None,
) -> dict | None:
    """Patch report fields. Use unset=['metrics'] to drop heavy payloads from DB."""
    unset_keys = list(unset or [])
    # Never persist metrics blob in DB — local file cache only.
    if "metrics" in fields:
        fields = {k: v for k, v in fields.items() if k != "metrics"}
        if "metrics" not in unset_keys:
            unset_keys.append("metrics")

    if _use_mongo():
        mdb = _mdb()
        ops: dict[str, Any] = {}
        if fields:
            ops["$set"] = fields
        if unset_keys:
            ops["$unset"] = {k: "" for k in unset_keys}
        if not ops:
            return fetch_monthly_report(report_id)
        result = mdb[COL_MONTHLY_REPORTS].update_one({"_id": report_id}, ops)
        if result.matched_count == 0:
            return None
        return fetch_monthly_report(report_id)

    data = _load_file()
    reports = data.get("monthly_reports") or {}
    doc = reports.get(report_id)
    if not isinstance(doc, dict):
        return None
    doc.update(fields)
    for key in unset_keys:
        doc.pop(key, None)
    _save_file(data)
    return {"id": report_id, **doc}


def seed_db() -> None:
    from app.config import settings

    username = (settings.SEED_DEMO_USERNAME or "").strip()
    password = settings.SEED_DEMO_PASSWORD or ""
    if not username or not password:
        return
    if fetch_user(username):
        return
    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    insert_user(
        {
            "username": username,
            "hashed_password": hashed,
            "is_active": True,
            "active_client_id": None,
            "active_channel_id": None,
            "clients": [],
        }
    )


def collection_stats() -> dict[str, int]:
    if not _use_mongo():
        nested = _load_file()
        users = nested.get("users") or {}
        n_clients = sum(len(u.get("clients") or []) for u in users.values())
        return {
            "mode": "file",
            "users": len(users),
            "clients_nested": n_clients,
            "monthly_reports": len(nested.get("monthly_reports") or {}),
        }
    db = _mdb()
    return {
        "mode": "mongo",
        COL_USERS: db[COL_USERS].estimated_document_count(),
        COL_CLIENTS: db[COL_CLIENTS].estimated_document_count(),
        COL_CHANNELS: db[COL_CHANNELS].estimated_document_count(),
        COL_VIDEOS: db[COL_VIDEOS].estimated_document_count(),
        COL_TOPICS: db[COL_TOPICS].estimated_document_count(),
        COL_CONTENT_PLANS: db[COL_CONTENT_PLANS].estimated_document_count(),
        COL_CONTENT_VIDEOS: db[COL_CONTENT_VIDEOS].estimated_document_count(),
        COL_WEEKLY_TRACKERS: db[COL_WEEKLY_TRACKERS].estimated_document_count(),
        COL_CUSTOM_TRACKERS: db[COL_CUSTOM_TRACKERS].estimated_document_count(),
        COL_TRACKER_SHEET_COMMENTS: db[COL_TRACKER_SHEET_COMMENTS].estimated_document_count(),
        COL_MONTHLY_REPORTS: db[COL_MONTHLY_REPORTS].estimated_document_count(),
    }


seed_db()
try:
    migrate_content_videos_from_plans()
except Exception as exc:  # noqa: BLE001 — never block app boot on a one-shot backfill
    print(f"[db] content_videos migrate skipped: {exc}", flush=True)
