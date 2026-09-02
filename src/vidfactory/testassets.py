"""Synthetic test footage.

Generating clips with FFmpeg's own sources means the integration test can
exercise the real rendering pipeline end to end without API credentials,
without network access and without shipping binary fixtures in the repository.
"""

from __future__ import annotations

from pathlib import Path

from .ffmpeg_utils import run_ffmpeg
from .logging_utils import get_logger

log = get_logger("ASSETS")

#: Names double as the searchable text for the local provider, so they are
#: written to look like real home decor footage filenames.
#: Enough distinct clips that an offline render can satisfy the one-source-
#: per-shot rule for a short video without repeating footage.
SAMPLE_CLIPS: tuple[tuple[str, str], ...] = (
    ("bright-living-room-sofa-natural-light", "0x8f7a66"),
    ("floor-to-ceiling-curtains-window-daylight", "0xb9a88a"),
    ("styled-bedroom-linen-bedding-sunlight", "0x6f7f74"),
    ("modern-kitchen-counter-natural-light", "0x9aa39b"),
    ("warm-lamp-lighting-evening-interior", "0xc4a06a"),
    ("large-area-rug-floor-living-room", "0x7d6b58"),
    ("indoor-plant-greenery-interior", "0x5f7a55"),
    ("shelf-storage-organization-styled", "0xa08f7d"),
    ("tall-mirror-reflecting-window-light", "0x8a8f96"),
    ("wooden-console-table-styled-decor", "0x7a6a52"),
    ("scandinavian-living-room-pale-wood", "0xc9c2b4"),
    ("cozy-armchair-corner-reading-nook", "0x94764f"),
    ("wide-shot-spacious-apartment-daylight", "0xa8a293"),
    ("close-up-linen-texture-cushion", "0xbfb3a0"),
    ("marble-surface-detail-kitchen", "0xd2cec6"),
    ("brass-hardware-detail-cabinet", "0xa8863f"),
    ("bathroom-folded-towels-spa-styled", "0xb6bcbc"),
    ("dining-table-pendant-light-warm", "0x8d7250"),
    ("bookshelf-full-of-books-interior", "0x6c5a48"),
    ("white-painted-wall-trim-detail", "0xd8d4cc"),
    ("ceramic-vase-branches-styled-table", "0x9e9384"),
    ("woven-basket-natural-texture-storage", "0xb09a72"),
    ("sunlight-shadows-on-plaster-wall", "0xcbbfa9"),
    ("minimal-bedroom-neutral-palette-wide", "0xa39a8d"),
)


def make_test_clip(
    destination: str | Path,
    seconds: float = 10.0,
    color: str = "0x8f7a66",
    label: str = "",
    width: int = 1920,
    height: int = 1080,
    fps: int = 30,
) -> Path:
    """Render one synthetic landscape clip with slow visible movement."""

    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    # A moving gradient plus a drifting box gives the encoder real motion to
    # compress, so the result behaves like genuine footage rather than a still.
    filters = (
        f"drawbox=x='mod(t*80\\,{width})':y='{height // 3}':w=320:h=240:"
        "color=white@0.35:t=fill,"
        f"drawbox=x='{width // 2}':y='mod(t*40\\,{height})':w=200:h=140:"
        "color=black@0.25:t=fill,"
        "noise=alls=6:allf=t,format=yuv420p"
    )
    run_ffmpeg(
        [
            "-f", "lavfi",
            "-i", f"color=c={color}:s={width}x{height}:r={fps}:d={seconds:.2f}",
            "-vf", filters,
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "26",
            "-pix_fmt", "yuv420p",
            "-t", f"{seconds:.2f}",
            str(target),
        ],
        description="test clip",
    )
    return target


def _shift(color: str, step: int) -> str:
    """Nudge a hex color so extra generated clips are visually distinct."""

    value = int(str(color).replace("0x", ""), 16)
    r = (value >> 16) & 0xFF
    g = (value >> 8) & 0xFF
    b = value & 0xFF
    r = (r + step * 23) % 200 + 40
    g = (g + step * 41) % 200 + 40
    b = (b + step * 17) % 200 + 40
    return f"0x{r:02x}{g:02x}{b:02x}"


def build_test_library(
    directory: str | Path,
    count: int = len(SAMPLE_CLIPS),
    seconds: float = 10.0,
    width: int = 1920,
    height: int = 1080,
) -> list[Path]:
    """Create a folder of synthetic clips usable by the ``local`` provider.

    ``count`` may exceed the curated list; extra clips are generated as
    recognisable variations so an offline render can still satisfy the
    one-source-per-shot rule for a longer video.
    """

    target_dir = Path(directory)
    target_dir.mkdir(parents=True, exist_ok=True)
    made: list[Path] = []
    wanted = max(1, int(count))

    for index in range(wanted):
        base_name, base_color = SAMPLE_CLIPS[index % len(SAMPLE_CLIPS)]
        cycle = index // len(SAMPLE_CLIPS)
        if cycle == 0:
            name, color = base_name, base_color
        else:
            name = f"{base_name}-variation-{cycle + 1}"
            color = _shift(base_color, cycle)
        path = target_dir / f"{name}.mp4"
        if not path.exists():
            make_test_clip(path, seconds=seconds, color=color, width=width, height=height)
        made.append(path)

    log.info("%d synthetic test clips ready in %s", len(made), target_dir)
    return made


def clips_needed_for(
    duration_minutes: float,
    average_shot_seconds: float = 4.5,
    safety: float = 1.8,
) -> int:
    """How many distinct clips a duration needs at one source video per shot.

    Deliberately over-provisions. The finished narration is usually longer
    than the requested duration - speech rate varies by TTS engine and every
    scene carries a pause - and running short of clips is what forces footage
    reuse. Synthetic clips are cheap; a repeated shot is not.
    """

    import math

    seconds = max(10.0, float(duration_minutes) * 60.0)
    base = seconds / max(1.0, average_shot_seconds)
    return max(12, int(math.ceil(base * max(1.0, safety))) + 6)
