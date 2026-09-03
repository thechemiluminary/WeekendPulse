"""WeekendPulse Reel renderer.

Turns one approved news story (from reels_batch.txt) into a short ~16s 9:16
Facebook Reel: Ken Burns pan/zoom over the article's real photo, Chatterbox-Nano
TTS narration of the AI's reel_blurb (random female voice, precise emotion),
whisper-captions, an animated title card, and a crossfade into a fixed
outro.mp4. Music (from GitHub WeekendPulse/music/) starts at position 0 and is
cut at narration end (loopable head, no tail-cut).

Runs inline in the notebook (no web server). Reuses the proven ScaryTales
audio-enhance + caption + duck-mix pipeline via enhance.py / align.py.
"""
import json
import random
import re
import subprocess
import time
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

import torch
import torchaudio

from enhance import enhance_audio

BASE = Path("/content/weekendpulse_reels")
VOICES_DIR = BASE / "voices"
OUTPUT_DIR = BASE / "output"
ASSET_DIR = BASE / "assets"
for _d in (VOICES_DIR, OUTPUT_DIR, ASSET_DIR):
    _d.mkdir(parents=True, exist_ok=True)

MAX_CHARS = 450
PAUSE_SECONDS = 0.4
TEMPERATURE = 0.8
REPETITION_PENALTY = 1.4

OUT_W = 1080
OUT_H = 1920
FPS = 30

ACCENT = "#FF6B00"       # vibrant orange
WHITE = "#FFFFFF"
OUTRO_FILENAME = "outro.mp4"
ENHANCE = True           # post-process narration (LavaSR/RNNoise/mastering)

MUSIC_REPO = "thechemiluminary/WeekendPulse"
MUSIC_GITHUB_API = "https://api.github.com/repos"
MUSIC_RAW = "https://raw.githubusercontent.com"

MODEL = None

# 10-voice female pool (random identity per reel). Each voice is a SUBFOLDER
# under voices/ (from the voice-zero voices-emotion set) holding one clip per
# emotion (excited.flac, surprised.flac, neutral.flac, ...). Emotion variant is
# chosen per the AI's reel_emotion; falls back to that voice's neutral.flac.
FEMALE_BASE = [
    "kristin_hughes", "jodi_krangle", "karen_savage",
    "emily_cripps", "cori_samuel", "mil_nicholson",
    "amy_koenig", "alana_jordan", "emily_anderson", "anna_simon",
]

EMOTIONS = {"neutral", "excited", "surprised"}


# ─────────────────────────────────────────────────────────────────── TTS
def _sanitize_for_tts(text):
    text = (text or "").replace("\r\n", "\n").strip()
    text = re.sub(r"[\u201c\u201d]", '"', text)
    text = re.sub(r"[\u2018\u2019]", "'", text)
    text = text.replace("\\n", " ")
    text = re.sub(r"\[\s*pause\s*\]", ".", text, flags=re.IGNORECASE)
    text = re.sub(r"[ \t]{2,}", " ", text).strip()
    if text and text[-1] not in ".!?":
        text += "."
    return text


def _chunk(text, max_chars=MAX_CHARS):
    sents = re.split(r"(?<=[.!?])\s+", text.strip())
    chunks, cur = [], ""
    for s in sents:
        if cur and len(cur) + len(s) + 1 > max_chars:
            chunks.append(cur)
            cur = s
        else:
            cur = (cur + " " + s) if cur else s
    if cur:
        chunks.append(cur)
    return chunks or [text]


def _apply_numpy2_patches(model):
    import math
    import types

    import pyloudnorm as ln
    import numpy as np

    def _safe_norm(self, wav, sr, target_lufs=-27):
        try:
            meter = ln.Meter(sr)
            loud = meter.integrated_loudness(wav)
            g = 10.0 ** ((target_lufs - loud) / 20.0)
            if math.isfinite(g) and g > 0.0:
                wav = wav * g
        except Exception:
            pass
        return np.asarray(wav, dtype="float32")

    model.norm_loudness = types.MethodType(_safe_norm, model)

    tok = getattr(getattr(model, "s3gen", None), "tokenizer", None)
    if tok is not None and hasattr(tok, "forward"):
        orig = tok.forward

        def _fwd(wavs, *a, **k):
            if isinstance(wavs, (list, tuple)):
                wavs = [__import__("numpy").asarray(w, dtype="float32") for w in wavs]
            return orig(wavs, *a, **k)
        tok.forward = _fwd


def get_model():
    global MODEL
    if MODEL is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"
        print("Loading Chatterbox-Nano on", device, "... (first run ~2.9 GB)")
        from chatterbox.tts_turbo import ChatterboxTurboTTS
        MODEL = ChatterboxTurboTTS.from_pretrained(device=device, nano=True)
        _apply_numpy2_patches(MODEL)
        print("Model ready.")
    return MODEL


def _tts_to_wav(text, voice_file, say=print):
    text = _sanitize_for_tts(text)
    chunks = _chunk(text)
    model = get_model()
    sr = model.sr
    parts = []
    for i, c in enumerate(chunks, 1):
        say(f"  TTS {i}/{len(chunks)}")
        wav = model.generate(
            c,
            audio_prompt_path=str(VOICES_DIR / voice_file),
            temperature=TEMPERATURE,
            repetition_penalty=REPETITION_PENALTY,
        )
        parts.append(wav.squeeze(0))
    if len(parts) > 1:
        silence = torch.zeros(int(sr * PAUSE_SECONDS), dtype=parts[0].dtype)
        a = parts[0]
        for p in parts[1:]:
            a = torch.cat([a, silence, p], dim=0)
    else:
        a = parts[0]
    path = OUTPUT_DIR / f"narr_{uuid.uuid4().hex[:8]}.wav"
    torchaudio.save(str(path), a.unsqueeze(0), sr)
    return path, a.shape[-1] / sr


# ──────────────────────────────────────────────────────── voice selection
def _resolve_voice(emotion):
    """Random female voice folder; try the exact emotion clip, else that voice's
    neutral clip, else any female voice's neutral clip. Never pins to one voice.
    Returns (voice_rel, emotion_used) where voice_rel is 'voice/emotion.flac'
    resolved against VOICES_DIR."""
    emotion = emotion if emotion in EMOTIONS else "neutral"

    def path_for(v, em):
        return VOICES_DIR / v / f"{em}.flac"

    picks = FEMALE_BASE[:]
    random.shuffle(picks)

    if emotion != "neutral":
        for v in picks:
            if path_for(v, emotion).exists():
                return f"{v}/{emotion}.flac", emotion
    for v in picks:
        if path_for(v, "neutral").exists():
            return f"{v}/neutral.flac", "neutral"
    return f"{FEMALE_BASE[0]}/neutral.flac", "neutral"


# ─────────────────────────────────────────────────────────────────── music
def _download_url(name):
    return f"{MUSIC_RAW}/{MUSIC_REPO}/main/music/{urllib.parse.quote(name)}"


def _github_list_tracks():
    req = urllib.request.Request(
        f"{MUSIC_GITHUB_API}/{MUSIC_REPO}/contents/music",
        headers={"Accept": "application/vnd.github.v3+json", "User-Agent": "wp"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        items = json.loads(r.read())
    return [it["name"] for it in items if it["type"] == "file"
            and it["name"].lower().endswith((".mp3", ".wav"))]


def _audio_dur(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(path)],
        capture_output=True, text=True).stdout.strip()
    try:
        return float(out)
    except Exception:
        return 12.0


def _mix_mastered(voice_wav, say=print):
    """Random WeekendPulse/music/ track, started at POSITION 0 and cut at the
    narration end (no tail-cut). Auto-ducked under the voice."""
    try:
        tracks = _github_list_tracks()
    except Exception as e:
        say(f"  Music list failed ({e}) - voice only")
        return voice_wav, None
    if not tracks:
        say("  No music tracks - voice only")
        return voice_wav, None
    name = random.choice(tracks)
    say(f"  Music: {name}")
    mpath = OUTPUT_DIR / f"mus_{uuid.uuid4().hex[:8]}"
    try:
        urllib.request.urlretrieve(_download_url(name), mpath)
    except Exception as e:
        say(f"  Music DL failed ({e}) - voice only")
        mpath.unlink(missing_ok=True)
        return voice_wav, None

    L = _audio_dur(voice_wav)
    fc = (
        f"[0:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,"
        f"volume=1.0dB,asplit=2[v_main][v_sc];"
        f"[1:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,"
        f"volume=-17dB,equalizer=f=2000:t=q:w=1:g=-3,"
        f"afade=t=in:st=0:d=0.4[m_music];"
        f"[m_music][v_sc]sidechaincompress=threshold=0.1:ratio=4:"
        f"attack=0.15:release=0.4[mduck];"
        f"[mduck]afade=t=out:st={max(0.0, L-1.0):.3f}:d=1.0[mf];"
        f"[v_main][mf]amix=inputs=2:duration=first:normalize=0,"
        f"alimiter=limit=0.95[out]"
    )
    master = OUTPUT_DIR / f"mix_{uuid.uuid4().hex[:8]}.wav"
    cmd = ["ffmpeg", "-y", "-i", str(voice_wav),
           "-ss", "0.000", "-t", f"{L:.3f}", "-i", str(mpath),
           "-filter_complex", fc, "-map", "[out]",
           "-ar", "48000", "-c:a", "pcm_s24le", str(master)]
    try:
        subprocess.run(cmd, capture_output=True, check=True)
    except subprocess.CalledProcessError:
        say("  Mix failed - voice only")
        master = voice_wav
    finally:
        mpath.unlink(missing_ok=True)
    return master, name


# ─────────────────────────────────────────────────────────── image + burn
def _download_image(url, dest):
    try:
        urllib.request.urlretrieve(url, dest)
        return dest.exists() and dest.stat().st_size > 5000
    except Exception:
        return False


def _find_font(px):
    import os
    from PIL import ImageFont
    # Prefer the brand "Anton" font (all-caps titles). It may live in the repo
    # data/fonts or be dropped into the Colab working dir.
    candidates = [
        "/content/weekendpulse_reels/Anton-Regular.ttf",
        "/content/Anton-Regular.ttf",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "Anton-Regular.ttf"),
        "Anton-Regular.ttf",
    ]
    for cand in candidates:
        if os.path.exists(cand):
            try:
                return ImageFont.truetype(cand, px)
            except Exception:
                pass
    # Fallback: DejaVuSans bold
    for cand in ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]:
        if os.path.exists(cand):
            try:
                return ImageFont.truetype(cand, px)
            except Exception:
                pass
    return ImageFont.load_default()


def _wrap(title, font, maxw):
    words = (title or "").split()
    lines, cur = [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if (not cur) or font.getlength(t) <= maxw:
            cur = t
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def _make_title_card(title, out_img):
    """Orange accent bar + white title text on a dark card (1080x1920)."""
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (OUT_W, OUT_H), (20, 20, 20))
    d = ImageDraw.Draw(img)
    d.rectangle([0, OUT_H - 600, OUT_W, OUT_H - 180], fill="#FF6B00")
    font = _find_font(76)
    lines = _wrap((title or "WeekendPulse").upper(), font, OUT_W - 160)
    text = "\n".join(lines[:3])
    d.multiline_text(
        (OUT_W // 2, OUT_H - 390), text,
        font=font, fill=(255, 255, 255), anchor="mm",
        align="center", spacing=12,
    )
    img.save(str(out_img))
    return out_img


def _make_fallback_image(title, out_img):
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (OUT_W, OUT_H), (20, 20, 20))
    d = ImageDraw.Draw(img)
    d.rectangle([0, OUT_H - 600, OUT_W, OUT_H - 180], fill="#FF6B00")
    font = _find_font(96)
    lines = _wrap("Premier League News", font, OUT_W - 160)
    d.multiline_text(
        (OUT_W // 2, OUT_H - 390), "\n".join(lines[:2]),
        font=font, fill=(255, 255, 255), anchor="mm", align="center", spacing=12)
    img.save(str(out_img))
    return out_img


def _align_captions(audio_path, narration, say=print):
    from align import asr_words, align, build_ass, tokenize, normalize_word
    tokens = tokenize(narration)
    narr_events = [{"raw": t["raw"], "norm": normalize_word(t["raw"])} for t in tokens]
    whisper = asr_words(str(audio_path))
    aligned = align(narr_events, whisper)
    for a in aligned:
        a["word"] = a.pop("word")
    content = build_ass(aligned, width=OUT_W, height=OUT_H,
                        fontsize=90, fontname="DejaVuSans",
                        max_chars_per_line=30, min_hold=0.45)
    ass_path = OUTPUT_DIR / f"cap_{uuid.uuid4().hex[:8]}.ass"
    ass_path.write_text(content, encoding="utf-8")
    return ass_path


def _burn_body(image_path, audio_path, ass_path, out_path):
    """Ken Burns body clip: wide image scaled to cover 9:16 (crops corners),
    slow horizontal pan + subtle zoom over the audio duration."""
    L = _audio_dur(audio_path)
    n = int(L * FPS)
    vf = (
        f"scale={OUT_W * 2}:{OUT_H * 2}:force_original_aspect_ratio=increase,"
        f"crop={OUT_W * 2}:{OUT_H * 2},"
        f"zoompan=z='1.0+0.08*on/{n}':"
        f"x='(iw-iw/zoom)/2 + 0.18*iw*on/{n}':y='(ih-ih/zoom)/2':"
        f"d={n}:s={OUT_W}x{OUT_H}:fps={FPS},format=yuv420p,ass={ass_path}"
    )
    cmd = ["ffmpeg", "-y", "-loop", "1", "-i", str(image_path),
           "-i", str(audio_path), "-vf", vf,
           "-c:v", "libx264", "-tune", "stillimage", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "192k", "-shortest",
           "-movflags", "+faststart", str(out_path)]
    subprocess.run(cmd, capture_output=True, check=True)
    return out_path


def _crossfade_title(body_path, title_img, title_dur, out_path):
    """Overlay the title card with a fade-in over the start of the body."""
    vf = ("[1:v]format=rgba,fade=t=in:st=0:d=0.5:alpha=1[t];"
          "[0:v][t]overlay=0:0:enable='between(t,0,{d})'[v]"
          ).format(d=title_dur)
    cmd = ["ffmpeg", "-y", "-i", str(body_path),
           "-loop", "1", "-i", str(title_img),
           "-filter_complex", vf, "-map", "[v]", "-map", "0:a",
           "-c:v", "libx264", "-pix_fmt", "yuv420p",
           "-c:a", "copy", "-movflags", "+faststart", str(out_path)]
    subprocess.run(cmd, capture_output=True, check=True)
    return out_path


def _concat_with_outro(body_path, outro_path, out_path, xfade=0.4):
    """Crossfade the body clip into the fixed outro.mp4 (audio fades too)."""
    body_dur = _audio_dur(body_path)
    # xfade between body and outro videos; concat audio with crossfade
    vf = ("[0:v][1:v]xfade=transition=fade:duration={x}:offset={off}[v]"
          ).format(x=xfade, off=max(0.0, body_dur - xfade))
    # audio: body audio then outro audio, crossfading 0.x
    af = ("[0:a][1:a]acrossfade=d={x}[a]").format(x=xfade)
    cmd = ["ffmpeg", "-y", "-i", str(body_path), "-i", str(outro_path),
           "-filter_complex", f"{vf};{af}",
           "-map", "[v]", "-map", "[a]",
           "-c:v", "libx264", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "192k",
           "-movflags", "+faststart", str(out_path)]
    subprocess.run(cmd, capture_output=True, check=True)
    return out_path


def render_reel(entry, say=print):
    """entry: dict from reels_batch.txt. Returns (out_path, summary)."""
    slug = (entry.get("slug") or "reel")[:40]
    title = entry.get("title", "") or ""
    blurb = entry.get("reel_blurb", "") or ""
    emotion = entry.get("reel_emotion", "neutral") or "neutral"
    image_url = entry.get("image_url", "") or ""

    t0 = time.time()
    say(f"\n=== Rendering '{slug}' ===")

    # 1. image (real article photo, else branded fallback card)
    image_path = None
    if image_url:
        dest = OUTPUT_DIR / f"img_{slug}_{uuid.uuid4().hex[:6]}.jpg"
        if _download_image(image_url, dest):
            image_path = dest
    if image_path is None:
        image_path = OUTPUT_DIR / f"fal_{uuid.uuid4().hex[:6]}.jpg"
        _make_fallback_image(title, image_path)
        say("  (no usable article image - using fallback card)")

    # 2. voice (random female + precise emotion)
    voice_file, emotion_used = _resolve_voice(emotion)
    say(f"  voice={voice_file} emotion={emotion_used}")

    # 3. TTS narration
    narr_wav, dur = _tts_to_wav(blurb, voice_file, say)
    say(f"  narration {dur:.1f}s")

    # 4. audio enhancement (LavaSR + RNNoise + mastering; skippable)
    if ENHANCE:
        try:
            enh = OUTPUT_DIR / f"enh_{uuid.uuid4().hex[:8]}.wav"
            enh_in, _ = enhance_audio(narr_wav, enh)
            say(f"  enhanced ({Path(enh_in).stat().st_size//1024} KiB)")
            narr_wav = Path(enh_in)
        except Exception as _e:
            say(f"  enhance skipped ({_e})")

    # 5. mix music under narration (start at 0)
    master, music = _mix_mastered(narr_wav, say)
    if music:
        say(f"  mixed with {music}")

    # 5. captions
    ass = _align_captions(master, blurb, say)

    # 6. burn Ken Burns body
    body = OUTPUT_DIR / f"body_{slug}_{uuid.uuid4().hex[:6]}.mp4"
    _burn_body(image_path, master, ass, body)

    # 7. title card overlay (fade-in) over body start
    title_dur = 2.4 if dur >= 2.8 else max(0, dur - 0.4)
    titled = body
    if title_dur > 0.4:
        card = OUTPUT_DIR / f"card_{slug}_{uuid.uuid4().hex[:6]}.png"
        _make_title_card(title, card)
        titled = OUTPUT_DIR / f"titled_{slug}_{uuid.uuid4().hex[:6]}.mp4"
        _crossfade_title(body, card, title_dur, titled)
        card.unlink(missing_ok=True)

    # 8. crossfade into fixed outro
    out = OUTPUT_DIR / f"{slug}.mp4"
    outro_path = ASSET_DIR / OUTRO_FILENAME
    if outro_path.exists():
        _concat_with_outro(titled, outro_path, out)
    else:
        subprocess.run(["ffmpeg", "-y", "-i", str(titled),
                        "-c", "copy", "-movflags", "+faststart", str(out)],
                       capture_output=True, check=True)

    # cleanup temps (keep final mp4)
    for p in (body, titled):
        if p != out and p.exists():
            p.unlink(missing_ok=True)
    narr_wav.unlink(missing_ok=True)
    if master != narr_wav:
        master.unlink(missing_ok=True)

    tl = _audio_dur(out)
    say(f"[{slug}] DONE {tl:.1f}s in {time.time() - t0:.1f}s")
    voice_name = voice_file.rsplit("/", 1)[0] if voice_file else ""
    summary = {"slug": slug, "title": title, "emotion": emotion_used,
               "voice": voice_name, "music": music, "duration_s": round(tl, 1)}
    return out, summary


def render_all(entries, say=print):
    results = []
    for e in entries:
        try:
            path, summary = render_reel(e, say)
            results.append(summary)
        except Exception:
            import traceback as _tb
            say("  ERROR rendering %s:\n%s" % (e.get("slug", "?"), _tb.format_exc()))
    return results