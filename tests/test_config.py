"""Configuration loading and validation."""

from __future__ import annotations

import pytest
import yaml

from vidfactory.config import Config, ConfigError, load_config, parse_bool, validate


def test_repository_config_is_valid(repo_root):
    config = load_config(repo_root / "config.yaml")
    assert config.width == 1920
    assert config.height == 1080
    assert config.fps == 30
    assert config.get("channel.audience_country") == "US"


def test_music_is_always_disabled(repo_root, tmp_path):
    config = load_config(repo_root / "config.yaml")
    assert config.music_enabled is False
    assert config.get("audio.music") is False


def test_music_true_is_rejected():
    data = {"audio": {"music": True}, "video": {"duration_minutes": 20, "resolution": "1920x1080", "fps": 30,
            "min_clip_seconds": 4, "max_clip_seconds": 8, "transition": "cut"},
            "tts": {"engine": "auto"}, "script": {"engine": "auto", "words_per_minute": 150},
            "youtube": {"privacy_status": "private"}, "topics": {"similarity_threshold": 0.6}}
    with pytest.raises(ConfigError, match="music"):
        validate(data)


def test_music_override_is_forced_off(tmp_path, repo_root):
    config = load_config(repo_root / "config.yaml", overrides={"audio.music": True})
    assert config.get("audio.music") is False


def test_overrides_apply(repo_root):
    config = load_config(
        repo_root / "config.yaml",
        overrides={"video.duration_minutes": 7, "tts.voice": "en_US-amy-medium"},
    )
    assert config.get("video.duration_minutes") == 7
    assert config.get("tts.voice") == "en_US-amy-medium"
    assert config.target_seconds == 7 * 60


def test_missing_file_uses_defaults(tmp_path):
    config = load_config(None) if False else load_config()
    assert config.get("channel.name")


def test_explicit_missing_file_raises(tmp_path):
    with pytest.raises(ConfigError):
        load_config(tmp_path / "nope.yaml")


@pytest.mark.parametrize(
    "dotted,value",
    [
        ("video.resolution", "1000x1000"),
        ("video.fps", 17),
        ("video.duration_minutes", 0),
        ("youtube.privacy_status", "secret"),
        ("tts.engine", "elevenlabs"),
        ("script.engine", "gpt"),
        ("topics.similarity_threshold", 1.5),
        ("script.words_per_minute", 400),
        ("video.transition", "starwipe"),
    ],
)
def test_invalid_values_are_rejected(repo_root, tmp_path, dotted, value):
    raw = yaml.safe_load((repo_root / "config.yaml").read_text(encoding="utf-8"))
    node = raw
    parts = dotted.split(".")
    for part in parts[:-1]:
        node = node[part]
    node[parts[-1]] = value
    target = tmp_path / "config.yaml"
    target.write_text(yaml.safe_dump(raw), encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(target)


def test_min_clip_must_not_exceed_max(repo_root, tmp_path):
    raw = yaml.safe_load((repo_root / "config.yaml").read_text(encoding="utf-8"))
    raw["video"]["min_clip_seconds"] = 12
    raw["video"]["max_clip_seconds"] = 6
    target = tmp_path / "config.yaml"
    target.write_text(yaml.safe_dump(raw), encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(target)


@pytest.mark.parametrize(
    "value,expected",
    [("true", True), ("TRUE", True), ("1", True), ("yes", True),
     ("false", False), ("0", False), ("", False), (None, False), (True, True)],
)
def test_parse_bool(value, expected):
    assert parse_bool(value, default=False) is expected


def test_dotted_get_and_set():
    config = Config(data={"a": {"b": 1}})
    assert config.get("a.b") == 1
    assert config.get("a.missing", "fallback") == "fallback"
    config.set("a.c.d", 5)
    assert config.get("a.c.d") == 5
