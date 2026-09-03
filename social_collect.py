"""
WeekendPulse - Social collector (runs every ~5 min, NO Gemini usage).
Ingests cheap, stable, token-less sources into the pooled talking points used
by the social scoring engine:
  - Telegram football channels via RSSHub public RSS (e.g. FabrizioRomanoTG)
  - Reddit football subreddits via free RSS (r/soccer)
  - today's PL fixtures + match status from football-data.org
Deduplicates by content hash. Returns a summary so the caller can log it.
"""
import datetime
import html
import re
import urllib.request
import urllib.error

import feedparser

import config
import social_state
import fixtures as fixtures_mod

# Keep posts that look football/PL-flavoured and reasonably short.
_MAX_TITLE = 300


def _clean(text):
    text = html.unescape(text or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _hash_slug(text):
    return str(abs(hash(text)) % 10_000_000)


def _collect_telegram(channels):
    """
    Pull each Telegram channel from its PUBLIC web preview page (t.me/s/<ch>).
    This is token-free, stable, and doesn't depend on fragile RSSHub instances.
    We only use the posts as TOPIC INSPIRATION (the AI rewrites originally).
    """
    added = 0
    for ch in channels:
        ch = ch.strip()
        if not ch:
            continue
        url = f"https://t.me/s/{ch}"
        texts = _fetch_telegram_texts(url)
        for t in texts:
            t = _clean(t)
            if not t:
                continue
            if _looks_football(t):
                if social_state.add_talking_point(t[:300], f"telegram/{ch}", _hash_slug(t)):
                    added += 1
        print(f"[collect] telegram/{ch}: {len(texts)} messages")
    return added


def _fetch_telegram_texts(url, limit=30):
    """Parse public Telegram channel preview page and return post texts."""
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept-Language": "en",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            page = r.read().decode("utf-8", "ignore")
    except (urllib.error.URLError, urllib.error.HTTPError, Exception) as e:
        print(f"[collect] telegram fetch failed {url}: {e}")
        return []
    # Each post body is a <div class="…message_text…">…</div>
    blocks = re.findall(r'class="[^"]*message_text[^"]*"[^>]*>(.*?)</div>', page, re.S)
    texts = []
    for b in blocks[:limit]:
        clean = re.sub(r"<[^>]+>", " ", b)
        clean = _clean(clean)
        if clean:
            texts.append(clean)
    return texts


def _collect_reddit(subs):
    """Pull each subreddit's new posts via Reddit's free RSS."""
    added = 0
    for sub in subs:
        sub = sub.strip()
        if not sub:
            continue
        url = f"https://www.reddit.com/r/{sub}/new/.rss" if sub else ""
        if not sub:
            continue
        try:
            feed = feedparser.parse(url)
        except Exception as e:
            print(f"[collect] reddit r/{sub} error: {e}")
            continue
        for entry in feed.entries:
            title = _clean(entry.get("title", ""))
            if not title:
                continue
            link = entry.get("link", "")
            body = (title[:200] + (f" | {link}" if link else ""))
            if _looks_football(body):
                if social_state.add_talking_point(body, f"reddit/r/{sub}", _hash_slug(body)):
                    added += 1
        print(f"[collect] reddit r/{sub}: {len(feed.entries)} entries")
    return added


def _collect_fixtures():
    """Add today's fixtures + statuses so the AI is grounded in real matchups."""
    added = 0
    fxs = fixtures_mod.get_today_fixtures()
    if not fxs:
        print("[collect] fixtures: none today")
        return 0
    for fx in fxs:
        kick = fx.get("utc_kickoff_iso", "")
        text = f"{fx.get('home')} vs {fx.get('away')} - kickoff {kick}"
        mk = fixtures_mod.match_key(fx)
        slug = f"fx-{mk or _hash_slug(text)}"
        if social_state.add_talking_point(text, "football-data/fixture", slug):
            added += 1
    print(f"[collect] fixtures: {len(fxs)} today")
    return added


def _looks_football(text):
    """Heuristic filter: keep only PL/English-football flavoured lines."""
    t = (text or "").lower()
    if any(s in t for s in config.PL_KEYWORDS):
        return True
    return False


def collect_all():
    """Ingest all sources into the pool. Returns a summary dict."""
    total = 0
    total += _collect_fixtures()
    total += _collect_telegram(config.SOCIAL_TELEGRAM_CHANNELS)
    total += _collect_reddit(config.SOCIAL_REDDIT_SUBS)
    print(f"[collect] total new talking points: {total}")
    return {"collected": total, "pool": len(social_state.pool_texts())}
