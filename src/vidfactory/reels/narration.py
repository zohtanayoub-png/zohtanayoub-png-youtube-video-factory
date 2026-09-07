"""Narration for a reel: same words, different delivery per beat.

:class:`vidfactory.tts.NarrationBuilder` reads a twenty-five minute script at
one pace with one pause between every scene, which is right for long-form and
is exactly what makes a forty second reel sound like an audiobook. The words
are already short and direct; what was missing is that a person does not read
a list at the speed they deliver the line they want you to remember.

So the reel walks its own beats:

* the **hook** lands at normal pace and is followed by a real breath, because
  it is the sentence the whole video is spent earning
* the **answer** follows immediately - no pause worth the name, because the
  brief's complaint is five seconds of context before any value
* **items** run slightly quick, the way anyone reads a list
* a **retention** line is a beat of punctuation, not a sentence
* the **takeaway** slows down; it is the one thing to carry away
* the **CTA** sits just under normal pace and is not rushed

Nothing about the text changes here. This is delivery, and it is the half of
"sounds robotic" that no amount of rewriting fixes.
"""

from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any, Sequence

from ..ffmpeg_utils import concat_audio, make_silence, probe_media, run_ffmpeg
from ..logging_utils import get_logger
from ..tts import Narration, NarrationChunk, chunk_text, normalize_for_speech

log = get_logger("REELVOICE")

#: Speed multiplier per beat kind. Small numbers on purpose: past about eight
#: percent either way the voice starts sounding like a tape running fast
#: rather than a person making a point.
BEAT_SPEED: dict[str, float] = {
    "hook": 1.00,
    "answer": 1.02,
    "lead": 1.03,
    "item": 1.06,
    "retention": 1.00,
    "takeaway": 0.92,
    "cta": 0.97,
}

#: Silence after each beat. The hook gets a breath; the items barely stop.
BEAT_PAUSE: dict[str, float] = {
    "hook": 0.30,
    "answer": 0.16,
    "lead": 0.14,
    "item": 0.12,
    "retention": 0.16,
    "takeaway": 0.30,
    "cta": 0.0,
}

#: Between sentences inside one beat.
SENTENCE_PAUSE = 0.14


def _accepts_speed(engine: Any) -> bool:
    try:
        return "speed" in inspect.signature(engine.synthesize).parameters
    except (TypeError, ValueError):                        # pragma: no cover
        return False


def narrate(
    beats: Sequence[Any],
    engine: Any,
    workdir: str | Path,
    destination: str | Path,
    language: Any = None,
    loudness_lufs: float = -16.0,
    sample_rate: int = 48000,
    max_chunk_chars: int = 320,
) -> Narration:
    """Synthesize the beats into one track, varying pace and pause.

    Returns the same :class:`vidfactory.tts.Narration` the long-form builder
    does, so subtitles, shot planning and the report do not know or care which
    of the two produced it.
    """

    work = Path(workdir)
    work.mkdir(parents=True, exist_ok=True)
    target = Path(destination)

    per_chunk_speed = _accepts_speed(engine)
    if not per_chunk_speed:
        log.info(
            "%s does not vary speed per chunk; the reel will be read at one "
            "pace", getattr(engine, "name", "the engine"),
        )

    parts: list[Path] = []
    chunks: list[NarrationChunk] = []
    scene_timings: dict[str, tuple[float, float]] = {}
    silence_cache: dict[str, Path] = {}
    timeline = 0.0
    index = 0

    def silence(seconds: float) -> Path:
        key = f"{seconds:.3f}"
        if key not in silence_cache:
            path = work / f"pause_{key.replace('.', '_')}.wav"
            make_silence(path, seconds, sample_rate)
            silence_cache[key] = path
        return silence_cache[key]

    for position, beat in enumerate(beats):
        kind = str(getattr(beat, "kind", "item"))
        scene_id = f"beat-{position:02d}"
        text = normalize_for_speech(str(getattr(beat, "text", "") or ""), language)
        if not text:
            continue
        speed = BEAT_SPEED.get(kind, 1.0)
        started = timeline

        for body in chunk_text(text, max_chunk_chars):
            index += 1
            wav = work / f"chunk_{index:05d}.wav"
            try:
                if per_chunk_speed:
                    engine.synthesize(body, wav, speed=speed)
                else:
                    engine.synthesize(body, wav)
            except Exception as exc:
                # One failed chunk must not lose the narration; the same rule
                # the long-form builder follows.
                log.warning("TTS failed on a %s chunk (%s); inserting a pause", kind, exc)
                make_silence(wav, max(0.8, len(body.split()) / 3.0), sample_rate)

            duration = probe_media(wav).duration or 1.0
            chunks.append(
                NarrationChunk(
                    text=body, start=timeline, end=timeline + duration,
                    scene_id=scene_id, path=str(wav),
                )
            )
            parts.append(wav)
            timeline += duration

            if SENTENCE_PAUSE > 0:
                parts.append(silence(SENTENCE_PAUSE))
                timeline += SENTENCE_PAUSE

        scene_timings[scene_id] = (started, timeline)

        gap = BEAT_PAUSE.get(kind, 0.12)
        if gap > 0 and position < len(beats) - 1:
            parts.append(silence(gap))
            timeline += gap

    if not parts:
        raise RuntimeError("no narration was produced - the reel script was empty")

    merged = work / "narration_raw.wav"
    concat_audio(parts, merged, sample_rate)
    normalized = _normalize(merged, target, loudness_lufs, sample_rate)
    actual = probe_media(normalized).duration or timeline

    # Loudness normalisation shifts the length by milliseconds; rescale so the
    # captions stay on the words.
    if actual > 0 and timeline > 0 and abs(actual - timeline) > 0.05:
        factor = actual / timeline
        for chunk in chunks:
            chunk.start *= factor
            chunk.end *= factor
        scene_timings = {
            key: (start * factor, end * factor)
            for key, (start, end) in scene_timings.items()
        }

    log.info(
        "Narration: %.1fs across %d beats (%s / %s%s)",
        actual, len(scene_timings), getattr(engine, "name", "?"),
        getattr(engine, "voice", "?"),
        ", varied pace" if per_chunk_speed else ", one pace",
    )
    return Narration(
        audio_path=normalized,
        duration=actual,
        chunks=chunks,
        scene_timings=scene_timings,
        engine=getattr(engine, "name", "?"),
        voice=getattr(engine, "voice", "?"),
    )


def _normalize(
    source: Path, destination: Path, loudness_lufs: float, sample_rate: int
) -> Path:
    import shutil

    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        run_ffmpeg(
            ["-i", str(source), "-af",
             f"loudnorm=I={loudness_lufs}:TP=-1.5:LRA=11",
             "-ar", str(sample_rate), "-ac", "1", "-c:a", "pcm_s16le",
             str(destination)],
            description="loudness normalization",
        )
    except Exception as exc:                               # pragma: no cover
        log.warning("Loudness normalization failed (%s); using the raw track", exc)
        shutil.copy2(source, destination)
    return destination
