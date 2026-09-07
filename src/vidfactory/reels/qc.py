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

Three more came with the brief's second revision, and they measure the same
complaint from three sides: value that starts too late, items that assert
without explaining, and a reel written about a subject rather than to a
person.

``value_starts_at``          the second the first item begins
``items_with_a_reason``      every item says why, not just what
``second_person_ratio``      how much of the reel speaks to the viewer

And five more once the reel narrated an apple over a picture of an orange:

``entity_grounding_failure_count``   item beats whose footage is the wrong food
``entity_grounding_pass_percentage`` of the beats that required one
``item_grounding_results``           per beat: food, source, score, verdict
``repaired_item_shot_count``         shots the repair pass replaced
``frozen_tail_duration``             seconds of held still frame at the end

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
from .script import HOOK_SECONDS, ReelScript

#: A reel is mostly value or it is filler. Measured as the share of spoken
#: words that carry the content, where the hook, the promise and the
#: conclusion count as content too - they are doing real work - and only the
#: retention lines, the format lead and the CTA do not.
VALUE_DENSITY_FLOOR = 0.78

#: How long before the end the CTA may start.
CTA_TAIL_SECONDS = 8.0

#: The answer has to have started by here.
#:
#: Value starts at the *answer*, not at the first item: "fresas, frambuesas,
#: kiwi, manzana con piel y aguacate" is the reel's point, said in the third
#: second, and a viewer who leaves after it has still been told the thing
#: they came for. So what this gate measures is the one thing that can delay
#: it - the length of the hook.
#:
#: The brief's timeline is hook 0-2s, answer 2-5s. Two seconds is six words
#: at this voice's rate, and the brief's own example hook - "Si tienes
#: diabetes y te preocupa que la fruta te dispare la glucosa, escucha esto" -
#: is fifteen. Both cannot be had, and of the two the hook is the one the
#: brief wrote out in full, so the gate is set at the length that still
#: leaves the shape intact rather than at the number. The builder already
#: prefers the shortest hook among the near-best for this reason.
VALUE_START_SECONDS = 6.5

#: The first item, after the hook and the answer. Not a gate - the answer is
#: already value - but past this the reel is slow and someone should know.
FIRST_ITEM_WARN_SECONDS = 11.0

#: Below this the reel is written about a subject rather than to a person.
#: Measured over the beats that are prose - the answer that lists five fruits
#: by name is not impersonal writing, it is a list.
SECOND_PERSON_FLOOR = 0.45

#: The duration bands the brief allows, as a tolerance around the request.
DURATION_TOLERANCE = 0.18

#: How much held still frame is tolerable at the end of a reel.
#:
#: The CTA is the reason the account exists and it may not play over a frozen
#: image. Two frames of hold while the audio finishes is a rounding error; two
#: seconds is a defect, and the last render had 1.7.
FROZEN_TAIL_LIMIT = 0.2


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


#: Second person, as Spanish actually marks it: the pronouns, the clitics and
#: the verb endings that only appear when someone is being addressed.
_SECOND_PERSON = re.compile(
    r"\b(tu|tus|ti|te|contigo|tuyo|tuya)\b|"
    r"\b\w+(?:as|es)\b(?=\s|$)|"
    r"\b(tienes|puedes|quieres|sabes|notas|comes|tomas|ves|eliges|mira|"
    r"apunta|prueba|revisa|anade|sirvete|pesa|compra|usa|empieza|cambia|"
    r"elige|ten|deja|guarda|lee|comprueba|consultalo|comentalo)\b"
)


def second_person_ratio(script: ReelScript) -> float:
    """The share of spoken lines that address the viewer.

    A sentence at a time rather than a word at a time, because one "te" does
    not make a paragraph second person and the question here is whether the
    reel is talking to somebody.
    """

    lines = [
        sentence
        for beat in script.beats
        for sentence in re.split(r"(?<=[.?!])\s+", beat.text)
        if len(sentence.split()) >= 4
    ]
    if not lines:
        return 0.0
    hits = sum(1 for line in lines if _SECOND_PERSON.search(_fold(line)))
    return round(hits / len(lines), 3)


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
    value_start: float = 0.0,
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

    no_reason = script.items_without_a_reason
    person = second_person_ratio(script)

    # Only measurable once the narration has been synthesized; before that the
    # word budget is the best estimate there is.
    def _spoken_before(kind: str) -> float:
        spoken = 0
        for beat in script.beats:
            if beat.kind == kind:
                break
            spoken += beat.word_count
        return spoken / max(0.5, script.words_per_second)

    value_start = float(value_start or 0.0) or _spoken_before("answer")
    first_item_start = _spoken_before("item")
    value_starts_immediately = value_start <= VALUE_START_SECONDS

    visual = dict(visual or {})
    captions = dict(captions or {})

    # Per-beat food grounding. A correct strawberry clip earlier in the reel
    # does not excuse an orange during the apple beat, so these are counted
    # per beat and never averaged across the reel.
    grounding_rows = list(visual.pop("item_grounding_results", []) or [])
    checked_rows = [r for r in grounding_rows if r.get("checked")]
    failed_rows = [r for r in checked_rows if not r.get("passed")]
    grounding_pass_pct = (
        round(100.0 * (len(checked_rows) - len(failed_rows)) / len(checked_rows), 1)
        if checked_rows else 100.0
    )
    frozen_tail = float(visual.pop("frozen_tail_duration", 0.0) or 0.0)
    repaired_shots = int(visual.pop("repaired_item_shot_count", 0) or 0)
    repair_rounds = int(visual.pop("repair_rounds_used", 0) or 0)

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
        "value_starts_at": round(value_start, 2),
        "value_starts_immediately": value_starts_immediately,
        "first_item_starts_at": round(first_item_start, 2),
        "items_with_a_reason": len(script.item_beats) - len(no_reason),
        "items_without_a_reason": len(no_reason),
        "second_person_ratio": person,
        "entity_grounding_failure_count": len(failed_rows),
        "entity_grounding_pass_percentage": grounding_pass_pct,
        "entity_grounding_checked_count": len(checked_rows),
        "item_grounding_results": grounding_rows,
        "repaired_item_shot_count": repaired_shots,
        "repair_rounds_used": repair_rounds,
        "frozen_tail_duration": round(frozen_tail, 3),
        "cta_present": cta_present,
        "cta_position_ok": cta_position_ok,
        **summarise(risks, unsupported),
        # ---- the rest of the picture -------------------------------------
        "hook": script.hook.hook,
        "hook_candidate_count": len(script.hook.candidates),
        "hook_rejected_count": len(script.hook.rejected),
        "cta": cta,
        "takeaway": script.takeaway,
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
            "every_item_shows_its_food",
            not failed_rows,
            (
                "; ".join(
                    f"{r['item'] or r['beat']} needed {r['required_entity']} and the "
                    f"footage looked like {r['looked_like'] or 'something else'} "
                    f"({r['score']:.2f})"
                    for r in failed_rows[:3]
                ) if failed_rows else
                f"all {len(checked_rows)} item beat(s) that name a food show it"
            ),
            # An error in production, a loud warning in test: the same split
            # the long-form grounding gate uses, and for the same reason -
            # a probe's false positives should not silently refuse a render
            # nobody has looked at yet.
            severity="error" if production else "warning",
        ),
        ReelCheck(
            "the_cta_is_not_a_frozen_frame",
            frozen_tail <= FROZEN_TAIL_LIMIT,
            (
                f"{frozen_tail:.2f}s of held still frame at the end "
                f"(limit {FROZEN_TAIL_LIMIT:.1f}s)"
            ),
            severity="error" if production else "warning",
        ),
        ReelCheck(
            "value_starts_immediately",
            value_starts_immediately,
            (
                f"the answer starts at {value_start:.1f}s "
                f"(limit {VALUE_START_SECONDS:.1f}s), the first item at "
                f"{first_item_start:.1f}s"
            ),
            severity="error",
        ),
        ReelCheck(
            "the_list_is_not_slow",
            first_item_start <= FIRST_ITEM_WARN_SECONDS,
            (
                f"the first item starts at {first_item_start:.1f}s "
                f"(soft limit {FIRST_ITEM_WARN_SECONDS:.0f}s)"
            ),
            severity="warning",
        ),
        ReelCheck(
            "every_item_gives_a_reason",
            not no_reason,
            (
                f"{len(no_reason)} item(s) assert without explaining: "
                f"{no_reason[0][:70]!r}" if no_reason
                else f"all {len(script.item_beats)} items say why"
            ),
            severity="error",
        ),
        ReelCheck(
            "speaks_to_the_viewer",
            person >= SECOND_PERSON_FLOOR,
            (
                f"{person:.0%} of the lines address the viewer "
                f"(floor {SECOND_PERSON_FLOOR:.0%})"
            ),
            severity="warning",
        ),
        ReelCheck(
            "ends_on_a_practical_takeaway",
            bool(script.takeaway),
            f"closes on {script.takeaway[:60]!r}" if script.takeaway
            else "no takeaway before the CTA",
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
