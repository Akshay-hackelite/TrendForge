"""HTML + Playwright PDF rendering for monthly reports."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
REPORTS_DIR = Path(__file__).resolve().parent.parent.parent / "reports"


def _safe_report_id(report_id: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "_", report_id)


def report_metrics_path(report_id: str) -> Path:
    """Local filesystem cache for fetched/computed YouTube metrics (not stored in DB)."""
    return REPORTS_DIR / f"{_safe_report_id(report_id)}.metrics.json"


def save_metrics_cache(report_id: str, metrics: dict[str, Any]) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = report_metrics_path(report_id)
    path.write_text(json.dumps(metrics, ensure_ascii=False), encoding="utf-8")
    return path


def load_metrics_cache(report_id: str) -> dict[str, Any] | None:
    path = report_metrics_path(report_id)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) and data else None


def has_metrics_cache(report_id: str) -> bool:
    return report_metrics_path(report_id).is_file()


def _fmt_int(value: Any) -> str:
    try:
        return f"{int(round(float(value or 0))):,}"
    except (TypeError, ValueError):
        return "0"


def _fmt_signed(value: Any) -> str:
    try:
        n = int(round(float(value or 0)))
    except (TypeError, ValueError):
        n = 0
    return f"+{n:,}" if n > 0 else f"{n:,}"


def _fmt_pct(value: Any) -> str:
    if value is None:
        return "—"
    try:
        n = float(value)
    except (TypeError, ValueError):
        return "—"
    sign = "+" if n > 0 else ""
    return f"{sign}{n:.1f}%"


def _month_label(yyyy_mm: str | None) -> str:
    if not yyyy_mm:
        return "—"
    try:
        year, month = yyyy_mm.split("-")
        names = [
            "",
            "January",
            "February",
            "March",
            "April",
            "May",
            "June",
            "July",
            "August",
            "September",
            "October",
            "November",
            "December",
        ]
        return f"{names[int(month)]} {year}"
    except (ValueError, IndexError):
        return yyyy_mm


def render_report_html(
    *,
    client_name: str,
    metrics: dict[str, Any],
    narrative: dict[str, Any],
    presentation: dict[str, Any] | None = None,
) -> str:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
    )
    env.globals["fmt_int"] = _fmt_int
    env.globals["fmt_signed"] = _fmt_signed
    env.globals["fmt_pct"] = _fmt_pct
    template = env.get_template("monthly_report.html")

    combined = metrics.get("combined") or {}
    current = combined.get("current") or {}
    previous = combined.get("previous") or {}
    ai = combined.get("ai") or {}
    old = combined.get("old") or {}
    mom = combined.get("mom") or {}
    ranges = metrics.get("date_ranges") or {}
    cur_range = ranges.get("current") or {}
    date_range_current = f"{cur_range.get('start', '')} → {cur_range.get('end', '')}"

    safe_narrative = {
        "executive_summary": narrative.get("executive_summary") or "",
        "strong_callout": narrative.get("strong_callout") or "",
        "milestone_note": narrative.get("milestone_note"),
        "ai_vs_old_story": narrative.get("ai_vs_old_story"),
        "organic_traffic_story": narrative.get("organic_traffic_story") or "",
        "subscriber_story": narrative.get("subscriber_story") or "",
        "channel_snapshot_blurb": narrative.get("channel_snapshot_blurb") or "",
        "previous_month_blurb": narrative.get("previous_month_blurb"),
        "retention_story": narrative.get("retention_story"),
    }

    ai_compare = metrics.get("ai_compare") or {
        "show_section": False,
        "show_views": False,
        "show_avg": False,
        "show_watch": False,
    }
    pres = presentation or {
        "show_mom_views_delta": True,
        "show_mom_watch_delta": True,
        "show_mom_subs_delta": True,
        "show_previous_month_section": True,
        "show_ai_section": True,
        "show_ai_vs_normal_table": bool(ai_compare.get("show_section")),
        "credit_top_overall_video": True,
        "suppress_chart_ids": [],
    }
    suppress = set(pres.get("suppress_chart_ids") or [])
    charts = [c for c in (metrics.get("charts") or []) if c.get("id") not in suppress]
    top_videos_all = metrics.get("top_videos") or []
    top_overall_video = top_videos_all[0] if top_videos_all else None

    return template.render(
        client_name=client_name,
        report_month_label=_month_label(metrics.get("report_month")),
        previous_month_label=_month_label(metrics.get("previous_month")),
        ai_start_label=_month_label(metrics.get("ai_videos_started_from")),
        date_range_current=date_range_current,
        channel_count=len(metrics.get("channels") or []),
        current=current,
        previous=previous,
        ai=ai,
        old=old,
        mom=mom,
        presentation=pres,
        ai_compare=ai_compare,
        channels=metrics.get("channels") or [],
        top_videos=top_videos_all[:12],
        top_overall_video=top_overall_video,
        top_ai_videos=((metrics.get("ai_highlights") or {}).get("top_ai_videos") or [])[:6],
        top_by_channel=metrics.get("top_by_channel") or [],
        high_retention_videos=metrics.get("high_retention_videos") or [],
        traffic_sources=metrics.get("traffic_sources") or [],
        narrative=safe_narrative,
        charts_json=json.dumps(charts),
    )


def export_html_to_pdf(html: str, pdf_path: Path) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    pdf_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "playwright is not installed. Run: pip install playwright && playwright install chromium"
        ) from exc

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.set_content(html, wait_until="networkidle")
        page.wait_for_function("window.__CHARTS_READY__ === true", timeout=30000)
        # Allow Chart.js paint
        page.wait_for_timeout(500)
        page.pdf(
            path=str(pdf_path),
            format="A4",
            print_background=True,
            margin={"top": "16mm", "bottom": "16mm", "left": "12mm", "right": "12mm"},
        )
        browser.close()
    return pdf_path


def report_pdf_path(report_id: str) -> Path:
    return REPORTS_DIR / f"{_safe_report_id(report_id)}.pdf"
