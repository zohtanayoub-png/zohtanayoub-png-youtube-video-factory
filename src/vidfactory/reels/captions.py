"""Captions and the fixed title, in a 1080x1920 frame.

Two things a vertical reel needs that a landscape video does not.

**Bigger captions, higher up.** Instagram, TikTok and Shorts all draw their
own furniture over the bottom of the frame - caption text, the account row,
the action rail - and the amount varies by app and by whether the post has a
description. Text placed where a 1080p video puts it is simply covered. The
margin below is measured from the bottom of a 1920px frame and leaves the
whole lower fifth alone.

**One fixed title for the entire reel.** Not a per-shot overlay and not a
changing headline: the brief asks for a single strong line at the top that
never moves, so someone arriving three seconds in still knows what they are
watching. It rides in the same .ass file as the captions, which means libass
draws both in one pass - no second filter, no second encode, and no way for
the two to disagree about the frame size.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Sequence

from ..ass_subtitles import (
    AssEvent,
    SubtitleStyle,
    available_font,
    format_ass_time,
    write_ass,
)

#: Vertical output. Every number below is in this frame.
REEL_WIDTH = 1080
REEL_HEIGHT = 1920

#: Characters per caption line. The long-form default of 42 is sized for a
#: 1920px-wide frame; at 1080 with a 76px font it runs off both edges, which
#: is exactly what the first render did.
REEL_LINE_CHARS = 24

#: How much of the bottom of the frame the platforms cover. Measured from the
#: bottom edge: caption text plus the action rail on Reels and TikTok runs to
#: roughly 340px on a 1920 frame, and the safe answer is to clear it with
#: room to spare rather than to fit exactly against it.
BOTTOM_UNSAFE = 340
#: The status bar and the platform's own header at the top.
TOP_UNSAFE = 150

#: Captions. Larger than the long-form style because this is watched on a
#: phone held at arm's length, in fewer words per block because the eye has
#: two seconds per shot rather than five.
REEL_CAPTIONS = SubtitleStyle(
    name="ReelCaption",
    # 68px, not the 76 this started at. A 1080px frame with 60px margins
    # leaves 960px of line, and at 76px the two-line wrap still ran off both
    # edges - visible immediately in the first rendered frame and invisible
    # to every check that only reads the .ass file.
    font_size=68,
    outline=3.4,
    shadow=2.0,
    bold=1,
    margin_v=BOTTOM_UNSAFE + 90,
    margin_h=60,
    spacing=0.2,
    fade_in_ms=90,
    fade_out_ms=90,
    emphasis=True,
    max_words=5,
    min_words=2,
)

#: The fixed title. ExtraBold, top-centred, with a heavier rim than the
#: captions because it sits over whatever the footage happens to be doing for
#: forty seconds rather than for two.
REEL_TITLE = SubtitleStyle(
    name="ReelTitle",
    font_size=82,
    primary="&H00FFFFFF",
    accent="&H0060B4EF",
    outline_colour="&H0A0A0A0A",
    shadow_colour="&H64000000",
    outline=4.2,
    shadow=2.2,
    bold=1,
    margin_v=TOP_UNSAFE + 40,
    margin_h=60,
    spacing=1.2,
    emphasis=False,
)

#: Fonts that actually carry an ExtraBold weight, preferred over the caption
#: font list. Falls back through the same chain as everything else.
TITLE_FONTS: tuple[str, ...] = (
    "Inter ExtraBold", "Inter Bold", "Inter",
    "Montserrat ExtraBold", "Montserrat Bold",
    "DejaVu Sans Bold", "DejaVu Sans",
)


def _title_style(font: str) -> str:
    """The title style line, top-aligned.

    ``to_ass`` hard-codes alignment 2 - bottom centre - because every caption
    in this project sits there. The title is the one thing that does not, so
    its alignment byte is rewritten to 8.
    """

    line = REEL_TITLE.to_ass(font)
    parts = line.split(",")
    # The "Style: " prefix is part of field 0, so the indices below are the
    # field numbers themselves:
    #  0 Name          6 BackColour    12 ScaleY      18 Alignment
    #  1 Fontname      7 Bold          13 Spacing     19 MarginL
    #  2 Fontsize      8 Italic        14 Angle       20 MarginR
    #  3 Primary       9 Underline     15 BorderStyle 21 MarginV
    #  4 Secondary    10 StrikeOut     16 Outline     22 Encoding
    #  5 OutlineColour 11 ScaleX       17 Shadow
    # The first version wrote 8 into field 19, which is MarginL: the title
    # kept alignment 2 and rendered at the *bottom* of the frame, on top of
    # the captions. Caught by looking at the rendered frame, not by any test.
    assert parts[18] == "2", parts
    parts[18] = "8"
    return ",".join(parts)


#: Codepoint ranges libass will not draw with a text font. Inter, Montserrat
#: and DejaVu carry no emoji glyphs, and libass does not fall back to a
#: colour-emoji font the way a browser does - so the first real render put a
#: "missing glyph" box where the strawberry should have been, in the one
#: element that is on screen for the entire reel.
_EMOJI = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF"
    "\U00002190-\U000021FF\U00002B00-\U00002BFF\uFE0F\u200D]"
)


def strip_emoji(text: str) -> str:
    """The title as libass can actually draw it.

    The emoji stays in the topic and in the caption, where the platform
    renders it natively. It is only removed from the burned-in title, because
    a tofu box is worse than no emoji at all.
    """

    return re.sub(r"\s{2,}", " ", _EMOJI.sub("", str(text or ""))).strip()


def accented(title: str, accent: str, style: SubtitleStyle = REEL_TITLE) -> str:
    """The title with one word in the accent colour.

    One word, not a phrase: the point of the accent is that the eye lands
    somewhere first, and colouring half the line defeats it.
    """

    text = strip_emoji(title)
    word = str(accent or "").strip()
    if not word or word.lower() not in text.lower():
        return text
    pattern = re.compile(re.escape(word), re.IGNORECASE)
    match = pattern.search(text)
    if match is None:                                     # pragma: no cover
        return text
    before, hit, after = (
        text[: match.start()], text[match.start():match.end()], text[match.end():]
    )
    return f"{before}{{\\c{style.accent}}}{hit}{{\\c{style.primary}}}{after}"


def title_event(
    title: str, accent: str, duration: float
) -> tuple[float, float, str, str]:
    """One dialogue line covering the whole reel."""

    return (0.0, max(0.5, float(duration)), REEL_TITLE.name,
            accented(title, accent))


def write_reel_ass(
    chunks: Sequence[Any],
    destination: str | Path,
    title: str,
    accent: str,
    duration: float,
    language: Any = None,
) -> tuple[Path, list[AssEvent], str]:
    """Captions plus the fixed title, in one file, at 1080x1920."""

    font = available_font(TITLE_FONTS)
    return write_ass(
        chunks,
        destination,
        style=REEL_CAPTIONS,
        language=language,
        width=REEL_WIDTH,
        height=REEL_HEIGHT,
        font=font,
        extra_styles=(_RawStyle(_title_style(font)),),
        extra_events=(title_event(title, accent, duration),),
        max_line_chars=REEL_LINE_CHARS,
    )


class _RawStyle:
    """A style whose .ass line is already written.

    ``render_ass`` asks each style for ``to_ass(font)``; the title's line has
    had its alignment byte rewritten, so it answers with itself.
    """

    def __init__(self, line: str) -> None:
        self.line = line
        self.name = REEL_TITLE.name

    def to_ass(self, font: str) -> str:                   # noqa: ARG002
        return self.line


def safe_area_report(events: Sequence[AssEvent]) -> dict[str, Any]:
    """What quality control asks about a vertical frame."""

    lines = [len(e.text.split("\\N")) for e in events]
    words = [len(e.text.replace("\\N", " ").split()) for e in events]
    caption_bottom = REEL_HEIGHT - REEL_CAPTIONS.margin_v
    title_top = REEL_TITLE.margin_v
    return {
        "frame": f"{REEL_WIDTH}x{REEL_HEIGHT}",
        "caption_event_count": len(events),
        "caption_max_lines": max(lines, default=0),
        "caption_average_words": round(sum(words) / len(words), 2) if words else 0.0,
        "caption_baseline_from_bottom": REEL_CAPTIONS.margin_v,
        "caption_clears_platform_ui": REEL_CAPTIONS.margin_v > BOTTOM_UNSAFE,
        "title_from_top": REEL_TITLE.margin_v,
        "title_clears_status_bar": REEL_TITLE.margin_v > TOP_UNSAFE,
        "title_and_captions_do_not_overlap": title_top < caption_bottom,
        "caption_font_size": REEL_CAPTIONS.font_size,
        "title_font_size": REEL_TITLE.font_size,
    }


def title_renders(title: str) -> bool:
    """Whether every character of this title has a glyph in a text font."""

    return strip_emoji(title) == str(title or "").strip()
