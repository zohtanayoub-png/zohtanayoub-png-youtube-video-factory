"""Second-stage promise validation - on the paragraph, not the idea.

:mod:`vidfactory.title_alignment` decides whether an *idea* can deliver what
the title promised. That is necessary and it is not sufficient. Run 6 chose
three ideas that all passed it:

1. Do not center the ceiling light by default
2. Paint the trim the same color as the walls
3. Measure the room before you buy anything

Only the second one *said*, in the narration the viewer actually hears, why it
makes a room look bigger. The first is a valid space trick and the script
talked about symmetry. The third is a valid space trick and the script talked
about the cost of returns. A viewer who came for "look bigger" got two ideas
that never connected the action to the outcome.

So this module reads the finished paragraph and looks for the causal chain:

    action  ->  because / so / which means  ->  promised outcome

"Measure before buying furniture because returns are expensive" fails: the
outcome is about money, not about perceived space. "Measure before buying
furniture because oversized pieces consume visible floor area, narrow the
pathways and make a small room feel cramped" passes, because the sentence
carries the mechanism, the connective and the outcome together.

A paragraph that fails is repaired first - every mechanism in
:mod:`vidfactory.title_alignment` carries a ``because`` sentence stating its
causal chain - and only replaced if repair is impossible.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Sequence

from .concepts import (
    Contamination,
    explanation_fits,
    find_contamination,
)
from .contradiction import (
    AdviceDirection,
    Contradiction,
    ContradictionReport,
    find_contradictions,
    read_direction,
)
from .logging_utils import get_logger
from .title_alignment import (
    GENERAL,
    Mechanism,
    Promise,
    mechanisms_for,
    rank_mechanisms,
)

log = get_logger("CAUSAL")

#: A paragraph must reach this to count as explaining itself.
PASS_THRESHOLD = 0.85

#: What the *video* has to average, which is a different question. A section
#: scoring exactly PASS_THRESHOLD passes on its own and cannot be the whole of
#: a video that has to average more than that - and repair never used to touch
#: it, because it had passed. A one item render then sat at 0.85 for ever
#: against a 0.90 gate it could not reach.
#:
#: Keep this equal to editorial.min_causal_promise_alignment in config.yaml.
#: They are the same requirement seen from the two ends: this one decides how
#: hard the writing tries, that one decides whether the result ships.
TARGET_AVERAGE = 0.90

#: Words that link an action to its consequence. Contrastive connectives
#: ("instead of", "rather than") are deliberately absent: they signal a
#: comparison, not a cause.
CAUSAL_CONNECTIVES: tuple[str, ...] = (
    "because", " so ", "so that", "which means", "which makes", "which is why",
    "that makes", "that is why", "as a result", "the result", "meaning",
    "since ", "leaving", "leaves", "lets ", "letting", "allows", "gives",
    "turns", "reads as", "makes the", "makes a ", "makes your", "makes any",
    "keeps the", "stops the", "and that ", "ends up", "so you", "so your",
)

#: Los mismos enlaces en español. "hace que" es el conector causal central del
#: idioma, así que aparece en varias formas; "en lugar de" y "en vez de" no
#: están, porque comparan en vez de explicar.
CAUSAL_CONNECTIVES_ES: tuple[str, ...] = (
    "porque", " así que ", "de modo que", "de manera que", "de forma que",
    "lo que hace", "hace que", "hacen que", "haciendo que", "por eso",
    "por tanto", "por lo tanto", "de ahí que", "con lo que", "ya que",
    "puesto que", "dado que", "de ese modo", "y eso ", "lo que deja",
    "deja ", "dejando", "permite", "consigue", "logra", "se lee como",
    "se lee más", "se lea como", "se lea más", "se percibe", "y por eso",
    "lo que da", "lo que hacen",
)

#: Conectores por idioma. La clave viene del propio Promise.
CONNECTIVES_BY_LANGUAGE: dict[str, tuple[str, ...]] = {
    "en": CAUSAL_CONNECTIVES,
    "es": CAUSAL_CONNECTIVES_ES,
}


def connectives_for(promise: Promise) -> tuple[str, ...]:
    """The causal vocabulary of the language this promise is written in."""

    return CONNECTIVES_BY_LANGUAGE.get(
        getattr(promise, "language", "en"), CAUSAL_CONNECTIVES
    )

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def outcomes_for(promise: Promise) -> tuple[str, ...]:
    """The phrases that state the outcome a title promised.

    These are the promise's own ``rescue_signals``: the vocabulary that means
    "this text is claiming the promised effect", which is exactly what a
    paragraph has to do to earn its place in the video.
    """

    return tuple(promise.rescue_signals or ())


@dataclass
class CausalResult:
    """Whether one written paragraph explains itself, and why we think so."""

    index: int = 0
    heading: str = ""
    score: float = 0.0
    outcomes: list[str] = field(default_factory=list)
    connectives: list[str] = field(default_factory=list)
    mechanisms: list[str] = field(default_factory=list)
    evidence: str = ""
    repaired: bool = False
    replaced: bool = False
    #: Sentences that argue against this section's own heading.
    contradictions: list[Contradiction] = field(default_factory=list)
    #: Sentences that are about something the section is not.
    contamination: list[Contamination] = field(default_factory=list)
    #: What the heading tells the viewer to do, and to avoid.
    direction: AdviceDirection | None = None

    @property
    def passed(self) -> bool:
        return (
            self.score >= PASS_THRESHOLD
            and not self.contradictions
            and not self.contamination
        )

    def explain(self) -> str:
        outcome = self.outcomes[0] if self.outcomes else ""
        connective = self.connectives[0].strip() if self.connectives else ""
        if not outcome and self.score >= PASS_THRESHOLD:
            # A title that promises no particular outcome cannot fail to
            # deliver one, so there is nothing to quote.
            return self.evidence or "the title makes no causal promise"
        if self.score >= 1.0:
            return (
                f"states the mechanism ({', '.join(self.mechanisms[:2])}) and links "
                f"it to '{outcome}' with '{connective}'"
            )
        if self.score >= PASS_THRESHOLD:
            return f"links the action to '{outcome}' with '{connective}'"
        if self.outcomes and not self.connectives:
            return (
                f"mentions '{self.outcomes[0]}' but never says the action causes it"
            )
        if self.outcomes:
            return f"only loosely connects the action to '{self.outcomes[0]}'"
        return "never states the outcome the title promised"

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "heading": self.heading,
            "causal_promise_alignment_score": round(self.score, 3),
            "passed": self.passed,
            "why": self.explain(),
            "outcomes": self.outcomes[:3],
            "connectives": self.connectives[:3],
            "mechanisms": self.mechanisms[:3],
            "evidence": self.evidence,
            "repaired": self.repaired,
            "replaced": self.replaced,
            "contradiction_count": len(self.contradictions),
            "contradictions": [c.to_dict() for c in self.contradictions],
            "cross_concept_contamination_count": len(self.contamination),
            "cross_concept_contamination": [c.to_dict() for c in self.contamination],
            "direction": self.direction.to_dict() if self.direction else {},
        }


def _hits(text: str, phrases: Sequence[str]) -> list[str]:
    return [p for p in phrases if p.strip() and p in text]


def score_paragraph(text: str, promise: Promise) -> CausalResult:
    """How explicitly a paragraph connects its action to the promised outcome.

    ==========  ==========================================================
    Score       Meaning
    ==========  ==========================================================
    1.00        one sentence carries the mechanism, a causal connective and
                the promised outcome
    0.85        one sentence links the action to the outcome causally
    0.70        the mechanism and the outcome appear together, uncoupled
    0.45        the outcome is mentioned somewhere, never explained
    0.00        the outcome is never claimed at all
    ==========  ==========================================================
    """

    result = CausalResult()
    outcomes = outcomes_for(promise)
    if promise.key == GENERAL.key or not outcomes or not promise.mechanisms:
        # A title that promises nothing specific cannot fail to deliver it.
        result.score = 1.0
        result.evidence = "the title makes no causal promise"
        return result

    connectives = connectives_for(promise)
    # Spanish keeps its accents and its ñ: stripping them would destroy
    # "más", "salón" and "pequeño", which is most of the vocabulary here.
    body = f" {re.sub(r'[^a-z0-9áéíóúüñ ]+', ' ', str(text or '').lower())} "
    sentences = [s for s in _SENTENCE_SPLIT.split(str(text or "")) if s.strip()]

    best = 0.0
    for sentence in sentences:
        padded = f" {re.sub(r'[^a-z0-9áéíóúüñ ]+', ' ', sentence.lower())} "
        found_outcomes = _hits(padded, outcomes)
        if not found_outcomes:
            continue
        found_connectives = _hits(padded, connectives)
        found_mechanisms = [m.name for m in mechanisms_for(promise, padded)]

        if found_connectives and found_mechanisms:
            value = 1.0
        elif found_connectives:
            value = 0.85
        elif found_mechanisms:
            value = 0.70
        else:
            value = 0.45
        if value > best:
            best = value
            result.outcomes = found_outcomes
            result.connectives = found_connectives
            result.mechanisms = found_mechanisms
            result.evidence = sentence.strip()[:180]

    if best == 0.0 and _hits(body, outcomes):
        best = 0.45
        result.outcomes = _hits(body, outcomes)[:3]
    result.score = round(best, 3)
    return result


def repair_text(
    text: str,
    promise: Promise,
    tip: dict[str, Any] | None = None,
    used: dict[str, int] | None = None,
    heading: str = "",
) -> str | None:
    """Add the missing causal explanation, or ``None`` if there is none to add.

    The sentence comes from the mechanism the idea already relies on, so the
    repair explains *this* idea rather than bolting a generic claim onto it.

    ``heading`` is what stops the repair reversing the advice. Mechanism
    explanations have a direction - some describe why the recommended thing
    works, others why the mistake fails - and appending the wrong one is
    exactly how run 16 ended up telling viewers to buy one bigger thing and
    then explaining that bigger things make a room feel cramped. A candidate
    sentence that contradicts the heading is skipped, and the next phrasing of
    the same mechanism is tried instead.
    """

    candidates: list[Mechanism] = rank_mechanisms(promise, str(text or ""))
    if tip:
        from .title_alignment import _tip_text

        for family in rank_mechanisms(promise, _tip_text(tip)):
            if family not in candidates:
                candidates.append(family)
    counters = used if used is not None else {}
    language = getattr(promise, "language", "en")
    direction = read_direction(heading, language=language) if heading else None
    for family in candidates:
        options = family.explanations
        if not options:
            continue
        start = counters.get(family.name, 0)
        for offset in range(len(options)):
            sentence = options[(start + offset) % len(options)]
            repaired = f"{str(text).rstrip()} {sentence}".strip()
            if score_paragraph(repaired, promise).score < PASS_THRESHOLD:
                continue
            if direction and find_contradictions(
                heading, sentence, language=language, direction=direction
            ):
                log.debug(
                    "Skipped the %s explanation for %r: it argues against the heading",
                    family.name, heading,
                )
                continue
            # A mechanism is not a subject. vertical_emphasis is equally true
            # of a curtain rod and a gallery wall, so without this the curtain
            # explanation lands on the art advice - which is what run 22
            # shipped, at a causal score of 1.00.
            if heading and not explanation_fits(heading, sentence, tip):
                log.debug(
                    "Skipped the %s explanation for %r: it is about something "
                    "the section is not", family.name, heading,
                )
                continue
            counters[family.name] = start + offset + 1
            return repaired
    return None


def strip_contradictions(
    text: str, contradictions: Sequence[Contradiction]
) -> str:
    """Remove the sentences that argue against the heading, keeping the rest."""

    offending = {c.sentence.strip() for c in contradictions}
    kept = [
        s.strip()
        for s in _SENTENCE_SPLIT.split(str(text or ""))
        if s.strip() and s.strip() not in offending
    ]
    return " ".join(kept)


@dataclass
class CausalReport:
    """Per-section causal alignment for the editorial quality report."""

    promise_key: str = "general"
    results: list[CausalResult] = field(default_factory=list)
    rewrites: int = 0
    replacements: int = 0
    #: Sections whose paragraph argued against their own heading, and what
    #: was done about it. Production requires this to be empty.
    contradiction: ContradictionReport = field(default_factory=ContradictionReport)
    #: Sentences transplanted from another subject. Production requires none.
    contamination: list[Contamination] = field(default_factory=list)
    contamination_rewrites: int = 0

    @property
    def overall(self) -> float:
        if not self.results:
            return 1.0
        return round(sum(r.score for r in self.results) / len(self.results), 3)

    @property
    def failures(self) -> list[CausalResult]:
        return [r for r in self.results if not r.passed]

    @property
    def contradiction_count(self) -> int:
        return self.contradiction.count

    @property
    def cross_concept_contamination_count(self) -> int:
        return len(self.contamination)

    def to_dict(self) -> dict[str, Any]:
        return {
            "promise": self.promise_key,
            "causal_promise_alignment_score": self.overall,
            "sections_passed": sum(1 for r in self.results if r.passed),
            "sections_total": len(self.results),
            "rewrites": self.rewrites,
            "replacements": self.replacements,
            "sections": [r.to_dict() for r in self.results],
            **self.contradiction.to_dict(),
            "cross_concept_contamination_count": len(self.contamination),
            "cross_concept_contamination": [c.to_dict() for c in self.contamination],
            "contamination_rewrites": self.contamination_rewrites,
        }


def validate_sections(
    sections: Sequence[Any],
    promise: Promise,
    rewrite: bool = True,
    used: dict[str, int] | None = None,
) -> CausalReport:
    """Score every item section, repairing the ones that do not explain themselves.

    ``sections`` are mutated in place when ``rewrite`` is true: an item that
    performs the action without stating the effect gets the effect appended in
    the idea's own terms.
    """

    report = CausalReport(promise_key=promise.key)
    counters = used if used is not None else {}
    language = getattr(promise, "language", "en")

    def rescore(section: Any) -> CausalResult:
        outcome = score_paragraph(section.text, promise)
        outcome.index = int(getattr(section, "index", 0))
        outcome.heading = str(getattr(section, "heading", ""))
        return outcome

    for section in sections:
        if getattr(section, "kind", "item") != "item":
            continue
        heading = str(getattr(section, "heading", ""))
        tip = getattr(section, "tip", None)
        result = rescore(section)

        if rewrite and result.score < PASS_THRESHOLD:
            repaired = repair_text(
                section.text, promise, tip, used=counters, heading=heading
            )
            if repaired:
                section.text = repaired
                result = rescore(section)
                result.repaired = True
                report.rewrites += 1
                log.info(
                    "Rewrote item %s to state why it delivers '%s'",
                    result.index, promise.key,
                )
            else:
                log.warning(
                    "Item %s (%s) does not explain how it delivers '%s' and "
                    "cannot be repaired from its own mechanism",
                    result.index, result.heading, promise.key,
                )

        # ------------------------------------------------------------------
        # Post-write contradiction check. Everything above is about whether
        # the paragraph explains itself; this is about whether the explanation
        # is on the same side as the heading. A paragraph can score 1.00 and
        # still tell the viewer the opposite of what the heading told them,
        # which is what run 16 shipped twice.
        # ------------------------------------------------------------------
        mechanism = result.mechanisms[0] if result.mechanisms else ""
        outcome_word = result.outcomes[0] if result.outcomes else ""
        direction = read_direction(
            heading, mechanism=mechanism, outcome=outcome_word, language=language
        )
        result.direction = direction
        found = find_contradictions(
            heading, section.text, language=language, direction=direction
        )
        if found and rewrite:
            # Drop the offending sentences and try to explain it again, this
            # time with the heading in hand so the repair cannot re-add one.
            trimmed = strip_contradictions(section.text, found)
            candidate = trimmed
            if score_paragraph(trimmed, promise).score < PASS_THRESHOLD:
                candidate = repair_text(
                    trimmed, promise, tip, used=counters, heading=heading
                ) or trimmed
            still = find_contradictions(
                heading, candidate, language=language, direction=direction
            )
            if not still and score_paragraph(candidate, promise).score >= PASS_THRESHOLD:
                section.text = candidate
                result = rescore(section)
                result.direction = direction
                result.repaired = True
                report.contradiction.rewrites += 1
                log.info(
                    "Item %s (%s) contradicted its own heading; rewrote it "
                    "without the offending sentence",
                    result.index, heading,
                )
                found = []
            else:
                found = still or found

        if found:
            for item in found:
                item.index = result.index
            result.contradictions = list(found)
            report.contradiction.items.extend(found)
            log.error(
                "Item %s (%s) contradicts its own advice: %s",
                result.index, heading, found[0].explain(),
            )

        # ------------------------------------------------------------------
        # Cross-concept contamination. A sentence can state the mechanism, use
        # a connective, claim the outcome and argue the right way round, and
        # still be about curtains in a section about pictures - which is what
        # run 22 shipped at a causal score of 1.00. Nothing above can see it,
        # because a mechanism is not a subject.
        # ------------------------------------------------------------------
        intruders = find_contamination(heading, section.text, tip)
        if intruders and rewrite:
            trimmed = " ".join(
                s.strip()
                for s in _SENTENCE_SPLIT.split(str(section.text or ""))
                if s.strip() and s.strip() not in {c.sentence for c in intruders}
            )
            candidate = trimmed
            if score_paragraph(trimmed, promise).score < PASS_THRESHOLD:
                candidate = repair_text(
                    trimmed, promise, tip, used=counters, heading=heading
                ) or trimmed
            if (
                not find_contamination(heading, candidate, tip)
                and score_paragraph(candidate, promise).score >= PASS_THRESHOLD
                and not find_contradictions(
                    heading, candidate, language=language, direction=direction
                )
            ):
                section.text = candidate
                result = rescore(section)
                result.direction = direction
                result.repaired = True
                report.contamination_rewrites += 1
                log.info(
                    "Item %s (%s) explained itself with somebody else's subject; "
                    "rewrote it in its own", result.index, heading,
                )
                intruders = []
            else:
                intruders = find_contamination(heading, section.text, tip)

        if intruders:
            for item in intruders:
                item.index = result.index
            result.contamination = list(intruders)
            report.contamination.extend(intruders)
            log.error(
                "Item %s (%s) is contaminated: %s",
                result.index, heading, intruders[0].explain(),
            )

        report.contradiction.directions.append(direction)
        report.results.append(result)

    # ------------------------------------------------------------------
    # Lift the weakest sections until the video clears the average it is
    # graded on. A section at exactly PASS_THRESHOLD has said the outcome
    # follows from the action but never named the mechanism, and naming it is
    # what takes the same paragraph to 1.00 - so this asks for the sentence
    # the idea already owns rather than settling. Only a strict improvement
    # is kept, and only when it does not contradict the heading, so this can
    # raise the score and can never lower it.
    # ------------------------------------------------------------------
    if rewrite and report.results:
        by_index = {int(getattr(s, "index", 0)): s for s in sections
                    if getattr(s, "kind", "item") == "item"}
        for result in sorted(report.results, key=lambda r: r.score):
            if report.overall >= TARGET_AVERAGE:
                break
            if result.score >= 1.0 or result.contradictions:
                continue
            section = by_index.get(result.index)
            if section is None:
                continue
            improved = repair_text(
                section.text, promise, getattr(section, "tip", None),
                used=counters, heading=result.heading,
            )
            if not improved:
                continue
            candidate = score_paragraph(improved, promise)
            if candidate.score <= result.score:
                continue
            if find_contradictions(
                result.heading, improved, language=language,
                direction=result.direction,
            ):
                continue
            section.text = improved
            log.info(
                "Item %s reached %.2f by naming its mechanism, lifting the "
                "video's causal average to %.2f",
                result.index, candidate.score, report.overall,
            )
            result.score = candidate.score
            result.outcomes = candidate.outcomes
            result.connectives = candidate.connectives
            result.mechanisms = candidate.mechanisms
            result.evidence = candidate.evidence
            result.repaired = True
            report.rewrites += 1
    return report
