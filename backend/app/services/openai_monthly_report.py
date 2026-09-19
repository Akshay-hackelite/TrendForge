"""OpenAI helpers for monthly report narrative generate + refine + polish."""

from __future__ import annotations

from typing import Any

from app.prompts.monthly_report import (
    NARRATIVE_SCHEMA,
    POLISH_SCHEMA,
    build_generate_messages,
    build_polish_messages,
    build_refine_messages,
)
from app.services.openai_content_plan import _call_openai

_NARRATIVE_KEYS = (
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
)


def generate_report_narrative(
    *,
    client_name: str,
    metrics: dict[str, Any],
) -> dict[str, Any]:
    messages = build_generate_messages(client_name=client_name, metrics=metrics)
    return _call_openai(
        messages=messages,
        schema=NARRATIVE_SCHEMA,
        schema_name="monthly_report_narrative",
        effort="low",
        stage="monthly-report-generate",
        timeout=180.0,
    )


def refine_report_narrative(
    *,
    client_name: str,
    metrics: dict[str, Any],
    prior_narrative: dict[str, Any] | None,
    refine_prompt: str,
) -> dict[str, Any]:
    messages = build_refine_messages(
        client_name=client_name,
        metrics=metrics,
        prior_narrative=prior_narrative,
        refine_prompt=refine_prompt,
    )
    return _call_openai(
        messages=messages,
        schema=NARRATIVE_SCHEMA,
        schema_name="monthly_report_narrative_refine",
        effort="low",
        stage="monthly-report-refine",
        timeout=180.0,
    )


def polish_report_narrative(
    *,
    client_name: str,
    metrics: dict[str, Any],
    base_narrative: dict[str, Any],
) -> dict[str, Any]:
    """Second AI pass: bias editor over draft + raw metrics."""
    messages = build_polish_messages(
        client_name=client_name,
        metrics=metrics,
        base_narrative=base_narrative,
    )
    return _call_openai(
        messages=messages,
        schema=POLISH_SCHEMA,
        schema_name="monthly_report_polish",
        effort="low",
        stage="monthly-report-polish",
        timeout=180.0,
    )


def split_polish_result(polished: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    narrative = {k: polished.get(k) for k in _NARRATIVE_KEYS}
    presentation = polished.get("presentation") if isinstance(polished.get("presentation"), dict) else {}
    return narrative, presentation


def apply_presentation_guards(
    metrics: dict[str, Any],
    presentation: dict[str, Any] | None,
) -> dict[str, Any]:
    """Hard server-side rules the model cannot override."""
    mom = ((metrics.get("combined") or {}).get("mom")) or {}
    ai_compare = metrics.get("ai_compare") or {}
    ai_highlights = metrics.get("ai_highlights") or {}
    pres = dict(presentation or {})

    def _neg(key: str) -> bool:
        val = mom.get(key)
        try:
            return val is not None and float(val) < 0
        except (TypeError, ValueError):
            return False

    if _neg("views_pct"):
        pres["show_mom_views_delta"] = False
    if _neg("watch_pct"):
        pres["show_mom_watch_delta"] = False
    if _neg("net_subs_pct"):
        pres["show_mom_subs_delta"] = False

    # If all core MoM deltas are hidden/negative, prefer hiding the MoM section
    if (
        not pres.get("show_mom_views_delta", True)
        and not pres.get("show_mom_watch_delta", True)
        and not pres.get("show_mom_subs_delta", True)
    ):
        # Keep section only if model explicitly wants it and at least one absolute compare is useful
        if "show_previous_month_section" not in pres:
            pres["show_previous_month_section"] = False

    if not ai_compare.get("show_section"):
        pres["show_ai_vs_normal_table"] = False

    if ai_highlights.get("has_positive_ai_story"):
        pres.setdefault("show_ai_section", True)
    elif not ai_highlights.get("top_ai_videos"):
        pres["show_ai_section"] = False

    suppress = set(pres.get("suppress_chart_ids") or [])
    if not pres.get("show_mom_views_delta", True):
        suppress.add("views_mom")
    if not pres.get("show_mom_watch_delta", True):
        suppress.add("watch_mom")
    if not pres.get("show_mom_subs_delta", True):
        suppress.update({"subs_net_mom", "subs_gained_lost"})
    if not ai_compare.get("show_views"):
        suppress.add("ai_vs_normal_views")
    if not ai_compare.get("show_avg"):
        suppress.add("ai_vs_normal_avg")
    if not ai_compare.get("show_watch"):
        suppress.add("ai_vs_normal_watch")
    if not ai_compare.get("show_section"):
        suppress.update({"ai_vs_normal_views", "ai_vs_normal_avg", "ai_vs_normal_watch"})

    # Default credit for top overall video (normal or AI)
    if "credit_top_overall_video" not in pres:
        pres["credit_top_overall_video"] = True

    for key, default in (
        ("show_mom_views_delta", True),
        ("show_mom_watch_delta", True),
        ("show_mom_subs_delta", True),
        ("show_previous_month_section", True),
        ("show_ai_section", True),
        ("show_ai_vs_normal_table", bool(ai_compare.get("show_section"))),
        ("credit_top_overall_video", True),
    ):
        if key not in pres:
            pres[key] = default

    # Re-apply hard negatives after defaults
    if _neg("views_pct"):
        pres["show_mom_views_delta"] = False
        suppress.add("views_mom")
    if _neg("watch_pct"):
        pres["show_mom_watch_delta"] = False
        suppress.add("watch_mom")
    if _neg("net_subs_pct"):
        pres["show_mom_subs_delta"] = False
        suppress.update({"subs_net_mom", "subs_gained_lost"})
    if not ai_compare.get("show_section"):
        pres["show_ai_vs_normal_table"] = False

    pres["suppress_chart_ids"] = sorted(suppress)
    return pres
