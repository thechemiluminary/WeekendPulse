#!/usr/bin/env python3
"""
align.py — Forced-alignment karaoke caption generator for ScaryTales Reels.

Inputs (same basename in a folder):
  <name>.txt   -> narration text is everything BEFORE the first "\n---\n"
                  (the rest is social caption metadata we ignore)
  <name>.wav   -> the narration audio (or .mp3)
Outputs:
  <name>.ass   -> karaoke (word-reveal) Advanced SubStation Alpha subtitles
                  burned with FFmpeg:  ffmpeg -i img -i audio -vf ass=<name>.ass

The on-screen words always match the WRITTEN narration, while timing comes
from faster-whisper's detected speech (forced alignment of the known text
onto the audio timeline). Word-by-word karaoke reveal.
"""

import argparse
import json
import os
import re
import sys

# ---------------------------------------------------------------- text utils

PUNCT = ".,!?;:\"'“”‘’()[]-–—…"


def normalize_word(w: str) -> str:
    """Lowercase, strip punctuation, collapse apostrophes/shy variation."""
    w = w.lower()
    w = re.sub(r"[\u2018\u2019\u0027]", "'", w)   # curly->straight apostrophe
    w = w.replace("’", "'")
    # strip everything except letters, digits, apostrophe, hyphen
    w = re.sub(r"[^a-z0-9'\-]+", "", w)
    return w


def tokenize(text: str):
    """Return list of words with approximate char positions (for punctuation
    recovery), splitting on whitespace but keeping punctuation attached."""
    # We split on whitespace; punctuation stays attached to tokens.
    # Char spans are only used to recover the ORIGINAL token substring.
    tokens = []
    for m in re.finditer(r"\S+", text):
        tokens.append({"raw": m.group(0), "start": m.start(), "end": m.end()})
    return tokens


def parse_events(raw):
    """raw: list of segment dicts from faster-whisper with .words.
    Returns list of {"word":..., "start":..., "end":...} flattened in order."""
    events = []
    for seg in raw:
        for w in seg.get("words", []):
            start = w.get("start")
            end = w.get("end")
            if start is None:
                continue
            events.append({"word": normalize_word(w.get("word", "")),
                           "start": float(start), "end": float(end)})
    return events


# ---------------------------------------------------------- alignment core

def align(narration_events, whisper_events):
    """Greedy left-to-right alignment.

    narration_events : ordered written words (normalized) we want timings for
    whisper_events    : ordered detected (normalized) words with timings

    Returns: list of dicts for the WRITTEN words:
        {"word": original written display token, "start":.., "end":..}
    A word that could not be matched falls back to the time of its nearest
    matched neighbour (clamped) so the timeline never gaps.
    """
    # Build sequence of whisper normalized words to allow skipping noise
    n = len(narration_events)
    # We'll walk whisper index forward, matching as many narration words as
    # possible. For unmatched whisper tokens we just skip them.
    result = [None] * n
    wi = 0
    wn_total = len(whisper_events)

    # First pass: match each narration word to a whisper word timing.
    # whisper word i corresponds to narration word i in a 1:1 clean read, but
    # whisper may drop/reorder; use a moving window search for a match.
    i = 0
    while i < n:
        target = narration_events[i]["norm"]
        found = None
        # search forward in whisper events by up to a few tokens
        search_limit = min(wn_total, wi + 6)
        for j in range(wi, search_limit):
            if whisper_events[j]["word"] == target:
                found = j
                break
        if found is not None:
            result[i] = (whisper_events[found]["start"],
                         whisper_events[found]["end"])
            wi = found + 1
            i += 1
        else:
            # narration word not found -> mark missing; keep wi, advance i
            result[i] = None
            i += 1

    # Second pass: fill missing timings by interpolation between known anchors.
    known_idx = [k for k, v in enumerate(result) if v is not None]
    if not known_idx:
        # nothing matched at all -> give each word a flat share of audio 0..X
        raise RuntimeError("No words matched between narration and audio "
                           "- check the narration text matches the audio.")
    # For each missing index between known anchors, linear interpolate.
    for i in range(n):
        if result[i] is not None:
            continue
        # find prev known
        prevs = [k for k in known_idx if k < i]
        nexts = [k for k in known_idx if k > i]
        if prevs and nexts:
            p = prevs[-1]
            nx = nexts[0]
            frac = (i - p) / (nx - p)
            s = result[p][0] + (result[nx][0] - result[p][0]) * frac
            e = result[p][1] + (result[nx][1] - result[p][1]) * frac
        elif prevs:
            p = prevs[-1]
            dur = (result[p][1] - result[p][0]) or 0.15
            s = result[p][1]
            e = s + dur
        elif nexts:
            nx = nexts[0]
            dur = (result[nx][1] - result[nx][0]) or 0.15
            e = result[nx][0]
            s = e - dur
        else:
            continue
        result[i] = (s, e)

    # Build output, one entry per written display token.
    out = []
    for i, ev in enumerate(narration_events):
        s, e = result[i]
        out.append({"word": ev["raw"], "start": round(s, 3), "end": round(e, 3)})
    return out


# ---------------------------------------------------------------- ASS output

def timestamp_ass(t):
    """ASS time format H:MM:SS.cc (centiseconds)."""
    t = max(0.0, t)
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = int(t % 60)
    cs = int(round((t - int(t)) * 100))
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def ass_header(fontsize=70, fontname="Chiller", alignment=5,
               outline=6, shadow=3, outline_colour="&H00222222",
               back_colour="&H80000000"):
    """Build the [Script Info] + [V4+ Styles] block.

    Default alignment=5 -> the caption block is centred both horizontally and
    vertically (middle of the frame), NOT pinned to the bottom.
    """
    return (
        f"[Script Info]\n"
        f"ScriptType: v4.00+\n"
        f"PlayResX: 1080\n"
        f"PlayResY: 1920\n"
        f"WrapStyle: 0\n"
        f"ScaledBorderAndShadow: yes\n"
        f"\n"
        f"[V4+ Styles]\n"
        f"Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Sub,{fontname},{fontsize},&H00FFFFFF,&H00555555,"
        f"{outline_colour},{back_colour},-1,0,0,0,100,100,0,0,1,"
        f"{outline},{shadow},{alignment},60,60,0,1\n"
        f"\n"
        f"[Events]\n"
        f"Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )


# Punctuation that is always stripped from inside a merged caption and only
# re-appended (in order) at the very end of the caption. Handles the standard
# set plus curly quotes / apostrophes / hyphens / dashes.
STRIP_RE = re.compile(r"[.,;:!?\"'\u2018\u2019\u201c\u201d()\[\]\u2013\u2014\-]+")


def build_ass(aligned, width=1080, height=1920, max_chars_per_line=30,
              fontsize=64, fontname="Chiller", min_hold=0.45):
    """aligned: list of {word, start, end}. Produce vertically-centred subtitle
    events (NOT backslash-k karaoke, which libass in ffmpeg renders as literal
    text).

    Merging rules:
      * words are grouped into readable chunks so a chunk stays visible
        >= min_hold seconds (fixes fast-speech single-word flicker)
      * a group NEVER crosses a sentence boundary (a word ending in .?! ),
        so the end of one sentence never merges with the start of another
      * groups are emitted with no time overlap (each has start >= prev end),
        even when whisper's own word timings overlap
      * NO punctuation ever appears inside a merged caption: every , ; : ! ?
        " ' ( ) - ... is stripped from the words, and only the punctuation that
        trailed the FINAL word of the group is re-appended at the very end of
        the caption line.
    """
    events = []

    # ---- grouping ----
    groups = []
    cur_words = []
    def close():
        nonlocal cur_words
        if cur_words:
            groups.append(cur_words)
            cur_words = []

    for item in aligned:
        if not cur_words:
            cur_words = [item]
        else:
            cur_words.append(item)
            span = item["end"] - cur_words[0]["start"]
            if span >= min_hold:
                close()
        # Always break the group if this word ends a sentence, so the next
        # sentence starts its own caption.
        if item["word"].rstrip().endswith((".", "!", "?")):
            close()
    close()

    # ---- emit with a guaranteed non-overlapping timeline ----
    prev_end = None
    for words in groups:
        start = words[0]["start"]
        end = max(w["end"] for w in words)

        # No-overlap guarantee: this caption may not begin before the previous
        # one ended (whisper word timings can overlap for fast speech).
        if prev_end is not None and start < prev_end:
            start = prev_end
        if end <= start:
            end = start + 0.3
        # Ensure a minimum visible window even for a lone long tail.
        if end - start < 0.3:
            end = start + 0.3
        prev_end = end

        # Strip ALL punctuation from every word. The only punctuation kept is
        # whatever trailed the FINAL word of the group, appended at the very
        # end of the caption — so the caption never carries , ; . ! ? mid-text.
        last = words[-1]["word"]
        last_trailing = "".join(
            ch for ch in last
            if ch in ".,;:!?\"'\u2018\u2019\u201c\u201d()[]\u2013\u2014-"
        )
        clean_words = [STRIP_RE.sub("", w["word"]) for w in words]
        clean_words = [c for c in clean_words if c]

        # Wrap long groups into multiple \N-separated lines.
        text_parts = []
        line_chars = 0
        line = []
        for cw in clean_words:
            wlen = len(cw) + 1  # +1 for a space between words
            if line and line_chars + wlen > max_chars_per_line:
                text_parts.append(" ".join(line))
                line = [cw]
                line_chars = len(cw)
            else:
                line.append(cw)
                line_chars += wlen
        if line:
            text_parts.append(" ".join(line))
        caption = "\\N".join(text_parts)
        # Append the final word's trailing punctuation at the very end.
        if last_trailing:
            caption = caption + last_trailing

        events.append(
            f"Dialogue: 0,{timestamp_ass(start)},{timestamp_ass(end)},"
            f"Sub,,0,0,0,,{caption}"
        )

    return ass_header(fontsize=fontsize, fontname=fontname) + "\n".join(events) + "\n"


# -------------------------------------------------------------------- main

def asr_words(audio_path):
    """Run faster-whisper, return flattened word events + raw segments."""
    from faster_whisper import WhisperModel
    model = WhisperModel("base", device="cpu", compute_type="int8")
    segments, _info = model.transcribe(
        audio_path, word_timestamps=True, language="en",
        initial_prompt="Horror story narration in English."
    )
    raw = []
    for seg in segments:
        words = seg.words or []
        raw.append({"text": seg.text, "start": seg.start, "end": seg.end,
                    "words": [
                        {"word": w.word, "start": w.start, "end": w.end}
                        for w in words
                    ]})
    return parse_events(raw)


def get_narration_text(txt_path):
    """Everything before the first '---' line in the story file."""
    with open(txt_path, encoding="utf-8") as f:
        content = f.read()
    part = content.split("\n---", 1)[0].strip()
    if not part:
        # fall back: whole file
        part = content.strip()
    return part


def main():
    ap = argparse.ArgumentParser(description="Forced-align captions to audio")
    ap.add_argument("name", help="basename (babysitter) - looks for \
        <name>.txt, <name>.wav|.mp3 in CWD")
    ap.add_argument("--fontsize", type=int, default=64)
    ap.add_argument("--fontname", default="Chiller",
                    help="font family for the captions (e.g. Chiller, Arial)")
    ap.add_argument("--maxchars", type=int, default=30,
                    help="max chars per caption line")
    ap.add_argument("--min-hold", type=float, default=0.45,
                    help="seconds each caption stays visible; larger = more "
                         "words merged into readable chunks (default 0.45)")
    args = ap.parse_args()

    base = args.name
    here = os.path.dirname(os.path.abspath(__file__))
    txt = os.path.join(here, base + ".txt")
    audio = None
    for ext in (".wav", ".mp3", ".m4a", ".flac"):
        p = os.path.join(here, base + ext)
        if os.path.exists(p):
            audio = p
            break
    if audio is None:
        print("ERROR: no audio (<name>.wav/.mp3/.m4a/.flac) found next to the .txt")
        sys.exit(1)

    narration = get_narration_text(txt)
    narration_tokens = tokenize(narration)
    narration_events = [
        {"raw": t["raw"], "norm": normalize_word(t["raw"])}
        for t in narration_tokens
    ]

    print(f"Audio        : {audio}")
    print(f"Narration    : {len(narration_events)} words")
    print(f"Running Whisper (base) on CPU...")

    whisper_events = asr_words(audio)
    print(f"Whisper      : {len(whisper_events)} detected words")

    aligned = align(narration_events, whisper_events)

    ass_path = os.path.join(here, base + ".ass")
    content = build_ass(aligned, fontsize=args.fontsize,
                        fontname=args.fontname,
                        max_chars_per_line=args.maxchars,
                        min_hold=args.min_hold)
    with open(ass_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"Wrote        : {ass_path}")

    # also dump a JSON for debugging
    for a in aligned:
        a["word"] = a.pop("word")
    with open(os.path.join(here, base + "_timings.json"), "w", encoding="utf-8") as f:
        json.dump(aligned, f, indent=1)

    # print first few words to sanity check
    print("\nFirst 8 timed words:")
    for a in aligned[:8]:
        print(f"  {a['word']!r:22s} {a['start']:.3f} -> {a['end']:.3f}")
    print(json.dumps({"total_words": len(aligned), "duration_end": aligned[-1]["end"]}, indent=1))


if __name__ == "__main__":
    main()
