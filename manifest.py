"""
WeekendPulse - Manifest.
Single source of truth (manifest.json). Holds every story that was sent to the
Page: the bot records each post (post_id, title, description, reel approval),
and the reel generator updates the same entry after it renders + posts the
reel (voice used, emotion used, reel video id, posted flag).

This REPLACES posts_log.csv as the shared record. Reading/writing is atomic
(read-modify-write) so the GitHub Actions bot and the Colab notebook can both
update it safely across runs.
"""
import json
import os
import re
from datetime import datetime, timezone

from config import BASE_DIR

MANIFEST_PATH = os.path.join(BASE_DIR, "manifest.json")


def _topic_fingerprint(title):
    """
    Compute a stable fingerprint from a title: the sorted, normalized set of
    proper-noun-ish tokens (player/club names). This is used for cross-run
    deduplication of the same story from different sources.
    """
    from scraper import key_names
    names = key_names(title)
    return " ".join(sorted(name.lower() for name in names))


def _slug_for(url, title):
    """Stable slug from the article url (falls back to the title)."""
    url = (url or "").strip()
    if url:
        base = url.rstrip("/").rsplit("/", 1)[-1]
        base = "".join(c for c in base if c.isalnum() or c in "-_") or "reel"
        return base[:40]
    t = (title or "").strip().lower()
    words = [w for w in t.replace("-", " ").split() if w]
    return ("-".join(words[:5])[:40]) or "reel"


def _empty_entry(slug):
    return {
        "slug": slug,
        "posted_at_utc": "",
        "post_id": "",
        "title": "",
        "description": "",
        "url": "",
        "image_url": "",
        "topic_fp": "",
        "reel_approved": False,
        "reel_emotion": "neutral",
        "reel_blurb": "",
        "rendered": False,
        "reel_posted": False,
        "reel_video_id": "",
        "reel_voice": "",
        "reel_emotion_used": "",
        "reel_music": "",
        "reel_rendered_at": "",
    }


def load_manifest():
    """Return the list of manifest entries, or [] if missing/empty."""
    if not os.path.exists(MANIFEST_PATH):
        return []
    try:
        with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return []
    entries = data if isinstance(data, list) else data.get("entries", [])
    return entries if isinstance(entries, list) else []


def save_manifest(entries):
    """Atomically write the manifest (tmp file + rename)."""
    tmp = MANIFEST_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2, ensure_ascii=False)
    os.replace(tmp, MANIFEST_PATH)
    return MANIFEST_PATH


def upsert(entry):
    """Insert or replace one entry by slug. Returns the saved path."""
    slug = entry.get("slug") or _slug_for(entry.get("url"), entry.get("title"))
    entry["slug"] = slug
    entries = load_manifest()
    for i, e in enumerate(entries):
        if e.get("slug") == slug:
            merged = _empty_entry(slug)
            merged.update(e)
            merged.update(entry)
            entries[i] = merged
            break
    else:
        merged = _empty_entry(slug)
        merged.update(entry)
        entries.append(merged)
    return save_manifest(entries)


def append_post_entry(post_id, article_row, reel_meta=None, topic_fp=None):
    """
    Record a post that was pushed to the Page. article_row: dict-like with
    id/url/title/source/image_url. reel_meta: optional dict with
    reel_worthy/reel_emotion/reel_blurb. topic_fp: an optional precomputed
    story fingerprint (blank -> computed here from the title).
    """
    reel_meta = reel_meta or {}
    worthy = bool(reel_meta.get("reel_worthy"))
    title = article_row["title"] if "title" in article_row.keys() else ""
    url = article_row["url"] if "url" in article_row.keys() else ""
    image_url = article_row["image_url"] if "image_url" in article_row.keys() else ""
    if not topic_fp:
        topic_fp = _topic_fingerprint(title)
    entry = {
        "posted_at_utc": datetime.now(timezone.utc).isoformat(),
        "post_id": post_id or "",
        "title": title or "",
        "description": (article_row["title"] if "title" in article_row.keys() else "") or "",
        "url": url or "",
        "image_url": image_url or "",
        "topic_fp": topic_fp or "",
        "reel_approved": worthy,
        "reel_emotion": reel_meta.get("reel_emotion", "neutral") if worthy else "neutral",
        "reel_blurb": reel_meta.get("reel_blurb", "") if worthy else "",
    }
    return upsert(entry)


def update_reel(slug, **fields):
    """Set reel render/post fields on an existing entry (or create if missing)."""
    entries = load_manifest()
    for e in entries:
        if e.get("slug") == slug:
            e.update(fields)
            return save_manifest(entries)
    entry = {"slug": slug}
    entry.update(fields)
    return upsert(entry)


def already_posted(url):
    """True if this article url has already been sent to the Page (per manifest)."""
    if not url:
        return False
    url = url.strip()
    return any(row.get("url", "").strip() == url for row in load_manifest())


def posted_titles():
    """Titles of every story already sent to the Page (for story-level dedup)."""
    return [row.get("title", "") or "" for row in load_manifest()]


def recent_topic_fingerprints(max_entries=100):
    """
    Story fingerprints of recent posts, most-recent first. Used for cross-run
    dedup of the SAME story scraped from multiple sources (the DB is gitignored
    and each GitHub run starts empty, so the committed manifest is the durable
    cross-run record).
    """
    return [
        (e.get("topic_fp") or "")
        for e in reversed(load_manifest())
        if e.get("topic_fp")
    ][:max_entries]


def reel_pending():
    """Entries approved for reels that have NOT yet been posted as a reel."""
    return [e for e in load_manifest()
            if e.get("reel_approved") and not e.get("reel_posted")]


# --- Match-preview (fixture) helpers ---

def already_posted_fixture(match_key):
    """True if this fixture (match_key) has already been scheduled/posted."""
    if not match_key:
        return False
    match_key = match_key.strip().lower()
    return any(
        (e.get("match_key") or "").strip().lower() == match_key
        for e in load_manifest()
    )


def append_match_entry(fixture, post_id, scheduled_unix):
    """
    Record a scheduled match-preview post. fixture: the dict from
    fixtures.get_today_fixtures(). post_id: the returned Graph post id.
    scheduled_unix: the `scheduled_publish_time` we asked Facebook to publish at.
    """
    entry = {
        "slug": fixture.get("match_key") or "",
        "posted_at_utc": datetime.now(timezone.utc).isoformat(),
        "post_id": post_id or "",
        "title": f"{fixture.get('home')} vs {fixture.get('away')}",
        "description": "match-preview",
        "url": "",
        "image_url": "",
        "reel_approved": False,
        "reel_emotion": "neutral",
        "reel_blurb": "",
        "match_key": fixture.get("match_key") or "",
        "fixture_id": fixture.get("match_id"),
        "scheduled_publish_time": str(int(scheduled_unix)) if scheduled_unix else "",
        "match_home": fixture.get("home"),
        "match_away": fixture.get("away"),
        "match_kickoff": fixture.get("utc_kickoff_iso") or "",
        "status": "scheduled",
    }
    return upsert(entry)
