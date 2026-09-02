"""Configuration loading and validation.

The whole pipeline is driven by ``config.yaml``. Values can be overridden by
CLI flags / workflow inputs, which is how the GitHub Action passes ``topic``,
``duration_minutes`` and friends.
"""

from __future__ import annotations

import copy
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = REPO_ROOT / "config.yaml"


class ConfigError(ValueError):
    """Raised when the configuration file is unusable."""


DEFAULTS: dict[str, Any] = {
    "channel": {
        "name": "HomeeDeeco",
        "language": "en-US",
        "audience_country": "US",
        "niche": "home decor",
    },
    "video": {
        "duration_minutes": 20,
        "resolution": "1920x1080",
        "fps": 30,
        "min_clip_seconds": 4,
        "max_clip_seconds": 8,
        "transition": "cut",
        "transition_seconds": 0.4,
        "motion": "subtle",
        "tail_seconds": 1.2,
        "video_bitrate": "6000k",
        "crf": 20,
        "preset": "veryfast",
    },
    "audio": {
        "narration": True,
        "music": False,
        "loudness_lufs": -16.0,
        "sample_rate": 48000,
        "aac_bitrate": "192k",
    },
    "tts": {
        "engine": "auto",
        "voice": "en_US-hfc_female-medium",
        "fallback_voices": ["en_US-amy-medium", "en_US-lessac-medium"],
        "speed": 1.0,
        "sentence_pause_seconds": 0.28,
        "paragraph_pause_seconds": 0.55,
        "scene_pause_seconds": 0.45,
        "max_chunk_chars": 320,
    },
    "subtitles": {
        "enabled": True,
        "burn_in": False,
        "max_line_chars": 42,
        "max_lines": 2,
    },
    "script": {
        "engine": "auto",
        "words_per_minute": 150,
        "llm": {
            "enabled": False,
            "model_repo": "Qwen/Qwen2.5-1.5B-Instruct-GGUF",
            "model_file": "qwen2.5-1.5b-instruct-q4_k_m.gguf",
            "context_size": 4096,
            "threads": 0,
            "max_seconds_per_call": 240,
            "temperature": 0.8,
        },
    },
    "sources": {
        "pexels": True,
        "pixabay": True,
        "local": False,
        "per_query_results": 20,
        "min_width": 1280,
        "min_height": 720,
        "prefer_width": 1920,
        "min_source_seconds": 5.0,
        "max_download_mb": 90,
        "download_timeout_seconds": 120,
        "retries": 3,
    },
    "ranking": {
        "weights": {
            "relevance": 30,
            "resolution": 20,
            "orientation": 15,
            "duration": 10,
            "novelty": 15,
            "quality": 10,
        },
        "min_score": 28,
        "clip_reuse_cooldown_days": 45,
        "max_uses_per_clip": 3,
    },
    "topics": {"similarity_threshold": 0.62, "history_limit": 500},
    "autopilot": {"enabled": False, "videos_per_week": 3},
    "youtube": {
        "upload_enabled": False,
        "privacy_status": "private",
        "category_id": "26",
        "made_for_kids": False,
    },
    "output": {"directory": "output", "keep_workdir": False},
    "quality": {
        "min_file_mb": 1.0,
        "duration_tolerance_seconds": 12.0,
        "max_repair_attempts": 1,
    },
}

_VALID_PRIVACY = {"private", "unlisted", "public"}
_VALID_TRANSITIONS = {"cut", "crossfade"}
_VALID_TTS_ENGINES = {"auto", "piper", "espeak", "silent"}
_VALID_SCRIPT_ENGINES = {"auto", "llm", "template"}
_TRUTHY = {"1", "true", "yes", "on", "y"}
_FALSY = {"0", "false", "no", "off", "n", ""}


def _deep_merge(base: Mapping[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(dict(base))
    for key, value in override.items():
        if isinstance(value, Mapping) and isinstance(out.get(key), Mapping):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def parse_bool(value: Any, default: bool = False) -> bool:
    """Tolerant bool parsing for workflow inputs (``"true"``, ``"1"``, ...)."""

    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in _TRUTHY:
        return True
    if text in _FALSY:
        return False
    return default


@dataclass
class Config:
    """Validated configuration object with convenient typed accessors."""

    data: dict[str, Any] = field(default_factory=dict)
    path: Path | None = None

    # -- access helpers -------------------------------------------------
    def get(self, dotted: str, default: Any = None) -> Any:
        node: Any = self.data
        for part in dotted.split("."):
            if not isinstance(node, Mapping) or part not in node:
                return default
            node = node[part]
        return node

    def set(self, dotted: str, value: Any) -> None:
        parts = dotted.split(".")
        node = self.data
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = value

    def __getitem__(self, key: str) -> Any:
        return self.data[key]

    # -- derived values -------------------------------------------------
    @property
    def width(self) -> int:
        return int(str(self.get("video.resolution", "1920x1080")).lower().split("x")[0])

    @property
    def height(self) -> int:
        return int(str(self.get("video.resolution", "1920x1080")).lower().split("x")[1])

    @property
    def fps(self) -> int:
        return int(self.get("video.fps", 30))

    @property
    def target_seconds(self) -> float:
        return float(self.get("video.duration_minutes", 20)) * 60.0

    @property
    def music_enabled(self) -> bool:
        """Always False. Kept as a property so callers can assert on it."""
        return False

    def to_dict(self) -> dict[str, Any]:
        return copy.deepcopy(self.data)


def validate(data: Mapping[str, Any]) -> None:
    """Raise :class:`ConfigError` when the configuration cannot be honoured."""

    if parse_bool(_dig(data, "audio.music"), False):
        raise ConfigError(
            "audio.music must be false - this project never adds background music."
        )

    duration = _dig(data, "video.duration_minutes")
    try:
        duration = float(duration)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"video.duration_minutes must be a number, got {duration!r}") from exc
    if not 0.2 <= duration <= 180:
        raise ConfigError("video.duration_minutes must be between 0.2 and 180")

    resolution = str(_dig(data, "video.resolution") or "")
    parts = resolution.lower().split("x")
    if len(parts) != 2 or not all(p.strip().isdigit() for p in parts):
        raise ConfigError(f"video.resolution must look like 1920x1080, got {resolution!r}")
    width, height = (int(p) for p in parts)
    if width < 640 or height < 360:
        raise ConfigError("video.resolution is too small for YouTube output")
    if abs((width / height) - (16 / 9)) > 0.02:
        raise ConfigError("video.resolution must be a 16:9 aspect ratio")

    fps = _dig(data, "video.fps")
    if int(fps) not in (24, 25, 30, 50, 60):
        raise ConfigError("video.fps must be one of 24, 25, 30, 50, 60")

    min_clip = float(_dig(data, "video.min_clip_seconds"))
    max_clip = float(_dig(data, "video.max_clip_seconds"))
    if min_clip <= 0 or max_clip <= 0 or min_clip > max_clip:
        raise ConfigError("video.min_clip_seconds must be > 0 and <= video.max_clip_seconds")

    transition = str(_dig(data, "video.transition") or "cut").lower()
    if transition not in _VALID_TRANSITIONS:
        raise ConfigError(f"video.transition must be one of {sorted(_VALID_TRANSITIONS)}")

    engine = str(_dig(data, "tts.engine") or "auto").lower()
    if engine not in _VALID_TTS_ENGINES:
        raise ConfigError(f"tts.engine must be one of {sorted(_VALID_TTS_ENGINES)}")

    script_engine = str(_dig(data, "script.engine") or "auto").lower()
    if script_engine not in _VALID_SCRIPT_ENGINES:
        raise ConfigError(f"script.engine must be one of {sorted(_VALID_SCRIPT_ENGINES)}")

    privacy = str(_dig(data, "youtube.privacy_status") or "private").lower()
    if privacy not in _VALID_PRIVACY:
        raise ConfigError(f"youtube.privacy_status must be one of {sorted(_VALID_PRIVACY)}")

    threshold = float(_dig(data, "topics.similarity_threshold"))
    if not 0.0 < threshold < 1.0:
        raise ConfigError("topics.similarity_threshold must be between 0 and 1 (exclusive)")

    wpm = float(_dig(data, "script.words_per_minute"))
    if not 80 <= wpm <= 220:
        raise ConfigError("script.words_per_minute must be between 80 and 220")


def _dig(data: Mapping[str, Any], dotted: str) -> Any:
    node: Any = data
    for part in dotted.split("."):
        if not isinstance(node, Mapping):
            return None
        node = node.get(part)
    return node


def load_config(
    path: str | os.PathLike[str] | None = None,
    overrides: Mapping[str, Any] | None = None,
) -> Config:
    """Load ``config.yaml``, merge defaults and overrides, then validate."""

    config_path = Path(path) if path else DEFAULT_CONFIG_PATH
    raw: dict[str, Any] = {}
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as handle:
            loaded = yaml.safe_load(handle) or {}
        if not isinstance(loaded, Mapping):
            raise ConfigError(f"{config_path} must contain a YAML mapping")
        raw = dict(loaded)
    elif path is not None:
        raise ConfigError(f"Configuration file not found: {config_path}")

    merged = _deep_merge(DEFAULTS, raw)

    for dotted, value in (overrides or {}).items():
        if value is None:
            continue
        node = merged
        parts = dotted.split(".")
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = value

    # Music is never negotiable, whatever the file or the overrides say.
    merged.setdefault("audio", {})["music"] = False

    validate(merged)
    return Config(data=merged, path=config_path if config_path.exists() else None)
