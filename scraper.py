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
from manifest import already_posted


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


# "Bleached" / stop words: the most common noise in football headlines that should
# not count toward story similarity. Source-independent and club-agnostic.
_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "for", "with", "without", "news",
    "could", "would", "should", "will", "still", "yet", "set", "now", "this",
    "vs", "v", "premier", "league", "summer", "window", "report", "reports",
    "preview", "no", "way", "on", "off", "out", "up", "down", "watch", "live",
    "how", "to", "free", "stream", "streams", "tv", "channels", "channel",
    "get", "your", "of", "in", "is", "at", "from", "be", "been", "after",
    "before", "as", "over", "into", "they", "their", "him", "his", "her",
    "we", "you", "us", "them", "s", "t", "d", "ll", "re", "ve",
}


# Capitalised words that regex will wrongly treat as proper-noun/entity names.
# These are common headline words, not players/clubs, and must not count toward
# "same story" matching. Otherwise long series titles (e.g. Guardian's "No 8/9")
# would falsely collapse into one story.
_NON_ENTITY_NAMES = {
    "No", "League", "Super", "Women", "Premier", "News", "Report", "Reports",
    "Video", "Watch", "Live", "Best", "Worst", "Biggest", "Top", "First", "New",
    "Club", "Star", "Striker", "Manager", "Way", "How", "Preview", "Transfer",
    "Window", "Summer", "Wins", "Win", "Weekend", "Final", "Free", "Stream",
    "Streams", "TV", "Channels", "Everything", "Three", "Things", "World",
    "Title", "Now", "Why", "Man", "Great", "Key", "Next", "Verdict", "Rating",
}


def key_names(title):
    """
    Return the set of proper-noun-ish tokens in a headline (player/club names),
    minus common non-entity words. This is the main "same story" signal -
    two headlines describing one story share the player/team involved.
    """
    title = title or ""
    names = set(re.findall(r"\b([A-Z][a-zA-Z]+)\b", title))
    return names - _NON_ENTITY_NAMES


def topic_fp(title):
    """
    Stable per-story fingerprint: sorted, normalized proper-noun entity set from
    the title. Two different magazines covering one story produce (near-)equal
    fingerprints, letting us dedup across runs/sources by exact string equality
    (much stricter than fuzzy ratio - only real same-entity stories collapse).
    """
    names = key_names(title)
    return " ".join(sorted(n.lower() for n in names))


def story_similar(title_a, title_b, threshold=None):
    """
    Fuzzy story match: do two headlines describe the SAME story?
    TRUE only when BOTH hold:
      1. They share at least one real proper-noun (player/club) name, AND
      2. Overall phrasing similarity (SequenceMatcher ratio) is high enough.
    This catches "same story, different magazine" (BBC/Sky/Guardian/...) while
    not collapsing genuinely distinct stories that merely share a club name.
    """
    title_a = title_a or ""
    title_b = title_b or ""
    ka = key_names(title_a)
    kb = key_names(title_b)
    if not ka or not kb:
        return False  # need identifiable names on both sides to call it a match
    if not (ka & kb):
        return False  # different player/club involved -> not the same story
    from difflib import SequenceMatcher
    ratio = SequenceMatcher(None, title_a.lower(), title_b.lower()).ratio()
    threshold = config.DEDUP_THRESHOLD if threshold is None else threshold
    return ratio >= threshold


def similar_to_any(title, titles):
    """Return True if title matches (fuzzily) any title in the iterable."""
    if not title:
        return False
    for other in titles:
        if other and story_similar(title, other):
            return True
    return False


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
    total_entries = 0
    pl_matched = 0
    skipped_posted = 0
    skipped_existing = 0
    for feed_url in config.RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
        except Exception as e:
            print(f"[scraper] feed error {feed_url}: {e}")
            continue

        feed_entries = len(feed.entries)
        total_entries += feed_entries
        feed_pl = 0
        feed_new = 0

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
            feed_pl += 1
            pl_matched += 1

            image_url = _extract_image(entry)

            # Skip already-published stories (per manifest).
            if already_posted(link):
                skipped_posted += 1
                continue

            if article_exists(conn, link):
                _backfill_image(conn, link, image_url)
                skipped_existing += 1
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
                feed_new += 1
                fresh_ids.append(conn.execute(
                    "SELECT id FROM articles WHERE url = ?", (link,)
                ).fetchone()["id"])

        short_url = feed_url.split("/")[2] if "//" in feed_url else feed_url
        print(f"[scraper] {short_url}: {feed_entries} entries, {feed_pl} PL-matched, {feed_new} new")

    # Fetch full rows for the freshly-inserted ids, newest scraped first.
    rows = []
    if fresh_ids:
        qmarks = ",".join("?" for _ in fresh_ids)
        rows = conn.execute(
            f"SELECT * FROM articles WHERE id IN ({qmarks}) ORDER BY id DESC",
            tuple(fresh_ids),
        ).fetchall()

    print(f"[scraper] TOTAL: {total_entries} entries across {len(config.RSS_FEEDS)} feeds, "
          f"{pl_matched} PL-matched, {skipped_posted} already-posted, "
          f"{skipped_existing} existing-in-DB, {new_count} NEW inserted")
    return new_count, rows


def _backfill_image(conn, url, image_url):
    """Set image_url on an existing article only if none is set yet."""
    if not image_url:
        return
    conn.execute("UPDATE articles SET image_url = ? WHERE url = ? AND image_url IS NULL", (image_url, url))
    conn.commit()


def select_postable(conn, fresh_rows, posted_titles, recent_fingerprints=None):
    """
    Returns the FIRST fresh article that should be posted, or None.
    Skips rows that:
      - are already in the durable post log by URL/exact match, OR
      - fuzzily match an already-posted story (same story, different magazine), OR
      - share a recent topic fingerprint (normalized entity set) with an already
        posted story (cross-run, same story from a different source), OR
      - fuzzily match ANOTHER article in this same fresh batch (so we never post
        two magazines covering one story in a single run).
    Returns a DB row (dict-like) eligible to post, or None if everything is a dup.
    """
    recent_fingerprints = set(recent_fingerprints or [])

    # Exact-URL guard first: never repost a URL already in the log.
    fresh = []
    for row in fresh_rows:
        url = row["url"] if "url" in row.keys() else None
        if already_posted(url):
            continue
        fresh.append(row)

    # Fuzzy + fingerprint guard against already-posted stories (cross-run,
    # cross-source). The fingerprint (exact entity-set match) is stricter than
    # fuzzy title ratio and is the primary cross-run same-story check.
    kept = []
    for row in fresh:
        title = row["title"] if "title" in row.keys() else ""
        if similar_to_any(title, posted_titles):
            continue
        fp = topic_fp(title)
        if recent_fingerprints and fp and fp in recent_fingerprints:
            continue
        kept.append(row)

    # Within-batch guard: collapse duplicate stories appearing in this batch.
    chosen = None
    chosen_title = None
    for row in kept:
        title = row["title"] if "title" in row.keys() else ""
        if chosen_title is not None and similar_to_any(title, [chosen_title]):
            continue
        chosen = row
        chosen_title = title
        break

    print(f"[scraper] select_postable: {len(fresh_rows)} fresh -> "
          f"{len(fresh)} after URL-dedup -> {len(kept)} after fuzzy+fingerprint-dedup -> "
          f"{'picked: ' + (chosen['title'][:60] if chosen else 'NONE')}")
    return chosen