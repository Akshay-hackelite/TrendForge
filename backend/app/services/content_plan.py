"""Content-plan selection: coverage cache, weighted topic pick, Long/Short alternate."""

from __future__ import annotations

import random
import statistics
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from app.services.content_formats import (
    coverage_summary,
    normalize_video_type,
    pick_video_type,
)
from app.services.openai_content_plan import (
    enrich_suggestions,
    generate_scripts_batch,
    map_videos_batch,
    refine_single_script,
)
from app.services.topics import normalize_topics, recommendation_score_for

SCORE_THRESHOLD = 50.0
REUSE_DAYS = 365
MAP_BATCH_SIZE = 40
# Primary topics: score >= threshold (matches Settings recommendations)


def _new_id() -> str:
    return str(uuid.uuid4())


def collect_client_videos(client: dict, *, public_only: bool = True) -> list[dict]:
    """Collect videos newest-first. Default: public only (hide unpublished from planning)."""
    videos: list[dict] = []
    for channel in client.get("channels") or []:
        for raw in channel.get("videos") or []:
            if not isinstance(raw, dict) or not raw.get("id"):
                continue
            privacy = (raw.get("privacy_status") or "public").lower()
            if public_only and privacy != "public":
                continue
            videos.append(
                {
                    "id": raw["id"],
                    "title": raw.get("title") or "",
                    "published_at": raw.get("published_at") or "",
                    "view_count": int(raw.get("view_count") or 0),
                    "is_short": bool(raw.get("is_short")),
                    "privacy_status": privacy,
                }
            )
    videos.sort(key=lambda v: v.get("published_at") or "", reverse=True)
    return videos


def _parse_published(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _median_views(videos: list[dict]) -> float:
    counts = [int(v.get("view_count") or 0) for v in videos]
    if not counts:
        return 0.0
    return float(statistics.median(counts))


def scored_topics(client: dict) -> list[dict]:
    topics = normalize_topics(client.get("topics"))
    out: list[dict] = []
    for topic in topics:
        row = dict(topic)
        if row.get("recommendation_score") is None:
            row.update(recommendation_score_for(row))
        else:
            try:
                row["recommendation_score"] = float(row["recommendation_score"])
            except (TypeError, ValueError):
                row.update(recommendation_score_for(row))
        out.append(row)
    return out


def _coverage_stale(client: dict, videos: list[dict], topics: list[dict]) -> bool:
    coverage = client.get("content_topic_coverage") or {}
    cached = coverage.get("videos") or {}
    if not cached:
        return True
    video_ids = {v["id"] for v in videos}
    cached_ids = set(cached.keys())
    if video_ids != cached_ids:
        return True
    topic_ids = {t["id"] for t in topics}
    fingerprint = coverage.get("topic_ids") or []
    if set(fingerprint) != topic_ids:
        return True
    return False


def ensure_video_topic_coverage(
    client: dict,
    *,
    force: bool = False,
) -> dict[str, Any]:
    """AI-map videos to keywords; cache on client with Long/Short keyword analysis."""
    topics = scored_topics(client)
    videos = collect_client_videos(client)
    if not topics:
        raise ValueError("No topics/keywords on this client. Refresh topics in Settings first.")
    if not videos:
        coverage = {
            "mapped_at": datetime.now(timezone.utc).isoformat(),
            "topic_ids": [t["id"] for t in topics],
            "videos": {},
            "keyword_analysis": build_keyword_analysis(topics, [], {}),
        }
        client["content_topic_coverage"] = coverage
        return coverage

    if not force and not _coverage_stale(client, videos, topics):
        coverage = client["content_topic_coverage"]
        # Backfill analysis if older cache lacks it
        if not coverage.get("keyword_analysis"):
            coverage["keyword_analysis"] = build_keyword_analysis(
                topics, videos, coverage
            )
            client["content_topic_coverage"] = coverage
        return coverage

    mapped: dict[str, dict] = {}
    by_id = {v["id"]: v for v in videos}
    for i in range(0, len(videos), MAP_BATCH_SIZE):
        batch = videos[i : i + MAP_BATCH_SIZE]
        rows = map_videos_batch(
            topics=topics,
            videos=batch,
            specialty=client.get("specialty"),
            client_id=client.get("id"),
        )
        for row in rows:
            vid = row["video_id"]
            src = by_id.get(vid) or {}
            is_short = bool(src.get("is_short"))
            mapped[vid] = {
                "topic_id": row.get("topic_id"),
                "out_of_keyword": bool(row.get("out_of_keyword")),
                "video_type": row.get("video_type"),
                "format": "Short" if is_short else "Long",
                "is_short": is_short,
                "title": src.get("title") or "",
                "published_at": src.get("published_at") or "",
                "view_count": int(src.get("view_count") or 0),
            }
        for v in batch:
            if v["id"] not in mapped:
                mapped[v["id"]] = {
                    "topic_id": None,
                    "out_of_keyword": True,
                    "video_type": None,
                    "format": "Short" if v.get("is_short") else "Long",
                    "is_short": bool(v.get("is_short")),
                    "title": v.get("title") or "",
                    "published_at": v.get("published_at") or "",
                    "view_count": int(v.get("view_count") or 0),
                }

    coverage: dict[str, Any] = {
        "mapped_at": datetime.now(timezone.utc).isoformat(),
        "topic_ids": [t["id"] for t in topics],
        "videos": mapped,
    }
    coverage["keyword_analysis"] = build_keyword_analysis(topics, videos, coverage)
    client["content_topic_coverage"] = coverage
    return coverage


def build_keyword_analysis(
    topics: list[dict],
    videos: list[dict],
    coverage: dict,
) -> list[dict]:
    """Per-keyword Long/Short coverage + linked videos (persisted after map)."""
    by_id = {v["id"]: v for v in videos}
    long_by_topic: dict[str, list[dict]] = {}
    short_by_topic: dict[str, list[dict]] = {}

    for vid, row in (coverage.get("videos") or {}).items():
        if not isinstance(row, dict) or row.get("out_of_keyword"):
            continue
        tid = row.get("topic_id")
        if not tid:
            continue
        video = by_id.get(vid) or {}
        is_short = bool(row.get("is_short") if row.get("is_short") is not None else video.get("is_short"))
        entry = {
            "video_id": vid,
            "title": row.get("title") or video.get("title") or "",
            "published_at": row.get("published_at") or video.get("published_at") or "",
            "view_count": int(row.get("view_count") if row.get("view_count") is not None else video.get("view_count") or 0),
            "video_type": row.get("video_type"),
            "format": "Short" if is_short else "Long",
        }
        if is_short:
            short_by_topic.setdefault(tid, []).append(entry)
        else:
            long_by_topic.setdefault(tid, []).append(entry)

    def _sort_vids(rows: list[dict]) -> list[dict]:
        return sorted(rows, key=lambda r: r.get("published_at") or "", reverse=True)

    analysis: list[dict] = []
    for topic in topics:
        tid = topic["id"]
        longs = _sort_vids(long_by_topic.get(tid) or [])
        shorts = _sort_vids(short_by_topic.get(tid) or [])
        covered_long = len(longs) > 0
        covered_short = len(shorts) > 0
        analysis.append(
            {
                "topic_id": tid,
                "topic_text": topic.get("text") or "",
                "recommendation_score": float(topic.get("recommendation_score") or 0),
                "weight": topic.get("weight") or "medium",
                "covered_long": covered_long,
                "covered_short": covered_short,
                "pending_long": not covered_long,
                "pending_short": not covered_short,
                "long_videos": longs,
                "short_videos": shorts,
            }
        )
    # Pending first, then by score
    analysis.sort(
        key=lambda r: (
            0 if (r["pending_long"] or r["pending_short"]) else 1,
            -(r.get("recommendation_score") or 0),
            (r.get("topic_text") or "").lower(),
        )
    )
    return analysis


def _covered_format_meta(
    videos: list[dict],
    coverage: dict,
) -> dict[str, dict[str, dict]]:
    """topic_id → {Long|Short → newest covering video}."""
    by_id = {v["id"]: v for v in videos}
    best: dict[str, dict[str, dict]] = {}
    for vid, row in (coverage.get("videos") or {}).items():
        if not isinstance(row, dict) or row.get("out_of_keyword"):
            continue
        tid = row.get("topic_id")
        if not tid:
            continue
        video = by_id.get(vid)
        if not video:
            continue
        fmt = "Short" if (row.get("is_short") if row.get("is_short") is not None else video.get("is_short")) else "Long"
        bucket = best.setdefault(tid, {})
        prev = bucket.get(fmt)
        if not prev or (video.get("published_at") or "") > (prev.get("published_at") or ""):
            bucket[fmt] = video
    return best


def _covered_topic_meta(
    videos: list[dict],
    coverage: dict,
) -> dict[str, dict]:
    """topic_id → best (newest) covering video meta for reuse checks (any format)."""
    by_format = _covered_format_meta(videos, coverage)
    best: dict[str, dict] = {}
    for tid, formats in by_format.items():
        candidates = list(formats.values())
        if not candidates:
            continue
        best[tid] = max(candidates, key=lambda v: v.get("published_at") or "")
    return best


def _is_reusable(video: dict, median_views: float, now: datetime) -> bool:
    published = _parse_published(video.get("published_at"))
    if not published:
        return False
    age_ok = published <= now - timedelta(days=REUSE_DAYS)
    views_ok = int(video.get("view_count") or 0) >= median_views
    return age_ok and views_ok


def eligible_topics(
    topics: list[dict],
    covered: dict[str, dict],
    median_views: float,
) -> list[dict]:
    """Legacy any-format eligibility (kept for callers). Prefer eligible_topics_for_format."""
    now = datetime.now(timezone.utc)
    primary = [
        t
        for t in topics
        if float(t.get("recommendation_score") or 0) >= SCORE_THRESHOLD
    ]
    if not primary:
        raise ValueError(
            f"No topics with recommendation_score >= {SCORE_THRESHOLD}. "
            "Analyze trends and save recommendations in Settings first."
        )

    fresh: list[dict] = []
    reusable: list[dict] = []
    for topic in primary:
        tid = topic["id"]
        if tid not in covered:
            fresh.append(topic)
            continue
        if _is_reusable(covered[tid], median_views, now):
            reusable.append(topic)

    pool = fresh if fresh else (reusable if reusable else primary)
    return pool


def eligible_topics_for_format(
    topics: list[dict],
    format_meta: dict[str, dict[str, dict]],
    median_views: float,
    fmt: str,
) -> list[dict]:
    """Topics still needing this Long/Short format (or reusable old high-view cover)."""
    now = datetime.now(timezone.utc)
    primary = [
        t
        for t in topics
        if float(t.get("recommendation_score") or 0) >= SCORE_THRESHOLD
    ]
    if not primary:
        raise ValueError(
            f"No topics with recommendation_score >= {SCORE_THRESHOLD}. "
            "Analyze trends and save recommendations in Settings first."
        )

    pending: list[dict] = []
    reusable: list[dict] = []
    for topic in primary:
        tid = topic["id"]
        video = (format_meta.get(tid) or {}).get(fmt)
        if not video:
            # Covered in the other format (or not at all) → this format is still pending
            pending.append(topic)
            continue
        if _is_reusable(video, median_views, now):
            reusable.append(topic)

    return pending if pending else (reusable if reusable else primary)


def pick_topics_for_formats(
    topics: list[dict],
    formats: list[str],
    format_meta: dict[str, dict[str, dict]],
    median_views: float,
) -> list[dict]:
    """One topic per slot; prefer keywords still pending that slot's Long/Short."""
    picked: list[dict] = []
    used: set[str] = set()
    for fmt in formats:
        pool = eligible_topics_for_format(topics, format_meta, median_views, fmt)
        pool = [t for t in pool if t["id"] not in used]
        if not pool:
            pool = [
                t
                for t in topics
                if float(t.get("recommendation_score") or 0) >= SCORE_THRESHOLD
                and t["id"] not in used
            ]
        if not pool:
            break
        choice = weighted_sample(pool, 1)[0]
        picked.append(choice)
        used.add(choice["id"])
    return picked


def weighted_sample(topics: list[dict], count: int) -> list[dict]:
    count = max(1, min(10, int(count)))
    if len(topics) <= count:
        return list(topics)

    pool = list(topics)
    picked: list[dict] = []
    for _ in range(count):
        if not pool:
            break
        weights = [max(float(t.get("recommendation_score") or 1), 0.1) for t in pool]
        choice = random.choices(pool, weights=weights, k=1)[0]
        picked.append(choice)
        pool = [t for t in pool if t["id"] != choice["id"]]
    return picked


def next_formats(videos: list[dict], count: int) -> list[str]:
    """Alternate Long/Short starting after the most recent video's format."""
    last_short = False
    if videos:
        last_short = bool(videos[0].get("is_short"))
    # Next should be opposite of last
    start_short = not last_short if videos else False
    formats: list[str] = []
    for i in range(count):
        is_short = start_short if i % 2 == 0 else not start_short
        formats.append("Short" if is_short else "Long")
    return formats


def recent_video_types(coverage: dict, videos: list[dict], limit: int = 20) -> list[str]:
    """Themes from the last N published videos (AI-mapped), newest first."""
    types: list[str] = []
    for v in videos[:limit]:
        row = (coverage.get("videos") or {}).get(v["id"]) or {}
        vt = row.get("video_type")
        if vt:
            types.append(vt)
    return types


def recent_library_topics(
    coverage: dict,
    videos: list[dict],
    topics_by_id: dict[str, dict],
    limit: int = 20,
) -> list[dict]:
    """Last N public library videos with mapped keyword (from DB coverage) for AI context."""
    rows: list[dict] = []
    for v in videos[:limit]:
        mapped = (coverage.get("videos") or {}).get(v["id"]) or {}
        tid = mapped.get("topic_id")
        topic = topics_by_id.get(tid) if tid else None
        rows.append(
            {
                "video_id": v["id"],
                "title": v.get("title") or "",
                "published_at": v.get("published_at") or "",
                "is_short": bool(v.get("is_short")),
                "view_count": int(v.get("view_count") or 0),
                "topic_id": tid,
                "topic_text": (topic or {}).get("text") if topic else None,
                "out_of_keyword": bool(mapped.get("out_of_keyword")) or not tid,
                "video_type": mapped.get("video_type"),
            }
        )
    return rows


def build_slots(
    picked: list[dict],
    formats: list[str],
    *,
    keyword_analysis_by_id: dict[str, dict] | None = None,
) -> list[dict]:
    """Slots for generate: lean fields for AI; score kept for UI persistence only."""
    analysis = keyword_analysis_by_id or {}
    slots: list[dict] = []
    for topic, fmt in zip(picked, formats):
        scores = recommendation_score_for(topic)
        row = analysis.get(topic["id"]) or {}
        pending_long = bool(row.get("pending_long", True))
        pending_short = bool(row.get("pending_short", True))
        score = float(
            topic.get("recommendation_score")
            if topic.get("recommendation_score") is not None
            else scores["recommendation_score"]
        )
        slots.append(
            {
                "topic_id": topic["id"],
                "topic_text": topic.get("text") or "",
                "format": fmt,
                "pending_long": pending_long,
                "pending_short": pending_short,
                # Kept for DB/UI — stripped before OpenAI
                "recommendation_score": score,
            }
        )
    return slots


def slots_from_previous_items(
    previous_items: list[dict],
    topics_by_id: dict[str, dict],
    keyword_analysis_by_id: dict[str, dict] | None = None,
) -> list[dict]:
    """Rebuild refine slots from the last plan — do not re-pick keywords."""
    analysis = keyword_analysis_by_id or {}
    slots: list[dict] = []
    for item in previous_items:
        if not isinstance(item, dict):
            continue
        tid = item.get("topic_id")
        if not tid:
            continue
        topic = topics_by_id.get(tid) or {}
        fmt = item.get("format") if item.get("format") in ("Long", "Short") else "Long"
        row = analysis.get(tid) or {}
        pending_long = bool(row.get("pending_long", True))
        pending_short = bool(row.get("pending_short", True))
        score = float(
            topic.get("recommendation_score")
            if topic.get("recommendation_score") is not None
            else item.get("recommendation_score") or 0
        )
        slots.append(
            {
                "topic_id": tid,
                "topic_text": item.get("topic_text") or topic.get("text") or "",
                "format": fmt,
                "pending_long": pending_long,
                "pending_short": pending_short,
                "recommendation_score": score,
                "previous_video_type": item.get("video_type"),
                "previous_title_en": item.get("title_en") or item.get("working_title"),
                "previous_title_hinglish": item.get("title_hinglish")
                or item.get("working_title"),
            }
        )
    return slots


def extra_keywords_for_refine(
    topics: list[dict],
    used_ids: set[str],
    *,
    keyword_analysis_by_id: dict[str, dict] | None = None,
    limit: int = 8,
) -> list[dict]:
    """Spare scored keywords the refine AI may swap in if the user prompt asks."""
    analysis = keyword_analysis_by_id or {}
    pool = [
        t
        for t in topics
        if t.get("id")
        and t["id"] not in used_ids
        and float(t.get("recommendation_score") or 0) >= SCORE_THRESHOLD
    ]
    pool.sort(
        key=lambda t: (
            -float(t.get("recommendation_score") or 0),
            (t.get("text") or "").lower(),
        )
    )
    extras: list[dict] = []
    for topic in pool[: max(0, limit)]:
        row = analysis.get(topic["id"]) or {}
        extras.append(
            {
                "topic_id": topic["id"],
                "topic_text": topic.get("text") or "",
                "recommendation_score": float(topic.get("recommendation_score") or 0),
                "pending_long": bool(row.get("pending_long", True)),
                "pending_short": bool(row.get("pending_short", True)),
            }
        )
    return extras


def merge_enriched(
    slots: list[dict],
    enriched: list[dict],
    recent_types: list[str],
    *,
    extra_keywords: list[dict] | None = None,
) -> list[dict]:
    by_id = {s["topic_id"]: s for s in slots}
    for ek in extra_keywords or []:
        tid = ek.get("topic_id")
        if tid and tid not in by_id:
            by_id[tid] = {
                "topic_id": tid,
                "topic_text": ek.get("topic_text") or "",
                "format": "Long",  # overridden by AI format when merging
                "recommendation_score": float(ek.get("recommendation_score") or 0),
                "pending_long": bool(ek.get("pending_long", True)),
                "pending_short": bool(ek.get("pending_short", True)),
            }

    items: list[dict] = []
    seen: set[str] = set()
    batch_types: list[str] = []
    target_count = len(slots)

    for idx, row in enumerate(enriched):
        if len(items) >= target_count:
            break
        tid = row.get("topic_id")
        base = by_id.get(tid) if tid else None
        if not base:
            text = (row.get("topic_text") or "").strip().lower()
            base = next(
                (
                    s
                    for s in list(by_id.values())
                    if (s.get("topic_text") or "").lower() == text
                ),
                None,
            )
        # Fall back to original slot at this index (title rewrite, same keyword)
        if not base and idx < len(slots):
            base = slots[idx]
        if not base or base["topic_id"] in seen:
            continue
        # Keep original slot format when rewriting; allow AI format only if valid
        slot_fmt = (
            slots[idx]["format"]
            if idx < len(slots)
            else base.get("format") or "Long"
        )
        fmt = row.get("format") if row.get("format") in ("Long", "Short") else slot_fmt
        vtype = normalize_video_type(row.get("video_type"), fmt)
        if not row.get("video_type"):
            vtype = pick_video_type(fmt, recent_types + batch_types)
        batch_types.append(vtype)
        title_en = (row.get("title_en") or "").strip()
        title_hi = (row.get("title_hinglish") or "").strip()
        if not title_en and not title_hi:
            title_en = f"{base['topic_text']}: what you must know"
            title_hi = f"{base['topic_text']} — jaanna zaroori hai"
        elif not title_en:
            title_en = title_hi
        elif not title_hi:
            title_hi = title_en
        items.append(
            {
                "id": _new_id(),
                "topic_id": base["topic_id"],
                "topic_text": base["topic_text"],
                "recommendation_score": base["recommendation_score"],
                "format": fmt,
                "video_type": vtype,
                "title_en": title_en,
                "title_hinglish": title_hi,
                "working_title": title_hi or title_en,
                "reasoning": (row.get("reasoning") or "").strip()
                or (
                    f"Score {base['recommendation_score']}; "
                    f"{fmt} for mix; theme {vtype}."
                ),
            }
        )
        seen.add(base["topic_id"])

    for slot in slots:
        if len(items) >= target_count:
            break
        if slot["topic_id"] in seen:
            continue
        fmt = slot["format"]
        vtype = pick_video_type(fmt, recent_types + batch_types)
        batch_types.append(vtype)
        title_en = f"{slot['topic_text']}: what you must know"
        title_hi = f"{slot['topic_text']} — jaanna zaroori hai"
        items.append(
            {
                "id": _new_id(),
                "topic_id": slot["topic_id"],
                "topic_text": slot["topic_text"],
                "recommendation_score": slot["recommendation_score"],
                "format": fmt,
                "video_type": vtype,
                "title_en": title_en,
                "title_hinglish": title_hi,
                "working_title": title_hi,
                "reasoning": (
                    f"Score {slot['recommendation_score']} from DB; "
                    f"{fmt}; theme {vtype}. AI enrichment incomplete."
                ),
            }
        )
        seen.add(slot["topic_id"])
    return items[:target_count]


def generate_content_plan(
    client: dict,
    *,
    count: int = 5,
    force_remap: bool = False,
    user_prompt: str | None = None,
    regenerate: bool = False,
) -> dict[str, Any]:
    count = max(2, min(10, int(count or 5)))
    topics = scored_topics(client)
    topics_by_id = {t["id"]: t for t in topics}
    videos = collect_client_videos(client, public_only=True)
    coverage = ensure_video_topic_coverage(client, force=force_remap)
    analysis = coverage.get("keyword_analysis") or build_keyword_analysis(
        topics, videos, coverage
    )
    analysis_by_id = {r["topic_id"]: r for r in analysis}

    prev = (client.get("content_suggestions") or {}).get("items") or []
    library_topics = recent_library_topics(coverage, videos, topics_by_id, limit=20)
    recent_types = recent_video_types(coverage, videos, limit=20)
    for item in prev[:5]:
        if isinstance(item, dict) and item.get("video_type"):
            recent_types.append(item["video_type"])

    extra_keywords: list[dict] = []
    analysis_for_ai: list[dict] = []
    if regenerate:
        if not prev:
            raise ValueError(
                "No existing suggestions to regenerate. Generate a content plan first."
            )
        slots = slots_from_previous_items(prev, topics_by_id, analysis_by_id)
        if not slots:
            raise ValueError(
                "Previous suggestions have no usable topics. Generate a content plan first."
            )
        used_ids = {s["topic_id"] for s in slots}
        extra_keywords = extra_keywords_for_refine(
            topics,
            used_ids,
            keyword_analysis_by_id=analysis_by_id,
            limit=8,
        )
    else:
        format_meta = _covered_format_meta(videos, coverage)
        median = _median_views(videos)
        formats = next_formats(videos, count)
        picked = pick_topics_for_formats(topics, formats, format_meta, median)
        slots = build_slots(
            picked,
            formats[: len(picked)],
            keyword_analysis_by_id=analysis_by_id,
        )
        picked_ids = {s["topic_id"] for s in slots}
        analysis_for_ai = [r for r in analysis if r.get("topic_id") in picked_ids]

    enriched = enrich_suggestions(
        slots=slots,
        specialty=client.get("specialty"),
        description=client.get("description"),
        recent_library_topics=library_topics,
        recent_video_types=recent_types,
        keyword_analysis=analysis_for_ai if not regenerate else None,
        fresh_channel=len(videos) == 0,
        client_id=client.get("id"),
        user_prompt=user_prompt,
        previous_items=prev if regenerate else None,
        extra_keywords=extra_keywords if regenerate else None,
        regenerate=regenerate,
    )
    items = merge_enriched(
        slots,
        enriched,
        recent_types,
        extra_keywords=extra_keywords if regenerate else None,
    )

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "count": len(items),
        "user_prompt": user_prompt,
        "items": items,
        "coverage": coverage_summary(coverage),
        "keyword_analysis": analysis,
        "recent_video_types": recent_types[:20],
        "recent_library_topics": library_topics,
    }
    client["content_suggestions"] = payload
    return payload


def map_content_plan_only(client: dict, *, force: bool = True) -> dict[str, Any]:
    """1st call: map library → keywords, persist Long/Short analysis (no titles yet)."""
    topics = scored_topics(client)
    videos = collect_client_videos(client, public_only=True)
    coverage = ensure_video_topic_coverage(client, force=force)
    analysis = coverage.get("keyword_analysis") or build_keyword_analysis(
        topics, videos, coverage
    )
    summary = coverage_summary(coverage)
    # Keep prior suggestions items if any; refresh analysis on the payload
    prev = client.get("content_suggestions") or {}
    payload = {
        **prev,
        "coverage": summary,
        "keyword_analysis": analysis,
        "mapped_at": coverage.get("mapped_at"),
    }
    if "items" not in payload:
        payload["items"] = []
        payload["count"] = 0
    client["content_suggestions"] = payload
    return payload


def _doctor_profile(client: dict) -> dict[str, str]:
    """Name + spoken designation; optional rare location for script intro."""
    name = (client.get("name") or "").strip()
    designation = (client.get("designation") or "").strip()
    description = (client.get("description") or "").strip()
    location = (client.get("location") or "").strip()
    if not name or name.lower() in {"client", "doctor"}:
        name = "[Creator Name]"
    if not designation:
        designation = "[Title / Role]"
    return {
        "doctor_name": name,
        "doctor_designation": designation,
        "doctor_location": location,
        "description": description,
    }


def _clean_script_text(text: str) -> str:
    """Strip em/en dashes from spoken script (use plain punctuation instead)."""
    if not text:
        return ""
    cleaned = text.replace("\u2014", ". ").replace("\u2013", ", ")
    # Collapse accidental double spaces / ". ." from replacements
    while "  " in cleaned:
        cleaned = cleaned.replace("  ", " ")
    cleaned = cleaned.replace(". .", ".").replace(",,", ",")
    return cleaned.strip()


def generate_scripts_for_plan(
    client: dict,
    *,
    example1: str | None = None,
    example2: str | None = None,
) -> dict[str, Any]:
    """Generate spoken Hinglish scripts for all current content-plan titles; persist."""
    suggestions = client.get("content_suggestions") or {}
    items = [i for i in (suggestions.get("items") or []) if isinstance(i, dict)]
    if not items:
        raise ValueError(
            "No content-plan titles yet. Generate titles first, then scripts."
        )

    profile = _doctor_profile(client)
    scripted = generate_scripts_batch(
        items=items,
        doctor_name=profile["doctor_name"],
        doctor_designation=profile["doctor_designation"],
        doctor_location=profile.get("doctor_location") or None,
        specialty=client.get("specialty"),
        description=client.get("description"),
        client_id=client.get("id"),
        example1=example1,
        example2=example2,
    )
    by_id = {
        (row.get("id") or "").strip(): row
        for row in scripted
        if isinstance(row, dict) and (row.get("id") or "").strip()
    }

    updated: list[dict] = []
    for item in items:
        row = dict(item)
        match = by_id.get((row.get("id") or "").strip())
        if match:
            row["script"] = _clean_script_text(match.get("script") or "")
            row["script_target_duration"] = (
                match.get("target_duration") or ""
            ).strip()
            row["script_hook_used"] = (match.get("hook_used") or "").strip()
            row["script_cta"] = _clean_script_text(match.get("cta_line") or "")
            row["script_checklist_passed"] = bool(match.get("checklist_passed"))
            row["script_checklist_notes"] = (
                match.get("checklist_notes") or ""
            ).strip()
        updated.append(row)

    missing = sum(1 for r in updated if not (r.get("script") or "").strip())
    if missing == len(updated):
        raise ValueError("OpenAI returned no usable scripts for the content plan.")

    payload = {
        **suggestions,
        "items": updated,
        "scripts_generated_at": datetime.now(timezone.utc).isoformat(),
        "count": len(updated),
    }
    client["content_suggestions"] = payload
    return payload


def refine_script_for_item(
    client: dict,
    *,
    item_id: str,
    user_prompt: str,
) -> dict[str, Any]:
    """Refine one content-plan item's script with a user prompt; persist."""
    prompt = (user_prompt or "").strip()
    if not prompt:
        raise ValueError("user_prompt is required to refine a script.")
    target_id = (item_id or "").strip()
    if not target_id:
        raise ValueError("item_id is required.")

    suggestions = client.get("content_suggestions") or {}
    items = [i for i in (suggestions.get("items") or []) if isinstance(i, dict)]
    if not items:
        raise ValueError("No content-plan items found.")

    idx = next(
        (i for i, row in enumerate(items) if (row.get("id") or "").strip() == target_id),
        None,
    )
    if idx is None:
        raise ValueError("Content-plan item not found.")

    item = items[idx]
    old_script = (item.get("script") or "").strip()
    if not old_script:
        raise ValueError("This item has no script yet. Generate scripts first.")

    profile = _doctor_profile(client)
    refined = refine_single_script(
        script=old_script,
        user_prompt=prompt,
        format=item.get("format") or "Long",
        video_type=item.get("video_type") or "",
        target_duration=item.get("script_target_duration"),
        topic_text=item.get("topic_text"),
        title_en=item.get("title_en") or item.get("working_title"),
        title_hinglish=item.get("title_hinglish") or item.get("working_title"),
        doctor_name=profile["doctor_name"],
        doctor_designation=profile["doctor_designation"],
        doctor_location=profile.get("doctor_location") or None,
        specialty=client.get("specialty"),
        client_id=client.get("id"),
    )
    new_script = (refined.get("script") or "").strip()
    if not new_script:
        raise ValueError("OpenAI returned an empty refined script.")

    updated = dict(item)
    updated["script"] = _clean_script_text(new_script)
    if refined.get("target_duration"):
        updated["script_target_duration"] = str(refined.get("target_duration")).strip()
    if refined.get("hook_used"):
        updated["script_hook_used"] = str(refined.get("hook_used")).strip()
    if refined.get("cta_line"):
        updated["script_cta"] = _clean_script_text(str(refined.get("cta_line")))
    if "checklist_passed" in refined:
        updated["script_checklist_passed"] = bool(refined.get("checklist_passed"))
    if refined.get("checklist_notes"):
        updated["script_checklist_notes"] = str(refined.get("checklist_notes")).strip()

    new_items = list(items)
    new_items[idx] = updated
    payload = {
        **suggestions,
        "items": new_items,
        "count": len(new_items),
    }
    client["content_suggestions"] = payload
    return payload
