from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth import router as auth_router
from app.config import settings
from app.google_oauth import router as google_router
from app.routes.admin import router as admin_router
from app.routes.channel import router as channel_router
from app.routes.client import router as client_router
from app.routes.report import router as report_router
from app.routes.social import router as social_router
from app.routes.tracker import router as tracker_router
from app.routes.custom_tracker import router as custom_tracker_router
from app.routes.tracker_sheet import router as tracker_sheet_router
from app.routes.video import router as video_router

app = FastAPI(
    title="YouTube Analytics API",
    description="FastAPI backend for YouTube Data and Analytics integration",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Narration-Cached", "Content-Disposition", "Content-Length"],
)

app.include_router(auth_router)
app.include_router(google_router)
app.include_router(admin_router)
app.include_router(client_router)
app.include_router(channel_router)
app.include_router(video_router)
app.include_router(report_router)
app.include_router(social_router)
app.include_router(tracker_router)
app.include_router(custom_tracker_router)
app.include_router(tracker_sheet_router)


@app.get("/health")
def health():
    from app.database import _use_mongo, collection_stats

    try:
        db_info = collection_stats()
    except Exception as exc:  # noqa: BLE001 — surface deploy misconfig
        db_info = {"error": str(exc)}
    return {
        "status": "ok",
        "mongo": _use_mongo(),
        "db": db_info,
    }
