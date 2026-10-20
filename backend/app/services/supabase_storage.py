"""Supabase Storage via the REST API (httpx)."""

from __future__ import annotations

import base64
from pathlib import Path
from urllib.parse import quote, unquote, urlparse

import httpx

from app.config import settings
from app.services.storage import StorageLimitError

# Free-tier hard cap for images and other small files. Instagram video copies
# use the resumable path and may be as large as a reel (1 GB).
MAX_FILE_BYTES = 50 * 1024 * 1024
VIDEO_CHUNK_BYTES = 8 * 1024 * 1024
VIDEO_UPLOAD_TIMEOUT = 3600.0
LARGE_FILE_BYTES = 32 * 1024 * 1024
INSTAGRAM_VIDEO_MAX_BYTES = 1000 * 1000 * 1000
STORAGE_TIMEOUT_DETAIL = (
    "Storage upload timed out after 1 hour. The video was not copied for Instagram."
)


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


def explain_storage_failure(exc: BaseException) -> str:
    text = str(exc)
    if "timeout" in text.lower() or "timed out" in text.lower():
        return STORAGE_TIMEOUT_DETAIL
    return text


def _is_video_copy(content_type: str, size: int, allow_large: bool) -> bool:
    if allow_large or content_type.startswith("video/"):
        return True
    return size > LARGE_FILE_BYTES and size <= MAX_FILE_BYTES


def _tus_metadata(blob_path: str, content_type: str) -> str:
    _, bucket, _ = _require_config()

    def field(name: str, value: str) -> str:
        encoded = base64.b64encode(value.encode()).decode()
        return f"{name} {encoded}"

    return ",".join([
        field("bucketName", bucket),
        field("objectName", blob_path),
        field("contentType", content_type),
        field("cacheControl", "3600"),
    ])


def _upload_resumable(
    path: Path,
    blob_path: str,
    content_type: str,
    on_progress,
) -> str:
    """8 MB TUS chunks. The public object stays up so Instagram can fetch it."""
    base, _, key = _require_config()
    size = path.stat().st_size
    endpoint = f"{base}/storage/v1/upload/resumable"
    headers = {
        "Authorization": f"Bearer {key}",
        "apikey": key,
        "x-upsert": "true",
        "Tus-Resumable": "1.0.0",
        "Upload-Length": str(size),
        "Upload-Metadata": _tus_metadata(blob_path, content_type),
    }
    timeout = httpx.Timeout(VIDEO_UPLOAD_TIMEOUT, connect=30.0)
    try:
        with httpx.Client(timeout=timeout) as client:
            created = client.post(endpoint, headers=headers)
            _raise_for_status(created, "resumable upload")
            location = created.headers.get("Location") or ""
            if location.startswith("/"):
                location = f"{base}{location}"
            if not location:
                raise ValueError("Supabase resumable upload did not return a Location.")
            sent = 0
            with path.open("rb") as handle:
                while sent < size:
                    blob = handle.read(VIDEO_CHUNK_BYTES)
                    if not blob:
                        break
                    patched = client.patch(
                        location,
                        headers={
                            "Authorization": f"Bearer {key}",
                            "apikey": key,
                            "Tus-Resumable": "1.0.0",
                            "Upload-Offset": str(sent),
                            "Content-Type": "application/offset+octet-stream",
                        },
                        content=blob,
                    )
                    _raise_for_status(patched, "resumable upload")
                    sent += len(blob)
                    if on_progress and size:
                        on_progress(min(100, int(sent * 100 / size)))
    except httpx.TimeoutException as exc:
        raise TimeoutError(STORAGE_TIMEOUT_DETAIL) from exc
    except Exception as exc:
        if isinstance(exc, TimeoutError):
            raise
        message = explain_storage_failure(exc)
        if message == STORAGE_TIMEOUT_DETAIL:
            raise TimeoutError(STORAGE_TIMEOUT_DETAIL) from exc
        raise
    return public_url(blob_path)


def upload_file(
    folder: str,
    local_path: Path | str,
    content_type: str = "application/pdf",
    *,
    on_progress=None,
    allow_large: bool = False,
) -> str:
    path = Path(local_path)
    size = path.stat().st_size
    if _is_video_copy(content_type, size, allow_large):
        if size > INSTAGRAM_VIDEO_MAX_BYTES:
            raise StorageLimitError("File is over 1 GB.")
        return _upload_resumable(path, _blob_path(folder, path.name), content_type, on_progress)
    _raise_if_too_large(size)
    blob_path = _blob_path(folder, path.name)
    with httpx.Client(timeout=120.0) as client:
        with path.open("rb") as handle:
            response = client.post(_object_api_url(blob_path), headers=_headers(content_type), content=handle.read())
    _raise_for_status(response, "upload")
    if on_progress:
        on_progress(100)
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
