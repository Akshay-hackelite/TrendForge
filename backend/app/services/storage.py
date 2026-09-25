"""Storage switcher: Supabase Storage (default) or Google Cloud Storage.

Set STORAGE_BACKEND=supabase or STORAGE_BACKEND=gcs. GCS code is kept; new uploads
follow the switcher. Deletes follow the URL host so mixed history still works.
"""

from __future__ import annotations

from pathlib import Path

from app.config import settings


class StorageLimitError(ValueError):
    """File exceeds the active backend's size limit."""


def _backend() -> str:
    return (settings.STORAGE_BACKEND or "supabase").strip().lower()


def upload_bytes(folder: str, filename: str, data: bytes, content_type: str = "image/png") -> str:
    backend = _backend()
    if backend == "gcs":
        from app.services import gcs_storage

        return gcs_storage.upload_bytes(folder, filename, data, content_type)
    if backend == "supabase":
        from app.services import supabase_storage

        return supabase_storage.upload_bytes(folder, filename, data, content_type)
    raise ValueError(f"Unknown STORAGE_BACKEND={backend!r} (use supabase or gcs)")


def upload_file(folder: str, local_path: Path | str, content_type: str = "application/pdf") -> str:
    backend = _backend()
    if backend == "gcs":
        from app.services import gcs_storage

        return gcs_storage.upload_file(folder, local_path, content_type)
    if backend == "supabase":
        from app.services import supabase_storage

        return supabase_storage.upload_file(folder, local_path, content_type)
    raise ValueError(f"Unknown STORAGE_BACKEND={backend!r} (use supabase or gcs)")


def delete_by_url(url: str) -> None:
    """Delete a cloud object based on the stored public URL, not the current backend."""
    text = (url or "").strip()
    if not text.startswith("http"):
        return
    if "storage.googleapis.com" in text:
        from app.services import gcs_storage

        rest = text.split("https://storage.googleapis.com/", 1)[-1]
        blob_path = rest.split("/", 1)[-1] if "/" in rest else ""
        if blob_path:
            gcs_storage.delete_file(blob_path)
        return
    if "supabase.co" in text:
        from app.services import supabase_storage

        key = supabase_storage.blob_path_from_url(text)
        if key:
            supabase_storage.delete_file(key)
