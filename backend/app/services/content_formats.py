"""Excel-derived video themes (Long/Short). Theme labels only — no scripts."""

from __future__ import annotations

from typing import Any

VIDEO_TYPES: list[dict[str, str]] = [
    {
        "name": "Explainer",
        "format": "Long",
        "use_when": "A topic needs context but should not feel like a lecture.",
    },
    {
        "name": "How-to",
        "format": "Long",
        "use_when": "Viewers want a method, process, or step-by-step they can apply.",
    },
    {
        "name": "Report decode",
        "format": "Long",
        "use_when": "A metric, report, or result creates confusion and search demand.",
    },
    {
        "name": "Lifestyle",
        "format": "Long",
        "use_when": "Viewers need practical daily habits or routines.",
    },
    {
        "name": "Comparison",
        "format": "Long",
        "use_when": "Two options feel similar and viewers are confused.",
    },
    {
        "name": "Story-led",
        "format": "Long",
        "use_when": "A relatable mini-scenario can teach the point faster.",
    },
    {
        "name": "Myth buster",
        "format": "Short",
        "use_when": "One sticky belief needs correction.",
    },
    {
        "name": "FAQ",
        "format": "Short",
        "use_when": "Viewers repeatedly ask one question.",
    },
    {
        "name": "When to act",
        "format": "Short",
        "use_when": "A signal needs a decision, not more theory.",
    },
    {
        "name": "Common mistake",
        "format": "Short",
        "use_when": "A common behaviour can worsen results.",
    },
    {
        "name": "Quick term",
        "format": "Short",
        "use_when": "One jargon word or report value is confusing.",
    },
    {
        "name": "Single tip",
        "format": "Short",
        "use_when": "One action can be shown simply.",
    },
    {
        "name": "Creator reacts",
        "format": "Short",
        "use_when": "Trending noise needs a creator take.",
    },
    {
        "name": "Seasonal alert",
        "format": "Short",
        "use_when": "Timely seasonal searches rise.",
    },
]

# Report decode also works as Short in Excel; keep Long primary above.
# Alias for map validation:
VIDEO_TYPE_NAMES: set[str] = {v["name"] for v in VIDEO_TYPES}


def types_for_format(fmt: str) -> list[dict[str, str]]:
    target = "Short" if fmt == "Short" else "Long"
    return [v for v in VIDEO_TYPES if v["format"] == target]


def catalog_for_prompt() -> list[dict[str, str]]:
    return [
        {"name": v["name"], "format": v["format"], "use_when": v["use_when"]}
        for v in VIDEO_TYPES
    ]


def normalize_video_type(name: str | None, fmt: str) -> str:
    """Pick a valid catalog name for the format; fall back to first matching type."""
    allowed = types_for_format(fmt)
    if name:
        for v in allowed:
            if v["name"].lower() == name.strip().lower():
                return v["name"]
        # Allow Long "Story-led lesson" mapped onto short alias
        for v in allowed:
            if name.strip().lower() in v["name"].lower() or v["name"].lower() in name.strip().lower():
                return v["name"]
    return allowed[0]["name"] if allowed else "FAQ"


def pick_video_type(fmt: str, recent_types: list[str]) -> str:
    """Fallback type picker — prefer themes not used in recent_types."""
    allowed = types_for_format(fmt)
    recent_lower = [t.lower() for t in recent_types if t]
    recent_set = set(recent_lower)
    fresh = [v for v in allowed if v["name"].lower() not in recent_set]
    pool = fresh or allowed
    return pool[0]["name"]


RECENT_TYPE_WINDOW = 20


def coverage_summary(coverage: dict[str, Any] | None) -> dict[str, int]:
    videos = (coverage or {}).get("videos") or {}
    mapped = 0
    out_of = 0
    for row in videos.values():
        if not isinstance(row, dict):
            continue
        if row.get("out_of_keyword"):
            out_of += 1
        elif row.get("topic_id"):
            mapped += 1
    return {
        "total": len(videos),
        "mapped_to_keyword": mapped,
        "out_of_keyword": out_of,
    }
