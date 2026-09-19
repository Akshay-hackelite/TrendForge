"""Prompts for monthly YouTube AI performance reports."""

from __future__ import annotations

import json
from typing import Any

NARRATIVE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "executive_summary": {"type": "string"},
        "strong_callout": {"type": "string"},
        "milestone_note": {"type": ["string", "null"]},
        "ai_vs_old_story": {"type": ["string", "null"]},
        "organic_traffic_story": {"type": "string"},
        "subscriber_story": {"type": "string"},
        "channel_snapshot_blurb": {"type": "string"},
        "previous_month_blurb": {"type": "string"},
        "retention_story": {"type": ["string", "null"]},
        "what_to_downplay": {"type": "string"},
    },
    "required": [
        "executive_summary",
        "strong_callout",
        "milestone_note",
        "ai_vs_old_story",
        "organic_traffic_story",
        "subscriber_story",
        "channel_snapshot_blurb",
        "previous_month_blurb",
        "retention_story",
        "what_to_downplay",
    ],
}

SYSTEM_GENERATE = """You write client-ready monthly YouTube performance reports for creator / client channels.
You receive grounded metrics JSON only — never invent numbers, video titles, or traffic sources.

Tone: analytical, persuasive, commercially useful. Lead with the strongest defensible wins.
Primary bias: make AI videos look strong. NEVER say AI videos underperformed vs normal/earlier videos.
Never invent a head-to-head win that flags/ai_compare do not support.

## AI story field (`ai_vs_old_story`) — ALWAYS try to fill this when ai_highlights.has_positive_ai_story is true
This section is the AI narrative. It is NOT only for AI-vs-normal totals.

If flags.show_ai_vs_normal is true:
- You may praise only the winning metrics in ai_compare (show_views / show_avg / show_watch).
- Still lead with specific AI video wins from ai_highlights.

If flags.show_ai_vs_normal is false:
- Do NOT compare AI totals against normal/earlier catalog totals at all.
- Still write a strong ai_vs_old_story using OTHER positive AI evidence from ai_highlights.positive_signals and ai_highlights.top_ai_videos, such as:
  - best AI video views / rank in the month
  - AI videos in the top 10
  - AI 100+ view outliers
  - AI subscriber contribution
  - AI high-retention titles
  - absolute AI views / watch minutes for the month (as a positive delivery number, not vs normal)
- Frame as momentum, breakout AI titles, proof the AI workflow is producing results — without mentioning that older catalog beat AI.

If ai_highlights.has_positive_ai_story is false (no AI views/signals), set ai_vs_old_story to null.

Also weave the best AI angle into executive_summary and strong_callout when possible.

## Traffic naming
Use human source names from metrics (Suggested videos, YouTube search, Browse features). Never raw codes like RELATED_VIDEO.

## Highlight priority (only if data supports it)
1) Biggest month-over-month growth
2) An AI video became top / high-ranked video
3) AI videos beat normal videos (ONLY when show_ai_vs_normal)
4) Other positive AI signals from ai_highlights (outliers, top-10 presence, subs, retention)
5) Strong Suggested videos / organic traffic
6) Combined multi-channel totals — name EVERY linked channel with exact views
7) Subscriber growth
8) High retention — ONLY if high_retention_videos non-empty; else retention_story = null

Do NOT headline weak retention, zero Browse features, sparse keywords, or soft metrics.
If Browse features is zero/null, do not mention Browse.
Use exact date ranges from metrics.date_ranges.
what_to_downplay is internal (not shown to client).
Keep sections concise (2–5 sentences). milestone_note / ai_vs_old_story / retention_story may be null.
"""

SYSTEM_REFINE = """You refine an existing monthly YouTube report narrative.
You receive: cached metrics JSON, prior narrative, and a user refinement prompt.
Never invent numbers. Stay persuasive and client-ready. Keep the same JSON keys.

Bias for AI videos:
- Never claim AI underperformed vs normal videos.
- If show_ai_vs_normal is false, do not compare AI vs normal totals; still write ai_vs_old_story from ai_highlights positive signals when available.
- If show_ai_vs_normal is true, only praise winning ai_compare metrics.
Use human traffic source names. Keep every channel named in channel_snapshot_blurb.
retention_story null unless high_retention_videos has items.
what_to_downplay remains internal.
"""


def build_generate_messages(
    *,
    client_name: str,
    metrics: dict[str, Any],
) -> list[dict[str, str]]:
    compact = _compact_metrics(metrics)
    user = (
        f"Creator / client: {client_name}\n"
        f"Report month: {metrics.get('report_month')}\n"
        f"Previous month: {metrics.get('previous_month')}\n"
        f"AI videos started from: {metrics.get('ai_videos_started_from')}\n"
        f"Channels: combine all linked channels.\n"
        f"IMPORTANT: Prioritize a strong AI-video story using ai_highlights. "
        f"If AI-vs-normal totals are not shown, find other positive AI data instead.\n\n"
        f"METRICS JSON:\n{json.dumps(compact, ensure_ascii=False)}"
    )
    return [
        {"role": "system", "content": SYSTEM_GENERATE},
        {"role": "user", "content": user},
    ]


POLISH_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "executive_summary": {"type": "string"},
        "strong_callout": {"type": "string"},
        "milestone_note": {"type": ["string", "null"]},
        "ai_vs_old_story": {"type": ["string", "null"]},
        "organic_traffic_story": {"type": "string"},
        "subscriber_story": {"type": "string"},
        "channel_snapshot_blurb": {"type": "string"},
        "previous_month_blurb": {"type": ["string", "null"]},
        "retention_story": {"type": ["string", "null"]},
        "what_to_downplay": {"type": "string"},
        "presentation": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "show_mom_views_delta": {"type": "boolean"},
                "show_mom_watch_delta": {"type": "boolean"},
                "show_mom_subs_delta": {"type": "boolean"},
                "show_previous_month_section": {"type": "boolean"},
                "show_ai_section": {"type": "boolean"},
                "show_ai_vs_normal_table": {"type": "boolean"},
                "credit_top_overall_video": {"type": "boolean"},
                "suppress_chart_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "editor_notes": {"type": "string"},
            },
            "required": [
                "show_mom_views_delta",
                "show_mom_watch_delta",
                "show_mom_subs_delta",
                "show_previous_month_section",
                "show_ai_section",
                "show_ai_vs_normal_table",
                "credit_top_overall_video",
                "suppress_chart_ids",
                "editor_notes",
            ],
        },
    },
    "required": [
        "executive_summary",
        "strong_callout",
        "milestone_note",
        "ai_vs_old_story",
        "organic_traffic_story",
        "subscriber_story",
        "channel_snapshot_blurb",
        "previous_month_blurb",
        "retention_story",
        "what_to_downplay",
        "presentation",
    ],
}

SYSTEM_POLISH = """You are the second-pass editor for a monthly YouTube creator / client report.
You receive: (1) raw metrics JSON from YouTube, (2) a first-draft narrative.

Your job is a smart bias pass — not fabrication:
1) Suppress weak MoM storylines: if a metric fell vs previous month, hide that delta and avoid leading with the decline. You may keep absolute report-month totals.
2) Where normal/earlier videos beat AI on totals, REMOVE AI-vs-normal comparison framing and the comparison table (show_ai_vs_normal_table=false). Still keep a positive AI section using ai_highlights (outliers, rank, retention, absolute AI delivery).
3) Give fair credit to standout normal videos as absolute winners (e.g. “X was the month’s top video”) WITHOUT saying they beat AI / AI lagged.
4) Prefer Suggested videos / organic wins, multi-channel totals, subscriber wins, AI outliers.
5) You may hide/soften sections via presentation flags and suppress_chart_ids (use chart ids from metrics.charts when present).
6) Never invent numbers or titles. Never claim AI beat normal unless flags/ai_compare say so.
7) Bias should be soft: normal catalog can still get credit; AI should look constructive without erasing the rest of the channel.

Set previous_month_blurb to null if the MoM story is mostly declines and you hide the section.
Set show_ai_section true whenever ai_highlights.has_positive_ai_story is true.
editor_notes is internal (what you hid/changed).
"""


def build_polish_messages(
    *,
    client_name: str,
    metrics: dict[str, Any],
    base_narrative: dict[str, Any],
) -> list[dict[str, str]]:
    compact = _compact_metrics(metrics)
    chart_ids = [c.get("id") for c in (metrics.get("charts") or []) if c.get("id")]
    user = (
        f"Creator / client: {client_name}\n"
        f"Report month: {metrics.get('report_month')}\n"
        f"Previous month: {metrics.get('previous_month')}\n"
        f"AI videos started from: {metrics.get('ai_videos_started_from')}\n"
        f"Available chart ids: {json.dumps(chart_ids)}\n\n"
        f"FIRST-DRAFT NARRATIVE JSON:\n{json.dumps(base_narrative or {}, ensure_ascii=False)}\n\n"
        f"RAW METRICS JSON:\n{json.dumps(compact, ensure_ascii=False)}\n\n"
        "Rewrite the narrative and set presentation flags for the final client PDF."
    )
    return [
        {"role": "system", "content": SYSTEM_POLISH},
        {"role": "user", "content": user},
    ]


def build_refine_messages(
    *,
    client_name: str,
    metrics: dict[str, Any],
    prior_narrative: dict[str, Any] | None,
    refine_prompt: str,
) -> list[dict[str, str]]:
    compact = _compact_metrics(metrics)
    user = (
        f"Creator / client: {client_name}\n"
        f"Report month: {metrics.get('report_month')}\n"
        f"Previous month: {metrics.get('previous_month')}\n"
        f"AI videos started from: {metrics.get('ai_videos_started_from')}\n\n"
        f"USER REFINEMENT PROMPT:\n{refine_prompt.strip()}\n\n"
        f"PRIOR NARRATIVE JSON:\n{json.dumps(prior_narrative or {}, ensure_ascii=False)}\n\n"
        f"CACHED METRICS JSON:\n{json.dumps(compact, ensure_ascii=False)}"
    )
    return [
        {"role": "system", "content": SYSTEM_REFINE},
        {"role": "user", "content": user},
    ]


def _compact_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    """Shrink payload for the LLM while keeping decision-critical facts.

    When AI loses the head-to-head, omit normal/old totals so the model cannot
    narrate underperformance — keep AI absolute totals + ai_highlights instead.
    """
    channels = []
    for ch in metrics.get("channels") or []:
        channels.append(
            {
                "channel_id": ch.get("channel_id"),
                "title": ch.get("title"),
                "current": ch.get("current"),
                "previous": ch.get("previous"),
                "top_videos": (ch.get("videos") or [])[:8],
                "previous_top_videos": (ch.get("previous_videos") or [])[:5],
            }
        )

    combined = dict(metrics.get("combined") or {})
    flags = metrics.get("flags") or {}
    ai_compare = metrics.get("ai_compare") or {}
    if not flags.get("show_ai_vs_normal") and not ai_compare.get("show_section"):
        # Hide losing baseline from the model; keep AI absolute delivery numbers
        combined = {
            "current": combined.get("current"),
            "previous": combined.get("previous"),
            "ai": combined.get("ai"),
            "mom": combined.get("mom"),
            "shortsViews": combined.get("shortsViews"),
            "longViews": combined.get("longViews"),
        }

    return {
        "report_month": metrics.get("report_month"),
        "previous_month": metrics.get("previous_month"),
        "ai_videos_started_from": metrics.get("ai_videos_started_from"),
        "date_ranges": metrics.get("date_ranges"),
        "combined": combined,
        "channels": channels,
        "traffic_sources": (metrics.get("traffic_sources") or [])[:12],
        "suggested_traffic": metrics.get("suggested_traffic"),
        "browse_traffic": metrics.get("browse_traffic"),
        "top_videos": (metrics.get("top_videos") or [])[:12],
        "outliers_100": (metrics.get("outliers_100") or [])[:12],
        "high_retention_videos": metrics.get("high_retention_videos") or [],
        "ai_compare": ai_compare,
        "ai_highlights": metrics.get("ai_highlights") or {},
        "flags": flags,
        "daily_sample": (metrics.get("daily") or [])[
            :: max(1, len(metrics.get("daily") or []) // 10 or 1)
        ][:12],
    }
