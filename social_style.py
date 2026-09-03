"""
WeekendPulse - Unicode styled text for social engagement posts.
Converts ASCII letters/digits to the Mathematical Alphanumeric Symbols block
(U+1D400-1D7FF) which Facebook renders as bold/italic/sans-serif styled text.
The AI marks words to emphasize with *asterisks*; we convert those runs.

Example: "NOBODY" -> "𝐍𝐎𝐁𝐎𝐃𝐘"  (bold serif)
          "MARK YOU CALENDAR" -> "𝗠𝗔𝗥𝗞 𝗬𝗢𝗨 𝗖𝗔𝗟𝗘𝗡𝗗𝗔𝗥" (bold sans)
          italic:  𝐼𝑡𝑎𝑙𝑖𝑐  -> 𝘐𝘵𝘢𝘭𝘪𝘤
"""

# Unicode Mathematical Alphanumeric Symbols bases (code point of A/a/0 per style)
_STYLES = {
    # (offset for uppercase A, lowercase a, digit 0)
    "bold":          (0x1D400, 0x1D41A, 0x1D7CE),  # 𝐀 𝐚 𝟎
    "italic":        (0x1D434, 0x1D44E, 0x1D7CE),  # 𝐴 𝑎 𝟎
    "bold_italic":   (0x1D468, 0x1D482, 0x1D7CE),  # 𝑨 𝒂 𝟎
    "sans":          (0x1D5A0, 0x1D5BA, 0x1D7E2),  # 𝖠 𝖺 𝟢
    "bold_sans":     (0x1D5D4, 0x1D5EE, 0x1D7F6),  # 𝗔 𝗮 𝟬
    "sans_italic":   (0x1D608, 0x1D622, 0x1D7E2),  # 𝘈 𝘢 𝟢
    "bold_sans_ital":(0x1D63C, 0x1D656, 0x1D7F6),  # 𝘼 𝙖 𝟬
    "mono":          (0x1D670, 0x1D68A, 0x1D7F6),  # 𝙰 𝚊 𝟶
    "script":        (0x1D49C, 0x1D4B6, 0x1D7CE),  # 𝒜 𝒶
    "fraktur":       (0x1D504, 0x1D51E, 0x1D7CE),  # 𝔄 𝔞
    "double":        (0x1D538, 0x1D552, 0x1D7D8),  # 𝔸 𝕒 𝟘
    "fullwidth":     (0xFF21, 0xFF41, 0xFF10),     # Ａ ａ ０
}

# Some letters have no code point in a given style (gaps in the Unicode block).
# We fall back to a different style or leave them. Best-effort is fine for
# social styling.
def _out_of_range(cp):
    return 0x1D400 <= cp <= 0x1D7FF


def _map_char(ch, upp, low, digit):
    if ch.isdigit() and digit is not None:
        return chr(digit + (ord(ch) - 0x30))
    if ch.isupper():
        return chr(upp + (ord(ch) - 0x41))
    if ch.islower():
        return chr(low + (ord(ch) - 0x61))
    return None


def style_text(text, style="bold_sans"):
    """
    Convert text to the given Unicode style. Characters without a mapping in
    that style are left unchanged (best-effort).
    """
    if style not in _STYLES:
        style = "bold_sans"
    upp, low, digit = _STYLES[style]
    out = []
    for ch in text:
        m = _map_char(ch, upp, low, digit)
        out.append(m if m is not None else ch)
    return "".join(out)


def apply_markup(text, style="bold_sans"):
    """
    Convert *emphasized* runs (surrounded by asterisks) to styled text.
    Everything not marked is left as-is. This is what the AI's post text uses.
    Example: "**NOBODY** can argue" -> "𝐍𝐎𝐁𝐎𝐃𝐘 can argue"
    """
    if not text:
        return text
    parts = []
    i = 0
    n = len(text)
    buf = []
    while i < n:
        if text[i] == "*":
            j = i + 1
            while j < n and text[j] == "*":
                j += 1
            star_count = j - i
            i = j
            if buf:
                parts.append("".join(buf))
                buf = []
            if star_count == 1:
                end = text.find("*", i)
                if end != -1:
                    parts.append(style_text(text[i:end], style))
                    i = end + 1
                else:
                    parts.append("*")
            else:
                # double/triple asterisk is treated as an emoji/bold-marker we
                # keep literal (avoid eating user emoji like **)
                parts.append("*" * star_count)
        else:
            buf.append(text[i])
            i += 1
    if buf:
        parts.append("".join(buf))
    return "".join(parts)


# Common emoji / flag shortcuts used heavily in these posts
ARROW = "\u2192"
EMOJI_ROCKET = "\U0001F680"
EMOJI_EYES = "\U0001F440"
EMOJI_FIRE = "\U0001F525"
EMOJI_CAL = "\U0001F4C5"
EMOJI_ALERT = "\U0001F6A8"
EMOJI_THINK = "\U0001F914"
EMOJI_HEART = "\u2764"
EMOJI_PRAY = "\U0001F64F"
