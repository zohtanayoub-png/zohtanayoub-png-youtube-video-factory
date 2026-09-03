# Setup guide

This guide assumes you have never written code. Everything happens in your web
browser, on the GitHub website. **You do not need to install anything and your
computer does not need to stay on.**

There are three parts:

1. **Required** - get a free Pexels key (5 minutes). Without this there is no footage.
2. **Optional** - add Pixabay as a second footage source (2 minutes).
3. **Optional** - let the system upload to YouTube by itself (20 minutes, one time).

---

## Part 1 - Required: the Pexels key

Pexels provides the stock video clips. The key is free and there is no card to enter.

1. Go to **https://www.pexels.com/api/**
2. Press **Get Started** and create an account (or log in).
3. It will ask what you are building. Any short honest answer is fine, for example
   *"Automated home decor videos for my YouTube channel."*
4. You will land on a page showing **Your API Key**. It is a long string of
   letters and numbers. Copy it.

Now put it into GitHub:

5. Open this repository on GitHub.
6. Click **Settings** (top right of the repository, not your profile settings).
7. In the left menu click **Secrets and variables**, then **Actions**.
8. Press the green **New repository secret** button.
9. In **Name** type exactly:

   ```
   PEXELS_API_KEY
   ```

10. In **Secret** paste the key you copied.
11. Press **Add secret**.

You are done with the required part.

> **Never** paste the key into `config.yaml`, into a file, or into a message.
> Secrets only ever go into that Secrets page.

---

## Part 2 - Optional: Pixabay as a second source

More sources means more variety and fewer repeated clips.

1. Go to **https://pixabay.com/api/docs/**
2. Create a free account and log in. Your key is shown on that page.
3. Back in GitHub: **Settings -> Secrets and variables -> Actions ->
   New repository secret**.
4. Name: `PIXABAY_API_KEY`. Value: your key. **Add secret**.

Nothing else to change - `config.yaml` already has `sources.pixabay: true`, and
the system simply skips a source when its key is missing.

---

## Part 3 - Making your first video

1. Click the **Actions** tab at the top of the repository.
2. If GitHub shows a banner asking you to enable workflows, press the button to
   enable them.
3. In the left-hand list click **Generate Video**.
4. On the right press **Run workflow**. A small form appears.
5. Either type a topic, for example:

   ```
   25 Small Living Room Ideas That Make Any Space Look Bigger
   ```

   or leave it **empty**, in which case the system invents a fresh topic that it
   has not covered before.
6. Press the green **Run workflow** button.
7. Refresh the page. A run appears with a yellow dot. It is working.
8. A 20 minute video usually takes **30 to 60 minutes**. You can close your
   browser and turn your computer off.
9. When it shows a green tick, click the run, scroll to the bottom to
   **Artifacts**, and download **video-run-...**. It is a zip containing your
   MP4, the subtitles, the script and the metadata.

If the run shows a red cross, open it and read the red step. The most common
cause is a missing or mistyped `PEXELS_API_KEY`.

---

## Part 4 - Optional: automatic videos on a schedule (autopilot)

Autopilot is deliberately protected by **two** switches, so it can never start
by accident.

**Switch 1 - the configuration file**

1. In the repository, click `config.yaml`.
2. Click the pencil icon to edit.
3. Find:

   ```yaml
   autopilot:
     enabled: false
     videos_per_week: 3
   ```

4. Change `false` to `true`.
5. Scroll down and press **Commit changes**.

**Switch 2 - the repository variable**

1. **Settings -> Secrets and variables -> Actions**.
2. Click the **Variables** tab (next to Secrets).
3. **New repository variable**.
4. Name: `AUTOPILOT`. Value: `true`. **Add variable**.

Autopilot now runs on **Monday, Wednesday and Friday at 14:00 UTC**.

`videos_per_week` is a real limit, not a note. Before each scheduled run,
autopilot counts how many videos were made in the last seven days and skips the
run if the limit has already been reached. So if you set `videos_per_week: 1`,
only the Monday run produces a video and the other two skip themselves. Set it
to `0` to remove the limit entirely.

To change the days, edit `.github/workflows/autopilot.yml` and change this line:

```yaml
    - cron: "0 14 * * 1,3,5"
```

The five numbers are: minute, hour, day-of-month, month, day-of-week
(1 = Monday). All times are UTC.

To stop autopilot, set the `AUTOPILOT` variable to `false`. That is the fastest
switch and it needs no code change.

---

## Part 5 - Optional: automatic YouTube uploads

This is the only part that needs about twenty minutes and a program run **once**
on your own computer. After that it is fully automatic forever.

### 5a. Create Google credentials

1. Go to **https://console.cloud.google.com/**
2. Top of the page, press the project dropdown, then **New Project**.
   Name it anything, e.g. `home-decor-uploader`. Press **Create**.
3. Make sure your new project is selected.
4. In the search bar type **YouTube Data API v3**, open it, press **Enable**.
5. In the left menu open **APIs & Services -> OAuth consent screen**.
   * User type: **External**. Press **Create**.
   * App name: anything. User support email: yours. Developer email: yours.
   * Press **Save and Continue** through the next screens.
   * On the **Test users** step press **Add users** and add your own Google
     account (the one that owns the YouTube channel). This matters.
   * Press **Save and Continue**, then **Back to Dashboard**.
6. Left menu: **APIs & Services -> Credentials**.
   * Press **Create Credentials -> OAuth client ID**.
   * Application type: **Desktop app**. Name: anything. Press **Create**.
   * Press **Download JSON**. Save the file as `client_secret.json` somewhere
     you can find it.

### 5b. Turn that into a refresh token (once, on your computer)

You need Python installed (https://www.python.org/downloads/ - during the
Windows installer, tick **Add Python to PATH**).

Download this repository as a zip (green **Code** button -> **Download ZIP**),
unzip it, then open a terminal in that folder and run:

```bash
python -m pip install -r requirements.txt
python -m pip install -r requirements-youtube.txt
python -m pip install -e .
python -m vidfactory.youtube_upload --authorize /full/path/to/client_secret.json
```

A browser window opens. Sign in with the Google account that owns the channel,
and accept the warning about the app being unverified (it is your own app).

The terminal then prints three values. Keep that window open.

### 5c. Put them into GitHub Secrets

Add three more secrets exactly as in Part 1
(**Settings -> Secrets and variables -> Actions -> New repository secret**):

| Name | Value |
|---|---|
| `YOUTUBE_CLIENT_ID` | the client id that was printed |
| `YOUTUBE_CLIENT_SECRET` | the client secret that was printed |
| `YOUTUBE_REFRESH_TOKEN` | the refresh token that was printed |

Then **delete `client_secret.json` from your computer** and never commit it.

### 5d. Turn uploading on

Two ways:

* **Per run:** on the *Generate Video* form, set `upload_to_youtube` to `true`
  and choose the privacy level.
* **Always:** edit `config.yaml` and set

  ```yaml
  youtube:
    upload_enabled: true
    privacy_status: private
  ```

Start with `private`. Watch a video yourself. Move to `unlisted`, then `public`
only when you are happy with the output.

> If an upload ever fails, the video is still produced and still attached to the
> run as an artifact. An upload problem never destroys a render.

---

## Changing how the videos look and sound

Edit `config.yaml` on the GitHub website (click the file, then the pencil).

| I want... | Change this |
|---|---|
| longer or shorter videos | `video.duration_minutes` |
| a different voice | `tts.voice` |
| slower narration | `tts.speed` (try `0.95`) |
| subtitles printed on the picture | `subtitles.burn_in: true` |
| soft fades between shots | `video.transition: crossfade` |
| completely still shots | `video.motion: none` |
| faster renders, slightly bigger files | `video.preset: superfast` |
| better quality, slower renders | `video.preset: medium` and `video.crf: 18` |

Voices you can use out of the box:

* `en_US-hfc_female-medium` - warm, clear American female (default)
* `en_US-amy-medium` - lighter American female
* `en_US-lessac-medium` - neutral American female
* `en_US-kristin-medium` - conversational American female
* `en_US-ryan-medium` - American male
* `en_US-hfc_male-medium` - deeper American male

---

## Using your own footage

If you own footage (or have permission to use it):

1. Put `.mp4` files into `assets/local_clips/`.
2. Name them descriptively, e.g. `cozy-living-room-curtains.mp4` - the filename
   is what the system searches.
3. In `config.yaml` set `sources.local: true`.

They are then ranked alongside the stock clips. Landscape, at least 1280x720,
at least about five seconds.

---

## How the factory decides a clip is good enough

Before a clip is used, three real frames of it - near the start, the middle and
near the end - are decoded with FFmpeg and measured. That is what catches the
things a stock caption cannot tell you, because the caption is usually honest
and still useless: "modern living room interior" is a true description of a
floor plan of a modern living room, of a dog asleep in one, and of one where
the sofa is still wrapped in plastic from the delivery.

What the frames are checked for:

| Rejected or heavily penalised | How it is spotted |
|---|---|
| Floor plans, drawings, documents | bright, colourless, made of hard thin lines |
| Empty or unfurnished rooms | large flat areas, almost no edges, almost no colour |
| Dark, poorly lit rooms | the luminance distribution itself |
| Furniture under plastic sheeting | colourless drape with hard glints on the folds |
| Renovation and building sites | dusty, low colour, busy with hard edges |
| A person or pet as the subject | skin tones clustered in the middle of the frame |
| Anything that does not show the narration | frame-to-sentence matching |

There is also an optional AI vision model (CLIP, free and open source, runs on
the CPU, cached between runs) that scores the same frames against written
descriptions. It makes plastic covers, pets and room types much more reliable.
It is **not required** - if it cannot be downloaded the frames are still
inspected, and the report says which was used. To check:

```bash
python -m vidfactory visual-check
```

You do not have to do anything with this. It is on by default and looks after
itself.

---

## Optional: the local AI script model

The scripts are written by a built-in engine that needs no model and no
network. There is also an optional local AI model (Qwen2.5-1.5B, free and
open source, roughly a 1 GB download) that can rewrite the wording.

It is **off by default**, because downloading the engine it needs is currently
unreliable on GitHub's runners. To see whether it works for you:

```bash
python -m vidfactory llm-check
```

If that prints `[ok] local model works`, you can switch it on in
`config.yaml`:

```yaml
script:
  llm:
    enabled: true
```

If it fails, leave it off. The videos are produced exactly as before.

---

## Language and subtitles

Videos come out **in English** by default, narrated by a female American
voice. There is nothing to set up.

Want one in Spanish? On the *Generate Video* screen pick `language: Spanish`.
Everything else follows automatically - the voice, the script, the subtitles
and the metadata all change language on their own. **You do not need to touch
the voice**: leave the `voice` dropdown on `Automatic`.

| Language | Voice it picks | Sounds like |
|---|---|---|
| English | `en_US-hfc_female-medium` | female, American, warm |
| Spanish | `es_ES-sharvard-medium` | female, Castilian, warm |

Subtitles come out two ways and both are in the artifact:

| File | What it is for |
|---|---|
| `subtitles.srt` | upload to YouTube; clean text, no styling |
| `subtitles.ass` | the premium style, already burned into the video |

The finished video has the captions **burned into the picture** in the premium
style: two lines at most, short phrases, an occasional keyword in warm amber,
and a generous bottom margin so the player controls never cover them. Prefer
plain white captions? Choose `subtitle_style: clean`. Do not want them in the
picture at all? Choose `none` - the `.srt` is still produced.

> One thing that may surprise you: the **stock footage searches stay in
> English** even when the video is in Spanish. That is deliberate. Pexels is
> indexed in English and returns far better material for
> `floor to ceiling curtains living room` than for a translation of it.

---

## Frequently hit problems

**"No stock footage provider is usable"**
`PEXELS_API_KEY` is missing or misspelled. Check the Secrets page. The name must
be exactly `PEXELS_API_KEY`.

**The narration sounds robotic**
That is the eSpeak NG fallback, which means the Piper voice could not be
downloaded. Re-run the workflow; it is nearly always a temporary network
problem. The run log says which engine was used.

**The video repeats the same footage**
This should no longer happen: a Pexels video may be used only once per video,
and the run fails if that is broken. Check
`editorial_quality_report.json` in the artifact - `source_video_reuse_count`
should be `0`. If it is not, the log will say `FOOTAGE SHORTAGE` and name the
cause.

**The video is shorter than I asked for**
A topic only has so much genuinely distinct material. The system tells you in
the log, and it renumbers the title so it stays honest. Ask for a broader topic
or a shorter duration.

**The run failed at "Generate the video"**
Open the step and read the last red lines. The message names the stage.

**I want to stop everything right now**
Set the `AUTOPILOT` variable to `false` and set `youtube.upload_enabled: false`
in `config.yaml`.

---

## Security notes

* API keys and OAuth credentials live **only** in GitHub Secrets. They are never
  written into the repository and the logger redacts anything that looks like a
  key before it can reach a log.
* The workflows that can see secrets are only triggered manually
  (`workflow_dispatch`) or on a schedule. They are **never** triggered by a pull
  request, so an outside contributor cannot reach your keys.
* The test workflow, which does run on pull requests, is given no secrets at all
  and only read permission.
* Workflow inputs are passed to the program through environment variables rather
  than pasted into a shell command, so a topic cannot inject commands.
* `.gitignore` blocks `.env`, `client_secret*.json`, tokens and all video files.

---

## AYOUB - DO ONLY THESE STEPS

1. Open **https://www.pexels.com/api/**, sign up, copy your API key.
2. In this repository: **Settings -> Secrets and variables -> Actions ->
   New repository secret**. Name `PEXELS_API_KEY`, paste the key, **Add secret**.
3. Open the **Actions** tab and enable workflows if GitHub asks you to.
4. Click **Generate Video**, press **Run workflow**, then the green
   **Run workflow** button. Change nothing else.
5. Wait 30-60 minutes. Your computer can be off.
6. Open the finished run, scroll to **Artifacts**, download **video-run-...**,
   and unzip it. `final_video.mp4` is your video.

Everything else on this page is optional and can wait until you have watched
your first video.
