"""Monthly YouTube AI report routes."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, HTMLResponse

from app import schemas
from app.auth import get_current_user
from app.services import monthly_report as report_service  # noqa: F401 — module API

router = APIRouter(tags=["report"])


def _summary(row: dict) -> schemas.ReportSummary:
    history = [
        schemas.ReportRefineHistoryItem(
            prompt=h.get("prompt") or "",
            created_at=h.get("created_at") or "",
        )
        for h in (row.get("refine_history") or [])
        if isinstance(h, dict)
    ]
    return schemas.ReportSummary(
        id=row["id"],
        client_id=row.get("client_id") or "",
        report_month=row.get("report_month") or "",
        previous_month=row.get("previous_month"),
        ai_videos_started_from=row.get("ai_videos_started_from"),
        channel_ids=list(row.get("channel_ids") or []),
        status=row.get("status") or "pending",
        error=row.get("error"),
        has_metrics_cache=bool(row.get("has_metrics_cache")),
        refine_history=history,
        created_at=row.get("created_at"),
        updated_at=row.get("updated_at"),
    )


def _detail(row: dict) -> schemas.ReportDetailResponse:
    history = [
        schemas.ReportRefineHistoryItem(
            prompt=h.get("prompt") or "",
            created_at=h.get("created_at") or "",
        )
        for h in (row.get("refine_history") or [])
        if isinstance(h, dict)
    ]
    return schemas.ReportDetailResponse(
        id=row["id"],
        client_id=row.get("client_id") or "",
        report_month=row.get("report_month") or "",
        previous_month=row.get("previous_month"),
        ai_videos_started_from=row.get("ai_videos_started_from"),
        channel_ids=list(row.get("channel_ids") or []),
        status=row.get("status") or "pending",
        error=row.get("error"),
        has_metrics_cache=bool(row.get("has_metrics_cache")),
        narrative=row.get("narrative"),
        metrics_summary=row.get("metrics_summary"),
        refine_history=history,
        html_url=row.get("html_url"),
        pdf_url=row.get("pdf_url"),
        created_at=row.get("created_at"),
        updated_at=row.get("updated_at"),
    )


@router.post("/report.list", response_model=schemas.ReportListResponse)
def report_list(
    body: schemas.ReportListRequest,
    current_user: dict = Depends(get_current_user),
):
    rows = report_service.list_reports(current_user["username"], body.client_id)
    return schemas.ReportListResponse(reports=[_summary(r) for r in rows])


@router.post("/report.get", response_model=schemas.ReportDetailResponse)
def report_get(
    body: schemas.ReportGetRequest,
    current_user: dict = Depends(get_current_user),
):
    report = report_service.get_report(current_user["username"], body.report_id)
    return _detail(report_service.report_to_detail(report))


@router.post("/report.generate", response_model=schemas.ReportDetailResponse)
def report_generate(
    body: schemas.ReportGenerateRequest,
    current_user: dict = Depends(get_current_user),
):
    detail = report_service.generate_report(
        current_user["username"],
        body.client_id,
        report_month=body.report_month,
        channel_ids=body.channel_ids,
    )
    return _detail(detail)


@router.post("/report.refine", response_model=schemas.ReportDetailResponse)
def report_refine(
    body: schemas.ReportRefineRequest,
    current_user: dict = Depends(get_current_user),
):
    detail = report_service.refine_report(
        current_user["username"],
        body.report_id,
        body.prompt,
    )
    return _detail(detail)


@router.get("/report.html/{report_id}")
def report_html(
    report_id: str,
    current_user: dict = Depends(get_current_user),
):
    report = report_service.get_report(current_user["username"], report_id)
    html = report.get("html")
    if not html:
        raise HTTPException(status_code=404, detail="HTML report not available")
    return HTMLResponse(content=html)


@router.get("/report.pdf/{report_id}")
def report_pdf(
    report_id: str,
    current_user: dict = Depends(get_current_user),
):
    report = report_service.get_report(current_user["username"], report_id)
    pdf_path = report.get("pdf_path")
    
    if not pdf_path:
        raise HTTPException(status_code=404, detail="PDF report not available")
        
    filename = f"{report.get('report_month') or 'report'}-youtube-report.pdf"
    
    if pdf_path.startswith("http"):
        import httpx
        from fastapi.responses import StreamingResponse
        client = httpx.Client()
        def iterfile():
            with client.stream("GET", pdf_path) as r:
                yield from r.iter_bytes()
        return StreamingResponse(
            iterfile(),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )
        
    if not Path(pdf_path).is_file():
        raise HTTPException(status_code=404, detail="PDF report not available")
        
    filename = f"{report.get('report_month') or 'report'}-youtube-report.pdf"
    return FileResponse(
        path=pdf_path,
        media_type="application/pdf",
        filename=filename,
    )
