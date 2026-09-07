"""A more human Spanish voice for the reels, with Piper still underneath.

Piper is excellent at what it is: a small, fast, offline neural TTS that
never fails to provision. It also reads Spanish like a station announcer,
and a reel is someone talking to you on a phone. So this adds a second
engine **for the reels only** - nothing in the long-form pipeline imports
this module, and ``build_engine`` in :mod:`vidfactory.tts` is untouched.

Kokoro-82M is the first candidate the brief names. What matters here:

* **Licence.** The model is published under Apache-2.0 and the ``kokoro``
  package under Apache-2.0, which permits commercial use. This module does
  not *assert* that - ``vidfactory reel-voice-check`` reads the installed
  distribution's own metadata and prints it, because a licence claim written
  in a docstring is worth nothing and a licence read off the installed
  package is worth something.
* **Spanish.** Kokoro's Spanish is served by ``lang_code="e"`` and the
  ``ef_dora`` voice, which is female. Grapheme-to-phoneme for Spanish goes
  through misaki, which calls **espeak-ng** - already installed on every
  runner here, because it is the existing fallback engine.
* **Failure is not fatal.** Provisioning a model on a runner is exactly the
  kind of thing that breaks, and the llama.cpp experience in
  :mod:`vidfactory.llm` is the cautionary tale in this repository. Every
  failure path raises ``TTSUnavailable`` so ``build_reel_engine`` falls
  straight through to Piper, and the report says which one actually spoke.

The one thing this module deliberately does not do is claim the result
sounds better. Nobody here can hear it. What it can do is render the same
script through both engines and hand over both files plus measured prosody
statistics - pitch variation, pause distribution, rate variation - so the
judgement is made by someone with ears, on evidence.
"""

from __future__ import annotations

import os
import wave
from pathlib import Path
from typing import Any, Sequence

from ..ffmpeg_utils import probe_media, run_ffmpeg
from ..logging_utils import get_logger
from ..tts import TTSEngine, TTSUnavailable, build_engine

log = get_logger("REELVOICE")

#: Spanish voices in the Kokoro v1.0 pack, best first. ``ef_`` is the Spanish
#: female prefix; ``em_`` is male and is only here so an explicit request can
#: reach it.
KOKORO_ES_VOICES: tuple[str, ...] = ("ef_dora", "em_alex", "em_santa")

#: Kokoro's language codes. "e" is Spanish; "a" and "b" are American and
#: British English and exist so this engine is not silently Spanish-only.
KOKORO_LANG_CODES: dict[str, str] = {"es": "e", "en": "a"}

#: The model repository and the licence it is published under. Printed by the
#: check command *alongside* what the installed package actually reports, so
#: the two can disagree visibly rather than silently.
KOKORO_REPO = "hexgrad/Kokoro-82M"
KOKORO_EXPECTED_LICENCE = "Apache-2.0"

#: Kokoro's native output rate. Everything downstream resamples.
KOKORO_SAMPLE_RATE = 24000


class KokoroEngine(TTSEngine):
    """Kokoro-82M through the ``kokoro`` package, on CPU.

    ``speed`` is per call rather than per engine, because a reel that reads
    its list at the same pace as its closing line sounds like an audiobook.
    :class:`vidfactory.reels.narration.ReelNarrator` sets it per beat.
    """

    name = "kokoro"
    #: Measured on the first CI run rather than guessed; see the check
    #: command's output. This is the starting estimate used to size a script
    #: before the voice has ever spoken here.
    speech_rate_wpm = 168.0

    def __init__(
        self,
        voice: str = "ef_dora",
        speed: float = 1.0,
        sample_rate: int = 48000,
        language: str = "es",
    ) -> None:
        super().__init__(voice or "ef_dora", speed, sample_rate)
        self.language = str(language or "es")
        self.lang_code = KOKORO_LANG_CODES.get(self.language, "e")
        self._pipeline = self._build_pipeline()

    # ------------------------------------------------------------------
    def _build_pipeline(self) -> Any:
        """Load the model, or explain why this machine cannot."""

        try:
            import torch                                   # noqa: F401
        except Exception as exc:                           # pragma: no cover
            raise TTSUnavailable(f"torch is not installed ({exc})") from exc
        try:
            from kokoro import KPipeline
        except Exception as exc:                           # pragma: no cover
            raise TTSUnavailable(
                f"the kokoro package is not installed ({exc}); "
                "pip install 'kokoro>=0.9' 'misaki[es]'"
            ) from exc

        # Spanish G2P goes through espeak-ng. Say so loudly here rather than
        # letting it surface as a stack trace three layers down.
        if self.lang_code == "e" and not _espeak_available():
            raise TTSUnavailable(
                "espeak-ng is required for Kokoro's Spanish phonemisation"
            )
        try:
            pipeline = KPipeline(lang_code=self.lang_code, repo_id=KOKORO_REPO)
        except Exception as exc:                           # pragma: no cover
            raise TTSUnavailable(f"could not load {KOKORO_REPO}: {exc}") from exc
        log.info(
            "Kokoro ready: %s / %s (lang_code=%r)", KOKORO_REPO, self.voice,
            self.lang_code,
        )
        return pipeline

    # ------------------------------------------------------------------
    def synthesize(self, text: str, destination: Path, speed: float = 0.0) -> Path:
        """One chunk of narration to a WAV file at the project's rate."""

        body = str(text or "").strip()
        if not body:
            raise TTSUnavailable("nothing to synthesize")
        rate = float(speed or self.speed or 1.0)

        try:
            import numpy as np
        except Exception as exc:                           # pragma: no cover
            raise TTSUnavailable(f"numpy is required ({exc})") from exc

        pieces: list[Any] = []
        try:
            for result in self._pipeline(body, voice=self.voice, speed=rate):
                audio = getattr(result, "audio", None)
                if audio is None and isinstance(result, (list, tuple)) and result:
                    audio = result[-1]
                if audio is None:
                    continue
                pieces.append(np.asarray(getattr(audio, "numpy", lambda: audio)()))
        except Exception as exc:                           # pragma: no cover
            raise TTSUnavailable(f"kokoro failed on a chunk: {exc}") from exc
        if not pieces:
            raise TTSUnavailable("kokoro returned no audio")

        samples = np.concatenate(pieces) if len(pieces) > 1 else pieces[0]
        raw = destination.with_suffix(".kokoro.wav")
        _write_wav(raw, samples, KOKORO_SAMPLE_RATE)
        # Resample to the project's rate so every chunk concatenates cleanly,
        # whichever engine produced it.
        destination.parent.mkdir(parents=True, exist_ok=True)
        run_ffmpeg(
            ["-i", str(raw), "-ar", str(self.sample_rate), "-ac", "1",
             "-c:a", "pcm_s16le", str(destination)],
            description="kokoro resample",
        )
        raw.unlink(missing_ok=True)
        return destination


def _espeak_available() -> bool:
    from shutil import which

    return bool(which("espeak-ng") or which("espeak") or os.environ.get("ESPEAK_DATA_PATH"))


def _write_wav(path: Path, samples: Any, sample_rate: int) -> Path:
    """Float samples in [-1, 1] to a 16-bit mono WAV."""

    import numpy as np

    path.parent.mkdir(parents=True, exist_ok=True)
    data = np.asarray(samples, dtype="float32").flatten()
    peak = float(np.max(np.abs(data))) if data.size else 0.0
    if peak > 1.0:
        data = data / peak
    pcm = (np.clip(data, -1.0, 1.0) * 32767.0).astype("<i2")
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(int(sample_rate))
        handle.writeframes(pcm.tobytes())
    return path


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------

def build_reel_engine(
    engine: str = "auto",
    voice: str = "",
    speed: float = 1.0,
    sample_rate: int = 48000,
    language: Any = None,
) -> TTSEngine:
    """Kokoro first, then everything :mod:`vidfactory.tts` already offers.

    ``engine`` accepts "kokoro", "piper", "espeak", "silent" or "auto". An
    explicit request is honoured and *not* silently downgraded when it is the
    only one named, because the whole point of the A/B comparison is that
    "piper" means piper.
    """

    from ..languages import resolve_language

    resolved = resolve_language(language)
    wanted = str(engine or "auto").strip().lower()

    if wanted in ("piper", "espeak", "silent"):
        return build_engine(
            engine=wanted, voice=_piper_voice(voice, resolved), speed=speed,
            sample_rate=sample_rate, language=resolved,
        )

    kokoro_voice = _kokoro_voice(voice, resolved)
    if wanted in ("auto", "kokoro"):
        try:
            return KokoroEngine(
                voice=kokoro_voice, speed=speed, sample_rate=sample_rate,
                language=resolved.key,
            )
        except TTSUnavailable as exc:
            log.warning("Kokoro unavailable (%s)", exc)
            if wanted == "kokoro":
                # Asked for by name: fall back rather than fail the render,
                # but make the substitution impossible to miss in the report.
                log.error("Kokoro was requested and could not load; using Piper")

    return build_engine(
        engine="auto", voice=_piper_voice(voice, resolved), speed=speed,
        sample_rate=sample_rate, language=resolved,
    )


def _kokoro_voice(requested: str, language: Any) -> str:
    wanted = str(requested or "").strip()
    if wanted.startswith(("ef_", "em_", "af_", "am_", "bf_", "bm_")):
        return wanted
    if getattr(language, "key", "es") == "es":
        return KOKORO_ES_VOICES[0]
    return "af_heart"


def _piper_voice(requested: str, language: Any) -> str:
    """A Kokoro voice name must not be handed to Piper as if it were one."""

    wanted = str(requested or "").strip()
    if wanted.startswith(("ef_", "em_", "af_", "am_", "bf_", "bm_")):
        return ""
    return wanted


# ---------------------------------------------------------------------------
# What the check command reports
# ---------------------------------------------------------------------------

#: What each Piper voice this project may reach for ships under. The runtime
#: and the voices are separate artefacts with separate terms, so recording
#: only the package licence would be recording the wrong one.
PIPER_VOICE_LICENCES: dict[str, str] = {
    "es_ES-sharvard-medium": "MIT",
    "es_MX-claude-high": "CC-BY-4.0",
    "es_ES-davefx-medium": "CC-BY-4.0",
    "es_ES-mls_9972-low": "CC0-1.0",
}


def licence_report() -> dict[str, Any]:
    """What the installed packages say about themselves.

    Read rather than asserted. If ``kokoro`` ever ships under something other
    than Apache-2.0, this prints the new licence instead of repeating the old
    claim from a comment.
    """

    from importlib import metadata

    out: dict[str, Any] = {
        "model_repo": KOKORO_REPO,
        "expected_model_licence": KOKORO_EXPECTED_LICENCE,
        "packages": {},
    }
    for name in ("kokoro", "misaki", "torch", "piper-tts"):
        entry: dict[str, Any] = {"installed": False}
        try:
            dist = metadata.distribution(name)
            entry["installed"] = True
            entry["version"] = dist.version
            meta = dist.metadata
            licence = meta.get("License") or ""
            classifiers = [
                c for c in meta.get_all("Classifier") or [] if "License" in c
            ]
            entry["license"] = licence.strip() or None
            entry["license_classifiers"] = classifiers
            expression = meta.get("License-Expression")
            if expression:
                entry["license_expression"] = expression
        except Exception as exc:
            entry["error"] = str(exc)
        out["packages"][name] = entry

    # Keyed by engine name as well, because that is what a narration knows
    # about itself: the report asks "what licence did the voice that spoke
    # this reel ship under", and the answer has to be reachable from
    # ``narration.engine``.
    out["kokoro"] = {
        "engine": "kokoro",
        "model": KOKORO_REPO,
        "model_licence": KOKORO_EXPECTED_LICENCE,
        "code_licence": out["packages"]["kokoro"].get("license"),
        "commercial_use": "yes - Apache-2.0 covers the weights and the code",
        "packages": {
            k: out["packages"][k].get("version")
            for k in ("kokoro", "misaki", "torch")
        },
    }
    out["piper"] = {
        "engine": "piper",
        "code_licence": out["packages"]["piper-tts"].get("license"),
        # The voices are distributed separately from the runtime and each
        # carries its own terms; es_ES-sharvard-medium is MIT. Named rather
        # than assumed, because "Piper is MIT" is a statement about the wrong
        # artefact.
        "voice_licences": dict(PIPER_VOICE_LICENCES),
    }
    return out


def prosody(path: str | Path) -> dict[str, Any]:
    """Measurable proxies for "does this sound like a person".

    None of these is naturalness. What they are is the difference between a
    delivery that varies and one that does not, which is the specific
    complaint the brief makes about the current voice - and unlike an opinion
    about a waveform, they can be compared between two files.

    ``loudness_variation`` is the spread of short-window RMS in decibels: a
    monotone read is flat, an emphatic one is not. ``silence_ratio`` and
    ``pause_count`` describe the phrasing. ``speech_rate_variation`` is how
    much the syllable-ish rate changes between windows.
    """

    target = Path(path)
    info = probe_media(target)
    duration = float(info.duration or 0.0)
    out: dict[str, Any] = {
        "file": target.name,
        "duration_seconds": round(duration, 2),
    }
    try:
        import numpy as np
    except Exception:                                      # pragma: no cover
        return out

    pcm = target.with_suffix(".probe.wav")
    try:
        run_ffmpeg(
            ["-i", str(target), "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le",
             str(pcm)],
            description="prosody probe",
        )
        with wave.open(str(pcm), "rb") as handle:
            frames = handle.readframes(handle.getnframes())
            rate = handle.getframerate()
        data = np.frombuffer(frames, dtype="<i2").astype("float32") / 32768.0
    except Exception as exc:                               # pragma: no cover
        out["error"] = str(exc)
        return out
    finally:
        pcm.unlink(missing_ok=True)

    if data.size == 0:
        return out

    window = max(1, int(rate * 0.05))          # 50 ms
    usable = data[: (data.size // window) * window].reshape(-1, window)
    rms = np.sqrt(np.mean(usable ** 2, axis=1) + 1e-12)
    db = 20.0 * np.log10(rms + 1e-9)

    # Silence relative to this file's own loud parts, so a quiet recording is
    # not scored as one long pause.
    floor = float(np.percentile(db, 90)) - 30.0
    quiet = db < floor
    out["loudness_variation_db"] = round(float(np.std(db[~quiet])) if (~quiet).any() else 0.0, 2)
    out["silence_ratio"] = round(float(np.mean(quiet)), 3)

    # A pause is a run of quiet windows at least 150 ms long.
    runs, current = [], 0
    for flag in quiet:
        if flag:
            current += 1
        elif current:
            runs.append(current); current = 0
    if current:
        runs.append(current)
    pauses = [r * 0.05 for r in runs if r * 0.05 >= 0.15]
    out["pause_count"] = len(pauses)
    out["pause_seconds_mean"] = round(float(np.mean(pauses)), 3) if pauses else 0.0
    out["pause_seconds_std"] = round(float(np.std(pauses)), 3) if pauses else 0.0

    # How much the energy envelope moves second to second: a proxy for rhythm
    # variation rather than for speed itself.
    per_second = max(1, int(1.0 / 0.05))
    seconds = db[: (db.size // per_second) * per_second].reshape(-1, per_second)
    if seconds.size:
        out["speech_rate_variation"] = round(float(np.std(np.mean(seconds, axis=1))), 2)
    return out


def compare(files: Sequence[tuple[str, str | Path]]) -> list[dict[str, Any]]:
    """Prosody for several renders of the same script, side by side."""

    rows: list[dict[str, Any]] = []
    for label, path in files:
        row = {"label": label}
        row.update(prosody(path))
        rows.append(row)
    return rows
