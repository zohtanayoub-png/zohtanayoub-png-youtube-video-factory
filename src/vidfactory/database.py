"""SQLite persistence + repository-friendly JSON snapshots.

GitHub Actions runners are ephemeral, so the durable copy of the history lives
in the repository as small JSON files under ``data/state/``. At the start of a
run those snapshots are imported into a local SQLite database; at the end the
database is exported back to JSON so the workflow can commit it.

That gives us real SQL for querying during a run and a merge-friendly,
diff-able, completely free durable store between runs.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

from .logging_utils import get_logger

log = get_logger("DB")

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_info (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS topics (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    slug          TEXT UNIQUE NOT NULL,
    title         TEXT NOT NULL,
    category      TEXT,
    angle         TEXT,
    item_count    INTEGER,
    created_at    TEXT NOT NULL,
    used_at       TEXT,
    status        TEXT NOT NULL DEFAULT 'planned'
);

CREATE TABLE IF NOT EXISTS videos (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    topic_slug     TEXT,
    title          TEXT NOT NULL,
    filename       TEXT,
    duration       REAL,
    word_count     INTEGER,
    scene_count    INTEGER,
    clip_count     INTEGER,
    created_at     TEXT NOT NULL,
    youtube_id     TEXT,
    status         TEXT NOT NULL DEFAULT 'rendered'
);

CREATE TABLE IF NOT EXISTS clips (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    provider       TEXT NOT NULL,
    provider_id    TEXT NOT NULL,
    url            TEXT,
    width          INTEGER,
    height         INTEGER,
    duration       REAL,
    content_hash   TEXT,
    first_used_at  TEXT,
    last_used_at   TEXT,
    use_count      INTEGER NOT NULL DEFAULT 0,
    last_topic     TEXT,
    UNIQUE(provider, provider_id)
);

CREATE TABLE IF NOT EXISTS scenes (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id     INTEGER,
    scene_id     TEXT NOT NULL,
    narration    TEXT NOT NULL,
    duration     REAL,
    query        TEXT,
    category     TEXT,
    FOREIGN KEY(video_id) REFERENCES videos(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS generations (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id        TEXT NOT NULL,
    topic         TEXT,
    started_at    TEXT NOT NULL,
    finished_at   TEXT,
    status        TEXT NOT NULL DEFAULT 'running',
    details       TEXT
);

CREATE INDEX IF NOT EXISTS idx_clips_provider ON clips(provider, provider_id);
CREATE INDEX IF NOT EXISTS idx_clips_hash ON clips(content_hash);
CREATE INDEX IF NOT EXISTS idx_topics_slug ON topics(slug);
"""

# Tables exported to / imported from JSON snapshots (in dependency order).
SNAPSHOT_TABLES: tuple[str, ...] = ("topics", "videos", "clips", "scenes", "generations")


def utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


class Database:
    """Thin, thread-safe wrapper around a SQLite file."""

    def __init__(self, path: str | os.PathLike[str] = "data/factory.db") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.execute("PRAGMA journal_mode = WAL")
        self.initialize()

    # ---------------------------------------------------------------- core
    def initialize(self) -> None:
        with self.transaction() as conn:
            conn.executescript(SCHEMA)
            # Migrations run here, before anything can read or write a row.
            # They used to run lazily, on the first record_clip_use, which is
            # after import_state - and import_state builds its column list from
            # PRAGMA table_info, so every load of the history silently dropped
            # test_use_count and test_last_used_at. That is how 420 clips ended
            # up recorded as never used at all: the release moved their count
            # out of use_count, and the next run's import threw away the column
            # it had been moved into.
            self._migrate_clip_modes(conn)
            conn.execute(
                "INSERT OR REPLACE INTO schema_info(key, value) VALUES('version', ?)",
                (str(SCHEMA_VERSION),),
            )

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            try:
                yield self._conn
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise

    def query(self, sql: str, params: Sequence[Any] = ()) -> list[sqlite3.Row]:
        with self._lock:
            return list(self._conn.execute(sql, params).fetchall())

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # -------------------------------------------------------------- topics
    def add_topic(
        self,
        slug: str,
        title: str,
        category: str | None = None,
        angle: str | None = None,
        item_count: int | None = None,
        status: str = "planned",
    ) -> int:
        with self.transaction() as conn:
            cur = conn.execute(
                """INSERT INTO topics(slug, title, category, angle, item_count, created_at, status)
                   VALUES(?,?,?,?,?,?,?)
                   ON CONFLICT(slug) DO UPDATE SET title=excluded.title""",
                (slug, title, category, angle, item_count, utcnow(), status),
            )
            if cur.lastrowid:
                return int(cur.lastrowid)
        row = self.query("SELECT id FROM topics WHERE slug = ?", (slug,))
        return int(row[0]["id"]) if row else 0

    def mark_topic_used(self, slug: str) -> None:
        with self.transaction() as conn:
            conn.execute(
                "UPDATE topics SET used_at = ?, status = 'used' WHERE slug = ?",
                (utcnow(), slug),
            )

    def topic_titles(self, limit: int = 500) -> list[str]:
        rows = self.query(
            "SELECT title FROM topics ORDER BY id DESC LIMIT ?", (int(limit),)
        )
        return [row["title"] for row in rows]

    def has_topic_slug(self, slug: str) -> bool:
        return bool(self.query("SELECT 1 FROM topics WHERE slug = ?", (slug,)))

    # --------------------------------------------------------------- clips
    # --------------------------------------------------------------- modes
    #: A render either counts towards the long-term footage cooldown or it
    #: does not. Sixteen development renders had already claimed a large slice
    #: of the good Pexels footage for 45 days before anything was published,
    #: which is a bill the real channel should never have been sent.
    PRODUCTION = "production"
    TEST = "test"

    def _migrate_clip_modes(self, conn: sqlite3.Connection) -> None:
        """Add the development-usage columns to a database that predates them."""

        existing = {row[1] for row in conn.execute("PRAGMA table_info(clips)")}
        if "test_use_count" not in existing:
            conn.execute(
                "ALTER TABLE clips ADD COLUMN test_use_count INTEGER NOT NULL DEFAULT 0"
            )
        if "test_last_used_at" not in existing:
            conn.execute("ALTER TABLE clips ADD COLUMN test_last_used_at TEXT")

    def get_clip(self, provider: str, provider_id: str) -> sqlite3.Row | None:
        rows = self.query(
            "SELECT * FROM clips WHERE provider = ? AND provider_id = ?",
            (provider, str(provider_id)),
        )
        return rows[0] if rows else None

    def clip_usage(self, provider: str, provider_id: str) -> tuple[int, datetime | None]:
        """Return ``(use_count, last_used_at)`` for a provider clip."""

        row = self.get_clip(provider, provider_id)
        if row is None:
            return 0, None
        return int(row["use_count"] or 0), _parse_ts(row["last_used_at"])

    def is_clip_on_cooldown(
        self, provider: str, provider_id: str, cooldown_days: float
    ) -> bool:
        _, last_used = self.clip_usage(provider, provider_id)
        if last_used is None or cooldown_days <= 0:
            return False
        return datetime.now(timezone.utc) - last_used < timedelta(days=cooldown_days)

    def hash_seen(self, content_hash: str) -> bool:
        if not content_hash:
            return False
        return bool(self.query("SELECT 1 FROM clips WHERE content_hash = ?", (content_hash,)))

    def record_clip_use(
        self,
        provider: str,
        provider_id: str,
        url: str | None = None,
        width: int | None = None,
        height: int | None = None,
        duration: float | None = None,
        content_hash: str | None = None,
        topic: str | None = None,
        mode: str = PRODUCTION,
    ) -> None:
        """Record that a clip was used.

        ``mode`` decides which set of columns moves. A test render still gets
        a row - knowing a clip was tried is useful - but it writes
        ``test_last_used_at``, which nothing consults when deciding whether
        footage is on cooldown. Only a production render touches
        ``last_used_at``.
        """

        now = utcnow()
        test = str(mode) == self.TEST
        with self.transaction() as conn:
            self._migrate_clip_modes(conn)
            conn.execute(
                """INSERT INTO clips(provider, provider_id, url, width, height, duration,
                                     content_hash, first_used_at, last_used_at, use_count,
                                     test_last_used_at, test_use_count, last_topic)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(provider, provider_id) DO UPDATE SET
                       url = COALESCE(excluded.url, clips.url),
                       width = COALESCE(excluded.width, clips.width),
                       height = COALESCE(excluded.height, clips.height),
                       duration = COALESCE(excluded.duration, clips.duration),
                       content_hash = COALESCE(excluded.content_hash, clips.content_hash),
                       last_used_at = COALESCE(excluded.last_used_at, clips.last_used_at),
                       use_count = clips.use_count + excluded.use_count,
                       test_last_used_at = COALESCE(
                           excluded.test_last_used_at, clips.test_last_used_at),
                       test_use_count = clips.test_use_count + excluded.test_use_count,
                       last_topic = COALESCE(excluded.last_topic, clips.last_topic)""",
                (
                    provider,
                    str(provider_id),
                    url,
                    width,
                    height,
                    duration,
                    content_hash,
                    now,
                    None if test else now,
                    0 if test else 1,
                    now if test else None,
                    1 if test else 0,
                    topic,
                ),
            )

    def clip_mode_stats(self) -> dict[str, int]:
        """How much of the footage history is production and how much is dev."""

        with self.transaction() as conn:
            self._migrate_clip_modes(conn)
        rows = self.query(
            "SELECT COUNT(*) AS n,"
            " SUM(CASE WHEN use_count > 0 THEN 1 ELSE 0 END) AS production,"
            " SUM(CASE WHEN test_use_count > 0 THEN 1 ELSE 0 END) AS test"
            " FROM clips"
        )
        row = rows[0] if rows else None
        return {
            "clips": int((row["n"] if row else 0) or 0),
            "production": int((row["production"] if row else 0) or 0),
            "test": int((row["test"] if row else 0) or 0),
        }

    def reclassify_clip_history(
        self,
        before: str | None = None,
        topics: Sequence[str] | None = None,
        dry_run: bool = False,
    ) -> dict[str, int]:
        """Move production footage usage into the development column.

        This is the repair for a cooldown that was filled by renders nobody
        published. It **moves** the usage rather than deleting it: the row, its
        counts and its timestamps all survive under ``test_*``, so the history
        of what was tried is intact and only the cooldown stops seeing it.

        ``before`` is an ISO timestamp; ``topics`` a list of topic slugs. With
        neither, every recorded production use moves, which is the right answer
        for a channel that has not published anything yet. Pass ``dry_run`` to
        count what would move without touching it.
        """

        clauses = ["use_count > 0"]
        params: list[Any] = []
        if before:
            clauses.append("last_used_at < ?")
            params.append(str(before))
        if topics:
            clauses.append(
                "last_topic IN (" + ",".join("?" for _ in topics) + ")"
            )
            params.extend(str(t) for t in topics)
        where = " AND ".join(clauses)

        with self.transaction() as conn:
            self._migrate_clip_modes(conn)
            affected = int(
                conn.execute(
                    f"SELECT COUNT(*) FROM clips WHERE {where}", params
                ).fetchone()[0]
            )
            if dry_run or not affected:
                return {"moved": 0, "would_move": affected}
            conn.execute(
                f"""UPDATE clips SET
                        test_use_count = test_use_count + use_count,
                        test_last_used_at = COALESCE(
                            MAX(COALESCE(test_last_used_at, ''), COALESCE(last_used_at, '')),
                            test_last_used_at),
                        use_count = 0,
                        last_used_at = NULL
                    WHERE {where}""",
                params,
            )
        log.info(
            "Moved %d clip(s) out of the production cooldown and into "
            "development history", affected,
        )
        return {"moved": affected, "would_move": affected}

    # -------------------------------------------------------------- videos
    def add_video(self, **fields: Any) -> int:
        payload = {
            "topic_slug": fields.get("topic_slug"),
            "title": fields.get("title", "untitled"),
            "filename": fields.get("filename"),
            "duration": fields.get("duration"),
            "word_count": fields.get("word_count"),
            "scene_count": fields.get("scene_count"),
            "clip_count": fields.get("clip_count"),
            "created_at": utcnow(),
            "youtube_id": fields.get("youtube_id"),
            "status": fields.get("status", "rendered"),
        }
        columns = ", ".join(payload)
        marks = ", ".join("?" for _ in payload)
        with self.transaction() as conn:
            cur = conn.execute(
                f"INSERT INTO videos({columns}) VALUES({marks})", tuple(payload.values())
            )
            return int(cur.lastrowid or 0)

    def set_video_youtube_id(self, video_id: int, youtube_id: str) -> None:
        with self.transaction() as conn:
            conn.execute(
                "UPDATE videos SET youtube_id = ?, status = 'uploaded' WHERE id = ?",
                (youtube_id, video_id),
            )

    def add_scenes(self, video_id: int, scenes: Iterable[dict[str, Any]]) -> None:
        rows = [
            (
                video_id,
                str(scene.get("scene_id")),
                scene.get("narration", ""),
                scene.get("duration"),
                scene.get("primary_visual_query"),
                scene.get("visual_category"),
            )
            for scene in scenes
        ]
        if not rows:
            return
        with self.transaction() as conn:
            conn.executemany(
                """INSERT INTO scenes(video_id, scene_id, narration, duration, query, category)
                   VALUES(?,?,?,?,?,?)""",
                rows,
            )

    # ---------------------------------------------------------- generations
    def start_generation(self, run_id: str, topic: str | None) -> int:
        with self.transaction() as conn:
            cur = conn.execute(
                "INSERT INTO generations(run_id, topic, started_at, status) VALUES(?,?,?,'running')",
                (run_id, topic, utcnow()),
            )
            return int(cur.lastrowid or 0)

    def finish_generation(self, generation_id: int, status: str, details: str = "") -> None:
        with self.transaction() as conn:
            conn.execute(
                "UPDATE generations SET finished_at = ?, status = ?, details = ? WHERE id = ?",
                (utcnow(), status, details[:4000], generation_id),
            )

    # ------------------------------------------------------------ snapshots
    def export_state(self, directory: str | os.PathLike[str]) -> list[Path]:
        """Write one JSON file per table so the repo can hold durable history."""

        out_dir = Path(directory)
        out_dir.mkdir(parents=True, exist_ok=True)
        written: list[Path] = []
        for table in SNAPSHOT_TABLES:
            rows = [dict(row) for row in self.query(f"SELECT * FROM {table} ORDER BY id")]
            target = out_dir / f"{table}.json"
            payload = {"table": table, "version": SCHEMA_VERSION, "rows": rows}
            target.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=False) + "\n",
                encoding="utf-8",
            )
            written.append(target)
        log.info("Exported %d state tables to %s", len(written), out_dir)
        return written

    def import_state(self, directory: str | os.PathLike[str]) -> int:
        """Load JSON snapshots back into SQLite. Existing rows are merged."""

        in_dir = Path(directory)
        if not in_dir.exists():
            return 0
        imported = 0
        for table in SNAPSHOT_TABLES:
            source = in_dir / f"{table}.json"
            if not source.exists():
                continue
            try:
                payload = json.loads(source.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                log.warning("Ignoring corrupt state snapshot: %s", source)
                continue
            rows = payload.get("rows") if isinstance(payload, dict) else payload
            if not isinstance(rows, list):
                continue
            valid_columns = {
                row["name"] for row in self.query(f"PRAGMA table_info({table})")
            }
            for row in rows:
                if not isinstance(row, dict):
                    continue
                clean = {k: v for k, v in row.items() if k in valid_columns}
                if not clean:
                    continue
                columns = ", ".join(clean)
                marks = ", ".join("?" for _ in clean)
                try:
                    with self.transaction() as conn:
                        conn.execute(
                            f"INSERT OR REPLACE INTO {table}({columns}) VALUES({marks})",
                            tuple(clean.values()),
                        )
                    imported += 1
                except sqlite3.Error as exc:  # pragma: no cover - defensive
                    log.warning("Skipped a %s row during import: %s", table, exc)
        if imported:
            log.info("Imported %d rows of persistent history", imported)
        return imported

    # ------------------------------------------------------------- reports
    def stats(self) -> dict[str, int]:
        return {
            table: int(self.query(f"SELECT COUNT(*) AS c FROM {table}")[0]["c"])
            for table in SNAPSHOT_TABLES
        }
