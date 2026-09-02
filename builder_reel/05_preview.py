# Cell 5 — Preview each rendered reel, switching with a slider (Next/Previous).
# Uses ipywidgets + embedded IPython.display.Video so it plays reliably in Colab.
import json
from pathlib import Path
from IPython.display import display, Video

REEL_ROOT = Path("/content/weekendpulse_reels")
OUT = REEL_ROOT / "output"

# --- order rendered mp4s by slug (render summary order if present)
results = []
res_path = REEL_ROOT / "rendered_results.json"
if res_path.exists():
    with open(res_path, encoding="utf-8") as f:
        results = json.load(f)
paths = [p for r in results
         if (p := OUT / f"{r['slug']}.mp4").exists()]
if not paths:
    paths = sorted(OUT.glob("*.mp4"))

if not paths:
    print("No rendered MP4s yet — run the RENDER cell first.")
else:
    def show(i):
        i = max(0, min(len(paths) - 1, i))
        path = paths[i]
        meta = results[i] if i < len(results) else {}
        print(f"{i+1}/{len(paths)}  {path.name}  "
              f"emotion={meta.get('emotion','?')}  music={meta.get('music','-')}  "
              f"{meta.get('duration_s',0):.1f}s")
        display(Video(filename=str(path), embed=True,
                      metadata={"mimetype": "video/mp4"}, width=360))
        state = REEL_ROOT / "preview_state.json"
        state.write_text(json.dumps({"i": i}), encoding="utf-8")

    try:
        import ipywidgets as widgets
        idx = 0
        s = REEL_ROOT / "preview_state.json"
        if s.exists():
            idx = json.loads(s.read_text(encoding="utf-8")).get("i", 0)
        slider = widgets.IntSlider(min=0, max=len(paths) - 1, value=idx,
                                   description="Reel")
        out = widgets.Output()
        # re-draw on slider change
        def _on_change(change):
            out.clear_output(wait=True)
            with out:
                show(change["new"])
        slider.observe(_on_change, names="value")
        display(widgets.VBox([
            widgets.HBox([widgets.Label("Index:"), slider]),
            out,
        ]))
        with out:
            show(slider.value)
    except Exception as _e:
        # fallback: static preview of the first reel
        print("ipywidgets unavailable — showing first reel.")
        show(0)