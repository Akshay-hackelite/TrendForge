"""Orchestrate monthly report generate / refine / persist."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status

from app.database import (
    fetch_client_doc,
    fetch_monthly_report,
    fetch_monthly_report_by_month,
    list_channels_meta,
    list_monthly_reports,
    update_client_fields,
    update_monthly_report_fields,
    upsert_monthly_report,
)
from app.services.monthly_report_metrics import (
    fetch_and_compute_metrics,
    metrics_summary_for_api,
    previous_calendar_month,
)
from app.services.monthly_report_render import (
    export_html_to_pdf,
    has_metrics_cache,
    load_metrics_cache,
    render_report_html,
    report_pdf_path,
    save_metrics_cache,
)
from app.services.gcs_storage import upload_file
from app.services.openai_monthly_report import (
    apply_presentation_guards,
    generate_report_narrative,
    polish_report_narrative,
    refine_report_narrative,
    split_polish_result,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _validate_month(yyyy_mm: str) -> str:
    cleaned = (yyyy_mm or "").strip()
    if not re.fullmatch(r"\d{4}-\d{2}", cleaned):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="report_month must be YYYY-MM.",
        )
    month = int(cleaned.split("-")[1])
    if month < 1 or month > 12:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="report_month month must be 01–12.",
        )
    return cleaned


def ensure_client(username: str, client_id: str) -> dict:
    client = fetch_client_doc(client_id, username=username)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    return client


def list_reports(username: str, client_id: str) -> list[dict]:
    ensure_client(username, client_id)
    return list_monthly_reports(client_id, username=username)


def get_report(username: str, report_id: str) -> dict:
    report = fetch_monthly_report(report_id, username=username)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return report


def _resolve_metrics(report: dict) -> dict[str, Any] | None:
    """Load metrics from local file. Migrate legacy DB blob to disk once if present."""
    report_id = report["id"]
    cached = load_metrics_cache(report_id)
    if cached:
        return cached
    legacy = report.get("metrics")
    if isinstance(legacy, dict) and legacy:
        save_metrics_cache(report_id, legacy)
        update_monthly_report_fields(report_id, {}, unset=["metrics"])
        return legacy
    return None


def _public_detail(report: dict) -> dict:
    metrics = _resolve_metrics(report) or {}
    return {
        "id": report["id"],
        "client_id": report.get("client_id"),
        "report_month": report.get("report_month"),
        "previous_month": report.get("previous_month"),
        "ai_videos_started_from": report.get("ai_videos_started_from"),
        "channel_ids": list(report.get("channel_ids") or []),
        "status": report.get("status") or "pending",
        "error": report.get("error"),
        "has_metrics_cache": has_metrics_cache(report["id"]) or bool(metrics),
        "narrative": report.get("narrative"),
        "metrics_summary": metrics_summary_for_api(metrics if metrics else None),
        "refine_history": list(report.get("refine_history") or [])[-10:],
        "html_url": f"/report.html/{report['id']}" if report.get("html") else None,
        "pdf_url": f"/report.pdf/{report['id']}" if report.get("pdf_path") else None,
        "created_at": report.get("created_at"),
        "updated_at": report.get("updated_at"),
    }


def report_to_detail(report: dict) -> dict:
    return _public_detail(report)


def _build_polished_narrative(
    *,
    client_name: str,
    metrics: dict[str, Any],
    base_narrative: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Run second AI scan over draft + raw metrics, then apply hard presentation guards."""
    polished = polish_report_narrative(
        client_name=client_name,
        metrics=metrics,
        base_narrative=base_narrative,
    )
    narrative, presentation = split_polish_result(polished)
    presentation = apply_presentation_guards(metrics, presentation)
    return narrative, presentation


def _render_and_store_artifacts(
    report_id: str,
    *,
    client_name: str,
    metrics: dict[str, Any],
    narrative: dict[str, Any],
    presentation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    html = render_report_html(
        client_name=client_name,
        metrics=metrics,
        narrative=narrative,
        presentation=presentation,
    )
    pdf_path = report_pdf_path(report_id)
    try:
        export_html_to_pdf(html, pdf_path)
        try:
            pdf_stored = upload_file("reports", pdf_path, content_type="application/pdf")
            # Clean up the local temp file since it's safely in GCS now
            pdf_path.unlink(missing_ok=True)
        except Exception as e:
            print(f"[monthly-report] GCS upload failed: {e}. Storing local path instead.", flush=True)
            pdf_stored = str(pdf_path)
    except Exception as exc:  # noqa: BLE001
        print(f"[monthly-report] PDF export failed: {exc}", flush=True)
        pdf_stored = None
    return {"html": html, "pdf_path": pdf_stored}


def generate_report(
    username: str,
    client_id: str,
    *,
    report_month: str | None = None,
    channel_ids: list[str] | None = None,
) -> dict:
    client = ensure_client(username, client_id)
    month = _validate_month(report_month or previous_calendar_month())
    ai_start = (client.get("ai_videos_started_from") or "").strip()
    if not ai_start:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="AI videos started from is not set for this client. Add it in Settings, then try again.",
        )
    _validate_month(ai_start)

    channels = list_channels_meta(client_id)
    if channel_ids:
        allow = set(channel_ids)
        selected = [c["id"] for c in channels if c.get("id") in allow]
    else:
        selected = [c["id"] for c in channels if c.get("id")]
    if not selected:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Link at least one YouTube channel before generating a report.",
        )

    existing = fetch_monthly_report_by_month(client_id, month, username=username)
    report_id = existing["id"] if existing else str(uuid.uuid4())
    now = _now()
    stub = {
        "id": report_id,
        "client_id": client_id,
        "username": username,
        "report_month": month,
        "previous_month": None,
        "ai_videos_started_from": ai_start,
        "channel_ids": selected,
        "status": "pending",
        "error": None,
        "narrative": (existing or {}).get("narrative"),
        "refine_history": list((existing or {}).get("refine_history") or []),
        "html": None,
        "pdf_path": None,
        "created_at": (existing or {}).get("created_at") or now,
        "updated_at": now,
    }
    upsert_monthly_report(stub)

    try:
        metrics = fetch_and_compute_metrics(
            username=username,
            client_id=client_id,
            report_month=month,
            ai_videos_started_from=ai_start,
            channel_ids=selected,
        )
        save_metrics_cache(report_id, metrics)
        client_name = client.get("name") or "Client"
        base_narrative = generate_report_narrative(
            client_name=client_name,
            metrics=metrics,
        )
        narrative, presentation = _build_polished_narrative(
            client_name=client_name,
            metrics=metrics,
            base_narrative=base_narrative,
        )
        artifacts = _render_and_store_artifacts(
            report_id,
            client_name=client_name,
            metrics=metrics,
            narrative=narrative,
            presentation=presentation,
        )
        update_monthly_report_fields(
            report_id,
            {
                "status": "ready",
                "error": None,
                "previous_month": metrics.get("previous_month"),
                "narrative": narrative,
                "presentation": presentation,
                "html": artifacts["html"],
                "pdf_path": artifacts["pdf_path"],
                "updated_at": _now(),
            },
            unset=["metrics"],
        )
    except HTTPException:
        update_monthly_report_fields(
            report_id,
            {"status": "failed", "error": "Generation failed", "updated_at": _now()},
            unset=["metrics"],
        )
        raise
    except Exception as exc:  # noqa: BLE001
        update_monthly_report_fields(
            report_id,
            {"status": "failed", "error": str(exc), "updated_at": _now()},
            unset=["metrics"],
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Report generation failed: {exc}",
        ) from exc

    return _public_detail(get_report(username, report_id))


def refine_report(username: str, report_id: str, prompt: str) -> dict:
    report = get_report(username, report_id)
    client = ensure_client(username, report["client_id"])
    cleaned = (prompt or "").strip()
    if not cleaned:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Refinement prompt is required.",
        )

    update_monthly_report_fields(
        report_id,
        {"status": "pending", "error": None, "updated_at": _now()},
        unset=["metrics"],
    )

    try:
        metrics = _resolve_metrics(report)
        if not metrics:
            ai_start = (
                report.get("ai_videos_started_from")
                or client.get("ai_videos_started_from")
                or ""
            ).strip()
            if not ai_start:
                raise ValueError("Missing ai_videos_started_from; cannot refetch metrics.")
            metrics = fetch_and_compute_metrics(
                username=username,
                client_id=report["client_id"],
                report_month=report["report_month"],
                ai_videos_started_from=ai_start,
                channel_ids=report.get("channel_ids") or None,
            )
            save_metrics_cache(report_id, metrics)

        client_name = client.get("name") or "Client"
        base_narrative = refine_report_narrative(
            client_name=client_name,
            metrics=metrics,
            prior_narrative=report.get("narrative"),
            refine_prompt=cleaned,
        )
        narrative, presentation = _build_polished_narrative(
            client_name=client_name,
            metrics=metrics,
            base_narrative=base_narrative,
        )
        artifacts = _render_and_store_artifacts(
            report_id,
            client_name=client_name,
            metrics=metrics,
            narrative=narrative,
            presentation=presentation,
        )
        history = list(report.get("refine_history") or [])
        history.append({"prompt": cleaned, "created_at": _now()})
        update_monthly_report_fields(
            report_id,
            {
                "status": "ready",
                "error": None,
                "narrative": narrative,
                "presentation": presentation,
                "html": artifacts["html"],
                "pdf_path": artifacts["pdf_path"],
                "previous_month": metrics.get("previous_month") or report.get("previous_month"),
                "refine_history": history[-20:],
                "updated_at": _now(),
            },
            unset=["metrics"],
        )
    except HTTPException:
        update_monthly_report_fields(
            report_id,
            {"status": "failed", "error": "Refine failed", "updated_at": _now()},
            unset=["metrics"],
        )
        raise
    except Exception as exc:  # noqa: BLE001
        update_monthly_report_fields(
            report_id,
            {"status": "failed", "error": str(exc), "updated_at": _now()},
            unset=["metrics"],
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Report refine failed: {exc}",
        ) from exc

    return _public_detail(get_report(username, report_id))


def set_ai_start_for_client_named(
    username: str,
    name_substr: str,
    ai_videos_started_from: str,
) -> dict | None:
    """Utility: set AI start month on first client whose name matches (case-insensitive)."""
    from app.database import list_clients_for_user

    needle = name_substr.strip().lower()
    for client in list_clients_for_user(username):
        if needle in (client.get("name") or "").lower():
            return update_client_fields(
                client["id"],
                username,
                {"ai_videos_started_from": ai_videos_started_from},
            )
    return None
