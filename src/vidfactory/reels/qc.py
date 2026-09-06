"""What has to be true before a reel is rendered, and before it is published.

The long-form editorial report grades an edit; this grades a script, and the
questions are different because the failure modes are. A reel cannot repeat
its footage for ten minutes - it is forty seconds long - but it can open with
a promise it does not keep, spend twenty of those seconds saying nothing, or
state something about glucose that is not true.

Seven metrics, all of them named in the brief:

``hook_strength_score``      how the chosen opening scored, out of every candidate
``hook_content_alignment``   whether the opening is about what follows it
``medical_claim_risk_count`` forbidden, alarmist or unhedged statements
``unsupported_claim_count``  factual sentences with no source behind them
``value_density_score``      how much of the runtime is actually content
``cta_present``              the reel ends by asking for the follow
``cta_position_ok``          it does so in the last few seconds, not the middle

In production the two safety counts must be zero. That is not a threshold to
be tuned later; it is the reason the safety module exists.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from .safety import find_risks, find_unsupported, mentions_caveat, summarise
from .script import ReelScript

#: A reel is mostly value or it is filler. Measured as the share of spoken
#: words that carry the content, where the hook, the promise and the
#: conclusion count as content too - they are doing real work - and only the
#: retention lines, the format lead and the CTA do not.
VALUE_DENSITY_FLOOR = 0.78

#: How long before the end the CTA may start.
CTA_TAIL_SECONDS = 8.0

#: The duration bands the brief allows, as a tolerance around the request.
DURATION_TOLERANCE = 0.18


def _fold(text: str) -> str:
    flat = unicodedata.normalize("NFKD", str(text or "").lower())
    flat = "".join(c for c in flat if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9 ]+", " ", flat)


@dataclass
class ReelCheck:
    name: str
    passed: bool
    detail: str = ""
    severity: str = "error"          # error | warning

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "passed": self.passed,
            "detail": self.detail,
            "severity": self.severity,
        }


@dataclass
class ReelReport:
    metrics: dict[str, Any] = field(default_factory=dict)
    checks: list[ReelCheck] = field(default_factory=list)

    @property
    def failures(self) -> list[ReelCheck]:
        return [c for c in self.checks if not c.passed and c.severity == "error"]

    @property
    def warnings(self) -> list[ReelCheck]:
        return [c for c in self.checks if not c.passed and c.severity == "warning"]

    @property
    def passed(self) -> bool:
        return not self.failures

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            **self.metrics,
            "checks": [c.to_dict() for c in self.checks],
        }

    def save(self, destination: str | Path) -> Path:
        import json

        target = Path(destination)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return target


def value_density(script: ReelScript) -> float:
    """The share of spoken words doing editorial work.

    The retention lines and the format lead are the honest overhead of the
    shape - useful, but they are not why anyone watched. The CTA is the point
    of the account and still is not content. Everything else has to earn its
    place, which is what "evitar relleno" means as a number.
    """

    total = script.word_count
    if not total:
        return 0.0
    overhead = sum(
        b.word_count for b in script.beats if b.kind in ("retention", "lead", "cta")
    )
    return round((total - overhead) / total, 3)


def repeated_lines(script: ReelScript) -> list[str]:
    """Sentences the reel says twice.

    Forty seconds is not long enough to repeat anything, and the retention
    lines are the one place a template could quietly do it.
    """

    seen: dict[str, int] = {}
    for beat in script.beats:
        key = _fold(beat.text).strip()
        if key:
            seen[key] = seen.get(key, 0) + 1
    return [k for k, n in seen.items() if n > 1]


def explains_something(text: str) -> bool:
    """Does this line say anything concrete, or just approve of a food?

    "Las fresas son muy buenas" passes no test worth having. A line earns its
    place by naming a mechanism, a comparison, a quantity or a condition -
    which is exactly the difference the brief draws between its two examples.
    """

    flat = _fold(text)
    concrete = (
        "fibra", "carbohidrat", "azucar", "proteina", "grasa", "racion",
        "porcion", "cantidad", "menos", "mas ", "mayor", "menor", "que otras",
        "por que", "porque", "asi que", "suele", "suelen", "puede", "pueden",
        "entera", "concentr", "absorb", "digest", "etiqueta", "gramos",
        "combina", "acompan", "lento", "lenta", "rapid", "sacia",
        # Label reading is concrete advice even when it names no nutrient:
        # "que ponga integral en el envase no siempre significa que la harina
        # lo sea" tells the viewer exactly what to do in the aisle.
        "integral", "harina", "envase", "ingredient", "no siempre",
        "no todas", "no todos", "en vez de", "mejor que", "medir", "pesar",
    )
    return any(word in flat for word in concrete)


def build_report(
    script: ReelScript,
    *,
    production: bool = False,
    actual_seconds: float = 0.0,
    cta_start: float = 0.0,
    audio_seconds: float = 0.0,
    visual: Mapping[str, Any] | None = None,
    captions: Mapping[str, Any] | None = None,
    sources: Sequence[Mapping[str, Any]] = (),
) -> ReelReport:
    """Grade one reel."""

    narration = script.narration
    risks = find_risks(narration)
    unsupported = find_unsupported(script.claims())
    density = value_density(script)
    duplicates = repeated_lines(script)
    thin = [b.text for b in script.item_beats if not explains_something(b.text)]

    cta = script.cta
    cta_present = bool(cta) and script.beats[-1].kind == "cta"
    reference = audio_seconds or actual_seconds or script.estimated_seconds
    cta_position_ok = bool(
        cta_present
        and reference > 0
        and (reference - cta_start) <= CTA_TAIL_SECONDS
    )

    target = float(script.target_seconds or 0.0)
    measured = float(actual_seconds or script.estimated_seconds)
    duration_ok = bool(
        target <= 0 or abs(measured - target) <= target * DURATION_TOLERANCE
    )

    visual = dict(visual or {})
    captions = dict(captions or {})

    metrics: dict[str, Any] = {
        "mode": "production" if production else "test",
        "slug": script.topic.slug,
        "title": script.title,
        "format": script.format,
        "top_title": script.top_title,
        "language": "es-ES",
        # ---- the seven the brief names ----------------------------------
        "hook_strength_score": round(script.hook.strength, 3),
        "hook_content_alignment": round(script.hook.alignment, 3),
        "value_density_score": density,
        "cta_present": cta_present,
        "cta_position_ok": cta_position_ok,
        **summarise(risks, unsupported),
        # ---- the rest of the picture -------------------------------------
        "hook": script.hook.hook,
        "hook_candidate_count": len(script.hook.candidates),
        "hook_rejected_count": len(script.hook.rejected),
        "cta": cta,
        "cta_start_seconds": round(cta_start, 2),
        "target_seconds": target,
        "estimated_seconds": script.estimated_seconds,
        "actual_seconds": round(measured, 2),
        "duration_ok": duration_ok,
        "word_count": script.word_count,
        "item_count": len(script.item_beats),
        "beat_count": len(script.beats),
        "dropped_items": list(script.dropped_items),
        "repeated_line_count": len(duplicates),
        "thin_item_count": len(thin),
        "thin_items": thin[:5],
        "mentions_caveat": mentions_caveat(narration),
        "source_count": len(sources),
        "sources": list(sources),
        **{f"visual_{k}": v for k, v in visual.items()},
        **{f"caption_{k}" if not k.startswith("caption") else k: v
           for k, v in captions.items()},
    }

    checks = [
        ReelCheck(
            "no_medical_claim_risk",
            not risks,
            (
                f"{len(risks)} risky statement(s): "
                + "; ".join(f"{r.code} - {r.sentence[:60]}" for r in risks[:3])
                if risks else "no forbidden, alarmist or unhedged claims"
            ),
            severity="error",
        ),
        ReelCheck(
            "every_claim_has_a_source",
            not unsupported,
            (
                f"{len(unsupported)} claim(s) with nothing behind them: "
                + "; ".join(u.sentence[:60] for u in unsupported[:3])
                if unsupported else
                f"all {len(script.claims())} claims carry a source"
            ),
            severity="error",
        ),
        ReelCheck(
            "hook_is_strong_enough",
            script.hook.strength >= _hook_pass(),
            (
                f"the chosen hook scored {script.hook.strength:.2f} of "
                f"{len(script.hook.candidates)} candidates "
                f"({len(script.hook.rejected)} rejected outright)"
            ),
            severity="error" if production else "warning",
        ),
        ReelCheck(
            "hook_matches_the_content",
            script.hook.alignment >= 0.5,
            (
                f"hook/content alignment {script.hook.alignment:.2f}; a hook "
                "that promises something the reel does not deliver is the one "
                "failure a strong opening makes more likely, not less"
            ),
            severity="error",
        ),
        ReelCheck(
            "cta_present",
            cta_present,
            f"ends on {cta!r}" if cta_present else "the reel never asks for the follow",
            severity="error",
        ),
        ReelCheck(
            "cta_in_the_last_seconds",
            cta_position_ok,
            (
                f"the CTA starts at {cta_start:.1f}s of {reference:.1f}s"
                if cta_present else "no CTA to place"
            ),
            severity="error",
        ),
        ReelCheck(
            "value_density",
            density >= VALUE_DENSITY_FLOOR,
            (
                f"{density:.0%} of the words are content "
                f"(floor {VALUE_DENSITY_FLOOR:.0%})"
            ),
            severity="warning",
        ),
        ReelCheck(
            "every_item_says_something_concrete",
            not thin,
            (
                f"{len(thin)} item(s) approve of a food without explaining "
                f"anything: {thin[0][:70]!r}" if thin
                else f"all {len(script.item_beats)} items name a mechanism, a "
                     "comparison or a quantity"
            ),
            severity="error",
        ),
        ReelCheck(
            "no_repeated_lines",
            not duplicates,
            f"{len(duplicates)} line(s) said twice" if duplicates
            else "nothing is repeated",
            severity="error",
        ),
        ReelCheck(
            "duration_within_tolerance",
            duration_ok,
            (
                f"{measured:.1f}s against a {target:.0f}s request "
                f"(tolerance {DURATION_TOLERANCE:.0%})"
            ),
            severity="warning",
        ),
        ReelCheck(
            "mentions_the_caveat",
            mentions_caveat(narration),
            (
                "the reel mentions quantity, preparation, combination or "
                "individual variation" if mentions_caveat(narration)
                else "no caveat anywhere: almost every statement in this niche "
                     "needs one to stay correct"
            ),
            severity="warning",
        ),
        ReelCheck(
            "sources_recorded",
            bool(sources),
            f"{len(sources)} source(s) kept in the metadata" if sources
            else "no sources recorded",
            severity="error",
        ),
    ]

    if captions:
        checks.append(
            ReelCheck(
                "captions_clear_the_platform_ui",
                bool(captions.get("caption_clears_platform_ui"))
                and bool(captions.get("title_clears_status_bar"))
                and bool(captions.get("title_and_captions_do_not_overlap")),
                (
                    f"captions {captions.get('caption_baseline_from_bottom')}px "
                    f"from the bottom, title "
                    f"{captions.get('title_from_top')}px from the top"
                ),
                severity="error",
            )
        )
        checks.append(
            ReelCheck(
                "caption_blocks_are_short",
                int(captions.get("caption_max_lines", 0) or 0) <= 2,
                f"at most {captions.get('caption_max_lines')} lines per caption",
                severity="error",
            )
        )

    return ReelReport(metrics=metrics, checks=checks)


def _hook_pass() -> float:
    from .hooks import HOOK_PASS

    return HOOK_PASS
