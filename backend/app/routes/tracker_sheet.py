from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app import schemas
from app.auth import get_current_user
from app.database import (
    list_clients_for_user,
    list_sheet_comments_for_month,
    save_sheet_comment,
)
from app.routes.custom_tracker import _ensure_week, _validate_month, _weeks_in_month
from app.routes.tracker import _ensure_week as ensure_weekly_week, _require_client, _now_iso, _weeks_in_month as weekly_weeks_in_month
from app.services.tracker_sheet import comments_map, flatten_weekly_rows

router = APIRouter(tags=["tracker-sheet"])


@router.post("/tracker.sheet.clients")
def tracker_sheet_clients(current_user: dict = Depends(get_current_user)):
    clients = list_clients_for_user(current_user["username"], with_topics=False)
    rows = sorted(
        [
            {
                "client_id": client["id"],
                "name": client.get("name") or "Untitled client",
            }
            for client in clients
        ],
        key=lambda row: (row["name"] or "").lower(),
    )
    return {"clients": rows}


@router.post("/tracker.sheet.weekly")
def tracker_sheet_weekly(
    body: schemas.TrackerSheetWeeklyRequest,
    current_user: dict = Depends(get_current_user),
):
    _validate_month(body.year, body.month)
    _require_client(current_user["username"], body.client_id)
    docs = {}
    for week in weekly_weeks_in_month(body.year, body.month):
        docs[week] = ensure_weekly_week(
            body.client_id,
            body.year,
            body.month,
            week,
            current_user["username"],
        )
    rows = flatten_weekly_rows(docs, body.year, body.month)
    comments = list_sheet_comments_for_month(body.client_id, body.year, body.month, tracker="weekly")
    return {
        "year": body.year,
        "month": body.month,
        "rows": rows,
        "comments": comments_map(comments),
    }


@router.post("/tracker.sheet.custom")
def tracker_sheet_custom(
    body: schemas.TrackerSheetCustomRequest,
    current_user: dict = Depends(get_current_user),
):
    _validate_month(body.year, body.month)
    _require_client(current_user["username"], body.client_id)
    weeks = []
    for week in _weeks_in_month(body.year, body.month):
        doc = _ensure_week(body.client_id, body.year, body.month, week, current_user["username"])
        weeks.append(
            {
                "week": week,
                "categories": doc.get("categories") or [],
            }
        )
    return {
        "year": body.year,
        "month": body.month,
        "weeks": weeks,
    }


@router.post("/tracker.sheet.comment.save")
def tracker_sheet_comment_save(
    body: schemas.TrackerSheetCommentSaveRequest,
    current_user: dict = Depends(get_current_user),
):
    _validate_month(body.year, body.month)
    if body.week < 1 or body.week > 4:
        raise HTTPException(status_code=400, detail="Week must be 1-4")
    _require_client(current_user["username"], body.client_id)
    row_key = str(body.row_key or "").strip()
    if not row_key:
        raise HTTPException(status_code=400, detail="row_key is required")
    saved = save_sheet_comment(
        {
            "client_id": body.client_id,
            "year": body.year,
            "month": body.month,
            "week": body.week,
            "tracker": "weekly",
            "row_key": row_key,
            "comment": str(body.comment or ""),
            "updated_at": _now_iso(),
            "updated_by": current_user["username"],
        }
    )
    return {"comment": saved}
