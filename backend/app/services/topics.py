"""Topic helpers + sitemap URL discovery for AI keyword extraction."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

import httpx

WEIGHTS = ("high", "medium", "low")
SOURCES = ("manual", "auto")

# Optional Google Trends fields preserved across normalize / merge
TREND_FIELDS = (
    "trend_score",
    "trend_confidence",
    "trend_geo",
    "web_interest",
    "youtube_interest",
    "momentum",
    "rising_flag",
    "trend_fetched_at",
)

# Combined recommendation fields (practice priority + trend)
RECOMMENDATION_FIELDS = (
    "recommendation_score",
    "priority_points",
    "trend_points",
    "recommendation_saved_at",
)

WEIGHT_POINTS = {"high": 50, "medium": 30, "low": 10}
SCORE_FIELDS = TREND_FIELDS + RECOMMENDATION_FIELDS

USER_AGENT = (
    "Mozilla/5.0 (compatible; GravityClientBot/1.0; +https://localhost) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# Path segments that mark blog / article / news content — skip these URLs
BLOG_PATH_MARKERS = (
    "/blog/",
    "/blogs/",
    "/blog-",
    "/article/",
    "/articles/",
    "/news/",
    "/post/",
    "/posts/",
    "/press/",
    "/media/",
    "/stories/",
    "/story/",
    "/insights/",
    "/resources/blog",
    "/category/",
    "/tag/",
    "/author/",
    "/wp/",
)

BLOG_SLUG_RE = re.compile(
    r"(^|/)(blog|blogs|article|articles|news|post|posts|press)(/|$)",
    re.I,
)


def new_topic_id() -> str:
    return str(uuid.uuid4())


def make_topic(text: str, weight: str = "medium", source: str = "auto") -> dict:
    cleaned = re.sub(r"\s+", " ", (text or "").strip())
    weight = weight if weight in WEIGHTS else "medium"
    source = source if source in SOURCES else "auto"
    return {
        "id": new_topic_id(),
        "text": cleaned,
        "weight": weight,
        "source": source,
    }


def _copy_trend_fields(target: dict, source: dict | None) -> dict:
    """Copy optional trend + recommendation fields from source onto target when present."""
    if not isinstance(source, dict):
        return target
    for field in SCORE_FIELDS:
        if field in source and source[field] is not None:
            target[field] = source[field]
    return target


def recommendation_score_for(topic: dict) -> dict:
    """Compute priority / trend / combined recommendation points for one topic."""
    weight = topic.get("weight") if topic.get("weight") in WEIGHT_POINTS else "medium"
    priority = float(WEIGHT_POINTS[weight])
    raw_trend = topic.get("trend_score")
    try:
        trend_score = float(raw_trend) if raw_trend is not None else None
    except (TypeError, ValueError):
        trend_score = None
    trend_points = round((trend_score / 100.0) * 50.0, 1) if trend_score is not None else 0.0
    combined = round(priority + trend_points, 1)
    return {
        "priority_points": priority,
        "trend_points": trend_points,
        "recommendation_score": combined,
    }


def apply_recommendation_scores(
    topics: list[dict],
    *,
    saved_at: str | None = None,
) -> list[dict]:
    """Attach combined recommendation scores to each topic and sort by score desc."""
    stamp = saved_at or datetime.now(timezone.utc).isoformat()
    updated: list[dict] = []
    for topic in topics:
        row = dict(topic)
        scores = recommendation_score_for(row)
        row.update(scores)
        row["recommendation_saved_at"] = stamp
        updated.append(row)
    updated.sort(
        key=lambda t: (
            -(float(t.get("recommendation_score") or 0)),
            (t.get("text") or "").lower(),
        )
    )
    return updated


def normalize_topics(raw) -> list[dict]:
    """Migrate legacy string lists / partial dicts into topic objects."""
    if not raw:
        return []
    out: list[dict] = []
    seen: set[str] = set()

    items = raw
    if isinstance(raw, dict):
        items = []
        for weight in WEIGHTS:
            for t in raw.get(weight, []) or []:
                if isinstance(t, str):
                    items.append({"text": t, "weight": weight, "source": "auto"})
                elif isinstance(t, dict):
                    items.append({**t, "weight": t.get("weight") or weight})

    for item in items:
        if isinstance(item, str):
            topic = make_topic(item, "medium", "manual")
        elif isinstance(item, dict):
            text = (item.get("text") or item.get("title") or "").strip()
            if not text:
                continue
            topic = make_topic(
                text,
                item.get("weight") or "medium",
                item.get("source") or "manual",
            )
            if item.get("id"):
                topic["id"] = str(item["id"])
            _copy_trend_fields(topic, item)
        else:
            continue

        key = topic["text"].lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(topic)
    return out


def merge_topics(
    manual: list[dict],
    auto: list[dict],
    *,
    previous: list[dict] | None = None,
) -> list[dict]:
    """Keep all manual topics; add auto topics that don't collide on text.

    When previous topics exist, re-attach trend fields by case-insensitive text match
    so a refresh does not wipe scored data for unchanged keywords.
    """
    prev_by_text = {
        t["text"].lower(): t
        for t in normalize_topics(previous or [])
        if t.get("text")
    }
    manuals = [t for t in normalize_topics(manual) if t.get("source") == "manual"]
    for topic in manuals:
        _copy_trend_fields(topic, prev_by_text.get(topic["text"].lower()))
    seen = {t["text"].lower() for t in manuals}
    result = list(manuals)
    for topic in normalize_topics(auto):
        topic = {**topic, "source": "auto"}
        key = topic["text"].lower()
        if key in seen:
            continue
        seen.add(key)
        _copy_trend_fields(topic, prev_by_text.get(key))
        result.append(topic)
    return result


def _normalize_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        raise ValueError("Website URL is required")
    if not urlparse(url).scheme:
        url = "https://" + url
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("Invalid website URL")
    return url


def _same_host(base: str, other: str) -> bool:
    return urlparse(base).netloc.lower().lstrip("www.") == urlparse(other).netloc.lower().lstrip("www.")


def _origin(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def is_blog_or_article_url(url: str) -> bool:
    """True for blog/news/article URLs we should not send to the keyword model."""
    path = (urlparse(url).path or "").lower()
    if not path or path in ("/",):
        return False
    padded = path if path.endswith("/") else path + "/"
    if any(marker in padded for marker in BLOG_PATH_MARKERS):
        return True
    if BLOG_SLUG_RE.search(path):
        return True
    # Date-style blog permalinks: /2024/03/15/slug or /2024/03/slug
    if re.search(r"/20\d{2}/\d{1,2}/", path):
        return True
    return False


def _fetch_text(client: httpx.Client, url: str) -> str | None:
    try:
        response = client.get(url, headers={"User-Agent": USER_AGENT})
        response.raise_for_status()
        return response.text
    except httpx.HTTPError:
        return None


def _discover_sitemap_urls(client: httpx.Client, site_url: str) -> list[str]:
    origin = _origin(site_url)
    found: list[str] = []
    seen: set[str] = set()

    def add(u: str) -> None:
        u = u.strip()
        if not u or u in seen:
            return
        seen.add(u)
        found.append(u)

    robots = _fetch_text(client, urljoin(origin + "/", "robots.txt"))
    if robots:
        for line in robots.splitlines():
            if line.lower().startswith("sitemap:"):
                add(line.split(":", 1)[1].strip())

    for path in (
        "/sitemap.xml",
        "/sitemap_index.xml",
        "/sitemap-index.xml",
        "/sitemaps.xml",
        "/sitemap/sitemap.xml",
        "/wp-sitemap.xml",
    ):
        add(urljoin(origin + "/", path.lstrip("/")))

    return found


def _local_name(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[-1]
    return tag


def _parse_sitemap_xml(xml_text: str) -> tuple[list[str], list[str]]:
    import xml.etree.ElementTree as ET

    page_urls: list[str] = []
    nested: list[str] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return [], []

    root_name = _local_name(root.tag).lower()

    if root_name == "sitemapindex":
        for child in list(root):
            if _local_name(child.tag).lower() != "sitemap":
                continue
            for sub in list(child):
                if _local_name(sub.tag).lower() == "loc" and (sub.text or "").strip():
                    nested.append(sub.text.strip())
        return page_urls, nested

    if root_name == "urlset":
        for child in list(root):
            if _local_name(child.tag).lower() != "url":
                continue
            for sub in list(child):
                if _local_name(sub.tag).lower() == "loc" and (sub.text or "").strip():
                    page_urls.append(sub.text.strip())
        return page_urls, nested

    for el in root.iter():
        if _local_name(el.tag).lower() == "loc" and (el.text or "").strip():
            page_urls.append(el.text.strip())
    return page_urls, nested


def collect_sitemap_urls(
    website_url: str,
    *,
    max_urls: int = 2000,
    max_sitemaps: int = 50,
) -> dict:
    """
    Discover as many same-host sitemap URLs as possible.
    Drops blog/article/news URLs. Does not fetch HTML pages.
    """
    url = _normalize_url(website_url)

    seed_sitemaps: list[str] = []
    fetched_sitemaps: list[str] = []
    failed_sitemaps: list[str] = []
    all_urls: list[str] = []
    kept_urls: list[str] = []
    skipped_blog_urls: list[str] = []

    try:
        with httpx.Client(follow_redirects=True, timeout=20.0) as client:
            print(f"[topics:sitemap] discover seeds for {url!r} …", flush=True)
            seed_sitemaps = _discover_sitemap_urls(client, url)
            print(f"[topics:sitemap] seeds={len(seed_sitemaps)}", flush=True)
            queue = list(seed_sitemaps)
            seen_sitemaps: set[str] = set()
            seen_pages: set[str] = set()

            while queue and len(fetched_sitemaps) < max_sitemaps and len(all_urls) < max_urls:
                sm_url = queue.pop(0)
                if sm_url in seen_sitemaps:
                    continue
                seen_sitemaps.add(sm_url)

                print(
                    f"[topics:sitemap] fetch ({len(fetched_sitemaps)+1}/{max_sitemaps}) {sm_url}",
                    flush=True,
                )
                text = _fetch_text(client, sm_url)
                if not text or (
                    not text.lstrip().startswith("<") and "<?xml" not in text[:200]
                ):
                    failed_sitemaps.append(sm_url)
                    print(f"[topics:sitemap] skip/fail {sm_url}", flush=True)
                    continue

                fetched_sitemaps.append(sm_url)
                pages, nested = _parse_sitemap_xml(text)
                for nest in nested:
                    if nest not in seen_sitemaps:
                        queue.append(nest)
                for page in pages:
                    if not _same_host(url, page):
                        continue
                    clean = page.split("#")[0].rstrip("/")
                    if clean in seen_pages:
                        continue
                    seen_pages.add(clean)
                    all_urls.append(page)
                    if is_blog_or_article_url(page):
                        skipped_blog_urls.append(page)
                    else:
                        kept_urls.append(page)
                    if len(all_urls) >= max_urls:
                        break
            print(
                f"[topics:sitemap] loop done fetched={len(fetched_sitemaps)} "
                f"kept={len(kept_urls)} blog={len(skipped_blog_urls)} failed={len(failed_sitemaps)}",
                flush=True,
            )
    except httpx.HTTPError as exc:
        raise ValueError(f"Could not fetch sitemaps: {exc}") from exc

    if not kept_urls and not all_urls:
        raise ValueError(
            "No sitemap URLs found. Ensure the site exposes sitemap.xml or a Sitemap entry in robots.txt."
        )

    result = {
        "website_url": url,
        "urls": kept_urls,
        "urls_total_from_sitemap": len(all_urls),
        "urls_kept": len(kept_urls),
        "urls_skipped_blog": len(skipped_blog_urls),
        "pages_scraped": len(kept_urls),
        "crawl_meta": {
            "seed_sitemaps": seed_sitemaps,
            "fetched_sitemaps": fetched_sitemaps,
            "failed_sitemaps": failed_sitemaps,
        },
        "page_snippet": (
            f"Sitemap: {len(all_urls)} URLs found, {len(kept_urls)} kept "
            f"(skipped {len(skipped_blog_urls)} blog/article URLs)."
        ),
    }

    return result


# Back-compat alias used by older call sites
def deep_scrape_website(website_url: str, specialty: str | None = None) -> dict:
    del specialty  # unused — specialty comes from the client / AI
    scraped = collect_sitemap_urls(website_url)
    return {
        "specialty": None,
        "page_title": None,
        "page_titles": [],
        "page_snippet": scraped["page_snippet"],
        "headings": [],
        "phrases": [],
        "pages_scraped": scraped["pages_scraped"],
        "sitemap_urls": scraped["urls"],
        "urls": scraped["urls"],
    }


def generate_auto_topics(
    *,
    specialty: str | None = None,
    website_url: str | None = None,
    video_titles: list[str] | None = None,
    client_name: str | None = None,
    client_id: str | None = None,
    description: str | None = None,
    channel_titles: list[str] | None = None,
    manual_topics: list | None = None,
    existing_auto_topics: list | None = None,
    user_prompt: str | None = None,
    use_openai: bool = True,
) -> tuple[list[dict], dict]:
    """
    OpenAI topic pipeline:

    - With user_prompt: stage 3 only (refine existing auto list).
    - Without: sitemap crawl → stage 1 (URLs→topics) → stage 2 (topics+specialty).

    Returns (topics, scrape_meta).
    """
    refine_only = bool((user_prompt or "").strip())
    scrape_meta: dict = {
        "specialty": specialty,
        "page_title": None,
        "page_snippet": None,
        "pages_scraped": 0,
        "urls_kept": 0,
        "mode": "refine_user_prompt" if refine_only else "sitemap_urls_only",
        "generator": "none",
    }
    sitemap_urls: list[str] = []

    # Stage 3 does not need a fresh sitemap crawl
    if not refine_only and website_url and website_url.strip():
        print(f"[topics] sitemap crawl start {website_url.strip()!r}", flush=True)
        try:
            scraped = collect_sitemap_urls(website_url.strip())
            sitemap_urls = scraped.get("urls") or []
            scrape_meta.update(
                {
                    "page_snippet": scraped.get("page_snippet"),
                    "pages_scraped": scraped.get("pages_scraped", 0),
                    "urls_kept": scraped.get("urls_kept", 0),
                    "urls_total_from_sitemap": scraped.get("urls_total_from_sitemap", 0),
                    "urls_skipped_blog": scraped.get("urls_skipped_blog", 0),
                }
            )
            print(
                f"[topics] sitemap crawl done kept={len(sitemap_urls)} "
                f"total={scraped.get('urls_total_from_sitemap')} "
                f"blog_skipped={scraped.get('urls_skipped_blog')}",
                flush=True,
            )
        except ValueError as exc:
            scrape_meta["page_snippet"] = str(exc)
            print(f"[topics] sitemap crawl error: {exc}", flush=True)
    elif refine_only:
        scrape_meta["page_snippet"] = "Refining existing auto topics from user prompt only."
        print("[topics] refine-only — skip sitemap", flush=True)
    else:
        print("[topics] no website_url — skip sitemap", flush=True)

    metadata = {
        "client_id": client_id,
        "client_name": client_name,
        "specialty": specialty,
        "description": description,
        "website_url": website_url,
        "sitemap_urls": sitemap_urls,
        "page_snippet": scrape_meta.get("page_snippet"),
        "pages_scraped": scrape_meta.get("pages_scraped"),
        "video_titles": video_titles or [],
        "channel_titles": channel_titles or [],
        "manual_topics": normalize_topics(manual_topics or []),
        "existing_auto_topics": normalize_topics(existing_auto_topics or []),
        "user_prompt": (user_prompt or "").strip() or None,
    }

    if not use_openai:
        scrape_meta["generator"] = "skipped"
        return [], scrape_meta

    from app.config import settings

    if not (settings.OPENAI_API_KEY or "").strip():
        scrape_meta["generator"] = "none"
        scrape_meta["openai_error"] = "OPENAI_API_KEY is not configured"
        scrape_meta["page_snippet"] = (
            (scrape_meta.get("page_snippet") or "")
            + " OpenAI key missing — no keywords generated."
        ).strip()
        return [], scrape_meta

    from app.services.openai_topics import generate_topics_with_openai

    try:
        print(
            f"[topics] OpenAI pipeline start extraction={settings.OPENAI_EXTRACTION_MODEL!r} "
            f"generation={settings.OPENAI_GENERATION_MODEL!r} "
            f"sitemap_urls={len(sitemap_urls)} specialty={bool(specialty)} "
            f"video_titles={len(metadata.get('video_titles') or [])} "
            f"refine_only={refine_only}",
            flush=True,
        )
        ai_topics, ai_meta = generate_topics_with_openai(metadata)
        print(
            f"[topics] OpenAI pipeline done topics={len(ai_topics)} "
            f"stages={ai_meta.get('stages_run')}",
            flush=True,
        )
        if ai_meta.get("detected_specialty") and not specialty:
            specialty = ai_meta["detected_specialty"]
            scrape_meta["specialty"] = specialty
        scrape_meta["generator"] = "openai"
        scrape_meta["openai_model"] = ai_meta.get("model")
        scrape_meta["openai_rationale"] = ai_meta.get("rationale")
        scrape_meta["openai_stages"] = ai_meta.get("stages_run") or []
        scrape_meta["sitemap_topic_count"] = ai_meta.get("sitemap_topic_count")
        scrape_meta["specialty"] = specialty or scrape_meta.get("specialty")
        scrape_meta["user_prompt_applied"] = refine_only
        return ai_topics, scrape_meta
    except ValueError as exc:
        scrape_meta["generator"] = "none"
        scrape_meta["openai_error"] = str(exc)
        scrape_meta["page_snippet"] = (
            f"{scrape_meta.get('page_snippet') or ''} OpenAI failed: {exc}"
        ).strip()
        return [], scrape_meta


def scrape_doctor_website(website_url: str) -> dict:
    topics, meta = generate_auto_topics(website_url=website_url)
    return {
        "specialty": meta.get("specialty"),
        "suggested_topics": topics,
        "page_title": meta.get("page_title"),
        "page_snippet": meta.get("page_snippet"),
        "pages_scraped": meta.get("pages_scraped", 0),
    }
