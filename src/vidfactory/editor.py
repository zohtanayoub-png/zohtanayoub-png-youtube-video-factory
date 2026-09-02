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


def plan_shots(
    scene_durations: Sequence[tuple[str, float]],
    clips: Sequence[Any],
    min_shot: float = 4.0,
    max_shot: float = 8.0,
    motion: str = "subtle",
    rng: random.Random | None = None,
) -> list[Shot]:
    """Lay clips onto the narration timeline.

    Each scene gets as many shots as its narration needs (a long scene never
    freezes on one clip), and when unique clips run out the planner reuses a
    clip from a *different in-point* with different motion so the repetition
    is not obvious.
    """

    rng = rng or random.Random(20240)
    usable = [c for c in clips if getattr(c, "duration", 0) > 0.5 and Path(getattr(c, "path", "")).exists()]
    if not usable:
        raise ValueError("No usable clips were downloaded - cannot build a video")

    shots: list[Shot] = []
    order = list(range(len(usable)))
    rng.shuffle(order)
    cursor = 0
    # Tracks how far into each source clip we have already taken footage.
    offsets: dict[int, float] = {index: 0.0 for index in order}
    uses: dict[int, int] = {index: 0 for index in order}

    for scene_id, scene_seconds in scene_durations:
        remaining = max(0.4, float(scene_seconds))
        # How many shots this scene needs to stay inside the shot-length window.
        shot_count = max(1, int(math.ceil(remaining / max_shot)))
        base_length = remaining / shot_count
        # Very short scenes are allowed to fall below min_shot; forcing 4s
        # there would push visuals out of sync with the narration.
        for position in range(shot_count):
            length = base_length if position < shot_count - 1 else remaining
            length = min(length, remaining)
            if length <= 0.05:
                break

            index = order[cursor % len(order)]
            cursor += 1
            clip = usable[index]
            clip_duration = float(getattr(clip, "duration", 0.0))

            start = offsets.get(index, 0.0)
            if start + length > clip_duration:
                # Wrap around and take a different section next time.
                start = 0.0 if clip_duration <= length else rng.uniform(
                    0.0, max(0.0, clip_duration - length)
                )
            offsets[index] = start + length + 0.25
            uses[index] = uses.get(index, 0) + 1

            chosen_motion = "none"
            if motion == "subtle":
                # Reused clips always get motion so the repeat reads differently.
                if uses[index] > 1 or rng.random() < 0.45:
                    chosen_motion = MOTIONS[(uses[index] + position) % len(MOTIONS)]

            shots.append(
                Shot(
                    source=Path(getattr(clip, "path")),
                    start=max(0.0, start),
                    duration=round(length, 3),
                    scene_id=scene_id,
                    clip_key=getattr(getattr(clip, "clip", None), "key", "") or "",
                    motion=chosen_motion,
                )
            )
            remaining -= length
            if remaining <= 0.05:
                break

    log.info(
        "%d shots planned across %d scenes from %d clips",
        len(shots),
        len(scene_durations),
        len(usable),
    )
    return shots


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

    # ------------------------------------------------------------------
    def _filter_for(self, shot: Shot) -> str:
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
        if shot.motion == "none":
            return ",".join(
                [
                    f"scale={width}:{height}:force_original_aspect_ratio=increase:flags=bicubic",
                    f"crop={width}:{height}",
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

        chain.extend([f"fps={self.fps}", "format=yuv420p", "setsar=1"])
        return ",".join(chain)

    # ------------------------------------------------------------------
    def render_shot(self, shot: Shot, index: int) -> Path:
        """Normalize one shot into an intermediate MP4 with identical params."""

        target = self.workdir / f"shot_{index:05d}.mp4"
        args = [
            "-ss", f"{shot.start:.3f}",
            "-t", f"{shot.duration:.3f}",
            "-i", str(shot.source),
            "-an",
            "-vf", self._filter_for(shot),
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
    def build_video_track(self, shots: Sequence[Shot]) -> Path:
        """Render every shot and join them into one silent video track."""

        rendered: list[Path] = []
        for index, shot in enumerate(shots, start=1):
            try:
                rendered.append(self.render_shot(shot, index))
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
            escaped = str(Path(subtitles).resolve()).replace("\\", "/").replace(":", r"\:")
            video_filters.append(
                f"subtitles='{escaped}':force_style='"
                "FontName=DejaVu Sans,Fontsize=22,PrimaryColour=&H00FFFFFF,"
                "OutlineColour=&H90000000,BorderStyle=3,Outline=1,Shadow=0,MarginV=48'"
            )

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
