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
SAMPLE_CLIPS: tuple[tuple[str, str], ...] = (
    ("living-room-sofa-interior", "0x8f7a66"),
    ("curtains-window-daylight-interior", "0xb9a88a"),
    ("bedroom-bed-linen-interior", "0x6f7f74"),
    ("kitchen-counter-modern-interior", "0x9aa39b"),
    ("warm-lamp-lighting-evening-interior", "0xc4a06a"),
    ("area-rug-floor-living-room", "0x7d6b58"),
    ("indoor-plant-green-interior", "0x5f7a55"),
    ("shelf-storage-organization-interior", "0xa08f7d"),
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


def build_test_library(
    directory: str | Path,
    count: int = len(SAMPLE_CLIPS),
    seconds: float = 10.0,
    width: int = 1920,
    height: int = 1080,
) -> list[Path]:
    """Create a folder of synthetic clips usable by the ``local`` provider."""

    target_dir = Path(directory)
    target_dir.mkdir(parents=True, exist_ok=True)
    made: list[Path] = []
    for name, color in SAMPLE_CLIPS[: max(1, count)]:
        path = target_dir / f"{name}.mp4"
        if not path.exists():
            make_test_clip(path, seconds=seconds, color=color, width=width, height=height)
        made.append(path)
    log.info("%d synthetic test clips ready in %s", len(made), target_dir)
    return made
