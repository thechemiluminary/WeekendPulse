"""
WeekendPulse - Pillow graphic generator.
Creates a simple branded debate card per post (optional).
If no font found, falls back to default (may look plain but still works).
"""
import os
from PIL import Image, ImageDraw, ImageFont
from config import IMAGE_DIR, FONT_DIR


def _find_font(size, bold=True):
    if os.path.exists(FONT_DIR):
        for name in ("montserrat-bold.ttf", "arialbd.ttf"):
            p = os.path.join(FONT_DIR, name)
            if os.path.exists(p):
                return ImageFont.truetype(p, size)
    # system fallbacks
    for p in (
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/bahnschrift.ttf",
    ):
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def _pick_color(title):
    t = title.lower()
    for key, color in _TEAM_COLORS.items():
        if key in t:
            return color
    return "#3D195B"  # default WeekendPulse purple


def make_debate_card(title, post_text, out_name):
    """
    Create a 1080x1080 debate card. Returns the saved file path.
    """
    os.makedirs(IMAGE_DIR, exist_ok=True)
    bg_color = _pick_color(title)
    img = Image.new("RGB", (1080, 1080), bg_color)
    draw = ImageDraw.Draw(img)

    font_head = _find_font(64, bold=True)
    font_body = _find_font(42, bold=False)

    # Header: brand + topic line
    draw.text((60, 60), "WEEKENDPULSE", fill=(255, 255, 255), font=font_head)

    # Wrap body text (approx char widths)
    wrapped = _wrap_text(post_text, 40)

    y = 220
    for line in wrapped[:14]:  # cap lines to fit card
        draw.text((60, y), line, fill=(255, 255, 255), font=font_body)
        y += font_body.size + 12

    out_path = os.path.join(IMAGE_DIR, out_name)
    img.save(out_path, "PNG")
    return out_path


def _wrap_text(text, max_chars):
    words, lines, cur = text.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 <= max_chars:
            cur = (cur + " " + w).strip()
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


# local copy to avoid import cycle
_TEAM_COLORS = {
    "arsenal": "#EF0107",
    "chelsea": "#034694",
    "liverpool": "#C8102E",
    "man city": "#6CABDD",
    "man city": "#6CABDD",
    "man united": "#DA291C",
    "tottenham": "#132257",
    "newcastle": "#241F20",
    "aston villa": "#670E36",
    "west ham": "#7A263A",
    "brighton": "#0057B8",
    "everton": "#003399",
    "crystal palace": "#1B458F",
    "wolves": "#FDB913",
    "nottingham": "#DD0000",
    "leicester": "#003090",
    "southampton": "#D71920",
}
