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

#: What to look for, as whole words. "picture" is deliberately absent from
#: artwork: run 34 matched "Picture the same room photographed by an estate
#: agent" - a hook sentence - and sampled a frame that had nothing to do with
#: hanging art.
TOPICS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("trim-wall", (r"trim", r"skirting", r"baseboard", r"moulding", r"molding",
                   r"same colou?r as the walls?", r"paint(ing)? the walls?")),
    ("rug", (r"rugs?", r"carpet")),
    ("curtains", (r"curtains?", r"drapes?", r"curtain rods?")),
    ("artwork", (r"art", r"artwork", r"framed", r"gallery wall", r"canvas")),
    ("lighting", (r"lamps?", r"sconces?", r"pendant", r"light sources?", r"lighting")),
)

#: How far either side of a cue to look when deciding whether it sits inside
#: the section that teaches this topic.
NEIGHBOURHOOD = 6

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

    # The grounding numbers belong next to the picture they describe.
    report = root / "editorial_quality_report.json"
    if report.exists():
        import json

        try:
            data = json.loads(report.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}
        grounding = data.get("final_shot_entity_grounding") or {}
        print("GROUNDING checked=%s failed=%s pass=%s%%" % (
            grounding.get("checked"), grounding.get("failed"),
            grounding.get("pass_percentage"),
        ))
        for name, row in (grounding.get("by_entity") or {}).items():
            print(f"GROUNDING {name}: {row}")
        for failure in grounding.get("failures") or []:
            print(f"GROUNDING failure: {failure}")

    timeline = cues(srt)
    patterns = {
        name: [re.compile(rf"\b{w}\b", re.I) for w in words]
        for name, words in TOPICS
    }

    def mentions(name: str, text: str) -> int:
        return sum(1 for p in patterns[name] if p.search(text))

    for name, _ in TOPICS:
        # The densest run of mentions, not the first one. A section that
        # teaches rugs says "rug" several times over consecutive cues; the
        # word turning up once inside "balance a bookcase with a sofa, not
        # with a floor lamp" is a different section talking about something
        # else, and run 34 sampled exactly that for lighting.
        best: tuple[int, int] | None = None
        for index, cue in enumerate(timeline):
            if not mentions(name, cue[2]):
                continue
            window = timeline[max(0, index - NEIGHBOURHOOD):index + NEIGHBOURHOOD + 1]
            density = sum(mentions(name, c[2]) for c in window)
            # Cues that also talk about other topics are weaker evidence.
            noise = sum(
                mentions(other, cue[2]) for other, _ in TOPICS if other != name
            )
            score = density - 2 * noise
            if best is None or score > best[0]:
                best = (score, index)
        if best is None:
            print(f"::warning::no narration found for {name}")
            continue
        start, end, text = timeline[best[1]]
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
        # The caption band at full resolution as well, for the first topic
        # only. A 640-wide downscale shrinks a 2.2px outline to under a pixel
        # and makes perfectly good captions look washed out, so legibility
        # cannot honestly be judged from the frames above.
        if name == TOPICS[0][0]:
            band = root / "inspect-caption-band.jpg"
            subprocess.run(
                ["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{at:.2f}",
                 "-i", str(video), "-frames:v", "1",
                 "-vf", "crop=1920:260:0:820", "-q:v", "4", str(band)],
                check=False,
            )
            if band.exists():
                blob = base64.b64encode(band.read_bytes()).decode("ascii")
                print(f"FRAME-BEGIN caption-band at={at:.1f}s "
                      f"bytes={band.stat().st_size}")
                print(f"FRAME-TEXT caption-band {text}")
                for i in range(0, len(blob), 200):
                    print(f"FRAME-DATA caption-band {blob[i:i + 200]}")
                print("FRAME-END caption-band")

        payload = base64.b64encode(frame.read_bytes()).decode("ascii")
        print(f"FRAME-BEGIN {name} at={at:.1f}s bytes={frame.stat().st_size}")
        print(f"FRAME-TEXT {name} {text}")
        for i in range(0, len(payload), 200):
            print(f"FRAME-DATA {name} {payload[i:i + 200]}")
        print(f"FRAME-END {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "."))
