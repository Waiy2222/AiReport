"""RSS feed scraper for AI news."""

import logging
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree

import httpx

from . import _insert_items

logger = logging.getLogger(__name__)

# Primary + fallback feeds
FEEDS: list[tuple[str, str]] = [
    (
        "hnrss",
        "https://hnrss.org/frontpage?q=ai+OR+llm+OR+gpt+OR+openai+OR+anthropic+OR+deepseek",
    ),
    (
        "hackernews",
        "https://feeds.feedburner.com/TheHackersNews",
    ),
]

# Atom namespace
_ATOM_NS = "http://www.w3.org/2005/Atom"


def _ns(tag: str) -> str:
    """Qualify a tag name with the Atom namespace."""
    return f"{{{_ATOM_NS}}}{tag}"


def _parse_rss_datetime(date_str: str | None) -> datetime | None:
    """Parse common RSS/Atom date formats into a timezone-aware datetime."""
    if not date_str:
        return None
    try:
        # RFC 2822 / RFC 822 (common in RSS)
        return parsedate_to_datetime(date_str)
    except (ValueError, TypeError):
        pass
    try:
        # ISO 8601 (common in Atom)
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        logger.debug("Could not parse RSS date: %r", date_str)
        return None


def _parse_rss_feed(root: ElementTree.Element) -> list[dict]:
    """Parse an RSS 2.0 feed, returning a list of item dicts."""
    items = []
    channel = root.find("channel")
    if channel is None:
        return items

    for item_elem in channel.findall("item"):
        try:
            title = item_elem.findtext("title", "")
            link = item_elem.findtext("link", "")
            description = item_elem.findtext("description", "")
            author = item_elem.findtext("author", "")
            pub_date = item_elem.findtext("pubDate")

            if not title or not link:
                continue

            published = _parse_rss_datetime(pub_date)
            items.append({
                "title": title,
                "url": link,
                "content": description or "",
                "author": author,
                "published_at": published or datetime.now(timezone.utc),
                "metadata": {"format": "rss"},
            })
        except Exception:
            logger.debug("Skipping malformed RSS item", exc_info=True)

    return items


def _parse_atom_feed(root: ElementTree.Element) -> list[dict]:
    """Parse an Atom feed, returning a list of item dicts."""
    items = []

    for entry in root.findall(_ns("entry")):
        try:
            title_elem = entry.find(_ns("title"))
            title = title_elem.text if title_elem is not None else ""

            link_elem = entry.find(_ns("link"))
            link = ""
            if link_elem is not None:
                link = link_elem.attrib.get("href", "")

            summary_elem = entry.find(_ns("summary"))
            content = summary_elem.text if summary_elem is not None else ""

            author_elem = entry.find(_ns("author"))
            author = ""
            if author_elem is not None:
                name_elem = author_elem.find(_ns("name"))
                author = name_elem.text if name_elem is not None else ""

            published_elem = entry.find(_ns("published"))
            updated_elem = entry.find(_ns("updated"))
            date_str = None
            if published_elem is not None:
                date_str = published_elem.text
            elif updated_elem is not None:
                date_str = updated_elem.text

            if not title or not link:
                continue

            published = _parse_rss_datetime(date_str)
            items.append({
                "title": title,
                "url": link,
                "content": content or "",
                "author": author,
                "published_at": published or datetime.now(timezone.utc),
                "metadata": {"format": "atom"},
            })
        except Exception:
            logger.debug("Skipping malformed Atom entry", exc_info=True)

    return items


def _parse_feed(xml_text: str) -> list[dict]:
    """Detect feed type and parse accordingly."""
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError as exc:
        logger.warning("Failed to parse RSS/Atom XML: %s", exc)
        return []

    # RSS 2.0
    if root.tag == "rss" or root.find("channel") is not None:
        return _parse_rss_feed(root)

    # Atom
    if _ATOM_NS in root.tag:
        return _parse_atom_feed(root)

    # Try as Atom even if namespace detection failed
    atom_items = _parse_atom_feed(root)
    if atom_items:
        return atom_items

    logger.warning("Unknown RSS feed format (root tag: %s)", root.tag)
    return []


async def fetch(pool, since: datetime, batch_id) -> int:
    """Fetch AI news from RSS feeds and insert into raw_items.

    Returns the number of newly inserted items (0 on complete failure).
    """
    headers = {"User-Agent": "ai-news-briefing/1.0"}
    all_items = []

    for feed_name, feed_url in FEEDS:
        logger.info("RSS: fetching feed '%s' from %s", feed_name, feed_url)
        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                resp = await client.get(feed_url, headers=headers)
                resp.raise_for_status()
        except Exception:
            logger.warning("Failed to fetch RSS feed '%s'", feed_name, exc_info=True)
            continue

        feed_items = _parse_feed(resp.text)
        logger.info(
            "RSS: feed '%s' yielded %d parsed items", feed_name, len(feed_items)
        )

        # Filter by since and tag with feed source
        for item in feed_items:
            try:
                published = datetime.fromisoformat(item["published_at"])
                if published < since:
                    continue
            except (ValueError, TypeError):
                pass  # keep item if we can't parse its date

            item["metadata"]["feed_source"] = feed_name
            all_items.append(item)

    logger.info("RSS: %d total items after date filter", len(all_items))
    return await _insert_items(pool, "rss", all_items, batch_id)
