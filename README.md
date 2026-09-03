# Home Decor YouTube Video Factory

An automatic, cloud-based factory that writes, narrates, edits and renders
**long-form home decor / interior design videos** for a US English audience -
and it runs entirely on **GitHub Actions**, so your own computer can be
switched off.

Every part of the production pipeline is **free and open source**. There is no
paid video API, no paid text-to-speech, no paid LLM at runtime and no paid
rendering service.

---

## What it produces

For every run you get:

| File | What it is |
|---|---|
| `final_video.mp4` | 1920x1080, 16:9, H.264 video with AAC narration audio |
| `subtitles.srt` | subtitle file, timed from the narration itself |
| `script.txt` | the original narration script |
| `metadata.json` | YouTube title, description, chapters, tags, summary |
| `video_sources.json` | every stock clip used, with attribution |
| `quality_report.json` | the ffprobe validation results |
| `editorial_quality_report.json` | footage repetition, relevance and diversity metrics |

The default target length is **20 minutes** and it is configurable.

**There is never any background music.** The audio track contains narration and
nothing else. This is enforced in code: setting `audio.music: true` makes the
program refuse to run.

---

## How it works

```
TOPIC  ->  TITLE  ->  ORIGINAL SCRIPT  ->  DOES EVERY PARAGRAPH EXPLAIN THE
   TITLE'S PROMISE?  ->  SCENE PLANNING  ->  VISUAL SEARCH QUERIES
   ->  SEARCH STOCK VIDEOS  ->  RANK ON METADATA (cheap)  ->  SHORTLIST
   ->  DECODE REAL FRAMES AND LOOK AT THEM  ->  RANK ON WHAT IS IN THEM
   ->  DOWNLOAD CLIPS  ->  RE-CHECK THEIR OWN FRAMES  ->  GENERATE NARRATION
   ->  MATCH CLIPS TO NARRATION  ->  EDIT VIDEO  ->  GENERATE SUBTITLES
   ->  RENDER 1080P MP4  ->  QUALITY CHECK  ->  YOUTUBE METADATA
   ->  SAVE  ->  OPTIONAL UPLOAD
```

One design decision is worth knowing about: **the narration is created before
the footage is chosen.** Once the narration exists, the exact length of every
sentence is known, so the visuals are cut to fit the words rather than the
words being stretched to fit the visuals. That is what stops a clip freezing on
screen for thirty seconds.

The second is that **clips are judged by their pixels, not by their captions.**
A stock caption saying "modern living room interior" is equally true of a floor
plan of one, a dog asleep in one, and one with the sofa still wrapped in
plastic from the delivery. So candidate footage has three real frames decoded
from it - the beginning, the middle and the end - and those frames are
measured. Nothing about that costs money: FFmpeg does the decoding, the
statistics are computed in-process, and the optional CLIP model is an
open-source ONNX export that runs on a CPU runner.

### The pieces

| Stage | Tool | Cost |
|---|---|---|
| Topic selection | built-in generator with similarity rejection | free |
| Script writing | curated knowledge base + variation engine (optional local LLM) | free |
| Narration | [Piper](https://github.com/OHF-Voice/piper1-gpl) neural TTS, eSpeak NG fallback | free |
| Footage | Pexels and Pixabay APIs | free |
| Frame inspection | FFmpeg decode + pixel statistics, optional CPU CLIP (ONNX) | free |
| Editing and rendering | FFmpeg | free |
| Subtitles | derived from the narration timeline (no speech recognition needed) | free |
| Compute | GitHub Actions | free tier |
| Upload | YouTube Data API v3 | free, optional |

---

## Getting started

Read **[SETUP.md](SETUP.md)**. It is written for someone who has never
programmed, and the short version is at the bottom of this file.

---

## Running it

### In the cloud (the normal way)

1. Open the **Actions** tab of this repository.
2. Choose **Generate Video** on the left.
3. Press **Run workflow**.
4. Fill in what you want (or leave everything as it is), press the green button.
5. When it finishes, download the artifact at the bottom of the run page.

Inputs you can set:

| Input | Default | Meaning |
|---|---|---|
| `topic` | empty | leave empty and the system picks a fresh topic itself |
| `duration_minutes` | `20` | target length |
| `voice` | `en_US-hfc_female-medium` | narration voice |
| `subtitles` | on | produce the `.srt` file |
| `burn_in_subtitles` | off | print the subtitles into the picture |
| `upload_to_youtube` | off | upload when finished |
| `privacy_status` | `private` | only used when uploading |

### Automatically, on a schedule

The **Autopilot** workflow can produce videos three times a week without you
doing anything. It is off by default and needs two switches turned on - see
SETUP.md. `autopilot.videos_per_week` is enforced: a scheduled run that would
exceed the weekly limit skips itself.

### On your own computer (optional)

```bash
python -m pip install -r requirements.txt
python -m pip install -e .

python -m vidfactory doctor                      # check the machine can render
python -m vidfactory topics --count 10           # preview generated topics
python -m vidfactory demo --duration 1           # short render, no API keys
python -m vidfactory generate --topic "25 Small Living Room Ideas" --duration 20
```

FFmpeg must be installed (`sudo apt install ffmpeg`, `brew install ffmpeg`, or
the Windows build from ffmpeg.org).

---

## Configuration

Everything lives in [`config.yaml`](config.yaml) and is safe to edit by hand.

```yaml
video:
  duration_minutes: 20
  resolution: 1920x1080
  fps: 30
  min_clip_seconds: 4
  max_clip_seconds: 8

audio:
  narration: true
  music: false          # permanently false - the program refuses to start otherwise

subtitles:
  enabled: true
  burn_in: false

autopilot:
  enabled: false
  videos_per_week: 3

youtube:
  upload_enabled: false
  privacy_status: private
```

---

## Repeating yourself is prevented

The system keeps a persistent history in `data/state/*.json`, which the
workflow commits back to the repository after every successful run:

* **Topics** - a new topic is compared against every previous title and
  rejected if it is too similar.
* **Clips** - every stock clip is recorded with the date it was used. Recently
  used clips are refused for a configurable cooldown (45 days by default), and
  unused clips always score higher than reused ones.
* **Files** - byte-identical downloads are detected and dropped, so the same
  footage served under two IDs is only used once.

No MP4 is ever committed to git; only the small JSON history files are.

---

## Quality control

Two independent gates. The technical one proves the file is a valid MP4; the
editorial one proves the video is actually watchable.

### Editorial

`editorial_quality_report.json` records, and the run **fails** on the first two:

* **no source video is used twice** - a Pexels video ID may appear once per
  video, and taking a second segment from the same source at a different
  timestamp counts as reuse
* **unique source ratio** of at least 0.95
* generic-query share, average clip score, creator / query / subject
  diversity, title-to-idea alignment, shot count and per-section coverage
* **`causal_promise_alignment_score`** - every item must *say*, in the words
  the viewer hears, how it produces the outcome the title promised. "Measure
  before buying, because returns are expensive" does not belong in a video
  called *...Make Your Space Look Bigger*; "measure, because oversized pieces
  eat visible floor area and make the room feel cramped" does. Paragraphs that
  fail are rewritten from the mechanism the idea already relies on, and
  replaced if that is not possible. `section_alignment_scores` records each
  one, and the run fails below 0.85.

### Visual (measured from real frames)

Also in `editorial_quality_report.json`:

* **`visual_semantic_match_average`** - how well the frames of each clip match
  the sentence being narrated
* **`low_relevance_clip_count`** - clips that barely match what they illustrate
* **`premium_visual_ratio`** - now requires the caption *and* the frames to
  agree; it was 0.912 for a video containing a floor plan and a
  plastic-wrapped sofa when captions were the only evidence
* **`empty_room_clip_count`**, **`plastic_covered_clip_count`**,
  **`floor_plan_clip_count`**, **`renovation_clip_count`**,
  **`people_dominant_clip_count`**, **`dark_clip_count`**
* **`visual_analysis_model`** and **`visual_analysis_frame_count`** - which
  backend produced the numbers, and how many frames it actually opened

Candidates whose frames disqualify them with high confidence are rejected;
medium confidence is a heavy ranking penalty. Ranking priority after
inspection is deliberately **relevance first**: semantic match (45) above
interior subject (30), visual quality (18), novelty (12) and technical quality
(8). A beautiful unrelated luxury interior loses to a plainer clip that
demonstrates the advice.

### Technical

After rendering, `ffprobe` checks the output and the workflow **fails loudly**
if any of these are wrong:

* the file exists and is a reasonable size
* there is a video stream and an audio stream
* the resolution is exactly 1920x1080
* the codecs are H.264 and AAC
* the video length matches the narration length
* subtitles were produced
* metadata was produced

---

## Tests

```bash
python -m pytest -q -m "not integration"   # fast unit tests
python -m pytest -q -m integration         # real short render with FFmpeg
python -m pytest -q                        # everything
```

The integration test renders a genuine ~40 second 1080p MP4 using synthetic
footage generated by FFmpeg, so it needs no API keys and no network access. It
exercises the same code path a real 20 minute run uses.

---

## Copyright and honesty

This produces **original narrated editorial videos**. The narration is written
by this project, not copied from articles or other channels. Stock footage is
used as supporting visuals under the Pexels and Pixabay licenses, its origin is
recorded in `video_sources.json`, and the description credits it. No ownership
of the stock footage is claimed and no watermarks are ever removed.

The pipeline does **not** scrape or download videos from TikTok, Instagram,
Pinterest, YouTube or any other creator's account.

---

## AYOUB - DO ONLY THESE STEPS

1. Go to **https://www.pexels.com/api/**, sign in, and copy your free API key.
2. In this repository open **Settings -> Secrets and variables -> Actions ->
   New repository secret**. Name it exactly `PEXELS_API_KEY`, paste the key,
   press **Add secret**.
3. Open the **Actions** tab. If you see a button asking to enable workflows,
   press it.
4. Click **Generate Video** in the left-hand list, then press
   **Run workflow**, then the green **Run workflow** button. Leave every box
   as it is.
5. Wait. It takes roughly 30 to 60 minutes for a 20 minute video.
6. When the run has a green tick, click it, scroll to the bottom, and download
   the **video-run-...** artifact. Your MP4 is inside.

That is everything. Nothing else is required, and your computer can be off
while it runs.

Optional extras, only when you want them, are in
**[SETUP.md](SETUP.md)**: a second footage source, automatic scheduling, and
automatic YouTube uploads.
