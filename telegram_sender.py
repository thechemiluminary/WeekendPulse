"""
WeekendPulse - Telegram draft sender for semi-auto social mode.
Sends generated social drafts to the user's Telegram bot chat so the user can
manually add an image and post to the Facebook page. Uses the Telegram Bot API
via plain `requests` (no new dependencies).
"""
import requests

import config


def send_draft(text):
    """Send a draft to the configured Telegram chat. Returns True on success."""
    if not config.TG_BOT_TOKEN or not config.TG_CHAT_ID:
        print("[telegram] TG_BOT_TOKEN/TG_CHAT_ID not configured - cannot send")
        return False
    if not text or not text.strip():
        print("[telegram] empty draft - nothing to send")
        return False

    url = f"https://api.telegram.org/bot{config.TG_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": config.TG_CHAT_ID,
        "text": text.strip(),
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    try:
        r = requests.post(url, json=payload, timeout=60)
        r.raise_for_status()
        ok = (r.json().get("ok") is True)
        if not ok:
            print(f"[telegram] API returned ok=False: {r.text}")
        return ok
    except Exception as e:
        print(f"[telegram] send failed: {e}")
        return False
