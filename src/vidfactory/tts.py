"""Local, free, open-source narration.

Engines, in preference order:

``piper``
    `Piper <https://github.com/OHF-Voice/piper1-gpl>`_ - a small ONNX neural
    TTS that runs fast on CPU and produces natural American English. Voice
    models are downloaded once from the public Hugging Face voice repository
    and cached (the GitHub Actions workflow caches that directory).

``espeak``
    eSpeak NG. Robotic but completely dependency-free and installable from
    every distro repository. Used when Piper cannot be prepared, so a runner
    without model access still produces a complete, audible video.

``silent``
    Correctly-timed silence. Only used by tests and as a last resort so the
    pipeline can still produce a valid, correctly-timed MP4.

No paid API is used, and no music is ever generated or mixed - the output
track contains narration only.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

from .ffmpeg_utils import concat_audio, make_silence, probe_media, run_ffmpeg
from .http import download_file
from .logging_utils import get_logger

log = get_logger("TTS")

CACHE_DIR = Path(os.environ.get("VIDFACTORY_CACHE", ".cache")) / "voices"
#: Override with VIDFACTORY_PIPER_VOICE_BASE to use a mirror.
VOICE_BASE = os.environ.get(
    "VIDFACTORY_PIPER_VOICE_BASE",
    "https://huggingface.co/rhasspy/piper-voices/resolve/main",
).rstrip("/")

#: Voices that ship as documented choices. Any other valid Piper voice name
#: also works - the repository path is derived from the name itself.
VOICE_PATHS: dict[str, str] = {
    # --- Spanish -------------------------------------------------------
    # sharvard is the female Castilian voice in the Piper catalogue and the
    # channel default. The others are fallbacks in order of how well they
    # substitute for it: a neutral Latin American female voice is a far better
    # failure mode for a Spanish channel than a male one or an English one.
    "es_ES-sharvard-medium": "es/es_ES/sharvard/medium",
    "es_MX-claude-high": "es/es_MX/claude/high",
    "es_ES-davefx-medium": "es/es_ES/davefx/medium",
    "es_ES-mls_9972-low": "es/es_ES/mls_9972/low",
    "es_ES-carlfm-x_low": "es/es_ES/carlfm/x_low",
    "es_MX-ald-medium": "es/es_MX/ald/medium",
    # --- English -------------------------------------------------------
    "en_US-hfc_female-medium": "en/en_US/hfc_female/medium",
    "en_US-amy-medium": "en/en_US/amy/medium",
    "en_US-lessac-medium": "en/en_US/lessac/medium",
    "en_US-lessac-high": "en/en_US/lessac/high",
    "en_US-libritts_r-medium": "en/en_US/libritts_r/medium",
    "en_US-ryan-medium": "en/en_US/ryan/medium",
    "en_US-hfc_male-medium": "en/en_US/hfc_male/medium",
    "en_US-kristin-medium": "en/en_US/kristin/medium",
    "en_US-kathleen-low": "en/en_US/kathleen/low",
}

_VOICE_NAME = re.compile(r"^(?P<family>[a-z]+)_(?P<region>[A-Za-z]+)-(?P<name>[^-]+)-(?P<quality>.+)$")


def voice_repository_path(voice: str) -> str | None:
    """Work out where a voice lives in the piper-voices repository.

    Known voices come from the table above; anything else is derived from the
    ``<lang>_<REGION>-<name>-<quality>`` naming convention, which is how Piper
    itself resolves voices. That means a new voice can be selected in
    ``config.yaml`` without any code change.
    """

    if voice in VOICE_PATHS:
        return VOICE_PATHS[voice]
    match = _VOICE_NAME.match(str(voice or ""))
    if not match:
        return None
    family = match.group("family")
    code = f"{family}_{match.group('region')}"
    return f"{family}/{code}/{match.group('name')}/{match.group('quality')}"


class TTSUnavailable(RuntimeError):
    """Raised when a specific TTS engine cannot be used."""


# ---------------------------------------------------------------------------
# Text normalization - what gets spoken is also what gets subtitled
# ---------------------------------------------------------------------------

_UNITS = {
    "cm": "centimeters",
    "mm": "millimeters",
    "kg": "kilograms",
    "lb": "pounds",
    "ft": "feet",
    "in": "inches",
}

_ABBREVIATIONS = {
    r"\be\.g\.\s*": "for example, ",
    r"\bi\.e\.\s*": "that is, ",
    r"\betc\.": "and so on",
    r"\bvs\.?\b": "versus",
    r"\bapprox\.": "approximately",
    r"\bTV\b": "T V",
    r"\bLED\b": "L E D",
    r"\bDIY\b": "D I Y",
    r"\bUS\b": "U S",
}


# ---------------------------------------------------------------------------
# Spanish
#
# Piper's Spanish voices read digits, but they read them the way a phonemizer
# does rather than the way a narrator does: "2,4" comes out as two separate
# numbers, "10 %" as "diez" followed by a pause, and "cm" as two letters. For
# long-form narration that is the difference between a voice you can listen to
# for twenty minutes and one you cannot, so the numbers are written out here
# before they ever reach the model.
# ---------------------------------------------------------------------------

_ES_UNITS: dict[str, str] = {
    "cm": "centímetros",
    "mm": "milímetros",
    "km": "kilómetros",
    "kg": "kilos",
    "m2": "metros cuadrados",
    "m²": "metros cuadrados",
    "m": "metros",
    "l": "litros",
    "h": "horas",
    "€": "euros",
    "K": "kelvin",
}

_ES_ABBREVIATIONS = {
    r"\bp\.\s?ej\.\s*": "por ejemplo, ",
    r"\betc\.": "etcétera",
    r"\baprox\.": "aproximadamente",
    r"\bTV\b": "tele",
    r"\bLED\b": "led",
    r"\bnº\s*": "número ",
    r"\bn\.º\s*": "número ",
    r"\bm²": " metros cuadrados",
    r"\bºC\b": " grados",
    r"\b1\.000\b": "mil",
}

_ES_UNITS_0_15 = (
    "cero", "uno", "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho",
    "nueve", "diez", "once", "doce", "trece", "catorce", "quince",
)
_ES_TENS = {
    2: "veinte", 3: "treinta", 4: "cuarenta", 5: "cincuenta",
    6: "sesenta", 7: "setenta", 8: "ochenta", 9: "noventa",
}
_ES_HUNDREDS = {
    1: "ciento", 2: "doscientos", 3: "trescientos", 4: "cuatrocientos",
    5: "quinientos", 6: "seiscientos", 7: "setecientos", 8: "ochocientos",
    9: "novecientos",
}
_ES_TEENS = {
    16: "dieciséis", 17: "diecisiete", 18: "dieciocho", 19: "diecinueve",
    21: "veintiuno", 22: "veintidós", 23: "veintitrés", 24: "veinticuatro",
    25: "veinticinco", 26: "veintiséis", 27: "veintisiete", 28: "veintiocho",
    29: "veintinueve",
}


def spanish_number(value: int) -> str:
    """Escribe un entero en palabras. Cubre de 0 a 999.999, que es de sobra
    para medidas, porcentajes y precios en un guion de decoración."""

    value = int(value)
    if value < 0:
        return "menos " + spanish_number(-value)
    if value <= 15:
        return _ES_UNITS_0_15[value]
    if value in _ES_TEENS:
        return _ES_TEENS[value]
    if value < 100:
        tens, ones = divmod(value, 10)
        base = _ES_TENS[tens]
        return base if ones == 0 else f"{base} y {_ES_UNITS_0_15[ones]}"
    if value == 100:
        return "cien"
    if value < 1000:
        hundreds, rest = divmod(value, 100)
        base = _ES_HUNDREDS[hundreds]
        return base if rest == 0 else f"{base} {spanish_number(rest)}"
    if value < 1_000_000:
        thousands, rest = divmod(value, 1000)
        base = "mil" if thousands == 1 else f"{spanish_number(thousands)} mil"
        return base if rest == 0 else f"{base} {spanish_number(rest)}"
    return str(value)


def _es_spoken_number(match: "re.Match[str]") -> str:
    """Un número con coma decimal se dice "dos coma cuatro"."""

    whole, decimals = match.group(1), match.group(2)
    spoken = spanish_number(int(whole))
    if decimals:
        digits = " ".join(spanish_number(int(d)) for d in decimals)
        spoken = f"{spoken} coma {digits}"
    return spoken


def normalize_spanish(text: str) -> str:
    """Deja el texto listo para que una voz española lo lea con naturalidad."""

    text = re.sub(r"\s+", " ", str(text or "")).strip()
    for pattern, replacement in _ES_ABBREVIATIONS.items():
        text = re.sub(pattern, replacement, text)

    # Porcentajes antes que nada: "10 %" y "10%" se dicen igual.
    text = re.sub(
        r"(\d+)(?:,(\d+))?\s*%",
        lambda m: _es_spoken_number(m) + " por ciento",
        text,
    )
    # Unidades pegadas a un número: "60 cm", "2,4 m", "90 €".
    for unit, spoken in _ES_UNITS.items():
        text = re.sub(
            # No absorbe el punto: "60 cm." termina una frase, y comerse ese
            # punto deja a la voz sin la pausa que separa dos ideas.
            rf"(\d+)(?:,(\d+))?\s*{re.escape(unit)}(?![a-zA-ZáéíóúñÁÉÍÓÚÑ0-9])",
            lambda m, spoken=spoken: f"{_es_spoken_number(m)} {spoken}",
            text,
        )
    # Rangos: "de 8 a 15" ya se lee bien una vez los números son palabras.
    text = re.sub(r"(\d+),(\d+)", _es_spoken_number, text)
    text = re.sub(r"\b(\d+)\b", lambda m: spanish_number(int(m.group(1))), text)

    text = text.replace("&", " y ")
    text = re.sub(r"[\"“”„«»]", "", text)
    text = re.sub(r"\s*[—–]\s*", ", ", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    return text


def normalize_for_speech(text: str, language: Any = None) -> str:
    """Make text safe and natural to speak, and keep subtitles matching it."""

    from .languages import resolve_language

    if not resolve_language(language).is_english:
        return normalize_spanish(text)

    text = re.sub(r"\s+", " ", str(text or "")).strip()
    for pattern, replacement in _ABBREVIATIONS.items():
        text = re.sub(pattern, replacement, text)
    for unit, spoken in _UNITS.items():
        text = re.sub(rf"(\d)\s*{re.escape(unit)}\.?(?![a-zA-Z])", rf"\1 {spoken}", text)
    text = text.replace("&", " and ")
    text = re.sub(r"[\"“”„]", "", text)
    text = re.sub(r"\s*[—–]\s*", ", ", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    return text


def chunk_text(text: str, max_chars: int = 320) -> list[str]:
    """Split narration into TTS-sized chunks without cutting sentences apart."""

    from .scene_planner import split_sentences

    chunks: list[str] = []
    current = ""
    for sentence in split_sentences(text):
        if not current:
            current = sentence
        elif len(current) + 1 + len(sentence) <= max_chars:
            current = f"{current} {sentence}"
        else:
            chunks.append(current)
            current = sentence
        # A single sentence longer than the limit is split on commas.
        while len(current) > max_chars:
            split_at = current.rfind(", ", 0, max_chars)
            if split_at < 40:
                split_at = current.rfind(" ", 0, max_chars)
            if split_at < 40:
                break
            chunks.append(current[: split_at + 1].strip())
            current = current[split_at + 1 :].strip()
    if current:
        chunks.append(current)
    return [c for c in chunks if c.strip()]


# ---------------------------------------------------------------------------
# Engines
# ---------------------------------------------------------------------------

class TTSEngine:
    """Base engine interface: synthesize one chunk of text into a WAV file."""

    name = "base"
    #: Words per minute this engine actually speaks at. The script generator
    #: uses it to size a script, so a 20 minute request produces 20 minutes of
    #: narration rather than 20 minutes' worth of words read at another pace.
    speech_rate_wpm = 150.0

    def __init__(self, voice: str = "", speed: float = 1.0, sample_rate: int = 48000) -> None:
        self.voice = voice
        self.speed = float(speed)
        self.sample_rate = int(sample_rate)

    def synthesize(self, text: str, destination: Path) -> Path:  # pragma: no cover - abstract
        raise NotImplementedError


class PiperEngine(TTSEngine):
    """Neural TTS through the ``piper`` CLI (installed by ``piper-tts``)."""

    name = "piper"
    speech_rate_wpm = 155.0

    def __init__(
        self,
        voice: str = "en_US-hfc_female-medium",
        speed: float = 1.0,
        sample_rate: int = 48000,
        fallback_voices: Sequence[str] = (),
    ) -> None:
        super().__init__(voice, speed, sample_rate)
        self.command_prefix = self._locate_piper()
        self.model_path: Path
        self.model_path = self._ensure_voice([voice, *fallback_voices])
        log.info("Voice ready: %s", self.model_path.stem)

    # ------------------------------------------------------------------
    @staticmethod
    def _locate_piper() -> list[str]:
        """Find piper as a console script, or fall back to ``python -m piper``."""

        binary = shutil.which("piper")
        if binary:
            return [binary]
        try:
            import piper  # noqa: F401
        except Exception as exc:
            raise TTSUnavailable(
                "piper is not installed (pip install piper-tts)"
            ) from exc
        return [sys.executable, "-m", "piper"]

    @staticmethod
    def _download_with_piper(voice: str, directory: Path) -> Path | None:
        """Use Piper's own downloader, which knows the current voice catalog."""

        directory.mkdir(parents=True, exist_ok=True)
        try:
            result = subprocess.run(
                [sys.executable, "-m", "piper.download_voices", voice,
                 "--download-dir", str(directory)],
                capture_output=True,
                text=True,
                timeout=600,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        if result.returncode != 0:
            return None
        model = directory / f"{voice}.onnx"
        config = directory / f"{voice}.onnx.json"
        return model if model.exists() and config.exists() else None

    @staticmethod
    def _download_directly(voice: str, directory: Path) -> Path | None:
        """Fetch the ONNX model and its config over plain HTTPS with retries."""

        path = voice_repository_path(voice)
        if not path:
            return None
        model = directory / f"{voice}.onnx"
        config = directory / f"{voice}.onnx.json"
        try:
            download_file(f"{VOICE_BASE}/{path}/{voice}.onnx", model, retries=3, timeout=600)
            download_file(
                f"{VOICE_BASE}/{path}/{voice}.onnx.json", config, retries=3, timeout=120
            )
        except Exception:
            model.unlink(missing_ok=True)
            config.unlink(missing_ok=True)
            return None
        return model

    @classmethod
    def _ensure_voice(cls, candidates: Sequence[str]) -> Path:
        """Return a local ONNX voice, downloading and caching it if needed."""

        override = os.environ.get("VIDFACTORY_PIPER_MODEL")
        if override and Path(override).exists():
            return Path(override)

        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        tried: list[str] = []
        for voice in candidates:
            if not voice:
                continue
            tried.append(voice)
            model = CACHE_DIR / f"{voice}.onnx"
            config = CACHE_DIR / f"{voice}.onnx.json"
            if model.exists() and config.exists() and model.stat().st_size > 1_000_000:
                return model
            for strategy in (cls._download_with_piper, cls._download_directly):
                found = strategy(voice, CACHE_DIR)
                if found is not None:
                    return found
                log.debug("%s failed for %s", strategy.__name__, voice)

        raise TTSUnavailable(
            "no Piper voice could be downloaded (tried "
            + ", ".join(tried[:4])
            + "); check the runner's network access"
        )

    # ------------------------------------------------------------------
    def synthesize(self, text: str, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        raw = destination.with_name(destination.stem + ".piper.wav")
        # Piper's length_scale is inverse to speed: 1.25 is 25% slower.
        length_scale = 1.0 / max(0.4, min(self.speed, 2.0))
        command = [
            *self.command_prefix,
            "-m", str(self.model_path),
            "-f", str(raw),
            "--length-scale", f"{length_scale:.3f}",
            "--sentence-silence", "0.15",
        ]
        try:
            result = subprocess.run(
                command,
                input=text,
                capture_output=True,
                text=True,
                timeout=300,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise TTSUnavailable(f"piper failed to run: {exc}") from exc
        if result.returncode != 0 or not raw.exists():
            raise TTSUnavailable(f"piper failed: {(result.stderr or '')[-300:]}")

        # Piper writes 22.05 kHz mono; resample once to the project rate.
        run_ffmpeg(
            ["-i", str(raw), "-ar", str(self.sample_rate), "-ac", "1", "-c:a", "pcm_s16le", str(destination)],
            description="tts resample",
        )
        raw.unlink(missing_ok=True)
        return destination


def _sounds_female(voice: str) -> bool:
    """Whether a Piper voice name is one of the documented female voices."""

    name = str(voice or "").lower()
    return (
        "female" in name
        or any(marker in name for marker in ("amy", "hfc_f", "kristin", "kathleen"))
        or any(marker in name for marker in ("sharvard", "claude", "mls_9972"))
    )


class EspeakEngine(TTSEngine):
    """eSpeak NG fallback: always available, intelligible, not natural."""

    name = "espeak"
    #: Measured, not assumed: eSpeak with our pacing settings runs far slower
    #: than Piper, and assuming otherwise made every fallback video overrun.
    speech_rate_wpm = 95.0

    def __init__(self, voice: str = "en-us", speed: float = 1.0, sample_rate: int = 48000) -> None:
        super().__init__(voice, speed, sample_rate)
        self.binary = shutil.which("espeak-ng") or shutil.which("espeak")
        if not self.binary:
            raise TTSUnavailable("espeak-ng is not installed")
        # Map a Piper-style voice name onto an eSpeak voice. The language part
        # matters more than the timbre: an English fallback reading Spanish is
        # not a degraded video, it is an unusable one.
        name = str(voice or "")
        if name.startswith("es_") or name.startswith("es-"):
            self.espeak_voice = "es+f3" if _sounds_female(name) else "es"
        else:
            self.espeak_voice = "en-us+f3" if _sounds_female(name) else "en-us"

    def synthesize(self, text: str, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        raw = destination.with_name(destination.stem + ".espeak.wav")
        words_per_minute = int(max(80, min(220, 165 * self.speed)))
        command = [
            self.binary,
            "-v", self.espeak_voice,
            "-s", str(words_per_minute),
            "-p", "45",
            "-g", "4",
            "-w", str(raw),
            text,
        ]
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=300, check=False)
        except (OSError, subprocess.SubprocessError) as exc:
            raise TTSUnavailable(f"espeak-ng failed to run: {exc}") from exc
        if result.returncode != 0 or not raw.exists():
            raise TTSUnavailable(f"espeak-ng failed: {(result.stderr or '')[-300:]}")

        run_ffmpeg(
            ["-i", str(raw), "-ar", str(self.sample_rate), "-ac", "1", "-c:a", "pcm_s16le", str(destination)],
            description="tts resample",
        )
        raw.unlink(missing_ok=True)
        return destination


class SilentEngine(TTSEngine):
    """Timed silence. Keeps the pipeline runnable when no TTS exists at all."""

    name = "silent"
    speech_rate_wpm = 150.0

    def synthesize(self, text: str, destination: Path) -> Path:
        # ~2.5 spoken words per second is the same rate the planner assumes.
        seconds = max(0.8, len(text.split()) / 2.5 / max(self.speed, 0.1))
        return make_silence(destination, seconds, self.sample_rate)


def voices_for_language(language: Any, requested: str = "") -> tuple[str, list[str]]:
    """Pick the voice and its fallbacks for a language.

    A beginner should never have to choose a voice. Selecting Spanish selects
    the Spanish voice; an explicitly requested voice always wins, but if it
    belongs to a different language than the script it is ignored with a
    warning rather than used, because narrating Spanish with an English voice
    produces something nobody can listen to.
    """

    from .languages import resolve_language

    resolved = resolve_language(language)
    prefix = "en_" if resolved.is_english else "es_"
    wanted = str(requested or "").strip()
    if wanted and wanted.startswith(prefix):
        rest = [v for v in resolved.voices if v != wanted]
        return wanted, rest
    if wanted:
        log.warning(
            "Requested voice %r is not a %s voice; using %s instead",
            wanted, resolved.label, resolved.voices[0],
        )
    return resolved.voices[0], list(resolved.voices[1:])


def build_engine(
    engine: str = "auto",
    voice: str = "en_US-hfc_female-medium",
    speed: float = 1.0,
    sample_rate: int = 48000,
    fallback_voices: Sequence[str] = (),
    language: Any = None,
) -> TTSEngine:
    """Return the best available engine, honoring an explicit request first."""

    if language is not None:
        voice, derived = voices_for_language(language, voice)
        fallback_voices = list(dict.fromkeys([*fallback_voices, *derived]))
        # A fallback in the wrong language is worse than no fallback.
        prefix = voice.split("_")[0] + "_"
        fallback_voices = [v for v in fallback_voices if v.startswith(prefix)]

    order: list[str]
    if engine in ("piper", "espeak", "silent"):
        order = [engine]
    else:
        order = ["piper", "espeak", "silent"]

    errors: list[str] = []
    for name in order:
        try:
            if name == "piper":
                return PiperEngine(voice, speed, sample_rate, fallback_voices)
            if name == "espeak":
                return EspeakEngine(voice, speed, sample_rate)
            return SilentEngine(voice, speed, sample_rate)
        except TTSUnavailable as exc:
            errors.append(f"{name}: {exc}")
            log.warning("TTS engine %s unavailable: %s", name, exc)

    raise TTSUnavailable("no TTS engine could be initialised - " + "; ".join(errors))


# ---------------------------------------------------------------------------
# Narration assembly
# ---------------------------------------------------------------------------

@dataclass
class NarrationChunk:
    """One spoken chunk with its exact place on the finished audio timeline."""

    text: str
    start: float
    end: float
    scene_id: str = ""
    path: str = ""

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


@dataclass
class Narration:
    """The finished narration track plus the timings subtitles are built from."""

    audio_path: Path
    duration: float
    chunks: list[NarrationChunk] = field(default_factory=list)
    #: ``{scene_id: (start, end)}`` for matching visuals to narration.
    scene_timings: dict[str, tuple[float, float]] = field(default_factory=dict)
    engine: str = ""
    voice: str = ""

    @property
    def spoken_text(self) -> str:
        """Exactly the narration that was handed to the TTS engine.

        The provenance check compares script.txt against this rather than
        against another in-memory copy of the script, so a mismatch between
        what was said and what was shipped cannot slip through.
        """

        return " ".join(chunk.text for chunk in self.chunks)

    def scene_duration(self, scene_id: str) -> float:
        start, end = self.scene_timings.get(scene_id, (0.0, 0.0))
        return max(0.0, end - start)


class NarrationBuilder:
    """Renders scenes to a single, loudness-normalized narration track."""

    def __init__(
        self,
        engine: TTSEngine,
        workdir: str | Path,
        sentence_pause: float = 0.28,
        scene_pause: float = 0.45,
        max_chunk_chars: int = 320,
        loudness_lufs: float = -16.0,
        sample_rate: int = 48000,
        language: Any = None,
    ) -> None:
        from .languages import resolve_language

        self.language = resolve_language(language)
        self.engine = engine
        self.workdir = Path(workdir)
        self.workdir.mkdir(parents=True, exist_ok=True)
        self.sentence_pause = float(sentence_pause)
        self.scene_pause = float(scene_pause)
        self.max_chunk_chars = int(max_chunk_chars)
        self.loudness_lufs = float(loudness_lufs)
        self.sample_rate = int(sample_rate)

    # ------------------------------------------------------------------
    def build(self, scenes: Sequence[Any], destination: str | Path) -> Narration:
        """Synthesize every scene and assemble one continuous narration file."""

        parts: list[Path] = []
        chunks: list[NarrationChunk] = []
        scene_timings: dict[str, tuple[float, float]] = {}
        timeline = 0.0
        chunk_index = 0
        silence_cache: dict[str, Path] = {}

        def silence(seconds: float) -> Path:
            key = f"{seconds:.3f}"
            if key not in silence_cache:
                path = self.workdir / f"pause_{key.replace('.', '_')}.wav"
                make_silence(path, seconds, self.sample_rate)
                silence_cache[key] = path
            return silence_cache[key]

        for scene_number, scene in enumerate(scenes):
            scene_id = getattr(scene, "scene_id", f"scene-{scene_number:03d}")
            narration_text = normalize_for_speech(
                getattr(scene, "narration", "") or "", self.language
            )
            if not narration_text:
                continue
            scene_start = timeline

            for chunk_text_value in chunk_text(narration_text, self.max_chunk_chars):
                chunk_index += 1
                wav = self.workdir / f"chunk_{chunk_index:05d}.wav"
                try:
                    self.engine.synthesize(chunk_text_value, wav)
                except Exception as exc:
                    # One failed chunk must not lose the whole narration: insert
                    # correctly-timed silence and carry on.
                    log.warning("TTS failed for a chunk (%s); inserting a pause", exc)
                    make_silence(wav, max(1.0, len(chunk_text_value.split()) / 2.5), self.sample_rate)

                info = probe_media(wav)
                duration = info.duration if info.duration > 0 else 1.0
                chunks.append(
                    NarrationChunk(
                        text=chunk_text_value,
                        start=timeline,
                        end=timeline + duration,
                        scene_id=scene_id,
                        path=str(wav),
                    )
                )
                parts.append(wav)
                timeline += duration

                if self.sentence_pause > 0:
                    pause = silence(self.sentence_pause)
                    parts.append(pause)
                    timeline += self.sentence_pause

            scene_timings[scene_id] = (scene_start, timeline)

            if self.scene_pause > 0 and scene_number < len(scenes) - 1:
                pause = silence(self.scene_pause)
                parts.append(pause)
                timeline += self.scene_pause

        if not parts:
            raise RuntimeError("No narration was produced - the script was empty")

        merged = self.workdir / "narration_raw.wav"
        concat_audio(parts, merged, self.sample_rate)

        target = Path(destination)
        normalized = self._normalize(merged, target)
        actual = probe_media(normalized).duration or timeline

        # Loudness normalization can shift the length by a few milliseconds;
        # rescale the timings so subtitles stay in sync with the real audio.
        if actual > 0 and timeline > 0 and abs(actual - timeline) > 0.05:
            factor = actual / timeline
            for chunk in chunks:
                chunk.start *= factor
                chunk.end *= factor
            scene_timings = {
                key: (start * factor, end * factor)
                for key, (start, end) in scene_timings.items()
            }

        log.info("Narration duration: %s (%s voice)", _fmt(actual), self.engine.name)
        return Narration(
            audio_path=normalized,
            duration=actual,
            chunks=chunks,
            scene_timings=scene_timings,
            engine=self.engine.name,
            voice=self.engine.voice,
        )

    # ------------------------------------------------------------------
    def _normalize(self, source: Path, destination: Path) -> Path:
        """Apply EBU R128 loudness normalization. Falls back to a plain copy."""

        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            run_ffmpeg(
                [
                    "-i", str(source),
                    "-af", f"loudnorm=I={self.loudness_lufs}:TP=-1.5:LRA=11",
                    "-ar", str(self.sample_rate),
                    "-ac", "1",
                    "-c:a", "pcm_s16le",
                    str(destination),
                ],
                description="loudness normalization",
            )
        except Exception as exc:
            log.warning("Loudness normalization failed (%s); using the raw track", exc)
            shutil.copy2(source, destination)
        return destination


def _fmt(seconds: float) -> str:
    minutes, secs = divmod(int(round(seconds)), 60)
    return f"{minutes:d}:{secs:02d}"
