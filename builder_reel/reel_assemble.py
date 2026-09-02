"""Build the Colab notebook `news_reel.ipynb` from the builder cells.

readme: 01_intro.md
run cells: 02_install.py (deps)
write (embeds story_src/*.py): generated here
assets: 03_assets.py
render: 04_render.py
preview: 05_preview.py
download: 06_download.py

The heavy renderer (`story_src/reel_render.py`, `align.py`, `enhance.py`) is
base64-embedded into a single cell that writes them into the Colab working dir —
matching the proven ScaryTales "write files then run" pattern and keeping the
renderer single-source in this repo.
"""
import base64
import json
from pathlib import Path

HERE = Path(__file__).parent
STORY_SRC = HERE / "story_src"
OUT_CELLS = [
    "02_install.py", "03_assets.py", "04_render.py",
    "05_preview.py", "06_download.py", "07_post.py",
]
MDS = ["01_intro.md"]


def _code_cell(source: str):
    return {"cell_type": "code", "execution_count": None,
            "metadata": {}, "outputs": [],
            "source": [source + "\n"] if not source.endswith("\n") else [source]}


def _md_cell(source: str):
    return {"cell_type": "markdown", "metadata": {}, "source": [source]}


def _make_write_src_cell() -> dict:
    """Base64-embed story_src/*.py and write them into the notebook's dir."""
    lines = [
        "# Cell — install the renderer modules (reel_render.py, align.py, enhance.py).",
        "import base64",
        "from pathlib import Path",
        "SRC = Path('/content/weekendpulse_reels/story_src')",
        "SRC.mkdir(parents=True, exist_ok=True)",
    ]
    for py in sorted(STORY_SRC.glob("*.py")):
        b64 = base64.b64encode(py.read_bytes()).decode("ascii")
        lines.append(f"SRC.joinpath('{py.name}').write_text(")
        lines.append(f"    base64.b64decode('{b64}').decode('utf-8'))")
    lines.append("print('story_src installed:', sorted(p.name for p in SRC.glob('*.py')))")
    return _code_cell("\n".join(lines))


def build():
    cells = []
    for md in MDS:
        cells.append(_md_cell((HERE / md).read_text(encoding="utf-8").strip()))
    cells.append(_code_cell((HERE / OUT_CELLS[0]).read_text(encoding="utf-8").strip()))
    cells.append(_make_write_src_cell())
    for c in OUT_CELLS[1:]:
        cells.append(_code_cell((HERE / c).read_text(encoding="utf-8").strip()))
    nb = {"nbformat": 4, "nbformat_minor": 0, "metadata": {
        "colab": {"provenance": []},
        "kernelspec": {"display_name": "Python 3", "name": "python3"},
        "language_info": {"name": "python"},
    }, "cells": cells}
    return nb


def main():
    nb = build()
    out = HERE.parent / "news_reel.ipynb"
    out.write_text(json.dumps(nb, indent=1), encoding="utf-8")
    print("Wrote", out, f"({len(nb['cells'])} cells)")


if __name__ == "__main__":
    main()