"""What gets pasted into the post: caption, hashtags, and the disclaimer.

The reel itself stays clean - nobody wants a forty second video that recites
its bibliography - but the post underneath it is where a health account
earns trust, so the sources go there and so does the line that says this is
information rather than medical advice.
"""

from __future__ import annotations

from typing import Any, Sequence

from .script import ReelScript

#: Always present, always last before the hashtags. Not a legal formula: the
#: point is that a person reading this knows where the boundary is.
DISCLAIMER = (
    "Contenido informativo. No sustituye la valoracion de tu equipo sanitario, "
    "que es quien conoce tu caso y tu tratamiento."
)

#: Tags every reel on this account carries, before the topic's own.
BASE_HASHTAGS: tuple[str, ...] = (
    "#diabetes", "#glucosa", "#diabetestipo2", "#alimentacionsaludable",
    "#saludable", "#nutricion",
)

#: Instagram allows thirty; more than a dozen reads as spam and the reach
#: gain is not real.
MAX_HASHTAGS = 12


def hashtags(script: ReelScript) -> list[str]:
    """The topic's own tags first, then the account's, deduplicated."""

    out: list[str] = []
    seen: set[str] = set()
    for tag in [*script.topic.hashtags, *BASE_HASHTAGS]:
        key = tag.lower().strip()
        if key and key not in seen:
            seen.add(key)
            out.append(tag.strip())
    return out[:MAX_HASHTAGS]


def caption(script: ReelScript, sources: Sequence[dict[str, Any]] = ()) -> str:
    """The post text: the hook, the substance, the CTA, the sources.

    The hook is repeated at the top on purpose. It is the line that already
    won a selection process against every other candidate, and it is what
    someone reading the feed with the sound off sees first.
    """

    lines: list[str] = [script.hook.hook, ""]

    bullets = [f"• {b.text}" for b in script.item_beats]
    if bullets:
        lines.extend(bullets)
        lines.append("")

    conclusion = next(
        (b.text for b in script.beats if b.kind == "takeaway"), ""
    )
    if conclusion:
        lines.extend([conclusion, ""])

    lines.extend([script.cta, ""])

    if sources:
        lines.append("Fuentes:")
        for source in sources:
            lines.append(f"• {source.get('org')} - {source.get('title')}: {source.get('url')}")
        lines.append("")

    lines.extend([DISCLAIMER, "", " ".join(hashtags(script))])
    return "\n".join(lines).strip() + "\n"


def publish_metadata(
    script: ReelScript,
    sources: Sequence[dict[str, Any]] = (),
    duration: float = 0.0,
) -> dict[str, Any]:
    """Everything a scheduler or a human needs to post this."""

    return {
        "title": script.title,
        "slug": script.topic.slug,
        "format": script.format,
        "language": "es-ES",
        "aspect_ratio": "9:16",
        "resolution": "1080x1920",
        "duration_seconds": round(float(duration), 2),
        "top_title": script.top_title,
        "top_title_accent": script.accent,
        "hook": script.hook.hook,
        "hook_candidates": [c.to_dict() for c in script.hook.candidates],
        "cta": script.cta,
        "caption": caption(script, sources),
        "hashtags": hashtags(script),
        "disclaimer": DISCLAIMER,
        "sources": list(sources),
        "platforms": ["Instagram Reels", "Facebook Reels", "TikTok", "YouTube Shorts"],
    }
