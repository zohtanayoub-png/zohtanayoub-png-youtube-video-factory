"""Premium styled captions - ASS, libass, and nothing that costs money.

``subtitles.srt`` stays exactly as it was: it is what YouTube ingests for
accessibility and search, and it should stay plain. This module adds the other
half - ``subtitles.ass``, rendered into the picture by FFmpeg's libass filter -
because a long-form decor channel is watched on a phone and unstyled burned-in
text looks like a screenshot of a text file.

Three things make these captions comfortable to watch for twenty minutes
rather than for twenty seconds:

* **Short phrases.** Three to seven words, split where the language allows a
  break. A caption is never left ending on "de", "the" or "que", because the
  eye then has to hold an unfinished phrase while the next one loads.
* **Restraint.** A subtle outline, a soft shadow, a quarter-second fade. No
  bouncing, no karaoke wipe, no opaque box across the middle of the room the
  video is about.
* **Emphasis that means something.** One warm accent tone, applied only to
  measurements, numbers, and the words that carry the outcome the title
  promised. Never to a random word for movement's sake.

Everything here is measured in the 1920x1080 frame the pipeline renders, with
a bottom margin well inside the player's own safe area.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

from .logging_utils import get_logger

log = get_logger("ASS")

#: Below this a caption is a flash rather than a caption.
MIN_EVENT_SECONDS = 0.42
MAX_EVENT_SECONDS = 6.0

#: Open-source families, best first. Every one of these is either already on a
#: GitHub Actions runner or installable from the Ubuntu archive, so the style
#: never depends on a font somebody has to license.
FONT_PREFERENCES: tuple[str, ...] = (
    "Inter",              # apt: fonts-inter, OFL
    "Noto Sans",          # apt: fonts-noto-core, OFL
    "Liberation Sans",    # apt: fonts-liberation2, OFL, metric-compatible
    "DejaVu Sans",        # always present on Ubuntu images
)
FALLBACK_FONT = "DejaVu Sans"


def available_font(preferences: Sequence[str] = FONT_PREFERENCES) -> str:
    """The first preferred family this machine can actually render.

    Asked at render time rather than assumed, because a caption in a font the
    runner does not have is a caption in whatever libass substitutes, which is
    usually not what the style was designed around.
    """

    binary = shutil.which("fc-list")
    if not binary:
        return FALLBACK_FONT
    try:
        result = subprocess.run(
            [binary, ":", "family"], capture_output=True, text=True, timeout=30, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return FALLBACK_FONT
    installed = (result.stdout or "").lower()
    for family in preferences:
        if family.lower() in installed:
            return family
    return FALLBACK_FONT


# ---------------------------------------------------------------------------
# Styles
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SubtitleStyle:
    """One caption look, in the coordinates of a 1920x1080 frame."""

    name: str
    font_size: int = 58
    #: &HAABBGGRR - blue, green, red, and an *inverted* alpha byte where 00
    #: is opaque and FF is invisible. Getting that backwards is why the first
    #: burned-in captions had almost no rim: &HC8 is 78% transparent, not 78%
    #: opaque, so the outline that was meant to hold the text against a pale
    #: wall was barely there.
    primary: str = "&H00FFFFFF"      # white, fully opaque
    accent: str = "&H0060B4EF"       # warm amber, for emphasis
    outline_colour: str = "&H14101010"   # near-black, 8% transparent
    shadow_colour: str = "&H78000000"    # black, 47% transparent - a soft drop
    outline: float = 2.6
    shadow: float = 1.6
    bold: int = 1
    #: Distance from the bottom of the frame to the bottom of the text.
    margin_v: int = 118
    margin_h: int = 210
    spacing: float = 0.4
    fade_in_ms: int = 120
    fade_out_ms: int = 120
    emphasis: bool = True
    max_words: int = 7
    min_words: int = 3

    def to_ass(self, font: str) -> str:
        return (
            f"Style: {self.name},{font},{self.font_size},{self.primary},"
            f"{self.primary},{self.outline_colour},{self.shadow_colour},"
            f"{self.bold},0,0,0,100,100,{self.spacing},0,1,"
            f"{self.outline},{self.shadow},2,"
            f"{self.margin_h},{self.margin_h},{self.margin_v},1"
        )


#: The channel default. Large enough to read on a phone, small enough that two
#: lines never cover the room, and warm rather than neon.
PREMIUM = SubtitleStyle(name="Premium")

#: Plain captions for anyone who wants the text and nothing else.
CLEAN = SubtitleStyle(
    name="Clean",
    font_size=54,
    outline_colour="&H14000000",
    shadow_colour="&H90000000",
    outline=2.2,
    shadow=1.0,
    bold=0,
    fade_in_ms=0,
    fade_out_ms=0,
    emphasis=False,
    max_words=8,
)

STYLES: dict[str, SubtitleStyle] = {"premium": PREMIUM, "clean": CLEAN}


def style_for(name: str) -> SubtitleStyle:
    key = str(name or "premium").strip().lower()
    if key in ("none", "off", "false"):
        key = "clean"
    return STYLES.get(key, PREMIUM)


# ---------------------------------------------------------------------------
# Phrase chunking
# ---------------------------------------------------------------------------

#: Punctuation that is always a good place to end a caption.
_BREAK_AFTER = (",", ";", ":", ".", "!", "?", "…")


def _clinging(language: Any) -> frozenset[str]:
    from .languages import resolve_language

    return resolve_language(language).clinging_words


def split_phrases(
    text: str,
    language: Any = None,
    min_words: int = 3,
    max_words: int = 7,
) -> list[str]:
    """Break a sentence into caption-sized phrases at places it can break.

    The rule that matters is the negative one: a caption never ends on an
    article, a preposition or a conjunction, because that leaves the reader
    holding an incomplete phrase. "Si tu salón parece más pequeño" is a
    caption; "Si tu salón parece más pequeño de" is a fragment.
    """

    words = re.sub(r"\s+", " ", str(text or "")).strip().split()
    if not words:
        return []
    clinging = _clinging(language)
    max_words = max(2, int(max_words))
    min_words = max(1, min(int(min_words), max_words))

    phrases: list[str] = []
    current: list[str] = []

    def bare(word: str) -> str:
        return re.sub(r"[^\w]", "", word, flags=re.UNICODE).lower()

    def can_end(index: int) -> bool:
        """Whether the phrase may end on the word at ``index``."""

        if bare(words[index]) in clinging:
            return False
        # Never separate a number from what it measures.
        if index + 1 < len(words) and re.fullmatch(r"[\d.,%]+", words[index]):
            return False
        return True

    for position, word in enumerate(words):
        current.append(word)
        ends_clause = word.endswith(_BREAK_AFTER)
        long_enough = len(current) >= min_words
        at_limit = len(current) >= max_words

        if not long_enough:
            continue
        if ends_clause and can_end(position):
            phrases.append(" ".join(current))
            current = []
            continue
        if at_limit:
            # Walk back to the last word this phrase is allowed to end on.
            cut = len(current)
            while cut > min_words and not can_end(position - (len(current) - cut)):
                cut -= 1
            phrases.append(" ".join(current[:cut]))
            current = current[cut:]

    if current:
        if phrases and len(current) < min_words and len(phrases[-1].split()) + len(current) <= max_words + 2:
            phrases[-1] = f"{phrases[-1]} {' '.join(current)}"
        else:
            phrases.append(" ".join(current))
    return [p for p in phrases if p.strip()]


# ---------------------------------------------------------------------------
# Emphasis
# ---------------------------------------------------------------------------

#: Words worth emphasising because they carry the instruction, not because
#: something needed to move. Measurements and numbers are always in.
_EMPHASIS_ES = (
    "más grande", "más amplio", "más amplia", "más alto", "más alta",
    "más espacioso", "más luminoso", "más caro", "más cara", "acogedor",
    "nunca", "siempre", "jamás", "el doble", "la mitad", "gratis",
    "hasta el techo", "del suelo al techo", "a ras de techo",
)
_EMPHASIS_EN = (
    "bigger", "larger", "taller", "wider", "brighter", "more expensive",
    "never", "always", "twice", "half", "free", "floor to ceiling",
)
_MEASUREMENT = re.compile(
    r"\b\d+(?:[.,]\d+)?\s*(?:%|cm|mm|m|km|kg|in|ft|k|kelvin|"
    r"centímetros?|metros?|milímetros?|grados?|euros?|por ciento)\b",
    re.IGNORECASE | re.UNICODE,
)
_BARE_NUMBER = re.compile(r"\b\d+(?:[.,]\d+)?\b")


def emphasis_spans(phrase: str, language: Any = None) -> list[tuple[int, int]]:
    """Character ranges in ``phrase`` worth marking, longest first, no overlap."""

    from .languages import resolve_language

    resolved = resolve_language(language)
    vocabulary = _EMPHASIS_EN if resolved.is_english else _EMPHASIS_ES
    lowered = phrase.lower()

    spans: list[tuple[int, int]] = []
    for term in sorted(vocabulary, key=len, reverse=True):
        start = lowered.find(term)
        if start >= 0:
            spans.append((start, start + len(term)))
    for pattern in (_MEASUREMENT, _BARE_NUMBER):
        for match in pattern.finditer(phrase):
            spans.append((match.start(), match.end()))

    spans.sort(key=lambda s: (s[0], -(s[1] - s[0])))
    merged: list[tuple[int, int]] = []
    for start, end in spans:
        if merged and start < merged[-1][1]:
            continue
        merged.append((start, end))
    # Two highlights in one short caption is already busy.
    return merged[:2]


def apply_emphasis(phrase: str, style: SubtitleStyle, language: Any = None) -> str:
    """Wrap the emphasised spans in an ASS colour override."""

    if not style.emphasis:
        return phrase
    spans = emphasis_spans(phrase, language)
    if not spans:
        return phrase
    out: list[str] = []
    cursor = 0
    for start, end in spans:
        out.append(phrase[cursor:start])
        out.append(f"{{\\c{style.accent}}}{phrase[start:end]}{{\\c{style.primary}}}")
        cursor = end
    out.append(phrase[cursor:])
    return "".join(out)


# ---------------------------------------------------------------------------
# Events and the file itself
# ---------------------------------------------------------------------------

@dataclass
class AssEvent:
    start: float
    end: float
    text: str
    lines: int = 1

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


def format_ass_time(seconds: float) -> str:
    """ASS wants ``H:MM:SS.cc`` with exactly two centisecond digits."""

    seconds = max(0.0, float(seconds))
    hours, remainder = divmod(int(seconds), 3600)
    minutes, secs = divmod(remainder, 60)
    centiseconds = int(round((seconds - int(seconds)) * 100))
    if centiseconds >= 100:            # 1.999 rounds to 200 without this
        centiseconds, secs = 0, secs + 1
        if secs >= 60:
            secs, minutes = 0, minutes + 1
    return f"{hours:d}:{minutes:02d}:{secs:02d}.{centiseconds:02d}"


def _wrap_two_lines(phrase: str, max_line_chars: int = 34) -> tuple[str, int]:
    """At most two lines, balanced, broken between words."""

    words = phrase.split()
    if not words:
        return "", 0
    if len(phrase) <= max_line_chars:
        return phrase, 1
    # Balance rather than fill: two lines of similar length read faster than a
    # full line above a stub.
    best, best_cost = len(words) // 2, None
    for split_at in range(1, len(words)):
        first = " ".join(words[:split_at])
        second = " ".join(words[split_at:])
        if len(first) > max_line_chars or len(second) > max_line_chars:
            continue
        cost = abs(len(first) - len(second))
        if best_cost is None or cost < best_cost:
            best, best_cost = split_at, cost
    first = " ".join(words[:best])
    second = " ".join(words[best:])
    return f"{first}\\N{second}", 2


def events_from_chunks(
    chunks: Sequence[object],
    style: SubtitleStyle = PREMIUM,
    language: Any = None,
    max_line_chars: int = 34,
) -> list[AssEvent]:
    """Turn the TTS timeline into caption events.

    The timing comes from the narration the pipeline already synthesized, so
    there is no transcription step and no drift: each chunk's measured span is
    divided between its phrases in proportion to how long they take to say.
    """

    events: list[AssEvent] = []
    for chunk in chunks:
        text = str(getattr(chunk, "text", "") or "").strip()
        start = float(getattr(chunk, "start", 0.0))
        end = float(getattr(chunk, "end", start))
        if not text or end <= start:
            continue

        phrases = split_phrases(text, language, style.min_words, style.max_words)
        if not phrases:
            continue

        # Characters track speaking time far more closely than word count,
        # because "de" and "sobredimensionado" are not the same amount of
        # speech.
        weights = [max(1, len(p)) for p in phrases]
        total = sum(weights)
        cursor = start
        span = end - start
        for position, (phrase, weight) in enumerate(zip(phrases, weights)):
            slice_end = end if position == len(phrases) - 1 else cursor + span * weight / total
            if slice_end - cursor < MIN_EVENT_SECONDS:
                slice_end = min(cursor + MIN_EVENT_SECONDS, end)
            wrapped, lines = _wrap_two_lines(phrase, max_line_chars)
            events.append(
                AssEvent(
                    start=round(cursor, 3),
                    end=round(min(slice_end, end), 3),
                    text=wrapped,
                    lines=lines,
                )
            )
            cursor = slice_end

    # No overlaps, no captions that outlive their sentence by seconds.
    for previous, current in zip(events, events[1:]):
        if current.start < previous.end:
            current.start = previous.end
        if previous.duration > MAX_EVENT_SECONDS:
            previous.end = previous.start + MAX_EVENT_SECONDS
    for event in events:
        if event.duration < MIN_EVENT_SECONDS:
            event.end = event.start + MIN_EVENT_SECONDS
    return events


ASS_HEADER = """[Script Info]
; Generated by vidfactory - premium burned-in captions, no paid software.
ScriptType: v4.00+
WrapStyle: 2
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709
PlayResX: {width}
PlayResY: {height}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
{styles}

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def render_ass(
    events: Sequence[AssEvent],
    style: SubtitleStyle = PREMIUM,
    language: Any = None,
    width: int = 1920,
    height: int = 1080,
    font: str = "",
) -> str:
    """The complete .ass document as text."""

    font = font or available_font()
    lines = [
        ASS_HEADER.format(width=width, height=height, styles=style.to_ass(font))
    ]
    fade = ""
    if style.fade_in_ms or style.fade_out_ms:
        fade = f"{{\\fad({int(style.fade_in_ms)},{int(style.fade_out_ms)})}}"
    for event in events:
        body = apply_emphasis(event.text, style, language)
        lines.append(
            f"Dialogue: 0,{format_ass_time(event.start)},{format_ass_time(event.end)},"
            f"{style.name},,0,0,0,,{fade}{body}"
        )
    return "\n".join(lines) + "\n"


def write_ass(
    chunks: Sequence[object],
    destination: str | Path,
    style: SubtitleStyle | str = PREMIUM,
    language: Any = None,
    width: int = 1920,
    height: int = 1080,
    font: str = "",
) -> tuple[Path, list[AssEvent], str]:
    """Write ``subtitles.ass`` and report what went into it."""

    resolved = style_for(style) if isinstance(style, str) else style
    chosen_font = font or available_font()
    events = events_from_chunks(chunks, resolved, language)
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        render_ass(events, resolved, language, width, height, chosen_font),
        encoding="utf-8",
    )
    log.info(
        "%d styled caption events written to %s (%s style, %s, %.1f words each)",
        len(events), target.name, resolved.name, chosen_font,
        (sum(len(e.text.replace("\\N", " ").split()) for e in events) / len(events))
        if events else 0.0,
    )
    return target, events, chosen_font


def report(events: Sequence[AssEvent], style: SubtitleStyle, height: int = 1080) -> dict[str, Any]:
    """The numbers quality control asks for."""

    words = [len(e.text.replace("\\N", " ").split()) for e in events]
    durations = [e.duration for e in events]
    overlaps = sum(
        1 for a, b in zip(events, events[1:]) if b.start < a.end - 1e-6
    )
    flashes = sum(1 for d in durations if d < MIN_EVENT_SECONDS - 1e-6)
    return {
        "subtitle_event_count": len(events),
        "average_subtitle_words": round(sum(words) / len(words), 2) if words else 0.0,
        "max_subtitle_words": max(words) if words else 0,
        "max_subtitle_lines": max((e.lines for e in events), default=0),
        # The bottom margin is measured in the same 1080 frame the video is
        # rendered in, so "inside the safe area" is a fact rather than a hope.
        "subtitle_bottom_margin_px": style.margin_v,
        "subtitle_safe_area_passed": (
            style.margin_v >= int(height * 0.06)
            and max((e.lines for e in events), default=0) <= 2
        ),
        "subtitle_timing_passed": overlaps == 0 and flashes == 0,
        "subtitle_overlap_count": overlaps,
        "subtitle_flash_count": flashes,
        "average_subtitle_seconds": round(sum(durations) / len(durations), 2) if durations else 0.0,
    }
