"""Where every claim in a reel comes from.

This is health content, so the rule the long-form side applies to footage -
a number in the report has to come from a measurement, not from a plausible
sentence - applies here to the *words*. Every factual statement a reel makes
carries the identifier of at least one reputable source, the reel keeps them
in its metadata, and ``unsupported_claim_count`` is an error rather than a
warning.

Two deliberate choices about what is listed here.

**Organisations and their standing guidance, not deep links into individual
studies.** A URL that has rotted is worse than no URL, and a reel that cites
one 2019 trial for "berries tend to have less carbohydrate per serving" is
citing the wrong kind of thing anyway: that is settled nutritional
composition, not a finding. Every entry below is the top-level nutrition
guidance of a body whose whole job is this, in Spanish where a Spanish
speaker can read it.

**The claims are written to be supportable, not trimmed to fit a source
afterwards.** "Diez frutas que bajan el azucar" cannot be supported by
anything here and is not a phrasing that gets softened later - it never
gets written. See :mod:`vidfactory.reels.safety`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class Source:
    """One organisation's standing guidance."""

    key: str
    org: str
    title: str
    url: str
    language: str = "es"

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "org": self.org,
            "title": self.title,
            "url": self.url,
            "language": self.language,
        }


SOURCES: dict[str, Source] = {
    s.key: s
    for s in (
        Source(
            key="ada_nutrition",
            org="American Diabetes Association",
            title="Food & Nutrition",
            url="https://diabetes.org/food-nutrition",
            language="en",
        ),
        Source(
            key="niddk_diet",
            org="National Institute of Diabetes and Digestive and Kidney Diseases (NIH)",
            title="Diabetes Diet, Eating, & Physical Activity",
            url="https://www.niddk.nih.gov/health-information/diabetes/overview/diet-eating-physical-activity",
            language="en",
        ),
        Source(
            key="who_diet",
            org="Organizacion Mundial de la Salud",
            title="Alimentacion sana",
            url="https://www.who.int/es/news-room/fact-sheets/detail/healthy-diet",
        ),
        Source(
            key="who_diabetes",
            org="Organizacion Mundial de la Salud",
            title="Diabetes",
            url="https://www.who.int/es/news-room/fact-sheets/detail/diabetes",
        ),
        Source(
            key="harvard_carbs",
            org="Harvard T.H. Chan School of Public Health",
            title="Carbohydrates and Blood Sugar",
            url="https://nutritionsource.hsph.harvard.edu/carbohydrates/carbohydrates-and-blood-sugar/",
            language="en",
        ),
        Source(
            key="harvard_fiber",
            org="Harvard T.H. Chan School of Public Health",
            title="Fiber",
            url="https://nutritionsource.hsph.harvard.edu/carbohydrates/fiber/",
            language="en",
        ),
        Source(
            key="fundacion_diabetes",
            org="Fundacion para la Diabetes Novo Nordisk",
            title="Alimentacion y diabetes",
            url="https://www.fundaciondiabetes.org/",
        ),
        Source(
            key="redgdps",
            org="Fundacion redGDPS",
            title="Guia de diabetes tipo 2 para clinicos",
            url="https://www.redgdps.org/",
        ),
        Source(
            key="diabetes_uk_food",
            org="Diabetes UK",
            title="Enjoy Food",
            url="https://www.diabetes.org.uk/guide-to-diabetes/enjoy-food",
            language="en",
        ),
    )
}


def resolve(keys: Iterable[str]) -> list[Source]:
    """The sources these keys name, skipping nothing silently.

    An unknown key raises rather than disappearing: a claim whose source was
    typed wrong is exactly the claim that would otherwise ship unsupported.
    """

    out: list[Source] = []
    for key in keys:
        source = SOURCES.get(str(key))
        if source is None:
            raise KeyError(f"unknown source {key!r}")
        out.append(source)
    return out


def bibliography(keys: Iterable[str]) -> list[dict[str, Any]]:
    """The metadata block a finished reel carries, deduplicated and ordered."""

    seen: set[str] = set()
    ordered: list[str] = []
    for key in keys:
        if key not in seen:
            seen.add(key)
            ordered.append(key)
    return [s.to_dict() for s in resolve(ordered)]
