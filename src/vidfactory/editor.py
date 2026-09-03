"""FFmpeg video assembly.

Design notes
------------
* **Narration drives the edit.** The narration track is rendered first, so
  every scene's exact duration is known. Shots are then cut to fit that
  timeline, which is what keeps visuals following the words.
* **One normalized intermediate per shot.** Each shot is scaled, cropped and
  re-encoded to identical parameters, then the shots are joined with the
  concat demuxer using stream copy. That is dramatically faster and far more
  reliable on a 2-core runner than one enormous ``filter_complex``.
* **Crossfades, when enabled**, are applied inside small groups (``xfade``
  requires re-encoding) and the groups are then concatenated by copy.
* **No music, ever.** The only audio input is the narration track.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

from .ffmpeg_utils import FFmpegError, probe_media, run_ffmpeg
from .logging_utils import get_logger

log = get_logger("FFMPEG")


@dataclass
class Shot:
    """One visual segment of the finished video."""

    source: Path
    start: float          # in-point inside the source clip
    duration: float       # how long this shot appears in the video
    scene_id: str = ""
    clip_key: str = ""
    motion: str = "none"  # none | zoom_in | zoom_out | pan_right | pan_left
    rendered: Path | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source.name,
            "start": round(self.start, 2),
            "duration": round(self.duration, 2),
            "scene_id": self.scene_id,
            "clip_key": self.clip_key,
            "motion": self.motion,
        }


MOTIONS = ("zoom_in", "zoom_out", "pan_right", "pan_left")


@dataclass
class ShotPlan:
    """The result of laying clips onto the narration timeline."""

    shots: list[Shot] = field(default_factory=list)
    #: provider keys that had to be used more than once (should be empty)
    reused_keys: list[str] = field(default_factory=list)
    #: how many distinct source videos the finished edit draws on
    unique_sources: int = 0
    shortfall: int = 0

    @property
    def reuse_count(self) -> int:
        return len(self.reused_keys)

    @property
    def unique_source_ratio(self) -> float:
        return (self.unique_sources / len(self.shots)) if self.shots else 0.0


def _clip_key(clip: Any) -> str:
    """Stable per-source identity: ``provider:id``, never the file path."""

    inner = getattr(clip, "clip", None)
    key = getattr(inner, "key", "") if inner is not None else ""
    return str(key or getattr(clip, "path", "") or id(clip))


def _shot_lengths(total: float, min_shot: float, max_shot: float,
                  rng: random.Random) -> list[float]:
    """Split a scene into shot lengths with a deliberately irregular rhythm.

    A constant cadence is what makes long stock-footage videos feel robotic,
    so each shot is jittered around the mean instead of every cut landing on
    the same beat.
    """

    total = max(0.05, float(total))
    if total <= max_shot * 1.05:
        return [total]

    target = (min_shot + max_shot) / 2.0
    count = max(1, int(round(total / target)))
    # Never let a single shot exceed max_shot.
    while total / count > max_shot and count < 200:
        count += 1

    weights = [rng.uniform(0.78, 1.22) for _ in range(count)]
    scale = total / sum(weights)
    lengths = [w * scale for w in weights]

    # Pull any outlier back inside the window, then re-normalise.
    for _ in range(3):
        lengths = [min(max(v, min_shot * 0.7), max_shot) for v in lengths]
        drift = total - sum(lengths)
        if abs(drift) < 0.02:
            break
        lengths = [v + drift / len(lengths) for v in lengths]
    lengths[-1] += total - sum(lengths)
    return [round(v, 3) for v in lengths]


def plan_shots(
    scene_durations: Sequence[tuple[str, float]],
    clips: Sequence[Any],
    min_shot: float = 3.0,
    max_shot: float = 6.0,
    motion: str = "subtle",
    rng: random.Random | None = None,
    scene_affinity: dict[str, list[str]] | None = None,
    allow_reuse: bool = True,
) -> ShotPlan:
    """Lay clips onto the narration timeline, one source video per shot.

    The hard rule is that a provider video ID appears **at most once** in a
    finished video. Taking a second segment from the same source at a
    different timestamp is exactly what made earlier videos look repetitive,
    so it is not treated as an acceptable substitute for finding more footage.

    ``scene_affinity`` maps a scene id to the clip keys that were found for
    that scene's own queries. Honouring it is what keeps the visuals grouped
    coherently around each idea instead of cycling through unrelated rooms.

    When there are genuinely fewer clips than shots, the shortfall is reported
    on the returned :class:`ShotPlan` and reuse is a logged last resort - never
    silent, and never in the original order.
    """

    rng = rng or random.Random(20240)
    usable = [
        c for c in clips
        if getattr(c, "duration", 0) > 0.5 and Path(getattr(c, "path", "")).exists()
    ]
    if not usable:
        raise ValueError("No usable clips were downloaded - cannot build a video")

    by_key: dict[str, Any] = {}
    for clip in usable:
        by_key.setdefault(_clip_key(clip), clip)

    affinity = scene_affinity or {}
    unused: list[str] = list(by_key)
    rng.shuffle(unused)
    consumed: set[str] = set()
    reused: list[str] = []
    # Creator of each of the last two placed shots, for the consecutive rule.
    recent_authors: list[str] = []

    def author_of(key: str) -> str:
        inner = getattr(by_key[key], "clip", None)
        return str(getattr(inner, "author", "") or "").lower()

    def take(scene_id: str) -> tuple[str, bool]:
        """Claim the best unused source for a scene. Returns (key, is_reuse)."""

        preferred = [k for k in affinity.get(scene_id, []) if k in by_key and k not in consumed]
        pools = (preferred, [k for k in unused if k not in consumed])

        for pool in pools:
            if not pool:
                continue
            # Enforce "no more than 2 consecutive clips from one creator".
            blocked = ""
            if len(recent_authors) >= 2 and recent_authors[-1] and recent_authors[-1] == recent_authors[-2]:
                blocked = recent_authors[-1]
            choice = next((k for k in pool if not blocked or author_of(k) != blocked), None)
            if choice is None:
                choice = pool[0]          # only that creator is left; take it
            consumed.add(choice)
            return choice, False

        # Everything has been used once. Reuse is a genuine last resort.
        if not allow_reuse:
            raise ValueError("ran out of unique clips and reuse is disabled")
        # Reuse the least recently placed source, never the original order.
        candidates = [k for k in by_key if k not in reused] or list(by_key)
        choice = rng.choice(candidates)
        reused.append(choice)
        return choice, True

    shots: list[Shot] = []
    used_offsets: dict[str, float] = {}

    for scene_id, scene_seconds in scene_durations:
        lengths = _shot_lengths(float(scene_seconds), min_shot, max_shot, rng)
        for position, length in enumerate(lengths):
            if length <= 0.05:
                continue
            key, is_reuse = take(scene_id)
            clip = by_key[key]
            clip_duration = float(getattr(clip, "duration", 0.0))

            if is_reuse:
                # Different section and different motion so a forced repeat is
                # at least not a literal replay of the earlier shot.
                previous = used_offsets.get(key, 0.0)
                span = max(0.0, clip_duration - length)
                start = rng.uniform(0.0, span) if span > 0.5 else 0.0
                if abs(start - previous) < length:
                    start = max(0.0, min(span, previous + length + 0.5))
            else:
                span = max(0.0, clip_duration - length)
                # Skip the first moments: stock clips often start on a fade or
                # a camera settle.
                start = min(span, 0.35) if span > 1.0 else 0.0
            used_offsets[key] = start

            chosen_motion = "none"
            if motion == "subtle":
                if is_reuse or rng.random() < 0.5:
                    chosen_motion = MOTIONS[(len(shots) + position) % len(MOTIONS)]

            shots.append(
                Shot(
                    source=Path(getattr(clip, "path")),
                    start=max(0.0, round(start, 3)),
                    duration=round(length, 3),
                    scene_id=scene_id,
                    clip_key=key,
                    motion=chosen_motion,
                )
            )
            recent_authors.append(author_of(key))
            del recent_authors[:-2]

    unique_sources = len({shot.clip_key for shot in shots})
    plan = ShotPlan(
        shots=shots,
        reused_keys=reused,
        unique_sources=unique_sources,
        shortfall=max(0, len(shots) - len(by_key)),
    )

    if reused:
        log.warning(
            "FOOTAGE SHORTAGE: %d of %d shots reuse a source video "
            "(%d unique sources available). Searches were exhausted; "
            "widen the queries or raise sources.per_query_results.",
            len(reused),
            len(shots),
            len(by_key),
        )
    log.info(
        "%d shots planned across %d scenes from %d unique source videos "
        "(%.0f%% unique, %.1fs average shot)",
        len(shots),
        len(scene_durations),
        unique_sources,
        plan.unique_source_ratio * 100,
        (sum(s.duration for s in shots) / len(shots)) if shots else 0.0,
    )
    return plan


def estimate_shot_count(
    scene_durations: Sequence[tuple[str, float]],
    min_shot: float = 3.0,
    max_shot: float = 6.0,
) -> int:
    """How many shots a timeline will need.

    The pipeline uses this to decide how much footage to gather. Guessing from
    the total duration alone under-counts badly, because every scene rounds its
    own shot count up independently - which is how earlier videos ended up
    with fewer clips than shots and had to repeat footage.
    """

    target = (min_shot + max_shot) / 2.0
    total = 0
    for _, seconds in scene_durations:
        seconds = max(0.05, float(seconds))
        if seconds <= max_shot * 1.05:
            total += 1
            continue
        count = max(1, int(round(seconds / target)))
        while seconds / count > max_shot and count < 200:
            count += 1
        total += count
    return total


def subtitle_filter(subtitles: str | Path) -> str:
    """The libass filter chain that burns captions into the picture.

    An ``.ass`` file carries its own styling - font, size, colours, margins,
    fades, per-word emphasis - so it is passed through untouched. A plain
    ``.srt`` has none of that, so it gets a readable default rather than
    libass's, which is small and hard to read at 1080p on a phone.

    The path is escaped rather than quoted casually: FFmpeg parses filter
    arguments before the shell does, and a Windows drive letter or a colon in
    a generation id would otherwise split the argument in half.
    """

    path = Path(subtitles)
    escaped = str(path.resolve()).replace("\\", "/").replace(":", r"\:")
    if path.suffix.lower() == ".ass":
        return f"ass='{escaped}'"
    return (
        f"subtitles='{escaped}':force_style='"
        "FontName=DejaVu Sans,Fontsize=22,PrimaryColour=&H00FFFFFF,"
        "OutlineColour=&H90000000,BorderStyle=3,Outline=1,Shadow=0,MarginV=48'"
    )


class VideoEditor:
    """Renders planned shots into a finished 1080p MP4 with narration."""

    #: How much larger than the output frame the source is scaled before a
    #: motion crop. 1.12 gives a visible but restrained drift.
    MOTION_SCALE = 1.12

    def __init__(
        self,
        workdir: str | Path,
        width: int = 1920,
        height: int = 1080,
        fps: int = 30,
        crf: int = 20,
        preset: str = "veryfast",
        transition: str = "cut",
        transition_seconds: float = 0.4,
        sample_rate: int = 48000,
        aac_bitrate: str = "192k",
        fast_mux: bool = True,
    ) -> None:
        self.workdir = Path(workdir)
        self.workdir.mkdir(parents=True, exist_ok=True)
        self.width = int(width)
        self.height = int(height)
        self.fps = int(fps)
        self.crf = int(crf)
        self.preset = str(preset)
        self.transition = str(transition)
        self.transition_seconds = float(transition_seconds)
        self.sample_rate = int(sample_rate)
        self.aac_bitrate = str(aac_bitrate)
        self.fast_mux = bool(fast_mux)

    # ------------------------------------------------------------------
    def _filter_for(self, shot: Shot, fade_out: float = 0.0) -> str:
        """Scale + crop to exactly WxH, preserving aspect ratio, plus motion.

        ``increase`` scaling followed by a center crop is what prevents
        stretched footage: the frame is filled and the overflow is trimmed
        rather than the image being distorted.

        Motion is done with a time-varying ``crop`` rather than ``zoompan``.
        ``zoompan`` is roughly a hundred times slower on a CPU runner and
        produces the wrong output duration, which is fatal for a pipeline that
        depends on exact shot lengths.
        """

        width, height = self.width, self.height
        tail: list[str] = []
        if fade_out > 0.01:
            # Baking the closing fade into the final shot means the finished
            # video can be assembled without re-encoding the whole timeline.
            start = max(0.0, shot.duration - fade_out)
            tail.append(f"fade=t=out:st={start:.3f}:d={fade_out:.3f}")

        if shot.motion == "none":
            return ",".join(
                [
                    f"scale={width}:{height}:force_original_aspect_ratio=increase:flags=bicubic",
                    f"crop={width}:{height}",
                    *tail,
                    f"fps={self.fps}",
                    "format=yuv420p",
                    "setsar=1",
                ]
            )

        # Oversample slightly so there is room to move inside the frame.
        over_w = int(round(width * self.MOTION_SCALE)) // 2 * 2
        over_h = int(round(height * self.MOTION_SCALE)) // 2 * 2
        duration = max(0.2, shot.duration)
        progress = f"min(t/{duration:.3f},1)"

        chain = [
            f"scale={over_w}:{over_h}:force_original_aspect_ratio=increase:flags=bicubic",
            f"crop={over_w}:{over_h}",
        ]

        if shot.motion == "zoom_in":
            chain.append(
                f"crop=w='2*floor(({over_w}-({over_w}-{width})*{progress})/2)'"
                f":h='2*floor(({over_h}-({over_h}-{height})*{progress})/2)'"
                ":x='(iw-ow)/2':y='(ih-oh)/2'"
            )
            chain.append(f"scale={width}:{height}")
        elif shot.motion == "zoom_out":
            chain.append(
                f"crop=w='2*floor(({width}+({over_w}-{width})*{progress})/2)'"
                f":h='2*floor(({height}+({over_h}-{height})*{progress})/2)'"
                ":x='(iw-ow)/2':y='(ih-oh)/2'"
            )
            chain.append(f"scale={width}:{height}")
        elif shot.motion == "pan_right":
            chain.append(
                f"crop=w={width}:h={height}:x='({over_w}-{width})*{progress}'"
                f":y='({over_h}-{height})/2'"
            )
        else:  # pan_left
            chain.append(
                f"crop=w={width}:h={height}:x='({over_w}-{width})*(1-{progress})'"
                f":y='({over_h}-{height})/2'"
            )

        chain.extend([*tail, f"fps={self.fps}", "format=yuv420p", "setsar=1"])
        return ",".join(chain)

    # ------------------------------------------------------------------
    def render_shot(self, shot: Shot, index: int, fade_out: float = 0.0) -> Path:
        """Normalize one shot into an intermediate MP4 with identical params."""

        target = self.workdir / f"shot_{index:05d}.mp4"
        args = [
            "-ss", f"{shot.start:.3f}",
            "-t", f"{shot.duration:.3f}",
            "-i", str(shot.source),
            "-an",
            "-vf", self._filter_for(shot, fade_out=fade_out),
            "-c:v", "libx264",
            "-preset", self.preset,
            "-crf", str(self.crf),
            "-pix_fmt", "yuv420p",
            "-r", str(self.fps),
            "-video_track_timescale", "90000",
            "-movflags", "+faststart",
            str(target),
        ]
        run_ffmpeg(args, description=f"shot {index}")

        info = probe_media(target)
        if not info.has_video or info.duration <= 0.02:
            raise FFmpegError(f"shot {index} rendered as an empty clip")
        shot.rendered = target
        return target

    # ------------------------------------------------------------------
    def _concat_copy(self, parts: Sequence[Path], destination: Path) -> Path:
        listing = destination.with_suffix(".concat.txt")
        with open(listing, "w", encoding="utf-8") as handle:
            for part in parts:
                resolved = str(Path(part).resolve()).replace("'", r"'\''")
                handle.write(f"file '{resolved}'\n")
        run_ffmpeg(
            [
                "-f", "concat",
                "-safe", "0",
                "-i", str(listing),
                "-c", "copy",
                "-movflags", "+faststart",
                str(destination),
            ],
            description="concat",
        )
        listing.unlink(missing_ok=True)
        return destination

    def _crossfade_group(self, parts: Sequence[Path], destination: Path) -> Path:
        """Chain xfade across a small group of shots (requires re-encoding)."""

        if len(parts) == 1:
            return Path(parts[0])

        fade = max(0.1, min(self.transition_seconds, 1.0))
        inputs: list[str] = []
        for part in parts:
            inputs.extend(["-i", str(part)])

        durations = [probe_media(p).duration for p in parts]
        filters: list[str] = []
        label = "0:v"
        offset = durations[0]
        for position in range(1, len(parts)):
            output = f"x{position}"
            filters.append(
                f"[{label}][{position}:v]xfade=transition=fade:duration={fade:.3f}"
                f":offset={max(0.0, offset - fade):.3f}[{output}]"
            )
            label = output
            offset = offset - fade + durations[position]

        run_ffmpeg(
            [
                *inputs,
                "-filter_complex", ";".join(filters),
                "-map", f"[{label}]",
                "-c:v", "libx264",
                "-preset", self.preset,
                "-crf", str(self.crf),
                "-pix_fmt", "yuv420p",
                "-r", str(self.fps),
                "-video_track_timescale", "90000",
                str(destination),
            ],
            description="crossfade group",
        )
        return destination

    # ------------------------------------------------------------------
    def build_video_track(self, shots: Sequence[Shot] | ShotPlan, fade_out: float = 0.0) -> Path:
        """Render every shot and join them into one silent video track."""

        if isinstance(shots, ShotPlan):
            shots = shots.shots
        rendered: list[Path] = []
        last = len(shots)
        for index, shot in enumerate(shots, start=1):
            try:
                shot_fade = fade_out if index == last else 0.0
                rendered.append(self.render_shot(shot, index, fade_out=shot_fade))
            except FFmpegError as exc:
                # A single bad source must not lose the render.
                log.warning("Shot %d failed (%s); it will be skipped", index, exc)
        if not rendered:
            raise FFmpegError("every shot failed to render")

        if len(rendered) < len(shots):
            log.warning("%d of %d shots were skipped", len(shots) - len(rendered), len(shots))

        if self.transition == "crossfade" and len(rendered) > 1:
            group_size = 8
            groups: list[Path] = []
            for start in range(0, len(rendered), group_size):
                batch = rendered[start : start + group_size]
                target = self.workdir / f"group_{start // group_size:04d}.mp4"
                groups.append(self._crossfade_group(batch, target))
            silent = self.workdir / "video_track.mp4"
            return self._concat_copy(groups, silent) if len(groups) > 1 else groups[0]

        silent = self.workdir / "video_track.mp4"
        return self._concat_copy(rendered, silent)

    # ------------------------------------------------------------------
    def mux(
        self,
        video_track: Path,
        narration: Path,
        destination: str | Path,
        tail_seconds: float = 1.2,
        subtitles: Path | None = None,
        video_bitrate: str | None = None,
    ) -> Path:
        """Combine the silent video with the narration into the final MP4.

        The output length is pinned to the narration plus a short tail, so the
        video can never end while narration is still playing and can never
        freeze on a still frame for long at the end.
        """

        target = Path(destination)
        target.parent.mkdir(parents=True, exist_ok=True)

        audio_info = probe_media(narration)
        video_info = probe_media(video_track)
        total = audio_info.duration + max(0.0, tail_seconds)

        if video_info.duration <= 0:
            raise FFmpegError("the assembled video track has no duration")

        needs_filters = bool(subtitles is not None and Path(subtitles).exists())
        long_enough = video_info.duration >= total - 0.05

        if self.fast_mux and long_enough and not needs_filters:
            # The video track already has the right size, frame rate, codec and
            # closing fade, so it can simply be trimmed and copied. On a 20
            # minute video this saves a full re-encode.
            log.info("Rendering %s (stream copy)...", target.name)
            run_ffmpeg(
                [
                    "-i", str(video_track),
                    "-i", str(narration),
                    "-map", "0:v:0",
                    "-map", "1:a:0",
                    "-c:v", "copy",
                    "-c:a", "aac",
                    "-b:a", self.aac_bitrate,
                    "-ar", str(self.sample_rate),
                    "-ac", "2",
                    "-af", "apad=pad_dur=%.3f" % max(0.0, tail_seconds),
                    "-t", f"{total:.3f}",
                    "-movflags", "+faststart",
                    str(target),
                ],
                description="final render (copy)",
                timeout=3600,
            )
            return target

        args = ["-i", str(video_track), "-i", str(narration)]
        video_filters: list[str] = []

        if video_info.duration < total - 0.05:
            # Hold the final frame rather than cutting to black.
            args = ["-i", str(video_track), "-i", str(narration)]
            video_filters.append("tpad=stop_mode=clone:stop_duration=%.3f" % (total - video_info.duration))
            log.info(
                "Video track is %.1fs shorter than the narration; holding the last frame",
                total - video_info.duration,
            )

        # A short fade out at the very end reads as deliberate rather than abrupt.
        fade_start = max(0.0, total - 0.6)
        video_filters.append(f"fade=t=out:st={fade_start:.3f}:d=0.6")
        video_filters.append("format=yuv420p")

        if subtitles is not None and Path(subtitles).exists():
            video_filters.append(subtitle_filter(subtitles))

        args.extend(
            [
                "-vf", ",".join(video_filters),
                "-map", "0:v:0",
                "-map", "1:a:0",
                "-c:v", "libx264",
                "-preset", self.preset,
                "-crf", str(self.crf),
                "-profile:v", "high",
                "-level", "4.1",
                "-pix_fmt", "yuv420p",
                "-r", str(self.fps),
                "-c:a", "aac",
                "-b:a", self.aac_bitrate,
                "-ar", str(self.sample_rate),
                "-ac", "2",
                "-af", "apad=pad_dur=%.3f" % max(0.0, tail_seconds),
                "-t", f"{total:.3f}",
                "-movflags", "+faststart",
                str(target),
            ]
        )
        if video_bitrate:
            args[-1:-1] = ["-maxrate", video_bitrate, "-bufsize", video_bitrate]

        log.info("Rendering %s...", target.name)
        run_ffmpeg(args, description="final render", timeout=7200)
        return target
