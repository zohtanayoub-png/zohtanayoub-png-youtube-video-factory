# CLAUDE.md - working notes for AI assistants and developers

Context for anyone (human or model) modifying this repository.

## What this project is

An autonomous, cloud-based factory that produces **two** things on GitHub
Actions CPU runners, from one set of shared machinery:

1. **Long-form** (15-30 minute) narrated home decor / interior design videos
   for a US English YouTube audience. This is the original product and
   everything outside `src/vidfactory/reels/` belongs to it.
2. **DIABETES REELS** - vertical 20-60 second Spanish reels about diabetes and
   glucose, for Instagram / TikTok / Shorts. `src/vidfactory/reels/`,
   `vidfactory reel`, `.github/workflows/generate-reel.yml`.

They share the parts that are genuinely general - TTS, stock search, ranking,
frame inspection, the downloader, the FFmpeg editor, the ASS caption renderer
- and share **no editorial logic at all**, because forty vertical seconds
about food and twenty-five horizontal minutes about living rooms disagree
about almost everything: shot length, frame shape, what a good opening is,
and what a false sentence costs. Nothing in `reels/` is imported by the
long-form pipeline, and a test enforces that.

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
  instructions.py    the whole visual claim, not the noun inside it
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
  reels/             DIABETES REELS - the second product (see below)
    knowledge.py     Spanish diabetes/glucose topics, claims and their sources
    sources.py       the organisations every claim rests on
    safety.py        what a reel about diabetes may never say
    foods.py         the food a beat names, and whether the shot shows it
    hooks.py         8-12 candidate openings, scored, one chosen
    script.py        hook/answer/value/retention/takeaway/CTA, fitted to length
    voice.py         Kokoro first, Piper as the fallback; licence + prosody
    narration.py     the reel's own narrator: pace and pause vary by beat
    captions.py      1080x1920 captions plus the fixed top title
    qc.py            the seven metrics, and the production gate
    metadata.py      caption, hashtags, disclaimer
    pipeline.py      orchestration, reusing the shared machinery
```

## DIABETES REELS

A health channel, so the rule the long-form side applies to footage - a number
in the report has to come from a measurement - applies here to the **words**.

* **Every factual sentence carries a source.** `sources.py` lists the standing
  guidance of bodies whose job this is (ADA, NIDDK, WHO, Harvard Nutrition
  Source, Diabetes UK, Fundacion para la Diabetes, redGDPS), and
  `unsupported_claim_count` is an error. A mistyped source key counts as
  unsupported rather than being skipped, because that is exactly the claim
  that would otherwise ship with nothing behind it.
* **Claims are written at the strength the evidence supports, not softened
  afterwards.** "10 frutas que bajan el azucar" is a false sentence; "10
  frutas que suelen tener un impacto mas moderado en la glucosa" is a true one
  carrying the same useful information. `safety.py` refuses the first: cure,
  reversal, guarantees, immediate effects, universal prohibitions, anything
  touching medication or insulin dosing, fear used to hold attention, and any
  effect claim missing the hedge that makes it true. The hedge rule is
  deliberately **directional** - "como influye el tamano de la racion en la
  glucosa" names a subject and asserts nothing, and demanding a hedge from it
  would be asking a title to apologise for existing.

  The exemption for viewer-conditional sentences reads the sentence rather
  than matching a list. "Si comes fruta sola y despues ves un pico grande"
  reports what the viewer has seen and asserts nothing, and the first version
  encoded that as a list of *situations* - "si tienes", "si comes", "si a
  media" - so every new opening had to be added to the list before it could
  be written. It now asks three things: does the sentence open with si or
  cuando, does that clause address the viewer, and is the effect word inside
  it. "Si comes fruta, tu glucosa sube" is still caught, in the main clause.

  Two rewrites were caught by this layer while shortening the items, which is
  the check earning its place: "dispara la racion" read as a glucose claim,
  and "influyen tu tratamiento" as individual medical instruction.
* **Three caveats recur because they are what make almost anything in this
  niche correct**: la cantidad, la preparacion, y con que se combina - plus
  the fact that people genuinely differ. A script that has been trimmed until
  it lost them all gets one back rather than a warning, because the warning
  tells an operator the reel is weaker and the viewer is the one who needed
  the sentence.
* **The hook is chosen, not written once, and what it is scored on is
  whether it names the viewer's problem.** Eight to twelve candidates per
  topic; the weights lead with problem recognition (0.26) and immediate
  usefulness (0.18) ahead of curiosity, specificity, emotion and relevance,
  and the whole thing is multiplied by how well the opening matches what the
  reel actually delivers - because "pick the strongest candidate" makes
  hook/content drift *more* likely, not less. A candidate that names no
  problem and carries no emotion has its curiosity discounted, because that
  combination is what a generic opening looks like from inside the scorer.

  `HOOK_PASS` was read off the brief's own preferred hooks rather than
  chosen: scored against the topics they belong to they land between
  **0.491 and 0.692**, a deliberately generic opening scores **0.376**, and
  "Si tienes diabetes, no todas las frutas afectan igual a tu glucosa" -
  true, on-topic and about fruit rather than about the viewer's problem with
  fruit - scores **0.320**. That last one used to pass at 0.54. It is scored
  low rather than refused, because refusing it would be a claim that it is
  dishonest and it is not.

  Every topic carries the viewer's actual `worry` as a clause ("que la fruta
  te dispare la glucosa", never "la glucosa"), the generic templates are
  filled from it, and the per-topic hooks are written problem-first: as
  subject-first openings they scored 0.12 to 0.36, and rewritten they choose
  between eight and twelve candidates at 0.48 to 0.78.

  Banned openers ("Hoy vamos a hablar de...", "En este video...", "Hola
  amigos...", a generic "?Sabias que...?") are refused outright rather than
  scored low: they are not weak openings, they are a wasted second, and it is
  the only second guaranteed to be watched.
* **The hook has a time budget as well as a quality one, and the three gates
  are applied together.** The brief puts the hook in the first two seconds -
  six words at this voice's rate - and its own example hook is fifteen. Both
  cannot be had, so the builder prefers the shortest hook among the near-best.
  That is worth more than it sounds: it is what pays for the fifth item.

  The three things the report will gate on - the hook is about this reel
  (alignment), it is strong enough (`HOOK_PASS`), and it is short enough to
  leave the answer at `HOOK_SECONDS` - are one predicate, not three filters in
  a row. In a row they fight: filtering by strength first threw away the only
  candidate that fitted the time budget, and the builder then handed out a
  hook its own report refused. `qc` reads `HOOK_SECONDS` from `script` for the
  same reason. Two topics had no candidate satisfying all three and were given
  one; `ranking-frutas` now opens at 0.68 with alignment 1.00 in 17 words.
* **The third second carries the answer, not a trailer for one.** "En este
  reel vas a ver cinco frutas" spends it describing the reel to somebody who
  is already watching it; "fresas, frambuesas, kiwi, manzana con piel y
  aguacate" is the same length and is already the value. A viewer who leaves
  after that sentence has still been told the thing they came for.
  `value_starts_at` measures it from the synthesized track, and the reel ends
  on a practical takeaway before the CTA.
* **Every item says why, and the duration is paid for in whole items.** The
  first version made the reason optional - the first thing dropped when the
  budget got tight - which is how a list of five assertions with nothing
  behind any of them came to be a reel. An item the viewer cannot act on is
  not shorter value, it is worse value, so the trim now drops items and every
  survivor keeps its reason. Making that affordable meant rewriting all 85
  items from prose to speech, 24 words each down to 17.
* **A number in the title is a requirement here too, and so is a number in
  the answer.** "5 frutas" that ships four has a false line burned into every
  frame of the reel, and "granola, barritas, salsas, zumos envasados y lacteos
  de sabores" followed by three items is the same lie three seconds in.
  `promises_all_items` marks the topics whose answer enumerates, and
  `required_item_count` covers both.

  `build` raises rather than renaming the video, which is the answer the
  long-form side gives - but a strict pure function is not a reason for the
  pipeline to produce nothing, and hard rule six says it degrades instead. So
  `build_fitted` takes the shortest allowed duration that keeps the promise,
  says loudly that it did, and puts `requested_seconds` and the rendered
  duration in the report. At the measured Kokoro rate six five-item topics
  render at 60s rather than 45s. That is the honest shape of five items that
  each carry a reason; the lever, if 45s matters more, is fewer items.
* **A reel is sized from the rate a *reel* is spoken at.** Not the content
  language's declared words-per-minute: that is 142 wpm for Spanish and it
  describes long-form narration with long-form pauses. The voice comparison
  measured the real thing on the runner - the same 126 word script ran 48.05s
  under Kokoro and 46.79s under Piper, so 2.62 and 2.69 words a second
  including every pause - and `MEASURED_WORDS_PER_SECOND` carries those,
  keyed by engine. The long-form number under-counts a reel's budget by a
  fifth, which is two items of a five item list: the first Kokoro render was
  refused before a word was synthesized for exactly that reason. A database
  measurement is looked up under the engine that will actually narrate, not
  under "piper" whatever is speaking.
* **The hook may not be the conclusion said twice.** Measured as the longest
  shared run of words, not as vocabulary overlap: a hook is *supposed* to
  share its subject with the conclusion, and what must not happen is the same
  clause appearing at both ends of a forty second video.
* **Never below two items** - a twenty second reel with two items is a reel,
  and one with none is a caption read aloud.
* **The trim counts the script it is actually going to ship.** It used to
  estimate the fixed beats and subtract, and the caveat line is appended
  *after* the script is written - so a 45 second request came out at 50.0.
  `_assemble` builds the real beat list for a candidate set of items and the
  trim counts that.
* **The interior gates are off, and that is not a lowered standard.**
  `enforce_premium`, `enforce_aspirational` and `min_interior_relevance` exist
  to reject footage that is not a photograph of a styled room. A bowl of
  strawberries is not a photograph of a styled room.
* **Test and production cannot mix, structurally.** The reel pipeline never
  calls `record_clip_use`, so it neither reads nor writes the 45-day footage
  cooldown the long-form product depends on. What the mode changes is the
  gate: in production one medical-claim risk or one unsupported claim fails
  the run.
* **The voice is Kokoro, and the licence is why.** `hexgrad/Kokoro-82M` is
  Apache-2.0 for both the weights and the code, which is what makes it usable
  for a commercial channel; it runs on CPU in Actions and reaches espeak-ng
  through misaki for Spanish G2P. **Piper stays** as the fallback and is not
  removed from the project - the long-form side still uses it, and a reel
  whose Kokoro import fails is narrated rather than failed. `licence_report`
  reads the installed distributions rather than repeating a claim from a
  comment, and it records the Piper *voice* licences separately from the
  Piper runtime's, because the two are separate artefacts and it is the voice
  that ends up in the video.
* **Delivery is half of "sounds robotic", and no amount of rewriting fixes
  it.** `NarrationBuilder` reads a script at one pace with one pause between
  scenes, which is right for twenty-five minutes and is exactly what makes
  forty seconds sound like an audiobook. The reel walks its own beats
  instead: the hook lands at normal pace and gets a real breath, the answer
  follows with no pause worth the name, items run slightly quick the way
  anyone reads a list, the takeaway is the slowest thing said. Nothing about
  the words changes. An engine that takes no speed argument (eSpeak) still
  works - it is read at one pace and the log says so.
* **A voice comparison has to be the same script.** `vidfactory
  reel-voice-check` builds one script and synthesizes it with each engine
  named, reporting licence, render time, audio duration and prosody -
  loudness variation, silence ratio, pause count, mean and spread of pause
  length, and speech-rate variation. None of those is naturalness; what they
  are is the difference between a delivery that varies and one that does not,
  which is the specific complaint, and unlike an opinion about a waveform
  they can be compared between two files. An engine asked for by name that
  quietly falls back is flagged `substituted`, because a comparison that
  compares Piper with Piper is worse than no comparison at all.
* **A beat that names one food has to show that food.** Run 34093462658
  narrated "la manzana con piel conserva la fibra" over a close-up of an
  **orange**, and nothing in the reel pipeline was in a position to notice:
  entity grounding is long-form's, and the reel asked only whether a clip was
  semantically similar to a sentence. A bowl of citrus on a wooden table is
  extremely similar to a sentence about fruit on a table.

  `reels/foods.py` is `entities.py` pointed at food - the machinery is
  imported, not copied, and `score_from_similarities` takes its thresholds as
  arguments so the long-form verdict is byte-identical. The registry is
  eighteen foods with Spanish triggers, English prompts, and the competitors a
  stock search actually returns instead; the apple's first competitor is an
  orange because that is what shipped.

  One rule the interiors never needed: **a beat naming one food requires that
  food; a beat naming several requires none.** "Fresas, frambuesas, kiwi,
  manzana con piel y aguacate" is the answer beat and a mixed bowl is the
  right picture for it. Where a sentence names two, the item's key decides -
  "cambiar la fruta entera por zumo" is about the juice. Abstract advice
  requires nothing, exactly as on the long-form side.

  Grounding follows the **narration timeline**, never the reel. Every beat
  knows when it is spoken and what it must show; a candidate that fails is put
  back before it is ever assigned, and the beat re-searches the *object* for
  up to three rounds, because the beat's own query is what returned the wrong
  food. A correct strawberry clip earlier cannot excuse an orange during the
  apple beat, because nothing is averaged across the reel.
* **The interiors' probe does not work on food, and the fix was the question
  rather than the prompts.** Measured before it was trusted, over 28 clips
  found by searching for the food and 28 found by searching for the food that
  turns up instead:

      cut   kept of correct   rejected of wrong
      0.20    12/28 (43%)        16/28 (57%)
      0.40    14/28 (50%)        12/28 (43%)
      0.60    17/28 (61%)         5/28 (18%)
      0.80    20/28 (71%)         3/28 (11%)

  kept% + rejected% is ~100 at every cut, which is one distribution rather
  than two: the threshold trades one error for the other along the same curve
  and buys nothing. `manzana` came back **inverted** - real apple footage at a
  median of 0.131 against orange footage at 0.508 - and `aguacate` did not
  separate at all, 0.958 against 0.910 on kiwi footage.

  This is the mirror image of the long-form result, and for the mirror-image
  reason. There, "does this room contain a wall" is true of every room, so
  presence separated nothing and displacement was the only answerable
  question. Here the opposite holds: a fruit close-up is *of one fruit*, and
  apple, orange and pear are mutually exclusive in a way a wall and a sofa are
  not. So `identify_food` ranks every prompt and asks which came first,
  scoring the share of frames in which the right food won. No margin band - a
  frame that looks marginally more like an orange than an apple is a frame of
  an orange.

  **And the backend was the limit here too.** All four combinations were
  measured - both probes on MobileCLIP-S0 and on the validated ViT-L/14 - and
  only one of them works:

      model / probe                  kept of correct   rejected of wrong
      MobileCLIP-S0 + dominance        43-71%            54% -> 11%  (chance)
      ViT-L/14 + dominance             89%               86%  (at 0.20)
      ViT-L/14 + identification        82.1%            100%  (0.40-0.60)

  So the reel is a **two-model pipeline** for the same reason the long-form
  side is: MobileCLIP-S0 stays the broad ranker and is never asked which fruit
  this is, and `visual.claim_model` answers the food question on the handful
  of candidates a beat actually downloads. `FOOD_IDENTIFY_PASS` is 0.5, the
  middle of a plateau where 0.4, 0.5 and 0.6 all reject every wrong-food clip
  at the same cost.

  Per food, apple against orange - the failure that started all this -
  separates perfectly, **1.0 against 0.0**; so do kiwi and avocado;
  strawberries run 0.834 against 0.0. **Raspberries do not identify
  themselves at all, 0.0 against 0.0**, and are the whole of the five-in-28
  loss. That is recorded rather than tuned away: dropping "strawberries" from
  the raspberry competitors would buy the number back and would be precisely
  the "lower the threshold until it passes" this methodology exists to
  prevent. What it costs is that a raspberry beat gets repaired three times
  and is then reported, which is the right failure to have.
* **Identifying the food is necessary and not sufficient.** The
  identification probe fixed the failure it was written for - three renders
  and the apple beat never showed an orange again - and the next three
  renders shipped an apple **cake**, a **peeled** apple against the line
  "la manzana con piel", a **dog** owning the strawberry frame and a
  **coconut** in the kiwi one. Every one of those scores `manzana = 1.00`.
  They are apples. Nothing is mis-scored; the question was too small.

  This is the same step the long-form side took between `entities.py` and
  `instructions.py`, for the same reason: presence is a property of an
  object, and what a beat needs is a property of the picture. So a
  requirement in `foods.py` has the parts the failures have -
  `required_entity`, `required_attributes`, `forbidden_attributes`,
  `forbidden_dominant_entities`, `context_requirements` - and they are the
  prompts as well as the requirement, because two parallel lists of "what we
  need" and "how we ask for it" stop being in step the first week.

  Four probes, **combined as a conjunction and never as an average**: which
  food is this, what state is it in, what kind of scene is it, and is the
  food the subject at all. An average is exactly the compensation this layer
  exists to refuse - apple 1.00 and state 0.00 must not come out at 0.50 -
  so the reported `entity_grounding_score` is the *weakest* probe that ran,
  and the report carries `wrong_food_failure_count`,
  `wrong_state_failure_count`, `wrong_context_failure_count` and
  `distractor_dominance_failure_count` separately, because an orange and an
  apple cake have different fixes. One decode and one text encode answers
  all four: `VisualAnalyzer.probe_frames` is the neutral primitive and
  `ground_entity` now goes through it.

  Two rules keep this from becoming a wall of guesses. **A probe with
  nothing written down abstains** - it does not pass and does not fail -
  because requiring a state nobody has observed going wrong rejects good
  footage for a rule written from imagination; only seven foods declare one,
  and each entry came from a frame somebody looked at. And **the dominance
  list is not per-food speculation**: a dog in front of the strawberries is
  a dog in front of anything. What is deliberately *not* in it is a person's
  hands or a person holding fruit - half the good footage in this niche has
  one - only "a close-up of a person's face with no food visible".

  The repair searches the **state** first: "manzana" is what found the cake,
  so `state_repair_queries` asks for "whole raw red apple with skin close
  up" before it falls back to the food's own searches.
* **The measurement comes before the render.** A forty second reel
  illustrates a grounding change; it does not measure one, and three of them
  had already been spent watching one failure class at a time. So
  `tools/reel_grounding_check.py validation` scores nine piles of real
  footage whose answer is already known - raw apple, peeled apple, apple
  pie, strawberries, strawberries with a dog, raspberries, kiwi, a tropical
  mix, avocado - twice: once by the entity probe that shipped, once by the
  conjunction. It reports both rates, and only one of them is the point:
  the **false positive** rate is the cake getting through, and the **false
  negative** rate is good footage the repair pass now has to replace. A
  stricter gate is only better when the second does not rise to meet the
  first. Every clip's provider id, score and a JPEG of it go in the
  artifact, because the pile labels are a search intent rather than ground
  truth and "peeled apple" returns the odd unpeeled one.
* **What the nine piles measured, run 34109716760.** Fifty-four clips, six
  per pile, on the validated ViT-L/14, scored twice:

      probe set                false negatives    false positives
      entity only (shipped)     8/30  (26.7%)      16/24 (66.7%)
      the four-probe and       15/30  (50.0%)       5/24 (20.8%)

  The conjunction cuts the failures that reach the screen by two thirds and
  doubles the good footage it throws away. That is the trade, stated as a
  trade: the second number is a repair pass, not a defect, but it is not
  free and no threshold makes it free.

  Per pile it is not one effect but four, and they are not equally good:

      pile                       before   after   caught by
      apple cake or pie            5/6     0/6    state, 6 of 6
      kiwi in a tropical mix       2/6     0/6    dominant subject, 6 of 6
      strawberries with a dog      3/6     1/6    all three, 3 each
      peeled apple                 6/6     4/6    state, 2 of 6

      raw apple with skin          4/6     3/6    (entity rejected 2)
      strawberries                 5/6     4/6
      kiwi                         6/6     5/6
      avocado                      6/6     2/6    state rejected 3
      raspberries                  1/6     1/6    entity rejected 5

  **The cake is solved and the peeled apple is not.** Every apple dessert is
  caught, and the brief's first example - "a peeled apple with no skin" -
  catches two in six, because absence is what a contrastive model is worst
  at: "a peeled apple with no skin" scores about as well against a whole
  apple as against a peeled one. The dominance probe is the cleanest of the
  three, taking the whole tropical pile at a cost of one kiwi.

  **The avocado is the price, and it is a prompt rather than a principle.**
  Three of six real halved avocados lost to "an avocado smoothie" - green
  flesh against green pulp - which is a badly chosen negative, not evidence
  that state cannot be scored. It is written down here rather than quietly
  reworded, because rewriting a prompt after seeing which clips it failed on
  is how a validation set stops measuring anything.
* **The raspberry is a wording problem, and the crop is worth more than the
  frames** (run 34109726602). Eight raspberry clips against eight strawberry
  clips, every combination of three wordings and three frame shapes:

      wording      shape      kept of raspberry   rejected of strawberry
      shipped      3 frames        1/8                    8/8
      shipped      7 frames        1/8                    8/8
      shipped      centre crop     1/8                    8/8
      texture      3 frames        1/8                    8/8
      texture      7 frames        1/8                    8/8
      texture      centre crop     1/8                    8/8
      arrangement  3 frames        3/8                    8/8
      arrangement  7 frames        2/8                    8/8
      arrangement  centre crop     5/8                    8/8

  So 0.0 against 0.0 was never the threshold's fault and never the model's.
  "Fresh raspberries", "a bowl of raspberries", "raspberries close up" -
  the shipped wording - identifies one clip in eight. Describing the *pile*
  instead ("a punnet of raspberries stacked in rows", "many small
  raspberries filling a bowl") reaches three, and scoring the middle of a
  frame decoded at twice the model's input reaches **five, with every
  strawberry clip still rejected**. Naming the berry's own features
  ("hollow centre", "drupelets") buys nothing at all: the model has no
  vocabulary for the thing that actually distinguishes them.

  More frames is not the answer either - seven frames scores slightly worse
  than three - which says the failure is per-frame resolution rather than
  sampling luck, and that is exactly what the crop fixes. None of this has
  been applied: the numbers come first, and a prompt rewritten after seeing
  which clips it failed on needs a fresh pile to be worth anything.
* **The held-out cycle, and the two results that only a held-out cycle
  could give** (run 34113587132; every pile excludes the fifty-four
  development clips by provider id and their nine queries by text).

  **The raspberry was never broken.** The development run measured the
  shipped prompts at 1 clip in 8 and pointed at a wording+crop candidate at
  5 in 8. On fresh footage the shipped prompts keep **6 of 6 raspberries and
  reject 6 of 6 strawberries, 6 of 6 blackberries and 6 of 6 blueberries** -
  a perfect production gate. The four-way confusion matrix moves from 0.750
  to 0.792 for the candidate, which is one clip in twenty-four, and it costs
  a strawberry. So the candidate was **not applied**: what the first number
  measured was a pile, not a probe, and re-tuning against it would have
  written a worse rule with a better-looking table. The probe's real
  weakness is blueberries against blackberries (recall 0.333), which is a
  confusion no reel narrates.

  **The apple was the question, not the backend.** Three formulations on
  four apple piles, on the quantized ViT-L/14 in production and on the same
  model at full precision:

      formulation            raw kept   peeled rejected   accuracy
      absence (shipped)        5/6           4/6           0.875
      positive-vs-positive     6/6           5/6           0.917
      colour-and-surface       6/6           5/6           0.958

  and the two backends score **identically on every row**, so quantization
  was never the limit. Describing the surface on one side and the cut flesh
  on the other - two positives, both about something visible - beats asking
  whether the skin is absent, which is what a contrastive model is worst at.
  Cost, measured on the runner: 0.55 s per frame and about 713 MB peak RSS,
  the same for both. SigLIP was the third candidate and **did not load**:
  its tokenizer.json is a Unigram model and the reader here is CLIP's BPE,
  so adding it is a tokenizer's worth of work rather than a config line.
  That is the honest state of "add a stronger verifier": nothing measured
  needs one yet.

  **The avocado state was asking about the cut.** It described halves and
  slices, so a *whole* avocado - dark bumpy skin, no green flesh anywhere -
  lost to "a tub of packaged guacamole dip" in five clips of six. The brief
  is right that whole, halved and sliced must all pass, and the reason they
  can is that the entity probe has already established the fruit: the only
  thing left for the state to exclude is the form where the food stops being
  visible, a drink or a puree. Rewritten that way and validated on a fresh
  avocado set rather than on the piles that exposed it.
* **The held-out benchmark, run 34115418980: the gate is precise and it is
  not yet ready.** Ninety clips over fifteen piles whose queries had never
  been used to decide anything, 48 valid against 42 invalid:

      probe set                precision   recall   false pos   false neg
      entity only (shipped)      0.723      0.708     31.0%       29.2%
      the four-probe and         0.875      0.583      9.5%       41.7%

  So the conjunction is worth having and it costs what it looked like it
  cost: **false positives fall to under a third of the entity probe's**, and
  one valid clip in six that used to survive no longer does. Per state, on
  fresh footage: peeled apple 2 accepted -> **0**, kiwi in a mixed platter
  4 -> **0**, guacamole 0, an animal owning the frame 0, a strawberry
  milkshake 0; sliced avocado **6 of 6 kept**, halved 5 of 6.

  **Two targets are missed and the reason is the same one both times.** A
  *whole* avocado is kept 2 times in 6 and a raw apple in a market crate 1
  in 6 - and the probe doing most of that rejecting is not the new state
  layer, it is the **entity probe underneath it**: on its own it keeps only
  2 of 6 whole avocados and 2 of 6 of those apples. Look at what
  ``aguacate`` says it is looking for - "a halved avocado", "avocado cut in
  half with the stone", "sliced avocado on a board" - and every positive
  describes a *cut*. A whole avocado is dark bumpy skin and no green flesh
  anywhere, and nothing in the registry describes it. That is the identical
  mistake the state prompts made, one layer down, and fixing the state layer
  could never have reached it.

  It is written down rather than fixed here, because this set has now graded
  a gate and cannot also design the repair: the next cycle needs its own
  calibration piles for the whole-fruit positives and then a third held-out
  set. The two remaining leaks are narrower - two apple tarts and two
  avocado smoothies, all four scoring entity 1.00 and state 1.00, which are
  frames where the glossy surface really is glossy and the fruit really is
  beside the glass.
* **The entity layer, run 34153962478, and the change that was refused.**
  Whole, cut and piled fruit on fresh piles, against what the search returns
  instead - pears and limes for the avocado, oranges for the apple:

      aguacate variant       valid kept   pears/limes accepted
      shipped                  10/12            2/6
      whole-and-cut             9/12            0/6
      whole-cut-and-many       10/12            1/6

      manzana variant        valid kept    oranges accepted
      shipped                   6/12            1/6
      single-and-many           8/12            3/6

  **Naming the whole avocado did not buy the whole avocados back.** Four of
  six either way, and the closest competitor is "guacamole dip" in every
  variant - so the "whole avocado 2 of 6" from the benchmark was again partly
  the pile. What the rewrite does buy is precision: `whole-cut-and-many`
  keeps the same ten valid clips as the shipped wording and halves the false
  positives, which dominates it on both axes, so that is what shipped.

  **The apple candidate was refused, and this is the interesting one.**
  `single-and-many` keeps two more valid clips and accepts two more
  **oranges** - and an orange under "manzana" is the failure this entire
  layer was built to stop. A trade that buys bulk-apple retention with orange
  rejection is the wrong trade whatever the totals say, so the apple keeps
  its wording and the bulk-apple weakness (2 of 6) stays recorded and
  unfixed. It is a real cost: a market-crate shot of apples is good footage
  the repair pass has to replace.
* **The third held-out benchmark, run 34154410206: precision 1.000, and the
  false negatives are no longer the conjunction's.** Ninety clips, fifteen
  fresh piles, 48 valid against 42 invalid:

      probe set                precision   recall   false pos   false neg
      entity only (shipped)      0.600      0.562     42.9%       43.8%
      the four-probe and         1.000      0.479      0.0%       52.1%

  **Every one of the forty-two invalid clips is rejected.** Apple dessert 6
  accepted -> 0, peeled apple 4 -> 0, a tropical platter 4 -> 0, a strawberry
  cheesecake 2 -> 0, an avocado smoothie 2 -> 0, guacamole and an animal 0
  throughout. Halved and sliced avocado are kept 6 of 6 each and whole
  avocado 4 of 6, up from 2 of 6 before the entity rewrite.

  The recall number is worse than the 50% that started this cycle, and the
  breakdown says something different from what it says:

      pile                  entity alone   after the conjunction
      apples in bulk            1/6              1/6
      raw apple with skin       3/6              3/6
      kiwi                      3/6              3/6
      raspberries               0/6              0/6
      whole avocado             4/6              4/6
      halved / sliced avocado   6/6              6/6
      strawberries              4/6              0/6

  **The conjunction costs four clips of forty-eight; the entity probe loses
  the other twenty-one on its own.** These piles are deliberately awkward
  presentations - strawberries scattered on linen, raspberries in a glass
  jar, apples in market boxes - and what they expose is that the layer
  underneath does not recognise fruit outside a bowl. The one pile the
  conjunction does damage is the strawberries, rejected by state, context and
  dominance together, and the reason is visible in the prompts: ``fresas``
  asks for "in a bowl as the main subject" and "on a kitchen table", and
  linen is neither. The context prompts name containers, which is a fact
  about the wording rather than about the footage.

  That is the next cycle's calibration - context prompts that describe the
  food rather than the crockery - and it needs its own piles again. Sixty
  queries are now spent across six runs.
* **Presentation, run 34156801236: the crockery was not the problem, and
  the measurement says where the problem is.** Ninety-eight clips over
  thirty-three piles that hold the food constant and vary how it is
  presented - bowl, plate, linen, board, supermarket box, a hand, a jar, a
  punnet, loose, single, piled, whole, halved, sliced:

      context wording          probe          precision   recall
      container-named          entity alone     0.789      0.662
      container-named          conjunction      0.971      0.485
      food-centred             entity alone     0.789      0.662
      food-centred             conjunction      0.971      0.500

  Rewriting the context to describe the food bought **one clip in
  ninety-eight**, at no cost to precision. It is the right wording and it
  was not the cause. Dropping the supermarket-shelf negative changed
  **nothing at all** - the two variants are identical to the digit - so that
  prompt stays.

  Per presentation, the pattern is not about containers either. Halved,
  sliced, piled and "many" are kept 6/6, 6/6, 3/3, 3/3; **jar, linen and
  plate are 0 of 3 before the conjunction ever runs**, and loose and punnet
  are 1 of 3. Per food:

      food         entity recall   conjunction recall   precision
      kiwi             1.000             0.889            1.000
      aguacate         0.833             0.833            0.909
      manzana          0.800             0.400            1.000
      fresas           0.529             0.471            1.000
      frambuesas       0.333             0.133            1.000

  Two separate faults, and neither is the one that was being looked for.
  **The berries are invisible to the entity probe** outside a heap - which
  is what the arrangement wording is for, and it is now shipped. **The apple
  loses half its valid clips between the entity probe and the conjunction**,
  which is the state wording adopted last cycle: "apples on a tree with
  their skin on" scored 0.958 on the pile that chose it and a single apple
  on a cutting board is not on a tree. That is the next calibration, on its
  own piles.
* **The apple state, and a hypothesis that did not survive its own
  measurement** (runs 34162044863, 34162048979 and 34162945046 - three
  independent apple sets, thirty-three fresh queries, no clip and no query
  reused). The presentation run put ``manzana`` at entity recall 0.800 and
  conjunction recall 0.400, and the obvious reading was that the state
  prompt encodes a *location*: "apples on a tree with their skin on", and a
  single apple on a board is not on a tree. Eight formulations were written
  to test that, none of whose positives names a tree, a plate, a table, a
  basket, a kitchen or a board:

      formulation                     precision  recall  state-blamed
      shipped                            1.000    0.472       13
      no orchard                         1.000    0.444       14
      visible skin                       1.000    0.306       19
      unpeeled                           1.000    0.389       16
      natural peel                       1.000    0.417       15
      all three skin wordings            1.000    0.472       11
      skin wordings, state negatives     0.880    0.611        4
      visible skin, state negatives      1.000    0.333       16

  **Every rewording of the positives is worse, and deleting the orchard
  clause is the second worst of them.** The location was not the cost. Only
  the variant that replaced the *negatives* recovers recall, and it does so
  at precision 0.880 with two peeled apples and one juice accepted - the
  three things the brief names as must-be-zero - so it was refused on those
  grounds rather than on its total.

  The held-out apple set agreed and said why. Fifty-four clips, precision
  **1.000**, recall 0.300, every one of the twenty-four invalid clips
  rejected: no orange, no dessert, no peeled apple. Of the twenty-one valid
  clips it lost, **fourteen name "pale wet apple flesh being cut" as the
  closest distractor** - six of six apples on a board, four of five wedges
  with the peel still on the edge. Both are presentations a ``con piel``
  beat must accept, and the mechanism is legible: a wedge does have pale
  flesh, and a whole apple beside a knife looks like an apple about to be
  cut.

  So one prompt was rewritten to name what a peeled apple actually has -
  that the pale surface is the *whole fruit* - the positives were left
  exactly as they were, and it was validated on a third apple set with the
  accept rule fixed before the run. **It lost.** Board recovers 0/6 to 1/6
  and the hand loses 3/6 to 1/6; recall 0.367 to 0.333 at the same
  precision. Whatever the "state negatives" variant bought on the
  calibration pile came from changing the positives and all three negatives
  together, and does not survive being isolated to the one prompt two
  measurements had blamed.

  **Nothing was applied.** The apple ships the wording it already had, and
  the honest state of it is three numbers on three sets: precision 1.000,
  1.000, 0.917 and recall 0.472, 0.300, 0.367. The one blemish is new and
  is *not* the state layer: on the third set the entity probe accepted one
  orange in six and the conjunction let it through, which is the first
  apple/orange leak measured since the identification probe was built. The
  state probe is doing its job on the invalid side throughout - on that
  same set it rejected five of six peeled apples and three of three
  desserts that the entity probe had waved past.

  What this cycle actually establishes is that the apple's recall is a
  **state-probe** cost (fifteen to eighteen of every twenty lost clips),
  that it concentrates almost entirely in one presentation - an apple on a
  board is 0/6 in all three sets - and that neither rewording the positives
  nor replacing the blamed negative fixes it. That is a real limit and it
  is written down rather than tuned around: the remaining lever is the
  verifier, and the verifier benchmark already says the two ViT-L/14
  builds score identically and no other candidate loads.

* **The test reel, run 34165114277: every gate passed and the repair pass
  was never needed.** Forty-seven seconds, sixteen shots from sixteen
  distinct sources, five items each with a reason, in test mode. All
  twenty-one checks pass. The seven grounding counters are all zero -
  ``wrong_food``, ``wrong_state``, ``wrong_context``,
  ``distractor_dominance``, ``image_fallback_shot_count``,
  ``ungrounded_fallback_count``, ``repair_rounds_used`` - with
  ``frozen_tail_duration`` at 0.00s and ``entity_grounding_pass_percentage``
  at 100% over five checked beats.

  **The prediction from the held-out numbers was wrong, and it is worth
  saying why.** Conjunction recall of 0.37 on the apple and 0.133 on the
  raspberry said those beats would burn their three repair rounds and reach
  the image fallback. They used **zero rounds**. The held-out piles are
  searched for awkward presentations on purpose - apples in market boxes,
  raspberries in a glass jar, strawberries on linen - and a beat does not
  search for those. It searches ``state_repair_queries`` and its own food,
  and it needs two clips out of a ranked shortlist rather than six out of
  six. A recall figure measured on hostile piles is a lower bound on what a
  beat experiences, not an estimate of it.

  **The manzana beat is the whole layer working, live.** It rejected six
  candidates before it accepted one: three **oranges** (entity, 0.00),
  a **tomato** (entity and dominant subject, 0.333), a **glass of orange
  juice** (entity and state, 0.333) and one clip on state alone, and then
  took ``pexels:5615187`` + ``pexels:33500303`` at 1.00 on all four probes.
  An orange under "la manzana con piel" is the failure this entire layer was
  built for, and it was refused three times in one forty-second render.

  One honest wrinkle: ``pexels:37239365`` was **accepted** as a manzana
  source in run 34164252796 and **rejected on state** in this one, as "pale
  wet apple flesh being cut". Same clip, opposite verdicts, three frames
  sampled each time - so that clip sits on the boundary and the sampling
  decides it. That is the same negative prompt the apple-state cycle
  blamed, behaving exactly as marginally in production as it did on the
  piles.

  Two things the report flags that grounding does not cover.
  ``visual_semantic_match_average`` is **0.217** with nineteen of
  twenty-three inspected clips at low relevance - that is MobileCLIP scoring
  a Spanish narration sentence against fruit footage, which is the metric
  the interior gates use and which this product deliberately does not gate
  on, but 0.217 is low enough to be worth a look rather than a shrug. And
  **Pixabay was unusable for want of a key**, so both renders drew on Pexels
  alone: a narrower pool than the configuration claims.

* **The raspberry candidate, decided at last** (runs 34113587132 and
  34155581648, two independent fresh four-berry sets). Adopt the
  arrangement wording, refuse the centre crop:

      set          shipped   +crop   arrangement   arrangement+crop
      third        0.750     0.750     0.792           0.792
      fourth       0.583     0.500     0.667           0.542

  On the fourth set raspberry recall goes 0.500 -> 0.667 and strawberry
  precision 0.8 -> 1.000, so it improves the raspberry without creating
  berry confusion, which was the condition. The crop won on the development
  pile and lost on both fresh ones; that is what a development pile is for
  and why it does not get to decide.
* **The CTA may not play over a frozen frame, and the gap is between the
  beats rather than after them.** The editor holds the last frame when the
  picture is shorter than the narration: run 34093462658 held it for 1.7
  seconds, across the whole call to action. Stretching the final beat to
  `narration + TAIL_SECONDS` fixed a third of it and run 34100918235 still
  froze for 1.52s, because a beat's `scene_timings` span covers only its own
  spoken chunks - the pause that follows it belongs to no beat at all, and a
  shot plan summed from the spans is short by *every pause in the reel*. Each
  beat's picture now runs to the **next beat's first word**, and the last one
  to the end. `frozen_tail_duration` is measured and gated at 0.2s.
* **The reel is spelled in correct Spanish.** ración, azúcar, síguenos,
  última: Kokoro is handed the script verbatim and a Spanish G2P front end
  does not read "racion" as "ración". `safety._flat` folds accents, because a
  medical check that stops matching the moment a word is spelled properly is
  not a check - only the *matching* is accentless, never the spoken text. The
  provider queries stay English, and a test enforces both halves.
* **A frame is labelled by the beat it lands in.** `inspect_reel_frames.py`
  mapped a sampled timestamp to the *first* beat of that kind, so a frame of
  the manzana line was reported as the fresas line and sent a reviewer looking
  for the wrong defect. It now maps the timestamp against each beat's own
  span, samples every item beat rather than two of them, and prints the
  required food, the source, the score and the verdict.
* **A vertical frame is not a small landscape one.** Captions at 68px with
  24-character lines, 430px clear of the bottom where Instagram, TikTok and
  Shorts draw their own furniture; one fixed ExtraBold title across the top
  for the whole reel, with a single accent word. Both ride in the same .ass
  file so libass draws them in one pass. Two bugs there were invisible to
  every check that read the file and obvious in the first rendered frame: the
  title's alignment byte is field **18**, not 19 - writing 8 into field 19
  sets MarginL and leaves the title at the bottom of the screen - and 42
  character lines sized for a 1920px frame run off both edges of a 1080px
  one.

* **Blur cannot be gated on any single-frame focus statistic, and the label
  set is what proved it.** ``window_sharpness`` was the first candidate and
  it cannot carry a floor: a pin-sharp lime window measures 0.000 while a
  blurred apple one measures 0.007. Four local measures were then computed
  on the same 92 windows - ``strong_edge_fraction``, high-percentile local
  gradient energy, contrast-normalised edge energy, and Laplacian variance -
  at 224x224 and at 480x270, because 224x224 squashes a 16:9 frame and is
  unsuitable for focus gating whatever else is true.

  On **13** labels ``laplacian_variance@480x270`` looked like the answer:
  3 of 3 held out, an 8.2x margin, a threshold at 13.77. On **34** labels
  the separation collapses. WATCHABLE runs **0.63 to 180.83** and
  UNWATCHABLE, excluding the held-out clip, runs **2.60 to 25.61** - eight
  watchable windows sit below two unwatchable ones. The sweep has no row
  that works: at 13.77 it catches four of six blurred windows and loses two
  of twenty-three watchable ones; at 26 it catches all six and loses eight.

  One clip settles the mechanism rather than the arithmetic. ``pexels:8212402``
  is green apples falling through water on black - same camera, same
  lighting, same focus - and its three windows are all sharp, all WATCHABLE,
  and score **0.63, 18.20 and 29.35**. The measure tracks how much of the
  frame the subject fills on a plain field. It is not measuring focus.

  **Nothing was shipped.** ``choose_window`` ranks on grounding first and
  quality as a tiebreak, exactly as it did, and a test asserts that no
  Laplacian appears in it. The remaining lever is a measure that is not a
  single-frame statistic at all; the labels are in
  ``data/calibration/window_readability_labels.json`` for whatever asks next.
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
* **Presence could not be measured; displacement could.** Three calibration
  runs (`vidfactory entity-check`, or the `calibrate-entities` task on the
  video workflow) decided the shape of this check, and two of them decided it
  against the obvious design. Best-positive against best-competitor scored
  sixty clips containing their own object at a median of **0.049** and sixty
  controls at **0.373** - inverted, because a broad prompt beats a specific
  one on CLIP similarity against almost any photograph, which is the same
  generality bias `_clip_semantic` documents. Scoring it scale-free fixed the
  direction and produced **0.708 against 0.737**: chance. The reason is not
  the prompts. A living room photograph contains a wall, a floor, a window, a
  sofa and a lamp at once, so "is the object present" is true of nearly all
  interior footage and separates nothing; only mirror and storage separated,
  because those are the two things a living room can actually lack. So the
  question is now **displacement**: how far the best distractor beats the best
  description of the object. The threshold is read off a sweep - at 0.20 it
  culls 8% of good footage and 5% of the control - and the honest reading of
  that table is that MobileCLIP-S0 can see a frame something else plainly
  owns and cannot do better. That is the failure that mattered, and all this
  claims to catch - and run 35 showed the limit is real, passing a close-up of
  ornate patterned decoration under "paint the trim the same colour as the
  walls" at `entity_grounding_failure_count = 0`, because a painted ornamental
  surface genuinely is a painted surface. The distractor list is where an
  observed failure goes; it is not a substitute for looking at the frames.

  Three prompts were added for that failure, and
  ``entity-check --probe-query ... --without ...`` measured what they do by
  scoring the same frames twice. On six real clips from an ornate-pattern
  search: **3 of 6 rejected with them, 0 of 6 without**, median 0.428 against
  1.000. So the failure class is now visible where it was invisible. But the
  control matters as much: on six clips from a plain "painted wall trim"
  search they reject **2 of 6** as well. They are aggressive, not selective.

  What saves that in practice is that the pipeline does not ship raw search
  results - run 38's eighteen ``wall_finish`` shots, chosen through the full
  ranking, sat at a minimum of 0.465 against a 0.20 cut and none were
  rejected. Read all three numbers together before touching this list: a
  distractor that catches a failure on a hostile search and costs nothing on
  selected footage is worth having, and the second half of that sentence is
  the half that needs re-checking every time one is added.
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
  good footage. Anything a shot of the object legitimately also contains -
  "a close-up of furniture" for a rug under a sofa - is not a distractor; it
  is a false positive waiting to happen.
* **Presence is a property of an object; an instruction is a property of a
  scene.** Run 44 reported `entity_grounding_failure_count = 0` and
  `entity_grounding_pass_percentage = 100%` over 93 grounded shots, and
  shipped a dragonfly sitting on a windowpane and a kitchen faucet under "do
  not block the window", and metallic ribbon strips, flowers beside a wall and
  ornate carved decoration under "paint the trim the same colour as the
  walls". Not one of those is a scoring error: every frame contains its
  object and nothing displaces it, which is the only question `entities.py`
  asks. The advice is not "show me a window" - it is *keep tall furniture away
  from the glass*, and only a room, a window and the relationship between them
  can demonstrate that.

  `instructions.py` states the whole claim in four parts - the subject
  `entities.py` already requires, the scene context, the relationship, and the
  scenes that satisfy the subject while failing the advice. Context and
  relationship are scored together as one set of positive prompts, because two
  independent CLIP margins multiply their false positive rates. The verdict is
  the same margin, and the reason it can work where the bare-noun probe
  measured chance is that **both sides are now equally specific**: "a dragonfly
  resting on a windowpane" against "a sofa placed clear of a bright living room
  window" gives the generality bias no generality gap to exploit.
  Whether MobileCLIP-S0 can see this is a measurement, not an argument, and
  it was made three times. `vidfactory instruction-check` (the
  `instruction-check` task on the video workflow) scores each claim's own
  searches against the searches that reproduce the run 44 failures.

  **MobileCLIP-S0 cannot** (runs 45, 46): over 48 valid clips and 72 from the
  failure searches it keeps 96% of the valid ones and rejects **1%** of the
  failures, with no crossing point anywhere in the sweep from 0.05 to 0.60 -
  past 0.30 it culls the valid side faster. The raw margins say it is not the
  aggregation: on ribbon and ornate-pattern footage the model *does* rank a
  forbidden prompt first on almost every clip, but at +0.001 to +0.05, and
  valid painted-wall footage produces the same margins. Median margins: valid
  +0.012, ribbons +0.008, ornate +0.013.

  **CLIP ViT-L/14 can** (runs 49, 50). On the two classes run 44 actually
  shipped, run 49 **keeps 24 of 24 valid clips and rejects 25 of 36
  failures**: the dragonfly 6/6, the kitchen faucet 4/6, the ribbons 5/6,
  flowers on a wall 6/6, ornate carving 3/6 - and in every one of those the
  closest forbidden prompt is the one naming that exact scene. Run 50 across
  all four claims: **keeps 48 of 48 valid clips and rejects 35 of 72
  failures**, with **zero valid footage culled at every cut in the sweep**,
  from 33% of the failures at 0.05 to 61% at 0.60. The backend was the limit,
  not the question.

  The weak claim is `layered_lighting` at 5 of 18, and it is weak for a
  reason worth keeping in mind rather than papering over: "at least three
  light sources" is a claim about *how many*, a lit lamp close-up genuinely
  resembles a lit lamp in a room, and counting is not something a
  contrastive image-text model does. What the numbers do say is that the
  false-positive side is clean - nothing culled a valid clip at any cut in
  either run - which is the half that matters for a check that refuses a
  render.

  So this is a **two-model pipeline** and the second model is the point.
  MobileCLIP-S0 stays the broad ranker: it is what decodes hundreds of
  shortlist candidates and it is never asked about claims, because its answer
  was measured at one percent. `visual.claim_model` (ViT-L/14, 224px) runs on
  the **final shots and on shortlisted repair candidates only** - the frames
  that will be on screen - which is a few hundred forward passes rather than
  tens of thousands. Validation is a property of the backend, not a flag:
  `VALIDATED_CLAIM_BACKENDS` lists the models a verdict may come from, and any
  other model returns an *unchecked* grounding, which the report and the
  repair pass already read as "no verdict" rather than "passed". If the
  verifier does not load, claims go unmeasured and the render carries on,
  exactly like every other optional model here.

  `instruction_grounding_failure_count` is an **error**, additional to entity
  grounding and a replacement for nothing, and it splits by mode as entity
  grounding does - one tolerated in test, none in production. A failed shot is
  repaired by searching for the *relationship*; searching for the object is
  what returned the dragonfly. A replacement must now improve the semantic
  score **and** contain the object **and** demonstrate the claim.

  One lead this did not need but which is worth keeping: the run 44 trim frame
  measures **colourfulness 104.2** against 27-36 for every other frame in that
  render, and "paint the trim the same colour as the walls" is advice *about*
  colour uniformity. A physical statistic can contradict that claim with no
  model involved at all.
* **The subject is the object named first, not the one named most.** "A rug
  too small to reach the sofa leaves the seating floating" names seating twice
  and the rug once. It is rug advice; the sofa is the landmark the rug is
  measured against.
* **An explanation is refused by its family, not by its wording.** Run 44's
  script QC returned zero contamination on four paragraphs that were all
  wrong. Removing the accidental match that caused one of them - "even" in the
  balance vocabulary, matched by "even though its footprint never changed" -
  fixes that sentence and not the problem: refuse it and the repair returns
  "a sofa that is too big for the room steals the floor around it", from the
  same mechanism family, sharing none of the first wording's words.
  `MECHANISM_PRINCIPLES` maps each mechanism in `title_alignment` to the
  principle it explains and `repair_text` skips the whole family when that
  principle is not the heading's, which is a fact about the repair rather than
  an inference from its output. Two of the four had no principle at all -
  focal-point layout and the window - and one had the wrong subject: a bare
  "window" was filed as window dressing, so "hanging the fabric high and wide
  leaves the glass itself uncovered" was formally curtain advice inside a
  curtain section. The aperture and what hangs on it are two subjects. Note
  which check catches that last one: **none of them**. It names the glass and
  the daylight, which are the window section's own words, so the concept check
  reads a normal comparison and the principle check exits before it looks for
  an intruder. Only refusing the family keeps it out.
* **A conditional is honest only about a choice the section offered.** Run 44
  closed "aim for at least three light sources per room" with "if you choose
  the wall finish, light on the walls makes the boundaries of the room
  visible", at `optional_example_leakage_count = 0` - because the leakage
  check had written that clause itself and its own repair satisfied it. The
  section offers a ceiling light, a lamp and a wall-mounted fitting; it never
  offers a wall finish. `VisualEntity.excluded` stops "wall-mounted" reading as
  the wall, and `find_false_conditioning` is the net under it, counted as
  leakage.
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
* **The premium ratio is mostly measuring caption vocabulary, not footage.**
  Measured, not guessed: over 293 real candidates, on the forty clips a ranker
  actually selects, **28 of 40 fail on the caption and 1 on the frames**. Of
  those 28, twenty-seven fail `interior_relevance_score >= 0.5` and **fifteen
  sit in the 0.35-0.49 band** - one interior word short. Renovation, dark and
  people-dominant, which dominate the *pool*, are already filtered out by
  ranking and appear zero times among the selected.

  The mechanism is arithmetic. `interior_relevance_score` starts at 0.25 and
  buys 0.15 per interior phrase, so a clip needs two of them to clear 0.5 -
  while an empty caption returns exactly 0.5 and passes. A Pexels slug reading
  "living room" scores 0.40 and is rejected; silence beats a short
  description. That is the shape of a false negative, not of a quality
  judgement, and it is why the ratio sits near 0.39 while the frames are fine.

  Fixed by putting the floor where "nothing is known" belongs:
  `interior_relevance_score` now starts at 0.5 and the caption moves it in
  whichever direction it carries evidence. One interior phrase is a short
  compatible caption and stays neutral; the second and later ones earn above
  it. Every negative keeps its full weight and two lists were widened, because
  raising a floor without that lets "construction site living room" through on
  the word "room" - `INTERIOR_INCOMPATIBLE_SIGNALS` for renovation and
  construction, and the off-topic list for footage that is not a photograph of
  a room at all. Deliberately not bare "abstract": decor captions say
  "abstract painting" about the wall art these videos exist to show.

  Note what this means for the *other* fixes: **searching and ranking cannot
  move this number much**, because the clips are already being selected on their pixels
  and their pixels already pass. Adding seven premium query phrases doubled
  the *pool's* ratio (0.135 to 0.270) and moved the *selected* ratio from
  0.250 to 0.275. Raising the frame-flag penalty from 60 to 110 moved it
  nothing, because frames were never the constraint. Both were worth keeping -
  the semantic average held at 0.686 to 0.691 and grounding was unchanged -
  and neither is a route to 0.60.
* **A ratio is not a diagnosis.** 0.39 could be thirty renovations or thirty
  dim rooms and those have opposite fixes, so every non-premium clip is
  labelled with the one thing most responsible - `premium_failure_reason`,
  reported as `final_shot_premium_failure_reasons`. And finding out should not
  cost a thirty minute render: `tools/premium_check.py` (the `premium-check`
  task) searches the provider as the pipeline does, inspects candidates on
  preview stills, and reports the premium ratio of what a ranker would
  actually select, before and after a proposed change, alongside the semantic
  average and grounding failures - because a ranking that buys premium footage
  by dropping relevance has made the video worse.
* **The grounding gate splits by mode.** Production tolerates no entity
  grounding failure; test tolerates one. The probe's own calibration puts its
  false positives near 8% and a ten minute video carries about 110 grounded
  shots, so an absolute gate refused runs 31, 37 and 38 over a single shot
  each while 32, 33 and 35 passed - which measures the probe more than the
  video. A tolerated failure is never silent: it is reported by name as a
  warning that says a production render would have been refused for it.
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
