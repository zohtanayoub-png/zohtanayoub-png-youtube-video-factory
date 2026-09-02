"""Subtitle generation.

Because the narration is generated locally, the exact duration of every spoken
chunk is already known from ffprobe. That means subtitles can be derived
directly from the TTS timeline - no speech recognition, no extra model, no
cost, and better accuracy than ASR would give.

Long chunks are split into readable cues, and each cue's share of the chunk's
time is allocated by character count, which tracks speech rate closely enough
for comfortable reading.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from .ffmpeg_utils import format_timestamp
from .logging_utils import get_logger

log = get_logger("SUBS")

MIN_CUE_SECONDS = 0.9
MAX_CUE_SECONDS = 7.0


@dataclass
class Cue:
    index: int
    start: float
    end: float
    text: str

    def to_srt(self) -> str:
        return (
            f"{self.index}\n"
            f"{format_timestamp(self.start)} --> {format_timestamp(self.end)}\n"
            f"{self.text}\n"
        )


def wrap_lines(text: str, max_line_chars: int = 42, max_lines: int = 2) -> str:
    """Wrap a cue into at most ``max_lines`` balanced lines."""

    words = text.split()
    if not words:
        return ""
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) <= max_line_chars or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)

    if len(lines) > max_lines:
        # Too long for the cue box: re-flow into exactly max_lines chunks.
        per_line = max(1, len(words) // max_lines + (1 if len(words) % max_lines else 0))
        lines = [
            " ".join(words[i : i + per_line]) for i in range(0, len(words), per_line)
        ][:max_lines]
    return "\n".join(lines)


def split_into_cues(text: str, max_chars: int = 84) -> list[str]:
    """Break one narration chunk into subtitle-sized pieces at natural breaks."""

    text = re.sub(r"\s+", " ", str(text or "")).strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    # Prefer sentence boundaries, then clause boundaries, then whitespace.
    pieces: list[str] = []
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        if len(sentence) <= max_chars:
            if sentence.strip():
                pieces.append(sentence.strip())
            continue
        remainder = sentence.strip()
        while len(remainder) > max_chars:
            window = remainder[:max_chars]
            split_at = max(window.rfind(", "), window.rfind("; "), window.rfind(" - "))
            if split_at < max_chars // 3:
                split_at = window.rfind(" ")
            if split_at <= 0:
                split_at = max_chars
            pieces.append(remainder[: split_at + 1].strip())
            remainder = remainder[split_at + 1 :].strip()
        if remainder:
            pieces.append(remainder)
    return [p for p in pieces if p]


def cues_from_chunks(
    chunks: Sequence[object],
    max_line_chars: int = 42,
    max_lines: int = 2,
) -> list[Cue]:
    """Build subtitle cues from :class:`~vidfactory.tts.NarrationChunk` records."""

    max_chars = max(20, max_line_chars * max_lines)
    cues: list[Cue] = []
    index = 0

    for chunk in chunks:
        text = str(getattr(chunk, "text", "") or "").strip()
        start = float(getattr(chunk, "start", 0.0))
        end = float(getattr(chunk, "end", start))
        if not text or end <= start:
            continue

        pieces = split_into_cues(text, max_chars)
        if not pieces:
            continue

        total_chars = sum(len(p) for p in pieces) or 1
        cursor = start
        span = end - start
        for position, piece in enumerate(pieces):
            share = len(piece) / total_chars
            piece_end = cursor + span * share
            if position == len(pieces) - 1:
                piece_end = end
            # Keep every cue readable even when the maths produces a sliver.
            if piece_end - cursor < MIN_CUE_SECONDS and position < len(pieces) - 1:
                piece_end = min(cursor + MIN_CUE_SECONDS, end)
            index += 1
            cues.append(
                Cue(
                    index=index,
                    start=round(cursor, 3),
                    end=round(min(piece_end, end), 3),
                    text=wrap_lines(piece, max_line_chars, max_lines),
                )
            )
            cursor = piece_end

    # Never let two cues overlap - some players stack them.
    for previous, current in zip(cues, cues[1:]):
        if current.start < previous.end:
            current.start = previous.end
        if current.end <= current.start:
            current.end = current.start + MIN_CUE_SECONDS
    return cues


def write_srt(cues: Iterable[Cue], destination: str | Path) -> Path:
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    blocks = [cue.to_srt() for cue in cues]
    target.write_text("\n".join(blocks), encoding="utf-8")
    log.info("%d subtitle cues written to %s", len(blocks), target.name)
    return target


def generate_subtitles(
    chunks: Sequence[object],
    destination: str | Path,
    max_line_chars: int = 42,
    max_lines: int = 2,
) -> tuple[Path, list[Cue]]:
    cues = cues_from_chunks(chunks, max_line_chars, max_lines)
    return write_srt(cues, destination), cues
