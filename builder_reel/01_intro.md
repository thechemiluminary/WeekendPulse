# WeekendPulse Reels — Batch Renderer

Turn today's **reel-approved** news posts into short, ~16s vertical Facebook
Reels, then **post them to the Page**. One reel per story. Source of truth is
`manifest.json`: the bot records each post there (post_id, title, description,
reel approval) and the notebook updates each entry after it renders + posts,
recording the voice + emotion used and the returned reel video id.

## Pipeline (per reel)
1. Ken Burns pan/zoom over the article's **real photo** (branded fallback card if none).
2. **Chatterbox-Nano** TTS narration of the AI's `reel_blurb` — a **random
   female voice**, precise emotion (`neutral` / `excited` / `surprised`).
3. Whisper-aligned **captions** burned in.
4. A **title card** (vibrant orange + white) fades in over the body.
5. Music from the repo `music/` folder starts at position 0 and is **cut at
   narration end** (loopable head, auto-ducked under the voice).
6. A **~0.4s crossfade** into the fixed 4s `outro.mp4`.
7. **Post cell** uploads each rendered MP4 to the Page via the Graph API
   `videos` endpoint and records the result in `manifest.json`.

## Voices
- **10 female voices** are auto-downloaded from the public
  `OwenTyme/voice-zero` `voices-emotion/` pool (each is a folder of emotion
  clips, e.g. `emily_cripps/excited.flac`).
- Every reel uses a **random female voice**. The AI's `reel_emotion`
  (`neutral` / `excited` / `surprised`) picks that voice's matching clip; if
  missing it falls back to the voice's `neutral.flac`. A voice is never pinned.
- The voice + emotion used are recorded in `manifest.json` so you can see what
  performs better.

## Usage
- **Run all cells in order.** Only Run/Render and Preview are heavy.
- Rendering needs the **T4 GPU** runtime (Chatterbox-Nano). First run downloads
  ~2.9 GB of model weights + 10 female voice clips + whisper model.
- The **Post** cell needs two tokens **at runtime** (paste them, or set Colab
  Secrets): the **FB page token** (posts reels) and the **GitHub repo token**
  (writes `manifest.json` back). Neither is ever baked into the notebook.
- An article is **not picked again** once its reel is posted (the manifest's
  `reel_posted` flag). Re-render a story is fine until you post it.

> TIP: shorter is better. Keep each reel ~16s (soft target), anything under
> ~25s is fine. Very long blurb results in a long reel — consider editing the
> blurb in `reels_batch.txt` before you re-render.