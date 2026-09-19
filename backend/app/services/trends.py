"""Google Trends (web + YouTube) scoring for client topics via SerpApi.

Region defaults to India. Batches up to 5 keywords per google_trends search
(web + YouTube). Scoring helpers match the original DataForSEO pipeline.
"""

from __future__ import annotations

import asyncio
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from serpapi import GoogleSearch

from app.config import settings

_FORBIDDEN_RE = re.compile(r'[<>|\\"\-+=~!:*()\[\]{}]')

# SerpApi google_trends supports up to 5 comparison queries
_BATCH_SIZE = 5

_STOP_STATUS_MARKERS = (
    "payment",
    "balance",
    "fund",
    "credit",
    "limit",
    "quota",
    "unauthorized",
    "forbidden",
    "invalid api key",
    "run out of searches",
)


def _log(msg: str) -> None:
    print(f"[trends] {msg}", flush=True)


def _api_key() -> str:
    key = (settings.SERPAPI_API_KEY or "").strip()
    if not key:
        raise ValueError(
            "SerpApi credentials missing. Set SERPAPI_API_KEY in .env "
            "(https://serpapi.com/manage-api-key)."
        )
    return key


def _sanitize_keyword(text: str) -> str | None:
    cleaned = re.sub(r"\s+", " ", (text or "").strip())
    cleaned = _FORBIDDEN_RE.sub(" ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if len(cleaned) < 2 or len(cleaned) > 100:
        return None
    return cleaned


def _chunk(items: list, size: int) -> list[list]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def _parse_timeline(body: dict | None, keywords: list[str]) -> list[list[dict]]:
    """SerpApi interest_over_time.timeline_data → per-keyword series."""
    series: list[list[dict]] = [[] for _ in keywords]
    if not body:
        return series
    timeline = ((body.get("interest_over_time") or {}).get("timeline_data")) or []
    keyword_lc = [k.lower() for k in keywords]
    for row in timeline:
        ts = int(row.get("timestamp") or 0)
        date_from = row.get("date")
        values = row.get("values") or []
        by_query: dict[str, float] = {}
        ordered: list[float | None] = []
        for cell in values:
            if not isinstance(cell, dict):
                continue
            raw = cell.get("extracted_value")
            if raw is None:
                raw = cell.get("value")
            try:
                val = float(raw)
            except (TypeError, ValueError):
                continue
            query = str(cell.get("query") or "").strip().lower()
            if query:
                by_query[query] = val
            ordered.append(val)
        for i, key in enumerate(keyword_lc):
            val = by_query.get(key)
            if val is None and i < len(ordered):
                val = ordered[i]
            if val is None:
                continue
            series[i].append({"timestamp": ts, "value": val, "date_from": date_from})
    return series


def _avg(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _series_avg(points: list[dict]) -> float | None:
    return _avg([p["value"] for p in points])


def _momentum(points: list[dict]) -> float | None:
    if len(points) < 8:
        return None
    recent_n = max(4, len(points) // 4)
    recent = points[-recent_n:]
    prior = points[-(2 * recent_n) : -recent_n]
    if not prior:
        return None
    recent_avg = _series_avg(recent)
    prior_avg = _series_avg(prior)
    if recent_avg is None or prior_avg is None or prior_avg <= 0:
        if recent_avg and recent_avg > 0:
            return 1.0
        return None
    return max(-1.0, min(2.0, (recent_avg / prior_avg) - 1.0))


def _confidence(
    web_avg: float | None, yt_avg: float | None, web_points: int, yt_points: int
) -> str:
    has_web = web_avg is not None and web_avg > 0 and web_points >= 4
    has_yt = yt_avg is not None and yt_avg > 0 and yt_points >= 4
    if has_web and has_yt:
        return "high"
    if has_web or has_yt:
        return "medium"
    return "low"


def _percentile_ranks(values: list[float | None]) -> list[float | None]:
    indexed = [(i, v) for i, v in enumerate(values) if v is not None]
    if not indexed:
        return [None] * len(values)
    indexed.sort(key=lambda x: x[1])
    n = len(indexed)
    ranks: list[float | None] = [None] * len(values)
    i = 0
    while i < n:
        j = i
        while j < n and indexed[j][1] == indexed[i][1]:
            j += 1
        avg_rank = (i + j - 1) / 2.0
        pct = (avg_rank / (n - 1) * 100.0) if n > 1 else 50.0
        for k in range(i, j):
            ranks[indexed[k][0]] = pct
        i = j
    return ranks


def _compose_score(
    web_pct: float | None,
    yt_pct: float | None,
    momentum: float | None,
    rising_flag: int,
) -> float | None:
    parts: list[tuple[float, float]] = []
    if web_pct is not None:
        parts.append((0.40, web_pct))
    if yt_pct is not None:
        parts.append((0.30, yt_pct))
    if momentum is not None:
        parts.append((0.20, ((momentum + 1.0) / 3.0) * 100.0))
    parts.append((0.10, {0: 0.0, 1: 50.0, 2: 100.0}.get(rising_flag or 0, 0.0)))
    if web_pct is None and yt_pct is None and momentum is None:
        return None
    total_w = sum(w for w, _ in parts)
    if total_w <= 0:
        return None
    return round(max(0.0, min(100.0, sum(w * v for w, v in parts) / total_w)), 1)


def _is_fresh(topic: dict, geo: str, ttl_days: int) -> bool:
    if topic.get("trend_geo") != geo:
        return False
    fetched = topic.get("trend_fetched_at")
    if not fetched:
        return False
    try:
        ts = datetime.fromisoformat(fetched.replace("Z", "+00:00"))
    except ValueError:
        return False
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - ts < timedelta(days=ttl_days)


def _should_stop(message: str | None, status_code: int | None = None) -> bool:
    if status_code in (401, 402, 403, 429):
        return True
    text = (message or "").lower()
    return any(m in text for m in _STOP_STATUS_MARKERS)


def _weight_rank(weight: str) -> int:
    return {"high": 0, "medium": 1, "low": 2}.get(weight or "medium", 1)


def _search_sync(
    keywords: list[str],
    *,
    trend_type: str,
    geo: str,
    api_key: str,
) -> dict[str, Any]:
    params: dict[str, Any] = {
        "engine": "google_trends",
        "q": ",".join(keywords),
        "geo": geo,
        "date": "today 12-m",
        "data_type": "TIMESERIES",
        "api_key": api_key,
    }
    if trend_type == "youtube":
        params["gprop"] = "youtube"
    search = GoogleSearch(params)
    return search.get_dict()


async def _fetch_batch(
    keywords: list[str],
    *,
    trend_type: str,
    geo: str,
    api_key: str,
) -> dict[str, Any]:
    label = f"{trend_type} [{', '.join(keywords)}]"
    _log(f"→ request {label}")
    try:
        body = await asyncio.to_thread(
            _search_sync, keywords, trend_type=trend_type, geo=geo, api_key=api_key
        )
    except Exception as exc:
        _log(f"✗ HTTP/SDK error on {label}: {exc}")
        return {
            "series": [[] for _ in keywords],
            "cost": 0.0,
            "error": f"SerpApi error: {exc}",
            "stop": _should_stop(str(exc)),
        }

    err = body.get("error")
    search_meta = body.get("search_metadata") or {}
    status = str(search_meta.get("status") or "")
    _log(f"← {label} status={status or 'ok'} error={err!r}")

    if err:
        return {
            "series": [[] for _ in keywords],
            "cost": 0.0,
            "error": str(err),
            "stop": _should_stop(str(err)),
        }

    series = _parse_timeline(body, keywords)
    avgs = [_series_avg(s) for s in series]
    _log(
        f"  ok points={[len(s) for s in series]} avgs="
        f"{[round(a, 1) if a is not None else None for a in avgs]}"
    )
    return {
        "series": series,
        "cost": 0.0,
        "error": None,
        "stop": False,
    }


async def analyze_topics_trends(
    topics: list[dict],
    *,
    force: bool = False,
) -> tuple[list[dict], dict]:
    """Score topics with India Google Search + YouTube Trends via SerpApi."""
    geo = (settings.TRENDS_GEO or "IN").strip().upper() or "IN"
    ttl_days = max(0, int(settings.TRENDS_TTL_DAYS or 7))
    now_iso = datetime.now(timezone.utc).isoformat()

    updated = [dict(t) for t in topics]
    to_fetch: list[int] = []
    skipped_cached = 0

    for i, topic in enumerate(updated):
        has_interest = (
            topic.get("web_interest") is not None
            or topic.get("youtube_interest") is not None
        )
        if (
            not force
            and _is_fresh(topic, geo, ttl_days)
            and (topic.get("trend_score") is not None or has_interest)
        ):
            skipped_cached += 1
            continue
        if not _sanitize_keyword(topic.get("text") or ""):
            _log(f"skip invalid keyword: {topic.get('text')!r}")
            topic["trend_score"] = None
            topic["trend_confidence"] = "low"
            topic["trend_geo"] = geo
            topic["web_interest"] = None
            topic["youtube_interest"] = None
            topic["momentum"] = None
            topic["rising_flag"] = 0
            topic["trend_fetched_at"] = now_iso
            continue
        to_fetch.append(i)

    to_fetch.sort(key=lambda idx: (_weight_rank(updated[idx].get("weight")), idx))

    n_fetch = len(to_fetch)
    n_batches = len(_chunk(to_fetch, _BATCH_SIZE)) if to_fetch else 0
    est_tasks = n_batches * 2

    _log(
        f"start force={force} geo={geo} total={len(updated)} "
        f"to_fetch={n_fetch} cached_skip={skipped_cached} "
        f"batches={n_batches}×2(web+yt)≈{est_tasks} SerpApi searches"
    )

    summary: dict[str, Any] = {
        "geo": geo,
        "scored": 0,
        "insufficient_data": 0,
        "skipped_cached": skipped_cached,
        "fetched_at": now_iso,
        "error": None,
        "api_tasks": 0,
        "total_cost": 0.0,
    }

    if not to_fetch:
        summary["scored"] = sum(1 for t in updated if t.get("trend_score") is not None)
        summary["insufficient_data"] = sum(
            1 for t in updated if t.get("trend_confidence") == "low"
        )
        _log("nothing to fetch")
        return updated, summary

    api_key = _api_key()
    metrics: dict[int, dict] = {}
    completed: set[int] = set()

    for batch_num, batch_idxs in enumerate(_chunk(to_fetch, _BATCH_SIZE), start=1):
        keywords = [_sanitize_keyword(updated[i]["text"]) for i in batch_idxs]
        assert all(keywords)
        _log(
            f"batch {batch_num}/{n_batches} "
            f"weights={[updated[i].get('weight') for i in batch_idxs]} "
            f"keywords={keywords}"
        )

        web = await _fetch_batch(
            keywords, trend_type="web", geo=geo, api_key=api_key
        )
        summary["api_tasks"] += 1
        summary["total_cost"] += float(web.get("cost") or 0)

        if web.get("stop"):
            summary["error"] = web.get("error") or "SerpApi stopped (quota/auth)"
            _log(f"STOP after web: {summary['error']}")
            break

        if web.get("error"):
            _log(f"web error (continuing): {web['error']}")
            if not summary["error"]:
                summary["error"] = web["error"]

        yt = await _fetch_batch(
            keywords, trend_type="youtube", geo=geo, api_key=api_key
        )
        summary["api_tasks"] += 1
        summary["total_cost"] += float(yt.get("cost") or 0)

        if yt.get("stop"):
            summary["error"] = yt.get("error") or "SerpApi stopped (quota/auth)"
            _log(f"STOP after youtube: {summary['error']}")
            for i, idx in enumerate(batch_idxs):
                web_pts = (web.get("series") or [[]])[i]
                metrics[idx] = {
                    "web_points": web_pts,
                    "yt_points": [],
                    "web_avg": _series_avg(web_pts),
                    "yt_avg": None,
                    "rising_flag": 0,
                }
                completed.add(idx)
            break

        if yt.get("error"):
            _log(f"youtube error (continuing): {yt['error']}")
            if not summary["error"]:
                summary["error"] = yt["error"]

        for i, idx in enumerate(batch_idxs):
            web_pts = (web.get("series") or [[]])[i]
            yt_pts = (yt.get("series") or [[]])[i]
            web_avg = _series_avg(web_pts)
            yt_avg = _series_avg(yt_pts)
            metrics[idx] = {
                "web_points": web_pts,
                "yt_points": yt_pts,
                "web_avg": web_avg,
                "yt_avg": yt_avg,
                "rising_flag": 0,
            }
            completed.add(idx)
            _log(f"  · {updated[idx]['text']!r}: web={web_avg} yt={yt_avg}")

        _log(
            f"running total: tasks={summary['api_tasks']} "
            f"completed={len(completed)}/{n_fetch}"
        )

    for idx in completed:
        m = metrics[idx]
        topic = updated[idx]
        mom = _momentum(m["web_points"])
        if mom is None:
            mom = _momentum(m["yt_points"])
        conf = _confidence(
            m["web_avg"], m["yt_avg"], len(m["web_points"]), len(m["yt_points"])
        )
        topic["web_interest"] = (
            round(m["web_avg"], 1) if m["web_avg"] is not None else None
        )
        topic["youtube_interest"] = (
            round(m["yt_avg"], 1) if m["yt_avg"] is not None else None
        )
        topic["momentum"] = round(mom, 3) if mom is not None else None
        topic["rising_flag"] = 0
        topic["trend_confidence"] = conf
        topic["trend_geo"] = geo
        topic["trend_fetched_at"] = now_iso

    all_web = [t.get("web_interest") for t in updated]
    all_yt = [t.get("youtube_interest") for t in updated]
    all_web_pct = _percentile_ranks(all_web)
    all_yt_pct = _percentile_ranks(all_yt)
    for i, topic in enumerate(updated):
        if topic.get("web_interest") is None and topic.get("youtube_interest") is None:
            topic["trend_score"] = None
            continue
        topic["trend_score"] = _compose_score(
            all_web_pct[i],
            all_yt_pct[i],
            topic.get("momentum"),
            int(topic.get("rising_flag") or 0),
        )

    summary["scored"] = sum(1 for t in updated if t.get("trend_score") is not None)
    summary["insufficient_data"] = sum(
        1 for t in updated if t.get("trend_confidence") == "low"
    )
    remaining = n_fetch - len(completed)
    _log(
        f"done scored={summary['scored']} low_data={summary['insufficient_data']} "
        f"completed={len(completed)} remaining_unfetched={remaining} "
        f"tasks={summary['api_tasks']} error={summary['error']!r}"
    )
    if remaining > 0 and summary["error"]:
        _log(
            f"partial run: {remaining} topics not fetched because of: {summary['error']}"
        )
    return updated, summary
