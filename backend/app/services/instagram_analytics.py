"""Instagram Login Graph insights for client analytics."""

from __future__ import annotations

import asyncio
import statistics
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

MAX_REELS = 40
REEL_PAGE_LIMIT = 50
INSIGHTS_SEMAPHORE = 8
GRAPH_TIMEOUT = 30.0
# Live Graph probes returned distinct totals through a full calendar year.
MAX_ANALYTICS_DAYS = 366


def clamp_analytics_window(
    since_dt: datetime, until_dt: datetime
) -> tuple[datetime, datetime]:
    if until_dt < since_dt:
        return until_dt, until_dt
    if (until_dt - since_dt).days > MAX_ANALYTICS_DAYS:
        return until_dt - timedelta(days=MAX_ANALYTICS_DAYS), until_dt
    return since_dt, until_dt


REEL_ENGAGEMENT_METRICS = (
    "views,reach,likes,comments,shares,saved,total_interactions"
)
REEL_WATCH_METRICS = (
    "ig_reels_avg_watch_time,ig_reels_video_view_total_time,reels_skip_rate"
)

CONTENT_BUCKETS = ("posts", "reels", "stories")


def _num(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _int(value: Any) -> int:
    return int(round(_num(value)))


def _parse_iso(value: str | None) -> datetime | None:
    raw = (value or "").strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    elif len(raw) >= 5 and (raw[-5] in "+-") and raw[-3] != ":":
        raw = raw[:-2] + ":" + raw[-2:]
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _lifetime_value(row: dict | None) -> float | None:
    if not row:
        return None
    values = row.get("values") or []
    if values:
        return _num(values[0].get("value"))
    total = row.get("total_value")
    if isinstance(total, dict) and "value" in total:
        return _num(total.get("value"))
    return None


def _metric_map(data: list) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for row in data or []:
        name = row.get("name")
        if name:
            out[name] = row
    return out


def _parse_breakdown(row: dict | None) -> dict[str, int]:
    if not row:
        return {}
    total = row.get("total_value") or {}
    breakdowns = total.get("breakdowns") or []
    if not breakdowns:
        return {}
    results = (breakdowns[0] or {}).get("results") or []
    parsed: dict[str, int] = {}
    for item in results:
        keys = item.get("dimension_values") or []
        if not keys:
            continue
        parsed[str(keys[0]).upper()] = _int(item.get("value"))
    return parsed


def _bucket_content_type(raw: str) -> str | None:
    key = (raw or "").upper()
    if key in {"REEL", "REELS"}:
        return "reels"
    if key in {"STORY", "STORIES"}:
        return "stories"
    if key in {"POST", "FEED", "CAROUSEL_CONTAINER", "CAROUSEL_ALBUM", "IMAGE"}:
        return "posts"
    return None


def _group_content_breakdown(raw: dict[str, int]) -> dict[str, int] | None:
    if not raw:
        return None
    grouped = {bucket: 0 for bucket in CONTENT_BUCKETS}
    matched = False
    for key, value in raw.items():
        bucket = _bucket_content_type(key)
        if not bucket:
            continue
        grouped[bucket] += int(value or 0)
        matched = True
    return grouped if matched else None


def _follow_type_split(raw: dict[str, int]) -> dict[str, int] | None:
    if not raw:
        return None
    out = {
        "follower": int(raw.get("FOLLOWER") or 0),
        "non_follower": int(raw.get("NON_FOLLOWER") or 0),
        "unknown": int(raw.get("UNKNOWN") or 0),
    }
    if out["follower"] == 0 and out["non_follower"] == 0 and out["unknown"] == 0:
        return None
    return out


def _parse_time_series(data: list) -> dict[str, list[dict]]:
    series: dict[str, list[dict]] = {}
    for row in data or []:
        name = row.get("name")
        values = row.get("values") or []
        if not name or not values:
            continue
        points = []
        for item in values:
            value = item.get("value")
            if isinstance(value, dict):
                continue
            points.append(
                {"value": _int(value), "end_time": item.get("end_time") or ""}
            )
        if points:
            series[name] = points
    return series


def _watch_seconds(raw_ms: float | None) -> float | None:
    if raw_ms is None:
        return None
    if raw_ms <= 0:
        return 0.0
    # Meta returns milliseconds for reel watch-time metrics.
    return round(raw_ms / 1000.0, 2)


def _rate_pct(count: float, views: float) -> float | None:
    if views <= 0:
        return None
    return round((count / views) * 100.0, 1)


def _median(values: list[float]) -> float | None:
    clean = [v for v in values if v is not None]
    if not clean:
        return None
    return round(float(statistics.median(clean)), 2)


def _is_reel(row: dict) -> bool:
    product = (row.get("media_product_type") or "").upper()
    media_type = (row.get("media_type") or "").upper()
    return product in {"REELS", "REEL"} or (
        media_type == "VIDEO" and product not in {"STORY", "FEED"}
    )


async def _get_json(
    client: httpx.AsyncClient, url: str, params: dict
) -> tuple[int, dict | list | None, str]:
    try:
        resp = await client.get(url, params=params)
    except Exception as exc:  # noqa: BLE001
        print(f"[plug:ig] request failed {url}: {exc}", flush=True)
        return 0, None, str(exc)
    text = resp.text
    try:
        payload = resp.json()
    except Exception:
        payload = None
    if not resp.is_success:
        err = ""
        if isinstance(payload, dict):
            err = str((payload.get("error") or {}).get("message") or text[:400])
        else:
            err = text[:400]
        print(f"[plug:ig] {resp.status_code} {url}: {err}", flush=True)
        return resp.status_code, payload, err
    return resp.status_code, payload, ""


async def _account_totals(
    client: httpx.AsyncClient,
    ig_id: str,
    token: str,
    since_ts: int,
    until_ts: int,
) -> tuple[dict[str, int], dict[str, list[dict]]]:
    base = f"https://graph.instagram.com/{ig_id}/insights"
    ts_status, ts_payload, _ = await _get_json(
        client,
        base,
        {
            "metric": "reach,follower_count,profile_views,views,likes,comments,saves,shares",
            "period": "day",
            "since": since_ts,
            "until": until_ts,
            "access_token": token,
        },
    )
    tv_status, tv_payload, _ = await _get_json(
        client,
        base,
        {
            "metric": (
                "reach,accounts_engaged,total_interactions,views,saves,likes,"
                "comments,shares,profile_views,website_clicks,follows_and_unfollows,"
                "profile_links_taps"
            ),
            "period": "day",
            "metric_type": "total_value",
            "since": since_ts,
            "until": until_ts,
            "access_token": token,
        },
    )
    ts_data = (ts_payload or {}).get("data") if ts_status == 200 and isinstance(ts_payload, dict) else []
    tv_data = (tv_payload or {}).get("data") if tv_status == 200 and isinstance(tv_payload, dict) else []
    by_name = _metric_map(tv_data)

    def tv(name: str) -> int:
        row = by_name.get(name)
        if not row:
            return 0
        total = row.get("total_value") or {}
        if isinstance(total, dict) and "value" in total:
            return _int(total.get("value"))
        return _int(_lifetime_value(row))

    metrics = {
        "reach": tv("reach"),
        "accounts_engaged": tv("accounts_engaged"),
        "total_interactions": tv("total_interactions"),
        "views": tv("views"),
        "saves": tv("saves"),
        "likes": tv("likes"),
        "comments": tv("comments"),
        "shares": tv("shares"),
        "profile_views": tv("profile_views"),
        "website_clicks": tv("website_clicks"),
        "follows_and_unfollows": tv("follows_and_unfollows"),
        "profile_links_taps": tv("profile_links_taps"),
    }
    return metrics, _parse_time_series(ts_data)


async def _breakdown_call(
    client: httpx.AsyncClient,
    ig_id: str,
    token: str,
    *,
    metric: str,
    breakdown: str,
    since_ts: int,
    until_ts: int,
) -> dict[str, int]:
    status, payload, _ = await _get_json(
        client,
        f"https://graph.instagram.com/{ig_id}/insights",
        {
            "metric": metric,
            "period": "day",
            "metric_type": "total_value",
            "breakdown": breakdown,
            "since": since_ts,
            "until": until_ts,
            "access_token": token,
        },
    )
    if status != 200 or not isinstance(payload, dict):
        return {}
    rows = payload.get("data") or []
    return _parse_breakdown(rows[0] if rows else None)


async def _list_reels_in_range(
    client: httpx.AsyncClient,
    ig_id: str,
    token: str,
    since_dt: datetime,
    until_dt: datetime,
) -> list[dict]:
    reels: list[dict] = []
    after: str | None = None
    while len(reels) < MAX_REELS:
        params: dict[str, Any] = {
            "fields": (
                "id,caption,media_type,media_product_type,timestamp,"
                "permalink,thumbnail_url,media_url"
            ),
            "limit": REEL_PAGE_LIMIT,
            "access_token": token,
        }
        if after:
            params["after"] = after
        status, payload, _ = await _get_json(
            client,
            f"https://graph.instagram.com/{ig_id}/media",
            params,
        )
        if status != 200 or not isinstance(payload, dict):
            break
        rows = payload.get("data") or []
        if not rows:
            break
        stop = False
        for row in rows:
            published = _parse_iso(row.get("timestamp"))
            if not published:
                continue
            if published > until_dt:
                continue
            if published < since_dt:
                stop = True
                break
            if not _is_reel(row):
                continue
            reels.append(row)
            if len(reels) >= MAX_REELS:
                break
        paging = ((payload.get("paging") or {}).get("cursors") or {})
        after = paging.get("after")
        if stop or not after:
            break
    return reels[:MAX_REELS]


def _build_reel_row(media: dict, engagement: dict, watch: dict) -> dict:
    views = _int(_lifetime_value(engagement.get("views")))
    reach = _int(_lifetime_value(engagement.get("reach")))
    likes = _int(_lifetime_value(engagement.get("likes")))
    comments = _int(_lifetime_value(engagement.get("comments")))
    shares = _int(_lifetime_value(engagement.get("shares")))
    saved = _int(_lifetime_value(engagement.get("saved")))
    total_interactions = _int(_lifetime_value(engagement.get("total_interactions")))
    avg_watch_seconds = _watch_seconds(_lifetime_value(watch.get("ig_reels_avg_watch_time")))
    total_watch_seconds = _watch_seconds(
        _lifetime_value(watch.get("ig_reels_video_view_total_time"))
    )
    skip_raw = _lifetime_value(watch.get("reels_skip_rate"))
    skip_rate = round(skip_raw, 1) if skip_raw is not None else None
    engagement_rate = None
    if reach > 0:
        engagement_rate = round(
            ((likes + comments + shares + saved) / reach) * 100.0, 1
        )
    caption = (media.get("caption") or "").strip()
    return {
        "id": media.get("id") or "",
        "caption": caption,
        "permalink": media.get("permalink") or "",
        "thumbnail_url": media.get("thumbnail_url") or media.get("media_url") or "",
        "timestamp": media.get("timestamp") or "",
        "views": views,
        "reach": reach,
        "likes": likes,
        "comments": comments,
        "shares": shares,
        "saved": saved,
        "total_interactions": total_interactions,
        "avg_watch_seconds": avg_watch_seconds,
        "total_watch_seconds": total_watch_seconds,
        "skip_rate": skip_rate,
        "like_rate": _rate_pct(likes, views),
        "share_rate": _rate_pct(shares, views),
        "save_rate": _rate_pct(saved, views),
        "comment_rate": _rate_pct(comments, views),
        "engagement_rate": engagement_rate,
    }


async def _reel_insights(
    client: httpx.AsyncClient,
    media: dict,
    token: str,
    semaphore: asyncio.Semaphore,
) -> dict:
    media_id = media.get("id") or ""
    async with semaphore:
        eng_status, eng_payload, _ = await _get_json(
            client,
            f"https://graph.instagram.com/{media_id}/insights",
            {
                "metric": REEL_ENGAGEMENT_METRICS,
                "period": "lifetime",
                "access_token": token,
            },
        )
        watch_status, watch_payload, _ = await _get_json(
            client,
            f"https://graph.instagram.com/{media_id}/insights",
            {
                "metric": REEL_WATCH_METRICS,
                "period": "lifetime",
                "access_token": token,
            },
        )
    engagement = {}
    if eng_status == 200 and isinstance(eng_payload, dict):
        engagement = _metric_map(eng_payload.get("data") or [])
    watch = {}
    if watch_status == 200 and isinstance(watch_payload, dict):
        watch = _metric_map(watch_payload.get("data") or [])
    return _build_reel_row(media, engagement, watch)


async def fetch_plug_analytics(
    *,
    ig_id: str,
    token: str,
    since_dt: datetime,
    until_dt: datetime,
) -> dict[str, Any]:
    since_ts = int(since_dt.timestamp())
    until_ts = int(until_dt.timestamp())
    empty_metrics = {
        "reach": 0,
        "accounts_engaged": 0,
        "total_interactions": 0,
        "views": 0,
        "saves": 0,
        "likes": 0,
        "comments": 0,
        "shares": 0,
        "profile_views": 0,
        "website_clicks": 0,
        "follows_and_unfollows": 0,
        "profile_links_taps": 0,
    }
    async with httpx.AsyncClient(timeout=GRAPH_TIMEOUT) as client:
        metrics, time_series = await _account_totals(
            client, ig_id, token, since_ts, until_ts
        )
        views_follow_raw, views_content_raw, interactions_raw, media_rows = (
            await asyncio.gather(
                _breakdown_call(
                    client,
                    ig_id,
                    token,
                    metric="views",
                    breakdown="follow_type",
                    since_ts=since_ts,
                    until_ts=until_ts,
                ),
                _breakdown_call(
                    client,
                    ig_id,
                    token,
                    metric="views",
                    breakdown="media_product_type",
                    since_ts=since_ts,
                    until_ts=until_ts,
                ),
                _breakdown_call(
                    client,
                    ig_id,
                    token,
                    metric="total_interactions",
                    breakdown="media_product_type",
                    since_ts=since_ts,
                    until_ts=until_ts,
                ),
                _list_reels_in_range(client, ig_id, token, since_dt, until_dt),
            )
        )
        semaphore = asyncio.Semaphore(INSIGHTS_SEMAPHORE)
        reels = []
        if media_rows:
            reels = await asyncio.gather(
                *[_reel_insights(client, row, token, semaphore) for row in media_rows]
            )
            reels = [r for r in reels if r.get("id")]
            reels.sort(key=lambda r: int(r.get("views") or 0), reverse=True)

    if not metrics:
        metrics = empty_metrics

    watch_values = [
        r["avg_watch_seconds"]
        for r in reels
        if r.get("avg_watch_seconds") is not None
    ]
    skip_values = [r["skip_rate"] for r in reels if r.get("skip_rate") is not None]
    reel_summary = {
        "count": len(reels),
        "total_views": sum(int(r.get("views") or 0) for r in reels),
        "median_avg_watch_seconds": _median(watch_values),
        "median_skip_rate": _median(skip_values),
    }

    return {
        "metrics": metrics,
        "time_series": time_series or None,
        "views_by_follow_type": _follow_type_split(views_follow_raw),
        "views_by_content_type": _group_content_breakdown(views_content_raw),
        "interactions_by_content_type": _group_content_breakdown(interactions_raw),
        "reels": reels,
        "reel_summary": reel_summary,
    }
