"""OpenAI helpers for content-plan: map videos, generate, regenerate, scripts."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from openai import OpenAI

from app.config import settings
from app.services.content_formats import VIDEO_TYPE_NAMES, catalog_for_prompt
from app.services.script_templates import catalog_for_script_prompt, template_for

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"

MAP_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "mappings": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "video_id": {"type": "string"},
                    "topic_id": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                    "out_of_keyword": {"type": "boolean"},
                    "video_type": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                },
                "required": ["video_id", "topic_id", "out_of_keyword", "video_type"],
            },
        }
    },
    "required": ["mappings"],
}

SUGGESTIONS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "items": {
            "type": "array",
            "minItems": 1,
            "maxItems": 10,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "topic_id": {"type": "string"},
                    "topic_text": {"type": "string"},
                    "format": {"type": "string", "enum": ["Long", "Short"]},
                    "video_type": {"type": "string"},
                    "title_en": {"type": "string"},
                    "title_hinglish": {"type": "string"},
                    "reasoning": {"type": "string"},
                },
                "required": [
                    "topic_id",
                    "topic_text",
                    "format",
                    "video_type",
                    "title_en",
                    "title_hinglish",
                    "reasoning",
                ],
            },
        }
    },
    "required": ["items"],
}

SCRIPTS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "items": {
            "type": "array",
            "minItems": 1,
            "maxItems": 10,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "id": {"type": "string"},
                    "script": {"type": "string"},
                    "target_duration": {"type": "string"},
                    "hook_used": {"type": "string"},
                    "cta_line": {"type": "string"},
                    "checklist_passed": {"type": "boolean"},
                    "checklist_notes": {"type": "string"},
                },
                "required": [
                    "id",
                    "script",
                    "target_duration",
                    "hook_used",
                    "cta_line",
                    "checklist_passed",
                    "checklist_notes",
                ],
            },
        }
    },
    "required": ["items"],
}

SCRIPT_REFINE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "script": {"type": "string"},
        "target_duration": {"type": "string"},
        "hook_used": {"type": "string"},
        "cta_line": {"type": "string"},
        "checklist_passed": {"type": "boolean"},
        "checklist_notes": {"type": "string"},
    },
    "required": [
        "script",
        "target_duration",
        "hook_used",
        "cta_line",
        "checklist_passed",
        "checklist_notes",
    ],
}


def _load_prompt(name: str) -> str:
    path = PROMPTS_DIR / name
    return path.read_text(encoding="utf-8").strip()


def _luna_fallback() -> str:
    return "gpt-5.6-luna"


def _extraction_model() -> str:
    return (
        getattr(settings, "OPENAI_EXTRACTION_MODEL", None)
        or settings.OPENAI_MODEL
        or _luna_fallback()
    ).strip() or _luna_fallback()


def _mapping_model() -> str:
    return (
        getattr(settings, "OPENAI_MAPPING_MODEL", None)
        or settings.OPENAI_MODEL
        or _luna_fallback()
    ).strip() or _luna_fallback()


def _generation_model() -> str:
    return (
        getattr(settings, "OPENAI_GENERATION_MODEL", None)
        or settings.OPENAI_CONTENT_PLAN_MODEL
        or _luna_fallback()
    ).strip() or _luna_fallback()


def _reasoning_effort(default: str = "low") -> str:
    return (settings.OPENAI_REASONING_EFFORT or default).strip() or default


def _call_openai(
    *,
    messages: list[dict],
    schema: dict[str, Any],
    schema_name: str,
    effort: str,
    stage: str,
    metadata: dict[str, Any] | None = None,
    timeout: float = 120.0,
    model: str | None = None,
) -> dict[str, Any]:
    if not (settings.OPENAI_API_KEY or "").strip():
        raise ValueError("OPENAI_API_KEY is not set.")

    client = OpenAI(
        api_key=settings.OPENAI_API_KEY,
        timeout=float(timeout or 120.0),
        max_retries=1,
    )
    model = (model or _generation_model()).strip() or _generation_model()
    effort = (effort or "low").strip() or "low"

    raw_text = ""
    api_used = "responses"
    t0 = time.perf_counter()
    print(
        f"[content-plan:openai] stage={stage} → API model={model} effort={effort!r} …",
        flush=True,
    )

    try:
        try:
            response = client.responses.create(
                model=model,
                input=messages,
                text={
                    "format": {
                        "type": "json_schema",
                        "name": schema_name,
                        "strict": True,
                        "schema": schema,
                    }
                },
                reasoning={"effort": effort},
            )
            raw_text = getattr(response, "output_text", None) or ""
            if not raw_text:
                chunks = []
                for item in getattr(response, "output", []) or []:
                    for part in getattr(item, "content", []) or []:
                        text = getattr(part, "text", None)
                        if text:
                            chunks.append(text)
                raw_text = "".join(chunks)
            print(
                f"[content-plan:openai] stage={stage} ← responses OK "
                f"in {time.perf_counter() - t0:.1f}s chars={len(raw_text)}",
                flush=True,
            )
        except Exception as resp_exc:
            print(
                f"[content-plan:openai] stage={stage} responses failed "
                f"({type(resp_exc).__name__}: {resp_exc}); chat.completions …",
                flush=True,
            )
            api_used = "chat.completions"
            kwargs: dict[str, Any] = {
                "model": model,
                "messages": messages,
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": schema_name,
                        "strict": True,
                        "schema": schema,
                    },
                },
                "reasoning_effort": effort,
            }
            try:
                completion = client.chat.completions.create(**kwargs)
            except Exception:
                kwargs.pop("reasoning_effort", None)
                kwargs["response_format"] = {"type": "json_object"}
                completion = client.chat.completions.create(**kwargs)
            raw_text = completion.choices[0].message.content or ""
            print(
                f"[content-plan:openai] stage={stage} ← chat.completions OK "
                f"in {time.perf_counter() - t0:.1f}s chars={len(raw_text)}",
                flush=True,
            )
    except Exception as exc:
        print(
            f"[content-plan:openai] stage={stage} FAILED after "
            f"{time.perf_counter() - t0:.1f}s: {type(exc).__name__}: {exc}",
            flush=True,
        )
        raise ValueError(f"OpenAI content-plan '{stage}' failed: {exc}") from exc

    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"OpenAI content-plan '{stage}' returned non-JSON") from exc

    return parsed


def map_videos_batch(
    *,
    topics: list[dict],
    videos: list[dict],
    specialty: str | None = None,
    client_id: str | None = None,
) -> list[dict]:
    """Map a batch of videos → topic_id or out_of_keyword (low effort)."""
    system = _load_prompt("content_plan_map_videos.txt")
    payload = {
        "specialty": specialty,
        "keywords": [{"id": t["id"], "text": t.get("text")} for t in topics],
        "video_types": catalog_for_prompt(),
        "videos": [
            {
                "id": v["id"],
                "title": v.get("title") or "",
                "is_short": bool(v.get("is_short")),
                "published_at": v.get("published_at") or "",
                "view_count": int(v.get("view_count") or 0),
            }
            for v in videos
        ],
    }
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]
    effort = (settings.OPENAI_CONTENT_PLAN_MAP_EFFORT or "low").strip() or "low"
    parsed = _call_openai(
        messages=messages,
        schema=MAP_SCHEMA,
        schema_name="content_plan_video_map",
        effort=effort,
        stage="map_videos",
        metadata={"client_id": client_id},
        model=_mapping_model(),
    )
    topic_ids = {t["id"] for t in topics}
    out: list[dict] = []
    for row in parsed.get("mappings") or []:
        if not isinstance(row, dict):
            continue
        vid = (row.get("video_id") or "").strip()
        if not vid:
            continue
        out_of = bool(row.get("out_of_keyword"))
        tid = row.get("topic_id")
        if tid and tid not in topic_ids:
            tid = None
            out_of = True
        if out_of:
            tid = None
        vtype = row.get("video_type")
        if vtype and vtype not in VIDEO_TYPE_NAMES:
            match = next(
                (n for n in VIDEO_TYPE_NAMES if n.lower() == str(vtype).lower()),
                None,
            )
            vtype = match
        out.append(
            {
                "video_id": vid,
                "topic_id": tid,
                "out_of_keyword": out_of or not tid,
                "video_type": vtype,
            }
        )
    return out


def _slots_for_ai(slots: list[dict], *, regenerate: bool = False) -> list[dict]:
    """Strip score / internal fields before sending to OpenAI."""
    lean: list[dict] = []
    for s in slots:
        row = {
            "topic_id": s.get("topic_id"),
            "topic_text": s.get("topic_text"),
            "format": s.get("format"),
            "pending_long": bool(s.get("pending_long")),
            "pending_short": bool(s.get("pending_short")),
        }
        if regenerate:
            if s.get("previous_video_type"):
                row["previous_video_type"] = s.get("previous_video_type")
            if s.get("previous_title_en"):
                row["previous_title_en"] = s.get("previous_title_en")
            if s.get("previous_title_hinglish"):
                row["previous_title_hinglish"] = s.get("previous_title_hinglish")
        lean.append(row)
    return lean


def enrich_suggestions(
    *,
    slots: list[dict],
    specialty: str | None,
    description: str | None,
    recent_library_topics: list[dict] | None = None,
    recent_video_types: list[str] | None = None,
    keyword_analysis: list[dict] | None = None,
    fresh_channel: bool = False,
    client_id: str | None = None,
    user_prompt: str | None = None,
    previous_items: list[dict] | None = None,
    extra_keywords: list[dict] | None = None,
    regenerate: bool = False,
) -> list[dict]:
    """Generate or regenerate titles + factor reasoning + video_type (high effort)."""
    prompt_name = (
        "content_plan_regenerate.txt" if regenerate else "content_plan_generate.txt"
    )
    system = _load_prompt(prompt_name)

    recent_compact = []
    for row in (recent_library_topics or [])[:20]:
        recent_compact.append(
            {
                "title": row.get("title"),
                "is_short": row.get("is_short"),
                "topic_text": row.get("topic_text"),
                "video_type": row.get("video_type"),
                "out_of_keyword": row.get("out_of_keyword"),
            }
        )

    if regenerate:
        payload: dict[str, Any] = {
            "specialty": specialty,
            "description": description,
            "channel_status": "fresh" if fresh_channel else "established",
            "video_types": catalog_for_prompt(),
            "previous_items": _slots_for_ai(slots, regenerate=True),
            "extra_keywords": [
                {
                    "topic_id": e.get("topic_id"),
                    "topic_text": e.get("topic_text"),
                    "pending_long": e.get("pending_long"),
                    "pending_short": e.get("pending_short"),
                }
                for e in (extra_keywords or [])
            ],
            "recent_library_topics": recent_compact,
            "recent_video_types": list(dict.fromkeys(recent_video_types or []))[:15],
            "user_prompt": (user_prompt or "").strip(),
            "note": (
                "REFINE MODE: keep the previous_items list (same count). "
                "Rewrite titles / video_type / reasoning using user_prompt. "
                "Only swap a keyword if user_prompt requires it — and only from extra_keywords. "
                "Keep each item's Long/Short format unless the user asks to change it. "
                "Titles: strong clickbait + medical keyword, simple to read. "
                "title_hinglish must mix Latin English letters + Devanagari (not romanized-only). "
                "video_types is the catalog; recent_* is last ~20 public videos for mix context. "
                "Return title_en + title_hinglish + short reasoning."
            ),
        }
    else:
        analysis_compact = []
        for row in keyword_analysis or []:
            analysis_compact.append(
                {
                    "topic_id": row.get("topic_id"),
                    "topic_text": row.get("topic_text"),
                    "pending_long": row.get("pending_long"),
                    "pending_short": row.get("pending_short"),
                }
            )
        payload = {
            "specialty": specialty,
            "description": description,
            "channel_status": "fresh" if fresh_channel else "established",
            "video_types": catalog_for_prompt(),
            "slots": _slots_for_ai(slots),
            "recent_library_topics": recent_compact,
            "recent_video_types": list(dict.fromkeys(recent_video_types or []))[:15],
            "slot_coverage": analysis_compact,
            "note": (
                "Long/Short on each slot is fixed. "
                "Pick video_type from the catalog to fit the topic; mix Long themes across the batch "
                "(Disease explainer is only a soft option, not the default). "
                "If channel_status is fresh or recent_library_topics is empty, treat as a new channel — "
                "no need to avoid recent themes. "
                "Titles: strong clickbait + medical keyword, simple to read. "
                "title_hinglish must mix Latin English letters + Devanagari (not romanized-only). "
                "Vary hooks across the batch — 'मत करें' / 'Don't ignore' are OK sparingly, not on most titles. "
                "Return title_en + title_hinglish + short reasoning."
            ),
        }
        if user_prompt:
            payload["user_prompt"] = user_prompt
        if previous_items:
            payload["previous_items"] = [
                {
                    "topic_text": p.get("topic_text"),
                    "format": p.get("format"),
                    "video_type": p.get("video_type"),
                    "title_en": p.get("title_en") or p.get("working_title"),
                    "title_hinglish": p.get("title_hinglish") or p.get("working_title"),
                }
                for p in previous_items
                if isinstance(p, dict)
            ]

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]
    effort = _reasoning_effort("low")
    stage = "regenerate" if regenerate else "generate"
    parsed = _call_openai(
        messages=messages,
        schema=SUGGESTIONS_SCHEMA,
        schema_name="content_plan_suggestions",
        effort=effort,
        stage=stage,
        metadata={"client_id": client_id, "user_prompt": user_prompt},
        model=_generation_model(),
    )
    return [row for row in (parsed.get("items") or []) if isinstance(row, dict)]


def generate_scripts_batch(
    *,
    items: list[dict],
    doctor_name: str,
    doctor_designation: str,
    doctor_location: str | None = None,
    specialty: str | None = None,
    description: str | None = None,
    client_id: str | None = None,
    example1: str | None = None,
    example2: str | None = None,
) -> list[dict]:
    """Generate Hinglish spoken scripts for all content-plan items."""
    system = _load_prompt("content_plan_generate_scripts.txt")
    
    if example1 or example2:
        system += "\n\n═══════════════════════════════════════════════════════════════════\n"
        system += "REFERENCE EXAMPLES FOR STYLE AND TONE\n"
        system += "═══════════════════════════════════════════════════════════════════\n"
        system += "The user has provided the following reference scripts. Analyze their formatting, tone, and clinical depth. You MUST match this exact style in your generated scripts.\n"
        if example1:
            system += f"\n--- EXAMPLE 1 ---\n{example1}\n"
        if example2:
            system += f"\n--- EXAMPLE 2 ---\n{example2}\n"

    slots: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        item_id = (item.get("id") or "").strip()
        if not item_id:
            continue
        fmt = "Short" if (item.get("format") or "") == "Short" else "Long"
        vtype = (item.get("video_type") or "").strip()
        tmpl = template_for(vtype, fmt)
        slots.append(
            {
                "id": item_id,
                "topic_id": item.get("topic_id"),
                "topic_text": item.get("topic_text"),
                "format": fmt,
                "video_type": vtype or tmpl.get("video_type"),
                "title_en": item.get("title_en") or item.get("working_title") or "",
                "title_hinglish": item.get("title_hinglish")
                or item.get("working_title")
                or "",
                "reasoning": item.get("reasoning") or "",
                "template": tmpl,
            }
        )
    if not slots:
        raise ValueError("No content-plan items to script.")

    payload: dict[str, Any] = {
        "doctor_name": doctor_name,
        "doctor_designation": doctor_designation,
        "doctor_location": doctor_location or "",
        "specialty": specialty,
        "description": description,
        "catalog": catalog_for_script_prompt(),
        "items": slots,
        "note": (
            "Generate a full spoken Hinglish script for EVERY item. "
            "Follow each item.template timing_map, hook formula, and ending CTA. "
            "Doctor intro MUST be: greeting → मैं [Name], [Designation] → plural team invite "
            "(आज समझेंगे / topic समझेंगे). Never solo 'समझाता हूं / clear करता हूं'. "
            "No invented hospital; location rarely if provided. "
            "Respectful chairman tone — never rude openers like 'सीधी बात'. "
            "Long CTA bias: call / नीचे दिए हुए नंबर / consultation / appointment / evaluation "
            "WITH urgency (अभी करें). Never insert a phone number or [Clinic Number]. "
            "Never speak section titles as dialogue (सीधा जवाब। / अब Migraine। / अब danger signs।). "
            "Soft bias: specialty-relevant treatment/next steps when topic allows. "
            "Always formal Hindi verbs (कीजिए / देखिए), never कर ले / देख ले. "
            "Never use em dashes (—) or en dashes (–) in script text. "
            "Pass the Script Checklist on every item. "
            "Across the batch: rotate hooks, intros, transitions, and CTA wording. "
            "Return the same ids, same count, same order."
        ),
    }
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]
    parsed = _call_openai(
        messages=messages,
        schema=SCRIPTS_SCHEMA,
        schema_name="content_plan_scripts",
        effort=_reasoning_effort("low"),
        stage="generate_scripts",
        metadata={"client_id": client_id},
        timeout=300.0,
        model=_generation_model(),
    )
    return [row for row in (parsed.get("items") or []) if isinstance(row, dict)]


def refine_single_script(
    *,
    script: str,
    user_prompt: str,
    format: str,
    video_type: str,
    target_duration: str | None = None,
    topic_text: str | None = None,
    title_en: str | None = None,
    title_hinglish: str | None = None,
    doctor_name: str | None = None,
    doctor_designation: str | None = None,
    doctor_location: str | None = None,
    specialty: str | None = None,
    client_id: str | None = None,
) -> dict:
    """Refine one script with user prompt only — no batch / catalog dump."""
    system = _load_prompt("content_plan_refine_script.txt")
    fmt = "Short" if (format or "") == "Short" else "Long"
    vtype = (video_type or "").strip()
    tmpl = template_for(vtype, fmt)
    payload: dict[str, Any] = {
        "user_prompt": (user_prompt or "").strip(),
        "old_script": (script or "").strip(),
        "doctor_name": doctor_name or "",
        "doctor_designation": doctor_designation or "",
        "doctor_location": doctor_location or "",
        "specialty": specialty or "",
        "format_meta": {
            "format": fmt,
            "video_type": vtype or tmpl.get("video_type"),
            "target_duration": (target_duration or tmpl.get("target_duration") or "").strip(),
            "timing_map": tmpl.get("timing_map") or tmpl.get("core_formula") or "",
            "opening_hook_formula": tmpl.get("opening_hook_formula")
            or tmpl.get("hook_style")
            or "",
            "ending_cta_spirit": tmpl.get("ending_cta") or "",
            "topic_text": topic_text or "",
            "title_en": title_en or "",
            "title_hinglish": title_hinglish or "",
        },
        "note": (
            "SINGLE SCRIPT REFINE. Rewrite only this script using user_prompt. "
            "Intro = greeting → name, designation → plural team invite (समझेंगे), "
            "not समझाता हूं / clear करता हूं. "
            "No hospital names. "
            "CTA bias: call / नीचे दिए हुए नंबर / consultation / appointment / evaluation "
            "with urgency (अभी…). Never insert a phone number. "
            "No spoken section titles. Soft specialty-treatment bias when fitting. "
            "Formal verbs only (कीजिए / देखिए), never कर ले / देख ले. "
            "Never use em dashes (—) or en dashes (–) in script text."
        ),
    }
    if not payload["user_prompt"]:
        raise ValueError("user_prompt is required to refine a script.")
    if not payload["old_script"]:
        raise ValueError("old_script is required to refine a script.")

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]
    return _call_openai(
        messages=messages,
        schema=SCRIPT_REFINE_SCHEMA,
        schema_name="content_plan_script_refine",
        effort=_reasoning_effort("low"),
        stage="refine_script",
        metadata={"client_id": client_id, "user_prompt": user_prompt},
        timeout=180.0,
        model=_generation_model(),
    )


def narrate_script_audio(*, text: str, force: bool = False) -> tuple[bytes, bool]:
    """Collect full TTS audio (non-streaming helper). Prefer stream_narrate_script_audio."""
    chunks: list[bytes] = []
    from_cache = False
    for chunk, cached in stream_narrate_script_audio(text=text, force=force):
        from_cache = cached
        if chunk:
            chunks.append(chunk)
    data = b"".join(chunks)
    if not data:
        raise ValueError("TTS returned empty audio.")
    return data, from_cache


def stream_narrate_script_audio(*, text: str, force: bool = False):
    """Yield (chunk, from_cache) for OpenAI TTS (timing markers stripped).

    On cache hit, yields the saved mp3 once (from_cache=True).
    On miss, streams OpenAI chunks (from_cache=False) and writes the file when done.
    """
    import re

    from app.services.narration_cache import cache_key, load_cached, save_cached

    if not (settings.OPENAI_API_KEY or "").strip():
        raise ValueError("OPENAI_API_KEY is not set.")
    cleaned = re.sub(r"\[[^\]]{0,40}\]", " ", text or "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        raise ValueError("Nothing to narrate.")
    # OpenAI speech input limit
    if len(cleaned) > 4000:
        cleaned = cleaned[:4000].rsplit(" ", 1)[0] + "…"

    model = (getattr(settings, "OPENAI_TTS_MODEL", None) or "gpt-4o-mini-tts").strip() or "gpt-4o-mini-tts"
    voice = (getattr(settings, "OPENAI_TTS_VOICE", None) or "onyx").strip() or "onyx"
    instructions = (getattr(settings, "OPENAI_TTS_INSTRUCTIONS", None) or "").strip()
    # tts-1 / tts-1-hd do not accept instructions
    use_instructions = bool(instructions) and "gpt-4o" in model.lower()
    effective_instructions = instructions if use_instructions else ""

    key = cache_key(
        text=cleaned,
        model=model,
        voice=voice,
        instructions=effective_instructions,
    )
    if not force:
        cached = load_cached(key)
        if cached is not None:
            print(
                f"[content-plan:tts] cache hit key={key[:12]}… "
                f"bytes={len(cached)} chars={len(cleaned)}",
                flush=True,
            )
            yield cached, True
            return

    client = OpenAI(api_key=settings.OPENAI_API_KEY, timeout=120.0, max_retries=1)

    print(
        f"[content-plan:tts] stream model={model} voice={voice} "
        f"hindi_instructions={use_instructions} chars={len(cleaned)} "
        f"force={force} …",
        flush=True,
    )
    create_kwargs: dict = {
        "model": model,
        "voice": voice,
        "input": cleaned,
        "response_format": "mp3",
    }
    if use_instructions:
        create_kwargs["instructions"] = instructions

    accumulated = bytearray()
    with client.audio.speech.with_streaming_response.create(**create_kwargs) as response:
        for chunk in response.iter_bytes(chunk_size=2048):
            if not chunk:
                continue
            accumulated.extend(chunk)
            yield bytes(chunk), False
    if not accumulated:
        raise ValueError("TTS returned empty audio.")
    save_cached(key, bytes(accumulated))
    print(
        f"[content-plan:tts] stream done bytes={len(accumulated)} "
        f"cached_key={key[:12]}…",
        flush=True,
    )
