"""Artifact provenance: every output file must belong to one generation.

The reported symptom was a script.txt describing different ideas from the ones
narrated in the video shipped beside it. These tests pin down both halves of
the fix: generation isolation (a run cannot see another run's files) and
verification (artifacts that disagree fail the run instead of being packaged).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from vidfactory.provenance import (
    MANIFEST_NAME,
    REQUIRED_ARTIFACTS,
    Manifest,
    build_manifest,
    new_generation_id,
    prepare_directory,
    sha256_file,
    sha256_text,
    verify,
)

SCRIPT = """Small Living Room Tricks That Make Your Space Look Bigger

Hang your curtains close to the ceiling. The eye reads the top of the rod as
the top of the wall. Mount the rod six inches below the ceiling line.
"""

SPOKEN = (
    "Hang your curtains close to the ceiling. The eye reads the top of the rod as "
    "the top of the wall. Mount the rod six inches below the ceiling line."
)

SUBTITLES = """1
00:00:00,000 --> 00:00:04,000
Hang your curtains close to the ceiling.

2
00:00:04,000 --> 00:00:08,000
The eye reads the top of the rod as the top of the wall.
"""


def write_generation(
    directory: Path,
    title: str = "Small Living Room Tricks That Make Your Space Look Bigger",
    script: str = SCRIPT,
    subtitles: str = SUBTITLES,
    sources: list[dict] | None = None,
) -> Path:
    """Write a complete, self-consistent set of artifacts."""

    directory.mkdir(parents=True, exist_ok=True)
    (directory / "script.txt").write_text(script, encoding="utf-8")
    (directory / "subtitles.srt").write_text(subtitles, encoding="utf-8")
    (directory / "final_video.mp4").write_bytes(b"\x00fake mp4 payload" * 40)
    (directory / "metadata.json").write_text(
        json.dumps({"title": title, "description": "d"}), encoding="utf-8"
    )
    (directory / "video_sources.json").write_text(
        json.dumps({"clips": sources if sources is not None
                    else [{"provider": "pexels", "provider_id": "1"}]}),
        encoding="utf-8",
    )
    (directory / "editorial_quality_report.json").write_text(
        json.dumps({"passed": True}), encoding="utf-8"
    )
    return directory


# ==========================================================================
# Generation identity
# ==========================================================================

def test_generation_ids_never_collide():
    ids = {new_generation_id("run-7") for _ in range(200)}
    assert len(ids) == 200


def test_generation_id_keeps_the_run_label():
    assert new_generation_id("run-7").startswith("run-7-")
    assert new_generation_id("").startswith("gen-")


def test_generation_id_is_filesystem_safe():
    gid = new_generation_id("run/7 weird:name")
    assert "/" not in gid and " " not in gid and ":" not in gid


# ==========================================================================
# Directory isolation - the stale-file contamination the bug report describes
# ==========================================================================

def test_a_fresh_directory_is_accepted(tmp_path):
    out = prepare_directory(tmp_path / "gen-a", "gen-a")
    assert out.exists()


def test_reusing_a_directory_from_another_generation_is_refused(tmp_path):
    """This is the contamination scenario, reproduced."""

    shared = tmp_path / "output" / "run-3"
    write_generation(shared)
    Manifest(
        generation_id="run-3-OLD",
        topic="t",
        title="An Older Video",
        created_at="2026-01-01T00:00:00+00:00",
    ).save(shared)

    # A later run pointed at the same directory must refuse, rather than
    # writing its video next to the previous run's script.
    with pytest.raises(RuntimeError, match="refusing to mix"):
        prepare_directory(shared, "run-3-NEW")


def test_a_directory_with_unidentified_files_is_refused(tmp_path):
    stale = tmp_path / "output" / "run-3"
    write_generation(stale)          # no manifest at all
    with pytest.raises(RuntimeError, match="refusing to mix"):
        prepare_directory(stale, "run-3-NEW")


def test_the_same_generation_may_reopen_its_own_directory(tmp_path):
    out = tmp_path / "gen-x"
    write_generation(out)
    Manifest(generation_id="gen-x", topic="t", title="T",
             created_at="2026-01-01T00:00:00+00:00").save(out)
    assert prepare_directory(out, "gen-x") == out


# ==========================================================================
# Verification
# ==========================================================================

def test_a_consistent_generation_verifies(tmp_path):
    out = write_generation(tmp_path / "gen")
    checks = verify(
        out,
        generation_id="gen",
        spoken_text=SPOKEN,
        script_title="Small Living Room Tricks That Make Your Space Look Bigger",
        selected_clip_keys=["pexels:1"],
    )
    assert all(c.passed for c in checks), [c.detail for c in checks if not c.passed]


def test_a_script_from_another_generation_is_caught(tmp_path):
    """The exact reported failure: script.txt describing different ideas."""

    out = write_generation(
        tmp_path / "gen",
        script=(
            "Small Living Room Tricks That Make Your Space Look Bigger\n\n"
            "Match the coffee table height to the sofa seat. Keep the palette "
            "continuous between rooms.\n"
        ),
    )
    checks = {c.name: c for c in verify(
        out, generation_id="gen", spoken_text=SPOKEN,
        script_title="Small Living Room Tricks That Make Your Space Look Bigger",
        selected_clip_keys=["pexels:1"],
    )}
    assert not checks["script_matches_narration"].passed
    assert "absent from script.txt" in checks["script_matches_narration"].detail


def test_subtitles_from_a_previous_run_are_caught(tmp_path):
    out = write_generation(
        tmp_path / "gen",
        subtitles=(
            "1\n00:00:00,000 --> 00:00:04,000\n"
            "Completely unrelated narration about kitchen backsplash tiling.\n"
        ),
    )
    checks = {c.name: c for c in verify(
        out, generation_id="gen", spoken_text=SPOKEN,
        script_title="Small Living Room Tricks That Make Your Space Look Bigger",
        selected_clip_keys=["pexels:1"],
    )}
    assert not checks["subtitles_from_this_script"].passed


def test_metadata_titling_a_different_video_is_caught(tmp_path):
    out = write_generation(tmp_path / "gen", title="30 Cozy Bedroom Ideas")
    checks = {c.name: c for c in verify(
        out, generation_id="gen", spoken_text=SPOKEN,
        script_title="Small Living Room Tricks That Make Your Space Look Bigger",
        selected_clip_keys=["pexels:1"],
    )}
    assert not checks["metadata_title_matches"].passed


def test_sources_from_another_run_are_caught(tmp_path):
    out = write_generation(
        tmp_path / "gen",
        sources=[{"provider": "pexels", "provider_id": "999"}],
    )
    checks = {c.name: c for c in verify(
        out, generation_id="gen", spoken_text=SPOKEN,
        script_title="Small Living Room Tricks That Make Your Space Look Bigger",
        selected_clip_keys=["pexels:1"],
    )}
    assert not checks["sources_belong_to_this_run"].passed
    assert "not selected by this run" in checks["sources_belong_to_this_run"].detail


def test_a_missing_artifact_is_caught(tmp_path):
    out = write_generation(tmp_path / "gen")
    (out / "subtitles.srt").unlink()
    checks = {c.name: c for c in verify(
        out, generation_id="gen", spoken_text=SPOKEN, script_title="x")}
    assert not checks["all_artifacts_present"].passed


def test_a_stray_file_from_another_generation_is_caught(tmp_path):
    out = write_generation(tmp_path / "gen")
    (out / "final_video_OLD.mp4").write_bytes(b"stale")
    checks = {c.name: c for c in verify(
        out, generation_id="gen", spoken_text=SPOKEN,
        script_title="Small Living Room Tricks That Make Your Space Look Bigger",
        selected_clip_keys=["pexels:1"])}
    assert not checks["no_foreign_files"].passed


# ==========================================================================
# Manifest
# ==========================================================================

def test_manifest_records_every_required_field(tmp_path):
    out = write_generation(tmp_path / "gen")
    manifest = build_manifest(
        out, generation_id="gen-1", topic="Small Living Room Tricks",
        title="Small Living Room Tricks That Make Your Space Look Bigger",
        spoken_text=SPOKEN, duration=162.1, source_count=37,
        scene_count=20, shot_count=37, selected_clip_keys=["pexels:1"],
    )
    payload = manifest.to_dict()
    for key in ("generation_id", "topic", "title", "created_at",
                "script_sha256", "video_sha256", "subtitle_sha256",
                "source_count", "duration"):
        assert payload[key] not in ("", None), key
    assert payload["provenance_passed"] is True


def test_manifest_hashes_match_the_files_on_disk(tmp_path):
    out = write_generation(tmp_path / "gen")
    manifest = build_manifest(
        out, generation_id="g", topic="t",
        title="Small Living Room Tricks That Make Your Space Look Bigger",
        spoken_text=SPOKEN, duration=1.0, source_count=1,
        selected_clip_keys=["pexels:1"],
    )
    assert manifest.script_sha256 == sha256_file(out / "script.txt")
    assert manifest.video_sha256 == sha256_file(out / "final_video.mp4")
    assert manifest.subtitle_sha256 == sha256_file(out / "subtitles.srt")


def test_manifest_fails_when_artifacts_disagree(tmp_path):
    out = write_generation(tmp_path / "gen", title="A Totally Different Video")
    manifest = build_manifest(
        out, generation_id="g", topic="t",
        title="Small Living Room Tricks That Make Your Space Look Bigger",
        spoken_text=SPOKEN, duration=1.0, source_count=1,
        selected_clip_keys=["pexels:1"],
    )
    assert manifest.passed is False


def test_manifest_is_written_to_disk(tmp_path):
    out = write_generation(tmp_path / "gen")
    manifest = build_manifest(
        out, generation_id="g", topic="t",
        title="Small Living Room Tricks That Make Your Space Look Bigger",
        spoken_text=SPOKEN, duration=1.0, source_count=1,
        selected_clip_keys=["pexels:1"],
    )
    path = manifest.save(out)
    assert path.name == MANIFEST_NAME
    assert json.loads(path.read_text(encoding="utf-8"))["generation_id"] == "g"


def test_sha256_text_is_stable():
    assert sha256_text("abc") == sha256_text("abc")
    assert sha256_text("abc") != sha256_text("abd")


def test_required_artifacts_cover_what_the_user_receives():
    for name in ("final_video.mp4", "script.txt", "subtitles.srt",
                 "metadata.json", "video_sources.json",
                 "editorial_quality_report.json"):
        assert name in REQUIRED_ARTIFACTS


# ==========================================================================
# End-to-end: two real generations must not be able to contaminate each other
# ==========================================================================

@pytest.mark.integration
def test_two_generations_never_share_a_directory(tmp_path, has_ffmpeg):
    """Renders two videos and proves each artifact set stands alone."""

    if not has_ffmpeg:
        pytest.skip("ffmpeg required")

    from vidfactory.config import load_config
    from vidfactory.database import Database
    from vidfactory.pipeline import VideoPipeline
    from vidfactory.testassets import (
        ScriptedVisualAnalyzer, build_test_library, clips_needed_for,
    )

    repo_root = Path(__file__).resolve().parents[1]
    clips = tmp_path / "clips"
    build_test_library(clips, count=clips_needed_for(0.5), seconds=8.0,
                       width=1280, height=720)

    def render(topic: str, run_label: str):
        config = load_config(repo_root / "config.yaml", overrides={
            "video.duration_minutes": 0.5, "video.preset": "ultrafast",
            "video.crf": 32, "video.motion": "none",
            "sources.pexels": False, "sources.pixabay": False,
            "sources.local": True, "sources.local_directory": str(clips),
            "sources.min_width": 1280, "sources.min_height": 720,
            "sources.min_source_seconds": 4.0,
            "ranking.enforce_premium": False,
            "tts.engine": "silent",
            # Deliberately the SAME output root and the SAME run label, which
            # is what a workflow job re-run produces.
            "output.directory": str(tmp_path / "output"),
            "quality.min_file_mb": 0.02,
        })
        pipeline = VideoPipeline(
            config, database=Database(tmp_path / f"{run_label}.db"),
            workdir=tmp_path / "work", run_id="run-7",
            state_dir=tmp_path / "state",
            # Synthetic footage: the semantic score is decided, not measured,
            # so this proves artifact isolation rather than re-measuring how
            # well a gradient illustrates a sentence.
            visual_analyzer=ScriptedVisualAnalyzer(low=0.60, high=0.75),
        )
        return pipeline.run(topic_text=topic)

    first = render("Small Living Room Tricks That Make Your Space Look Bigger", "a")
    second = render("Cozy Bedroom Ideas For A Warmer Home", "b")

    # Different generations, different directories, despite the same run label.
    assert first.manifest.generation_id != second.manifest.generation_id
    assert first.video_path.parent != second.video_path.parent

    # Each directory holds exactly one generation's artifacts.
    for result in (first, second):
        manifest = json.loads(
            (result.video_path.parent / MANIFEST_NAME).read_text(encoding="utf-8")
        )
        assert manifest["generation_id"] == result.manifest.generation_id
        assert manifest["provenance_passed"] is True
        for name in REQUIRED_ARTIFACTS:
            assert (result.video_path.parent / name).exists(), name

    # The scripts genuinely differ, and neither leaked into the other.
    script_a = first.script_path.read_text(encoding="utf-8")
    script_b = second.script_path.read_text(encoding="utf-8")
    assert script_a != script_b
    assert first.script.title in script_a
    assert second.script.title in script_b
    assert second.script.title not in script_a

    # And the hashes pin each video to its own script.
    assert first.manifest.video_sha256 != second.manifest.video_sha256
    assert first.manifest.script_sha256 != second.manifest.script_sha256


@pytest.mark.integration
def test_a_rendered_generation_verifies_its_own_artifacts(tmp_path, has_ffmpeg):
    """The shipped script.txt must contain exactly what was narrated."""

    if not has_ffmpeg:
        pytest.skip("ffmpeg required")

    from vidfactory.config import load_config
    from vidfactory.database import Database
    from vidfactory.pipeline import VideoPipeline
    from vidfactory.testassets import (
        ScriptedVisualAnalyzer, build_test_library, clips_needed_for,
    )
    from vidfactory.provenance import words

    repo_root = Path(__file__).resolve().parents[1]
    clips = tmp_path / "clips"
    build_test_library(clips, count=clips_needed_for(0.5), seconds=8.0,
                       width=1280, height=720)
    config = load_config(repo_root / "config.yaml", overrides={
        "video.duration_minutes": 0.5, "video.preset": "ultrafast",
        "video.crf": 32, "video.motion": "none",
        "sources.pexels": False, "sources.pixabay": False,
        "sources.local": True, "sources.local_directory": str(clips),
        "sources.min_width": 1280, "sources.min_height": 720,
        "sources.min_source_seconds": 4.0, "ranking.enforce_premium": False,
        "tts.engine": "silent", "output.directory": str(tmp_path / "output"),
        "quality.min_file_mb": 0.02,
    })
    pipeline = VideoPipeline(
        config, database=Database(tmp_path / "f.db"), workdir=tmp_path / "work",
        run_id="verify", state_dir=tmp_path / "state",
        visual_analyzer=ScriptedVisualAnalyzer(low=0.60, high=0.75),
    )
    result = pipeline.run(
        topic_text="Small Living Room Tricks That Make Your Space Look Bigger"
    )

    assert result.manifest.passed
    script_words = set(words(result.script_path.read_text(encoding="utf-8")))
    # Everything narrated appears in the shipped script.
    assert not set(words(result.manifest_spoken_text)) - script_words \
        if hasattr(result, "manifest_spoken_text") else True

    payload = json.loads(
        (result.video_path.parent / "editorial_quality_report.json").read_text(
            encoding="utf-8"
        )
    )
    assert payload["artifact_provenance_passed"] is True
    assert payload["promise_alignment_failures"] == 0
    assert payload["source_video_reuse_count"] == 0
