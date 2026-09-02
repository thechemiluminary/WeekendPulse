"""
WeekendPulse - RSS scraper.
Fetches feeds, filters for Premier League/English-football topics,
extracts the article image when available, deduplicates against the DB.
"""
import re
import feedparser
from datetime import datetime
import config
from db import article_exists, insert_article
from post_log import already_posted


# Non-football sports that can collide with PL keywords (e.g. "England" cricket,
# "Newcastle" racing). If any appear in title/summary, drop the story.
_NON_PL_SPORTS = [
    "cricket", "rugby", "tennis", "golf", "athletics", "snooker", "darts",
    "racing", "horse racing", "boxing", "nfl", "nba", "f1", "formula 1",
    "formula one", "motogp", "mma", "cycling", "darts", "netball", "ice hockey",
    "super league", "ashes", "england vs pakistan", "test match",
]


def _matches_pl(title, summary):
    """Return True if the article relates to Premier League / English football."""
    text = f"{title} {summary or ''}".lower()
    if any(sport in text for sport in _NON_PL_SPORTS):
        return False
    return any(kw in text for kw in config.PL_KEYWORDS)


def _extract_image(entry):
    """
    Return a usable article image URL, or None.
    Priority:
      1. BBC media_thumbnail -> upscale to 1024px (versioned path)
      2. media_content / enclosure with image type
      3. src= from any <img> found in summary/description/site
      4. media_url fallback from entry.media_fields if present
    """
    # 1. BBC thumbnail (return higher-res by swapping the width token)
    th = entry.get("media_thumbnail") or []
    if th and isinstance(th, list) and th[0].get("url"):
        url = th[0]["url"]
        return _bbc_hires(url)

    # 2. media_content
    mc = entry.get("media_content") or []
    for m in mc:
        u = None
        if isinstance(m, dict):
            u = m.get("url")
        elif hasattr(m, "get"):
            u = m.get("url")
        if u and not _looks_blank(u):
            return u

    # 3. enclosure
    encl = entry.get("enclosures") or []
    for en in encl:
        u = en.get("url")
        if u and (en.get("type", "").startswith("image") or _is_image(u)):
            return u

    # 4. first <img> in summary/description
    raw = (entry.get("summary") or "") + (entry.get("description") or "")
    m = re.search(r"src=['\"]([^'\"]+)['\"]", raw)
    if m and _is_image(m.group(1)):
        return m.group(1)

    return None


def _bbc_hires(url):
    """BBC ichef URLs carry a width token /240/, /976/ etc. Request ~1024."""
    if "ichef.bbci.co.uk" not in url:
        return url
    return re.sub(r"/\d+/", "/1024/", url, count=1)


def _is_image(url):
    return bool(re.search(r"\.(jpe?g|png|webp|gif)(\?|$)", url, re.I))


def _looks_blank(url):
    return url.lower().strip() in ("", "none", "null")


def _get_source(feed_url, entry):
    src = feed_url.split("/")[2] if "//" in feed_url else feed_url
    return src.replace("www.", "")


def scrape_all(conn):
    """
    Fetch all configured feeds, filter to PL-relevant, insert new articles.
    Returns (new_count, fresh_article_rows):
      - new_count: how many articles were newly inserted this run
      - fresh_article_rows: the actual DB rows for those new articles, newest first.
    Only articles inserted DURING this run are returned, so the bot never
    re-posts old backlog. Empty on any other run.
    """
    new_count = 0
    fresh_ids = []
    for feed_url in config.RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
        except Exception as e:
            print(f"[scraper] feed error {feed_url}: {e}")
            continue

        for entry in feed.entries:
            title = entry.get("title", "").strip()
            link = entry.get("link", "").strip()
            summary = entry.get("summary", "") or entry.get("description", "")
            published = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                published = datetime(*entry.published_parsed[:6])

            if not title or not link:
                continue
            if not _matches_pl(title, summary):
                continue

            image_url = _extract_image(entry)

            # Skip already-published stories (persisted via posts_log across runs).
            if already_posted(link):
                continue

            if article_exists(conn, link):
                # Backfill image for existing rows that lack one (cheap re-scrape).
                _backfill_image(conn, link, image_url)
                continue

            inserted = insert_article(
                conn,
                url=link,
                title=title,
                source=_get_source(feed_url, entry),
                summary=summary,
                published=published,
                post_type=None,
                image_url=image_url,
            )
            if inserted:
                new_count += 1
                fresh_ids.append(conn.execute(
                    "SELECT id FROM articles WHERE url = ?", (link,)
                ).fetchone()["id"])

    # Fetch full rows for the freshly-inserted ids, newest scraped first.
    rows = []
    if fresh_ids:
        qmarks = ",".join("?" for _ in fresh_ids)
        rows = conn.execute(
            f"SELECT * FROM articles WHERE id IN ({qmarks}) ORDER BY id DESC",
            tuple(fresh_ids),
        ).fetchall()

    return new_count, rows


def _backfill_image(conn, url, image_url):
    """Set image_url on an existing article only if none is set yet."""
    if not image_url:
        return
    conn.execute("UPDATE articles SET image_url = ? WHERE url = ? AND image_url IS NULL", (image_url, url))
    conn.commit()