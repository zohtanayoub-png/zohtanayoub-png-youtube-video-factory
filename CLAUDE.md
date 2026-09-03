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
7. **A development render must not claim production footage.** `generation.mode`
   is `test` by default; only `production` writes a clip's `last_used_at`, and
   only that column feeds the cooldown. Sixteen development renders had already
   taken 465 Pexels videos out of circulation for 45 days each before anything
   was published; `vidfactory cooldown --release` moves that usage into the
   development columns without deleting a row.
8. **Content language and search language are different things.** The channel
   narrates in US English by default and in Spanish on request; Pexels is
   always queried in English whichever is chosen. A Spanish string must never
   reach a stock provider. See `languages.py`.

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
  queries.py         specific -> variant -> broad -> generic query ladder
  languages.py       content language vs search language; the registry
  knowledge_es.py    ~150 ideas written natively in Spanish
  phrases_es.py      Spanish hooks, frames, transitions, elaborations
  ass_subtitles.py   premium burned-in captions (ASS + libass)
  visual_analysis.py FFmpeg frame sampling + pixel statistics + flags
  visual_model.py    optional ONNX CLIP backend, always optional
  state_merge.py     union two divergent copies of data/state (see below)
  causal_alignment.py does the written paragraph explain the title's promise
  contradiction.py   does the paragraph argue *for* its own heading
  concepts.py        is the paragraph about the same thing as its heading
  principles.py      does the causal sentence explain *this* section's idea
  entities.py        the object a concrete shot has to actually contain
  title_alignment.py what a title promises, and which ideas actually deliver it
  editorial_qc.py    repetition, relevance and diversity gates (not ffprobe)
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

## Editorial invariants (added after the first production video repeated footage)

* **A provider video ID appears at most once per video.** Not once per scene,
  not "a different timestamp is fine" - once. `plan_shots` enforces it and
  `editorial_qc` fails the run if it is violated. The v1 planner cycled
  `order[cursor % len(order)]`, which replayed the whole clip sequence in its
  original order once the cursor wrapped; that is what made the final third of
  the first video look repetitive.
* **Footage is sized from `estimate_shot_count`, never from
  `duration / max_shot`.** Every scene rounds its own shot count up
  independently, so the naive formula under-counts and starves the edit.
* **Specific queries are exhausted before the generic category fallback**, and
  the generic share is measured in the editorial report.
* **Every idea must support the title's promise.** `title_alignment` rejects
  ideas that do not, before the script is written.
* **Every written paragraph must say *why* it delivers that promise.**
  `title_alignment` validates the idea; `causal_alignment` validates the
  narration the viewer actually hears. "Measure before buying because returns
  are expensive" fails a "look bigger" title; the same idea explained through
  visible floor area passes. A failing paragraph is repaired from its own
  mechanism, and replaced only if that is impossible.
* **A clip is judged by its pixels, not by its caption.** Run 6 reported 91%
  premium footage for a video containing a floor plan, two empty rooms and a
  plastic-wrapped sofa, because Pexels described all of them as interiors.
  `visual_analysis` decodes three frames of every shortlisted candidate and
  measures them. `premium_visual_ratio` now requires the caption *and* the
  frames to agree.
* **Spanish is optional but not second-class, and it is written rather than
  translated.**
  `knowledge_es` and `phrases_es` are original Spanish, not a pass over the
  English modules. Promise alignment, the causal check, the topic grammar and
  the metadata all have Spanish vocabulary of their own, because a translated
  keyword list matches almost nothing in a natural Spanish script.
* **Captions are burned in, and the SRT stays plain.** `subtitles.srt` is
  what YouTube ingests; `subtitles.ass` is what goes into the picture.
  Three-to-seven-word phrases, never ending on an article or preposition,
  one warm accent tone on measurements and outcome words, a 120 ms fade, and
  a 118 px bottom margin at 1080p.
* **ASS alpha is inverted.** `00` is opaque, `FF` is invisible. The first
  burned-in captions used `&HC8` for the outline - 78% *transparent* - and
  white text on a pale wall had almost nothing holding it.
* **An explanation has a direction, and it must point the same way as the
  heading.** Run 16 shipped "Buy one bigger thing instead of three medium
  things ... Oversized pieces eat visible floor area, so a small room feels
  cramped". It scored 1.00 for causal alignment, because it does state a
  mechanism, a connective and the promised outcome - it just states them
  against the advice. `contradiction.py` reads each item as
  `recommended_action -> mechanism -> desired_outcome`, and a sentence blaming
  the pole the heading recommends is rejected: first by refusing that
  explanation during repair, then by a post-write check that rewrites the
  paragraph and finally replaces the idea. `contradiction_count` is an **error**
  in the editorial report, not a warning.
* **A mechanism is not a subject.** `vertical_emphasis` is equally true of a
  curtain rod, a bookcase and a gallery wall, so matching on the mechanism
  alone let run 22 explain "Hang art at eye level" with "hanging the fabric
  high and wide leaves the glass itself uncovered". Causal alignment scored it
  1.00 and the contradiction check found nothing, because on their own terms
  both were right. `concepts.py` locks an explanation to **mechanism +
  concept**: `repair_text` will not reach for another subject's sentence, and
  a post-write pass rewrites anything that slips through.
  `cross_concept_contamination_count` is an **error** in the report.
* **A number in the topic is a requirement.** "10 Small Living Room Tricks"
  must contain ten; run 22 renamed it to five. `Topic.count_is_explicit`
  carries the request, `plan_item_count` honours it, and `_trim_to_duration`
  pays for it by shortening sections - optional material first, and only then
  the advice itself, never the causal explanation. An impossible count raises
  rather than renaming the video.
* **The script is sized from the rate the voice actually spoke at.** The
  engine's declared words-per-minute is a constant; `record_speech_rate`
  measures each render and `measured_speech_rate` sizes the next one, so a
  five minute request lands inside ten percent instead of at 4:04.
* **A large mirror and an oversized sofa are not the same mechanism.**
  `statement_piece_scale` (fewer, larger objects reduce visual fragmentation)
  and `furniture_footprint_scale` (an oversized sofa eats visible floor) share
  no words and no explanations. One mechanism owning both is what let the sofa
  sentence be appended to the artwork advice.
* **An idea must deliver the promise with its *primary* mechanism.**
  `subject_deny_signals` is matched against an idea's title and tags only and
  cannot be rescued, because "Mix at least three materials in every room" is a
  texture tip however many sentences about reflection get bolted on.
* **A weak final shot is repaired, not reported.** Detecting a problem and
  giving up is not a pipeline. Before editorial QC, `_repair_weak_shots` takes
  every final shot below `LOW_RELEVANCE_MATCH`, sends its own shot intent back
  out to search - rephrased differently each round: framing words, then
  synonyms, then the room and technique rather than the object - ranks,
  frame-inspects, and swaps the clip **only** when the replacement scores
  strictly better on the same measurement. Three rounds, then the gate fails.
  Good shots are never touched, a replacement can never be a source another
  shot holds, and no threshold moves: `repair_rounds_used`,
  `weak_shots_before_repair`, `weak_shots_after_repair`,
  `repaired_shot_count` and the before/after averages are all in the report.
* **Low relevance triggers a new search, not a warning.** A scene whose footage
  does not match its narration sends the search back out - the shot intents it
  has not spent, then deeper pages, then the rest of its ladder - for
  `sources.relevance_search_budget` rounds. Only then is a weaker clip
  acceptable, and the log says so.
* **Production is graded on the clips that reach the screen.** `final_shot_*`
  metrics measure the edit; `candidate_*` measure the search. Run 16 gated on
  the candidate pool and reported "19 of 49 low relevance" for a 36-shot video.
* **Every 3-6 second chunk of narration gets its own visual intent.** A scene
  used to carry one query for a whole paragraph, so "an undersized rug leaves
  the seating floating" and "choose one large enough for the front legs" were
  searched and scored identically. `ShotIntent.search_text` is always English
  and is what CLIP scores the frames against.
* **Similarity is not presence.** Run 25 averaged 0.569 across the clips on
  screen with not one below the 0.50 floor, and showed colourful ribbons for
  "paint the trim the same colour as the walls" and potted plants for "a rug
  too small to reach the sofa". No threshold on sentence similarity would have
  caught it: a styled living room genuinely *is* similar to a sentence about
  the rug in it - same palette, same furniture, same vocabulary. The rug is
  simply not there. `entities.py` maps concrete advice to the object it
  requires and MobileCLIP scores the frames against short "it is here" prompts
  against short prompts naming the failures actually observed ("a floor with
  no rug", "indoor potted plants", "colourful clothing and ribbons"); the
  verdict is the margin between them. `entity_grounding_failure_count` is an
  **error**, additional to every existing threshold and a replacement for
  none. A failed shot is repaired first, searched by the object rather than by
  the advice - the advice is what found the plants - and a replacement must
  improve the semantic score **and** contain the object. Abstract advice
  requires nothing: demanding an object the sentence never promised rejects
  good footage.
* **The subject is the object named first, not the one named most.** "A rug
  too small to reach the sofa leaves the seating floating" names seating twice
  and the rug once. It is rug advice; the sofa is the landmark the rug is
  measured against.
* **A principle is not an object either.** "Balance visual weight across the
  room" names nothing physical, so the cross-concept check had no subject and
  correctly returned 0 while run 25 explained that section through furniture
  footprint and walking paths. `principles.py` gives abstract headings a
  subject of their own, and `primary_concept_contamination_count` is an
  **error**. It fires only on sentences carrying a causal connective, only
  when a competing vocabulary appears at least twice, and only when the
  section's own appears not at all - a false positive here rewrites a
  paragraph that was already right.
* **An optional example is not the principle.** A section offering a plant, a
  lamp, a mirror or a chair and then explaining itself through the mirror's
  reflection has given three readers in four no reason at all. The repair
  conditions the sentence rather than deleting it - "if you choose the mirror,
  a reflection adds depth" - because the reason is true, it just has to say
  which case it covers. `optional_example_leakage_count` is an **error**.
* **Long-form quality is measured, not assumed.** Run 22 finished at a 0.638
  premium ratio and run 25, three times longer, at 0.493.
  `final_shot_premium_visual_ratio` targets 0.60: a warning in test mode, a
  gate in production. The answer to a weak pool is more pages and more query
  variants, never a lower definition of premium.
* **Relevance outranks beauty.** The second ranking stage weights
  scene-to-clip semantic match (45) above interior subject (30), visual
  quality (18), novelty (12) and technical quality (8). A beautiful unrelated
  luxury interior loses to a plainer clip that shows the advice.

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
* **The local llama.cpp path stays opt-in because provisioning it on a GitHub
  Actions runner is not reliable.** Measured over four CI runs: ggml-org
  publishes prebuilt binaries only on rolling `bNNNN` tags while marking a
  stale `v0.3.0` (containing one text file) as "latest", and the releases API
  is rate limited from runners. `vidfactory llm-check` reports what actually
  happens on a given machine; enable `script.llm.enabled` only if it passes
  there. Model choice if you do: Qwen2.5-1.5B-Instruct Q4_K_M, Apache-2.0,
  about 1.0 GB on disk and 2 GB of RAM at a 4k context.
* **Frame inspection is two-stage on purpose.** Metadata ranking is cheap and
  filters the obvious rejects; only a shortlist (`visual.shortlist_multiplier`,
  capped by `visual.max_clips_analyzed`) has its frames decoded. Provider
  preview stills are used where the provider publishes them - Pexels gives
  about fifteen per video - so a candidate can be rejected without
  transferring any of it. Downloaded clips are then re-inspected against
  their own frames, so the numbers in the report describe what is on screen.
* **The CLIP backend is optional and must stay that way.** `visual_model`
  loads a small ONNX CLIP export on CPU and returns `None` on any failure.
  `vidfactory visual-check` reports what a given machine can actually do.
  Without it, pixel statistics still catch empty rooms, dark scenes and floor
  plans; plastic covers, pets and room types get weaker.
* **Two branches that both rendered have two histories, and git cannot merge
  them.** Both sides rewrite every line of `data/state/*.json`, so the conflict
  is total, and `--ours` or `--theirs` deletes real renders and real cooldown.
  `vidfactory merge-state --base --ours --theirs --out` unions them on the
  natural keys the schema already declares - `topics.slug`,
  `clips(provider, provider_id)`, `videos(created_at, title)`,
  `generations(run_id, started_at)` - renumbers the ids and carries each scene
  to its video's new one. Counters use `ours + theirs - base`, the only
  formula that neither loses a use nor invents one; importing both snapshots
  instead would key on the autoincrement `id` and let one branch's
  `videos.id = 3` overwrite the other's different video. `schema_info` is
  merged too, because it holds the measured speech rate: the version takes
  the newer side, and two measured rates for one voice are averaged rather
  than picked between, since both are real renders of the same voice.
  Leaving that table out of the union restored the engine's declared 155
  wpm on the next render, which is the whole of the duration bug.
* **Schema migrations run in `initialize()`, not lazily.** They used to run on
  the first `record_clip_use`, which is *after* `import_state` - and
  `import_state` builds its column list from `PRAGMA table_info`, so every
  load of the history silently dropped `test_use_count` and
  `test_last_used_at`. That is how 420 clips came to be recorded as never
  used: `cooldown --release` moved their count out of `use_count`, and the
  next run's import threw away the column it had been moved into. The merge
  reconstructs those from the `first_used_at` that survived, as development
  history so nothing wrongly returns to the production cooldown.
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
python -m pytest -q -m "not integration"   # ~400 fast tests
python -m pytest -q -m integration         # a genuine ~60 s 1080p render
python -m vidfactory llm-check             # is the optional local model viable here
python -m vidfactory visual-check          # is the CLIP backend viable here
python -m vidfactory cooldown              # how much footage is locked up
python -m vidfactory cooldown --release --dry-run   # what a release would free
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
