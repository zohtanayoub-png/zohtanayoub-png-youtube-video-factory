# CLAUDE.md - working notes for AI assistants and developers

Context for anyone (human or model) modifying this repository.

## What this project is

An autonomous, cloud-based factory that produces long-form (15-30 minute)
narrated home decor / interior design videos for a US English YouTube audience,
running entirely on GitHub Actions CPU runners.

## Hard rules

These are requirements, not preferences. Do not relax them.

1. **No background music, ever.** The audio track is narration only.
   `audio.music` is forced to `false` in `load_config` and `validate` raises
   `ConfigError` if it is true. `Config.music_enabled` always returns `False`.
2. **No paid services at runtime.** No Runway, Veo, Kling, ElevenLabs, OpenAI,
   Anthropic, or any paid TTS / video / editing API. Claude Code was used to
   build this; it is not a runtime dependency.
3. **No scraping of social media.** Footage comes from the Pexels and Pixabay
   APIs, or from files the owner supplies in `assets/local_clips/`.
4. **Secrets never touch the repository.** Environment variables and GitHub
   Secrets only. `logging_utils.RedactingFilter` scrubs anything key-shaped
   out of log records.
5. **Never commit MP4s.** Only the small JSON history in `data/state/` is
   committed.
6. **The pipeline degrades, it does not crash.** A failed clip, a failed TTS
   chunk, a missing LLM, an unreachable provider - each has a fallback.

## Layout

```
src/vidfactory/
  config.py          configuration load + validation (music guard lives here)
  logging_utils.py   tagged logging + secret redaction
  database.py        SQLite + JSON snapshot import/export
  knowledge.py       ~240 curated home decor ideas (the script engine's source)
  topic_engine.py    title grammar, similarity detection, duplicate rejection
  script_generator.py template engine (default) + adaptive length fitting
  llm.py             optional local llama.cpp engine, always optional
  scene_planner.py   narration -> scenes -> per-scene visual queries
  stock/             provider adapters: base, pexels, pixabay, local, registry
  ranking.py         six-dimension clip scoring + diversification
  downloader.py      retries, ffprobe validation, content hashing
  tts.py             Piper -> eSpeak NG -> silent, chunking, loudness, timings
  subtitles.py       SRT built from the TTS timeline (no ASR needed)
  editor.py          shot planning + FFmpeg assembly
  ffmpeg_utils.py    run/probe wrappers
  metadata.py        title, description, chapters, tags
  quality_control.py ffprobe validation report
  youtube_upload.py  optional YouTube Data API v3 upload
  pipeline.py        orchestration
  main.py            CLI
  testassets.py      synthetic FFmpeg footage for the offline integration test
```

## Non-obvious decisions

* **Narration comes before footage.** `pipeline.run` synthesizes audio, then
  plans shots against the measured per-scene durations. Reversing this would
  reintroduce drift between words and pictures.
* **`zoompan` is banned.** It ran roughly 150x slower on a CPU runner and
  produced wrong output durations (5 s in, 2560 s out). Ken Burns motion is a
  time-varying `crop` plus `scale`; see `VideoEditor._filter_for`.
* **Shots are rendered to identical intermediates and joined with the concat
  demuxer using stream copy.** A single giant `filter_complex` is far slower
  and much more fragile with 200+ inputs. Crossfades re-encode in groups of
  eight and the groups are then copied together.
* **Subtitles are derived from ffprobe durations of the TTS chunks**, so they
  are exact and free. Do not add Whisper.
* **The template script engine is the default, not a fallback of last resort.**
  It is deterministic, fast and always works. The LLM path exists for quality
  experiments and must never become required.
* **`data/state/*.json` is the durable store; SQLite is the working copy.**
  Runners are ephemeral and a binary `.db` is hostile to git.
* **`autopilot.videos_per_week` is enforced by the workflow**, which counts
  `created_at` entries in `data/state/videos.json` from the last seven days and
  skips the run when the quota is met. The cron may fire more often than the
  quota allows; that is intentional.
* **The final mux stream-copies by default.** The closing fade is baked into
  the last shot and shot planning covers the audio tail, so the whole timeline
  does not need re-encoding. Burned-in subtitles fall back to a re-encode.

## Testing

```bash
python -m pytest -q -m "not integration"   # ~200 fast tests
python -m pytest -q -m integration         # a genuine ~40 s 1080p render
```

The integration test uses FFmpeg-generated synthetic footage and the offline TTS
engine, so it needs no credentials or network. It must keep passing.

## Adding a stock provider

1. Subclass `StockProvider` in `src/vidfactory/stock/`.
2. Implement `search()` and a `classmethod parse()` so responses can be tested
   without network access.
3. Register it in `stock/registry.py` (`PROVIDER_CLASSES`, and `ENV_KEYS` if it
   needs an API key).
4. Add a `sources.<name>` flag to `config.yaml`.
5. Add a parse test with a realistic captured payload.

## Adding knowledge

`knowledge.py` entries need `title`, `why` (>= 12 words), `how` (>= 10 words),
at least three `queries` and some `tags`. `mistake` is optional. Content must be
original and written in American English - `tests/test_script_and_scenes.py`
enforces the shape.
