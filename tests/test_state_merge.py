"""Merging two histories without losing any of either one.

Both branches render videos, so both rewrite every line of
``data/state/*.json`` and git reports a conflict it cannot resolve. Taking a
side deletes real renders and real cooldown, so these tests pin the behaviour
that makes the union safe: natural keys instead of autoincrement ids, counters
added rather than overwritten, and nothing left pointing at a row that is no
longer there.
"""

from __future__ import annotations

import json

from vidfactory.database import Database
from vidfactory.state_merge import find_orphans, merge_state


def write(directory, table, rows):
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{table}.json").write_text(
        json.dumps({"table": table, "version": 1, "rows": rows}), encoding="utf-8"
    )


def clip(provider_id, use=0, test=0, last=None, first="2026-01-01T00:00:00+00:00", **extra):
    row = {
        "provider": "pexels",
        "provider_id": provider_id,
        "use_count": use,
        "test_use_count": test,
        "first_used_at": first,
        "last_used_at": last,
    }
    row.update(extra)
    return row


def video(title, created_at, **extra):
    row = {"title": title, "created_at": created_at, "topic_slug": "a-topic"}
    row.update(extra)
    return row


def _sides(tmp_path):
    return tmp_path / "base", tmp_path / "ours", tmp_path / "theirs", tmp_path / "out"


def test_videos_from_both_sides_survive(tmp_path):
    base, ours, theirs, out = _sides(tmp_path)
    write(base, "videos", [video("Shared", "2026-01-01T00:00:00+00:00", id=1)])
    write(ours, "videos", [
        video("Shared", "2026-01-01T00:00:00+00:00", id=1),
        video("Only on the branch", "2026-02-01T00:00:00+00:00", id=2),
    ])
    write(theirs, "videos", [
        video("Shared", "2026-01-01T00:00:00+00:00", id=1),
        video("Only on main", "2026-03-01T00:00:00+00:00", id=2),
    ])
    for side in (base, ours, theirs):
        write(side, "topics", [{"slug": "a-topic", "title": "A", "created_at": "2026-01-01T00:00:00+00:00"}])

    merge_state(base, ours, theirs, out)
    titles = {v["title"] for v in json.load(open(out / "videos.json"))["rows"]}
    assert titles == {"Shared", "Only on the branch", "Only on main"}


def test_the_same_autoincrement_id_is_not_treated_as_the_same_video(tmp_path):
    """Both sides numbered their rows from 1. They are different videos."""

    base, ours, theirs, out = _sides(tmp_path)
    write(base, "videos", [])
    write(ours, "videos", [video("Branch video", "2026-02-01T00:00:00+00:00", id=1)])
    write(theirs, "videos", [video("Main video", "2026-03-01T00:00:00+00:00", id=1)])

    merge_state(base, ours, theirs, out)
    rows = json.load(open(out / "videos.json"))["rows"]
    assert len(rows) == 2
    assert len({r["id"] for r in rows}) == 2, "ids must be reassigned, not collided"


def test_a_clip_both_sides_used_is_counted_twice(tmp_path):
    base, ours, theirs, out = _sides(tmp_path)
    write(base, "clips", [clip("1", use=1, last="2026-01-01T00:00:00+00:00")])
    write(ours, "clips", [clip("1", use=2, last="2026-02-01T00:00:00+00:00")])
    write(theirs, "clips", [clip("1", use=2, last="2026-03-01T00:00:00+00:00")])

    merge_state(base, ours, theirs, out)
    row = json.load(open(out / "clips.json"))["rows"][0]
    # 2 + 2 - 1: each side's own extra use, the shared one counted once.
    assert row["use_count"] == 3
    assert row["last_used_at"] == "2026-03-01T00:00:00+00:00"


def test_history_neither_side_touched_is_not_double_counted(tmp_path):
    base, ours, theirs, out = _sides(tmp_path)
    write(base, "clips", [clip("1", use=4, last="2026-01-01T00:00:00+00:00")])
    write(ours, "clips", [clip("1", use=4, last="2026-01-01T00:00:00+00:00")])
    write(theirs, "clips", [clip("1", use=4, last="2026-01-01T00:00:00+00:00")])

    merge_state(base, ours, theirs, out)
    assert json.load(open(out / "clips.json"))["rows"][0]["use_count"] == 4


def test_test_and_production_history_stay_separate(tmp_path):
    """A released development clip stays released; a production use stays production."""

    base, ours, theirs, out = _sides(tmp_path)
    write(base, "clips", [clip("1", use=1, last="2026-01-01T00:00:00+00:00")])
    # Our side released it out of the cooldown.
    write(ours, "clips", [clip("1", use=0, test=1, last=None, test_last_used_at="2026-01-01T00:00:00+00:00")])
    # Their side recorded a genuine production use afterwards.
    write(theirs, "clips", [clip("1", use=2, last="2026-03-01T00:00:00+00:00")])

    merge_state(base, ours, theirs, out)
    row = json.load(open(out / "clips.json"))["rows"][0]
    assert row["use_count"] == 1, "only the other side's new production use"
    assert row["test_use_count"] == 1, "the released development use survives"
    assert row["last_used_at"] == "2026-03-01T00:00:00+00:00"


def test_a_clip_with_no_production_use_is_not_on_cooldown(tmp_path):
    base, ours, theirs, out = _sides(tmp_path)
    write(base, "clips", [])
    write(ours, "clips", [clip("1", use=0, test=3, test_last_used_at="2026-02-01T00:00:00+00:00")])
    write(theirs, "clips", [])

    merge_state(base, ours, theirs, out)
    row = json.load(open(out / "clips.json"))["rows"][0]
    assert row["use_count"] == 0
    assert row["last_used_at"] is None

    database = Database(str(tmp_path / "f.db"))
    database.import_state(out)
    assert not database.is_clip_on_cooldown("pexels", "1", 45)


def test_a_clip_that_lost_its_count_keeps_its_history(tmp_path):
    """The import bug zeroed counts but never cleared first_used_at."""

    base, ours, theirs, out = _sides(tmp_path)
    write(base, "clips", [])
    write(ours, "clips", [clip("1", use=0, test=0, first="2026-02-01T00:00:00+00:00")])
    write(theirs, "clips", [])

    merge_state(base, ours, theirs, out)
    row = json.load(open(out / "clips.json"))["rows"][0]
    assert row["test_use_count"] == 1, "a clip with a first use was used"
    assert row["use_count"] == 0, "and the recovered use must not claim cooldown"


def test_a_clip_that_genuinely_never_ran_is_left_alone(tmp_path):
    base, ours, theirs, out = _sides(tmp_path)
    write(base, "clips", [])
    write(ours, "clips", [clip("1", use=0, test=0, first=None)])
    write(theirs, "clips", [])

    merge_state(base, ours, theirs, out)
    row = json.load(open(out / "clips.json"))["rows"][0]
    assert row["use_count"] == 0 and row["test_use_count"] == 0


def test_scenes_follow_their_video_to_its_new_id(tmp_path):
    base, ours, theirs, out = _sides(tmp_path)
    write(base, "videos", [])
    write(ours, "videos", [video("Branch", "2026-02-01T00:00:00+00:00", id=1)])
    write(theirs, "videos", [video("Main", "2026-03-01T00:00:00+00:00", id=1)])
    write(ours, "scenes", [
        {"id": 1, "video_id": 1, "scene_id": "item-001-00", "narration": "ours"}
    ])
    write(theirs, "scenes", [
        {"id": 1, "video_id": 1, "scene_id": "item-001-00", "narration": "theirs"}
    ])

    merge_state(base, ours, theirs, out)
    videos = {v["id"]: v["title"] for v in json.load(open(out / "videos.json"))["rows"]}
    scenes = json.load(open(out / "scenes.json"))["rows"]
    assert len(scenes) == 2, "both sides' scenes survive"
    narrations = {videos[s["video_id"]]: s["narration"] for s in scenes}
    assert narrations == {"Branch": "ours", "Main": "theirs"}


def test_a_scene_whose_video_is_missing_is_reported_not_shipped(tmp_path):
    base, ours, theirs, out = _sides(tmp_path)
    write(base, "videos", [])
    write(ours, "videos", [])
    write(theirs, "videos", [])
    write(ours, "scenes", [{"id": 1, "video_id": 99, "scene_id": "x", "narration": "orphan"}])

    report = merge_state(base, ours, theirs, out)
    assert report.orphan_scenes == 1
    assert json.load(open(out / "scenes.json"))["rows"] == []


def test_topics_and_generations_from_both_sides_survive(tmp_path):
    base, ours, theirs, out = _sides(tmp_path)
    write(base, "topics", [])
    write(ours, "topics", [{"slug": "ours", "title": "O", "created_at": "2026-02-01T00:00:00+00:00", "status": "used"}])
    write(theirs, "topics", [{"slug": "theirs", "title": "T", "created_at": "2026-03-01T00:00:00+00:00", "status": "planned"}])
    write(ours, "generations", [{"run_id": "run-7", "started_at": "2026-02-01T00:00:00+00:00", "status": "success"}])
    write(theirs, "generations", [{"run_id": "run-6", "started_at": "2026-03-01T00:00:00+00:00", "status": "success"}])

    merge_state(base, ours, theirs, out)
    assert {t["slug"] for t in json.load(open(out / "topics.json"))["rows"]} == {"ours", "theirs"}
    assert {g["run_id"] for g in json.load(open(out / "generations.json"))["rows"]} == {"run-6", "run-7"}


def test_a_topic_used_on_either_side_is_used(tmp_path):
    base, ours, theirs, out = _sides(tmp_path)
    write(base, "topics", [{"slug": "a", "title": "A", "created_at": "2026-01-01T00:00:00+00:00", "status": "planned"}])
    write(ours, "topics", [{"slug": "a", "title": "A", "created_at": "2026-01-01T00:00:00+00:00", "status": "planned"}])
    write(theirs, "topics", [{"slug": "a", "title": "A", "created_at": "2026-01-01T00:00:00+00:00",
                              "status": "used", "used_at": "2026-03-01T00:00:00+00:00"}])

    merge_state(base, ours, theirs, out)
    row = json.load(open(out / "topics.json"))["rows"][0]
    assert row["status"] == "used"
    assert row["used_at"] == "2026-03-01T00:00:00+00:00"


def test_the_committed_history_has_no_orphans():
    """The resolution that is actually in the repository."""

    orphans = find_orphans("data/state")
    assert orphans["scenes_without_a_video"] == []
    assert orphans["videos_without_a_topic"] == []
    assert orphans["duplicate_clips"] == []
    assert orphans["negative_use_counts"] == []
    assert orphans["clips_whose_cooldown_disagrees_with_their_use_count"] == []


def test_importing_the_committed_history_keeps_the_mode_columns(tmp_path):
    """The bug that destroyed 420 clips' counts: import ran before the migration."""

    database = Database(str(tmp_path / "f.db"))
    database.import_state("data/state")
    stats = database.clip_mode_stats()
    assert stats["clips"] > 0
    assert stats["test"] > 0, "development history must survive a round trip"


def test_the_measured_speech_rate_survives_an_export_and_import(tmp_path):
    """A measurement that lives only in the runner's database is not a measurement.

    schema_info was not in SNAPSHOT_TABLES, so run 23 measured 182 words per
    minute, wrote it to an ephemeral SQLite file, and the next render started
    again from the engine's declared 155 - which is exactly the 300s request
    that came out at 263s.
    """

    first = Database(str(tmp_path / "a.db"))
    first.initialize()
    first.record_speech_rate("piper", "en_US-hfc_female-medium", 798, 264.0)
    first.export_state(tmp_path / "state")

    second = Database(str(tmp_path / "b.db"))
    second.import_state(tmp_path / "state")
    assert second.measured_speech_rate("piper", "en_US-hfc_female-medium") > 150.0
