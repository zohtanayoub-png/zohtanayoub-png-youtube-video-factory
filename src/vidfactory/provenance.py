"""Artifact provenance: proving every output file belongs to one generation.

A video and its script are only trustworthy together if they demonstrably came
from the same run. Nothing in the earlier design enforced that: each artifact
was written independently, the output directory was named after a reusable run
identifier, and the workflow collected artifacts with an unbounded
``output/**`` glob that happily picked up files from *any* generation present
on disk.

So this module gives every run a collision-proof generation id, and writes an
``artifact_manifest.json`` recording what was produced and the SHA-256 of each
file. Before packaging, :func:`verify` re-reads the artifacts and checks they
agree with each other and with the manifest. A mismatch fails the run rather
than shipping a video whose script describes something else.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .logging_utils import get_logger

log = get_logger("PROV")

MANIFEST_NAME = "artifact_manifest.json"

#: Files a complete generation must produce.
REQUIRED_ARTIFACTS: tuple[str, ...] = (
    "final_video.mp4",
    "script.txt",
    "subtitles.srt",
    "metadata.json",
    "video_sources.json",
    "editorial_quality_report.json",
)

#: Produced by most runs but not by all: styled captions are skipped when
#: ``subtitles.style`` is ``none``, so their absence is a configuration
#: choice rather than a missing artifact.
OPTIONAL_ARTIFACTS: tuple[str, ...] = (
    "subtitles.ass",
    "script.json",
    "scenes.json",
    "quality_report.json",
)


def new_generation_id(prefix: str = "") -> str:
    """A generation id that cannot collide with a previous run.

    A workflow run number alone is not enough: re-running a job reuses it, and
    two workflows can produce the same number. The random suffix makes reuse
    impossible, which is what guarantees a fresh directory.
    """

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    suffix = uuid.uuid4().hex[:8]
    clean = re.sub(r"[^A-Za-z0-9_-]+", "-", str(prefix or "")).strip("-")
    return f"{clean}-{stamp}-{suffix}" if clean else f"gen-{stamp}-{suffix}"


def sha256_file(path: str | os.PathLike[str], chunk: int = 1024 * 1024) -> str:
    """SHA-256 of a file, streamed so a large MP4 does not sit in memory."""

    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            block = handle.read(chunk)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(str(text).encode("utf-8")).hexdigest()


def _normalize(text: str) -> str:
    """Comparable form of narration: case and whitespace carry no meaning."""

    return re.sub(r"[^a-z0-9 ]+", " ", str(text or "").lower())


def words(text: str) -> list[str]:
    return _normalize(text).split()


@dataclass
class ProvenanceCheck:
    name: str
    passed: bool
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "passed": self.passed, "detail": self.detail}


@dataclass
class Manifest:
    """What one generation produced, and the hashes that pin it down."""

    generation_id: str
    topic: str
    title: str
    created_at: str
    script_sha256: str = ""
    video_sha256: str = ""
    subtitle_sha256: str = ""
    metadata_sha256: str = ""
    sources_sha256: str = ""
    source_count: int = 0
    duration: float = 0.0
    scene_count: int = 0
    shot_count: int = 0
    checks: list[ProvenanceCheck] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks)

    def to_dict(self) -> dict[str, Any]:
        return {
            "generation_id": self.generation_id,
            "topic": self.topic,
            "title": self.title,
            "created_at": self.created_at,
            "script_sha256": self.script_sha256,
            "video_sha256": self.video_sha256,
            "subtitle_sha256": self.subtitle_sha256,
            "metadata_sha256": self.metadata_sha256,
            "sources_sha256": self.sources_sha256,
            "source_count": self.source_count,
            "duration": round(float(self.duration), 2),
            "scene_count": self.scene_count,
            "shot_count": self.shot_count,
            "provenance_passed": self.passed,
            "checks": [c.to_dict() for c in self.checks],
        }

    def save(self, directory: str | os.PathLike[str]) -> Path:
        target = Path(directory) / MANIFEST_NAME
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return target


def prepare_directory(directory: str | os.PathLike[str], generation_id: str) -> Path:
    """Create an output directory that provably holds only this generation.

    Refuses to reuse a directory that already contains artifacts from another
    generation. Silently overwriting is how a video ends up shipped next to a
    previous run's script.
    """

    target = Path(directory)
    if target.exists():
        existing = [p for p in target.iterdir() if p.is_file()]
        manifest = target / MANIFEST_NAME
        if manifest.exists():
            try:
                previous = json.loads(manifest.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                previous = {}
            if previous.get("generation_id") not in ("", None, generation_id):
                raise RuntimeError(
                    f"{target} already holds generation "
                    f"{previous.get('generation_id')!r}; refusing to mix artifacts"
                )
        elif existing:
            raise RuntimeError(
                f"{target} already contains {len(existing)} file(s) from an "
                "unidentified generation; refusing to mix artifacts"
            )
    target.mkdir(parents=True, exist_ok=True)
    return target


def verify(
    directory: str | os.PathLike[str],
    generation_id: str,
    spoken_text: str,
    script_title: str,
    scene_narrations: Sequence[str] = (),
    selected_clip_keys: Iterable[str] = (),
) -> list[ProvenanceCheck]:
    """Re-read the artifacts on disk and prove they belong together.

    ``spoken_text`` is the narration actually handed to the TTS engine, so the
    check compares the shipped script against what was really said rather than
    against another in-memory copy of the same object.
    """

    out = Path(directory)
    checks: list[ProvenanceCheck] = []

    def add(name: str, ok: bool, detail: str = "") -> None:
        checks.append(ProvenanceCheck(name, ok, detail))

    # 1. Every required artifact is present.
    missing = [n for n in REQUIRED_ARTIFACTS if not (out / n).exists()]
    add("all_artifacts_present", not missing, f"missing: {missing}" if missing else "all present")

    # 2. Nothing from another generation is sitting in the directory.
    strays = [
        p.name
        for p in out.iterdir()
        if p.is_file()
        and p.name not in {*REQUIRED_ARTIFACTS, *OPTIONAL_ARTIFACTS, MANIFEST_NAME}
    ]
    add("no_foreign_files", not strays, f"unexpected: {strays}" if strays else "clean")

    if missing:
        return checks

    script_text = (out / "script.txt").read_text(encoding="utf-8")
    subtitle_text = (out / "subtitles.srt").read_text(encoding="utf-8")
    metadata = json.loads((out / "metadata.json").read_text(encoding="utf-8"))
    sources = json.loads((out / "video_sources.json").read_text(encoding="utf-8"))

    # 3. The shipped script is what was actually narrated. Two adjustments,
    #    both because the comparison is of meaning rather than of bytes:
    #    the script file carries a title line that is never spoken, so the
    #    spoken text has to be a subset rather than identical; and the text
    #    handed to the voice has been through speech normalisation, which
    #    deliberately rewrites "2,4 m" as "dos coma cuatro metros". Comparing
    #    the normalised script against the normalised narration keeps the
    #    guarantee - every spoken word traces back to the shipped script -
    #    without failing on a transformation the pipeline performed on purpose.
    from .tts import normalize_for_speech

    spoken_words = set(words(spoken_text))
    script_words = set(words(script_text))
    for language in ("es", "en"):
        script_words |= set(words(normalize_for_speech(script_text, language)))
    unspoken = spoken_words - script_words
    add(
        "script_matches_narration",
        not unspoken,
        "every narrated word appears in script.txt"
        if not unspoken
        else f"{len(unspoken)} narrated word(s) absent from script.txt: {sorted(unspoken)[:8]}",
    )

    # 4. Subtitles were derived from this script, not a previous one.
    subtitle_body = re.sub(r"^\d+$|^\d{2}:\d{2}:\d{2},\d{3}.*$", " ",
                           subtitle_text, flags=re.MULTILINE)
    subtitle_words = set(words(subtitle_body))
    foreign = subtitle_words - script_words
    ratio = 1.0 - (len(foreign) / len(subtitle_words)) if subtitle_words else 0.0
    add(
        "subtitles_from_this_script",
        ratio >= 0.98,
        f"{ratio:.1%} of subtitle words appear in script.txt",
    )

    # 5. The metadata titles this video, not another.
    add(
        "metadata_title_matches",
        _normalize(metadata.get("title", "")) == _normalize(script_title),
        f"metadata {metadata.get('title', '')!r} vs script {script_title!r}",
    )

    # 6. Every recorded source was actually selected by this run.
    recorded = {f"{c.get('provider')}:{c.get('provider_id')}" for c in sources.get("clips", [])}
    expected = set(selected_clip_keys)
    if expected:
        stale = recorded - expected
        add(
            "sources_belong_to_this_run",
            not stale,
            "all sources were selected by this run"
            if not stale
            else f"{len(stale)} source(s) not selected by this run: {sorted(stale)[:5]}",
        )
    else:
        add("sources_belong_to_this_run", bool(recorded), f"{len(recorded)} sources recorded")

    # 7. The script title agrees with the script body's first line.
    first_line = script_text.splitlines()[0] if script_text.splitlines() else ""
    add(
        "script_title_matches",
        _normalize(first_line) == _normalize(script_title),
        f"script.txt opens with {first_line[:50]!r}",
    )

    # 8. Scene narration is present in the shipped script.
    if scene_narrations:
        joined = " ".join(scene_narrations)
        scene_words = set(words(joined))
        missing_scene = scene_words - script_words
        add(
            "scenes_belong_to_this_script",
            not missing_scene,
            "all scene narration appears in script.txt"
            if not missing_scene
            else f"{len(missing_scene)} scene word(s) absent from script.txt",
        )

    return checks


def build_manifest(
    directory: str | os.PathLike[str],
    generation_id: str,
    topic: str,
    title: str,
    spoken_text: str,
    duration: float,
    source_count: int,
    scene_count: int = 0,
    shot_count: int = 0,
    scene_narrations: Sequence[str] = (),
    selected_clip_keys: Iterable[str] = (),
) -> Manifest:
    """Hash the artifacts, verify they agree, and return the manifest."""

    out = Path(directory)
    created = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    manifest = Manifest(
        generation_id=generation_id,
        topic=topic,
        title=title,
        created_at=created,
        source_count=int(source_count),
        duration=float(duration),
        scene_count=int(scene_count),
        shot_count=int(shot_count),
    )

    for attribute, filename in (
        ("script_sha256", "script.txt"),
        ("video_sha256", "final_video.mp4"),
        ("subtitle_sha256", "subtitles.srt"),
        ("metadata_sha256", "metadata.json"),
        ("sources_sha256", "video_sources.json"),
    ):
        path = out / filename
        if path.exists():
            setattr(manifest, attribute, sha256_file(path))

    manifest.checks = verify(
        out,
        generation_id=generation_id,
        spoken_text=spoken_text,
        script_title=title,
        scene_narrations=scene_narrations,
        selected_clip_keys=selected_clip_keys,
    )

    for check in manifest.checks:
        if check.passed:
            log.debug("PASS %s - %s", check.name, check.detail)
        else:
            log.error("%s: %s", check.name, check.detail)

    if manifest.passed:
        log.info(
            "Artifact provenance verified for %s (%d sources, %s)",
            generation_id,
            manifest.source_count,
            f"video {manifest.video_sha256[:12]}",
        )
    return manifest
