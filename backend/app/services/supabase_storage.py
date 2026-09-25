"""Supabase Storage via the REST API (httpx)."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import quote, unquote, urlparse

import httpx

from app.config import settings
from app.services.storage import StorageLimitError

# Free-tier hard cap. GCS is not limited by this module.
MAX_FILE_BYTES = 50 * 1024 * 1024


def _blob_path(folder: str, filename: str) -> str:
    prefix = f"{folder.strip('/')}/" if folder else ""
    return f"{prefix}{filename}"


def _base() -> str:
    return (settings.SUPABASE_URL or "").strip().rstrip("/")


def _bucket() -> str:
    return (settings.SUPABASE_BUCKET or "").strip().strip("/")


def _key() -> str:
    return (settings.SUPABASE_SERVICE_ROLE_KEY or "").strip()


def _require_config() -> tuple[str, str, str]:
    base, bucket, key = _base(), _bucket(), _key()
    if not base or not bucket or not key:
        raise ValueError("SUPABASE_URL, SUPABASE_BUCKET, and SUPABASE_SERVICE_ROLE_KEY must be set.")
    return base, bucket, key


def _headers(content_type: str | None = None) -> dict[str, str]:
    _, _, key = _require_config()
    headers = {
        "Authorization": f"Bearer {key}",
        "apikey": key,
        "x-upsert": "true",
    }
    if content_type:
        headers["Content-Type"] = content_type
    return headers


def _encoded_key(blob_path: str) -> str:
    return "/".join(quote(part, safe="") for part in blob_path.strip("/").split("/") if part)


def _object_api_url(blob_path: str) -> str:
    base, bucket, _ = _require_config()
    return f"{base}/storage/v1/object/{bucket}/{_encoded_key(blob_path)}"


def public_url(blob_path: str) -> str:
    base, bucket, _ = _require_config()
    return f"{base}/storage/v1/object/public/{bucket}/{_encoded_key(blob_path)}"


def _raise_if_too_large(size: int) -> None:
    if size > MAX_FILE_BYTES:
        raise StorageLimitError("File is over 50 MB. Supabase free storage rejects larger files.")


def _raise_for_status(response: httpx.Response, action: str) -> None:
    if response.is_success:
        return
    detail = (response.text or "").strip()[:400]
    raise ValueError(f"Supabase {action} failed ({response.status_code}): {detail or response.reason_phrase}")


def upload_bytes(folder: str, filename: str, data: bytes, content_type: str = "image/png") -> str:
    _raise_if_too_large(len(data))
    blob_path = _blob_path(folder, filename)
    with httpx.Client(timeout=120.0) as client:
        response = client.post(_object_api_url(blob_path), headers=_headers(content_type), content=data)
    _raise_for_status(response, "upload")
    return public_url(blob_path)


def upload_file(folder: str, local_path: Path | str, content_type: str = "application/pdf") -> str:
    path = Path(local_path)
    _raise_if_too_large(path.stat().st_size)
    blob_path = _blob_path(folder, path.name)
    with httpx.Client(timeout=120.0) as client:
        with path.open("rb") as handle:
            response = client.post(_object_api_url(blob_path), headers=_headers(content_type), content=handle.read())
    _raise_for_status(response, "upload")
    return public_url(blob_path)


def delete_file(blob_path: str) -> None:
    key = (blob_path or "").lstrip("/")
    if not key:
        return
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.delete(_object_api_url(key), headers=_headers())
        if response.status_code in {404, 400}:
            return
        _raise_for_status(response, "delete")
    except Exception as exc:
        print(f"Failed to delete Supabase file {key}: {exc}", flush=True)


def blob_path_from_url(url: str) -> str | None:
    """Parse object key from a Supabase public storage URL."""
    parsed = urlparse(url)
    host = (parsed.netloc or "").lower()
    if "supabase.co" not in host:
        return None
    path = unquote(parsed.path or "").lstrip("/")
    marker = "storage/v1/object/public/"
    if marker not in path:
        return None
    rest = path.split(marker, 1)[-1]
    parts = rest.split("/", 1)
    if len(parts) != 2:
        return None
    return parts[1] or None
