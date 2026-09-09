#!/usr/bin/env python3
"""Carry real frames of a finished reel out of a GitHub Actions runner.

The same trick ``inspect_frames.py`` uses for long-form, and the same reason:
the runner is gone by the time anyone reads the log, an artifact download is
not always available, and the only honest way to say "the title is in the
right place and the captions are legible" is to look at a frame.

A reel needs different sample points than a twenty-five minute video. Five
here, chosen by structure rather than by clock time:

    hook        two seconds in - the frame that decides whether anyone stays
    promise     the beat that says what they are about to get
    first-item  the first real piece of content
    mid-item    somewhere in the middle of the list
    cta         the last three seconds, where the follow is asked for

Plus the caption band and the title band at full resolution, because a
640-wide downscale turns a 3.4px outline into one pixel and makes perfectly
good captions look washed out.
"""

from __future__ import annotations

import base64
import json
import subprocess
import sys
from pathlib import Path
from typing import Sequence

#: Full-resolution bands, sampled once. These are the two things a downscale
#: lies about: the title's weight and the captions' outline.
BANDS: tuple[tuple[str, str], ...] = (
    ("title-band", "crop=1080:300:0:120"),
    ("caption-band", "crop=1080:320:0:1300"),
)


def newest(root: Path) -> Path | None:
    directories = [p for p in root.glob("*") if p.is_dir() and (p / "reel.mp4").exists()]
    if not directories:
        return None
    return max(directories, key=lambda p: p.stat().st_mtime)


def duration(video: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(video)],
        capture_output=True, text=True, check=False,
    ).stdout.strip()
    try:
        return float(out)
    except ValueError:
        return 0.0


def emit(name: str, path: Path, at: float, note: str = "") -> None:
    if not path.exists():
        print(f"::warning::no frame for {name}")
        return
    blob = base64.b64encode(path.read_bytes()).decode("ascii")
    print(f"FRAME-BEGIN {name} at={at:.1f}s bytes={path.stat().st_size}")
    if note:
        print(f"FRAME-TEXT {name} {note}")
    for index in range(0, len(blob), 200):
        print(f"FRAME-DATA {name} {blob[index:index + 200]}")
    print(f"FRAME-END {name}")


def grab(video: Path, at: float, target: Path, filters: str) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{at:.2f}", "-i", str(video),
         "-frames:v", "1", "-vf", filters, "-q:v", "5", str(target)],
        check=False,
    )


def beat_at(beats: list, at: float) -> tuple[int, dict]:
    """The beat being spoken at this second.

    By timestamp against the beat's own span, not by kind. Mapping kind to the
    first beat of that kind is what reported a frame of the *manzana* line as
    the *fresas* line, and sent a reviewer looking for the wrong defect.
    """

    for index, beat in enumerate(beats):
        first, last = float(beat.get("start", 0.0)), float(beat.get("end", 0.0))
        if last > first and first <= at < last:
            return index, beat
    return -1, {}


def describe(position: int, beat: dict, grounding: dict,
             segments: Sequence[dict] | None = None) -> str:
    """Everything a reviewer needs to judge one frame, on one line."""

    if not beat:
        return "no beat covers this timestamp"
    parts = [f"beat-{position:02d} [{beat.get('kind', '?')}] {beat.get('text', '')}"]
    row = grounding.get(f"beat-{position:02d}")
    if row:
        verdict = "PASS" if row.get("passed") else "FAIL"
        parts.append(
            f"requires={row.get('required_entity', '')} "
            f"source={','.join(row.get('sources', []) or []) or '-'} "
            # Which provider served this beat and what kind of asset it is.
            # "source=pexels:5615187" already carries the provider, but a
            # reviewer checking whether the second provider is really being
            # used should not have to parse keys to find out.
            f"via={'+'.join(row.get('providers', []) or []) or '-'}"
            f"/{'+'.join(sorted(set(row.get('media_types', []) or []))) or '-'} "
            # The seconds of the source that reached the screen, which is the
            # claim that matters: a clip containing the food and a crop
            # showing it are two different things.
            f"{_segments(segments or (), row.get('beat', ''))} "
            f"score={float(row.get('score', 0.0)):.2f} {verdict}"
        )
        # The four probes, separately. One combined number cannot tell a
        # reviewer whether the frame held an orange or an apple cake, and
        # those are different defects with different fixes.
        parts.append(
            "entity={:.2f} state={} context={} subject={:.2f}".format(
                float(row.get("entity_presence_score", 0.0)),
                f"{float(row.get('state_match_score', 0.0)):.2f}"
                if row.get("state_checked") else "-",
                f"{float(row.get('context_match_score', 0.0)):.2f}"
                if row.get("context_checked") else "-",
                float(row.get("dominant_subject_score", 0.0)),
            )
        )
        if row.get("required_attributes"):
            parts.append("must be " + "; ".join(row["required_attributes"][:2]))
        if not row.get("passed"):
            failed = ", ".join(row.get("failed_on") or []) or "grounding"
            looked = row.get("looked_like") or "something else"
            parts.append(f"FAILED ON {failed} - looked like {looked}")
    return " | ".join(parts)


def _segments(segments: Sequence[dict], beat: str) -> str:
    """The used crops of one beat, as "12.4-15.3s@1.00(moved)"."""

    rows = [r for r in segments if r.get("beat") == beat]
    if not rows:
        return "segment=-"
    parts = []
    for row in rows:
        moved = ",moved" if row.get("window_moved") else ""
        verdict = "" if row.get("segment_grounding_passed") else ",FAILED"
        parts.append(
            f"{float(row.get('source_start') or 0.0):.1f}-"
            f"{float(row.get('source_end') or 0.0):.1f}s@"
            f"{float(row.get('segment_grounding_score') or 0.0):.2f}{moved}{verdict}"
        )
    return "segment=" + "+".join(parts)


def main(argument: str) -> int:
    root = Path(argument)
    run_dir = root if (root / "reel.mp4").exists() else newest(root)
    if run_dir is None:
        print(f"::warning::no reel found under {root}")
        return 0
    video = run_dir / "reel.mp4"
    total = duration(video)
    print(f"REEL {video} duration={total:.2f}s")

    script = {}
    script_path = run_dir / "script.json"
    if script_path.exists():
        try:
            script = json.loads(script_path.read_text(encoding="utf-8"))
        except Exception:                                  # pragma: no cover
            script = {}
    beats = script.get("beats", [])
    report = {}
    report_path = run_dir / "reel_quality_report.json"
    if report_path.exists():
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except Exception:                                  # pragma: no cover
            report = {}
    grounding = {
        str(row.get("beat", "")): row
        for row in report.get("item_grounding_results", []) or []
    }
    # The crops that actually reached the screen, per shot rather than per
    # beat: a beat with two shots has two of them, and either can be the one
    # a reviewer is looking at.
    used_segments = list(report.get("used_segment_results", []) or [])

    # One frame per beat, sampled in the middle of the beat and labelled with
    # the beat that timestamp actually lands in. Every item beat is sampled,
    # because "does the apple line show an apple" is a question about the
    # apple line and no other.
    samples: list[tuple[str, float]] = []
    for index, beat in enumerate(beats):
        kind = str(beat.get("kind", ""))
        if kind in ("lead", "retention"):
            continue
        first, last = float(beat.get("start", 0.0)), float(beat.get("end", 0.0))
        if last <= first:
            continue
        name = f"{index:02d}-{kind}"
        if kind == "item" and beat.get("item_key"):
            name = f"{index:02d}-item-{beat['item_key']}"
        samples.append((name, first + (last - first) / 2.0))

    if not samples:                                        # pragma: no cover
        samples = [("mid", total * 0.5)]

    for name, at in samples:
        at = max(0.3, min(at, max(0.3, total - 0.2)))
        position, beat = beat_at(beats, at)
        frame = run_dir / f"inspect-{name}.jpg"
        # Scaled to 540 wide: half the reel's own width, which keeps the log
        # payload reasonable and the layout readable.
        grab(video, at, frame, "scale=540:-2")
        emit(name, frame, at, describe(position, beat, grounding, used_segments))

    mid = max(0.5, total * 0.45)
    for name, filters in BANDS:
        band = run_dir / f"inspect-{name}.jpg"
        grab(video, mid, band, filters)
        emit(name, band, mid,
             script.get("top_title", "") if name == "title-band"
             else "captions at full resolution")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "output/reels"))
