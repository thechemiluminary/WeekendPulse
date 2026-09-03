"""
WeekendPulse - Social engagement state store.
Manages social_state.json, a committed file that is the single source of truth
for the social engine:
  - a rolling pool of today's talking points (from the 5-min collector)
  - tracker of which formats/topics have been posted (avoid repetition)
  - the daily post counter (SOCIAL_MAX_PER_DAY cap)
  - per-post engagement results (feedback for future scoring, appended later)

Reads/writes atomically (tmp + rename) like manifest.json so the GitHub Actions
bot and local runs can both update it safely.
"""
import json
import os
from datetime import datetime, timezone

from config import BASE_DIR

SOCIAL_PATH = os.path.join(BASE_DIR, "social_state.json")
_MAX_POOL = 80          # cap pooled talking points so the file stays small
_MAX_HISTORY = 400      # cap stored history


def _default():
    return {
        "last_collect_utc": "",
        "today": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "posted_today": 0,
        "pool": [],          # [{text, source, ts_utc, hash}]
        "posted": [],        # [{ts_utc, format, topic, post_text, post_id, image_url}]
        "drafts": [],        # semi-auto drafts sent to Telegram (NOT counted in posted_today)
        "engagement": [],    # [{post_id, ts_utc, reactions, comments, shares}] appended later
    }


def load():
    if not os.path.exists(SOCIAL_PATH):
        return _default()
    try:
        with open(SOCIAL_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return _default()
        # roll the day counter if the date changed
        d = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if data.get("today") != d:
            data["posted_today"] = 0
            data["pool"] = []
            data["today"] = d
        data.setdefault("posted", [])
        data.setdefault("drafts", [])
        data.setdefault("engagement", [])
        data.setdefault("pool", [])
        return data
    except Exception:
        return _default()


def save(data):
    data["last_collect_utc"] = datetime.now(timezone.utc).isoformat()
    tmp = SOCIAL_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, SOCIAL_PATH)
    return SOCIAL_PATH


def add_talking_point(text, source, hash_slug=None):
    """Add a talking point to the pool (dedup by hash if provided). Returns True if added."""
    if not text or not text.strip():
        return False
    text = text.strip()
    data = load()
    slug = hash_slug or str(abs(hash(text)) % 10_000_000)
    for p in data["pool"]:
        if p.get("hash") == slug or p.get("text") == text:
            return False
    data["pool"].append({
        "text": text,
        "source": source,
        "ts_utc": datetime.now(timezone.utc).isoformat(),
        "hash": slug,
    })
    # keep newest-ish: drop oldest beyond cap
    if len(data["pool"]) > _MAX_POOL:
        data["pool"] = data["pool"][-_MAX_POOL:]
    save(data)
    return True


def record_posted(format_label, topic, post_text, post_id=None, image_url=""):
    """Record a generated post (used for daily cap + repetition guard)."""
    data = load()
    data["posted"].append({
        "ts_utc": datetime.now(timezone.utc).isoformat(),
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "format": format_label,
        "topic": topic,
        "post_text": post_text,
        "post_id": post_id,
        "image_url": image_url,
    })
    if len(data["posted"]) > _MAX_HISTORY:
        data["posted"] = data["posted"][-_MAX_HISTORY:]
    # bump daily counter based on today's actual posts
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    data["posted_today"] = sum(1 for r in data["posted"] if r.get("date") == today)
    save(data)


def track_draft(format_label, topic, post_text):
    """Record a semi-auto draft sent to Telegram. Does NOT touch posted_today
    (drafts don't count toward the daily cap) but still feeds the repetition
    guard so future drafts avoid repeating this topic/format."""
    data = load()
    data["drafts"].append({
        "ts_utc": datetime.now(timezone.utc).isoformat(),
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "format": format_label,
        "topic": topic,
        "post_text": post_text,
    })
    if len(data["drafts"]) > _MAX_HISTORY:
        data["drafts"] = data["drafts"][-_MAX_HISTORY:]
    save(data)


def undo_last_posted():
    """Roll back the last recorded post (used if publish actually failed)."""
    data = load()
    if data["posted"]:
        data["posted"] = data["posted"][:-1]
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        data["posted_today"] = sum(1 for r in data["posted"] if r.get("date") == today)
        save(data)


def posted_today():
    data = load()
    return data.get("posted_today", 0)


def recent_topics(total=25):
    """Return the most recent posted/drafted topic slugs (repetition guard)."""
    data = load()
    topics = [r.get("topic", "") for r in data["posted"] if r.get("topic")]
    topics += [r.get("topic", "") for r in data["drafts"] if r.get("topic")]
    return topics[-total:]


def pool_texts(limit=60):
    """Return pooled talking-point texts, newest first, for the AI prompt."""
    data = load()
    items = list(data["pool"])
    items.sort(key=lambda p: p.get("ts_utc", ""), reverse=True)
    return [p.get("text", "") for p in items[:limit]]


def add_engagement(post_id, reactions=0, comments=0, shares=0):
    """Append real engagement for a post id (feedback for future scoring)."""
    if not post_id:
        return
    data = load()
    data["engagement"].append({
        "post_id": post_id,
        "ts_utc": datetime.now(timezone.utc).isoformat(),
        "reactions": reactions,
        "comments": comments,
        "shares": shares,
    })
    if len(data["engagement"]) > _MAX_HISTORY:
        data["engagement"] = data["engagement"][-_MAX_HISTORY:]
    save(data)


def last_fired_slot():
    """Return the last (date, slot_key) that fired, or None."""
    data = load()
    lf = data.get("last_fired_slot")
    if not lf:
        return None
    return (lf.get("date", ""), lf.get("slot", ""))


def set_fired_slot(slot_key):
    """Record that a given slot fired (persistent double-fire guard)."""
    data = load()
    data["last_fired_slot"] = {
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "slot": slot_key,
    }
    save(data)
