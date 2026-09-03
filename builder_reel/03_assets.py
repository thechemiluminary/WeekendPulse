# Cell 3 — Assets: fetch reels_batch.txt + 10 female voices + outro.
import os, json, subprocess, urllib.request, urllib.parse, shutil
from pathlib import Path

# Reels working dir #######################################################
REEL_ROOT = Path("/content/weekendpulse_reels")
V = REEL_ROOT / "voices"
O = REEL_ROOT / "output"
A = REEL_ROOT / "assets"
for d in (V, O, A):
    d.mkdir(parents=True, exist_ok=True)

REPO = "thechemiluminary/WeekendPulse"
RAW = "https://raw.githubusercontent.com"

# 1. Batch of approved reels (produced by the GitHub reel_batch workflow) ###
def fetch_raw(path):
    url = f"{RAW}/{REPO}/main/{path}"
    with urllib.request.urlopen(url, timeout=40) as r:
        return r.read()

try:
    batch_bytes = fetch_raw("reels_batch.txt")
    (REEL_ROOT / "reels_batch.txt").write_bytes(batch_bytes)
    batch = json.loads(batch_bytes.decode("utf-8"))
    print(f"Loaded reels_batch.txt: {len(batch['reels'])} reel(s)")
except Exception as e:
    print("WARN could not fetch a fresh reels_batch.txt:", e)
    batch = {"generated_at_utc": None, "count": 0, "reels": []}

# 2. Download 10 female voice folders + emotion clips ####################
def dl(url, dest):
    try:
        urllib.request.urlretrieve(url, dest)
    except Exception:
        return False
    return Path(dest).exists() and Path(dest).stat().st_size > 1000

# voices-emotion/<voice>/<emotion>.flac  (OwenTyme/voice-zero, public)
VOICE_REPO = "OwenTyme/voice-zero"
VOICE_PATH = "voices-emotion"
FEMALE_BASE = [
    "kristin_hughes", "jodi_krangle", "karen_savage",
    "emily_cripps", "cori_samuel", "mil_nicholson",
    "amy_koenig", "alana_jordan", "emily_anderson", "anna_simon",
]
# only fetch the emotions this project uses; neutral always
EMOTION_CLIPS = ["neutral", "excited", "surprised"]
got_voices = []
for v in FEMALE_BASE:
    vdir = V / v
    vdir.mkdir(parents=True, exist_ok=True)
    have = 0
    for em in EMOTION_CLIPS:
        dest = vdir / f"{em}.flac"
        url = (f"{RAW}/{VOICE_REPO}/main/{VOICE_PATH}/"
               f"{urllib.parse.quote(v)}/{em}.flac")
        if dl(url, dest):
            have += 1
    if have:
        got_voices.append(v)
        print(f"  voice + {v} ({have}/{len(EMOTION_CLIPS)} clips)")
    else:
        print(f"  MISSING voice {v}")
print(f"Downloaded {len(got_voices)} female voice(s) into {V}: {got_voices}")
if not got_voices:
    raise RuntimeError("No voices downloaded - check VOICE_REPO/path above")

# 3. Outro clip (user's fixed 4s outro) ###################################
outro_src = A / "outro.mp4"
outro_url = f"{RAW}/{REPO}/main/outro/{'outro.mp4'}"
if not outro_src.exists() or outro_src.stat().st_size < 1000:
    dl(outro_url, outro_src)
if outro_src.exists() and outro_src.stat().st_size > 1000:
    print("outro.mp4 ready:", outro_src.stat().st_size // 1024, "KiB")
else:
    print("WARN outro.mp4 missing — reels will render without the outro clip")

# 4. Anton font (brand, all-caps titles) ###################################
anton_src = A / "Anton-Regular.ttf"
if not anton_src.exists() or anton_src.stat().st_size < 1000:
    dl(f"{RAW}/{REPO}/main/data/fonts/Anton-Regular.ttf", anton_src)
# copy to REEL_ROOT so reel_render._find_font picks it up
if anton_src.exists() and anton_src.stat().st_size > 1000:
    shutil.copy(anton_src, REEL_ROOT / "Anton-Regular.ttf")
    print("Anton font ready:", anton_src.stat().st_size // 1024, "KiB")
else:
    print("WARN Anton font missing — reel titles will use DejaVuSans fallback")

print("\nAssets ready. Review reels_batch.txt before rendering.")