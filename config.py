"""
WeekendPulse - Configuration
All secrets come from environment variables at runtime (never hardcoded).
"""
import os

# --- Facebook ---
FB_PAGE_ID = os.environ.get("FB_PAGE_ID", "1256418564223752")
FB_PAGE_TOKEN = os.environ.get("FB_PAGE_TOKEN", "")

# --- AI providers ---
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-20b")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "models/gemini-3.6-flash")

# --- RSS feed sources ---
RSS_FEEDS = [
    "https://feeds.bbci.co.uk/sport/football/rss.xml",
    "https://www.skysports.com/rss/12040",
    "https://www.theguardian.com/football/rss",
    "https://www.espn.com/espn/rss/soccer/news",
    "https://www.goal.com/en/rss",
    "https://www.football365.com/news/feed",
    "https://www.premierleague.com/news/rss",
    "https://www.fourfourtwo.com/feeds/all",
]

# --- Premier League keyword filter (title must relate to PL/English football) ---
PL_KEYWORDS = [
    "premier league", "arsenal", "chelsea", "liverpool", "manchester",
    "man united", "man city", "tottenham", "newcastle", "aston villa",
    "west ham", "brighton", "everton", "fulham", "brentford", "crystal palace",
    "wolves", "bournemouth", "nottingham", "leicester", "southampton",
    "leeds", "burnley", "luton", "sheffield", "premierleague",
    "england squad", "english football", "fa cup", "carabao",
]

# --- Posting ---
MAX_POSTS_PER_RUN = 1          # one post per scheduled run (5 runs/day)
DRY_RUN = os.environ.get("DRY_RUN", "0") == "1"

# --- Cross-source story dedup ---
# Two headlines count as the SAME story when they (a) share a real player/club
# name AND (b) reach this SequenceMatcher similarity ratio. This stops BBC/Sky/
# Guardian/FourFourTwo covering one story from being posted more than once.
# Raise to dedup harder (fewer posts), lower to allow more distinct posts.
DEDUP_THRESHOLD = float(os.environ.get("DEDUP_THRESHOLD", "0.3"))

# --- Reels (short per-article video summary) ---
REEL_EMOTIONS = ["neutral", "excited", "surprised"]
REEL_BLURB_MAX_WORDS = 55          # keeps each narration ~12s for retention
REEL_MAX_PER_RUN = 6               # cap on reels rendered in one nightly batch
REEL_TARGET_SECONDS = 16           # soft target (not enforced)
REEL_SOFT_MAX_SECONDS = 25         # soft ceiling: only a warning, never blocks/trims
ROWS_REEL_TODAY_UTC_HOUR = 0       # not used; reel cutoff is "posted today (UK)"
REEL_ACCENT_COLOR = "#FF6B00"      # vibrant orange
REEL_WHITE = "#FFFFFF"
REEL_DAYS_BACK = 1                 # only today's posted stories are reel-eligible

# --- Facebook Graph API ---
GRAPH_BASE = os.environ.get("GRAPH_BASE", "https://graph.facebook.com/v26.0")

# --- Fixtures / match-preview posts ---
FOOTBALL_API_TOKEN = os.environ.get("FOOTBALL_API_TOKEN", "")
FOOTBALL_BASE_URL = os.environ.get("FOOTBALL_BASE_URL", "https://api.football-data.org/v4")
FOOTBALL_COMPETITION = os.environ.get("FOOTBALL_COMPETITION", "PL")
MATCH_POST_HOURS_BEFORE = int(os.environ.get("MATCH_POST_HOURS_BEFORE", "5"))
MATCH_POST_MAX_PER_DAY = int(os.environ.get("MATCH_POST_MAX_PER_DAY", "10"))

# --- Paths ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "data", "weekendpulse.db")
MANIFEST_PATH = os.path.join(BASE_DIR, "manifest.json")
PROMPT_PATH = os.path.join(BASE_DIR, "prompts", "debate_post.txt")
MATCH_PROMPT_PATH = os.path.join(BASE_DIR, "prompts", "match_post.txt")
FONT_DIR = os.path.join(BASE_DIR, "data", "fonts")
IMAGE_DIR = os.path.join(BASE_DIR, "data", "images")

# --- Team accent colors (for image_gen) ---
TEAM_COLORS = {
    "arsenal": "#EF0107",
    "chelsea": "#034694",
    "liverpool": "#C8102E",
    "manchester city": "#6CABDD",
    "man city": "#6CABDD",
    "manchester united": "#DA291C",
    "man united": "#DA291C",
    "tottenham": "#132257",
    "newcastle": "#241F20",
    "aston villa": "#670E36",
    "west ham": "#7A263A",
    "brighton": "#0057B8",
    "everton": "#003399",
    "fulham": "#000000",
    "brentford": "#E30613",
    "crystal palace": "#1B458F",
    "wolves": "#FDB913",
    "bournemouth": "#DA291C",
    "nottingham": "#DD0000",
    "leicester": "#003090",
    "southampton": "#D71920",
}
