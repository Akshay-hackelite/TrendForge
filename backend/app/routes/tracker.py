from __future__ import annotations

import mimetypes
import uuid
from calendar import monthrange
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse

from app import schemas
from app.auth import get_current_user
from app.config import settings
from app.database import (
    fetch_client_bundle,
    fetch_content_video,
    fetch_weekly_tracker,
    list_clients_for_user,
    list_tracker_script_placements,
    list_weekly_trackers_for_month,
    save_weekly_tracker,
)
from app.services.gcs_storage import upload_bytes

router = APIRouter(tags=["weekly-tracker"])

TRACKER_ASSETS_DIR = Path(__file__).resolve().parent.parent.parent / "social_assets" / "weekly_tracker"
UPLOADED_VIDEOS_DIR = TRACKER_ASSETS_DIR.parent / "uploaded_videos"
VIDEO_MIME_TYPES = {"video/mp4", "video/quicktime", "video/webm"}
VIDEO_EXTS = {".mp4", ".mov", ".webm"}

CARD_TYPES = ("long_video", "short", "static_post", "blog")
LANG_ORDER = ("hinglish",)
DEFAULT_PLATFORMS = {
    "long_video": ["youtube", "facebook", "instagram"],
    "short": ["youtube", "facebook", "instagram"],
    "static_post": ["facebook", "instagram"],
    "blog": ["website"],
}
STAGES = {
    "long_video": [
        "planned",
        "script_generated",
        "yt_metadata_generated",
        "audio_generated",
        "video_edited",
        "shared_with_doctor",
        "posted",
    ],
    "short": [
        "planned",
        "script_generated",
        "yt_metadata_generated",
        "audio_generated",
        "video_edited",
        "shared_with_doctor",
        "posted",
    ],
    "static_post": ["planned", "posted"],
    "blog": ["planned", "published"],
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _require_client(username: str, client_id: str) -> dict:
    client = fetch_client_bundle(client_id, username, with_videos=False)
    if not client:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")
    return client


def assigned_languages(client: dict) -> list[str]:
    return ["hinglish"]


def _new_id(prefix: str = "id") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


VIDEO_DEFAULT_SLOTS = {
    "hinglish": ["youtube", "facebook", "instagram"],
}


def _empty_assets() -> dict:
    return {"script_url": "", "script_text": "", "audio_url": "", "video_url": ""}


def default_card(card_type: str, sort_order: int, *, is_default: bool = False) -> dict:
    if card_type not in CARD_TYPES:
        raise HTTPException(status_code=400, detail="Invalid card type")
    return {
        "id": _new_id("card"),
        "type": card_type,
        "title": "",
        "started": False,
        "collapsed": True,
        "sort_order": sort_order,
        "stage": "planned",
        "is_default": is_default,
        "assets": _empty_assets(),
        "destinations": [],
        "structure": {
            "platforms": list(DEFAULT_PLATFORMS[card_type]),
            "extra_slots": [],
            "hidden_cells": [],
        },
        "generated_post_ids": [],
        "destination_post_ids": {},
        "feedback_notes": [],
        "doctor_notes": [],
        "doctor_files": [],
        "content_plan_item_id": None,
        "topic_id": None,
    }


def seed_default_cards() -> list[dict]:
    return [
        default_card("long_video", 0, is_default=True),
        default_card("short", 1, is_default=True),
        default_card("static_post", 2, is_default=True),
        default_card("blog", 3, is_default=True),
    ]


def seed_destinations_for_card(card: dict, languages: list[str]) -> dict:
    if card.get("destinations"):
        return card
    langs = languages or list(LANG_ORDER)
    destinations = []
    if card["type"] in {"long_video", "short"}:
        for lang in langs:
            for platform in VIDEO_DEFAULT_SLOTS.get(lang, ["youtube", "facebook"]):
                destinations.append(
                    {
                        "id": _new_id("dest"),
                        "language": lang,
                        "platform": platform,
                        "url": "",
                    }
                )
    else:
        platforms = list((card.get("structure") or {}).get("platforms") or DEFAULT_PLATFORMS.get(card["type"], []))
        for platform in platforms:
            destinations.append(
                {
                    "id": _new_id("dest"),
                    "platform": platform,
                    "url": "",
                }
            )
    card["destinations"] = destinations
    return card


def _validate_month(year: int, month: int) -> None:
    if month < 1 or month > 12:
        raise HTTPException(status_code=400, detail="Month must be 1-12")
    if year < 2000 or year > 2100:
        raise HTTPException(status_code=400, detail="Invalid year")
    monthrange(year, month)


def _validate_week(year: int, month: int, week: int) -> None:
    _validate_month(year, month)
    if week < 1 or week > 4:
        raise HTTPException(status_code=400, detail="Week must be 1-4")


def _weeks_in_month(year: int, month: int) -> list[int]:
    last = monthrange(year, month)[1]
    return [week for week, start in enumerate((1, 8, 15, 22), start=1) if start <= last]


def _card_is_out(card: dict) -> bool:
    return any(str(dest.get("url") or "").strip() for dest in card.get("destinations") or [])


def _week_summary_from_cards(week: int, cards: list[dict] | None) -> dict:
    if cards is None:
        return {"week": week, "out": 0, "total": 4, "to_start": 4}
    return {
        "week": week,
        "out": sum(1 for card in cards if _card_is_out(card)),
        "total": len(cards),
        "to_start": sum(1 for card in cards if not card.get("started")),
    }


def _public_card(card: dict) -> dict:
    row = dict(card)
    row.pop("generated_posts", None)
    row.pop("yt_locales", None)
    return row


def _locale_has_title(locales) -> bool:
    if not isinstance(locales, dict):
        return False
    return any(
        isinstance(loc, dict) and str(loc.get("yt_title") or "").strip()
        for loc in locales.values()
    )


def _fill_empty_dest(card: dict, platform: str, url: str, language: str | None = None) -> None:
    if not url:
        return
    dests = list(card.get("destinations") or [])
    match = next(
        (
            dest
            for dest in dests
            if dest.get("platform") == platform
            and (not language or dest.get("language") == language)
            and not str(dest.get("url") or "").strip()
        ),
        None,
    )
    if match:
        match["url"] = url
        return
    if language:
        match = next(
            (
                dest
                for dest in dests
                if dest.get("platform") == platform
                and dest.get("language") == language
                and not str(dest.get("url") or "").strip()
            ),
            None,
        )
        if match:
            match["url"] = url
            return
    card.setdefault("destinations", dests)


def _merge_posted_urls(card: dict, package: dict) -> None:
    for row in package.get("youtube_urls") or []:
        if isinstance(row, dict):
            _fill_empty_dest(card, "youtube", str(row.get("url") or "").strip(), row.get("language"))
    for row in package.get("instagram_urls") or []:
        if isinstance(row, dict):
            _fill_empty_dest(card, "instagram", str(row.get("url") or "").strip(), row.get("language"))
    for row in package.get("facebook_urls") or []:
        if isinstance(row, dict):
            _fill_empty_dest(card, "facebook", str(row.get("url") or "").strip(), row.get("language"))


def _hydrate_cards(client_id: str, cards: list[dict]) -> list[dict]:
    out = []
    for card in cards:
        row = dict(card)
        row["destinations"] = [dict(dest) for dest in (card.get("destinations") or []) if isinstance(dest, dict)]
        topic_id = str(row.get("topic_id") or "").strip()
        if topic_id:
            package = fetch_content_video(client_id, topic_id)
            if package:
                locales = package.get("yt_locales") or {}
                row["yt_locales"] = locales
                if _locale_has_title(locales):
                    _at_least_stage(row, "yt_metadata_generated")
                _merge_posted_urls(row, package)
                has_posted = bool(
                    (package.get("youtube_urls") or [])
                    or (package.get("instagram_urls") or [])
                    or (package.get("facebook_urls") or [])
                )
                if has_posted:
                    _at_least_stage(row, "posted")
        out.append(row)
    return out


def _ensure_week(client_id: str, year: int, month: int, week: int, username: str) -> dict:
    existing = fetch_weekly_tracker(client_id, year, month, week)
    if existing:
        return existing
    doc = {
        "client_id": client_id,
        "year": year,
        "month": month,
        "week": week,
        "cards": seed_default_cards(),
        "updated_at": _now_iso(),
        "updated_by": username,
    }
    return save_weekly_tracker(doc)


def _find_card(doc: dict, card_id: str) -> dict:
    for card in doc.get("cards") or []:
        if card.get("id") == card_id:
            return card
    raise HTTPException(status_code=404, detail="Tracker card not found")


def _response(doc: dict, languages: list[str]) -> dict:
    cards = _hydrate_cards(doc["client_id"], doc.get("cards") or [])
    return {
        "tracker": {
            "id": doc.get("id") or "",
            "client_id": doc["client_id"],
            "year": doc["year"],
            "month": doc["month"],
            "week": doc["week"],
            "cards": cards,
            "languages": languages,
            "updated_at": doc.get("updated_at"),
            "updated_by": doc.get("updated_by"),
        },
        "languages": languages,
    }


FORMAT_TO_CARD_TYPE = {"Long": "long_video", "Short": "short"}


def _script_slot_empty(card: dict) -> bool:
    assets = card.get("assets") or {}
    if str(assets.get("script_text") or "").strip():
        return False
    legacy = str(assets.get("script_url") or "").strip()
    return not legacy or legacy.startswith("http")


def _at_least_stage(card: dict, stage_id: str) -> None:
    stages = STAGES.get(card.get("type") or "") or []
    current = card.get("stage") or "planned"
    if stage_id not in stages:
        return
    if current not in stages or stages.index(current) < stages.index(stage_id):
        card["stage"] = stage_id


def _fill_card_from_plan_item(card: dict, item: dict, languages: list[str]) -> dict:
    assets = dict(card.get("assets") or _empty_assets())
    assets["script_text"] = str(item.get("script") or "")
    assets["script_url"] = ""
    card["assets"] = assets
    card["content_plan_item_id"] = item.get("id")
    card["topic_id"] = item.get("topic_id")
    card["title"] = (
        str(item.get("title_hinglish") or "").strip()
        or str(item.get("working_title") or "").strip()
        or str(item.get("title_en") or "").strip()
        or str(item.get("topic_text") or "").strip()
        or card.get("title")
        or ""
    )
    card["started"] = True
    card["collapsed"] = False
    if not card.get("destinations"):
        seed_destinations_for_card(card, languages)
    _at_least_stage(card, "script_generated")
    return card


def _plan_item_for_client(client: dict, item_id: str) -> dict:
    items = ((client.get("content_suggestions") or {}).get("items") or [])
    match = next((row for row in items if isinstance(row, dict) and row.get("id") == item_id), None)
    if not match:
        raise HTTPException(status_code=404, detail="Content plan item not found")
    if not str(match.get("script") or "").strip():
        raise HTTPException(status_code=400, detail="Generate a script for this keyword first.")
    return match


@router.post("/weekly.tracker.get")
def weekly_tracker_get(
    body: schemas.WeeklyTrackerGetRequest,
    current_user: dict = Depends(get_current_user),
):
    _validate_week(body.year, body.month, body.week)
    client = _require_client(current_user["username"], body.client_id)
    languages = assigned_languages(client)
    doc = _ensure_week(body.client_id, body.year, body.month, body.week, current_user["username"])
    return _response(doc, languages)


@router.post("/weekly.tracker.month.summary")
def weekly_tracker_month_summary(
    body: schemas.WeeklyTrackerMonthSummaryRequest,
    current_user: dict = Depends(get_current_user),
):
    _validate_month(body.year, body.month)
    _require_client(current_user["username"], body.client_id)
    docs = {
        int(doc.get("week") or 0): doc
        for doc in list_weekly_trackers_for_month(body.client_id, body.year, body.month)
    }
    weeks = [
        _week_summary_from_cards(week, (docs[week].get("cards") if week in docs else None))
        for week in _weeks_in_month(body.year, body.month)
    ]
    return {"weeks": weeks}


@router.post("/weekly.tracker.poc.summary")
def weekly_tracker_poc_summary(
    body: schemas.WeeklyTrackerPocSummaryRequest,
    current_user: dict = Depends(get_current_user),
):
    _validate_month(body.year, body.month)
    week_ids = _weeks_in_month(body.year, body.month)
    clients_out = []
    totals = {week: {"week": week, "out": 0, "total": 0, "to_start": 0} for week in week_ids}
    for client in list_clients_for_user(current_user["username"], with_topics=False):
        client_id = client["id"]
        docs = {
            int(doc.get("week") or 0): doc
            for doc in list_weekly_trackers_for_month(client_id, body.year, body.month)
        }
        weeks = [
            _week_summary_from_cards(week, (docs[week].get("cards") if week in docs else None))
            for week in week_ids
        ]
        for row in weeks:
            totals[row["week"]]["out"] += row["out"]
            totals[row["week"]]["total"] += row["total"]
            totals[row["week"]]["to_start"] += row["to_start"]
        clients_out.append(
            {
                "client_id": client_id,
                "name": client.get("name") or "Untitled client",
                "weeks": weeks,
            }
        )
    clients_out.sort(key=lambda row: (row["name"] or "").lower())
    return {"weeks": [totals[week] for week in week_ids], "clients": clients_out}


@router.post("/weekly.tracker.save")
def weekly_tracker_save(
    body: schemas.WeeklyTrackerSaveRequest,
    current_user: dict = Depends(get_current_user),
):
    _validate_week(body.year, body.month, body.week)
    client = _require_client(current_user["username"], body.client_id)
    languages = assigned_languages(client)
    existing = _ensure_week(body.client_id, body.year, body.month, body.week, current_user["username"])
    cards = []
    for index, incoming in enumerate(body.cards):
        card = incoming.model_dump()
        card["sort_order"] = index if card.get("sort_order") is None else card["sort_order"]
        if card.get("started") and not card.get("destinations"):
            seed_destinations_for_card(card, languages)
        cards.append(_public_card(card))
    cards.sort(key=lambda row: int(row.get("sort_order") or 0))
    doc = {
        **existing,
        "cards": cards,
        "updated_at": _now_iso(),
        "updated_by": current_user["username"],
    }
    saved = save_weekly_tracker(doc)
    return _response(saved, languages)


@router.post("/weekly.tracker.script-links.get")
def weekly_tracker_script_links_get(
    body: schemas.WeeklyTrackerScriptLinksRequest,
    current_user: dict = Depends(get_current_user),
):
    _require_client(current_user["username"], body.client_id)
    return {"placements": list_tracker_script_placements(body.client_id)}


@router.post("/weekly.tracker.attach-script")
def weekly_tracker_attach_script(
    body: schemas.WeeklyTrackerAttachScriptRequest,
    current_user: dict = Depends(get_current_user),
):
    _validate_week(body.year, body.month, body.week)
    client = _require_client(current_user["username"], body.client_id)
    languages = assigned_languages(client)
    item = _plan_item_for_client(client, body.item_id)
    wanted_type = FORMAT_TO_CARD_TYPE.get(item.get("format") or "Long", "long_video")
    doc = _ensure_week(body.client_id, body.year, body.month, body.week, current_user["username"])
    cards = list(doc.get("cards") or [])

    if body.card_id:
        card = _find_card(doc, body.card_id)
        if card.get("type") not in {"long_video", "short"}:
            raise HTTPException(status_code=400, detail="Scripts can only attach to Long video or Short cards.")
        if card.get("type") != wanted_type:
            raise HTTPException(
                status_code=400,
                detail=f"This script is a {item.get('format') or 'Long'} video. Pick a matching tracker card.",
            )
        already_here = str(card.get("content_plan_item_id") or "") == body.item_id and not _script_slot_empty(card)
        if already_here:
            return {**_response(doc, languages), "status": "already", "card_id": card.get("id")}
        _fill_card_from_plan_item(card, item, languages)
    else:
        same_week = [
            card for card in cards
            if str(card.get("content_plan_item_id") or "") == body.item_id
        ]
        if same_week:
            return {**_response(doc, languages), "status": "already", "card_id": same_week[0].get("id")}
        empty = next(
            (
                card for card in cards
                if card.get("type") == wanted_type and _script_slot_empty(card)
            ),
            None,
        )
        if empty:
            _fill_card_from_plan_item(empty, item, languages)
        else:
            extra = default_card(wanted_type, len(cards), is_default=False)
            _fill_card_from_plan_item(extra, item, languages)
            extra["sort_order"] = len(cards)
            cards.append(extra)
            doc["cards"] = cards

    for index, card in enumerate(doc.get("cards") or []):
        card["sort_order"] = index
    doc["updated_at"] = _now_iso()
    doc["updated_by"] = current_user["username"]
    saved = save_weekly_tracker(doc)
    return {**_response(saved, languages), "status": "attached"}


def _static_platform_empty(card: dict, platform: str) -> bool:
    dests = [dest for dest in (card.get("destinations") or []) if dest.get("platform") == platform]
    if not dests:
        return True
    return all(not str(dest.get("url") or "").strip() for dest in dests)


def _write_static_permalink(card: dict, platform: str, url: str, post_id: str | None) -> None:
    dests = list(card.get("destinations") or [])
    empty = next(
        (dest for dest in dests if dest.get("platform") == platform and not str(dest.get("url") or "").strip()),
        None,
    )
    if empty:
        empty["url"] = url
    else:
        dests.append({"id": _new_id("dest"), "platform": platform, "url": url})
        card["destinations"] = dests
    ids = dict(card.get("destination_post_ids") or {})
    ids[platform] = post_id or ""
    card["destination_post_ids"] = ids
    card["started"] = True
    card["collapsed"] = False
    card["stage"] = "posted"
    if post_id:
        gids = list(card.get("generated_post_ids") or [])
        if post_id not in gids:
            gids.append(post_id)
        card["generated_post_ids"] = gids
    if not card.get("destinations"):
        card["destinations"] = dests


def week_parts_ist(when=None) -> tuple[int, int, int]:
    ist = timezone(timedelta(hours=5, minutes=30))
    now = when
    if now is None:
        now = datetime.now(ist)
    elif getattr(now, "tzinfo", None) is None:
        now = now.replace(tzinfo=ist)
    else:
        now = now.astimezone(ist)
    day = now.day
    week = 1 if day <= 7 else 2 if day <= 14 else 3 if day <= 21 else 4
    return now.year, now.month, week


def sync_social_publish_to_tracker(
    client_id: str,
    post: dict,
    *,
    published_at=None,
    year: int | None = None,
    month: int | None = None,
    week: int | None = None,
) -> dict | None:
    """Write IG/FB permalinks onto that week's static tracker card (create extra card if filled)."""
    if not client_id or not isinstance(post, dict):
        return None
    ig = str(post.get("instagram_permalink") or "").strip()
    fb = str(post.get("facebook_permalink") or "").strip()
    if not ig and not fb:
        return None
    if year and month and week:
        y, m, w = int(year), int(month), int(week)
    else:
        y, m, w = week_parts_ist(published_at)
    try:
        _validate_week(y, m, w)
    except HTTPException:
        y, m, w = week_parts_ist(published_at)
    doc = _ensure_week(client_id, y, m, w, "system")
    cards = list(doc.get("cards") or [])
    fills = []
    if ig:
        fills.append(("instagram", ig))
    if fb:
        fills.append(("facebook", fb))
    post_id = post.get("id")
    for platform, url in fills:
        target = next(
            (card for card in cards if card.get("type") == "static_post" and _static_platform_empty(card, platform)),
            None,
        )
        if not target:
            extra = default_card("static_post", len(cards), is_default=False)
            seed_destinations_for_card(extra, [])
            extra["started"] = True
            extra["collapsed"] = False
            cards.append(extra)
            target = extra
        _write_static_permalink(target, platform, url, post_id)
    for index, card in enumerate(cards):
        card["sort_order"] = index
    doc["cards"] = cards
    doc["updated_at"] = _now_iso()
    doc["updated_by"] = "system"
    return save_weekly_tracker(doc)


@router.post("/weekly.tracker.note.add")
def weekly_tracker_note_add(
    body: schemas.WeeklyTrackerNoteAddRequest,
    current_user: dict = Depends(get_current_user),
):
    _validate_week(body.year, body.month, body.week)
    _require_client(current_user["username"], body.client_id)
    if body.section not in {"feedback", "doctor"}:
        raise HTTPException(status_code=400, detail="section must be feedback or doctor")
    text = (body.text or "").strip()
    if not text and not body.attachments:
        raise HTTPException(status_code=400, detail="Enter a note or attach a file.")
    doc = fetch_weekly_tracker(body.client_id, body.year, body.month, body.week)
    if not doc:
        raise HTTPException(status_code=404, detail="Tracker week not found")
    card = _find_card(doc, body.card_id)
    note = {
        "id": _new_id("note"),
        "text": text,
        "language": body.language or "all",
        "attachments": [item.model_dump() for item in body.attachments],
        "created_by": current_user["username"],
        "created_at": _now_iso(),
    }
    key = "feedback_notes" if body.section == "feedback" else "doctor_notes"
    card.setdefault(key, []).append(note)
    if body.section == "doctor" and card.get("type") in {"long_video", "short"}:
        stages = STAGES[card["type"]]
        current = card.get("stage") or "planned"
        shared_at = stages.index("shared_with_doctor")
        if stages.index(current) < shared_at:
            card["stage"] = "shared_with_doctor"
    doc["updated_at"] = _now_iso()
    doc["updated_by"] = current_user["username"]
    saved = save_weekly_tracker(doc)
    client = fetch_client_bundle(body.client_id, current_user["username"], with_videos=False) or {}
    return _response(saved, assigned_languages(client))


@router.post("/weekly.tracker.file.upload")
async def weekly_tracker_file_upload(
    client_id: str = Form(...),
    year: int = Form(...),
    month: int = Form(...),
    week: int = Form(...),
    card_id: str = Form(...),
    target: str = Form("pending"),
    language: str = Form("all"),
    text: str = Form(""),
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    _validate_week(year, month, week)
    _require_client(current_user["username"], client_id)
    if target not in {"pending", "doctor_files", "feedback_note", "doctor_note", "video_url"}:
        raise HTTPException(status_code=400, detail="Invalid upload target")

    content_type = file.content_type or "application/octet-stream"
    mime = content_type.split(";")[0].strip().lower()
    ext = mimetypes.guess_extension(mime) or Path(file.filename or "").suffix or ".bin"
    if ext.lower() in {".jpe"}:
        ext = ".jpg"

    if target == "video_url":
        file_ext = Path(file.filename or "").suffix.lower()
        if mime not in VIDEO_MIME_TYPES and file_ext not in VIDEO_EXTS:
            raise HTTPException(status_code=400, detail="File must be an mp4, mov, or webm video.")
        if file_ext in VIDEO_EXTS:
            ext = file_ext
        else:
            ext = { "video/mp4": ".mp4", "video/quicktime": ".mov", "video/webm": ".webm" }.get(mime, ".mp4")
        content_type = mime if mime in VIDEO_MIME_TYPES else {
            ".mp4": "video/mp4",
            ".mov": "video/quicktime",
            ".webm": "video/webm",
        }.get(ext, "video/mp4")

    filename = f"{uuid.uuid4().hex}{ext}"
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")

    gcs_folder = "uploaded_videos" if target == "video_url" else "weekly_tracker"
    try:
        public_url = upload_bytes(gcs_folder, filename, content, content_type=content_type)
    except Exception as exc:
        print(f"GCS upload failed: {exc}. Falling back to local disk.", flush=True)
        if target == "video_url":
            UPLOADED_VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
            path = UPLOADED_VIDEOS_DIR / filename
            path.write_bytes(content)
            base_url = settings.BASE_URL.rstrip("/")
            public_url = f"{base_url}/weekly.tracker.asset/uploaded_videos/{filename}"
        else:
            TRACKER_ASSETS_DIR.mkdir(parents=True, exist_ok=True)
            path = TRACKER_ASSETS_DIR / filename
            path.write_bytes(content)
            base_url = settings.BASE_URL.rstrip("/")
            public_url = f"{base_url}/weekly.tracker.asset/{filename}"

    attachment = {
        "id": _new_id("att"),
        "name": file.filename or filename,
        "url": public_url,
        "content_type": content_type,
    }

    if target == "pending":
        return {"file": attachment}

    doc = fetch_weekly_tracker(client_id, year, month, week)
    if not doc:
        raise HTTPException(status_code=404, detail="Tracker week not found")
    card = _find_card(doc, card_id)
    if target == "video_url":
        assets = dict(card.get("assets") or _empty_assets())
        assets["video_url"] = public_url
        card["assets"] = assets
        if card.get("type") in {"long_video", "short"}:
            _at_least_stage(card, "video_edited")
    elif target == "doctor_files":
        card.setdefault("doctor_files", []).append(
            {
                "id": _new_id("file"),
                "name": attachment["name"],
                "url": attachment["url"],
                "created_by": current_user["username"],
                "created_at": _now_iso(),
            }
        )
        if card.get("type") in {"long_video", "short"}:
            stages = STAGES[card["type"]]
            current = card.get("stage") or "planned"
            shared_at = stages.index("shared_with_doctor")
            if stages.index(current) < shared_at:
                card["stage"] = "shared_with_doctor"
    else:
        note = {
            "id": _new_id("note"),
            "text": (text or "").strip(),
            "language": language or "all",
            "attachments": [attachment],
            "created_by": current_user["username"],
            "created_at": _now_iso(),
        }
        key = "feedback_notes" if target == "feedback_note" else "doctor_notes"
        card.setdefault(key, []).append(note)
    doc["updated_at"] = _now_iso()
    doc["updated_by"] = current_user["username"]
    saved = save_weekly_tracker(doc)
    client = fetch_client_bundle(client_id, current_user["username"], with_videos=False) or {}
    return {**_response(saved, assigned_languages(client)), "file": attachment}


@router.get("/weekly.tracker.asset/{file_path:path}")
def weekly_tracker_asset(file_path: str):
    if ".." in file_path or file_path.startswith("/"):
        raise HTTPException(status_code=404, detail="Asset not found")
    if file_path.startswith("uploaded_videos/"):
        path = TRACKER_ASSETS_DIR.parent / file_path
    else:
        path = TRACKER_ASSETS_DIR / file_path
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Asset not found")
    media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return FileResponse(path, media_type=media_type)
