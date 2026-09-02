"""Audio post-processing pipeline for Chatterbox Nano output.

Stages (each independently skippable on failure):
  1. LavaSR   — speech enhancement (warmth, bandwidth, clarity)
  2. RNNoise  — artifact removal (metallic hiss, clicks)
  3. auto-editor — trim dead silence and stutters
  4. FFmpeg   — mastering (EQ, compression, LUFS normalization)
"""

import os
import shutil
import subprocess
import time
from pathlib import Path


_LAVA_MODEL = None
_LAVA_LOCK = None


def _get_lava():
    """Lazy singleton for LavaSR model (~50MB, loads once)."""
    global _LAVA_MODEL, _LAVA_LOCK
    if _LAVA_LOCK is None:
        import threading
        _LAVA_LOCK = threading.Lock()
    with _LAVA_LOCK:
        if _LAVA_MODEL is None:
            try:
                from LavaSR.model import LavaEnhance2
                _LAVA_MODEL = LavaEnhance2("YatharthS/LavaSR", "cpu")
                print("[enhance] LavaSR model loaded")
            except Exception as e:
                print(f"[enhance] LavaSR load failed: {e}")
                _LAVA_MODEL = False  # sentinel: do not retry
    return _LAVA_MODEL if _LAVA_MODEL is not False else None


# ---------------------------------------------------------------------------
# Stage 1: LavaSR speech enhancement
# ---------------------------------------------------------------------------
def _stage_lava(src, dst):
    lava = _get_lava()
    if lava is None:
        return False
    import soundfile as sf
    audio, _sr = lava.load_audio(str(src))
    out = lava.enhance(audio, denoise=False, batch=False).cpu().numpy().squeeze()
    sf.write(str(dst), out, 48000)
    return True


# ---------------------------------------------------------------------------
# Stage 2: RNNoise artifact removal
# ---------------------------------------------------------------------------
def _stage_rnnoise(src, dst):
    tmp48 = str(dst) + "._48k.wav"
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(src),
             "-ar", "48000", "-ac", "1", "-sample_fmt", "s16", tmp48],
            capture_output=True, check=True,
        )
    except subprocess.CalledProcessError:
        return False

    denoised = str(dst) + "._dn.wav"
    ran = False
    # try CLI first
    try:
        subprocess.run(["denoise", tmp48, denoised], capture_output=True, check=True)
        ran = True
    except FileNotFoundError:
        pass
    # fallback: Python API
    if not ran:
        try:
            from pyrnnoise import RNNoise
            denoiser = RNNoise(sample_rate=48000)
            for _ in denoiser.denoise_wav(tmp48, denoised):
                pass
            ran = True
        except Exception:
            pass
    # cleanup temp inputs
    for f in [tmp48]:
        if os.path.exists(f):
            os.remove(f)
    if not ran or not os.path.exists(denoised):
        return False

    # restore sample rate
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", denoised, "-ar", "24000", str(dst)],
            capture_output=True, check=True,
        )
    except subprocess.CalledProcessError:
        shutil.copy2(denoised, str(dst))
    if os.path.exists(denoised):
        os.remove(denoised)
    return True


# ---------------------------------------------------------------------------
# Stage 3: auto-editor silence / artifact trimming
# ---------------------------------------------------------------------------
def _stage_autoeditor(src, dst):
    try:
        subprocess.run(
            ["auto-editor", str(src), "--output", str(dst),
             "--threshold", "0.04", "--margin", "0.2"],
            capture_output=True, check=True,
        )
        return dst.exists() and dst.stat().st_size > 0
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


# ---------------------------------------------------------------------------
# Stage 4: FFmpeg mastering (EQ, compression, LUFS)
# ---------------------------------------------------------------------------
def _stage_master(src, dst):
    # probe source sample rate
    try:
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "a:0",
             "-show_entries", "stream=sample_rate", "-of", "csv=p=0",
             str(src)],
            capture_output=True, text=True, check=True,
        )
        sr = int(probe.stdout.strip()) or 24000
    except Exception:
        sr = 24000

    chain = ",".join([
        "highpass=f=80",
        "equalizer=f=3000:t=q:w=1:g=-2",
        "equalizer=f=150:t=q:w=1:g=1",
        "compand=attacks=0.3:decays=0.8:points=-80/-80|-20/-14|0/-7:gain=0",
        "loudnorm=I=-19:TP=-1.5:LRA=11",
    ])
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(src), "-af", chain,
             "-ar", str(sr), str(dst)],
            capture_output=True, check=True,
        )
        return True
    except subprocess.CalledProcessError:
        return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
STAGES = [
    ("lava",       _stage_lava),
    ("rnnoise",    _stage_rnnoise),
    ("autoeditor", _stage_autoeditor),
    ("master",     _stage_master),
]


def enhance_audio(input_path, output_path=None, enable=True):
    """Run the full post-processing pipeline.

    Args:
        input_path:  Path to input WAV.
        output_path: Path to output WAV (default: overwrite input).
        enable:      False to skip all processing.

    Returns:
        (output_path_str, stats_dict)
    """
    if not enable:
        return str(input_path), {}

    input_path = Path(input_path)
    if output_path is None:
        output_path = input_path
    else:
        output_path = Path(output_path)

    stats = {}
    current = input_path

    for name, fn in STAGES:
        tmp = input_path.parent / f".tmp_{name}_{input_path.name}"
        try:
            t0 = time.time()
            ok = fn(current, tmp)
            elapsed = f"{time.time() - t0:.1f}s"
            if ok and tmp.exists() and tmp.stat().st_size > 0:
                current = tmp
                stats[name] = elapsed
                print(f"  [enhance] {name}: {elapsed}")
            else:
                print(f"  [enhance] {name}: skipped")
        except Exception as e:
            print(f"  [enhance] {name}: failed ({e})")

    # move final result to output_path
    if current != output_path:
        shutil.move(str(current), str(output_path))

    # cleanup remaining temp files
    for name, _ in STAGES:
        tmp = input_path.parent / f".tmp_{name}_{input_path.name}"
        if tmp.exists() and tmp != output_path:
            try:
                tmp.unlink()
            except OSError:
                pass

    return str(output_path), stats
