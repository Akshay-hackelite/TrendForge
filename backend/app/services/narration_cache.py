"""Disk cache for OpenAI TTS narration audio (mp3).

Key is a hash of cleaned script text + TTS model/voice/instructions so
unchanged scripts reuse the same file across requests and page reloads.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "narration_cache"


def _ensure_dir() -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR


def cache_key(*, text: str, model: str, voice: str, instructions: str) -> str:
    payload = "\n".join(
        [
            "v1",
            (model or "").strip(),
            (voice or "").strip(),
            (instructions or "").strip(),
            (text or "").strip(),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def cache_path(key: str) -> Path:
    return _ensure_dir() / f"{key}.mp3"


def load_cached(key: str) -> bytes | None:
    path = cache_path(key)
    if not path.is_file():
        return None
    data = path.read_bytes()
    if len(data) < 64:
        return None
    return data


def save_cached(key: str, data: bytes) -> Path:
    if not data:
        raise ValueError("Cannot cache empty audio.")
    path = cache_path(key)
    path.write_bytes(data)
    return path
