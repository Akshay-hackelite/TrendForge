from __future__ import annotations

from calendar import monthrange

TYPE_LABELS = {
    "long_video": "Long video",
    "short": "Short",
    "static_post": "Static post",
    "blog": "Blog",
}

STAGE_LABELS = {
    "planned": "Planned",
    "script_generated": "Script generated",
    "yt_metadata_generated": "YT metadata generated",
    "audio_generated": "Audio generated",
    "video_edited": "Video edited",
    "shared_with_doctor": "Shared with client",
    "posted": "Posted",
    "published": "Published",
}


def weeks_in_month(year: int, month: int) -> list[int]:
    last = monthrange(year, month)[1]
    return [week for week, start in enumerate((1, 8, 15, 22), start=1) if start <= last]


def card_links(card: dict) -> list[str]:
    urls = []
    for dest in card.get("destinations") or []:
        if not isinstance(dest, dict):
            continue
        url = str(dest.get("url") or "").strip()
        if url:
            urls.append(url)
    return urls


def flatten_weekly_rows(docs_by_week: dict[int, dict], year: int, month: int) -> list[dict]:
    rows = []
    for week in weeks_in_month(year, month):
        doc = docs_by_week.get(week) or {}
        cards = sorted(
            [card for card in (doc.get("cards") or []) if isinstance(card, dict)],
            key=lambda row: int(row.get("sort_order") or 0),
        )
        for card in cards:
            card_type = str(card.get("type") or "").strip()
            stage = str(card.get("stage") or "planned").strip()
            rows.append(
                {
                    "week": week,
                    "card_id": card.get("id") or "",
                    "row_key": f"card:{card.get('id') or ''}",
                    "content_type": card_type,
                    "content_type_label": TYPE_LABELS.get(card_type, card_type or "Unknown"),
                    "stage": stage,
                    "stage_label": STAGE_LABELS.get(stage, stage.replace("_", " ").title()),
                    "links": card_links(card),
                }
            )
    return rows


def comments_map(comments: list[dict]) -> dict[str, str]:
    out: dict[str, str] = {}
    for row in comments:
        if not isinstance(row, dict):
            continue
        key = str(row.get("row_key") or "").strip()
        if not key:
            continue
        out[key] = str(row.get("comment") or "")
    return out
