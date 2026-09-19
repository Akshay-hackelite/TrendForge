"""Pull and compute multi-channel YouTube metrics for monthly AI reports."""

from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timedelta, timezone
from typing import Any

from app.database import (
    list_channels_meta,
    list_videos_for_channel,
    replace_channel_videos,
)
from app.google_oauth import get_user_google_creds
from app.services.youtube_api import (
    fetch_channel_analytics,
    fetch_video_snippets,
    sync_videos_from_youtube,
)

CHANNEL_TOTAL_METRICS = (
    "views,estimatedMinutesWatched,subscribersGained,subscribersLost,"
    "averageViewDuration,likes,comments,shares"
)
VIDEO_METRICS = (
    "views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,"
    "subscribersGained,subscribersLost"
)
TRAFFIC_METRICS = "views,estimatedMinutesWatched"

# YouTube Analytics insightTrafficSourceType → client-facing Studio names
TRAFFIC_SOURCE_LABELS = {
    "RELATED_VIDEO": "Suggested videos",
    "SUBSCRIBER": "Browse features",
    "YT_SEARCH": "YouTube search",
    "YT_CHANNEL": "Channel pages",
    "YT_OTHER_PAGE": "Other YouTube features",
    "EXT_URL": "External",
    "NO_LINK_OTHER": "Direct or unknown",
    "NO_LINK_EMBEDDED": "Embedded player",
    "PLAYLIST": "Playlists",
    "END_SCREEN": "End screens",
    "NOTIFICATION": "Notifications",
    "SHORTS": "Shorts feed",
    "HASHTAGS": "Hashtags",
    "ADVERTISING": "Advertising",
    "ANNOTATION": "Annotations",
    "CAMPAIGN_CARD": "Campaign card",
    "LIVE_REDIRECT": "Live redirect",
    "PRODUCT_PAGE": "Product page",
    "SOUND_PAGE": "Sounds",
    "VIDEO_REMIXES": "Video remixes",
    "PROMOTED": "Promoted",
}


def traffic_source_label(code: str | None) -> str:
    raw = str(code or "UNKNOWN").strip()
    key = raw.upper()
    if key in TRAFFIC_SOURCE_LABELS:
        return TRAFFIC_SOURCE_LABELS[key]
    return raw.replace("_", " ").title()


def previous_calendar_month(today: date | None = None) -> str:
    today = today or date.today()
    first = today.replace(day=1)
    prev_last = first - timedelta(days=1)
    return f"{prev_last.year:04d}-{prev_last.month:02d}"


def shift_month(yyyy_mm: str, delta: int = -1) -> str:
    year, month = map(int, yyyy_mm.split("-"))
    month += delta
    while month < 1:
        month += 12
        year -= 1
    while month > 12:
        month -= 12
        year += 1
    return f"{year:04d}-{month:02d}"


def month_bounds(yyyy_mm: str, *, today: date | None = None) -> tuple[date, date]:
    today = today or date.today()
    year, month = map(int, yyyy_mm.split("-"))
    start = date(year, month, 1)
    end = date(year, month, monthrange(year, month)[1])
    yesterday = today - timedelta(days=1)
    if end > yesterday:
        end = yesterday
    if end < start:
        end = start
    return start, end


def ai_start_date(yyyy_mm: str) -> date:
    year, month = map(int, yyyy_mm.split("-"))
    return date(year, month, 1)


def _rows_to_dicts(headers: list[str], rows: list) -> list[dict[str, Any]]:
    out = []
    for row in rows or []:
        item = {}
        for i, key in enumerate(headers):
            item[key] = row[i] if i < len(row) else None
        out.append(item)
    return out


def _safe_analytics(creds, channel_id: str, **kwargs) -> tuple[list[str], list]:
    try:
        return fetch_channel_analytics(creds, channel_id, **kwargs)
    except Exception as exc:  # noqa: BLE001 — keep report generation resilient
        print(f"[monthly-report] analytics failed channel={channel_id}: {exc}", flush=True)
        return [], []


def _sum_metric(rows: list[dict], key: str) -> float:
    total = 0.0
    for row in rows:
        val = row.get(key)
        if val is None:
            continue
        try:
            total += float(val)
        except (TypeError, ValueError):
            continue
    return total


def _parse_published(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return datetime.strptime(value[:10], "%Y-%m-%d").date()
        except ValueError:
            return None


def _video_meta_map(client_id: str, channel_id: str) -> dict[str, dict]:
    meta = {}
    for v in list_videos_for_channel(channel_id, client_id):
        vid = v.get("id") or v.get("video_id")
        if not vid:
            continue
        meta[str(vid)] = {
            "id": str(vid),
            "title": v.get("title") or str(vid),
            "published_at": v.get("published_at") or v.get("publishedAt"),
            "is_short": bool(v.get("is_short")),
            "duration_type": v.get("duration_type")
            or ("short" if v.get("is_short") else "long"),
            "channel_id": channel_id,
        }
    return meta


def sync_video_catalogs_for_report(
    *,
    username: str,
    client_id: str,
    channels_meta: list[dict[str, Any]],
) -> dict[str, int]:
    """Refresh local video catalogs for every linked channel before metrics.

    Titles + published_at drive AI classification and report labels. Without a
    fresh sync, analytics video IDs fall back to bare IDs and are never counted
    as AI (no publish date).
    """
    synced_counts: dict[str, int] = {}
    for ch in channels_meta:
        channel_id = ch.get("id")
        if not channel_id:
            continue
        label = ch.get("title") or channel_id
        try:
            creds = get_user_google_creds(username, client_id, channel_id)
            synced_videos = sync_videos_from_youtube(creds, channel_id)
            existing = {
                v["id"]: v for v in list_videos_for_channel(channel_id, client_id)
            }
            for v in synced_videos:
                prev = existing.get(v.id) or {}
                v.notes = prev.get("notes", "") or ""
                v.metadata_fields = prev.get("metadata_fields", {}) or {}
            rows = [v.model_dump() for v in synced_videos]
            replace_channel_videos(channel_id, client_id, rows)
            synced_counts[channel_id] = len(rows)
            print(
                f"[monthly-report] synced catalog channel={label!r} "
                f"videos={len(rows)}",
                flush=True,
            )
        except Exception as exc:
            # Keep going with stale/empty catalog for this channel
            synced_counts[channel_id] = -1
            print(
                f"[monthly-report] catalog sync failed channel={label!r}: {exc}",
                flush=True,
            )
    return synced_counts


def _enrich_missing_video_meta(
    creds,
    channel_id: str,
    video_ids: list[str],
    video_meta: dict[str, dict],
) -> None:
    """Fill title/published_at for analytics IDs still missing after catalog sync."""
    missing = [
        vid
        for vid in video_ids
        if vid
        and (
            vid not in video_meta
            or not video_meta[vid].get("published_at")
            or (video_meta[vid].get("title") or "") == vid
        )
    ]
    if not missing:
        return
    snippets = fetch_video_snippets(creds, missing)
    for vid, snip in snippets.items():
        prev = video_meta.get(vid) or {
            "id": vid,
            "is_short": False,
            "duration_type": "long",
            "channel_id": channel_id,
        }
        prev["title"] = snip.get("title") or prev.get("title") or vid
        if snip.get("published_at"):
            prev["published_at"] = snip["published_at"]
        video_meta[vid] = prev


def _empty_totals() -> dict[str, float]:
    return {
        "views": 0.0,
        "estimatedMinutesWatched": 0.0,
        "subscribersGained": 0.0,
        "subscribersLost": 0.0,
        "netSubscribers": 0.0,
        "likes": 0.0,
        "comments": 0.0,
        "shares": 0.0,
        "averageViewDuration": 0.0,
        "videosWithViews": 0,
    }


def _totals_from_channel_rows(rows: list[dict]) -> dict[str, float]:
    totals = _empty_totals()
    if not rows:
        return totals
    # No dimension → one aggregate row; day dimension → sum
    totals["views"] = _sum_metric(rows, "views")
    totals["estimatedMinutesWatched"] = _sum_metric(rows, "estimatedMinutesWatched")
    totals["subscribersGained"] = _sum_metric(rows, "subscribersGained")
    totals["subscribersLost"] = _sum_metric(rows, "subscribersLost")
    totals["netSubscribers"] = totals["subscribersGained"] - totals["subscribersLost"]
    totals["likes"] = _sum_metric(rows, "likes")
    totals["comments"] = _sum_metric(rows, "comments")
    totals["shares"] = _sum_metric(rows, "shares")
    view_sum = totals["views"]
    if view_sum > 0:
        weighted = 0.0
        for row in rows:
            try:
                v = float(row.get("views") or 0)
                d = float(row.get("averageViewDuration") or 0)
            except (TypeError, ValueError):
                continue
            weighted += d * v
        totals["averageViewDuration"] = weighted / view_sum if view_sum else 0.0
    return totals


def _merge_totals(parts: list[dict[str, float]]) -> dict[str, float]:
    merged = _empty_totals()
    view_weight = 0.0
    dur_weight = 0.0
    for part in parts:
        for key in (
            "views",
            "estimatedMinutesWatched",
            "subscribersGained",
            "subscribersLost",
            "likes",
            "comments",
            "shares",
        ):
            merged[key] += float(part.get(key) or 0)
        merged["videosWithViews"] += int(part.get("videosWithViews") or 0)
        v = float(part.get("views") or 0)
        d = float(part.get("averageViewDuration") or 0)
        view_weight += v
        dur_weight += d * v
    merged["netSubscribers"] = merged["subscribersGained"] - merged["subscribersLost"]
    merged["averageViewDuration"] = dur_weight / view_weight if view_weight else 0.0
    return merged


def _pct_change(current: float, previous: float) -> float | None:
    if previous == 0:
        return None if current == 0 else 100.0
    return round(((current - previous) / previous) * 100.0, 1)


def _channel_short(title: str | None, channel_id: str = "") -> str:
    text = (title or channel_id or "Channel").strip()
    if "|" in text:
        return text.split("|")[-1].strip() or text
    return text[:36]


def _build_charts(metrics: dict[str, Any]) -> list[dict[str, Any]]:
    """Build a large positive-leaning chart appendix (target 16–22)."""
    combined = metrics.get("combined") or {}
    cur = combined.get("current") or {}
    prev = combined.get("previous") or {}
    ai = combined.get("ai") or {}
    old = combined.get("old") or {}
    daily = metrics.get("daily") or []
    top_videos = metrics.get("top_videos") or []
    outliers = metrics.get("outliers_100") or []
    channels = metrics.get("channels") or []
    traffic = metrics.get("traffic_sources") or []
    top_by_channel = metrics.get("top_by_channel") or []
    charts: list[dict[str, Any]] = []

    def add(chart_id: str, title: str, chart_type: str, labels: list, datasets: list, **extra):
        charts.append(
            {
                "id": chart_id,
                "title": title,
                "type": chart_type,
                "labels": labels,
                "datasets": datasets,
                **extra,
            }
        )

    add(
        "views_mom",
        "Views — report month vs previous",
        "bar",
        ["Previous month", "Report month"],
        [{"label": "Views", "data": [prev.get("views") or 0, cur.get("views") or 0]}],
    )
    add(
        "watch_mom",
        "Watch time (minutes) — MoM",
        "bar",
        ["Previous month", "Report month"],
        [
            {
                "label": "Minutes watched",
                "data": [
                    prev.get("estimatedMinutesWatched") or 0,
                    cur.get("estimatedMinutesWatched") or 0,
                ],
            }
        ],
    )
    add(
        "subs_net_mom",
        "Net subscribers — MoM",
        "bar",
        ["Previous month", "Report month"],
        [
            {
                "label": "Net subscribers",
                "data": [prev.get("netSubscribers") or 0, cur.get("netSubscribers") or 0],
            }
        ],
    )
    add(
        "likes_mom",
        "Likes — MoM",
        "bar",
        ["Previous month", "Report month"],
        [{"label": "Likes", "data": [prev.get("likes") or 0, cur.get("likes") or 0]}],
    )
    add(
        "shares_mom",
        "Shares — MoM",
        "bar",
        ["Previous month", "Report month"],
        [{"label": "Shares", "data": [prev.get("shares") or 0, cur.get("shares") or 0]}],
    )
    add(
        "videos_with_views_mom",
        "Videos with views — MoM",
        "bar",
        ["Previous month", "Report month"],
        [
            {
                "label": "Videos",
                "data": [prev.get("videosWithViews") or 0, cur.get("videosWithViews") or 0],
            }
        ],
    )

    if daily:
        add(
            "daily_views",
            "Daily views (report month)",
            "line",
            [d["day"] for d in daily],
            [{"label": "Views", "data": [d.get("views") or 0 for d in daily]}],
        )
        add(
            "daily_watch",
            "Daily watch time (report month)",
            "line",
            [d["day"] for d in daily],
            [
                {
                    "label": "Minutes",
                    "data": [d.get("estimatedMinutesWatched") or 0 for d in daily],
                }
            ],
        )
        add(
            "daily_subs",
            "Daily net subscribers (report month)",
            "line",
            [d["day"] for d in daily],
            [
                {
                    "label": "Net subs",
                    "data": [
                        float(d.get("subscribersGained") or 0)
                        - float(d.get("subscribersLost") or 0)
                        for d in daily
                    ],
                }
            ],
        )

    # Only chart AI vs normal when AI wins that metric (never show underperformance)
    ai_compare = metrics.get("ai_compare") or {}
    if ai_compare.get("show_views"):
        add(
            "ai_vs_normal_views",
            "AI videos vs normal videos — views",
            "bar",
            ["AI videos", "Normal videos"],
            [{"label": "Views", "data": [ai.get("views") or 0, old.get("views") or 0]}],
        )
    if ai_compare.get("show_avg"):
        add(
            "ai_vs_normal_avg",
            "AI videos vs normal videos — avg views",
            "bar",
            ["AI videos", "Normal videos"],
            [
                {
                    "label": "Avg views",
                    "data": [ai.get("avgViews") or 0, old.get("avgViews") or 0],
                }
            ],
        )
    if ai_compare.get("show_watch"):
        add(
            "ai_vs_normal_watch",
            "AI videos vs normal videos — watch time",
            "bar",
            ["AI videos", "Normal videos"],
            [
                {
                    "label": "Minutes",
                    "data": [
                        ai.get("estimatedMinutesWatched") or 0,
                        old.get("estimatedMinutesWatched") or 0,
                    ],
                }
            ],
        )

    report_month = metrics.get("report_month") or "report month"
    if top_videos:
        labels = [(v.get("title") or v["id"])[:48] for v in top_videos[:10]]
        add(
            "top_videos",
            f"Top videos — {report_month}",
            "bar",
            labels,
            [{"label": "Views", "data": [v.get("views") or 0 for v in top_videos[:10]]}],
            horizontal=True,
        )

    if channels:
        labels = [_channel_short(c.get("title"), c.get("channel_id", "")) for c in channels]
        add(
            "channel_views",
            "Channel contribution — report-month views",
            "bar",
            labels,
            [
                {
                    "label": "Views",
                    "data": [(c.get("current") or {}).get("views") or 0 for c in channels],
                }
            ],
        )
        add(
            "channel_views_mom",
            "Channel views — previous vs report month",
            "bar",
            labels,
            [
                {
                    "label": "Previous month",
                    "data": [(c.get("previous") or {}).get("views") or 0 for c in channels],
                },
                {
                    "label": "Report month",
                    "data": [(c.get("current") or {}).get("views") or 0 for c in channels],
                },
            ],
        )
        add(
            "channel_watch",
            "Channel watch time — report month",
            "bar",
            labels,
            [
                {
                    "label": "Minutes",
                    "data": [
                        (c.get("current") or {}).get("estimatedMinutesWatched") or 0
                        for c in channels
                    ],
                }
            ],
        )
        add(
            "channel_subs",
            "Channel net subscribers — report month",
            "bar",
            labels,
            [
                {
                    "label": "Net subs",
                    "data": [
                        (c.get("current") or {}).get("netSubscribers") or 0 for c in channels
                    ],
                }
            ],
        )

    if top_by_channel:
        for block in top_by_channel:
            vids = block.get("videos") or []
            if not vids:
                continue
            label = _channel_short(block.get("title"), block.get("channel_id", ""))
            add(
                f"top_{block.get('channel_id')}",
                f"Top videos — {label} ({report_month})",
                "bar",
                [(v.get("title") or v["id"])[:40] for v in vids[:6]],
                [{"label": "Views", "data": [v.get("views") or 0 for v in vids[:6]]}],
                horizontal=True,
            )

    if traffic:
        ordered = sorted(traffic, key=lambda t: float(t.get("views") or 0), reverse=True)
        add(
            "traffic_mix",
            "Traffic source mix (views)",
            "bar",
            [t.get("source") for t in ordered[:8]],
            [{"label": "Views", "data": [t.get("views") or 0 for t in ordered[:8]]}],
            horizontal=True,
        )
        add(
            "traffic_watch",
            "Traffic source mix (watch minutes)",
            "bar",
            [t.get("source") for t in ordered[:8]],
            [
                {
                    "label": "Minutes",
                    "data": [t.get("estimatedMinutesWatched") or 0 for t in ordered[:8]],
                }
            ],
            horizontal=True,
        )

    if outliers:
        add(
            "outliers",
            "100+ view outliers",
            "bar",
            [(v.get("title") or v["id"])[:42] for v in outliers[:10]],
            [{"label": "Views", "data": [v.get("views") or 0 for v in outliers[:10]]}],
            horizontal=True,
        )

    shorts_views = float(combined.get("shortsViews") or 0)
    long_views = float(combined.get("longViews") or 0)
    if shorts_views or long_views:
        add(
            "long_vs_shorts",
            "Long-form vs Shorts views",
            "bar",
            ["Long-form", "Shorts"],
            [{"label": "Views", "data": [long_views, shorts_views]}],
        )

    if (cur.get("subscribersGained") or 0) > 0 or (cur.get("subscribersLost") or 0) > 0:
        add(
            "subs_gained_lost",
            "Subscribers gained vs lost",
            "bar",
            ["Gained", "Lost"],
            [
                {
                    "label": "Subscribers",
                    "data": [
                        cur.get("subscribersGained") or 0,
                        cur.get("subscribersLost") or 0,
                    ],
                }
            ],
        )

    return charts[:22]


def fetch_and_compute_metrics(
    *,
    username: str,
    client_id: str,
    report_month: str,
    ai_videos_started_from: str,
    channel_ids: list[str] | None = None,
) -> dict[str, Any]:
    prev_month = shift_month(report_month, -1)
    cur_start, cur_end = month_bounds(report_month)
    prev_start, prev_end = month_bounds(prev_month)
    ai_from = ai_start_date(ai_videos_started_from)

    channels_meta = list_channels_meta(client_id)
    if channel_ids:
        allow = set(channel_ids)
        channels_meta = [c for c in channels_meta if c.get("id") in allow]
    if not channels_meta:
        raise ValueError("No linked YouTube channels found for this client.")

    # Always refresh catalogs on all linked channels first (titles + AI publish dates).
    sync_video_catalogs_for_report(
        username=username,
        client_id=client_id,
        channels_meta=channels_meta,
    )

    channel_results: list[dict[str, Any]] = []
    combined_daily: dict[str, dict[str, float]] = {}
    combined_traffic: dict[str, dict[str, float]] = {}
    all_videos: list[dict[str, Any]] = []

    for ch in channels_meta:
        channel_id = ch["id"]
        creds = get_user_google_creds(username, client_id, channel_id)
        video_meta = _video_meta_map(client_id, channel_id)

        # Aggregate totals (no dimension)
        cur_h, cur_r = _safe_analytics(
            creds,
            channel_id,
            start_date=cur_start,
            end_date=cur_end,
            metrics=CHANNEL_TOTAL_METRICS,
            dimensions=None,
            sort=None,
        )
        # Fall back to day sum if aggregate query returns nothing
        if not cur_r:
            cur_h, cur_r = _safe_analytics(
                creds,
                channel_id,
                start_date=cur_start,
                end_date=cur_end,
                metrics=CHANNEL_TOTAL_METRICS,
                dimensions="day",
                sort="day",
            )
        prev_h, prev_r = _safe_analytics(
            creds,
            channel_id,
            start_date=prev_start,
            end_date=prev_end,
            metrics=CHANNEL_TOTAL_METRICS,
            dimensions=None,
            sort=None,
        )
        if not prev_r:
            prev_h, prev_r = _safe_analytics(
                creds,
                channel_id,
                start_date=prev_start,
                end_date=prev_end,
                metrics=CHANNEL_TOTAL_METRICS,
                dimensions="day",
                sort="day",
            )

        cur_rows = _rows_to_dicts(cur_h, cur_r)
        prev_rows = _rows_to_dicts(prev_h, prev_r)
        current_totals = _totals_from_channel_rows(cur_rows)
        previous_totals = _totals_from_channel_rows(prev_rows)

        day_h, day_r = _safe_analytics(
            creds,
            channel_id,
            start_date=cur_start,
            end_date=cur_end,
            metrics="views,estimatedMinutesWatched,subscribersGained,subscribersLost",
            dimensions="day",
            sort="day",
        )
        for row in _rows_to_dicts(day_h, day_r):
            day = str(row.get("day") or "")
            bucket = combined_daily.setdefault(
                day,
                {
                    "day": day,
                    "views": 0.0,
                    "estimatedMinutesWatched": 0.0,
                    "subscribersGained": 0.0,
                    "subscribersLost": 0.0,
                },
            )
            for key in (
                "views",
                "estimatedMinutesWatched",
                "subscribersGained",
                "subscribersLost",
            ):
                try:
                    bucket[key] += float(row.get(key) or 0)
                except (TypeError, ValueError):
                    pass

        traf_h, traf_r = _safe_analytics(
            creds,
            channel_id,
            start_date=cur_start,
            end_date=cur_end,
            metrics=TRAFFIC_METRICS,
            dimensions="insightTrafficSourceType",
            sort="-views",
            max_results=25,
        )
        for row in _rows_to_dicts(traf_h, traf_r):
            source_code = str(row.get("insightTrafficSourceType") or "UNKNOWN")
            bucket = combined_traffic.setdefault(
                source_code,
                {
                    "source_code": source_code,
                    "source": traffic_source_label(source_code),
                    "views": 0.0,
                    "estimatedMinutesWatched": 0.0,
                },
            )
            try:
                bucket["views"] += float(row.get("views") or 0)
                bucket["estimatedMinutesWatched"] += float(
                    row.get("estimatedMinutesWatched") or 0
                )
            except (TypeError, ValueError):
                pass

        def _video_rows_for_range(start, end) -> list[dict[str, Any]]:
            vh, vr = _safe_analytics(
                creds,
                channel_id,
                start_date=start,
                end_date=end,
                metrics=VIDEO_METRICS,
                dimensions="video",
                sort="-views",
                max_results=200,
            )
            if not vr:
                # Fallback if averageViewPercentage is unsupported for this query
                fallback = (
                    "views,estimatedMinutesWatched,averageViewDuration,"
                    "subscribersGained,subscribersLost"
                )
                vh, vr = _safe_analytics(
                    creds,
                    channel_id,
                    start_date=start,
                    end_date=end,
                    metrics=fallback,
                    dimensions="video",
                    sort="-views",
                    max_results=200,
                )
            raw_rows = _rows_to_dicts(vh, vr)
            missing_ids = [
                str(row.get("video") or "")
                for row in raw_rows
                if row.get("video")
            ]
            _enrich_missing_video_meta(creds, channel_id, missing_ids, video_meta)

            rows_out: list[dict[str, Any]] = []
            for row in raw_rows:
                vid = str(row.get("video") or "")
                if not vid:
                    continue
                meta = video_meta.get(vid) or {
                    "id": vid,
                    "title": vid,
                    "published_at": None,
                    "is_short": False,
                    "duration_type": "long",
                    "channel_id": channel_id,
                }
                pub = _parse_published(meta.get("published_at"))
                is_ai = bool(pub and pub >= ai_from)
                rows_out.append(
                    {
                        "id": vid,
                        "title": meta.get("title") or vid,
                        "published_at": meta.get("published_at"),
                        "is_short": bool(meta.get("is_short")),
                        "duration_type": meta.get("duration_type") or "long",
                        "channel_id": channel_id,
                        "channel_title": ch.get("title") or channel_id,
                        "is_ai": is_ai,
                        "views": float(row.get("views") or 0),
                        "estimatedMinutesWatched": float(
                            row.get("estimatedMinutesWatched") or 0
                        ),
                        "averageViewDuration": float(row.get("averageViewDuration") or 0),
                        "averageViewPercentage": float(
                            row.get("averageViewPercentage") or 0
                        ),
                        "subscribersGained": float(row.get("subscribersGained") or 0),
                        "subscribersLost": float(row.get("subscribersLost") or 0),
                    }
                )
            return rows_out

        video_rows = _video_rows_for_range(cur_start, cur_end)
        prev_video_rows = _video_rows_for_range(prev_start, prev_end)
        all_videos.extend(video_rows)

        current_totals["videosWithViews"] = sum(
            1 for v in video_rows if (v.get("views") or 0) > 0
        )
        previous_totals["videosWithViews"] = sum(
            1 for v in prev_video_rows if (v.get("views") or 0) > 0
        )

        channel_results.append(
            {
                "channel_id": channel_id,
                "title": ch.get("title") or channel_id,
                "current": current_totals,
                "previous": previous_totals,
                "videos": video_rows,
                "previous_videos": prev_video_rows,
            }
        )

    combined_current = _merge_totals([c["current"] for c in channel_results])
    combined_previous = _merge_totals([c["previous"] for c in channel_results])

    ai_videos = [v for v in all_videos if v.get("is_ai")]
    old_videos = [v for v in all_videos if not v.get("is_ai")]

    def group_stats(videos: list[dict]) -> dict[str, float]:
        views = sum(float(v.get("views") or 0) for v in videos)
        watch = sum(float(v.get("estimatedMinutesWatched") or 0) for v in videos)
        count = len(videos)
        return {
            "videoCount": count,
            "views": views,
            "estimatedMinutesWatched": watch,
            "avgViews": (views / count) if count else 0.0,
            "subscribersGained": sum(float(v.get("subscribersGained") or 0) for v in videos),
            "subscribersLost": sum(float(v.get("subscribersLost") or 0) for v in videos),
        }

    ai_stats = group_stats(ai_videos)
    old_stats = group_stats(old_videos)
    top_videos = sorted(all_videos, key=lambda v: float(v.get("views") or 0), reverse=True)[:15]
    outliers = [
        v
        for v in sorted(all_videos, key=lambda x: float(x.get("views") or 0), reverse=True)
        if float(v.get("views") or 0) >= 100
    ][:15]
    top_by_channel = []
    for ch in channel_results:
        vids = sorted(
            ch.get("videos") or [],
            key=lambda v: float(v.get("views") or 0),
            reverse=True,
        )[:8]
        top_by_channel.append(
            {
                "channel_id": ch.get("channel_id"),
                "title": ch.get("title"),
                "videos": vids,
                "current": ch.get("current"),
                "previous": ch.get("previous"),
            }
        )

    # High retention: meaningful views + strong average view % (skip if none qualify)
    high_retention = []
    for v in all_videos:
        views = float(v.get("views") or 0)
        pct = float(v.get("averageViewPercentage") or 0)
        if views < 100 or pct < 40:
            continue
        high_retention.append(
            {
                "id": v.get("id"),
                "title": v.get("title"),
                "channel_title": v.get("channel_title"),
                "views": views,
                "averageViewPercentage": round(pct, 1),
                "averageViewDuration": float(v.get("averageViewDuration") or 0),
                "is_short": bool(v.get("is_short")),
            }
        )
    high_retention.sort(
        key=lambda x: (float(x.get("averageViewPercentage") or 0), float(x.get("views") or 0)),
        reverse=True,
    )
    high_retention = high_retention[:8]
    top_ai = next((v for v in top_videos if v.get("is_ai")), None)
    top_overall = top_videos[0] if top_videos else None
    top_long = next(
        (v for v in top_videos if (v.get("duration_type") or "long") != "short"),
        None,
    )
    top_long_ai = next(
        (
            v
            for v in top_videos
            if v.get("is_ai") and (v.get("duration_type") or "long") != "short"
        ),
        None,
    )

    traffic_list = sorted(
        combined_traffic.values(), key=lambda t: float(t.get("views") or 0), reverse=True
    )
    suggested = next(
        (
            t
            for t in traffic_list
            if str(t.get("source_code", "")).upper() == "RELATED_VIDEO"
            or "suggested" in str(t.get("source", "")).lower()
        ),
        None,
    )
    browse = next(
        (
            t
            for t in traffic_list
            if str(t.get("source_code", "")).upper() == "SUBSCRIBER"
            or "browse" in str(t.get("source", "")).lower()
        ),
        None,
    )

    daily_list = [combined_daily[k] for k in sorted(combined_daily.keys())]

    ai_views = float(ai_stats.get("views") or 0)
    old_views = float(old_stats.get("views") or 0)
    ai_avg = float(ai_stats.get("avgViews") or 0)
    old_avg = float(old_stats.get("avgViews") or 0)
    ai_watch = float(ai_stats.get("estimatedMinutesWatched") or 0)
    old_watch = float(old_stats.get("estimatedMinutesWatched") or 0)
    # Bias: only surface AI-vs-normal stats where AI wins; hide underperformance
    ai_compare = {
        "show_views": ai_views > old_views,
        "show_avg": ai_avg > old_avg,
        "show_watch": ai_watch > old_watch,
    }
    ai_compare["show_section"] = bool(
        ai_compare["show_views"] or ai_compare["show_avg"] or ai_compare["show_watch"]
    )

    # Positive-only AI angles for the LLM (used when head-to-head totals are weak)
    ai_ranked = sorted(ai_videos, key=lambda v: float(v.get("views") or 0), reverse=True)
    top_ai_videos = ai_ranked[:6]
    ai_outliers = [v for v in ai_ranked if float(v.get("views") or 0) >= 100][:8]
    ai_retention = [
        v
        for v in high_retention
        if any(a.get("id") == v.get("id") for a in ai_videos)
    ][:5]
    best_ai = top_ai_videos[0] if top_ai_videos else None
    best_ai_rank = None
    if best_ai:
        for idx, v in enumerate(top_videos):
            if v.get("id") == best_ai.get("id"):
                best_ai_rank = idx + 1
                break
    ai_in_top10 = sum(1 for v in top_videos[:10] if v.get("is_ai"))
    ai_subs = float(ai_stats.get("subscribersGained") or 0)

    positive_signals: list[str] = []
    if best_ai and float(best_ai.get("views") or 0) > 0:
        rank_bit = f", rank #{best_ai_rank} overall" if best_ai_rank else ""
        positive_signals.append(
            f"Top AI video “{best_ai.get('title')}” earned "
            f"{int(float(best_ai.get('views') or 0)):,} views{rank_bit}."
        )
    if ai_outliers:
        positive_signals.append(
            f"{len(ai_outliers)} AI video(s) cleared 100+ views this month."
        )
    if ai_in_top10:
        positive_signals.append(f"{ai_in_top10} AI video(s) appear in the month’s top 10.")
    if ai_subs > 0:
        positive_signals.append(
            f"AI videos contributed {int(ai_subs):,} subscribers gained."
        )
    if ai_retention:
        positive_signals.append(
            f"{len(ai_retention)} AI video(s) show high average % viewed."
        )
    if ai_compare["show_views"]:
        positive_signals.append("AI catalog beat normal videos on total views.")
    if ai_compare["show_avg"]:
        positive_signals.append("AI catalog beat normal videos on average views per video.")
    if ai_compare["show_watch"]:
        positive_signals.append("AI catalog beat normal videos on watch time.")
    if float(ai_stats.get("views") or 0) > 0:
        positive_signals.append(
            f"AI videos delivered {int(ai_views):,} views and "
            f"{int(ai_watch):,} watch minutes in the report month."
        )

    ai_highlights = {
        "top_ai_videos": top_ai_videos,
        "ai_outliers_100": ai_outliers,
        "ai_high_retention": ai_retention,
        "best_ai_rank": best_ai_rank,
        "ai_in_top10": ai_in_top10,
        "ai_totals": {
            "videoCount": ai_stats.get("videoCount") or 0,
            "views": ai_views,
            "estimatedMinutesWatched": ai_watch,
            "avgViews": ai_avg,
            "subscribersGained": ai_subs,
        },
        "positive_signals": positive_signals,
        "has_positive_ai_story": bool(positive_signals),
    }

    metrics: dict[str, Any] = {
        "report_month": report_month,
        "previous_month": prev_month,
        "ai_videos_started_from": ai_videos_started_from,
        "date_ranges": {
            "current": {"start": cur_start.isoformat(), "end": cur_end.isoformat()},
            "previous": {"start": prev_start.isoformat(), "end": prev_end.isoformat()},
        },
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "channels": channel_results,
        "combined": {
            "current": combined_current,
            "previous": combined_previous,
            "ai": ai_stats,
            "old": old_stats,
            "shortsViews": sum(
                float(v.get("views") or 0) for v in all_videos if v.get("is_short")
            ),
            "longViews": sum(
                float(v.get("views") or 0) for v in all_videos if not v.get("is_short")
            ),
            "mom": {
                "views_pct": _pct_change(
                    float(combined_current.get("views") or 0),
                    float(combined_previous.get("views") or 0),
                ),
                "watch_pct": _pct_change(
                    float(combined_current.get("estimatedMinutesWatched") or 0),
                    float(combined_previous.get("estimatedMinutesWatched") or 0),
                ),
                "net_subs_pct": _pct_change(
                    float(combined_current.get("netSubscribers") or 0),
                    float(combined_previous.get("netSubscribers") or 0),
                ),
            },
        },
        "daily": daily_list,
        "traffic_sources": traffic_list,
        "suggested_traffic": suggested,
        "browse_traffic": browse if browse and float(browse.get("views") or 0) > 0 else None,
        "top_videos": top_videos,
        "top_by_channel": top_by_channel,
        "outliers_100": outliers,
        "high_retention_videos": high_retention,
        "ai_compare": ai_compare,
        "ai_highlights": ai_highlights,
        "flags": {
            "ai_is_top_video": bool(
                top_overall and top_ai and top_overall.get("id") == top_ai.get("id")
            ),
            "ai_is_top_long": bool(
                top_long and top_long_ai and top_long.get("id") == top_long_ai.get("id")
            ),
            "ai_beats_old_views": ai_compare["show_views"],
            "ai_beats_old_avg": ai_compare["show_avg"],
            "ai_beats_old_watch": ai_compare["show_watch"],
            "show_ai_vs_normal": ai_compare["show_section"],
            "has_positive_ai_story": bool(positive_signals),
            "has_high_retention": bool(high_retention),
        },
        "all_videos": all_videos,
    }
    metrics["charts"] = _build_charts(metrics)
    return metrics


def metrics_summary_for_api(metrics: dict[str, Any] | None) -> dict[str, Any] | None:
    if not metrics:
        return None
    combined = metrics.get("combined") or {}
    return {
        "report_month": metrics.get("report_month"),
        "previous_month": metrics.get("previous_month"),
        "date_ranges": metrics.get("date_ranges"),
        "current": combined.get("current"),
        "previous": combined.get("previous"),
        "ai": combined.get("ai"),
        "old": combined.get("old"),
        "mom": combined.get("mom"),
        "flags": metrics.get("flags"),
        "top_videos": (metrics.get("top_videos") or [])[:5],
        "chart_count": len(metrics.get("charts") or []),
        "channel_count": len(metrics.get("channels") or []),
        "fetched_at": metrics.get("fetched_at"),
    }
