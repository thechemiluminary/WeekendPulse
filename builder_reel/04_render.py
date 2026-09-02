# Cell 4 — RENDER all reels in the batch (one MP4 per reel).
import json, time
from pathlib import Path

REEL_ROOT = Path("/content/weekendpulse_reels")
OUT = REEL_ROOT / "output"

# Load batch built in the Assets cell
with open(REEL_ROOT / "reels_batch.txt", encoding="utf-8") as f:
    batch = json.load(f)

entries = batch.get("reels", [])
entries = entries[:6]                       # soft cap REEL_MAX_PER_RUN=6
print(f"Rendering {len(entries)} reel(s) ...\n")

# the renderer module (written to disk by the 'write files' cell)
import sys
sys.path.insert(0, str(REEL_ROOT / "story_src"))
import reel_render

t_start = time.time()
results = reel_render.render_all(entries)
print("\n=== SUMMARY ===")
for r in results:
    print(f"  {r['slug']:<30} {r['duration_s']:>5.1f}s  emotion={r['emotion']:<9} music={r['music']}")

# persist summaries for the preview cell
(REEL_ROOT / "rendered_results.json").write_text(
    json.dumps(results, indent=2), encoding="utf-8")
(REEL_ROOT / "rendered_list.txt").write_text(
    "\n".join(str(OUT / r["slug"]) + ".mp4" for r in results), encoding="utf-8")
print(f"\nTotal render time: {time.time() - t_start:.0f}s")
print("Outputs:", OUT)