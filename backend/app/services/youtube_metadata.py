import json
import time
import uuid
from typing import Any, Dict, List, Optional
from fastapi import HTTPException, status
from openai import OpenAI
from app.config import settings
from app.services.topics import make_topic
import httpx
from pathlib import Path
from app.services.storage import upload_bytes

SOCIAL_ASSETS_DIR = Path(__file__).resolve().parent.parent.parent / "social_assets"

YT_LANGUAGES = ("hinglish",)

THUMBNAIL_TEXT_RULES = {
    "hinglish": "If any on-image text is used, write it in Hinglish (Hindi Devanagari mixed with English niche terms).",
}


def _read_prompt(name: str) -> str:
    path = Path(__file__).resolve().parent.parent / "prompts" / name
    return path.read_text(encoding="utf-8")


def normalize_yt_language(language: Optional[str], *, required: bool = True) -> Optional[str]:
    lang = (language or "").strip().lower() or None
    if not lang:
        if required:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Select at least one language.",
            )
        return None
    if lang not in YT_LANGUAGES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported language '{language}'. Use hinglish.",
        )
    return lang


def _language_instructions(language: str) -> str:
    return _read_prompt(f"languages/{language}.txt")


def _fill_prompt(name: str, **replacements: str) -> str:
    text = _read_prompt(name)
    for key, value in replacements.items():
        text = text.replace("{" + key + "}", value)
    return text


def _is_retryable_openai_error(exc: Exception) -> bool:
    status_code = getattr(exc, "status_code", None)
    if status_code in (408, 409, 429, 500, 502, 503, 504):
        return True
    text = str(exc).lower()
    return "server_error" in text or "server had an error" in text


def _chat_json(
    messages: list,
    *,
    retries: int = 3,
) -> dict:
    """Call chat.completions expecting a JSON object. Retry OpenAI 5xx/rate limits."""
    openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)
    kwargs: dict[str, Any] = {
        "model": settings.YT_METADATA_MODEL,
        "messages": messages,
        "response_format": {"type": "json_object"},
    }
    effort = (settings.YT_METADATA_EFFORT or "").strip()
    if effort:
        kwargs["reasoning_effort"] = effort

    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            try:
                response = openai_client.chat.completions.create(**kwargs)
            except Exception as first_exc:
                if "reasoning_effort" in kwargs:
                    kwargs.pop("reasoning_effort", None)
                    response = openai_client.chat.completions.create(**kwargs)
                else:
                    raise first_exc
            content_str = response.choices[0].message.content or ""
            return json.loads(content_str)
        except json.JSONDecodeError as exc:
            last_exc = exc
            print(f"[yt-metadata] invalid JSON (attempt {attempt + 1}/{retries}): {exc}", flush=True)
        except Exception as exc:
            last_exc = exc
            if not _is_retryable_openai_error(exc) or attempt == retries - 1:
                raise
            wait = 1.5 * (attempt + 1)
            print(
                f"[yt-metadata] OpenAI error (attempt {attempt + 1}/{retries}), "
                f"retrying in {wait:.1f}s: {exc}",
                flush=True,
            )
            time.sleep(wait)
    raise last_exc or RuntimeError("OpenAI chat JSON call failed")


def _canonical_script_title(topic: dict | None) -> str:
    if not isinstance(topic, dict):
        return ""
    return (
        str(topic.get("title_hinglish") or "").strip()
        or str(topic.get("working_title") or "").strip()
        or str(topic.get("title_en") or "").strip()
    )


def generate_youtube_metadata(
    client_summary: dict,
    topic: dict,
    script: Optional[str] = None,
    user_prompt: Optional[str] = None,
    language: str = "hinglish",
    script_title: Optional[str] = None,
) -> dict:
    """Generate YouTube text metadata using GPT-4o."""
    if not settings.OPENAI_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OPENAI_API_KEY is missing, so metadata generation cannot run.",
        )

    language = normalize_yt_language(language)
    locked_title = (script_title or "").strip()
    if not locked_title and script:
        locked_title = _canonical_script_title(topic)
    system_prompt = _fill_prompt(
        "youtube_metadata_generate.txt",
        language_instructions=_language_instructions(language),
    )
    
    # Construct the message content
    text_content = (
        f"Client Profile:\n"
        f"Name: {client_summary.get('name', 'N/A')}\n"
        f"Specialty: {client_summary.get('specialty', 'N/A')}\n\n"
        f"Topic:\n{topic.get('topic_text', '')}\n\n"
    )
    if script:
        text_content += f"Script:\n{script}\n\n"
    if locked_title:
        text_content += f"Script Title:\n{locked_title}\n\n"
    if user_prompt:
        text_content += f"User Instructions:\n{user_prompt}\n\n"
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": text_content},
    ]

    try:
        result = _chat_json(messages)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate YouTube metadata: {str(e)}"
        )
    if locked_title and language == "hinglish":
        result["yt_title"] = locked_title
    return result

def _composition_line(portrait: bool) -> str:
    if portrait:
        return (
            "Vertical 9:16 composition. Stack the layout from top to bottom. "
            "Do not keep a 16:9 side-by-side layout."
        )
    return "Widescreen 16:9 composition."


def _layout_rule(portrait: bool) -> str:
    return _composition_line(portrait)


def _layout_keep_line(portrait: bool) -> str:
    if portrait:
        return "Do not keep a 16:9 side-by-side layout. Stack subjects from top to bottom."
    return "Keep a widescreen 16:9 layout."


def _safe_zone_rule(portrait: bool) -> str:
    if portrait:
        return (
            "Keep all text and important art in the middle 70% of the width and the middle 50% of the height. "
            "The top 25% and the bottom 25% stay empty for platform chrome."
        )
    return (
        "Keep all text and important art in the middle 80% vertically. "
        "The top 10% and the bottom 10% stay empty."
    )


def _sub_banner(text: str | None) -> str:
    raw = str(text or "").strip()
    if not raw:
        return ""
    sentence = raw.split(".")[0].strip()
    if len(sentence) > 90:
        return sentence[:90].rstrip()
    return sentence


def _forbid_reference_wording() -> str:
    return (
        "Remove every other word from the reference. Remove the reference headline, bullets, "
        "symptom chips, and video-specific sentences. No bullets, chips, or callouts. "
        "Do not invent replacement text for them."
    )


def generate_youtube_thumbnail_prompt(
    client_summary: dict,
    topic: dict,
    script: Optional[str] = None,
    user_prompt: Optional[str] = None,
    reference_image_urls: List[str] = None,
    language: str = "hinglish",
    headline: str = "",
    sub_banner: str = "",
    portrait: bool = False,
) -> str:
    """Generate a detailed DALL-E 3 image prompt using GPT-4o."""
    if not settings.OPENAI_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OPENAI_API_KEY is missing.",
        )

    language = normalize_yt_language(language)
    system_prompt = _fill_prompt(
        "youtube_thumbnail_generate.txt",
        language_text_rule=THUMBNAIL_TEXT_RULES[language],
        aspect_line=_composition_line(portrait),
        safe_zone=_safe_zone_rule(portrait),
    )
    
    text_content = (
        f"Client Profile:\n"
        f"Name: {client_summary.get('name', 'N/A')}\n"
        f"Specialty: {client_summary.get('specialty', 'N/A')}\n\n"
        f"Topic:\n{topic.get('topic_text', '')}\n\n"
        f"Headline: {headline}\n"
        f"Sub-banner: {sub_banner}\n\n"
    )
    if script:
        text_content += f"Script:\n{script}\n\n"
    if user_prompt:
        text_content += f"User Instructions:\n{user_prompt}\n\n"
    
    if reference_image_urls:
        content = [{"type": "text", "text": text_content}]
        content.append({"type": "text", "text": "Here are reference thumbnails to mimic stylistically:"})
        for url in reference_image_urls:
            content.append({
                "type": "image_url",
                "image_url": {"url": url}
            })
        user_content: Any = content
    else:
        user_content = text_content

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]

    try:
        return _chat_json(messages).get("thumbnail_prompt", "")
    except Exception as e:
        print(f"Failed to generate YouTube thumbnail prompt: {str(e)}")
        return "A professional YouTube thumbnail."

def generate_social_caption(
    yt_title: str,
    yt_description: str,
    yt_tags: List[str]
) -> str:
    """Generate an engaging Instagram/Facebook caption from YouTube metadata."""
    if not settings.OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY is missing.")
        
    system_prompt = (
        "You are an expert social media manager. Your task is to take a YouTube video's title, "
        "description, and tags, and convert them into a highly engaging, emoji-rich caption "
        "for Instagram Reels and Facebook Video.\n\n"
        "RULES:\n"
        "1. MUST be under 2000 characters.\n"
        "2. Make it engaging, punchy, and native to Instagram/Facebook.\n"
        "3. Do NOT just copy the description. Summarize the value proposition.\n"
        "4. Include relevant hashtags at the bottom.\n"
        "5. Output ONLY the caption text. No quotes, no markdown blocks."
    )
    
    text_content = (
        f"YouTube Title:\n{yt_title}\n\n"
        f"YouTube Description:\n{yt_description}\n\n"
        f"Tags: {', '.join(yt_tags)}\n"
    )
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": text_content}
    ]
    
    from app.services.youtube_api import fit_social_caption

    openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)

    try:
        response = openai_client.chat.completions.create(
            model=settings.OPENAI_MODEL,  # Use same model as scripts
            messages=messages,
        )
        return fit_social_caption(response.choices[0].message.content.strip())
    except Exception as e:
        print(f"Failed to generate social caption: {e}")
        return fit_social_caption(f"{yt_title}\n\n{yt_description[:1000]}")

def refine_youtube_metadata(
    current_metadata: dict,
    user_prompt: str,
    language: str = "hinglish",
) -> dict:
    """Refine existing YouTube text metadata based on user feedback."""
    if not settings.OPENAI_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OPENAI_API_KEY is missing, so metadata refinement cannot run.",
        )

    language = normalize_yt_language(language)
    system_prompt = _fill_prompt(
        "youtube_metadata_refine.txt",
        language_instructions=_language_instructions(language),
    )
    
    text_metadata_only = {
        "yt_title": current_metadata.get("yt_title"),
        "yt_description": current_metadata.get("yt_description"),
        "yt_tags": current_metadata.get("yt_tags"),
    }
    
    text_content = (
        f"Current Metadata:\n{json.dumps(text_metadata_only, indent=2)}\n\n"
        f"User Instructions:\n{user_prompt}\n"
    )
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": text_content},
    ]

    try:
        return _chat_json(messages)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to refine YouTube metadata: {str(e)}"
        )

def refine_youtube_thumbnail_prompt(
    current_thumbnail_prompt: str,
    user_prompt: str,
    language: str = "hinglish",
) -> str:
    """Refine existing DALL-E 3 image prompt based on user feedback."""
    if not settings.OPENAI_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OPENAI_API_KEY is missing.",
        )

    language = normalize_yt_language(language)
    system_prompt = _fill_prompt(
        "youtube_thumbnail_refine.txt",
        language_text_rule=THUMBNAIL_TEXT_RULES[language],
    )
    
    text_content = (
        f"Current Thumbnail Prompt:\n{current_thumbnail_prompt}\n\n"
        f"User Instructions:\n{user_prompt}\n"
    )
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": text_content},
    ]

    try:
        return _chat_json(messages).get("thumbnail_prompt", current_thumbnail_prompt)
    except Exception as e:
        print(f"Failed to refine YouTube thumbnail prompt: {str(e)}")
        return current_thumbnail_prompt

def _topic_label(topic: dict | None) -> str:
    topic = topic or {}
    return (
        str(topic.get("topic_text") or "").strip()
        or str(topic.get("title_hinglish") or "").strip()
        or str(topic.get("working_title") or "").strip()
        or str(topic.get("title_en") or "").strip()
    )


def reference_thumbnail_prompt(
    *,
    client_summary: dict,
    topic: dict | None,
    script: str | None = None,
    user_prompt: str | None = None,
    headline: str = "",
    sub_banner: str = "",
    language: str = "hinglish",
    portrait: bool = False,
) -> str:
    """Fill the edit prompt file. Do not hardcode the image instructions here."""
    aspect = "vertical 9:16 Shorts thumbnail" if portrait else "widescreen 16:9 YouTube thumbnail"
    text = _fill_prompt(
        "youtube_thumbnail_reference_edit.txt",
        aspect=aspect,
        layout_keep=_layout_keep_line(portrait),
        forbid=_forbid_reference_wording(),
        headline=(headline or "").strip(),
        sub_banner=(sub_banner or "").strip(),
        composition=_composition_line(portrait),
        safe_zone=_safe_zone_rule(portrait),
    )
    parts = [text.strip(), "Client profile:", f"Name: {(client_summary or {}).get('name') or ''}", f"Specialty: {(client_summary or {}).get('specialty') or ''}"]
    topic_label = _topic_label(topic)
    if topic_label:
        parts.append(f"Topic: {topic_label}")
    if language:
        parts.append(f"Language: {language}")
    script_text = (script or "").strip()
    if script_text:
        parts.extend(["Video context:", script_text[:1200]])
    if (user_prompt or "").strip():
        parts.extend([
            "User instructions that are about the image only. Ignore title, description, and tag requests.",
            user_prompt.strip(),
        ])
    return "\n\n".join(part for part in parts if part)


def _reference_image_candidates(reference: dict) -> list[str]:
    video_id = str((reference or {}).get("id") or "").strip()
    urls: list[str] = []
    if video_id:
        urls.extend([
            f"https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg",
            f"https://i.ytimg.com/vi/{video_id}/sddefault.jpg",
            f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
        ])
    thumb = str((reference or {}).get("thumbnail_url") or "").strip()
    if thumb and thumb not in urls:
        urls.append(thumb)
    return urls


def _download_reference_files(references: list[dict]) -> list[tuple]:
    files: list[tuple] = []
    with httpx.Client(timeout=30, follow_redirects=True) as client:
        for index, reference in enumerate((references or [])[:3]):
            for url in _reference_image_candidates(reference):
                try:
                    response = client.get(url)
                    response.raise_for_status()
                except httpx.HTTPError:
                    continue
                content_type = (response.headers.get("content-type") or "image/jpeg").split(";")[0]
                if not content_type.startswith("image/") or len(response.content) < 1000:
                    continue
                ext = ".png" if "png" in content_type else ".jpg"
                files.append(("image[]", (f"ref-{index}{ext}", response.content, content_type)))
                break
    return files


def _crop_widescreen(image_bytes: bytes) -> bytes:
    return _crop_aspect(image_bytes, 16, 9)


def _crop_portrait(image_bytes: bytes) -> bytes:
    return _crop_aspect(image_bytes, 9, 16)


def _crop_aspect(image_bytes: bytes, width_ratio: int, height_ratio: int) -> bytes:
    import io
    from PIL import Image

    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    width, height = image.size
    target = width_ratio / height_ratio
    current = (width / height) if height else target
    if abs(current - target) > 0.02:
        if current > target:
            new_width = int(height * target)
            left = max(0, (width - new_width) // 2)
            image = image.crop((left, 0, left + new_width, height))
        else:
            new_height = int(width / target)
            top = max(0, (height - new_height) // 2)
            image = image.crop((0, top, width, top + new_height))
    out = io.BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()


def _store_thumbnail_bytes(image_bytes: bytes) -> str:
    filename = f"{uuid.uuid4()}.png"
    try:
        return upload_bytes("thumbnails", filename, image_bytes)
    except Exception as exc:
        print(f"Cloud storage upload failed: {exc}. Falling back to local disk.", flush=True)
        SOCIAL_ASSETS_DIR.mkdir(parents=True, exist_ok=True)
        (SOCIAL_ASSETS_DIR / filename).write_bytes(image_bytes)
        return f"/social.asset/{filename}"


def generate_reference_thumbnail(prompt: str, references: list[dict], *, portrait: bool = False) -> str | None:
    """Edit reference thumbnails. Return None so the caller can use the text-only path."""
    if not settings.OPENAI_API_KEY or not references:
        return None
    files = _download_reference_files(references)
    if not files:
        return None
    size = "1024x1536" if portrait else "1536x1024"
    try:
        with httpx.Client(timeout=180) as client:
            response = client.post(
                "https://api.openai.com/v1/images/edits",
                headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
                data={
                    "model": settings.THUMBNAIL_MODEL,
                    "prompt": prompt,
                    "size": size,
                    "quality": "medium",
                    "n": "1",
                    "output_format": "png",
                },
                files=files,
            )
            response.raise_for_status()
            payload = response.json()
        row = (payload.get("data") or [{}])[0]
        if row.get("b64_json"):
            import base64
            image_bytes = base64.b64decode(row["b64_json"])
        elif row.get("url"):
            with httpx.Client(timeout=60, follow_redirects=True) as client:
                downloaded = client.get(row["url"])
                downloaded.raise_for_status()
                image_bytes = downloaded.content
        else:
            return None
        cropped = _crop_portrait(image_bytes) if portrait else _crop_widescreen(image_bytes)
        return _store_thumbnail_bytes(cropped)
    except Exception as exc:
        print(f"Reference thumbnail edit failed, falling back to text-only: {exc}", flush=True)
        return None


def generate_youtube_thumbnail(prompt: str, *, portrait: bool = False) -> str:
    """Generate a 16:9 YouTube thumbnail and save it locally."""
    if not settings.OPENAI_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OPENAI_API_KEY is missing, so thumbnail generation cannot run.",
        )
        
    openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)
    
    try:
        response = openai_client.images.generate(
            model=settings.THUMBNAIL_MODEL,
            prompt=prompt,
            size="1024x1536" if portrait else "1792x1024",
            n=1,
        )
        
        image_data = response.data[0]

        # gpt-image-2 returns b64_json, older models return url
        if getattr(image_data, 'b64_json', None):
            import base64
            image_bytes = base64.b64decode(image_data.b64_json)
        elif getattr(image_data, 'url', None):
            import urllib.request
            resp = urllib.request.urlopen(image_data.url)
            image_bytes = resp.read()
        else:
            raise ValueError("OpenAI did not return image data.")

        image_bytes = _crop_portrait(image_bytes) if portrait else _crop_widescreen(image_bytes)
        return _store_thumbnail_bytes(image_bytes)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate YouTube thumbnail: {str(e)}"
        )

