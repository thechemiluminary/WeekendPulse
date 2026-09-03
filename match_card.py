"""
WeekendPulse - Match-preview VS card generator (template-driven).
Composites a user-designed 1080x1350 PSD template (MATCH_TEMPLATE_PSD.psd) and
places the two clubs' REAL LOCAL crests (logos/PL/*.png) into the Home/Away
slot layers, plus the kickoff time (Anton, all-caps) into the kickoff slot
layer. The PSD defines the design + slot geometry via named shape layers, so
layout is always pixel-perfect (no code-guessed overlap).

If the PSD cannot be loaded, falls back to a simple rectangle card so the
scheduler never crashes.
"""
import os
import io
import requests
from PIL import Image, ImageDraw, ImageFont, ImageFilter

import config
from config import IMAGE_DIR, MATCH_TEMPLATE_PSD, FONT_ANTON
import crests

W, H = 1080, 1350
WHITE = "#FFFFFF"
DARK = "#10131A"

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) WeekendPulse bot/1.0"


# --------------------------------------------------------------------------
# Template / slot loading via psd-tools
# --------------------------------------------------------------------------
def _load_template():
    """
    Return (canvas_rgba, slot_bounds) where slot_bounds is a dict:
        {"home": (x0,y0,x1,y1), "away": ..., "kickoff": ...}
    Each is the bounding box of the named shape layer. Returns (None, {})
    on any failure (caller falls back).
    """
    if not os.path.exists(MATCH_TEMPLATE_PSD):
        print("[match_card] template not found, using fallback")
        return None, {}
    try:
        from psd_tools import PSDImage
        psd = PSDImage.open(MATCH_TEMPLATE_PSD)
        canvas = psd.composite().convert("RGBA")
        slots = {}
        # match by name (case-insensitive, allow home/away_crest variants)
        def find(n):
            for lay in psd:
                if lay.name.lower() == n:
                    return lay
            return None
        for key, names in (
            ("home", ("home", "home_crest")),
            ("away", ("away", "away_crest")),
            ("kickoff", ("kickoff", "kickoff_slot")),
        ):
            for n in names:
                lay = find(n)
                if lay is not None:
                    b = lay.bbox
                    slots[key] = tuple(int(v) for v in b)
                    break
        return canvas, slots
    except Exception as e:
        print(f"[match_card] template load failed ({e}), using fallback")
        return None, {}


def _load_crest_image(fx, side):
    """
    Resolve + open the crest for home/away as RGBA, or None.
    Prefers local logos/PL/*.png; falls back to remote URL.
    """
    key = "home" if side == "home" else "away"
    team = fx.get(key) or fx.get(f"{key}_tla") or ""
    remote = fx.get(f"{key}_crest") or (fx.get(f"{key}_id") and
                                        f"https://crests.football-data.org/{fx.get(f'{key}_id')}.png")
    src, found = crests.resolve_crest(team, remote)
    if src == "local":
        try:
            return Image.open(found).convert("RGBA")
        except Exception as e:
            print(f"[match_card] local crest open failed ({found}): {e}")
            return None
    if src == "remote":
        try:
            r = requests.get(found, headers={"User-Agent": _UA}, timeout=20)
            r.raise_for_status()
            return Image.open(io.BytesIO(r.content)).convert("RGBA")
        except Exception as e:
            print(f"[match_card] remote crest download failed ({found}): {e}")
            return None
    print(f"[match_card] no crest for team '{team}'")
    return None


def _paste_crest_contain(canvas, crest, box, shadow_radius=8, shadow_alpha=80, shadow_color=(255, 255, 255)):
    """
    Paste a crest image contained within box (x0,y0,x1,y1) preserving aspect
    ratio + transparency, centred in the box.  Adds a soft white shadow
    surrounding all edges equally (zero-offset) so the crest reads cleanly
    on the card.
    """
    if crest is None:
        return
    x0, y0, x1, y1 = box
    bw, bh = x1 - x0, y1 - y0
    scale = min(bw / crest.width, bh / crest.height)
    nw, nh = max(1, int(crest.width * scale)), max(1, int(crest.height * scale))
    c = crest.resize((nw, nh), Image.LANCZOS).convert("RGBA")
    cx = x0 + (bw - nw) // 2
    cy = y0 + (bh - nh) // 2

    # Build shadow: silhouette of the crest in shadow_color, blurred outward
    # (subtle, barely noticeable). Zero offset - surrounds all edges equally.
    pad = shadow_radius * 2
    sw, sh = nw + pad, nh + pad
    shadow = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
    # Create silhouette copy of crest (preserve alpha shape), scaled down in
    # alpha so the shadow stays faint
    col_crest = Image.new("RGBA", c.size, (*shadow_color, shadow_alpha))
    col_crest.putalpha(c.split()[3].point(lambda a: int(a * (shadow_alpha / 255))))
    shadow.paste(col_crest, (shadow_radius, shadow_radius))
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=shadow_radius))
    canvas.alpha_composite(shadow, (cx - shadow_radius, cy - shadow_radius))

    canvas.alpha_composite(c, (cx, cy))


def _anton_font(size):
    """Return Anton font at the given size, or a bold fallback."""
    if os.path.exists(FONT_ANTON):
        return ImageFont.truetype(FONT_ANTON, size)
    from image_gen import _find_font
    return _find_font(size, bold=True)


def _draw_kickoff(canvas, text, box):
    """Draw the kickoff label (Anton, all-caps) centred in box."""
    if not box:
        return
    x0, y0, x1, y1 = box
    label = (text or "KICKOFF TONIGHT").upper()
    size = config.MATCH_KICKOFF_FONT_SIZE
    color = config.MATCH_KICKOFF_COLOR
    draw = ImageDraw.Draw(canvas)
    # shrink font so text fits the box width
    font = _anton_font(size)
    while font.getlength(label) > (x1 - x0) and size > 24:
        size -= 2
        font = _anton_font(size)
    w = font.getlength(label)
    cx = x0 + (x1 - x0 - w) / 2
    cy = y0 + (y1 - y0) / 2
    # approximate vertical centre via ascent
    asc, desc = font.getmetrics()
    ty = cy - (asc + desc) / 2
    draw.text((cx, ty), label, font=font, fill=color)


# --------------------------------------------------------------------------
# Public builders
# --------------------------------------------------------------------------
def make_match_card(fx, kickoff_label, out_name):
    """
    Build the VS card from the PSD template. fx provides
    home/home_crest/away/away_crest (+ _id). Returns the saved file path.
    """
    os.makedirs(IMAGE_DIR, exist_ok=True)
    if not out_name.endswith(".png"):
        out_name += ".png"
    out_path = os.path.join(IMAGE_DIR, out_name)

    canvas, slots = _load_template()
    if canvas is not None and slots:
        _build_from_template(canvas, slots, fx, kickoff_label, out_path)
        return out_path

    # Fallback: simple generated card (never crash)
    _build_fallback(fx, kickoff_label, out_path)
    return out_path


def _build_from_template(canvas, slots, fx, kickoff_label, out_path):
    # paste crests
    _paste_crest_contain(canvas, _load_crest_image(fx, "home"), slots.get("home"))
    _paste_crest_contain(canvas, _load_crest_image(fx, "away"), slots.get("away"))
    # kickoff text
    _draw_kickoff(canvas, kickoff_label, slots.get("kickoff"))
    canvas.convert("RGB").save(out_path, "PNG")


def _build_fallback(fx, kickoff_label, out_path):
    """Basic non-blocking fallback card (previous layout) if template is missing."""
    img = Image.new("RGBA", (W, H), DARK)
    draw = ImageDraw.Draw(img)
    from image_gen import _find_font
    font_logo = _find_font(64, bold=True)
    lw = draw.textlength("WEEKENDPULSE", font=font_logo)
    draw.text(((W - lw) / 2, 30), "WEEKENDPULSE", fill=WHITE, font=font_logo)
    _paste_crest_contain(img, _load_crest_image(fx, "home"), (389, 320, 691, 622))
    _paste_crest_contain(img, _load_crest_image(fx, "away"), (389, 728, 691, 1030))
    _draw_kickoff(img, kickoff_label, (224, 1136, 857, 1289))
    img.save(out_path, "PNG")
