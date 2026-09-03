"""Shared pytest fixtures."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from vidfactory.config import load_config          # noqa: E402
from vidfactory.database import Database           # noqa: E402
from vidfactory.ffmpeg_utils import ffmpeg_available  # noqa: E402
from vidfactory.script_generator import generate_script  # noqa: E402
from vidfactory.topic_engine import TopicEngine    # noqa: E402


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture
def config(tmp_path):
    """A real config with output paths redirected into the test tmp dir."""

    return load_config(
        REPO_ROOT / "config.yaml",
        overrides={
            "output.directory": str(tmp_path / "output"),
            "video.preset": "ultrafast",
            "video.crf": 30,
        },
    )


@pytest.fixture
def database(tmp_path) -> Database:
    db = Database(tmp_path / "factory.db")
    yield db
    db.close()


@pytest.fixture
def topic():
    # The shared fixtures are English: the Spanish pipeline has its own
    # module. The channel default is Spanish, so this says so explicitly.
    engine = TopicEngine(history=[], language="en")
    # No number in the title: these fixtures are about script structure, and
    # a count in the topic is now a binding request that a short test render
    # could not honour.
    return engine.from_user_input(
        "Small Living Room Ideas That Make Any Space Look Bigger"
    )


@pytest.fixture
def script(topic):
    return generate_script(
        topic, duration_minutes=5.0, engine="template", seed=7, language="en"
    )


@pytest.fixture(scope="session")
def has_ffmpeg() -> bool:
    return ffmpeg_available()


def pytest_configure(config):  # noqa: D103
    config.addinivalue_line("markers", "integration: renders real video with FFmpeg")
