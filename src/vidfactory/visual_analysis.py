"""Real frame inspection - judging footage by its pixels, not its caption.

Every quality signal before this module read a provider caption. That is why
run 6 reported ``premium_visual_ratio = 0.912`` while a human reviewer found a
floor plan, a dog on a sofa, two nearly empty rooms and a sofa still wrapped
in plastic in the finished video: Pexels described all five of them as
interiors, and by the only evidence we had, they were.

This module opens the footage. Frames are decoded with FFmpeg - from the
provider's own preview stills where it publishes them, otherwise from the
video itself - and measured directly:

* luminance distribution      -> is it actually a dark scene?
* saturation and colorfulness -> is this a photograph or a line drawing?
* edge density and flatness   -> is there any furniture in this room?
* hue diversity and specular  -> plastic sheeting, or upholstery?
* skin-tone coverage          -> is a person the subject rather than the room?

None of this needs a paid API, a GPU, or a network round trip. It runs in
pure Python over a 96x54 decode of each sampled frame, which is small enough
that inspecting three frames of forty candidates costs a couple of seconds on
a two-core runner.

An optional CLIP image/text model (:mod:`vidfactory.visual_model`) plugs in on
top and scores the same frames against written concepts. It is strictly a
supplement: when it is unavailable the statistics still run, and the report
says which of the two produced the numbers via ``visual_analysis_model``.
"""

from __future__ import annotations

import math
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .ffmpeg_utils import ffmpeg_path
from .entities import (
    EntityGrounding,
    grounding_prompts,
    required_entity,
    score_from_similarities,
)
from .logging_utils import get_logger

log = get_logger("VISUAL")

#: Frames are analyzed at this size. Small on purpose: every statistic below
#: is a distribution over the whole frame, and 5,184 pixels estimate those
#: distributions just as well as two million while costing 400x less Python.
STAT_SIZE: tuple[int, int] = (96, 54)

#: How far a negative concept must out-score every positive one before the
#: flag is certain. CLIP text-image cosines for related prompts differ by
#: hundredths, so the range is small - but it starts at exactly zero, because
#: a negative concept that merely *ties* the best positive is not evidence of
#: anything. Starting below zero gave every clip a floor on every flag: the
#: first margin-scored render put "construction" at 0.2 to 0.44 on all forty
#: clips and dropped premium_visual_ratio to 8%.
CONCEPT_MARGIN_LOW = 0.0
CONCEPT_MARGIN_HIGH = 0.05
#: The same idea for the scene prompt's margin over the average alternative.
SEMANTIC_MARGIN_LOW = -0.02
SEMANTIC_MARGIN_HIGH = 0.06

#: Confidence at which a visual flag rejects a candidate outright.
REJECT_CONFIDENCE = 0.72
#: Confidence at which a visual flag applies a large ranking penalty.
PENALTY_CONFIDENCE = 0.42

#: Positive concepts: what this channel wants footage to be, and what every
#: negative concept has to beat before it counts as evidence.
#:
#: The short entries are not redundant. CLIP scores a short prompt higher than
#: a long one on the same image, so a six-word positive ("a beautiful
#: professionally styled living room") loses to a three-word negative ("a
#: construction site") on footage that is plainly a living room. On a real
#: render that mismatch flagged construction or renovation on fifteen of forty
#: ordinary Pexels interiors. Giving the positives short forms of the same
#: meaning makes the comparison about the meaning again.
POSITIVE_CONCEPTS: tuple[str, ...] = (
    # the descriptive form - what "premium" means here
    "a beautiful professionally styled living room",
    "a bright aspirational home interior",
    "a furnished elegant interior",
    "a cozy high quality living room",
    "modern interior design",
    "a well styled residential room",
    # the same meanings at the length the negatives are written at
    "a living room",
    "a home interior",
    "a furnished room",
    "a decorated room",
    "a styled interior",
    "a bedroom",
)

#: Negative concepts. ``flag`` maps a concept onto the flag it evidences.
NEGATIVE_CONCEPTS: tuple[tuple[str, str], ...] = (
    ("an empty unfurnished room", "empty_room"),
    ("furniture covered with plastic sheeting", "plastic_covered_furniture"),
    ("a room under renovation", "renovation"),
    ("a construction site", "construction"),
    ("a floor plan or architectural drawing", "floor_plan_or_document"),
    ("a person or a pet as the main subject", "dominant_pet_or_person"),
    ("a dark poorly lit room", "dark_scene"),
    ("a close-up of a single generic object", "object_closeup"),
    ("an office", "non_home_space"),
    ("a furniture showroom", "non_home_space"),
    ("an unrelated room type", "unrelated_room"),
)

#: Every flag this module can raise, in report order.
FLAG_NAMES: tuple[str, ...] = (
    "empty_room",
    "plastic_covered_furniture",
    "renovation",
    "construction",
    "floor_plan_or_document",
    "dominant_pet_or_person",
    "dark_scene",
    "non_home_space",
    "object_closeup",
    "unrelated_room",
)


# ---------------------------------------------------------------------------
# Frames
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Frame:
    """One decoded frame as packed rgb24 bytes."""

    width: int
    height: int
    pixels: bytes
    source: str = ""
    timestamp: float = 0.0

    @property
    def ok(self) -> bool:
        return self.width > 0 and len(self.pixels) == self.width * self.height * 3


def sample_positions(duration: float, count: int = 3) -> list[float]:
    """Where to sample a clip: near the start, the middle, and near the end.

    The first and last frames of stock footage are often a fade or a still
    hold, so the ends are sampled inside the clip rather than at it.
    """

    count = max(1, int(count))
    duration = max(0.0, float(duration))
    if duration <= 0.2:
        return [0.0] * count
    if count == 1:
        return [duration * 0.5]
    lead, tail = duration * 0.12, duration * 0.88
    step = (tail - lead) / (count - 1)
    return [round(lead + step * i, 3) for i in range(count)]


def decode_frame(
    source: str | Path,
    timestamp: float | None = None,
    size: tuple[int, int] = STAT_SIZE,
    timeout: float = 30.0,
) -> Frame | None:
    """Decode one frame of a video or still image to raw rgb24 via FFmpeg.

    ``source`` may be a local path, an http(s) video URL or an http(s) still.
    Seeking before ``-i`` keeps a remote seek to a byte range instead of a
    full download.
    """

    width, height = int(size[0]), int(size[1])
    command = [ffmpeg_path(), "-nostdin", "-v", "error"]
    if timestamp is not None and float(timestamp) > 0:
        command += ["-ss", f"{float(timestamp):.3f}"]
    command += [
        "-i", str(source),
        "-frames:v", "1",
        "-vf", f"scale={width}:{height}:force_original_aspect_ratio=disable",
        "-f", "rawvideo",
        "-pix_fmt", "rgb24",
        "-",
    ]
    try:
        proc = subprocess.run(
            command, capture_output=True, timeout=timeout, check=False
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        log.debug("frame decode failed for %s: %s", source, exc)
        return None
    data = proc.stdout or b""
    if len(data) < width * height * 3:
        log.debug(
            "frame decode returned %d bytes for %s (%s)",
            len(data), source, (proc.stderr or b"")[:120].decode("utf-8", "replace"),
        )
        return None
    return Frame(
        width=width,
        height=height,
        pixels=data[: width * height * 3],
        source=str(source),
        timestamp=float(timestamp or 0.0),
    )


def sample_frames(
    video: str | Path | None = None,
    stills: Sequence[str] = (),
    duration: float = 0.0,
    count: int = 3,
    size: tuple[int, int] = STAT_SIZE,
    timeout: float = 30.0,
) -> list[Frame]:
    """Collect up to ``count`` frames spread across a clip.

    Provider preview stills are preferred when there are enough of them:
    Pexels publishes about fifteen stills sampled across every video, so the
    beginning, middle and end can be inspected without transferring a single
    frame of the video itself. Otherwise the video is decoded directly.
    """

    count = max(1, int(count))
    chosen: list[Frame] = []

    usable_stills = [s for s in stills if s]
    if len(usable_stills) >= count:
        # Spread the picks across the published stills rather than taking the
        # first three, which would all come from the opening second.
        step = (len(usable_stills) - 1) / (count - 1) if count > 1 else 0
        picks = [usable_stills[int(round(i * step))] for i in range(count)]
        for index, url in enumerate(dict.fromkeys(picks)):
            frame = decode_frame(url, None, size, timeout)
            if frame and frame.ok:
                chosen.append(frame)
        if len(chosen) >= min(count, 2):
            return chosen[:count]

    if video:
        for position in sample_positions(duration, count):
            frame = decode_frame(video, position, size, timeout)
            if frame and frame.ok:
                chosen.append(frame)
            if len(chosen) >= count:
                break

    if not chosen and usable_stills:
        frame = decode_frame(usable_stills[0], None, size, timeout)
        if frame and frame.ok:
            chosen.append(frame)
    return chosen[:count]


# ---------------------------------------------------------------------------
# Pixel statistics
# ---------------------------------------------------------------------------

@dataclass
class FrameStats:
    """Measured properties of one frame. Every field is 0.0 - 1.0 unless noted."""

    mean_luma: float = 0.0            # 0-255
    p05_luma: float = 0.0             # 0-255
    p95_luma: float = 0.0             # 0-255
    luma_spread: float = 0.0          # 0-255
    mean_saturation: float = 0.0
    colorfulness: float = 0.0         # 0-110ish, Hasler-Suesstrunk
    white_fraction: float = 0.0
    black_fraction: float = 0.0
    specular_fraction: float = 0.0
    edge_density: float = 0.0         # mean absolute gradient, 0-255
    strong_edge_fraction: float = 0.0
    flat_fraction: float = 0.0
    vertical_bias: float = 0.0        # -1 horizontal .. +1 vertical structure
    distinct_hues: int = 0
    hue_entropy: float = 0.0
    green_fraction: float = 0.0
    warm_fraction: float = 0.0
    skin_fraction: float = 0.0
    center_skin_fraction: float = 0.0
    outer_skin_fraction: float = 0.0
    lower_flat_fraction: float = 0.0
    upper_brightness: float = 0.0     # 0-255
    lower_brightness: float = 0.0     # 0-255

    def to_dict(self) -> dict[str, Any]:
        return {
            k: (round(v, 4) if isinstance(v, float) else v)
            for k, v in self.__dict__.items()
        }


def _percentile(sorted_values: Sequence[float], fraction: float) -> float:
    if not sorted_values:
        return 0.0
    index = min(len(sorted_values) - 1, max(0, int(fraction * (len(sorted_values) - 1))))
    return float(sorted_values[index])


def measure(frame: Frame) -> FrameStats:
    """Compute every statistic for one frame in a single pass over the pixels."""

    width, height, data = frame.width, frame.height, frame.pixels
    total = width * height
    if total <= 0 or len(data) < total * 3:
        return FrameStats()

    luma: list[float] = [0.0] * total
    sat_sum = 0.0
    white = black = specular = 0
    skin = center_skin = center_total = 0
    green = warm = saturated = 0
    hue_bins = [0] * 12
    rg_sum = rg_sq = yb_sum = yb_sq = 0.0

    x0, x1 = width // 4, (width * 3) // 4
    y0, y1 = height // 5, (height * 4) // 5

    index = 0
    for y in range(height):
        in_center_row = y0 <= y < y1
        for x in range(width):
            r = data[index]
            g = data[index + 1]
            b = data[index + 2]
            index += 3

            value = 0.299 * r + 0.587 * g + 0.114 * b
            luma[y * width + x] = value
            if value >= 235:
                white += 1
                if value >= 248:
                    specular += 1
            elif value <= 25:
                black += 1

            high = r if r >= g else g
            if b > high:
                high = b
            low = r if r <= g else g
            if b < low:
                low = b
            delta = high - low
            saturation = (delta / high) if high else 0.0
            sat_sum += saturation

            rg = float(r - g)
            yb = 0.5 * (r + g) - b
            rg_sum += rg
            rg_sq += rg * rg
            yb_sum += yb
            yb_sq += yb * yb

            if saturation > 0.15 and delta:
                saturated += 1
                if high == r:
                    hue = ((g - b) / delta) % 6
                elif high == g:
                    hue = ((b - r) / delta) + 2
                else:
                    hue = ((r - g) / delta) + 4
                degrees = hue * 60.0
                hue_bins[int(degrees // 30) % 12] += 1
                if 70 <= degrees <= 165:
                    green += 1
                elif degrees <= 55 or degrees >= 340:
                    warm += 1

            # Kovac's RGB skin rule, which is cheap and orientation free.
            if (
                r > 95 and g > 40 and b > 20
                and delta > 15
                and abs(r - g) > 15
                and r > g and r > b
            ):
                skin += 1
                if in_center_row and x0 <= x < x1:
                    center_skin += 1
            if in_center_row and x0 <= x < x1:
                center_total += 1

    # ---- gradients -------------------------------------------------------
    gradient_sum = 0.0
    strong = flat = samples = 0
    vertical_energy = horizontal_energy = 0.0
    lower_flat = lower_samples = 0
    lower_start = (height * 2) // 3
    for y in range(height - 1):
        row = y * width
        next_row = row + width
        for x in range(width - 1):
            here = luma[row + x]
            dx = abs(luma[row + x + 1] - here)
            dy = abs(luma[next_row + x] - here)
            gradient = dx + dy
            gradient_sum += gradient
            samples += 1
            horizontal_energy += dx
            vertical_energy += dy
            if gradient > 40:
                strong += 1
            elif gradient < 6:
                flat += 1
                if y >= lower_start:
                    lower_flat += 1
            if y >= lower_start:
                lower_samples += 1

    upper_sum = sum(luma[: width * (height // 3)]) or 0.0
    lower_sum = sum(luma[width * lower_start:]) or 0.0
    upper_count = max(1, width * (height // 3))
    lower_count = max(1, total - width * lower_start)

    ordered = sorted(luma)
    mean_luma = sum(luma) / total
    mean_rg, mean_yb = rg_sum / total, yb_sum / total
    var_rg = max(0.0, rg_sq / total - mean_rg * mean_rg)
    var_yb = max(0.0, yb_sq / total - mean_yb * mean_yb)
    colorfulness = math.sqrt(var_rg + var_yb) + 0.3 * math.sqrt(
        mean_rg * mean_rg + mean_yb * mean_yb
    )

    entropy = 0.0
    if saturated:
        for count in hue_bins:
            if count:
                share = count / saturated
                entropy -= share * math.log(share, 2)

    samples = max(1, samples)
    return FrameStats(
        mean_luma=mean_luma,
        p05_luma=_percentile(ordered, 0.05),
        p95_luma=_percentile(ordered, 0.95),
        luma_spread=_percentile(ordered, 0.95) - _percentile(ordered, 0.05),
        mean_saturation=sat_sum / total,
        colorfulness=colorfulness,
        white_fraction=white / total,
        black_fraction=black / total,
        specular_fraction=specular / total,
        edge_density=gradient_sum / samples,
        strong_edge_fraction=strong / samples,
        flat_fraction=flat / samples,
        vertical_bias=(
            (vertical_energy - horizontal_energy)
            / max(1.0, vertical_energy + horizontal_energy)
        ),
        distinct_hues=sum(1 for c in hue_bins if c >= max(4, saturated * 0.04)),
        hue_entropy=entropy,
        green_fraction=green / total,
        warm_fraction=warm / total,
        skin_fraction=skin / total,
        center_skin_fraction=center_skin / max(1, center_total),
        outer_skin_fraction=(skin - center_skin) / max(1, total - center_total),
        lower_flat_fraction=lower_flat / max(1, lower_samples),
        upper_brightness=upper_sum / upper_count,
        lower_brightness=lower_sum / lower_count,
    )


# ---------------------------------------------------------------------------
# Flag detectors
#
# Each returns (confidence 0.0-1.0, evidence). Confidence from pixels alone is
# deliberately capped below :data:`REJECT_CONFIDENCE` for the categories that
# statistics cannot settle on their own - a bright minimal room and an empty
# one differ by how much furniture is in them, and a 96x54 histogram only
# narrows that down. Those flags reject a clip when the caption or the CLIP
# backend independently agrees; on their own they apply a heavy penalty.
# ---------------------------------------------------------------------------

def _ramp(value: float, low: float, high: float) -> float:
    """0.0 at or below ``low``, 1.0 at or above ``high``, linear between."""

    if high <= low:
        return 1.0 if value >= high else 0.0
    return max(0.0, min(1.0, (value - low) / (high - low)))


def _band(value: float, low: float, high: float, slack: float) -> float:
    """1.0 inside [low, high], falling to 0.0 ``slack`` beyond either edge."""

    if low <= value <= high:
        return 1.0
    if value < low:
        return _ramp(value, low - slack, low)
    return 1.0 - _ramp(value, high, high + slack)


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def detect_floor_plan(s: FrameStats) -> tuple[float, list[str]]:
    """A drawing, a document or a floor plan rather than a photograph.

    The giveaway is not brightness - plenty of beautiful rooms are white - but
    that even the *darkest* five percent of the frame is bright. A photograph
    of a white room still contains shadows under the sofa; a line drawing on
    paper does not.
    """

    if (
        s.mean_saturation > 0.20
        or s.mean_luma < 155
        or s.colorfulness > 20.0
        # A drawing is made of lines. An empty white room has no edges at all,
        # which is what separates the two once both are pale and colourless.
        or s.strong_edge_fraction < 0.010
    ):
        return 0.0, []
    parts = [
        _ramp(s.white_fraction, 0.20, 0.70),
        _ramp(s.mean_luma, 155.0, 225.0),
        _ramp(0.20 - s.mean_saturation, 0.03, 0.17),
        _ramp(20.0 - s.colorfulness, 4.0, 18.0),
        _ramp(s.strong_edge_fraction, 0.010, 0.09),
        _ramp(s.p05_luma, 60.0, 190.0),
    ]
    return round(_mean(parts), 3), [
        f"colorfulness={s.colorfulness:.1f}",
        f"saturation={s.mean_saturation:.3f}",
        f"strong_edges={s.strong_edge_fraction:.3f}",
    ]


def detect_dark(s: FrameStats) -> tuple[float, list[str]]:
    if s.mean_luma > 96:
        return 0.0, []
    confidence = max(
        _ramp(96.0 - s.mean_luma, 4.0, 46.0),
        0.8 * _ramp(150.0 - s.p95_luma, 10.0, 70.0),
    )
    evidence = [f"mean_luma={s.mean_luma:.0f}", f"p95_luma={s.p95_luma:.0f}"]
    # Warm evening ambience is the look this channel wants, not a fault.
    if s.warm_fraction > 0.18 and s.specular_fraction > 0.004:
        confidence *= 0.45
        evidence.append("warm ambience")
    return round(min(1.0, confidence), 3), evidence


def detect_empty_room(s: FrameStats) -> tuple[float, list[str]]:
    """Large flat areas, almost no edges and almost no colour: nothing in it."""

    if s.flat_fraction < 0.55 or s.edge_density > 11.0:
        return 0.0, []
    parts = [
        _ramp(s.flat_fraction, 0.55, 0.90),
        _ramp(12.0 - s.edge_density, 2.0, 10.0),
        _ramp(38.0 - s.colorfulness, 6.0, 30.0),
        _ramp(s.lower_flat_fraction, 0.50, 0.92),
    ]
    return round(_mean(parts) * 0.70, 3), [
        f"flat={s.flat_fraction:.2f}",
        f"edges={s.edge_density:.1f}",
        f"lower_flat={s.lower_flat_fraction:.2f}",
    ]


def detect_plastic_cover(s: FrameStats) -> tuple[float, list[str]]:
    """Sheeting over furniture: colourless, bright, and glinting.

    Plastic reads as a desaturated drape with hard specular highlights on the
    folds - bright pixels where a fabric of the same lightness would have
    none - over a shape that still has furniture-scale edges.
    """

    if (
        s.mean_saturation > 0.22
        or s.specular_fraction < 0.0035
        or s.colorfulness > 22.0
        # Sheeting drapes in soft folds; hard lines everywhere mean a drawing.
        or s.strong_edge_fraction > 0.06
    ):
        return 0.0, []
    parts = [
        _ramp(0.22 - s.mean_saturation, 0.03, 0.19),
        _ramp(s.specular_fraction, 0.0035, 0.05),
        _ramp(s.white_fraction, 0.06, 0.45),
        _ramp(4.0 - s.distinct_hues, 0.5, 3.5),
        _band(s.edge_density, 4.0, 16.0, 8.0),
    ]
    return round(_mean(parts) * 0.80, 3), [
        f"saturation={s.mean_saturation:.3f}",
        f"specular={s.specular_fraction:.4f}",
        f"hues={s.distinct_hues}",
    ]


def detect_renovation(s: FrameStats) -> tuple[float, list[str]]:
    """Bare, dusty and busy: stripped walls, tools, materials on the floor."""

    if (
        s.mean_saturation > 0.30
        or s.strong_edge_fraction < 0.02
        # Bright and airy is not a building site, and a colourless frame is a
        # drawing rather than a stripped room.
        or s.mean_luma > 190
        or s.colorfulness < 8.0
    ):
        return 0.0, []
    parts = [
        _ramp(0.30 - s.mean_saturation, 0.05, 0.26),
        _ramp(s.strong_edge_fraction, 0.02, 0.16),
        _ramp(s.edge_density, 8.0, 26.0),
        _ramp(150.0 - s.mean_luma, 5.0, 80.0),
    ]
    return round(_mean(parts) * 0.62, 3), [
        f"saturation={s.mean_saturation:.3f}",
        f"strong_edges={s.strong_edge_fraction:.3f}",
    ]


def detect_construction(s: FrameStats) -> tuple[float, list[str]]:
    confidence, evidence = detect_renovation(s)
    if not confidence or s.green_fraction > 0.08:
        return 0.0, []
    return round(confidence * 0.8, 3), evidence


def detect_person_or_pet(s: FrameStats) -> tuple[float, list[str]]:
    """A subject in the middle of the frame rather than a room.

    Skin tone alone is a poor signal indoors - oak floors, terracotta and warm
    beige walls all satisfy any RGB skin rule - so what counts is
    *concentration*: skin-toned pixels clustered in the centre of the frame
    and comparatively absent from its edges. That is a body or an animal in
    front of the camera. It is capped well below the rejection threshold
    because it cannot tell a person from a cushion on its own.
    """

    if s.center_skin_fraction < 0.18:
        return 0.0, []
    concentration = s.center_skin_fraction / max(0.02, s.outer_skin_fraction)
    if concentration < 1.6:
        return 0.0, []
    confidence = _ramp(s.center_skin_fraction, 0.14, 0.46) * _ramp(concentration, 1.6, 3.2)
    return round(min(0.55, confidence), 3), [
        f"center_skin={s.center_skin_fraction:.2f}",
        f"concentration={concentration:.1f}x",
    ]


def detect_object_closeup(s: FrameStats) -> tuple[float, list[str]]:
    if s.edge_density > 8.0 or s.distinct_hues > 3 or s.colorfulness < 25.0:
        return 0.0, []
    parts = [
        _ramp(9.0 - s.edge_density, 1.0, 7.0),
        _ramp(4.0 - s.distinct_hues, 0.5, 3.0),
        _ramp(s.colorfulness, 25.0, 60.0),
    ]
    return round(_mean(parts) * 0.5, 3), [f"edges={s.edge_density:.1f}"]


#: name -> detector. ``non_home_space`` and ``unrelated_room`` are deliberately
#: absent: no pixel statistic separates a living room from a hotel lobby, so
#: those two are left to the caption signals and the CLIP backend.
STAT_DETECTORS = {
    "floor_plan_or_document": detect_floor_plan,
    "dark_scene": detect_dark,
    "empty_room": detect_empty_room,
    "plastic_covered_furniture": detect_plastic_cover,
    "renovation": detect_renovation,
    "construction": detect_construction,
    "dominant_pet_or_person": detect_person_or_pet,
    "object_closeup": detect_object_closeup,
}


def interior_likeness(s: FrameStats) -> float:
    """How much the frame looks like a photograph of a furnished room."""

    parts = [
        _ramp(s.colorfulness, 10.0, 48.0),
        _band(s.flat_fraction, 0.22, 0.76, 0.22),
        _ramp(float(s.distinct_hues), 1.0, 6.0),
        _band(s.mean_luma, 90.0, 205.0, 60.0),
        _band(s.edge_density, 6.0, 30.0, 8.0),
    ]
    return round(_mean(parts), 3)


# ---------------------------------------------------------------------------
# Scene-to-clip semantic matching
#
# The narration says "paint the trim the same color as the walls". A gorgeous
# but unrelated luxury living room is the wrong clip for that sentence, and no
# amount of beauty makes it right. Where the CLIP backend is present the match
# is a real image/text similarity. Where it is not, each family of narration
# has a *visual expectation* - what a frame that demonstrates that sentence
# actually looks like - and the frame is measured against it.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class VisualExpectation:
    name: str
    triggers: tuple[str, ...]
    describe: str
    weights: tuple[tuple[str, float, float, float], ...]
    #: ``(statistic, low, high, weight)``; ``low > high`` inverts the ramp.

    def score(self, s: FrameStats) -> float:
        parts: list[float] = []
        total = 0.0
        for name, low, high, weight in self.weights:
            value = float(getattr(s, name, 0.0))
            fit = _ramp(value, low, high) if high >= low else _ramp(-value, -low, -high)
            parts.append(fit * weight)
            total += weight
        return round(sum(parts) / total, 3) if total else 0.5


EXPECTATIONS: tuple[VisualExpectation, ...] = (
    VisualExpectation(
        "wall_and_trim_paint",
        ("paint", "painted", "trim", "molding", "moulding", "skirting",
         "baseboard", "wall color", "wall colour", "walls", "monochrome",
         "same color", "same colour", "doorway", "door frame", "architrave"),
        "broad flat painted planes in one or two tones",
        (("flat_fraction", 0.30, 0.75, 1.0),
         ("distinct_hues", 5.0, 2.0, 1.0),
         ("mean_luma", 80.0, 185.0, 0.8),
         ("strong_edge_fraction", 0.12, 0.02, 0.6)),
    ),
    VisualExpectation(
        "curtains_and_windows",
        ("curtain", "drape", "rod", "blind", "shutter", "window",
         "daylight", "natural light", "sunlight"),
        "tall bright vertical bands against a wall",
        (("vertical_bias", -0.15, 0.30, 1.0),
         ("p95_luma", 150.0, 245.0, 1.0),
         ("upper_brightness", 90.0, 210.0, 0.8)),
    ),
    VisualExpectation(
        "mirror_and_reflection",
        ("mirror", "reflect", "reflection", "glass", "glazed", "glossy"),
        "a bright reflective plane with a hard outline",
        (("specular_fraction", 0.002, 0.05, 1.0),
         ("luma_spread", 60.0, 200.0, 0.9),
         ("strong_edge_fraction", 0.01, 0.10, 0.7)),
    ),
    VisualExpectation(
        "visible_floor",
        ("floor", "flooring", "rug", "carpet", "legs", "walkway", "pathway",
         "path", "circulation", "square footage", "floor space"),
        "an uninterrupted run of floor in the lower frame",
        (("lower_flat_fraction", 0.25, 0.80, 1.0),
         ("lower_brightness", 45.0, 175.0, 0.7),
         ("edge_density", 34.0, 8.0, 0.6)),
    ),
    VisualExpectation(
        "lighting",
        ("lamp", "light", "lighting", "sconce", "pendant", "chandelier",
         "bulb", "dimmer", "glow", "lit"),
        "a visible light source and warm falloff",
        (("specular_fraction", 0.001, 0.04, 1.0),
         ("warm_fraction", 0.05, 0.45, 0.9),
         ("luma_spread", 60.0, 200.0, 0.7)),
    ),
    VisualExpectation(
        "vertical_storage",
        ("shelf", "shelves", "shelving", "bookshelf", "storage", "cabinet",
         "cupboard", "wardrobe", "vertical", "ceiling", "tall", "height",
         "floor to ceiling", "upward"),
        "repeating structure carrying the eye upward",
        (("edge_density", 6.0, 30.0, 1.0),
         ("strong_edge_fraction", 0.01, 0.12, 0.9),
         ("upper_brightness", 50.0, 190.0, 0.5)),
    ),
    VisualExpectation(
        "seating",
        ("sofa", "couch", "armchair", "chair", "seating", "cushion",
         "upholstery", "ottoman", "bench"),
        "large soft furniture shapes",
        (("flat_fraction", 0.20, 0.62, 1.0),
         ("colorfulness", 14.0, 55.0, 0.8),
         ("edge_density", 4.0, 22.0, 0.7)),
    ),
    VisualExpectation(
        "bedroom",
        ("bed", "headboard", "bedding", "duvet", "linen", "nightstand",
         "bedside", "mattress", "pillow"),
        "a large low horizontal mass with soft folds",
        (("vertical_bias", 0.25, -0.15, 1.0),
         ("flat_fraction", 0.25, 0.70, 0.9),
         ("mean_luma", 70.0, 190.0, 0.6)),
    ),
    VisualExpectation(
        "plants",
        ("plant", "plants", "greenery", "foliage", "leaf", "leaves",
         "botanical", "tree", "fern"),
        "living green foliage in frame",
        (("green_fraction", 0.01, 0.22, 1.0),
         ("colorfulness", 15.0, 55.0, 0.5)),
    ),
    VisualExpectation(
        "kitchen",
        ("kitchen", "counter", "countertop", "backsplash", "cabinetry",
         "appliance", "worktop", "island"),
        "long horizontal working surfaces",
        (("vertical_bias", 0.25, -0.10, 1.0),
         ("edge_density", 6.0, 28.0, 0.8),
         ("mean_luma", 70.0, 195.0, 0.6)),
    ),
    VisualExpectation(
        "decluttered_surfaces",
        ("clutter", "declutter", "surfaces", "tidy", "minimal", "edited",
         "clear", "negative space", "pare"),
        "calm surfaces with very little on them",
        (("flat_fraction", 0.35, 0.78, 1.0),
         ("strong_edge_fraction", 0.10, 0.01, 0.9),
         ("colorfulness", 8.0, 40.0, 0.5)),
    ),
    VisualExpectation(
        "artwork",
        ("art", "artwork", "frame", "framed", "gallery", "picture", "print",
         "poster", "canvas"),
        "framed rectangles hung on a plain wall",
        (("strong_edge_fraction", 0.005, 0.09, 1.0),
         ("flat_fraction", 0.28, 0.72, 0.8)),
    ),
    VisualExpectation(
        "textiles",
        ("throw", "blanket", "fabric", "textile", "wool", "weave", "texture",
         "velvet", "linen"),
        "close woven texture and soft shadow",
        (("edge_density", 8.0, 34.0, 1.0),
         ("colorfulness", 12.0, 50.0, 0.7)),
    ),
)

#: Alternatives the CLIP backend scores a scene prompt against, so the match
#: is "does this frame show *this* rather than something else a decor video
#: might show", not "is this vaguely an interior".
DISTRACTOR_PROMPTS: tuple[str, ...] = (
    "a kitchen counter",
    "a bathroom",
    "an empty hallway",
    "a person sitting on a sofa",
    "an architectural floor plan",
    "an office desk",
    "a bedroom with a made bed",
    "a close-up of a potted plant",
    "the outside of a house",
)


def match_expectations(text: str) -> list[VisualExpectation]:
    """Which visual expectations a narration line or query triggers."""

    haystack = " " + re.sub(r"[^a-z0-9]+", " ", str(text or "").lower()).strip() + " "
    matched: list[VisualExpectation] = []
    for expectation in EXPECTATIONS:
        for trigger in expectation.triggers:
            word = re.sub(r"[^a-z0-9]+", " ", trigger.lower()).strip()
            if f" {word} " in haystack or f" {word}s " in haystack:
                matched.append(expectation)
                break
    return matched


# ---------------------------------------------------------------------------
# The analysis record
# ---------------------------------------------------------------------------

#: How much each flag costs a clip's premium visual score.
FLAG_DAMAGE: dict[str, float] = {
    "floor_plan_or_document": 0.95,
    "empty_room": 0.90,
    "plastic_covered_furniture": 0.90,
    "renovation": 0.85,
    "construction": 0.85,
    "dominant_pet_or_person": 0.70,
    "dark_scene": 0.60,
    "non_home_space": 0.55,
    "unrelated_room": 0.55,
    "object_closeup": 0.40,
}


def combine_confidence(a: float, b: float) -> float:
    """Merge two independent estimates of the same flag.

    Two weak-but-agreeing signals are worth more than either alone - a caption
    saying "empty apartment" and a frame with no edges in it are separate
    pieces of evidence - so agreement compounds. A single signal never does.
    """

    a, b = max(0.0, min(1.0, a)), max(0.0, min(1.0, b))
    if a >= 0.35 and b >= 0.35:
        return round(1.0 - (1.0 - a) * (1.0 - b), 3)
    return round(max(a, b), 3)


@dataclass
class VisualAnalysis:
    """What the pixels of one candidate clip actually show."""

    analyzed: bool = False
    frame_count: int = 0
    model: str = "none"
    semantic_source: str = "none"
    flags: dict[str, float] = field(default_factory=dict)
    evidence: dict[str, list[str]] = field(default_factory=dict)
    semantic_match: float = 0.5
    interior_likeness: float = 0.5
    brightness: float = 0.0
    premium_visual_score: float = 0.0
    is_premium_visual: bool = False
    rejected: bool = False
    reject_reason: str = ""
    frames: list[dict[str, Any]] = field(default_factory=list)
    expectations: list[str] = field(default_factory=list)
    #: The object this shot's narration promised, and whether it is on screen.
    #: A high ``semantic_match`` cannot stand in for it: run 25 averaged 0.569
    #: while showing ribbons for painted trim and plants for an undersized rug.
    grounding: EntityGrounding = field(default_factory=EntityGrounding)

    @property
    def penalised_flags(self) -> dict[str, float]:
        return {k: v for k, v in self.flags.items() if v >= PENALTY_CONFIDENCE}

    def to_dict(self) -> dict[str, Any]:
        return {
            "analyzed": self.analyzed,
            "model": self.model,
            "frame_count": self.frame_count,
            "semantic_match": round(self.semantic_match, 3),
            "semantic_source": self.semantic_source,
            "interior_likeness": round(self.interior_likeness, 3),
            "brightness": round(self.brightness, 1),
            "premium_visual_score": round(self.premium_visual_score, 3),
            "is_premium_visual": self.is_premium_visual,
            "rejected": self.rejected,
            "reject_reason": self.reject_reason,
            "expectations": list(self.expectations),
            "flags": {k: round(v, 3) for k, v in sorted(self.flags.items()) if v > 0},
            "evidence": {k: v[:3] for k, v in self.evidence.items() if v},
            **self.grounding.to_dict(),
        }


#: Every concept, distractor and scene prompt goes through one template, so
#: comparisons are between meanings rather than between phrasings.
PROMPT_TEMPLATE = "a photo of {}"


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)


def downsample(frame: Frame, size: tuple[int, int] = STAT_SIZE) -> Frame:
    """Nearest-neighbour shrink, so one decode can serve both consumers."""

    width, height = int(size[0]), int(size[1])
    if frame.width == width and frame.height == height:
        return frame
    source = frame.pixels
    out = bytearray(width * height * 3)
    for y in range(height):
        sy = min(frame.height - 1, y * frame.height // height)
        row = sy * frame.width
        target = y * width * 3
        for x in range(width):
            sx = min(frame.width - 1, x * frame.width // width)
            index = (row + sx) * 3
            out[target] = source[index]
            out[target + 1] = source[index + 1]
            out[target + 2] = source[index + 2]
            target += 3
    return Frame(width, height, bytes(out), frame.source, frame.timestamp)


class VisualAnalyzer:
    """Turns sampled frames into a judgement about one clip.

    ``model`` is any object exposing ``name``, ``image_size``,
    ``encode_images(frames)`` and ``encode_texts(texts)``. When it is ``None``
    the pixel statistics carry the analysis on their own and say so.
    """

    def __init__(
        self,
        model: Any | None = None,
        frames_per_clip: int = 3,
        timeout: float = 30.0,
        reject_confidence: float = REJECT_CONFIDENCE,
        penalty_confidence: float = PENALTY_CONFIDENCE,
        allow_remote_video: bool = True,
    ) -> None:
        self.model = model
        self.frames_per_clip = max(1, int(frames_per_clip))
        self.timeout = float(timeout)
        self.reject_confidence = float(reject_confidence)
        self.penalty_confidence = float(penalty_confidence)
        self.allow_remote_video = bool(allow_remote_video)
        self._text_cache: dict[str, list[float]] = {}

    # ------------------------------------------------------------------
    @property
    def model_name(self) -> str:
        if self.model is None:
            return "pixel-statistics"
        return f"{getattr(self.model, 'name', 'clip')}+pixel-statistics"

    @property
    def decode_size(self) -> tuple[int, int]:
        if self.model is None:
            return STAT_SIZE
        edge = int(getattr(self.model, "image_size", 224))
        return (edge, edge)

    # ------------------------------------------------------------------
    def sample(self, clip: Any, video: str | Path | None = None) -> list[Frame]:
        """Decode representative frames for one clip, cheapest source first."""

        stills = list(getattr(clip, "preview_images", None) or [])
        single = getattr(clip, "preview_image", "")
        if single and single not in stills:
            stills.append(single)

        source: str | Path | None = video or getattr(clip, "local_path", "") or None
        if source is None and self.allow_remote_video:
            source = getattr(clip, "download_url", "") or None

        return sample_frames(
            video=source,
            stills=stills,
            duration=float(getattr(clip, "duration", 0.0) or 0.0),
            count=self.frames_per_clip,
            size=self.decode_size,
            timeout=self.timeout,
        )

    # ------------------------------------------------------------------
    def analyze(
        self,
        frames: Sequence[Frame],
        query: str = "",
        narration: str = "",
        metadata_flags: Mapping[str, float] | None = None,
    ) -> VisualAnalysis:
        """Judge a clip from its frames plus whatever the caption suggested."""

        metadata_flags = dict(metadata_flags or {})
        usable = [f for f in frames if f and f.ok]
        if not usable:
            # No pixels: fall back to whatever metadata said, and be explicit
            # that no frame was ever opened.
            analysis = VisualAnalysis(
                analyzed=False,
                model=self.model_name,
                semantic_source="none",
                flags={k: round(float(v), 3) for k, v in metadata_flags.items() if v > 0},
            )
            analysis.premium_visual_score = self._premium(0.5, analysis.flags)
            analysis.is_premium_visual = False
            entity = required_entity(f"{query} {narration}")
            if entity is not None:
                # Required, but nothing was ever opened to look for it. Named
                # in the report, not counted as a failure: an unchecked shot
                # is not a measured absence.
                analysis.grounding = EntityGrounding(
                    entity=entity.name, labels=entity.labels
                )
            return analysis

        stat_frames = [downsample(f, STAT_SIZE) for f in usable]
        stats = [measure(f) for f in stat_frames]

        # ---- flags from pixels -------------------------------------------
        flags: dict[str, float] = {}
        evidence: dict[str, list[str]] = {}
        for name, detector in STAT_DETECTORS.items():
            per_frame = [detector(s) for s in stats]
            # A flag counts when it holds across the clip, not in one frame:
            # the median keeps a single dark transition from condemning a clip
            # and keeps one lit frame from rescuing a dark one.
            confidences = sorted(c for c, _ in per_frame)
            median = confidences[len(confidences) // 2]
            if median > 0:
                flags[name] = round(median, 3)
                best = max(per_frame, key=lambda item: item[0])
                evidence[name] = list(best[1])

        # ---- the CLIP backend, when present ------------------------------
        semantic_source = "pixel-expectations"
        semantic = 0.5
        image_vectors: list[list[float]] = []
        if self.model is not None:
            try:
                image_vectors = list(self.model.encode_images(usable))
            except Exception as exc:                     # pragma: no cover
                log.warning("visual model failed on images: %s", exc)
                image_vectors = []
        if image_vectors:
            concept_flags = self._concept_flags(image_vectors)
            for name, value in concept_flags.items():
                flags[name] = combine_confidence(flags.get(name, 0.0), value)
                evidence.setdefault(name, []).append("clip concept")
            matched = self._clip_semantic(image_vectors, query, narration)
            if matched is not None:
                semantic, semantic_source = matched, "clip-embeddings"

        # ---- caption evidence --------------------------------------------
        for name, value in metadata_flags.items():
            if value > 0:
                flags[name] = combine_confidence(flags.get(name, 0.0), float(value))
                evidence.setdefault(name, []).append("caption")

        likeness = round(_mean([interior_likeness(s) for s in stats]), 3)
        expectations = match_expectations(f"{query} {narration}")
        grounding = self._entity_grounding(image_vectors, query, narration)
        if semantic_source == "pixel-expectations":
            semantic = self._expectation_semantic(stats, expectations, likeness)

        analysis = VisualAnalysis(
            analyzed=True,
            frame_count=len(usable),
            model=self.model_name,
            semantic_source=semantic_source,
            flags={k: v for k, v in flags.items() if v > 0},
            evidence=evidence,
            semantic_match=round(semantic, 3),
            interior_likeness=likeness,
            brightness=round(_mean([s.mean_luma for s in stats]), 1),
            expectations=[e.name for e in expectations],
            grounding=grounding,
            frames=[
                {
                    "source": f.source[-72:],
                    "timestamp": round(f.timestamp, 2),
                    "mean_luma": round(s.mean_luma, 1),
                    "saturation": round(s.mean_saturation, 3),
                    "edge_density": round(s.edge_density, 2),
                    "flat_fraction": round(s.flat_fraction, 3),
                    "colorfulness": round(s.colorfulness, 1),
                }
                for f, s in zip(usable, stats)
            ],
        )
        analysis.premium_visual_score = self._premium(likeness, analysis.flags)
        worst = max(analysis.flags.values(), default=0.0)
        analysis.is_premium_visual = (
            analysis.premium_visual_score >= 0.55 and worst < self.penalty_confidence
        )
        for name, confidence in sorted(
            analysis.flags.items(), key=lambda kv: kv[1], reverse=True
        ):
            if confidence >= self.reject_confidence:
                analysis.rejected = True
                analysis.reject_reason = (
                    f"{name} at {confidence:.2f} "
                    f"({', '.join(evidence.get(name, [])[:2])})"
                )
                break
        return analysis

    # ------------------------------------------------------------------
    def analyze_clip(
        self,
        clip: Any,
        query: str = "",
        narration: str = "",
        video: str | Path | None = None,
        metadata_flags: Mapping[str, float] | None = None,
    ) -> VisualAnalysis:
        frames = self.sample(clip, video=video)
        return self.analyze(frames, query=query, narration=narration,
                            metadata_flags=metadata_flags)

    # ------------------------------------------------------------------
    @staticmethod
    def _premium(likeness: float, flags: Mapping[str, float]) -> float:
        """Interior likeness, less what the flags cost it.

        Confidences are put through a ramp before they cost anything, so a
        stack of near-zero suspicions cannot quietly add up to a verdict. Only
        evidence worth acting on damages the score.
        """

        damage = 1.0
        for name, confidence in flags.items():
            effective = _ramp(float(confidence), 0.25, 1.0)
            damage *= 1.0 - FLAG_DAMAGE.get(name, 0.3) * effective
        return round(max(0.0, min(1.0, likeness * damage)), 3)

    @staticmethod
    def _expectation_semantic(
        stats: Sequence[FrameStats],
        expectations: Sequence[VisualExpectation],
        likeness: float,
    ) -> float:
        if not expectations:
            # Nothing specific was asked for, so nothing specific can be
            # confirmed. Neutral, not "great".
            return round(min(0.6, 0.35 + 0.35 * likeness), 3)
        scores = [
            _mean([expectation.score(s) for s in stats]) for expectation in expectations
        ]
        scores.sort(reverse=True)
        best = _mean(scores[:2])
        # Capped: pixel statistics are a proxy for meaning, not a reading of
        # it, and the report should never claim more certainty than that.
        return round(min(0.85, 0.65 * best + 0.35 * likeness), 3)

    # ------------------------------------------------------------------
    def _encode_texts(self, texts: Sequence[str]) -> list[list[float]]:
        missing = [t for t in texts if t not in self._text_cache]
        if missing:
            vectors = list(self.model.encode_texts(missing))
            for text, vector in zip(missing, vectors):
                self._text_cache[text] = list(vector)
        return [self._text_cache[t] for t in texts]

    def _concept_flags(self, image_vectors: Sequence[Sequence[float]]) -> dict[str, float]:
        """Zero-shot concept scoring, as a margin over the positive concepts.

        Not a softmax. CLIP's classification softmax runs at a temperature of
        100, which makes it winner-take-all: a frame that is only marginally
        more like "a room under renovation" than like a styled living room
        comes out at a probability near 1.0, and the first real render duly
        flagged five renovations and four plastic covers in forty perfectly
        ordinary Pexels interiors.

        What we actually want to know is comparative and unnormalised: does
        this frame look *more* like the failure than like any of the six
        descriptions of footage we want? That margin is small, bounded, and
        does not amplify noise.
        """

        prompts = [
            PROMPT_TEMPLATE.format(text)
            for text in (*POSITIVE_CONCEPTS, *(t for t, _ in NEGATIVE_CONCEPTS))
        ]
        try:
            text_vectors = self._encode_texts(prompts)
        except Exception as exc:                          # pragma: no cover
            log.warning("visual model failed on concepts: %s", exc)
            return {}

        offset = len(POSITIVE_CONCEPTS)
        per_flag: dict[str, list[float]] = {}
        for image in image_vectors:
            similarities = [_cosine(image, t) for t in text_vectors]
            best_positive = max(similarities[:offset])
            frame: dict[str, float] = {}
            for index, (_, flag) in enumerate(NEGATIVE_CONCEPTS):
                margin = similarities[offset + index] - best_positive
                # Two concepts can evidence one flag; the strongest wins.
                frame[flag] = max(
                    frame.get(flag, 0.0), _ramp(margin, CONCEPT_MARGIN_LOW, CONCEPT_MARGIN_HIGH)
                )
            for flag, value in frame.items():
                per_flag.setdefault(flag, []).append(value)

        merged: dict[str, float] = {}
        for flag, values in per_flag.items():
            values.sort()
            merged[flag] = round(values[len(values) // 2], 3)
        return {k: v for k, v in merged.items() if v >= 0.12}

    def _entity_grounding(
        self,
        image_vectors: Sequence[Sequence[float]],
        query: str,
        narration: str,
    ) -> EntityGrounding:
        """Is the object the narration is about actually in the picture?

        Asked separately from ``_clip_semantic`` on purpose. That measures how
        well the frames match a *sentence*, and a styled living room matches a
        sentence about the rug in it whether or not the rug is there - same
        palette, same furniture, same vocabulary. Run 25 scored 0.569 on
        average doing exactly that.

        This asks a narrower question with short prompts: does the frame look
        more like "an area rug on the floor" than like the best of "a floor
        with no rug", "indoor potted plants", "a close-up of furniture"? The
        competitors are the failures actually observed, so the comparison is
        against what the search keeps returning rather than against noise.
        """

        entity = required_entity(f"{query} {narration}")
        if entity is None:
            return EntityGrounding()          # abstract advice; nothing to find
        if not image_vectors:
            return EntityGrounding(entity=entity.name, labels=entity.labels)

        prompts, _ = grounding_prompts(entity)
        try:
            text_vectors = self._encode_texts(
                [PROMPT_TEMPLATE.format(p) for p in prompts]
            )
        except Exception as exc:                          # pragma: no cover
            log.warning("visual model failed on entity prompts: %s", exc)
            return EntityGrounding(entity=entity.name, labels=entity.labels)

        per_frame = [
            [_cosine(image, t) for t in text_vectors] for image in image_vectors
        ]
        return score_from_similarities(entity, per_frame, _ramp)

    # ------------------------------------------------------------------
    def _clip_semantic(
        self, image_vectors: Sequence[Sequence[float]], query: str, narration: str
    ) -> float | None:
        """How well the frames show *this* sentence rather than something else.

        Scored by where the scene's own prompt lands among a fixed set of
        plausible alternatives, not by a softmax probability. A specific
        narration prompt ("painted trim matching the wall color") is longer
        and rarer than a generic one ("a bedroom with a made bed"), and under
        a temperature-100 softmax it loses to the generic prompt almost every
        time - which is how the first real render measured an average match of
        0.01 across forty clips that were mostly fine.

        Two scale-free signals instead: the prompt's position in the range of
        similarities, and its margin over the average alternative.
        """

        wanted = (query or narration or "").strip()
        if not wanted:
            return None
        prompt = PROMPT_TEMPLATE.format(wanted) if len(wanted) < 60 else wanted
        prompts = [prompt, *(PROMPT_TEMPLATE.format(d) for d in DISTRACTOR_PROMPTS)]
        try:
            text_vectors = self._encode_texts(prompts)
        except Exception as exc:                          # pragma: no cover
            log.warning("visual model failed on the scene prompt: %s", exc)
            return None

        scores: list[float] = []
        for image in image_vectors:
            similarities = [_cosine(image, t) for t in text_vectors]
            low, high = min(similarities), max(similarities)
            spread = high - low
            position = (similarities[0] - low) / spread if spread > 1e-6 else 0.5
            margin = similarities[0] - _mean(similarities[1:])
            scores.append(
                0.65 * position + 0.35 * _ramp(margin, SEMANTIC_MARGIN_LOW, SEMANTIC_MARGIN_HIGH)
            )
        return round(_mean(scores), 3)


#: Why a clip is not premium, in the words a reviewer would use. Ordered by
#: severity: a frame can carry several flags at once and the report needs one
#: answer per clip, so the first match wins.
PREMIUM_FAILURE_REASONS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("renovation_or_construction", ("renovation", "construction")),
    ("unfinished_or_empty_room", ("empty_room", "plastic_covered_furniture")),
    ("floor_plan_or_document", ("floor_plan_or_document",)),
    ("people_dominate_frame", ("dominant_pet_or_person",)),
    ("poor_lighting", ("dark_scene",)),
    ("not_a_home_interior", ("non_home_space", "unrelated_room")),
    ("object_closeup", ("object_closeup",)),
)


def premium_failure_reason(
    visual: Mapping[str, Any],
    caption_premium: bool | None = None,
    penalty_confidence: float = PENALTY_CONFIDENCE,
) -> str:
    """The one thing most responsible for a clip not counting as premium.

    ``final_shot_premium_visual_ratio`` is a single number, and a single
    number cannot be acted on: 39% could be thirty renovations or thirty
    dim rooms, and those have opposite fixes. This names the dominant cause
    per clip so the ratio can be broken down by what to do about it.

    A clip that the frames like but the caption does not is its own category,
    because the fix there is the caption vocabulary rather than the search.
    """

    if not visual.get("analyzed"):
        return "not_inspected" if caption_premium is not False else "caption_rejected"

    flags = {k: float(v) for k, v in dict(visual.get("flags") or {}).items()}
    acting = {k: v for k, v in flags.items() if v >= penalty_confidence}
    for reason, names in PREMIUM_FAILURE_REASONS:
        if any(name in acting for name in names):
            return reason

    if not bool(visual.get("is_premium_visual")):
        # No single flag was strong enough, so what failed is the composition
        # itself: the frame simply does not look much like a furnished room.
        return "weak_interior_composition"
    if caption_premium is False:
        return "caption_rejected"
    return "premium"


def premium_breakdown(
    pairs: Sequence[tuple[Mapping[str, Any], Mapping[str, Any]]],
    penalty_confidence: float = PENALTY_CONFIDENCE,
) -> dict[str, Any]:
    """Count each reason over ``(caption_report, visual_report)`` pairs."""

    counts: dict[str, int] = {}
    for caption, visual in pairs:
        reason = premium_failure_reason(
            visual, bool(caption.get("is_premium", False)), penalty_confidence
        )
        counts[reason] = counts.get(reason, 0) + 1
    total = sum(counts.values()) or 1
    return {
        "clips": sum(counts.values()),
        "premium": counts.get("premium", 0),
        "ratio": round(counts.get("premium", 0) / total, 3),
        "reasons": dict(sorted(counts.items(), key=lambda kv: kv[1], reverse=True)),
        "percentages": {
            k: round(100.0 * v / total, 1)
            for k, v in sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
        },
    }
