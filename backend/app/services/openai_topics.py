"""OpenAI topic pipeline — three separate API calls.

1) Sitemap URLs → website niche keywords
2) Website topics + specialty → weighted keyword list
3) Existing list + specialty + user_prompt → refined list (prompt-only)
"""

from __future__ import annotations

import json
import time
from typing import Any

from openai import OpenAI

from app.config import settings
from app.services.topics import WEIGHTS, make_topic, normalize_topics

# ---------------------------------------------------------------------------
# Shared schema
# ---------------------------------------------------------------------------

TOPIC_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "detected_specialty": {
            "anyOf": [{"type": "string"}, {"type": "null"}],
            "description": "Best specialty / niche label inferred, or null.",
        },
        "rationale": {
            "type": "string",
            "description": "1-3 sentences explaining the output.",
        },
        "topics": {
            "type": "array",
            "minItems": 10,
            "maxItems": 90,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "Niche keyword (1-4 words).",
                    },
                    "weight": {
                        "type": "string",
                        "enum": ["high", "medium", "low"],
                        "description": (
                            "high=core problem/topic; medium=related topic; "
                            "low=method/tool/how-to. Never put methods in high."
                        ),
                    },
                },
                "required": ["text", "weight"],
            },
        },
    },
    "required": ["detected_specialty", "rationale", "topics"],
}

WEIGHTING_RULES = """
Weighting (strict):
- high: CORE PROBLEMS and SEARCH TOPICS the audience cares about
  e.g. email marketing, morning routine, budget travel, home workout, brand storytelling
- medium: related / adjacent topics, or lighter method mentions
- low: METHODS, TOOLS, and HOW-TOS (software, frameworks, processes, product names)
  e.g. Notion template, color grading, SEO audit, Canva workflow

Audience problems ALWAYS outrank methods/tools. Never put a method or tool in "high".
"""

SYSTEM_SITEMAP = f"""You extract niche topic keywords from website sitemap URLs only.

Infer core topics, methods, and audience-problem labels from URL path slugs.
Ignore blog/article/news/press paths, locale hubs, about/contact/privacy pages,
brand slogans, and creator names.

Good core topics (prefer high): "email marketing", "morning routine", "budget travel", "home workout"
Methods/tools (prefer low): "Notion template", "SEO audit", "color grading"
Bad: brand legal names, slogans, CTAs, full sentences

{WEIGHTING_RULES}
Output short niche keywords (1–4 words) with weights. Return JSON only.
"""

SYSTEM_SPECIALTY = f"""You build a creator/brand niche keyword library.

You receive website-derived topics (from their sitemap) plus specialty/context.
Expand and refine into a large set of BROAD niche keywords for content planning.

Rules:
- Keep topics as niche keywords (problems, subjects, methods).
- Prefer specialty-aligned keywords; use website topics as evidence of what they cover.
- 1–4 words each. No brand legal names, slogans, CTAs, creator names, or video titles.
- Bias the list toward PROBLEMS/CORE TOPICS over methods/tools.
{WEIGHTING_RULES}
- Do not copy manual_topics_to_preserve into the output.
Return JSON only.
"""

SYSTEM_REFINE = f"""You revise an existing niche keyword list using ONLY the user's instruction.

Inputs: current auto topics, specialty, and user_prompt.
Apply the user_prompt to add/remove/reweight/rename topics.
Stay on-niche and specialty-aligned. Do not invent marketing copy.
Unless the user_prompt says otherwise, keep PROBLEMS/CORE TOPICS weighted higher than METHODS/TOOLS.
{WEIGHTING_RULES}
Do not include manual_topics_to_preserve in the output.
Return the full updated auto list as JSON.
"""


# ---------------------------------------------------------------------------
# Prompt builders (one per stage)
# ---------------------------------------------------------------------------

def _topics_compact(topics: list | None) -> list[dict]:
    return [
        {"text": t.get("text"), "weight": t.get("weight")}
        for t in normalize_topics(topics or [])
    ]


def build_sitemap_prompt(metadata: dict[str, Any]) -> str:
    urls = list(metadata.get("sitemap_urls") or [])[:600]
    payload = {
        "website_url": metadata.get("website_url"),
        "client_name": metadata.get("client_name"),
        "sitemap_urls": urls,
        "sitemap_url_count": len(metadata.get("sitemap_urls") or []),
        "note": (
            "Extract niche keywords from these non-blog sitemap URLs. "
            "Ignore about/contact/privacy/locale-only pages."
        ),
        "output_requirements": {
            "format": "niche keywords only",
            "weights": list(WEIGHTS),
            "weighting": {
                "high": "core problems and search topics only",
                "medium": "related / adjacent topics",
                "low": "methods, tools, and how-tos",
            },
            "target_counts": {"high": "8-20", "medium": "10-25", "low": "5-15"},
        },
    }
    return (
        "Extract niche topic keywords from the sitemap URLs.\n\n"
        f"INPUT (JSON):\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n\n"
        "Respond with JSON: detected_specialty, rationale, topics[]."
    )


def build_specialty_prompt(
    metadata: dict[str, Any],
    sitemap_topics: list[dict],
) -> str:
    payload = {
        "client_name": metadata.get("client_name"),
        "specialty": metadata.get("specialty"),
        "description": metadata.get("description"),
        "website_url": metadata.get("website_url"),
        "sitemap_topics": _topics_compact(sitemap_topics),
        "youtube": {
            "channel_titles": metadata.get("channel_titles") or [],
            "recent_video_titles": (metadata.get("video_titles") or [])[:30],
            "note": (
                "Optional signal from linked library and/or a public reference channel "
                "(RSS, no OAuth). Mine niche keywords only; never copy full titles."
            ),
        },
        "manual_topics_to_preserve": [
            t.get("text") if isinstance(t, dict) else str(t)
            for t in (metadata.get("manual_topics") or [])
        ],
        "output_requirements": {
            "format": "niche keywords only",
            "weights": list(WEIGHTS),
            "weighting": {
                "high": "core problems and search topics only",
                "medium": "related / adjacent topics",
                "low": "methods, tools, and how-tos",
            },
            "target_counts": {"high": "10-25", "medium": "15-30", "low": "10-25"},
            "mode": "expand_sitemap_topics_with_specialty",
        },
    }
    return (
        "Build the full niche keyword list from sitemap topics + specialty.\n\n"
        f"INPUT (JSON):\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n\n"
        "Respond with JSON: detected_specialty, rationale, topics[]."
    )


def build_refine_prompt(metadata: dict[str, Any]) -> str:
    existing_auto = [
        t
        for t in _topics_compact(metadata.get("existing_auto_topics") or [])
    ]
    payload = {
        "specialty": metadata.get("specialty"),
        "user_prompt": (metadata.get("user_prompt") or "").strip(),
        "existing_auto_topics": existing_auto,
        "manual_topics_to_preserve": [
            t.get("text") if isinstance(t, dict) else str(t)
            for t in (metadata.get("manual_topics") or [])
        ],
        "output_requirements": {
            "format": "niche keywords only",
            "weights": list(WEIGHTS),
            "weighting": {
                "high": "core problems and search topics only",
                "medium": "related / adjacent topics",
                "low": "methods, tools, and how-tos",
            },
            "mode": "refine_existing_list_with_user_prompt_only",
            "note": (
                "Modify the existing list based on user_prompt only. "
                "Unless instructed otherwise, keep problems/core topics higher than methods/tools."
            ),
        },
    }
    return (
        "Revise the existing auto topic list using ONLY the user_prompt.\n"
        "Specialty is context for staying on-domain.\n\n"
        f"INPUT (JSON):\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n\n"
        "Respond with JSON: detected_specialty, rationale, topics[]."
    )


# Back-compat name used nowhere critical
def build_user_prompt(metadata: dict[str, Any]) -> str:
    if (metadata.get("user_prompt") or "").strip():
        return build_refine_prompt(metadata)
    return build_sitemap_prompt(metadata)


# ---------------------------------------------------------------------------
# Parse + API helpers
# ---------------------------------------------------------------------------

def _parse_topics_payload(data: dict[str, Any]) -> tuple[list[dict], dict]:
    topics_out: list[dict] = []
    seen: set[str] = set()
    for item in data.get("topics") or []:
        if not isinstance(item, dict):
            continue
        text = (item.get("text") or "").strip()
        weight = item.get("weight") or "medium"
        if not text:
            continue
        words = text.split()
        if len(words) > 6 or len(text) > 60:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        if weight not in WEIGHTS:
            weight = "medium"
        topics_out.append(make_topic(text, weight, "auto"))

    meta = {
        "detected_specialty": data.get("detected_specialty"),
        "rationale": data.get("rationale"),
        "model": settings.OPENAI_GENERATION_MODEL or settings.OPENAI_MODEL,
    }
    return topics_out, meta


def _call_chat_completions(client: OpenAI, model: str, messages: list[dict]) -> tuple[str, Any, str]:
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "creator_youtube_topics",
                "strict": True,
                "schema": TOPIC_SCHEMA,
            },
        },
    }
    effort = (settings.OPENAI_REASONING_EFFORT or "").strip()
    if effort:
        kwargs["reasoning_effort"] = effort

    t0 = time.perf_counter()
    print(
        f"[topics:openai] → chat.completions.create model={model} effort={effort!r} …",
        flush=True,
    )
    try:
        try:
            completion = client.chat.completions.create(**kwargs)
        except Exception as first_exc:
            print(
                f"[topics:openai] chat.completions schema/effort failed "
                f"({type(first_exc).__name__}: {first_exc}); retry json_object …",
                flush=True,
            )
            kwargs.pop("reasoning_effort", None)
            kwargs["response_format"] = {"type": "json_object"}
            completion = client.chat.completions.create(**kwargs)
    except Exception as exc:
        print(
            f"[topics:openai] ← chat.completions FAILED after "
            f"{time.perf_counter() - t0:.1f}s: {type(exc).__name__}: {exc}",
            flush=True,
        )
        raise

    raw_text = completion.choices[0].message.content or ""
    raw_response = completion.model_dump() if hasattr(completion, "model_dump") else str(completion)
    print(
        f"[topics:openai] ← chat.completions OK in {time.perf_counter() - t0:.1f}s "
        f"chars={len(raw_text)}",
        flush=True,
    )
    return raw_text, raw_response, "chat.completions"


def _call_responses_api(client: OpenAI, model: str, messages: list[dict]) -> tuple[str, Any, str]:
    effort = (settings.OPENAI_REASONING_EFFORT or "low").strip() or "low"
    t0 = time.perf_counter()
    print(
        f"[topics:openai] → responses.create model={model} effort={effort!r} …",
        flush=True,
    )
    try:
        response = client.responses.create(
            model=model,
            input=messages,
            text={
                "format": {
                    "type": "json_schema",
                    "name": "creator_youtube_topics",
                    "strict": True,
                    "schema": TOPIC_SCHEMA,
                }
            },
            reasoning={"effort": effort},
        )
    except Exception as exc:
        print(
            f"[topics:openai] ← responses.create FAILED after "
            f"{time.perf_counter() - t0:.1f}s: {type(exc).__name__}: {exc}",
            flush=True,
        )
        raise

    raw_text = getattr(response, "output_text", None) or ""
    if not raw_text:
        chunks = []
        for item in getattr(response, "output", []) or []:
            for part in getattr(item, "content", []) or []:
                text = getattr(part, "text", None)
                if text:
                    chunks.append(text)
        raw_text = "".join(chunks)
    raw_response = response.model_dump() if hasattr(response, "model_dump") else str(response)
    print(
        f"[topics:openai] ← responses.create OK in {time.perf_counter() - t0:.1f}s "
        f"chars={len(raw_text)}",
        flush=True,
    )
    return raw_text, raw_response, "responses"


def _raise_openai_error(exc: Exception) -> None:
    message = str(exc)
    lower = message.lower()
    if "invalid_api_key" in lower or "incorrect api key" in lower:
        raise ValueError(
            "OpenAI API key is invalid. Update OPENAI_API_KEY in backend/.env "
            "(https://platform.openai.com/account/api-keys), then restart the backend."
        ) from exc
    if "insufficient_quota" in lower or "billing" in lower:
        raise ValueError(
            "OpenAI quota/billing error. Check your OpenAI account billing and retry."
        ) from exc
    raise ValueError(f"OpenAI topic generation failed: {exc}") from exc


def _run_stage(
    *,
    client: OpenAI,
    model: str,
    stage: str,
    system: str,
    user_content: str,
    metadata: dict[str, Any],
) -> tuple[list[dict], dict]:
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_content},
    ]

    print(
        f"[topics:openai] stage={stage} calling API model={model} "
        f"effort={settings.OPENAI_REASONING_EFFORT!r} …",
        flush=True,
    )
    try:
        try:
            raw_text, _, api_used = _call_responses_api(client, model, messages)
            print(
                f"[topics:openai] stage={stage} responses API OK chars={len(raw_text)}",
                flush=True,
            )
        except Exception as resp_exc:
            print(
                f"[topics:openai] stage={stage} responses API failed "
                f"({type(resp_exc).__name__}: {resp_exc}); falling back to chat.completions …",
                flush=True,
            )
            raw_text, _, api_used = _call_chat_completions(client, model, messages)
            print(
                f"[topics:openai] stage={stage} chat.completions OK chars={len(raw_text)}",
                flush=True,
            )
    except Exception as exc:
        print(
            f"[topics:openai] stage={stage} FAILED {type(exc).__name__}: {exc}",
            flush=True,
        )
        _raise_openai_error(exc)
        raise  # unreachable

    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"OpenAI stage '{stage}' returned non-JSON output") from exc

    topics, ai_meta = _parse_topics_payload(parsed)
    if not topics:
        raise ValueError(f"OpenAI stage '{stage}' returned no topics")

    print(
        f"[topics:openai] stage={stage} parsed topics={len(topics)} api={api_used}",
        flush=True,
    )

    ai_meta["stage"] = stage
    ai_meta["api"] = api_used
    return normalize_topics(topics), ai_meta


# ---------------------------------------------------------------------------
# Public stage entry points
# ---------------------------------------------------------------------------

def extract_topics_from_sitemap(
    client: OpenAI,
    model: str,
    metadata: dict[str, Any],
) -> tuple[list[dict], dict]:
    """API call 1: sitemap URLs → website niche topics."""
    if not (metadata.get("sitemap_urls") or []):
        raise ValueError("No sitemap URLs available for website topic extraction.")
    return _run_stage(
        client=client,
        model=model,
        stage="1_sitemap",
        system=SYSTEM_SITEMAP,
        user_content=build_sitemap_prompt(metadata),
        metadata=metadata,
    )


def expand_topics_with_specialty(
    client: OpenAI,
    model: str,
    metadata: dict[str, Any],
    sitemap_topics: list[dict],
) -> tuple[list[dict], dict]:
    """API call 2: sitemap topics + specialty → full weighted keyword list."""
    return _run_stage(
        client=client,
        model=model,
        stage="2_specialty",
        system=SYSTEM_SPECIALTY,
        user_content=build_specialty_prompt(metadata, sitemap_topics),
        metadata=metadata,
    )


def refine_topics_with_user_prompt(
    client: OpenAI,
    model: str,
    metadata: dict[str, Any],
) -> tuple[list[dict], dict]:
    """API call 3: existing list + specialty + user_prompt → revised list."""
    prompt = (metadata.get("user_prompt") or "").strip()
    if not prompt:
        raise ValueError("user_prompt is required to refine topics.")
    if not normalize_topics(metadata.get("existing_auto_topics") or []):
        raise ValueError("No existing auto topics to refine. Generate topics first.")
    return _run_stage(
        client=client,
        model=model,
        stage="3_user_prompt",
        system=SYSTEM_REFINE,
        user_content=build_refine_prompt(metadata),
        metadata=metadata,
    )


def generate_topics_with_openai(metadata: dict[str, Any]) -> tuple[list[dict], dict]:
    """
    Orchestrate the OpenAI stages:

    - If user_prompt is set → call 3 only (refine existing list).
    - Else → call 1 (sitemap) then call 2 (specialty expansion).
    """
    api_key = (settings.OPENAI_API_KEY or "").strip()
    if not api_key:
        raise ValueError(
            "OPENAI_API_KEY is not configured. Add it to .env to generate AI topics."
        )

    extraction_model = (
        getattr(settings, "OPENAI_EXTRACTION_MODEL", None) or settings.OPENAI_MODEL or "gpt-5.6-luna"
    ).strip() or "gpt-5.6-luna"
    generation_model = (
        getattr(settings, "OPENAI_GENERATION_MODEL", None) or settings.OPENAI_MODEL or "gpt-5.6-luna"
    ).strip() or "gpt-5.6-luna"
    # Connect/read timeouts so refresh cannot hang forever on a stalled OpenAI call
    client = OpenAI(api_key=api_key, timeout=120.0, max_retries=1)
    print(
        f"[topics:openai] client ready extraction={extraction_model!r} "
        f"generation={generation_model!r} "
        f"effort={settings.OPENAI_REASONING_EFFORT!r} timeout=120s max_retries=1",
        flush=True,
    )
    user_prompt = (metadata.get("user_prompt") or "").strip()

    # --- Stage 3 only: refine by user prompt ---
    if user_prompt:
        print("[topics:openai] running stage 3_user_prompt only", flush=True)
        topics, ai_meta = refine_topics_with_user_prompt(client, generation_model, metadata)
        ai_meta["stages_run"] = ["3_user_prompt"]
        return topics, ai_meta

    # --- Stages 1 + 2: sitemap → specialty keywords ---
    if not (metadata.get("sitemap_urls") or []):
        has_specialty = bool(metadata.get("specialty"))
        has_yt = bool(metadata.get("video_titles") or [])
        if not has_specialty and not has_yt:
            raise ValueError(
                "No sitemap URLs, specialty, or YouTube titles available to extract keywords from."
            )
        # Specialty-only or YouTube-only: skip sitemap stage
        print(
            f"[topics:openai] skip sitemap → stage 2_specialty "
            f"(specialty={has_specialty} yt_titles={has_yt})",
            flush=True,
        )
        sitemap_topics: list[dict] = []
        stages = ["2_specialty"]
        topics, ai_meta = expand_topics_with_specialty(
            client, generation_model, metadata, sitemap_topics
        )
        ai_meta["stages_run"] = stages
        ai_meta["sitemap_topic_count"] = 0
        return topics, ai_meta

    print(
        f"[topics:openai] stage 1_sitemap ({len(metadata.get('sitemap_urls') or [])} urls) …",
        flush=True,
    )
    sitemap_topics, sitemap_meta = extract_topics_from_sitemap(
        client, extraction_model, metadata
    )
    print(
        f"[topics:openai] stage 1 done topics={len(sitemap_topics)}; starting 2_specialty …",
        flush=True,
    )
    topics, ai_meta = expand_topics_with_specialty(
        client, generation_model, metadata, sitemap_topics
    )

    # Prefer specialty detection from either stage
    detected = ai_meta.get("detected_specialty") or sitemap_meta.get("detected_specialty")
    ai_meta["detected_specialty"] = detected
    ai_meta["stages_run"] = ["1_sitemap", "2_specialty"]
    ai_meta["sitemap_topic_count"] = len(sitemap_topics)
    ai_meta["sitemap_rationale"] = sitemap_meta.get("rationale")
    ai_meta["rationale"] = (
        f"Sitemap: {sitemap_meta.get('rationale') or ''} | "
        f"Specialty: {ai_meta.get('rationale') or ''}"
    ).strip(" |")
    return topics, ai_meta
