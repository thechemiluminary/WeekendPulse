# Cell 2 — Environment. Keep cell order; run all.
import subprocess, sys, os

def sh(cmd, **kw):
    return subprocess.run(cmd, shell=True, check=True, **kw)

print("Installing dependencies ...")
sh("apt-get -qq update >/dev/null && apt-get -qq install -y ffmpeg >/dev/null")
pip_base = [sys.executable, "-m", "pip", "-q", "install"]

# core: TTS runtime + torch extras
sh("-c", " ".join([*pip_base,
                  "chatterbox", "pyloudnorm", "torchaudio",
                  "faster-whisper", "torch",
                  "librosa", "soundfile", "pydub", "Pillow",
                  "ipython", "IPython"]))

print("ffmpeg:", sh("ffmpeg -version | head -n1", capture_output=True, text=True).stdout.strip())
print("Setup done.")