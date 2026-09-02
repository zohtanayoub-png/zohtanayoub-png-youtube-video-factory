"""YouTube metadata generation: title, description, chapters, tags, summary.

Chapters are built from the real narration timeline (the TTS gives exact
per-scene timings), so the timestamps in the description match the video.

SEO here is deliberately restrained: natural US English phrasing, a readable
description, and a modest keyword set. No keyword stuffing.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .ffmpeg_utils import format_chapter
from .logging_utils import get_logger

log = get_logger("META")

YOUTUBE_TITLE_LIMIT = 100
YOUTUBE_DESCRIPTION_LIMIT = 4900          # real limit is 5000; leave headroom
YOUTUBE_TAG_TOTAL_LIMIT = 480             # real limit is 500 characters
MAX_TAGS = 22

BASE_TAGS = (
    "home decor",
    "interior design",
    "home decorating ideas",
    "decorating tips",
    "home design",
)

CATEGORY_TAGS: dict[str, tuple[str, ...]] = {
    "living rooms": ("living room ideas", "living room decor", "living room design"),
    "bedrooms": ("bedroom ideas", "bedroom decor", "bedroom design"),
    "kitchens": ("kitchen ideas", "kitchen decor", "kitchen design"),
    "bathrooms": ("bathroom ideas", "bathroom decor", "small bathroom"),
    "small spaces": ("small space ideas", "small apartment", "small home design"),
    "home organization": ("home organization", "declutter", "organizing ideas"),
    "lighting": ("home lighting", "lighting ideas", "interior lighting"),
    "colors": ("paint colors", "color palette", "interior colors"),
    "furniture placement": ("furniture layout", "furniture arrangement", "room layout"),
    "storage": ("storage ideas", "smart storage", "home storage"),
    "expensive look": ("make home look expensive", "luxury on a budget", "high end look"),
    "interior design mistakes": ("design mistakes", "decorating mistakes", "interior design tips"),
    "budget decorating": ("budget decorating", "affordable decor", "cheap home decor"),
    "renter-friendly decorating": ("renter friendly", "rental decor", "apartment decor"),
    "cozy homes": ("cozy home", "cozy decor", "hygge"),
    "minimalist design": ("minimalist home", "minimalism", "minimalist decor"),
    "scandinavian design": ("scandinavian design", "nordic interior", "scandi decor"),
    "modern homes": ("modern interior", "modern home design", "contemporary decor"),
    "luxury interiors": ("luxury interior", "luxury home", "elegant decor"),
    "apartment decorating": ("apartment decor", "apartment ideas", "small apartment"),
    "farmhouse design": ("farmhouse decor", "modern farmhouse", "country interior"),
    "mediterranean design": ("mediterranean interior", "coastal decor", "warm minimalism"),
    "seasonal decorating": ("seasonal decor", "home refresh", "seasonal styling"),
    "timeless interiors": ("timeless design", "classic interior", "timeless decor"),
    "diy decor": ("diy home decor", "diy projects", "home diy"),
    "design trends": ("interior design trends", "home decor trends", "design 2025"),
}


@dataclass
class Chapter:
    seconds: float
    title: str

    def line(self) -> str:
        return f"{format_chapter(self.seconds)} {self.title}"


@dataclass
class VideoMetadata:
    title: str
    description: str
    tags: list[str] = field(default_factory=list)
    chapters: list[Chapter] = field(default_factory=list)
    summary: str = ""
    filename: str = "final_video.mp4"
    category_id: str = "26"
    privacy_status: str = "private"
    language: str = "en-US"
    duration_seconds: float = 0.0
    made_for_kids: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "description": self.description,
            "tags": list(self.tags),
            "chapters": [{"time": format_chapter(c.seconds), "seconds": round(c.seconds, 2), "title": c.title} for c in self.chapters],
            "summary": self.summary,
            "filename": self.filename,
            "category_id": self.category_id,
            "privacy_status": self.privacy_status,
            "language": self.language,
            "duration_seconds": round(self.duration_seconds, 2),
            "made_for_kids": self.made_for_kids,
        }

    def save(self, destination: str | Path) -> Path:
        target = Path(destination)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        return target


# ---------------------------------------------------------------------------

def safe_filename(title: str, extension: str = ".mp4", max_length: int = 80) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", title).strip("-").lower()
    slug = re.sub(r"-{2,}", "-", slug)[:max_length].strip("-")
    return f"{slug or 'home-decor-video'}{extension}"


def build_chapters(
    script: Any,
    scene_timings: Mapping[str, tuple[float, float]],
    scenes: Sequence[Any],
    min_gap: float = 10.0,
) -> list[Chapter]:
    """Map script sections onto real timestamps from the narration timeline.

    YouTube requires the first chapter to start at 0:00 and needs at least
    three chapters at least ten seconds apart, so short videos legitimately end
    up with fewer than one chapter per idea.
    """

    # The first scene of each section is where that section starts.
    section_starts: dict[tuple[str, int], float] = {}
    for scene in scenes:
        key = (getattr(scene, "section_kind", "item"), int(getattr(scene, "section_index", 0)))
        start = scene_timings.get(getattr(scene, "scene_id", ""), (None, None))[0]
        if start is None:
            continue
        if key not in section_starts or start < section_starts[key]:
            section_starts[key] = start

    chapters: list[Chapter] = []
    for section in getattr(script, "sections", []):
        key = (section.kind, int(section.index))
        start = section_starts.get(key)
        if start is None:
            continue
        title = section.heading.strip()
        if not chapters:
            start = 0.0
        elif start - chapters[-1].seconds < min_gap:
            continue
        chapters.append(Chapter(seconds=max(0.0, start), title=title))

    if chapters:
        chapters[0] = Chapter(seconds=0.0, title=chapters[0].title)
    return chapters


def build_tags(topic: Any, extra: Iterable[str] = ()) -> list[str]:
    """Assemble a modest, relevant tag list that fits YouTube's limits."""

    category = getattr(topic, "category", "")
    candidates: list[str] = []

    def push(value: str) -> None:
        cleaned = re.sub(r"\s+", " ", str(value)).strip().lower()
        if cleaned and cleaned not in candidates and len(cleaned) <= 40:
            candidates.append(cleaned)

    for tag in CATEGORY_TAGS.get(category, ()):
        push(tag)
    for tag in BASE_TAGS:
        push(tag)
    for tag in extra:
        push(tag)

    # Keep the whole set inside YouTube's total character budget.
    selected: list[str] = []
    total = 0
    for tag in candidates[:MAX_TAGS]:
        cost = len(tag) + 1
        if total + cost > YOUTUBE_TAG_TOTAL_LIMIT:
            break
        selected.append(tag)
        total += cost
    return selected


def build_summary(script: Any, limit: int = 320) -> str:
    """A short plain-language summary for metadata.json and social use."""

    items = [s.heading.split(". ", 1)[-1] for s in getattr(script, "items", lambda: [])()]
    lead = f"{len(items)} practical " if len(items) > 1 else "Practical "
    body = "; ".join(items[:3])
    text = (
        f"{lead}home decor ideas covering {body}"
        if body
        else "Practical home decor and interior design ideas."
    )
    if len(text) > limit:
        text = text[: limit - 3].rstrip(" ,;") + "..."
    return text if text.endswith((".", "...")) else text + "."


def build_description(
    script: Any,
    chapters: Sequence[Chapter],
    sources: Sequence[Mapping[str, Any]] = (),
    channel_name: str = "",
) -> str:
    """Compose the YouTube description: hook, chapters, credits, disclosure."""

    items = getattr(script, "items", lambda: [])()
    opening = getattr(script, "sections", [])
    intro_text = opening[0].text if opening else ""
    first_sentences = " ".join(re.split(r"(?<=[.!?])\s+", intro_text)[:2]).strip()

    parts: list[str] = []
    if first_sentences:
        parts.append(first_sentences)
    if items:
        noun = "idea" if len(items) == 1 else "ideas"
        quantity = "one" if len(items) == 1 else str(len(items))
        parts.append(
            f"In this video we go through {quantity} {noun}, with the reasoning "
            "behind each one and how to actually apply it at home."
        )

    if len(chapters) >= 3:
        parts.append("Chapters:\n" + "\n".join(chapter.line() for chapter in chapters))

    if items:
        listed = "\n".join(f"- {section.heading.split('. ', 1)[-1]}" for section in items[:30])
        parts.append("What is covered:\n" + listed)

    providers = sorted({str(s.get("provider", "")) for s in sources if s.get("provider")})
    if providers:
        parts.append(
            "Footage credit: supporting video clips are licensed stock footage from "
            + ", ".join(p.title() for p in providers)
            + ". All narration and editorial content is original."
        )

    if channel_name:
        parts.append(f"{channel_name} - practical home decor and interior design ideas.")

    description = "\n\n".join(part for part in parts if part).strip()
    if len(description) > YOUTUBE_DESCRIPTION_LIMIT:
        description = description[:YOUTUBE_DESCRIPTION_LIMIT].rsplit("\n", 1)[0].rstrip()
    return description


def build_metadata(
    script: Any,
    scenes: Sequence[Any],
    scene_timings: Mapping[str, tuple[float, float]],
    duration_seconds: float,
    sources: Sequence[Mapping[str, Any]] = (),
    channel_name: str = "",
    language: str = "en-US",
    category_id: str = "26",
    privacy_status: str = "private",
    made_for_kids: bool = False,
) -> VideoMetadata:
    """Build the complete metadata bundle for one finished video."""

    title = str(getattr(script, "title", "Home Decor Ideas")).strip()
    if len(title) > YOUTUBE_TITLE_LIMIT:
        title = title[: YOUTUBE_TITLE_LIMIT - 1].rstrip(" ,;:-") + "…"

    chapters = build_chapters(script, scene_timings, scenes)
    metadata = VideoMetadata(
        title=title,
        description=build_description(script, chapters, sources, channel_name),
        tags=build_tags(getattr(script, "topic", None), extra=getattr(getattr(script, "topic", None), "keywords", [])),
        chapters=chapters,
        summary=build_summary(script),
        filename=safe_filename(title),
        category_id=str(category_id),
        privacy_status=str(privacy_status),
        language=str(language),
        duration_seconds=float(duration_seconds),
        made_for_kids=bool(made_for_kids),
    )
    log.info(
        "Metadata ready: %d chapters, %d tags, %d character description",
        len(metadata.chapters),
        len(metadata.tags),
        len(metadata.description),
    )
    return metadata
