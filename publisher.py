"""
WeekendPulse - Facebook publisher.
Posts text (+ optional real article image) to the Page via Graph API.
"""
import os
import requests
from config import FB_PAGE_ID, FB_PAGE_TOKEN, IMAGE_DIR

GRAPH = "https://graph.facebook.com/v26.0"

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) WeekendPulse bot/1.0"


def _headers():
    if not FB_PAGE_TOKEN:
        raise RuntimeError("FB_PAGE_TOKEN not set - cannot publish.")
    return {"Authorization": f"Bearer {FB_PAGE_TOKEN}"}


def post_text(message):
    """
    Publish a text post to the Page. Returns (ok, post_id_or_error).
    """
    url = f"{GRAPH}/{FB_PAGE_ID}/feed"
    resp = requests.post(url, json={"message": message}, headers=_headers(), timeout=60)
    data = resp.json()
    if resp.status_code == 200 and "id" in data:
        return True, data["id"]
    return False, data


def _download_bytes(image_url, timeout=30):
    """Download an image and return raw bytes, or None on failure."""
    resp = requests.get(image_url, timeout=timeout, headers={"User-Agent": _UA})
    resp.raise_for_status()
    if not resp.content:
        return None
    return resp.content


def post_text_with_image_url(message, image_url, save_dir=IMAGE_DIR):
    """
    Download the article's real image and publish it as a photo post with caption.
    Returns (ok, result).
    """
    try:
        content = _download_bytes(image_url)
    except Exception as e:
        return False, f"image download failed: {e}"
    if not content:
        return False, "image download returned empty"

    # Save a local copy too (for the local debug cache; harmless if dir missing)
    os.makedirs(save_dir, exist_ok=True)
    local_path = os.path.join(save_dir, "latest_article_image.jpg")
    try:
        with open(local_path, "wb") as f:
            f.write(content)
    except Exception:
        pass

    url = f"{GRAPH}/{FB_PAGE_ID}/photos"
    files = {"source": content}  # send raw bytes
    data = {"message": message}
    head = _headers()
    resp = requests.post(url, data=data, files=files, headers=head, timeout=120)
    j = resp.json()
    if resp.status_code == 200 and ("id" in j or "post_id" in j):
        return True, j.get("post_id") or j.get("id")
    return False, j


def post_text_with_image(message, image_path):
    """
    Publish a photo + caption from a local file. Returns (ok, post_id_or_error).
    """
    with open(image_path, "rb") as f:
        content = f.read()
    url = f"{GRAPH}/{FB_PAGE_ID}/photos"
    files = {"source": content}
    data = {"message": message}
    head = _headers()
    resp = requests.post(url, data=data, files=files, headers=head, timeout=120)
    j = resp.json()
    if resp.status_code == 200 and ("id" in j or "post_id" in j):
        return True, j.get("post_id") or j.get("id")
    return False, j


def schedule_post(message, image_path, scheduled_unix):
    """
    Schedule a photo + caption to go LIVE at scheduled_unix (Unix seconds).
    Uses the /photos endpoint with published=false + scheduled_publish_time so
    the `source` is a real file upload (the /feed endpoint only accepts `source`
    as a URL, so it can't upload a local image). BOTH published=false and
    scheduled_publish_time must be sent together - if published defaults to true
    the post goes live immediately instead of on schedule.

    Publish window is 10 minutes .. 30 days from the request. Returns
    (ok, post_id_or_error).
    """
    with open(image_path, "rb") as f:
        content = f.read()
    url = f"{GRAPH}/{FB_PAGE_ID}/photos"
    files = {"source": content}
    data = {
        "message": message,
        "published": "false",
        "scheduled_publish_time": str(int(scheduled_unix)),
    }
    head = _headers()
    resp = requests.post(url, data=data, files=files, headers=head, timeout=120)
    j = resp.json()
    if resp.status_code == 200 and ("id" in j or "post_id" in j):
        return True, j.get("post_id") or j.get("id")
    return False, j