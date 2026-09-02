# Cell 6 — Download rendered MP4s (zip them all, plus individual links).
import zipfile
from pathlib import Path
from IPython.display import FileLink, HTML, display

OUT = Path("/content/weekendpulse_reels/output")
mp4s = sorted(str(p) for p in OUT.glob("*.mp4"))
if not mp4s:
    print("No rendered MP4s yet — run the RENDER cell first.")
else:
    zip_path = OUT / "reels.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for m in mp4s:
            z.write(m, arcname=Path(m).name)
    print(f"{len(mp4s)} reel(s) in {zip_path.name}  ({zip_path.stat().st_size//1024} KiB)")
    display(FileLink(str(zip_path), result_html_prefix="Download all: "))
    display(HTML("<h4>Download individually</h4>"))
    for m in mp4s:
        display(FileLink(m))