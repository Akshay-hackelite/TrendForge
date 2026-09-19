from __future__ import annotations

import uuid
from calendar import monthrange
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status

from app import schemas
from app.auth import get_current_user
from app.database import (
    fetch_client_bundle,
    fetch_custom_tracker,
    list_custom_trackers_for_month,
    save_custom_tracker,
)

router = APIRouter(tags=["custom-tracker"])

DEFAULT_CATEGORIES = (
    "Videos",
    "Socials",
    "Website",
    "Digital Marketing",
    "Bots",
    "Communication",
)
STATUSES = {"todo", "in_progress", "done"}
PRIORITIES = {"p0", "p1", "p2"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id(prefix: str = "id") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def _require_client(username: str, client_id: str) -> dict:
    client = fetch_client_bundle(client_id, username, with_videos=False)
    if not client:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")
    return client


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


def seed_categories() -> list[dict]:
    return [
        {
            "id": _new_id("cat"),
            "name": name,
            "is_default": True,
            "collapsed": False,
            "issues": [],
        }
        for name in DEFAULT_CATEGORIES
    ]


def _board_summary(week: int, categories: list[dict] | None) -> dict:
    if not categories:
        return {"week": week, "issues": 0, "done": 0, "open": 0}
    issues = 0
    done = 0
    for category in categories:
        for issue in category.get("issues") or []:
            issues += 1
            if issue.get("status") == "done":
                done += 1
    return {"week": week, "issues": issues, "done": done, "open": issues - done}


def _clean_due_date(value: object) -> str:
    raw = str(value or "").strip()
    if len(raw) >= 10 and raw[4] == "-" and raw[7] == "-":
        return raw[:10]
    return ""


def _clean_note(row: dict) -> dict:
    text = str(row.get("text") or "").strip()
    if not text:
        return {}
    return {
        "id": row.get("id") or _new_id("note"),
        "text": text,
        "created_by": str(row.get("created_by") or "").strip(),
        "created_at": str(row.get("created_at") or "").strip() or _now_iso(),
    }


def _clean_subtask(row: dict) -> dict:
    return {
        "id": row.get("id") or _new_id("sub"),
        "title": str(row.get("title") or "").strip(),
        "done": bool(row.get("done")),
        "due_date": _clean_due_date(row.get("due_date")),
        "comment": str(row.get("comment") or "").strip(),
    }


def _clean_task(row: dict) -> dict:
    return {
        "id": row.get("id") or _new_id("tsk"),
        "title": str(row.get("title") or "").strip(),
        "done": bool(row.get("done")),
        "due_date": _clean_due_date(row.get("due_date")),
        "comment": str(row.get("comment") or "").strip(),
        "subtasks": [_clean_subtask(sub) for sub in (row.get("subtasks") or []) if isinstance(sub, dict)],
    }


def _clean_issue(row: dict) -> dict:
    status_value = str(row.get("status") or "todo").strip().lower()
    priority = str(row.get("priority") or "p1").strip().lower()
    notes = [_clean_note(note) for note in (row.get("notes") or []) if isinstance(note, dict)]
    return {
        "id": row.get("id") or _new_id("iss"),
        "display_id": str(row.get("display_id") or "").strip(),
        "title": str(row.get("title") or "").strip(),
        "status": status_value if status_value in STATUSES else "todo",
        "priority": priority if priority in PRIORITIES else "p1",
        "collapsed": bool(row.get("collapsed")),
        "comment": str(row.get("comment") or "").strip(),
        "tasks": [_clean_task(task) for task in (row.get("tasks") or []) if isinstance(task, dict)],
        "notes": [note for note in notes if note],
    }


def _clean_category(row: dict) -> dict:
    name = str(row.get("name") or "").strip() or "Untitled"
    return {
        "id": row.get("id") or _new_id("cat"),
        "name": name,
        "is_default": bool(row.get("is_default")),
        "collapsed": bool(row.get("collapsed")),
        "issues": [_clean_issue(issue) for issue in (row.get("issues") or []) if isinstance(issue, dict)],
    }


def _ensure_week(client_id: str, year: int, month: int, week: int, username: str) -> dict:
    existing = fetch_custom_tracker(client_id, year, month, week)
    if existing:
        return existing
    doc = {
        "client_id": client_id,
        "year": year,
        "month": month,
        "week": week,
        "categories": seed_categories(),
        "issue_seq": 0,
        "updated_at": _now_iso(),
        "updated_by": username,
    }
    return save_custom_tracker(doc)


def _response(doc: dict) -> dict:
    return {
        "tracker": {
            "id": doc.get("id"),
            "client_id": doc["client_id"],
            "year": doc["year"],
            "month": doc["month"],
            "week": doc["week"],
            "categories": doc.get("categories") or [],
            "issue_seq": int(doc.get("issue_seq") or 0),
            "updated_at": doc.get("updated_at"),
            "updated_by": doc.get("updated_by"),
        }
    }


@router.post("/custom.tracker.get", response_model=schemas.CustomTrackerResponse)
def custom_tracker_get(
    body: schemas.CustomTrackerGetRequest,
    current_user: dict = Depends(get_current_user),
):
    _validate_week(body.year, body.month, body.week)
    _require_client(current_user["username"], body.client_id)
    doc = _ensure_week(body.client_id, body.year, body.month, body.week, current_user["username"])
    return _response(doc)


@router.post("/custom.tracker.month.summary", response_model=schemas.CustomTrackerMonthSummaryResponse)
def custom_tracker_month_summary(
    body: schemas.WeeklyTrackerMonthSummaryRequest,
    current_user: dict = Depends(get_current_user),
):
    _validate_month(body.year, body.month)
    _require_client(current_user["username"], body.client_id)
    docs = {
        int(doc.get("week") or 0): doc
        for doc in list_custom_trackers_for_month(body.client_id, body.year, body.month)
    }
    weeks = [
        _board_summary(week, docs[week].get("categories") if week in docs else None)
        for week in _weeks_in_month(body.year, body.month)
    ]
    return {"weeks": weeks}


@router.post("/custom.tracker.save", response_model=schemas.CustomTrackerResponse)
def custom_tracker_save(
    body: schemas.CustomTrackerSaveRequest,
    current_user: dict = Depends(get_current_user),
):
    _validate_week(body.year, body.month, body.week)
    _require_client(current_user["username"], body.client_id)
    existing = _ensure_week(body.client_id, body.year, body.month, body.week, current_user["username"])
    categories = [_clean_category(row.model_dump()) for row in body.categories]
    issue_seq = max(0, int(body.issue_seq or 0))
    doc = {
        **existing,
        "categories": categories,
        "issue_seq": issue_seq,
        "updated_at": _now_iso(),
        "updated_by": current_user["username"],
    }
    saved = save_custom_tracker(doc)
    return _response(saved)
