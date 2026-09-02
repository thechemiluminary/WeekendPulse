# Cell 7 — POST rendered reels to the Facebook Page and record results.
# Requires two secrets at RUNTIME (never hardcoded):
#   FB_PAGE_TOKEN  -> posts each reel via the Graph API `videos` endpoint
#   GH_TOKEN       -> writes the updated manifest.json back to the repo
# Both are entered via Colab secrets / getpass. This cell is idempotent: it
# posts only reels that are rendered and NOT already recorded as posted.
import json
import os
import time
import requests
from pathlib import Path
from getpass import getpass

REEL_ROOT = Path("/content/weekendpulse_reels")
OUT = REEL_ROOT / "output"
REPO = "thechemiluminary/WeekendPulse"
RAW = "https://raw.githubusercontent.com"
GRAPH = "https://graph.facebook.com/v26.0"
MANIFEST = "manifest.json"

FB_PAGE_TOKEN = os.environ.get("FB_PAGE_TOKEN", "") or getpass("FB page token (paste): ")
GH_TOKEN = os.environ.get("GH_TOKEN", "") or getpass("GitHub repo token (paste): ")
FB_PAGE_ID = os.environ.get("FB_PAGE_ID", "1256418564223752")

if not FB_PAGE_TOKEN or not GH_TOKEN:
    raise SystemExit("Both FB_PAGE_TOKEN and GH_TOKEN are required.")

# 1. Load rendered summaries + the batch we rendered.
with open(REEL_ROOT / "rendered_results.json", encoding="utf-8") as f:
    results = json.load(f)
with open(REEL_ROOT / "reels_batch.txt", encoding="utf-8") as f:
    batch = json.load(f)
by_slug = {r["slug"]: r for r in results}

# 2. Pull the current manifest from the repo so we update latest state.
def gh_manifest():
    try:
        r = requests.get(f"{RAW}/{REPO}/main/{MANIFEST}", timeout=30)
        r.raise_for_status()
        return r.json(), None
    except Exception as e:
        return None, str(e)

def gh_update(manifest_entries, sha):
    url = f"https://api.github.com/repos/{REPO}/contents/{MANIFEST}"
    payload = {
        "message": "chore: record posted reels [skip ci]",
        "content": __import__("base64").b64encode(
            json.dumps(manifest_entries, indent=2, ensure_ascii=False).encode("utf-8")
        ).decode("ascii"),
    }
    if sha:
        payload["sha"] = sha
    return requests.put(url, json=payload,
                        headers={"Authorization": f"Bearer {GH_TOKEN}",
                                 "Accept": "application/vnd.github+json",
                                 "User-Agent": "wp"}, timeout=60)

# A slug -> entry map (slug is stable across batch + manifest via same slugger).
manifest_entries, m_err = gh_manifest()
if manifest_entries is None:
    print("WARN could not fetch manifest:", m_err, "- using empty base.")
    manifest_entries = []

if not isinstance(manifest_entries, list):
    manifest_entries = manifest_entries.get("entries", []) if isinstance(manifest_entries, dict) else []

sha = None
try:
    r = requests.get(f"https://api.github.com/repos/{REPO}/contents/{MANIFEST}",
                     headers={"Accept": "application/vnd.github+json",
                              "User-Agent": "wp"}, timeout=30)
    if r.status_code == 200:
        sha = r.json().get("sha")
except Exception:
    sha = None

def slug_for(url, title):
    url = (url or "").strip()
    if url:
        base = url.rstrip("/").rsplit("/", 1)[-1]
        base = "".join(c for c in base if c.isalnum() or c in "-_") or "reel"
        return base[:40]
    t = (title or "").strip().lower()
    return (("-".join(w for w in t.replace("-", " ").split() if w)[:5])[:40]) or "reel"

by_manifest = {}
for e in manifest_entries:
    s = e.get("slug") or slug_for(e.get("url"), e.get("title"))
    by_manifest[s] = e

header = {"Authorization": f"Bearer {FB_PAGE_TOKEN}"}
posted = 0
skipped = 0
failed = []
for ent in batch.get("reels", []):
    slug = ent["slug"]
    summary = by_slug.get(slug)
    mp4 = OUT / f"{slug}.mp4"
    if not mp4.exists():
        print(f"  SKIP {slug}: mp4 not found")
        skipped += 1
        continue

    m = by_manifest.get(slug, {"slug": slug})
    if m.get("reel_posted"):
        print(f"  SKIP {slug}: already posted (id={m.get('reel_video_id')})")
        skipped += 1
        continue

    title = ent.get("title", "")
    desc = ent.get("reel_blurb", "") or title
    print(f"  POST {slug} -> videos ...")
    try:
        with open(mp4, "rb") as vf:
            resp = requests.post(
                f"{GRAPH}/{FB_PAGE_ID}/videos",
                files={"source": ("reel.mp4", vf, "video/mp4")},
                data={"title": title, "description": desc},
                headers=header, timeout=600)
        data = resp.json()
        if resp.status_code == 200 and ("id" in data):
            vid = data["id"]
            m.update({
                "rendered": True,
                "reel_posted": True,
                "reel_video_id": vid,
                "reel_voice": summary.get("voice", "") if summary else "",
                "reel_emotion_used": summary.get("emotion", "") if summary else "",
                "reel_music": summary.get("music") or "" if summary else "",
                "reel_rendered_at": __import__("datetime").datetime.now(
                    __import__("datetime").timezone.utc).isoformat(),
            })
            by_manifest[slug] = m
            posted += 1
            print(f"    posted id={vid}")
        else:
            failed.append((slug, data))
            print(f"    FAIL {slug}: {data}")
    except Exception as e:
        failed.append((slug, str(e)))
        print(f"    ERROR {slug}: {e}")

# 3. Write the manifest back to the repo.
out_list = list(by_manifest.values())
put = gh_update(out_list, sha)
if put.status_code in (200, 201):
    print(f"\nManifest updated on repo ({len(out_list)} entries).")
else:
    print(f"\nManifest write-back FAILED ({put.status_code}): {put.text[:300]}")

print(f"\nPosted: {posted}  Skipped(already): {skipped}  Failed: {len(failed)}")
if failed:
    print("Failed:", json.dumps(failed, default=str))
