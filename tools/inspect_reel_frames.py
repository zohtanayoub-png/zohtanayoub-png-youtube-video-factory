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

#: Where in the reel to sample, as a fraction of the finished duration, with
#: the two ends pinned to real seconds instead.
SAMPLES: tuple[tuple[str, float], ...] = (
    ("hook", 0.0),
    ("answer", 0.16),
    ("first-item", 0.35),
    ("mid-item", 0.60),
    ("takeaway", 0.85),
    ("cta", 1.0),
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
    by_kind = {}
    for beat in beats:
        by_kind.setdefault(beat.get("kind"), beat.get("text", ""))

    notes = {
        "hook": by_kind.get("hook", ""),
        "answer": by_kind.get("answer", ""),
        "first-item": by_kind.get("item", ""),
        "mid-item": by_kind.get("item", ""),
        "takeaway": by_kind.get("takeaway", ""),
        "cta": by_kind.get("cta", ""),
    }

    for name, fraction in SAMPLES:
        if name == "hook":
            at = min(2.0, max(0.5, total * 0.05))
        elif name == "cta":
            at = max(0.5, total - 2.0)
        else:
            at = max(0.5, total * fraction)
        frame = run_dir / f"inspect-{name}.jpg"
        # Scaled to 540 wide: half the reel's own width, which keeps the log
        # payload reasonable and the layout readable.
        grab(video, at, frame, "scale=540:-2")
        emit(name, frame, at, notes.get(name, ""))

    # Full resolution bands: the title across the top and the captions where
    # they sit. These are the two things a downscale lies about.
    mid = max(0.5, total * 0.45)
    title_band = run_dir / "inspect-title-band.jpg"
    grab(video, mid, title_band, "crop=1080:300:0:120")
    emit("title-band", title_band, mid, script.get("top_title", ""))

    caption_band = run_dir / "inspect-caption-band.jpg"
    grab(video, mid, caption_band, "crop=1080:320:0:1300")
    emit("caption-band", caption_band, mid, "captions at full resolution")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "output/reels"))
