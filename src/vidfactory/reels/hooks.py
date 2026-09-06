"""The first two seconds, chosen rather than written once.

A reel lives or dies on its opening line, so this generates a spread of
candidates and picks between them on measured criteria instead of trusting
the first phrasing that came out. Six dimensions, all of them cheap to
compute and none of them a proxy for "sounds punchy":

``curiosity``      does it open a gap - a contrast, an exception, a "but"
``clarity``        can it be understood in one pass, at a readable length
``benefit``        does it say who this is for or what they get
``relevance``      is it about what the reel actually contains
``naturalness``    does it sound like a person, not a channel intro
``honesty``        does it avoid clickbait, fear and unhedged claims

The last one is not a tie-breaker, it is a gate: a hook carrying a medical
risk scores zero and is discarded whatever else it does, because the whole
point of a strong opening is that people act on what follows it.

The banned openers are the ones the brief names. They are refused rather
than penalised - "Hoy vamos a hablar de..." is not a weak hook, it is a
wasted second, and the two seconds it occupies are the only ones guaranteed
to be watched.

A hook also has to stand alone. Someone lands on this video with no context,
mid-scroll, having seen nothing else: if the line only makes sense as the
second sentence of something, it has failed.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Sequence

from .knowledge import Topic
from .safety import find_risks, is_hedged, makes_effect_claim

#: Openings the brief rules out by name, plus the obvious neighbours.
BANNED_OPENERS: tuple[str, ...] = (
    r"^hoy (vamos a|te voy a|os voy a)",
    r"^en (este|el) (video|v[ií]deo|reel)",
    r"^en el (video|v[ií]deo) de hoy",
    r"^hola\b",
    r"^bienvenid",
    r"^buenas\b",
    r"^vamos a hablar",
    r"^te (voy a )?cuento",
    r"^suscr[ií]bete",
    #: "?Sabias que...?" used as a generic opener. Not banned as a construction
    #: - banned as an opening, which is how it is always used.
    r"^\W*sabias que",
    r"^\W*¿sabias que",
)

#: Words that open a gap: an exception, a contrast, a correction.
CURIOSITY: tuple[str, ...] = (
    "no todas", "no todos", "no siempre", "no es", "pero", "aunque",
    "parece", "parecen", "en realidad", "muchas veces", "casi nadie",
    "la mayoria", "antes de", "puede que", "quiza", "sin darte cuenta",
    "lo que casi", "y sin embargo", "no tiene por que", "mas de lo que",
    "no lo son", "no lo es", "se repite", "innecesari", "mas rapido",
    "mejor opcion", "y no es", "de lo que parece", "ni de lejos",
    "cuenta el doble", "no esta descartad",
)

#: Phrases that tell the viewer this is for them, or what they get out of it.
BENEFIT: tuple[str, ...] = (
    "si tienes diabetes", "si tu glucosa", "si te", "si comes", "si sueles",
    "si desayunas", "si compras", "si picas", "si entre horas",
    "para cuidar", "para controlar", "para evitar", "mira esto", "apunta",
    "toma nota", "estas son", "aqui tienes", "te interesa", "te va a interesar",
    "ayudarte", "te ayuda", "presta atencion", "sin renunciar",
    "sin complicarte", "sin tecnicismos", "sencill", "en un minuto",
)

#: Clickbait that promises more than the content can deliver.
CLICKBAIT: tuple[str, ...] = (
    "te va a sorprender", "nadie te lo dice", "los medicos no quieren",
    "el secreto", "truco definitivo", "esto lo cambia todo",
    "no vas a creer", "increible", "impactante", "urgente",
)

#: How the six dimensions are weighted. Honesty is not here because it is a
#: gate rather than a score: a hook that fails it is discarded.
WEIGHTS: dict[str, float] = {
    "curiosity": 0.28,
    "clarity": 0.18,
    "benefit": 0.20,
    "relevance": 0.22,
    "naturalness": 0.12,
}

#: Below this a hook is not good enough to open a reel with.
#:
#: Read off the brief's own eight example hooks rather than chosen. Scored
#: against the fruit topic they land between 0.54 and 0.80, so the floor sits
#: just under the weakest of them: anything the brief would call a good
#: opening passes, and the banned openers do not reach it because they are
#: rejected outright rather than scored. All seventeen topics currently clear
#: it, between 0.56 and 0.80.
HOOK_PASS = 0.52


def _fold(text: str) -> str:
    flat = unicodedata.normalize("NFKD", str(text or "").lower())
    flat = "".join(c for c in flat if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", flat).strip()


def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", _fold(text)))


def _hits(text: str, phrases: Sequence[str]) -> int:
    haystack = " " + _fold(text) + " "
    return sum(1 for p in phrases if _fold(p) in haystack)


def is_banned_opener(text: str) -> bool:
    flat = _fold(text)
    return any(re.search(pattern, flat) for pattern in BANNED_OPENERS)


@dataclass
class HookCandidate:
    """One opening line and everything that was measured about it."""

    text: str
    scores: dict[str, float] = field(default_factory=dict)
    total: float = 0.0
    rejected: bool = False
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "total": round(self.total, 3),
            "scores": {k: round(v, 3) for k, v in sorted(self.scores.items())},
            "rejected": self.rejected,
            "reason": self.reason,
        }


def _clarity(text: str) -> float:
    words = len(text.split())
    if words < 5 or words > 26:
        return 0.15
    # 9 to 18 words is one comfortable breath and fits two caption lines.
    if 9 <= words <= 18:
        base = 1.0
    elif words < 9:
        base = 0.72
    else:
        base = 0.62
    # Stacked subordinate clauses read badly out loud.
    commas = text.count(",")
    return round(max(0.1, base - 0.12 * max(0, commas - 1)), 3)


def _naturalness(text: str) -> float:
    score = 1.0
    if text.isupper():
        score -= 0.6
    if text.count("!") > 1 or "!!" in text:
        score -= 0.4
    if len(re.findall(r"[A-Z]{4,}", text)) > 0:
        score -= 0.2
    if text.count("...") > 1:
        score -= 0.15
    return round(max(0.0, score), 3)


def _content_words(topic: Topic) -> set[str]:
    """Everything the reel says, as a vocabulary.

    The hashtags are in here on purpose: "diabetes" is what this channel is
    about and belongs in the subject vocabulary even when a particular
    topic's title happens not to say the word.
    """

    content = " ".join(
        [topic.title, topic.promise, topic.conclusion, *topic.hashtags]
        + [f"{i.display} {i.claim} {i.why}" for i in topic.items]
    )
    return {w for w in _words(content) if len(w) > 3}


def score_hook(text: str, topic: Topic) -> HookCandidate:
    """Six numbers and a verdict for one candidate."""

    candidate = HookCandidate(text=text.strip())
    if not candidate.text:
        candidate.rejected, candidate.reason = True, "empty"
        return candidate
    if is_banned_opener(candidate.text):
        candidate.rejected, candidate.reason = True, "generic channel opener"
        return candidate

    risks = find_risks(candidate.text)
    if risks:
        candidate.rejected = True
        candidate.reason = f"medical risk: {risks[0].code}"
        return candidate
    if makes_effect_claim(candidate.text) and not is_hedged(candidate.text):
        candidate.rejected = True
        candidate.reason = "states an effect the evidence does not support"
        return candidate
    if _hits(candidate.text, CLICKBAIT):
        candidate.rejected = True
        candidate.reason = "clickbait"
        return candidate

    # Measured against everything the reel actually says, not just its title.
    # A narrow vocabulary made honest, on-subject hooks score zero here
    # simply because the title happened not to repeat their nouns.
    shared = {w for w in _words(candidate.text) if len(w) > 3} & _content_words(topic)

    scores = {
        "curiosity": min(1.0, 0.45 * _hits(candidate.text, CURIOSITY)),
        "clarity": _clarity(candidate.text),
        "benefit": min(1.0, 0.55 * _hits(candidate.text, BENEFIT)),
        "relevance": min(1.0, 0.25 * len(shared)),
        "naturalness": _naturalness(candidate.text),
    }
    candidate.scores = scores
    candidate.total = round(
        sum(scores[k] * w for k, w in WEIGHTS.items()), 3
    )
    return candidate


# ---------------------------------------------------------------------------
# Candidate generation
# ---------------------------------------------------------------------------

#: A small number of openings that stay grammatical whatever they are handed,
#: kept as extra candidates so the choice is never between one option and
#: nothing. The topics carry their own written hooks, which is where the good
#: ones come from: a template that has to fit seventeen subjects produces
#: interchangeable openings, and the opening is the one part of a reel that
#: must not be interchangeable.
TEMPLATES: dict[str, tuple[str, ...]] = {
    "comparison": (
        "{Left_cap} o {right}: parecen lo mismo y no lo son.",
        "Antes de elegir entre {left} y {right}, mira esto.",
    ),
    "myth": (
        "Se repite mucho, y no es exactamente asi.",
        "Lo que suele decirse sobre esto no cuenta toda la historia.",
    ),
    "error_solution": (
        "Aqui es donde mucha gente se equivoca, y tiene arreglo facil.",
    ),
    "list": (
        "Estas son {count} ideas sencillas para el dia a dia.",
    ),
    "ranking": (
        "Un orden orientativo, no una regla: la racion puede cambiarlo entero.",
    ),
    "combination": (
        "Lo que acompana a un alimento cambia bastante el resultado.",
    ),
}


def _capitalise(text: str) -> str:
    text = text.strip()
    return text[:1].upper() + text[1:] if text else text


def generate(topic: Topic) -> list[str]:
    """Between five and ten candidate openings for this topic.

    The topic's own written openings come first and the generic templates
    follow, because a hook written for this subject beats a hook that had to
    fit seventeen of them - which is exactly what the scoring below keeps
    finding.
    """

    left = topic.items[0].display if topic.items else "esta opcion"
    right = topic.items[1].display if len(topic.items) > 1 else "la otra"
    values = {
        "count": str(len(topic.items)),
        "left": left,
        "right": right,
        "Left_cap": _capitalise(left),
    }

    # The topic's own hooks first: they are written for this subject and they
    # are the ones that win. The templates are the floor, not the source.
    out: list[str] = [h for h in topic.hooks]
    for template in TEMPLATES.get(topic.format, TEMPLATES["list"]):
        try:
            out.append(template.format(**values))
        except KeyError:                                  # pragma: no cover
            continue
    # Deduplicate, keep order.
    seen: set[str] = set()
    unique: list[str] = []
    for text in out:
        key = _fold(text)
        if key and key not in seen:
            seen.add(key)
            unique.append(text)
    return unique[:10]


@dataclass
class HookChoice:
    """The chosen opening, and every candidate that lost to it."""

    hook: str
    strength: float
    alignment: float
    candidates: list[HookCandidate] = field(default_factory=list)

    @property
    def rejected(self) -> list[HookCandidate]:
        return [c for c in self.candidates if c.rejected]

    def to_dict(self) -> dict[str, Any]:
        return {
            "hook": self.hook,
            "hook_strength_score": round(self.strength, 3),
            "hook_content_alignment": round(self.alignment, 3),
            "candidates": [c.to_dict() for c in self.candidates],
        }


def alignment(hook: str, topic: Topic) -> float:
    """Does the hook promise what the reel actually delivers?

    A strong hook about fruit on a reel about breakfast cereal is a lie the
    viewer discovers four seconds in, and it is the failure mode that
    "genera varios hooks y escoge el mas fuerte" makes *more* likely rather
    than less, because the strongest-sounding line is often the one that
    drifts furthest from the content.
    """

    hook_words = {w for w in _words(hook) if len(w) > 3}
    if not hook_words:
        return 0.0
    shared = hook_words & _content_words(topic)
    return round(min(1.0, len(shared) / max(3.0, len(hook_words) * 0.5)), 3)


def choose(topic: Topic, extra: Sequence[str] = ()) -> HookChoice:
    """Score every candidate and take the best one that is honest.

    Alignment is applied as a multiplier rather than a seventh weighted
    dimension: a hook that is not about this reel does not get to be
    two-thirds right.
    """

    texts = list(generate(topic)) + [t for t in extra if t]
    candidates = [score_hook(text, topic) for text in texts]
    for candidate in candidates:
        if not candidate.rejected:
            candidate.scores["alignment"] = alignment(candidate.text, topic)
            candidate.total = round(
                candidate.total * (0.78 + 0.22 * candidate.scores["alignment"]), 3
            )
    live = [c for c in candidates if not c.rejected]
    live.sort(key=lambda c: c.total, reverse=True)
    candidates.sort(key=lambda c: (c.rejected, -c.total))
    if not live:
        # Every candidate failed, which is a bug in the templates rather than
        # a reason to ship a bad opening. The topic's own title is at least
        # honest and on-subject.
        fallback = score_hook(_capitalise(topic.title) + ".", topic)
        return HookChoice(
            hook=fallback.text,
            strength=fallback.total,
            alignment=alignment(fallback.text, topic),
            candidates=candidates + [fallback],
        )
    best = live[0]
    return HookChoice(
        hook=best.text,
        strength=best.total,
        alignment=best.scores.get("alignment", 0.0),
        candidates=candidates,
    )
