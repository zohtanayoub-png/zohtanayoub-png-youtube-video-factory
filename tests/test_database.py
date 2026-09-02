"""SQLite persistence and the repository-friendly JSON snapshots."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from vidfactory.database import Database, SNAPSHOT_TABLES


def test_schema_is_created_automatically(database):
    tables = {
        row["name"]
        for row in database.query("SELECT name FROM sqlite_master WHERE type='table'")
    }
    for expected in SNAPSHOT_TABLES:
        assert expected in tables


def test_initialisation_is_idempotent(tmp_path):
    path = tmp_path / "a.db"
    Database(path).close()
    db = Database(path)
    db.initialize()
    assert db.stats()["topics"] == 0
    db.close()


def test_topics_round_trip(database):
    database.add_topic("slug-1", "25 Small Living Room Ideas", "living rooms", "ideas", 25)
    assert database.has_topic_slug("slug-1")
    assert "25 Small Living Room Ideas" in database.topic_titles()


def test_adding_the_same_slug_twice_does_not_duplicate(database):
    database.add_topic("slug-1", "First title")
    database.add_topic("slug-1", "Updated title")
    assert database.stats()["topics"] == 1
    assert database.topic_titles()[0] == "Updated title"


def test_mark_topic_used(database):
    database.add_topic("slug-1", "A title")
    database.mark_topic_used("slug-1")
    row = database.query("SELECT status, used_at FROM topics WHERE slug='slug-1'")[0]
    assert row["status"] == "used"
    assert row["used_at"]


def test_clip_usage_is_counted(database):
    database.record_clip_use("pexels", "42", url="u", width=1920, height=1080, duration=10.0)
    database.record_clip_use("pexels", "42")
    count, last_used = database.clip_usage("pexels", "42")
    assert count == 2
    assert last_used is not None
    # Metadata from the first insert survives the second.
    row = database.get_clip("pexels", "42")
    assert row["width"] == 1920


def test_cooldown_detection(database):
    database.record_clip_use("pexels", "7")
    assert database.is_clip_on_cooldown("pexels", "7", cooldown_days=45) is True
    assert database.is_clip_on_cooldown("pexels", "7", cooldown_days=0) is False
    assert database.is_clip_on_cooldown("pexels", "never-used", cooldown_days=45) is False


def test_hash_lookup(database):
    database.record_clip_use("pexels", "9", content_hash="abc123")
    assert database.hash_seen("abc123") is True
    assert database.hash_seen("other") is False
    assert database.hash_seen("") is False


def test_videos_and_scenes(database):
    video_id = database.add_video(
        topic_slug="slug", title="A video", filename="final_video.mp4",
        duration=1200.0, word_count=3000, scene_count=90, clip_count=40,
    )
    assert video_id > 0
    database.add_scenes(video_id, [
        {"scene_id": "item-001-00", "narration": "text", "duration": 5.0,
         "primary_visual_query": "living room", "visual_category": "living rooms"},
    ])
    assert database.stats()["scenes"] == 1
    database.set_video_youtube_id(video_id, "abc123")
    row = database.query("SELECT youtube_id, status FROM videos WHERE id=?", (video_id,))[0]
    assert row["youtube_id"] == "abc123"
    assert row["status"] == "uploaded"


def test_generation_lifecycle(database):
    gid = database.start_generation("run-1", "a topic")
    database.finish_generation(gid, "success", "all good")
    row = database.query("SELECT status, finished_at FROM generations WHERE id=?", (gid,))[0]
    assert row["status"] == "success"
    assert row["finished_at"]


def test_state_export_and_import_round_trip(tmp_path):
    source = Database(tmp_path / "source.db")
    source.add_topic("slug-1", "25 Small Living Room Ideas", "living rooms")
    source.record_clip_use("pexels", "1", content_hash="hash-1")
    source.add_video(title="A video", topic_slug="slug-1")
    state_dir = tmp_path / "state"
    written = source.export_state(state_dir)
    assert len(written) == len(SNAPSHOT_TABLES)
    source.close()

    target = Database(tmp_path / "target.db")
    imported = target.import_state(state_dir)
    assert imported >= 3
    assert target.has_topic_slug("slug-1")
    assert target.hash_seen("hash-1")
    target.close()


def test_state_files_are_readable_json(tmp_path, database):
    database.add_topic("slug", "Title")
    state_dir = tmp_path / "state"
    database.export_state(state_dir)
    payload = json.loads((state_dir / "topics.json").read_text(encoding="utf-8"))
    assert payload["table"] == "topics"
    assert payload["rows"][0]["slug"] == "slug"


def test_import_ignores_a_corrupt_snapshot(tmp_path):
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    (state_dir / "topics.json").write_text("{not json", encoding="utf-8")
    db = Database(tmp_path / "t.db")
    assert db.import_state(state_dir) == 0
    db.close()


def test_import_of_a_missing_directory_is_safe(tmp_path, database):
    assert database.import_state(tmp_path / "does-not-exist") == 0


def test_import_ignores_unknown_columns(tmp_path):
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    (state_dir / "topics.json").write_text(
        json.dumps({"table": "topics", "rows": [
            {"id": 1, "slug": "s", "title": "T", "created_at": "2026-01-01T00:00:00+00:00",
             "status": "planned", "unexpected_column": "value"}
        ]}),
        encoding="utf-8",
    )
    db = Database(tmp_path / "t.db")
    assert db.import_state(state_dir) == 1
    assert db.has_topic_slug("s")
    db.close()


def test_repeated_import_is_idempotent(tmp_path, database):
    database.add_topic("slug", "Title")
    state_dir = tmp_path / "state"
    database.export_state(state_dir)
    database.import_state(state_dir)
    database.import_state(state_dir)
    assert database.stats()["topics"] == 1
