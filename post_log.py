"""
WeekendPulse - Post log.
Appends a record for every post the bot publishes to a tracked file in the repo
(posts_log.csv). This gives a durable, committed history of each push (link, id, ...).
"""
import csv
import os
from datetime import datetime, timezone

from config import BASE_DIR

LOG_PATH = os.path.join(BASE_DIR, "posts_log.csv")
_COLUMNS = ["posted_at_utc", "post_id", "article_id", "title", "url", "source", "pub_image"]

_HEADER = _COLUMNS


def _ensure_file():
    if not os.path.exists(LOG_PATH):
        with open(LOG_PATH, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(_HEADER)


def append_post(post_id, article_row, image_used):
    """
    Append a row for a published post. Returns the path written.
    article_row: a DB row (dict-like) with id/url/title/source/image_url.
    """
    _ensure_file()
    row = {
        "posted_at_utc": datetime.now(timezone.utc).isoformat(),
        "post_id": post_id or "",
        "article_id": article_row["id"] if "id" in article_row.keys() else "",
        "title": (article_row["title"] if "title" in article_row.keys() else "") or "",
        "url": (article_row["url"] if "url" in article_row.keys() else "") or "",
        "source": (article_row["source"] if "source" in article_row.keys() else "") or "",
        "pub_image": "yes" if image_used else "no",
    }
    with open(LOG_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=_COLUMNS)
        # write header only if file is empty/new
        if f.tell() == 0:
            writer.writeheader()
        writer.writerow(row)
    return LOG_PATH


def read_log():
    """Return a list of dicts for the log, or [] if missing/empty."""
    if not os.path.exists(LOG_PATH):
        return []
    with open(LOG_PATH, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


def already_posted(url):
    """
    Return True if this article URL has already been published (per the log).
    The log persists in the repo across runs, so this provides cross-run
    duplicate protection even when the local DB resets (e.g. ephemeral CI).
    """
    if not url:
        return False
    url = url.strip()
    for row in read_log():
        if row.get("url", "").strip() == url:
            return True
    return False


def posted_titles():
    """
    Return the titles (and URLs) of every story already published, for fuzzy
    story-level dedup across runs. Stored so repeated calls are cheap.
    """
    return [row.get("title", "") or "" for row in read_log()]