# WeekendPulse Reels — Batch Renderer

Turn today's **reel-worthy** news posts (from `reels_batch.txt`) into short,
~16s vertical Facebook Reels. One reel per story.

## Pipeline (per reel)
1. Ken Burns pan/zoom over the article's **real photo** (branded fallback card if none).
2. **Chatterbox-Nano** TTS narration of the AI's `reel_blurb` — a **random
   female voice**, precise emotion (`neutral` / `excited` / `surprised`).
3. Whisper-aligned **captions** burned in.
4. A **title card** (vibrant orange + white) fades in over the body.
5. Music from the repo `music/` folder starts at position 0 and is **cut at
   narration end** (loopable head, auto-ducked under the voice).
6. A **~0.4s crossfade** into the fixed 4s `outro.mp4`.

## Voices
- **10 female voices** are auto-downloaded from the public
  `OwenTyme/voice-zero` `voices-emotion/` pool (each is a folder of emotion
  clips, e.g. `emily_cripps/excited.flac`).
- Every reel uses a **random female voice**. The AI's `reel_emotion`
  (`neutral` / `excited` / `surprised`) picks that voice's matching clip; if
  missing it falls back to the voice's `neutral.flac`. A voice is never pinned.

## Usage
- **Run all cells in order.** Only Run/Render and Preview are heavy.
- Rendering needs the **T4 GPU** runtime (Chatterbox-Nano). First run downloads
  ~2.9 GB of model weights + 10 female voice clips + whisper model.
- After rendering, use the **Preview** cell to review one reel at a time
  (Next / Previous). Download the ones you like with the **Download** cell.
- **Nothing is auto-pushed to Facebook** — you post manually.

> TIP: shorter is better. Keep each reel ~16s (soft target), anything under
> ~25s is fine. Very long blurb results in a long reel — consider editing the
> blurb in `reels_batch.txt` before you re-render.