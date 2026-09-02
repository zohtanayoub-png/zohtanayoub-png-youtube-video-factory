"""Pipeline wiring and the command line interface, with mocked providers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from vidfactory.config import load_config
from vidfactory.database import Database
from vidfactory.http import HttpError, download_file, request_json
from vidfactory.logging_utils import RedactingFilter, get_logger, setup_logging
from vidfactory.main import build_parser, main
from vidfactory.pipeline import PipelineError, VideoPipeline
from vidfactory.scene_planner import Scene


# ------------------------------------------------------------------- logging

def test_secret_values_are_redacted(monkeypatch):
    monkeypatch.setenv("PEXELS_API_KEY", "super-secret-key-value")
    redactor = RedactingFilter()
    assert "super-secret-key-value" not in redactor.redact("key=super-secret-key-value")


def test_url_style_tokens_are_redacted():
    redactor = RedactingFilter()
    cleaned = redactor.redact("https://example.invalid/x?api_key=abcdef123456&q=1")
    assert "abcdef123456" not in cleaned


def test_tagged_logger_writes_its_tag(capsys):
    setup_logging()
    get_logger("TESTTAG").info("hello world")
    assert "[TESTTAG]" in capsys.readouterr().out


# ---------------------------------------------------------------------- http

def test_request_json_retries_then_succeeds(monkeypatch):
    calls = {"n": 0}

    class Response:
        def __init__(self, status):
            self.status_code = status
            self.headers = {}

        def raise_for_status(self):
            if self.status_code >= 400:
                raise RuntimeError("bad")

        def json(self):
            return {"ok": True}

    class Session:
        def get(self, url, headers=None, params=None, timeout=None):
            calls["n"] += 1
            return Response(503 if calls["n"] == 1 else 200)

    monkeypatch.setattr("vidfactory.http.time.sleep", lambda s: None)
    payload = request_json("https://example.invalid/x", session=Session(), retries=3)
    assert payload == {"ok": True}
    assert calls["n"] == 2


def test_request_json_gives_up_and_hides_the_url(monkeypatch):
    class Session:
        def get(self, *args, **kwargs):
            raise __import__("requests").RequestException("nope")

    monkeypatch.setattr("vidfactory.http.time.sleep", lambda s: None)
    with pytest.raises(HttpError) as exc:
        request_json("https://example.invalid/x?api_key=secret", session=Session(), retries=2)
    assert "secret" not in str(exc.value)


# ------------------------------------------------------------------ pipeline

@pytest.fixture
def local_pipeline(tmp_path, has_ffmpeg, repo_root):
    if not has_ffmpeg:
        pytest.skip("ffmpeg required")
    from vidfactory.testassets import build_test_library

    clips = tmp_path / "clips"
    build_test_library(clips, count=24, seconds=8.0, width=1280, height=720)
    config = load_config(
        repo_root / "config.yaml",
        overrides={
            "video.duration_minutes": 0.5,
            "video.preset": "ultrafast",
            "video.crf": 32,
            "video.motion": "none",
            "sources.pexels": False,
            "sources.pixabay": False,
            "sources.local": True,
            "sources.local_directory": str(clips),
            "sources.min_width": 1280,
            "sources.min_height": 720,
            "sources.min_source_seconds": 4.0,
            "tts.engine": "silent",
            "output.directory": str(tmp_path / "output"),
            "quality.min_file_mb": 0.02,
        },
    )
    database = Database(tmp_path / "f.db")
    return VideoPipeline(
        config,
        database=database,
        workdir=tmp_path / "work",
        run_id="unit",
        state_dir=tmp_path / "state",
    )


def test_pipeline_fails_clearly_without_any_provider(tmp_path, repo_root):
    config = load_config(
        repo_root / "config.yaml",
        overrides={
            "sources.pexels": False,
            "sources.pixabay": False,
            "sources.local": False,
            "output.directory": str(tmp_path / "out"),
        },
    )
    pipeline = VideoPipeline(
        config, database=Database(tmp_path / "f.db"), workdir=tmp_path / "w",
        state_dir=tmp_path / "state",
    )

    class FakeNarration:
        duration = 30.0
        scene_timings: dict = {}

    with pytest.raises(PipelineError, match="provider"):
        pipeline._gather_footage([], FakeNarration(), _dummy_topic(), shots_needed=5)


def test_scene_search_order_puts_item_leads_first():
    scenes = [
        Scene("item-001-01", "b", 3.0, "q"),
        Scene("item-001-00", "a", 3.0, "q"),
        Scene("item-002-00", "c", 3.0, "q"),
    ]
    ordered = VideoPipeline._scene_search_order(scenes)
    assert [s.scene_id for s in ordered[:2]] == ["item-001-00", "item-002-00"]


def test_clip_history_is_loaded_for_ranking(local_pipeline):
    local_pipeline.database.record_clip_use("pexels", "77")
    history = local_pipeline._clip_history()
    assert "pexels:77" in history
    count, days = history["pexels:77"]
    assert count == 1
    assert days is not None and days < 1


def test_pipeline_runs_end_to_end_with_local_clips(local_pipeline):
    result = local_pipeline.run(topic_text="5 Small Living Room Ideas")
    assert result.video_path.exists()
    assert result.report.passed
    assert result.duration > 5.0
    payload = json.loads(result.metadata_path.read_text(encoding="utf-8"))
    assert payload["title"]
    # History was written, so the next run will avoid the same topic and clips.
    assert local_pipeline.database.stats()["videos"] == 1
    assert (local_pipeline.state_dir / "videos.json").exists()


def test_a_failed_run_is_recorded(local_pipeline, monkeypatch):
    monkeypatch.setattr(
        VideoPipeline,
        "_narrate",
        lambda self, scenes, engine=None: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    with pytest.raises(RuntimeError):
        local_pipeline.run(topic_text="20 Cozy Bedroom Ideas")
    rows = local_pipeline.database.query("SELECT status FROM generations")
    assert rows[-1]["status"] == "failed"


# ----------------------------------------------------------------------- CLI

def test_parser_exposes_the_documented_inputs():
    parser = build_parser()
    args = parser.parse_args(
        ["generate", "--topic", "X", "--duration", "12", "--voice", "en_US-amy-medium",
         "--subtitles", "false", "--upload", "false"]
    )
    assert args.topic == "X"
    assert args.duration == 12
    assert args.voice == "en_US-amy-medium"


def test_topics_command_prints_titles(tmp_path, capsys):
    code = main(
        ["--database", str(tmp_path / "d.db"), "--state", str(tmp_path / "s"),
         "topics", "--count", "3"]
    )
    assert code == 0
    lines = [l for l in capsys.readouterr().out.splitlines() if l.rstrip().endswith("]") and "[TOPIC]" not in l]
    assert len(lines) == 3


def test_doctor_command_runs(tmp_path, capsys):
    code = main(["--database", str(tmp_path / "d.db"), "--state", str(tmp_path / "s"), "doctor"])
    assert code in (0, 1)
    output = capsys.readouterr().out
    assert "background music" in output
    assert "disabled (correct)" in output


def test_state_command_syncs(tmp_path, capsys):
    code = main(["--database", str(tmp_path / "d.db"), "--state", str(tmp_path / "s"), "state"])
    assert code == 0
    assert (tmp_path / "s" / "topics.json").exists()
    assert "topics" in capsys.readouterr().out


def _dummy_topic():
    from vidfactory.topic_engine import Topic

    return Topic(title="25 Small Living Room Ideas", category="living rooms")
