"""Fetch public YouTube channel video titles without OAuth / API keys.

Uses the public channel page (to resolve @handles → UC…) and the built-in
Atom RSS feed: https://www.youtube.com/feeds/videos.xml?channel_id=UC…
(~15 most recent public uploads).
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

import httpx

USER_AGENT = (
    "Mozilla/5.0 (compatible; GravityKeywordBot/1.0; +https://localhost) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
CHANNEL_ID_RE = re.compile(r"(UC[\w-]{22})")
# Common patterns in channel HTML / ytInitialData
CHANNEL_ID_HTML_PATTERNS = [
    # Prefer stable channel-page identifiers; avoid first "channelId" (often unrelated)
    re.compile(r'<link\s+rel="canonical"\s+href="[^"]*?/channel/(UC[\w-]{22})"', re.I),
    re.compile(r'"externalId"\s*:\s*"(UC[\w-]{22})"'),
    re.compile(r'"browseId"\s*:\s*"(UC[\w-]{22})"'),
    re.compile(r'<meta\s+itemprop="channelId"\s+content="(UC[\w-]{22})"', re.I),
    re.compile(r'"channelId"\s*:\s*"(UC[\w-]{22})"'),
    re.compile(r'/channel/(UC[\w-]{22})'),
]
ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}


def normalize_channel_input(raw: str | None) -> str | None:
    text = (raw or "").strip()
    if not text:
        return None
    if text.startswith("@"):
        return f"https://www.youtube.com/{text}"
    if CHANNEL_ID_RE.fullmatch(text):
        return f"https://www.youtube.com/channel/{text}"
    if text.startswith("youtube.com") or text.startswith("www.youtube.com"):
        return f"https://{text}"
    if text.startswith("http://") or text.startswith("https://"):
        return text
    # Bare handle without @
    if re.fullmatch(r"[\w.-]{2,}", text) and " " not in text and "/" not in text:
        return f"https://www.youtube.com/@{text}"
    return text


def extract_channel_id_from_url(url: str) -> str | None:
    parsed = urlparse(url)
    path = unquote(parsed.path or "")

    m = re.search(r"/channel/(UC[\w-]{22})", path)
    if m:
        return m.group(1)

    qs = parse_qs(parsed.query or "")
    for key in ("channel_id", "channelId"):
        vals = qs.get(key) or []
        if vals and CHANNEL_ID_RE.fullmatch(vals[0]):
            return vals[0]

    # Raw UC in path segment
    for part in path.strip("/").split("/"):
        if CHANNEL_ID_RE.fullmatch(part):
            return part
    return None


def extract_channel_id_from_html(html: str) -> str | None:
    for pattern in CHANNEL_ID_HTML_PATTERNS:
        m = pattern.search(html)
        if m:
            return m.group(1)
    return None


def resolve_channel_id(channel_ref: str, *, timeout: float = 20.0) -> dict[str, Any]:
    """Resolve a channel URL / @handle / UC id to a channel ID."""
    normalized = normalize_channel_input(channel_ref)
    if not normalized:
        raise ValueError("Reference YouTube channel is empty.")

    direct = extract_channel_id_from_url(normalized)
    if direct:
        return {
            "channel_id": direct,
            "resolved_url": f"https://www.youtube.com/channel/{direct}",
            "input": channel_ref.strip(),
        }

    print(f"[topics:yt] resolve channel page {normalized!r} …", flush=True)
    headers = {"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"}
    with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as client:
        resp = client.get(normalized)
        if resp.status_code >= 400:
            raise ValueError(
                f"Could not open YouTube channel page (HTTP {resp.status_code}). "
                "Use a public channel URL or @handle."
            )
        channel_id = extract_channel_id_from_html(resp.text)
        if not channel_id:
            # Final URL after redirects may contain /channel/UC…
            channel_id = extract_channel_id_from_url(str(resp.url))
        if not channel_id:
            raise ValueError(
                "Could not resolve channel ID from that YouTube link. "
                "Try a /channel/UC… URL or @handle."
            )
        print(f"[topics:yt] resolved channel_id={channel_id}", flush=True)
        return {
            "channel_id": channel_id,
            "resolved_url": f"https://www.youtube.com/channel/{channel_id}",
            "input": channel_ref.strip(),
            "page_url": str(resp.url),
        }


def fetch_rss_video_titles(channel_id: str, *, timeout: float = 20.0) -> list[str]:
    """Return recent public upload titles from the channel Atom feed (no API key)."""
    if not CHANNEL_ID_RE.fullmatch(channel_id or ""):
        raise ValueError("Invalid YouTube channel ID.")

    feed_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    print(f"[topics:yt] fetch RSS {feed_url}", flush=True)
    headers = {"User-Agent": USER_AGENT, "Accept": "application/atom+xml,application/xml,text/xml"}
    with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as client:
        resp = client.get(feed_url)
        if resp.status_code >= 400:
            raise ValueError(
                f"YouTube RSS feed unavailable (HTTP {resp.status_code}). "
                "Channel may be invalid or restricted."
            )
        text = resp.text

    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise ValueError("YouTube RSS feed was not valid XML.") from exc

    titles: list[str] = []
    seen: set[str] = set()
    for entry in root.findall("atom:entry", ATOM_NS):
        title_el = entry.find("atom:title", ATOM_NS)
        title = (title_el.text or "").strip() if title_el is not None else ""
        if not title:
            continue
        key = title.lower()
        if key in seen:
            continue
        seen.add(key)
        titles.append(title)

    # Fallback without namespaces (some parsers strip them)
    if not titles:
        for entry in root.iter():
            if entry.tag.endswith("entry") or entry.tag == "entry":
                for child in entry:
                    if child.tag.endswith("title") or child.tag == "title":
                        title = (child.text or "").strip()
                        if title and title.lower() not in seen:
                            seen.add(title.lower())
                            titles.append(title)
                        break

    return titles


def fetch_public_channel_titles(
    channel_ref: str | None,
    *,
    limit: int = 30,
) -> dict[str, Any]:
    """
    Resolve a public channel reference and return recent video titles.

    Returns dict with keys: channel_id, channel_title (optional), titles, error.
    Never raises for empty input — returns empty titles.
    """
    raw = (channel_ref or "").strip()
    if not raw:
        return {"channel_id": None, "titles": [], "error": None}

    try:
        resolved = resolve_channel_id(raw)
        titles = fetch_rss_video_titles(resolved["channel_id"])[: max(1, limit)]
        return {
            "channel_id": resolved["channel_id"],
            "resolved_url": resolved.get("resolved_url"),
            "titles": titles,
            "title_count": len(titles),
            "error": None,
        }
    except ValueError as exc:
        return {
            "channel_id": None,
            "titles": [],
            "title_count": 0,
            "error": str(exc),
        }
    except httpx.HTTPError as exc:
        return {
            "channel_id": None,
            "titles": [],
            "title_count": 0,
            "error": f"Network error fetching YouTube channel: {exc}",
        }


def merge_title_lists(*lists: list[str], limit: int = 60) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for lst in lists:
        for title in lst or []:
            t = (title or "").strip()
            if not t:
                continue
            key = t.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(t)
            if len(out) >= limit:
                return out
    return out
