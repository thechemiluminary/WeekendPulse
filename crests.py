"""
WeekendPulse - Local crest resolution.
Maps a football-data.org team name to a LOCAL logo file under logos/PL/
(1500x1500 transparent PNGs). Falls back to the remote crests.football-data.org
URL if no local file matches, and ultimately to None (caller decides fallback).

The football-data API returns names like "Liverpool FC", "Ipswich Town FC",
"Manchester United FC", "AFC Bournemouth". Our local files are the slug names
(e.g. liverpool-fc.png, ipswich-town.png, manchester-united.png).
"""
import os

import config

_LOGO_DIR = config.LOGOS_DIR

# Local logo slug -> the football-data display names it should match.
# Each local file lives at logos/PL/<slug>.png
_TEAM_ALIASES = {
    "afc-bournemouth": ["afc bournemouth", "bournemouth"],
    "arsenal": ["arsenal"],
    "aston-villa": ["aston villa"],
    "brentford": ["brentford"],
    "brighton-and-hove-albion": ["brighton", "brighton and hove albion"],
    "chelsea": ["chelsea"],
    "coventry-city": ["coventry", "coventry city"],
    "crystal-palace": ["crystal palace"],
    "everton": ["everton"],
    "fulham": ["fulham"],
    "hull-city": ["hull", "hull city"],
    "ipswich-town": ["ipswich", "ipswich town"],
    "leeds-united": ["leeds", "leeds united"],
    "liverpool-fc": ["liverpool"],
    "manchester-city": ["manchester city"],
    "manchester-united": ["manchester united"],
    "newcastle-united": ["newcastle", "newcastle united"],
    "nottingham-forest": ["nottingham forest", "nottingham"],
    "sunderland": ["sunderland"],
    "tottenham-hotspur": ["tottenham", "tottenham hotspur"],
}


def _norm(name):
    """Lowercase, strip 'fc'/'afc' suffixes and punctuation for fuzzy match."""
    n = (name or "").lower().strip()
    for suf in (" football club", " fc", " afc"):
        if n.endswith(suf):
            n = n[: -len(suf)]
    return n.strip()


def local_logo_path(team_name):
    """Return the local logos/PL/<slug>.png path for a team name, or None."""
    n = _norm(team_name)
    if not n:
        return None
    # exact alias match first
    for slug, aliases in _TEAM_ALIASES.items():
        if any(_norm(a) == n for a in aliases):
            p = os.path.join(_LOGO_DIR, f"{slug}.png")
            if os.path.exists(p):
                return p
    # fallback: try the normalized name itself as a filename
    cand = n.replace(" ", "-")
    p = os.path.join(_LOGO_DIR, f"{cand}.png")
    if os.path.exists(p):
        return p
    return None


def resolve_crest(team_name, remote_url=None):
    """
    Return (source, image_path_or_url) for a team crest.
    source is 'local' (path), 'remote' (url) or None (no crest found).
    Prefers the local 1500x1500 PNG; falls back to the football-data URL.
    """
    local = local_logo_path(team_name)
    if local:
        return "local", local
    if remote_url:
        return "remote", remote_url
    return None, None
