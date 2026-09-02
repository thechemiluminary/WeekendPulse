"""
WeekendPulse - Fixture source.
Fetches today's Premier League fixtures from football-data.org (free tier) and
returns the ones that are still scheduled to be played (not started). Used by
the match-preview orchestrator to schedule a comment-bait post 5h before each
kickoff.

Free tier: no credit card, PL fixtures included, 10 calls/min. Auth header:
    X-Auth-Token: <FOOTBALL_API_TOKEN>

All failures are swallowed -> caller sees [] (the nightly news bot still runs).
"""
import datetime
import urllib.request
import urllib.error
import json

import config


def _today_iso():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")


def get_today_fixtures(token=None):
    """
    Return today's PL fixtures as a list of dicts:
        {match_id, home, home_tla, home_id, home_crest,
         away, away_tla, away_id, away_crest,
         utc_kickoff (datetime), utc_kickoff_iso, venue, matchday}
    Only SCHEDULED/TIMED (not yet started) matches are included.
    Returns [] on any error or if no token is configured.
    """
    token = token if token is not None else config.FOOTBALL_API_TOKEN
    if not token:
        print("[fixtures] FOOTBALL_API_TOKEN not set - skipping match previews")
        return []
    url = (
        f"{config.FOOTBALL_BASE_URL}/competitions/"
        f"{config.FOOTBALL_COMPETITION}/matches?dateFrom={_today_iso()}&dateTo={_today_iso()}"
    )
    try:
        req = urllib.request.Request(url, headers={
            "X-Auth-Token": token,
            "User-Agent": "WeekendPulse/1.0",
        })
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, Exception) as e:
        print(f"[fixtures] failed to fetch fixtures: {e}")
        return []

    fixtures = []
    for m in data.get("matches", []):
        status = m.get("status", "")
        if status not in ("SCHEDULED", "TIMED"):
            continue  # skip live/finished/postponed
        ht = m.get("homeTeam") or {}
        at = m.get("awayTeam") or {}
        home = ht.get("name") or ""
        away = at.get("name") or ""
        if not home or not away:
            continue
        utc = None
        try:
            utc = datetime.datetime.fromisoformat(
                m.get("utcDate", "").replace("Z", "+00:00"))
        except Exception:
            utc = None
        if utc is None:
            continue
        fixtures.append({
            "match_id": m.get("id"),
            "home": home,
            "home_tla": ht.get("tla") or home,
            "home_id": ht.get("id"),
            "home_crest": ht.get("crest") or (f"https://crests.football-data.org/{ht.get('id')}.png" if ht.get("id") else ""),
            "away": away,
            "away_tla": at.get("tla") or away,
            "away_id": at.get("id"),
            "away_crest": at.get("crest") or (f"https://crests.football-data.org/{at.get('id')}.png" if at.get("id") else ""),
            "utc_kickoff": utc,
            "utc_kickoff_iso": m.get("utcDate", ""),
            "venue": m.get("venue") or "",
            "matchday": m.get("matchday"),
        })
    return fixtures


def match_key(fx):
    """Stable dedup key for a fixture: HOMETLA-vs-AWAYTLA-DATE."""
    date = fx.get("utc_kickoff").strftime("%Y-%m-%d") if fx.get("utc_kickoff") else _today_iso()
    return f"{fx.get('home_tla','')}-vs-{fx.get('away_tla','')}-{date}".lower()
