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

    @property
    def passed(self) -> bool:
        return self.score >= PASS_THRESHOLD

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
) -> str | None:
    """Add the missing causal explanation, or ``None`` if there is none to add.

    The sentence comes from the mechanism the idea already relies on, so the
    repair explains *this* idea rather than bolting a generic claim onto it.
    """

    candidates: list[Mechanism] = rank_mechanisms(promise, str(text or ""))
    if tip:
        from .title_alignment import _tip_text

        for family in rank_mechanisms(promise, _tip_text(tip)):
            if family not in candidates:
                candidates.append(family)
    counters = used if used is not None else {}
    for family in candidates:
        options = family.explanations
        if not options:
            continue
        start = counters.get(family.name, 0)
        for offset in range(len(options)):
            sentence = options[(start + offset) % len(options)]
            repaired = f"{str(text).rstrip()} {sentence}".strip()
            if score_paragraph(repaired, promise).score >= PASS_THRESHOLD:
                counters[family.name] = start + offset + 1
                return repaired
    return None


@dataclass
class CausalReport:
    """Per-section causal alignment for the editorial quality report."""

    promise_key: str = "general"
    results: list[CausalResult] = field(default_factory=list)
    rewrites: int = 0
    replacements: int = 0

    @property
    def overall(self) -> float:
        if not self.results:
            return 1.0
        return round(sum(r.score for r in self.results) / len(self.results), 3)

    @property
    def failures(self) -> list[CausalResult]:
        return [r for r in self.results if not r.passed]

    def to_dict(self) -> dict[str, Any]:
        return {
            "promise": self.promise_key,
            "causal_promise_alignment_score": self.overall,
            "sections_passed": sum(1 for r in self.results if r.passed),
            "sections_total": len(self.results),
            "rewrites": self.rewrites,
            "replacements": self.replacements,
            "sections": [r.to_dict() for r in self.results],
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
    for section in sections:
        if getattr(section, "kind", "item") != "item":
            continue
        result = score_paragraph(section.text, promise)
        result.index = int(getattr(section, "index", 0))
        result.heading = str(getattr(section, "heading", ""))

        if rewrite and not result.passed:
            repaired = repair_text(
                section.text, promise, getattr(section, "tip", None), used=counters
            )
            if repaired:
                section.text = repaired
                result = score_paragraph(repaired, promise)
                result.index = int(getattr(section, "index", 0))
                result.heading = str(getattr(section, "heading", ""))
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
        report.results.append(result)
    return report
