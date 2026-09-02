"""
WeekendPulse - Match-preview VS card generator.
Composes a 1080x1350 (4:5 portrait) card with the two clubs' REAL crests
(downloaded from crests.football-data.org), a center "VS", a WeekEndPulse
"TONIGHT" header and the kickoff time. If a crest fails to download it falls
back to a team-colour split so the scheduler never crashes.
"""
import os
import io
import requests
from PIL import Image, ImageDraw, ImageFont

from config import IMAGE_DIR
from image_gen import _find_font, _wrap_text

W, H = 1080, 1350
ACCENT = "#FF6B00"
WHITE = "#FFFFFF"
DARK = "#10131A"
MID = "#1C2230"

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) WeekendPulse bot/1.0"


def _load_crest(url):
    """Download a crest; return a RGBA PIL image or None on any failure."""
    if not url:
        return None
    try:
        r = requests.get(url, headers={"User-Agent": _UA}, timeout=20)
        r.raise_for_status()
        return Image.open(io.BytesIO(r.content)).convert("RGBA")
    except Exception as e:
        print(f"[match_card] crest download failed ({url}): {e}")
        return None


def _team_color(name):
    t = (name or "").lower()
    for key, color in _TEAM_COLORS.items():
        if key in t:
            return color
    return "#3D195B"


def _paste_crest_padded(canvas, draw, crest, cx, cy, size, name, round_canvas):
    box_w = int(size * 1.45)
    box_h = int(size * 1.1)
    left = cx - box_w // 2
    top = cy - box_h // 2
    draw.rounded_rectangle([left, top, left + box_w, top + box_h], radius=28,
                           fill=MID, outline=(255, 255, 255, 60), width=4)
    if crest is not None:
        c = crest.resize((size, size), Image.LANCZOS)
        # round the crest corners a touch
        mask = Image.new("L", (size, size), 0)
        md = ImageDraw.Draw(mask)
        md.rounded_rectangle([0, 0, size, size], radius=int(size * 0.12), fill=255)
        canvas.paste(c, (cx - size // 2, cy - size // 2), mask)
    font = _find_font(40, bold=True)
    label = _wrap_text(name, 14)
    yy = top + box_h + 22
    for line in label[:2]:
        lw = draw.textlength(line, font=font)
        draw.text(((W - lw) / 2, yy), line, fill=WHITE, font=font)
        yy += font.size + 6


def make_match_card(fx, kickoff_label, out_name):
    """
    Build the VS card. fx provides home/home_crest/away/away_crest.
    Returns the saved file path.
    """
    os.makedirs(IMAGE_DIR, exist_ok=True)

    img = Image.new("RGB", (W, H), DARK)
    draw = ImageDraw.Draw(img)
    canvas = img

    # Header band
    draw.rectangle([0, 0, W, 150], fill=ACCENT)
    font_logo = _find_font(64, bold=True)
    lw = draw.textlength("WEEKENDPULSE", font=font_logo)
    draw.text(((W - lw) / 2, 30), "WEEKENDPULSE", fill=DARK, font=font_logo)
    font_sub = _find_font(40, bold=True)
    sw = draw.textlength("TONIGHT", font=font_sub)
    draw.text(((W - sw) / 2, 104), "TONIGHT", fill=DARK, font=font_sub)

    # Load crests
    home_crest = _load_crest(fx.get("home_crest"))
    away_crest = _load_crest(fx.get("away_crest"))

    # Center bands
    top_cy = 520
    bottom_cy = 1040
    size = 230

    # Home band (top): home crest + name
    hc = _team_color(fx.get("home"))
    draw.rectangle([0, 300, W, top_cy - 40], fill=_shade(hc))
    _paste_crest_padded(canvas, draw, home_crest, W // 2, top_cy, size,
                        fx.get("home") or fx.get("home_tla") or "HOME", canvas)

    # Away band (bottom): away crest + name
    ac = _team_color(fx.get("away"))
    draw.rectangle([0, bottom_cy - 60, W, H - 260], fill=_shade(ac))
    _paste_crest_padded(canvas, draw, away_crest, W // 2, bottom_cy, size,
                        fx.get("away") or fx.get("away_tla") or "AWAY", canvas)

    # Center "VS"
    font_vs = _find_font(96, bold=True)
    vw = draw.textlength("VS", font=font_vs)
    draw.text(((W - vw) / 2, 720), "VS", fill=ACCENT, font=font_vs)

    # Kickoff line at the bottom
    font_ko = _find_font(48, bold=True)
    ko_text = kickoff_label or "KICKOFF TONIGHT"
    kw = draw.textlength(ko_text, font=font_ko)
    draw.text(((W - kw) / 2, H - 160), ko_text, fill=WHITE, font=font_ko)

    out_path = os.path.join(IMAGE_DIR, out_name)
    img.save(out_path, "PNG")
    return out_path


def _shade(hex_color):
    """Return a darkened version of a hex color for a band."""
    r = int(hex_color[1:3], 16)
    g = int(hex_color[3:5], 16)
    b = int(hex_color[5:7], 16)
    return (r // 2, g // 2, b // 2)


# local team colors (avoid cycle)
_TEAM_COLORS = {
    "arsenal": "#EF0107",
    "chelsea": "#034694",
    "liverpool": "#C8102E",
    "man city": "#6CABDD",
    "manchester city": "#6CABDD",
    "man united": "#DA291C",
    "manchester united": "#DA291C",
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
