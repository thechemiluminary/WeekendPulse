"""
WeekendPulse - Reel batch builder.
Reads the committed posts_log.csv, picks the articles posted "today" whose AI
verdict set reel_worthy=yes, and writes a reels_batch.txt manifest that the Colab
news_reel notebook consumes to render one short reel per entry (N -> N).

Usage:
    python reel_batch.py            # build reels_batch.txt from today's posts
    DRY_RUN=1 python reel_batch.py  # print what would be written, don't save
"""
import json
import os
import sys
from datetime import datetime, timezone

from config import BASE_DIR, REEL_EMOTIONS, REEL_MAX_PER_RUN, REEL_BLURB_MAX_WORDS
from post_log import read_log, LOG_PATH

BATCH_PATH = os.path.join(BASE_DIR, "reels_batch.txt")
DRY_RUN = os.environ.get("DRY_RUN", "0") == "1"


def _parse_utc(iso):
    """Parse an ISO timestamp to a timezone-aware datetime, or None."""
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except Exception:
        return None


def _posted_today(row):
    """Return True if the row's posted_at_utc is within the last REEL_DAYS_BACK
    days (approx. "today"), using UTC to stay simple and clock-independent."""
    ts = _parse_utc(row.get("posted_at_utc", ""))
    if ts is None:
        return False
    now = datetime.now(timezone.utc)
    return (now - ts).total_seconds() <= 24 * 3600  # within last ~24h


def _sanitize_emotion(emotion):
    emotion = (emotion or "").strip().lower()
    return emotion if emotion in REEL_EMOTIONS else "neutral"


def _sanitize_blurb(blurb):
    blurb = (blurb or "").strip()
    words = blurb.split()
    if len(words) > REEL_BLURB_MAX_WORDS:
        blurb = " ".join(words[:REEL_BLURB_MAX_WORDS])
    return blurb


def collect_batch(posts=None):
    """
    Return the list of reel-eligible entries from the post log.
    Each entry: {slug, title, image_url, reel_emotion, reel_blurb, post_text, url}.
    Uses only today's posted stories with reel_worthy=yes, newest first, capped.
    """
    posts = posts if posts is not None else read_log()
    entries = []
    for row in posts:
        if row.get("reel_worthy", "").strip().lower() != "yes":
            continue
        if not _posted_today(row):
            continue
        # slug: a URL-ish unique id for the reel (stable-ish, from url or title)
        slug = _slug_for(row)
        if not slug:
            continue
        entries.append({
            "slug": slug,
            "title": row.get("title", "") or "",
            "url": row.get("url", "") or "",
            "post_text": row.get("title", "") or "",
            "image_url": row.get("image_url", "") or "",
            "reel_emotion": _sanitize_emotion(row.get("reel_emotion", "neutral")),
            "reel_blurb": _sanitize_blurb(row.get("reel_blurb", "")),
            "posted_at": row.get("posted_at_utc", "") or "",
        })
    # newest first (latest posted_at), cap it
    entries = sorted(entries, key=lambda e: e.get("posted_at", ""), reverse=True)
    return entries[:REEL_MAX_PER_RUN]


def _slug_for(row):
    url = (row.get("url") or "").strip()
    if url:
        base = url.rstrip("/").rsplit("/", 1)[-1]
        base = "".join(c for c in base if c.isalnum() or c in "-_") or "reel"
        return base[:40]
    title = (row.get("title") or "").strip().lower()
    words = [w for w in title.replace("-", " ").split() if w]
    return ("-".join(words[:5])[:40]) or "reel"


def write_batch(entries):
    """Write the batch manifest as a JSON array (one object per reel)."""
    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "count": len(entries),
        "reels": entries,
    }
    with open(BATCH_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    return BATCH_PATH


def main():
    entries = collect_batch()
    print(f"posts_log rows on disk: {len(read_log())}")
    print(f"reel-worthy today: {len(entries)}")
    for e in entries:
        print(f"  - [{e['reel_emotion']}] {e['title'][:60]}")
    if DRY_RUN:
        print("DRY_RUN - not writing file.")
        return
    if not entries:
        print("Nothing reel-worthy today - skipping write.")
        return
    path = write_batch(entries)
    print(f"wrote {BATCH_PATH}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001
        print(f"reel_batch error: {e}", file=sys.stderr)
        sys.exit(1)