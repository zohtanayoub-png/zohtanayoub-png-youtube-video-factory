"""Emit the frames a reviewer needs to see, through the only channel available.

The finished video never leaves the runner - it is an artifact behind Azure
blob storage, and the environment this repository is developed from can reach
neither that nor Pexels. So "look at the rug section" is not a thing that can
be done after the fact from a report; the frame has to be carried out of the
job itself.

This picks the moment each named topic is actually being narrated, using the
subtitle timeline (which is exact, being built from the TTS chunk durations),
grabs the frame on screen at that moment, and prints it base64 so it comes
back in the job log. Small JPEGs: this is for judging whether a rug is in the
picture, not for grading the encode.
"""

from __future__ import annotations

import base64
import re
import subprocess
import sys
from pathlib import Path

#: What to look for, and the narration that means we have found it.
TOPICS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("trim-wall", ("trim", "skirting", "baseboard", "paint the wall", "wall color",
                   "wall colour", "same color as the wall", "moulding", "molding")),
    ("rug", ("rug", "carpet")),
    ("curtains", ("curtain", "drape", "blind")),
    ("artwork", ("art", "artwork", "frame", "gallery wall", "picture")),
    ("lighting", ("lamp", "sconce", "light source", "lighting", "pendant")),
)

_TIME = re.compile(
    r"(\d\d):(\d\d):(\d\d),(\d\d\d)\s*-->\s*(\d\d):(\d\d):(\d\d),(\d\d\d)"
)


def cues(srt: Path) -> list[tuple[float, float, str]]:
    out: list[tuple[float, float, str]] = []
    block: list[str] = []
    for line in srt.read_text(encoding="utf-8").splitlines() + [""]:
        if line.strip():
            block.append(line)
            continue
        stamp = next((l for l in block if _TIME.search(l)), "")
        text = " ".join(l for l in block if l is not stamp and not l.strip().isdigit())
        match = _TIME.search(stamp) if stamp else None
        if match:
            a = [int(x) for x in match.groups()]
            start = a[0] * 3600 + a[1] * 60 + a[2] + a[3] / 1000.0
            end = a[4] * 3600 + a[5] * 60 + a[6] + a[7] / 1000.0
            out.append((start, end, text.strip()))
        block = []
    return out


def main(directory: str) -> int:
    root = Path(directory)
    video = root / "final_video.mp4"
    srt = root / "subtitles.srt"
    if not video.exists() or not srt.exists():
        print(f"nothing to inspect in {root}")
        return 0

    timeline = cues(srt)
    for name, words in TOPICS:
        hit = next(
            (c for c in timeline if any(w in c[2].lower() for w in words)), None
        )
        if hit is None:
            print(f"::warning::no narration found for {name}")
            continue
        start, end, text = hit
        at = start + (end - start) / 2.0
        frame = root / f"inspect-{name}.jpg"
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{at:.2f}", "-i", str(video),
             "-frames:v", "1", "-vf", "scale=640:-2", "-q:v", "6", str(frame)],
            check=False,
        )
        if not frame.exists():
            print(f"::warning::could not extract a frame for {name}")
            continue
        payload = base64.b64encode(frame.read_bytes()).decode("ascii")
        print(f"FRAME-BEGIN {name} at={at:.1f}s bytes={frame.stat().st_size}")
        print(f"FRAME-TEXT {name} {text}")
        for i in range(0, len(payload), 200):
            print(f"FRAME-DATA {name} {payload[i:i + 200]}")
        print(f"FRAME-END {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "."))
