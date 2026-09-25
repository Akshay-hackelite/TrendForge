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

def generate_youtube_thumbnail_prompt(
    client_summary: dict,
    topic: dict,
    script: Optional[str] = None,
    user_prompt: Optional[str] = None,
    reference_image_urls: List[str] = None,
    language: str = "hinglish",
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
    )
    
    text_content = (
        f"Client Profile:\n"
        f"Name: {client_summary.get('name', 'N/A')}\n"
        f"Specialty: {client_summary.get('specialty', 'N/A')}\n\n"
        f"Topic:\n{topic.get('topic_text', '')}\n\n"
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
    
    openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)
    
    try:
        response = openai_client.chat.completions.create(
            model=settings.OPENAI_MODEL,  # Use same model as scripts
            messages=messages,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"Failed to generate social caption: {e}")
        return f"{yt_title}\n\n{yt_description[:1000]}"

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

def generate_youtube_thumbnail(prompt: str) -> str:
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
            size="1792x1024",
            n=1,
        )
        
        image_data = response.data[0]
        filename = f"{uuid.uuid4()}.png"
        
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
            
        try:
            public_url = upload_bytes("thumbnails", filename, image_bytes)
            return public_url
        except Exception as e:
            print(f"Cloud storage upload failed: {e}. Falling back to local disk.")
            SOCIAL_ASSETS_DIR.mkdir(parents=True, exist_ok=True)
            path = SOCIAL_ASSETS_DIR / filename
            path.write_bytes(image_bytes)
            return f"/social.asset/{filename}"
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate YouTube thumbnail: {str(e)}"
        )

