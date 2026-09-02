"""Shot planning, ffmpeg helpers, metadata and quality control."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from vidfactory.editor import Shot, ShotPlan, VideoEditor, estimate_shot_count, plan_shots
from vidfactory.ffmpeg_utils import (
    FFmpegError,
    ffmpeg_available,
    format_chapter,
    is_valid_video,
    make_silence,
    probe_media,
)
from vidfactory.metadata import (
    build_chapters,
    build_description,
    build_metadata,
    build_summary,
    build_tags,
    safe_filename,
)
from vidfactory.quality_control import validate_output
from vidfactory.scene_planner import plan_scenes


class _FakeInner:
    def __init__(self, key: str, author: str) -> None:
        self.key = key
        self.author = author


class FakeClip:
    def __init__(self, path: str, duration: float, key: str = "", author: str = "") -> None:
        self.path = path
        self.duration = duration
        self.clip = _FakeInner(key or path, author or "someone")


# --------------------------------------------------------------------- ffmpeg

def test_ffmpeg_is_available_in_this_environment():
    assert ffmpeg_available() is True, "FFmpeg must be installed to run this project"


def test_probe_of_a_missing_file_is_safe(tmp_path):
    info = probe_media(tmp_path / "missing.mp4")
    assert info.has_video is False
    assert info.duration == 0.0


def test_probe_of_a_non_media_file_is_safe(tmp_path):
    junk = tmp_path / "junk.mp4"
    junk.write_bytes(b"definitely not a video")
    assert is_valid_video(junk) is False


def test_make_silence_has_the_requested_length(tmp_path):
    path = make_silence(tmp_path / "s.wav", 2.5)
    assert probe_media(path).duration == pytest.approx(2.5, abs=0.05)


def test_run_ffmpeg_raises_on_a_bad_command():
    from vidfactory.ffmpeg_utils import run_ffmpeg

    with pytest.raises(FFmpegError):
        run_ffmpeg(["-i", "/definitely/not/here.mp4", "/tmp/out.mp4"], description="bad")


# ---------------------------------------------------------------- shot planner

def test_a_long_scene_gets_multiple_shots(tmp_path):
    clips = [FakeClip(str(_touch(tmp_path, f"c{i}.mp4")), 15.0, key=f"pexels:{i}") for i in range(8)]
    plan = plan_shots([("s1", 30.0)], clips, min_shot=3, max_shot=6, motion="none")
    assert len(plan.shots) >= 5
    assert all(shot.duration <= 6.5 for shot in plan.shots)
    assert sum(shot.duration for shot in plan.shots) == pytest.approx(30.0, abs=0.1)


def test_shots_cover_every_scene_exactly(tmp_path):
    clips = [FakeClip(str(_touch(tmp_path, f"c{i}.mp4")), 12.0, key=f"pexels:{i}") for i in range(8)]
    scenes = [("s1", 6.0), ("s2", 11.0), ("s3", 3.0)]
    plan = plan_shots(scenes, clips, min_shot=3, max_shot=6, motion="none")
    for scene_id, duration in scenes:
        covered = sum(s.duration for s in plan.shots if s.scene_id == scene_id)
        assert covered == pytest.approx(duration, abs=0.05)


def test_no_single_clip_is_frozen_for_a_whole_long_scene(tmp_path):
    clips = [FakeClip(str(_touch(tmp_path, f"c{i}.mp4")), 20.0, key=f"pexels:{i}") for i in range(10)]
    plan = plan_shots([("s1", 40.0)], clips, min_shot=3, max_shot=6, motion="none")
    assert len({shot.source for shot in plan.shots}) > 1


def test_forced_reuse_is_reported_and_varied(tmp_path):
    """With one clip and many shots, reuse is unavoidable - but never silent."""

    clips = [FakeClip(str(_touch(tmp_path, "only.mp4")), 30.0, key="pexels:1")]
    plan = plan_shots([("s1", 24.0)], clips, min_shot=3, max_shot=6, motion="subtle")
    assert plan.reuse_count > 0
    assert plan.unique_sources == 1
    assert plan.shortfall == len(plan.shots) - 1
    starts = [round(shot.start, 2) for shot in plan.shots]
    assert len(set(starts)) > 1
    assert any(shot.motion != "none" for shot in plan.shots)


def test_planning_without_clips_raises():
    with pytest.raises(ValueError):
        plan_shots([("s1", 10.0)], [], min_shot=4, max_shot=8)


def test_motion_none_disables_movement(tmp_path):
    clips = [FakeClip(str(_touch(tmp_path, f"c{i}.mp4")), 20.0, key=f"pexels:{i}") for i in range(8)]
    plan = plan_shots([("s1", 20.0)], clips, motion="none")
    assert all(shot.motion == "none" for shot in plan.shots)


def test_filter_chain_scales_and_crops_without_stretching(tmp_path):
    editor = VideoEditor(tmp_path / "work")
    chain = editor._filter_for(Shot(source=Path("x.mp4"), start=0, duration=5, motion="none"))
    assert "force_original_aspect_ratio=increase" in chain
    assert "crop=1920:1080" in chain
    assert "setsar=1" in chain


def test_motion_filter_uses_crop_not_zoompan(tmp_path):
    editor = VideoEditor(tmp_path / "work")
    chain = editor._filter_for(Shot(source=Path("x.mp4"), start=0, duration=5, motion="zoom_in"))
    assert "zoompan" not in chain
    assert "crop=" in chain
    assert chain.endswith("setsar=1")


# -------------------------------------------------------------------- metadata

def test_safe_filename():
    assert safe_filename("25 Small Living Room Ideas!") == "25-small-living-room-ideas.mp4"
    assert safe_filename("???").endswith(".mp4")


def test_chapter_formatting():
    assert format_chapter(0) == "0:00"
    assert format_chapter(48) == "0:48"
    assert format_chapter(3725) == "1:02:05"


def test_chapters_start_at_zero_and_increase(script):
    scenes = plan_scenes(script)
    timings = _fake_timings(scenes)
    chapters = build_chapters(script, timings, scenes)
    assert chapters
    assert chapters[0].seconds == 0.0
    seconds = [c.seconds for c in chapters]
    assert seconds == sorted(seconds)
    assert len(set(seconds)) == len(seconds)


def test_chapters_are_at_least_ten_seconds_apart(script):
    scenes = plan_scenes(script)
    chapters = build_chapters(script, _fake_timings(scenes), scenes)
    for previous, current in zip(chapters, chapters[1:]):
        assert current.seconds - previous.seconds >= 10.0


def test_tags_are_relevant_and_within_youtube_limits(topic):
    tags = build_tags(topic, extra=topic.keywords)
    assert tags
    assert len(tags) <= 22
    assert sum(len(t) + 1 for t in tags) <= 500
    assert any("living room" in t for t in tags)
    assert len(tags) == len(set(tags))


def test_description_includes_chapters_and_credit(script):
    scenes = plan_scenes(script)
    chapters = build_chapters(script, _fake_timings(scenes), scenes)
    description = build_description(
        script, chapters, sources=[{"provider": "pexels"}], channel_name="HomeeDeeco"
    )
    assert "Chapters:" in description
    assert "0:00" in description
    assert "Pexels" in description
    assert "original" in description.lower()
    assert len(description) <= 4900


def test_summary_is_short(script):
    summary = build_summary(script)
    assert 0 < len(summary) <= 330


def test_full_metadata_bundle(tmp_path, script):
    scenes = plan_scenes(script)
    metadata = build_metadata(
        script=script,
        scenes=scenes,
        scene_timings=_fake_timings(scenes),
        duration_seconds=1234.0,
        sources=[{"provider": "pexels"}],
        channel_name="HomeeDeeco",
    )
    assert len(metadata.title) <= 100
    assert metadata.tags
    assert metadata.filename.endswith(".mp4")
    path = metadata.save(tmp_path / "metadata.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["title"] == metadata.title
    assert payload["chapters"][0]["time"] == "0:00"


def test_long_titles_are_truncated(script):
    script.title = "A" * 200
    scenes = plan_scenes(script)
    metadata = build_metadata(script, scenes, _fake_timings(scenes), 100.0)
    assert len(metadata.title) <= 100


# ------------------------------------------------------------- quality control

def test_validation_fails_for_a_missing_file(tmp_path):
    report = validate_output(tmp_path / "nope.mp4", expected_duration=10)
    assert report.passed is False
    assert report.failures[0].name == "file_exists"


def test_validation_fails_for_an_audio_only_file(tmp_path):
    audio = make_silence(tmp_path / "a.wav", 3.0)
    report = validate_output(audio, expected_duration=3.0, min_file_mb=0.0)
    names = {c.name for c in report.failures}
    assert "video_stream" in names


def test_validation_report_serialises(tmp_path):
    report = validate_output(tmp_path / "nope.mp4", expected_duration=1)
    path = report.save(tmp_path / "report.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["passed"] is False
    assert payload["checks"]


# ---------------------------------------------------------------------- helpers

def _touch(directory: Path, name: str) -> Path:
    path = directory / name
    path.write_bytes(b"placeholder")
    return path


def _fake_timings(scenes) -> dict[str, tuple[float, float]]:
    timings: dict[str, tuple[float, float]] = {}
    cursor = 0.0
    for scene in scenes:
        timings[scene.scene_id] = (cursor, cursor + scene.estimated_duration)
        cursor += scene.estimated_duration + 0.4
    return timings
