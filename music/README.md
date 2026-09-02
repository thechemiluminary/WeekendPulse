# music/

Drop **loopable** background tracks here (`.mp3` or `.wav`). The reel renderer
picks one randomly, starts it at position 0, and cuts it wherever the narration
ends (it is NOT tail-cut). Keep tracks short ~20-40s so they cover a full reel.

Notes:
- Tracks are committed and served publicly (raw.githubusercontent) so the Colab
  notebook can fetch them without auth. If WeekendPulse is made private later,
  the Contents-API fetch will need a token.
- The duck mixer lowers the music under the TTS voice automatically.