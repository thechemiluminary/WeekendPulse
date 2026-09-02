"""
WeekendPulse - Reel batch builder.
Reads the committed manifest.json, picks the articles "today" that are
reel_approved AND not yet posted as a reel (reel_posted false), and writes a
reels_batch.txt manifest that the Colab news_reel notebook consumes to render
one short reel per entry (N -> N).

Usage:
    python reel_batch.py            # build reels_batch.txt from today's posts
    DRY_RUN=1 python reel_batch.py  # print what would be written, don't save
"""
import json
import os
import sys
from datetime import datetime, timezone

import manifest
from config import REEL_EMOTIONS, REEL_MAX_PER_RUN, REEL_BLURB_MAX_WORDS, MANIFEST_PATH

BATCH_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reels_batch.txt")
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


def collect_batch(rows=None):
    """
    Return the list of reel-eligible entries from the manifest.
    Selects entries that are reel_approved AND not yet posted as a reel
    (reel_posted false), which are "today" (within REEL_DAYS_BACK), newest
    first, capped at REEL_MAX_PER_RUN.
    Each output entry: {slug, title, image_url, reel_emotion, reel_blurb,
                        post_text, url, posted_at}.
    """
    rows = rows if rows is not None else manifest.reel_pending()
    entries = []
    for row in rows:
        if not _posted_today(row):
            continue
        slug = row.get("slug") or manifest._slug_for(row.get("url"), row.get("title"))
        if not slug:
            continue
        entries.append({
            "slug": slug,
            "title": row.get("title", "") or "",
            "url": row.get("url", "") or "",
            "post_text": row.get("description", "") or row.get("title", "") or "",
            "image_url": row.get("image_url", "") or "",
            "reel_emotion": _sanitize_emotion(row.get("reel_emotion", "neutral")),
            "reel_blurb": _sanitize_blurb(row.get("reel_blurb", "")),
            "posted_at": row.get("posted_at_utc", "") or "",
        })
    # newest first (latest posted_at), cap it
    entries = sorted(entries, key=lambda e: e.get("posted_at", ""), reverse=True)
    return entries[:REEL_MAX_PER_RUN]


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
    print(f"manifest entries on disk: {len(manifest.load_manifest())}")
    print(f"reel-approved + not-yet-posted today: {len(entries)}")
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