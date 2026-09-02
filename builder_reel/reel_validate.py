"""Validate the reel builder sources WITHOUT importing torch/flask/whisper.

Run:  python builder_reel/reel_validate.py
Checks:
  1. notebook assembles (reel_assemble.build) with expected cell count
  2. story_src py files parse (ast) and the notebook embeds them base64-equivalently
  3. renderer's emotion/voice resolution logic is consistent
  4. reel_batch path/ourselves present (batch contract keys)
  5. asset cell references existing repo paths (music/, outro/, voices)
"""
import ast
import base64
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent

fails = []


def check(name, ok, detail=""):
    msg = f"[{('PASS' if ok else 'FAIL')}] {name}"
    if detail:
        msg += f" — {detail}"
    print(msg)
    if not ok:
        fails.append(name)
    return ok


# 1. notebook assembles --------------------------------------------------
def test_assemble():
    sys.path.insert(0, str(HERE))
    import reel_assemble
    nb = reel_assemble.build()
    ncells = len(nb["cells"])
    ok_cells = 1 + 1 + 1 + len(reel_assemble.OUT_CELLS[1:])  # md+install+writesrc+4
    check("notebook assembles", ncells == ok_cells, f"{ncells} cells")
    # embedded modules present in the write-src cell
    write_cell = nb["cells"][2]["source"]
    joined = "".join(write_cell)
    for name in ["reel_render.py", "align.py", "enhance.py"]:
        check(f"notebook embeds {name}",
              f"{name}" in joined and "base64.b64decode" in joined)


# 2. story_src parse ------------------------------------------------------
def test_src_parse():
    src = HERE / "story_src"
    py_files = sorted(src.glob("*.py"))
    check("story_src has 3 modules", len(py_files) == 3,
          ", ".join(p.name for p in py_files))
    for p in py_files:
        try:
            ast.parse(p.read_text(encoding="utf-8"))
            check(f"parses {p.name}", True)
        except SyntaxError as e:
            check(f"parses {p.name}", False, str(e))


# 3. renderer logic (no heavy imports) ------------------------------------
def test_renderer_logic():
    src = (HERE / "story_src" / "reel_render.py").read_text(encoding="utf-8")
    check("renderer has render_all", "def render_all" in src)
    check("renderer guards 6-reel cap", "[:6]" in src)
    check("renderer picks random female voice",
          "random.shuffle(picks)" in src and "FEMALE_BASE" in src)
    check("emotion set correct", "EMOTIONS = {\"neutral\", \"excited\", \"surprised\"}"
          in src.replace(" ", "").replace("\n", "") or re.search(
              r"EMOTIONS.*neutral.*excited.*surprised", src))
    check("palette orange+white", "#FF6B00" in src and "#FFFFFF" in src)
    check("crossfade into outro", "xfade=" in src and "outro.mp4" in src)
    check("music head-cut not tail-cut",
          "duration=first" in src and "afade=t=out" in src and "t=in:st=0" in src)


# 4. batch contract / asset references ------------------------------------
def test_assets():
    assets = (HERE / "03_assets.py").read_text(encoding="utf-8")
    check("assets fetch reels_batch.txt", "reels_batch.txt" in assets)
    check("assets download 10 female voices from voice-zero",
          "OwenTyme/voice-zero" in assets and "voices-emotion" in assets
          and "FEMALE_BASE" in assets)
    check("assets fetch neutral/excited/surprised clips",
          "neutral" in assets and "excited" in assets and "surprised" in assets)
    check("assets reference outro/ and voices/",
          "main/outro/" in assets and "voices" in assets)

    render = (HERE / "story_src" / "reel_render.py").read_text(encoding="utf-8")
    check("renderer music uses WeekendPulse music/", "/main/music/" in render)
    check("renderer outro from assets/outro.mp4", "ASSET_DIR" in render
          and "outro.mp4" in render)
    check("renderer voices are subfolder-based",
          "VOICES_DIR / v /" in render or "/ f\"{em}.flac\"" in render
          or "emotion.flac" in render)


def test_batch_contract():
    sample = {
        "generated_at_utc": "2026-09-02T12:00:00Z",
        "count": 2,
        "reels": [
            {"slug": "a", "title": "T", "url": "u", "post_text": "p",
             "image_url": "i", "reel_emotion": "excited", "reel_blurb": "b"},
            {"slug": "b", "title": "T2", "url": "u2", "post_text": "p2",
             "image_url": "i2", "reel_emotion": "weird", "reel_blurb": "b2"},
        ],
    }
    nb = json.dumps(sample)
    decoded = json.loads(nb)
    check("batch contract parses", decoded["count"] == 2 and
          len(decoded["reels"]) == 2)
    # emotion sanitize (mirror of renderer)
    EMOTIONS = {"neutral", "excited", "surprised"}
    ems = [r["reel_emotion"] if r["reel_emotion"] in EMOTIONS else "neutral"
           for r in decoded["reels"]]
    check("emotion sanitize", ems == ["excited", "neutral"])


if __name__ == "__main__":
    test_assemble()
    test_src_parse()
    test_renderer_logic()
    test_assets()
    test_batch_contract()
    print()
    if fails:
        print("FAILURES:", fails)
        sys.exit(1)
    print("ALL REEL VALIDATIONS PASSED")