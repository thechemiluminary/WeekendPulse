"""
WeekendPulse - Configuration
All secrets come from environment variables at runtime (never hardcoded).
"""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# --- Facebook ---
FB_PAGE_ID = os.environ.get("FB_PAGE_ID", "1256418564223752")
FB_PAGE_TOKEN = os.environ.get("FB_PAGE_TOKEN", "")

# --- AI providers ---
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
# Extra Groq keys for the social engine's multi-API-key rotation. If one key is
# rate-limited/errors, the next key is tried. Empty keys are skipped.
GROQ_API_KEY_2 = os.environ.get("GROQ_API_KEY_2", "")
GROQ_API_KEY_3 = os.environ.get("GROQ_API_KEY_3", "")
# Dedicated key for the social engagement engine (user's 2nd account). Falls
# back to GEMINI_API_KEY then GROQ_API_KEY.
GEMINI_KEY_SOCIAL = os.environ.get("GEMINI_KEY_SOCIAL", "")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-20b")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "models/gemini-3.6-flash")
# Primary social engine provider: OpenRouter (OpenAI-compatible gateway). It
# replaces GEMINI_KEY_SOCIAL which was 403-blocked. Images not supported (no
# Search Grounding) -> social posts are text-only via this path.
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "google/gemini-3.6-flash")

# --- Extra OpenAI-compatible fallback providers (both host gpt-oss-120b) ---
# Cerebras: free-ish tier, ultra-fast, OpenAI-compatible.
CEREBRAS_API_KEY = os.environ.get("CEREBRAS_API_KEY", "")
CEREBRAS_BASE_URL = os.environ.get("CEREBRAS_BASE_URL", "https://api.cerebras.ai/v1")
CEREBRAS_MODEL = os.environ.get("CEREBRAS_MODEL", "gpt-oss-120b")
# NVIDIA NIM: free OpenAI-compatible endpoint (replaces the retired GitHub Models).
NIM_API_KEY = os.environ.get("NIM_API_KEY", "")
NIM_BASE_URL = os.environ.get("NIM_BASE_URL", "https://integrate.api.nvidia.com/v1")
NIM_MODEL = os.environ.get("NIM_MODEL", "openai/gpt-oss-20b")

# --- Semi-auto social mode ---
# When enabled, the social engine does NOT auto-publish to Facebook. Instead it
# generates a draft and sends it to the user's Telegram bot (TG_BOT_TOKEN ->
# TG_CHAT_ID) so the user manually adds an image and posts. Drafts are tracked
# separately and do NOT count toward the SOCIAL_MAX_PER_DAY cap.
SOCIAL_SEMIAUTO = os.environ.get("SOCIAL_SEMIAUTO", "0") == "1"
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN", "")
TG_CHAT_ID = os.environ.get("TG_CHAT_ID", "")

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
MAX_POSTS_PER_RUN = 3          # up to 3 posts per run (compensates for missed cron runs)
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

# --- Match card template (user-designed PSD) + local crests ---
MATCH_TEMPLATE_PSD = os.environ.get(
    "MATCH_TEMPLATE_PSD", os.path.join(BASE_DIR, "MATCH_TEMPLATE_PSD.psd"))
LOGOS_DIR = os.environ.get("LOGOS_DIR", os.path.join(BASE_DIR, "logos", "PL"))
FONT_ANTON = os.path.join(BASE_DIR, "data", "fonts", "Anton-Regular.ttf")
# Kickoff text styling on the match card (Anton, all-caps)
MATCH_KICKOFF_FONT_SIZE = int(os.environ.get("MATCH_KICKOFF_FONT_SIZE", "96"))
MATCH_KICKOFF_COLOR = os.environ.get("MATCH_KICKOFF_COLOR", "#FFFFFF")

# --- Paths ---
DB_PATH = os.path.join(BASE_DIR, "data", "weekendpulse.db")
MANIFEST_PATH = os.path.join(BASE_DIR, "manifest.json")
PROMPT_PATH = os.path.join(BASE_DIR, "prompts", "debate_post.txt")
MATCH_PROMPT_PATH = os.path.join(BASE_DIR, "prompts", "match_post.txt")
FONT_DIR = os.path.join(BASE_DIR, "data", "fonts")
IMAGE_DIR = os.path.join(BASE_DIR, "data", "images")

# --- Social engagement engine ---
SOCIAL_ENABLED = os.environ.get("SOCIAL_ENABLED", "1") == "1"
SOCIAL_MAX_PER_DAY = int(os.environ.get("SOCIAL_MAX_PER_DAY", "6"))
# Explicit UK (Europe/London) fire slots: (hour, minute). 6 posts/day.
SOCIAL_POST_SLOTS = [(11, 30), (14, 0), (15, 0), (16, 0), (19, 0), (20, 0)]
# How many minutes after a slot the engine is still allowed to fire (the 5-min
# collector means the actual run can land a few minutes late).
SOCIAL_FIRE_WINDOW_MIN = int(os.environ.get("SOCIAL_FIRE_WINDOW_MIN", "10"))
SOCIAL_GROUNDED = os.environ.get("SOCIAL_GROUNDED", "1") == "1"
SOCIAL_NUM_CANDIDATES = int(os.environ.get("SOCIAL_NUM_CANDIDATES", "4"))
# How many pooled talking points are sent to the AI per request. Keeps the
# prompt small/inside model input limits even if many channels/subreddits are
# configured (collector may still ingest more; only the prompt is capped).
SOCIAL_POOL_LIMIT = int(os.environ.get("SOCIAL_POOL_LIMIT", "15"))
SOCIAL_EMBED_MODEL = os.environ.get("SOCIAL_EMBED_MODEL", GEMINI_MODEL)
# Sources ingested by the 5-min collector (free, stable, token-less).
SOCIAL_TELEGRAM_CHANNELS = os.environ.get(
    "SOCIAL_TELEGRAM_CHANNELS",
    "FabrizioRomanoTG",
).split(",")
SOCIAL_REDDIT_SUBS = os.environ.get("SOCIAL_REDDIT_SUBS", "soccer").split(",")
# Trusted image domains for the grounding image_url (avoids junk attachments).
SOCIAL_IMAGE_ALLOW = [
    "cdn.", "images.", "media.", "static.", "img.", "assets.", "ichef.",
    "upload.", "thumbnails.", "ts1.", "ts2.",
]

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
