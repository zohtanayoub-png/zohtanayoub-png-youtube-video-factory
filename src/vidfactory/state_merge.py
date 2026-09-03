"""Merging two divergent copies of the persistent history.

``data/state/*.json`` is the durable record of everything the factory has ever
made: which topics were used, which Pexels clips were spent and when, which
videos exist, their scenes, and every generation attempt. Two branches that
both rendered videos have two histories, and git cannot merge them - it sees
two rewritten JSON arrays and reports a conflict on almost every line.

Taking one side is data loss. ``--ours`` throws away the other branch's
renders; ``--theirs`` throws away this one's. So does the obvious repair of
importing both snapshots into one database, because
:meth:`Database.import_state` keys on the autoincrement ``id`` and the two
sides numbered their rows independently - one branch's ``videos.id = 3`` and
the other's are different videos, and ``INSERT OR REPLACE`` would silently
keep one.

This module merges on the **natural** key instead:

===============  ==========================================================
topics           ``slug`` (UNIQUE in the schema)
clips            ``(provider, provider_id)`` (UNIQUE in the schema)
videos           ``(created_at, title)`` - two renders cannot share both
scenes           carried with their video, renumbered to follow it
generations      ``(run_id, started_at)`` - a run id can be retried
===============  ==========================================================

Counters get three-way arithmetic rather than a maximum. A clip both sides
used once has been used twice, but a clip the *base* already recorded and
neither side touched has still only been used once, so the merged count is

    ours + theirs - base

which is the only formula that neither loses a use nor invents one. The same
reasoning keeps ``test_use_count`` separate from ``use_count``: development
renders that were released out of the cooldown stay released, and a production
use recorded on the other side stays production.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

from .database import SNAPSHOT_TABLES, Database
from .logging_utils import get_logger

log = get_logger("MERGE")

Row = dict[str, Any]


def read_snapshot(directory: str | Path, table: str) -> list[Row]:
    """Rows for one table, or an empty list when the side has no such file."""

    source = Path(directory) / f"{table}.json"
    if not source.exists():
        return []
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        log.warning("Ignoring corrupt snapshot: %s", source)
        return []
    rows = payload.get("rows") if isinstance(payload, dict) else payload
    return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []


def _text(value: Any) -> str:
    return "" if value is None else str(value)


def _later(left: Any, right: Any) -> Any:
    """The later of two ISO timestamps, treating missing as earliest."""

    a, b = _text(left), _text(right)
    if not a:
        return right if b else left
    if not b:
        return left
    return left if a >= b else right


def _earlier(left: Any, right: Any) -> Any:
    a, b = _text(left), _text(right)
    if not a:
        return right if b else left
    if not b:
        return left
    return left if a <= b else right


def _count(row: Row | None, field_name: str) -> int:
    if not row:
        return 0
    try:
        return int(row.get(field_name) or 0)
    except (TypeError, ValueError):
        return 0


def _three_way_count(
    ours: Row | None, theirs: Row | None, base: Row | None, field_name: str
) -> int:
    """``ours + theirs - base``, never negative.

    Each side's own increment is preserved and the history they share is
    counted once. Taking the maximum instead would lose a use whenever both
    sides used the same clip.
    """

    merged = (
        _count(ours, field_name) + _count(theirs, field_name) - _count(base, field_name)
    )
    return max(0, merged)


# ---------------------------------------------------------------------------
# Natural keys
# ---------------------------------------------------------------------------

def _topic_key(row: Row) -> str:
    return _text(row.get("slug")).lower()


def _clip_key(row: Row) -> str:
    return f"{_text(row.get('provider')).lower()}:{_text(row.get('provider_id'))}"


def _video_key(row: Row) -> str:
    return f"{_text(row.get('created_at'))}|{_text(row.get('title'))}"


def _generation_key(row: Row) -> str:
    return f"{_text(row.get('run_id'))}|{_text(row.get('started_at'))}"


KEYS: dict[str, Callable[[Row], str]] = {
    "topics": _topic_key,
    "clips": _clip_key,
    "videos": _video_key,
    "generations": _generation_key,
}


def _index(rows: Iterable[Row], key: Callable[[Row], str]) -> dict[str, Row]:
    out: dict[str, Row] = {}
    for row in rows:
        out[key(row)] = row
    return out


# ---------------------------------------------------------------------------
# Per-table merges
# ---------------------------------------------------------------------------

def _merge_topic(ours: Row | None, theirs: Row | None, base: Row | None) -> Row:
    """A topic used on either side is used, and keeps the earlier creation."""

    merged = dict(theirs or {})
    merged.update({k: v for k, v in (ours or {}).items() if v is not None})
    merged["created_at"] = _earlier(
        (ours or {}).get("created_at"), (theirs or {}).get("created_at")
    )
    merged["used_at"] = _later(
        (ours or {}).get("used_at"), (theirs or {}).get("used_at")
    )
    statuses = {_text((ours or {}).get("status")), _text((theirs or {}).get("status"))}
    merged["status"] = "used" if "used" in statuses else (
        next((s for s in statuses if s), "planned")
    )
    return merged


def _merge_clip(ours: Row | None, theirs: Row | None, base: Row | None) -> Row:
    """Union the metadata, add up the uses, keep the widest time span."""

    merged = dict(theirs or {})
    for field_name, value in (ours or {}).items():
        if value is not None:
            merged[field_name] = value
    # Metadata: prefer whichever side actually recorded something.
    for field_name in ("url", "width", "height", "duration", "content_hash", "last_topic"):
        merged[field_name] = (
            (ours or {}).get(field_name)
            if (ours or {}).get(field_name) is not None
            else (theirs or {}).get(field_name)
        )
    merged["first_used_at"] = _earlier(
        (ours or {}).get("first_used_at"), (theirs or {}).get("first_used_at")
    )
    # The cooldown reads last_used_at, so it has to be the most recent
    # *production* use either side recorded - and stay empty when neither did,
    # which is what a released development clip looks like.
    merged["last_used_at"] = _later(
        (ours or {}).get("last_used_at"), (theirs or {}).get("last_used_at")
    )
    merged["test_last_used_at"] = _later(
        (ours or {}).get("test_last_used_at"), (theirs or {}).get("test_last_used_at")
    )
    merged["use_count"] = _three_way_count(ours, theirs, base, "use_count")
    merged["test_use_count"] = _three_way_count(ours, theirs, base, "test_use_count")

    # A clip cannot become less used than it already was. Before the migration
    # ran at initialize() rather than lazily, import_state built its column
    # list before test_use_count existed and dropped it, so releasing a
    # development clip took the count out of use_count and the next import
    # threw away the column it had been moved into - 420 clips ended up
    # recorded as never used at all. Their uses were development uses, so the
    # shortfall is restored as development history, where it does not put
    # anything back on the production cooldown.
    def total(row: Row | None) -> int:
        return _count(row, "use_count") + _count(row, "test_use_count")

    ever = max(total(base), total(ours), total(theirs))
    shortfall = ever - (merged["use_count"] + merged["test_use_count"])
    if shortfall > 0:
        merged["test_use_count"] += shortfall
        merged["test_last_used_at"] = _later(
            merged.get("test_last_used_at"),
            _later((base or {}).get("last_used_at"), (theirs or {}).get("last_used_at")),
        )

    # Same damage, one step further on: a clip the branch first used after the
    # snapshots diverged has no row on either other side to compare against, so
    # the arithmetic above has nothing to restore from. Its first_used_at
    # survived - the release never cleared it - and a clip with a first use and
    # a topic attached was used at least once. Recording exactly one
    # development use is the smallest claim consistent with that evidence, and
    # it keeps the clip out of the production cooldown where it belongs.
    if (
        merged["use_count"] + merged["test_use_count"] == 0
        and _text(merged.get("first_used_at"))
    ):
        merged["test_use_count"] = 1
        merged["test_last_used_at"] = _later(
            merged.get("test_last_used_at"), merged.get("first_used_at")
        )

    if not merged["use_count"]:
        # No production use survives, so nothing may hold it on cooldown.
        merged["last_used_at"] = None
    return merged


def _merge_video(ours: Row | None, theirs: Row | None, base: Row | None) -> Row:
    merged = dict(theirs or {})
    for field_name, value in (ours or {}).items():
        if value is not None:
            merged[field_name] = value
    # An upload that happened on either side happened.
    merged["youtube_id"] = (ours or {}).get("youtube_id") or (theirs or {}).get("youtube_id")
    return merged


def _merge_generation(ours: Row | None, theirs: Row | None, base: Row | None) -> Row:
    merged = dict(theirs or {})
    for field_name, value in (ours or {}).items():
        if value is not None:
            merged[field_name] = value
    merged["finished_at"] = _later(
        (ours or {}).get("finished_at"), (theirs or {}).get("finished_at")
    )
    return merged


MERGERS: dict[str, Callable[[Row | None, Row | None, Row | None], Row]] = {
    "topics": _merge_topic,
    "clips": _merge_clip,
    "videos": _merge_video,
    "generations": _merge_generation,
}


@dataclass
class MergeReport:
    """What the merge did, per table."""

    counts: dict[str, dict[str, int]] = field(default_factory=dict)
    orphan_scenes: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {"tables": self.counts, "orphan_scenes_dropped": self.orphan_scenes}

    def describe(self) -> str:
        lines = []
        for table, numbers in self.counts.items():
            lines.append(
                f"  {table}: {numbers['merged']} rows "
                f"(ours {numbers['ours']}, theirs {numbers['theirs']}, "
                f"both {numbers['shared']})"
            )
        if self.orphan_scenes:
            lines.append(f"  dropped {self.orphan_scenes} scene(s) with no video")
        return "\n".join(lines)


def merge_state(
    base_dir: str | Path,
    ours_dir: str | Path,
    theirs_dir: str | Path,
    out_dir: str | Path,
    database_path: str | Path = ":memory:",
) -> MergeReport:
    """Union two histories and write the result through the real exporter.

    The merged rows are loaded into an actual :class:`Database` and written
    back out with :meth:`Database.export_state`, so the resolved files are
    byte-for-byte the shape the pipeline itself produces rather than something
    a merge script invented.
    """

    report = MergeReport()
    merged_tables: dict[str, list[Row]] = {}

    for table in ("topics", "clips", "videos", "generations"):
        key = KEYS[table]
        ours = _index(read_snapshot(ours_dir, table), key)
        theirs = _index(read_snapshot(theirs_dir, table), key)
        base = _index(read_snapshot(base_dir, table), key)
        merge = MERGERS[table]

        rows: list[Row] = []
        for natural in sorted(set(ours) | set(theirs)):
            rows.append(merge(ours.get(natural), theirs.get(natural), base.get(natural)))
        merged_tables[table] = rows
        report.counts[table] = {
            "ours": len(ours),
            "theirs": len(theirs),
            "shared": len(set(ours) & set(theirs)),
            "merged": len(rows),
        }

    # Videos are renumbered, so their scenes have to follow. A scene is
    # identified by the video it belongs to, and its old id means nothing once
    # both sides' numbering is thrown away.
    video_ids: dict[str, int] = {}
    for position, row in enumerate(merged_tables["videos"], start=1):
        video_ids[_video_key(row)] = position
        row["id"] = position

    scenes: list[Row] = []
    seen_scenes: set[tuple[int, str]] = set()
    for side, directory in (("ours", ours_dir), ("theirs", theirs_dir)):
        videos_by_old_id = {
            int(v["id"]): _video_key(v)
            for v in read_snapshot(directory, "videos")
            if v.get("id") is not None
        }
        for row in read_snapshot(directory, "scenes"):
            natural = videos_by_old_id.get(int(row.get("video_id") or 0))
            new_id = video_ids.get(natural or "")
            if new_id is None:
                report.orphan_scenes += 1
                continue
            marker = (new_id, _text(row.get("scene_id")))
            if marker in seen_scenes:
                continue
            seen_scenes.add(marker)
            carried = dict(row)
            carried["video_id"] = new_id
            carried.pop("id", None)
            scenes.append(carried)
    merged_tables["scenes"] = scenes
    report.counts["scenes"] = {
        "ours": len(read_snapshot(ours_dir, "scenes")),
        "theirs": len(read_snapshot(theirs_dir, "scenes")),
        "shared": 0,
        "merged": len(scenes),
    }

    # Renumber everything else in a stable order too, so the exported files do
    # not depend on which side happened to be checked out.
    for table in ("topics", "clips", "generations"):
        for position, row in enumerate(merged_tables[table], start=1):
            row["id"] = position
    for position, row in enumerate(merged_tables["scenes"], start=1):
        row["id"] = position

    database = Database(database_path)
    database.initialize()
    with database.transaction() as conn:
        database._migrate_clip_modes(conn)
        for table in SNAPSHOT_TABLES:
            rows = merged_tables.get(table, [])
            if not rows:
                continue
            valid = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
            for row in rows:
                clean = {k: v for k, v in row.items() if k in valid}
                columns = ", ".join(clean)
                marks = ", ".join("?" for _ in clean)
                conn.execute(
                    f"INSERT OR REPLACE INTO {table}({columns}) VALUES({marks})",
                    tuple(clean.values()),
                )
    database.export_state(out_dir)
    log.info("Merged persistent history:\n%s", report.describe())
    return report


def find_orphans(directory: str | Path) -> dict[str, list[Any]]:
    """Records that point at something which is not there.

    Run after a merge. A scene whose video was dropped, or a video whose topic
    never made it across, is exactly the damage a careless resolution causes,
    and it is silent unless something looks for it.
    """

    videos = read_snapshot(directory, "videos")
    topics = read_snapshot(directory, "topics")
    scenes = read_snapshot(directory, "scenes")
    clips = read_snapshot(directory, "clips")

    video_ids = {int(v["id"]) for v in videos if v.get("id") is not None}
    topic_slugs = {_text(t.get("slug")).lower() for t in topics}

    orphan_scenes = [
        s.get("id") for s in scenes if int(s.get("video_id") or 0) not in video_ids
    ]
    orphan_videos = [
        v.get("id")
        for v in videos
        if _text(v.get("topic_slug")) and _text(v.get("topic_slug")).lower() not in topic_slugs
    ]
    duplicate_clips: list[Any] = []
    seen: set[str] = set()
    for clip in clips:
        marker = _clip_key(clip)
        if marker in seen:
            duplicate_clips.append(marker)
        seen.add(marker)
    negative_counts = [
        _clip_key(c)
        for c in clips
        if _count(c, "use_count") < 0 or _count(c, "test_use_count") < 0
    ]
    # A clip on production cooldown must say when it was last used, and one
    # with no production use must not.
    inconsistent_cooldown = [
        _clip_key(c)
        for c in clips
        if bool(_count(c, "use_count")) != bool(_text(c.get("last_used_at")))
    ]
    return {
        "scenes_without_a_video": orphan_scenes,
        "videos_without_a_topic": orphan_videos,
        "duplicate_clips": duplicate_clips,
        "negative_use_counts": negative_counts,
        "clips_whose_cooldown_disagrees_with_their_use_count": inconsistent_cooldown,
    }
