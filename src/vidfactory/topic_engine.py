"""Autonomous topic generation with duplicate / similarity rejection.

The engine composes titles from a structured grammar (count + qualifier +
subject + promise) rather than from a fixed list, so it can keep producing
fresh, natural-sounding titles indefinitely. Every candidate is compared
against the persistent history and rejected when it is too similar.
"""

from __future__ import annotations

import random
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

from .knowledge import ALL_CATEGORIES, normalize_category, tips_for
from .logging_utils import get_logger

log = get_logger("TOPIC")

_STOPWORDS = {
    "a", "an", "and", "any", "are", "as", "at", "be", "can", "for", "from", "in",
    "into", "is", "it", "make", "makes", "of", "on", "or", "our", "should", "that",
    "the", "their", "them", "these", "they", "this", "to", "too", "up", "we",
    "will", "with", "you", "your", "ideas", "tips", "ways", "things",
}

_NUMBER_WORDS = re.compile(r"^\d+\s+")


def slugify(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii").lower()
    ascii_text = re.sub(r"[^a-z0-9]+", "-", ascii_text).strip("-")
    return re.sub(r"-{2,}", "-", ascii_text)[:96] or "topic"


def _tokens(text: str) -> list[str]:
    text = _NUMBER_WORDS.sub("", text.lower())
    words = re.findall(r"[a-z]+", text)
    return [w for w in words if w not in _STOPWORDS and len(w) > 2]


def _bigrams(tokens: Sequence[str]) -> set[tuple[str, str]]:
    return {(tokens[i], tokens[i + 1]) for i in range(len(tokens) - 1)}


def similarity(a: str, b: str) -> float:
    """Blended token-Jaccard + bigram similarity in the range ``0.0 - 1.0``.

    Word overlap catches "25 Small Living Room Ideas" versus "30 Small Living
    Room Ideas"; bigram overlap catches reordered phrasings of the same topic.
    """

    tokens_a, tokens_b = _tokens(a), _tokens(b)
    if not tokens_a or not tokens_b:
        return 1.0 if a.strip().lower() == b.strip().lower() else 0.0

    set_a, set_b = set(tokens_a), set(tokens_b)
    jaccard = len(set_a & set_b) / len(set_a | set_b)

    big_a, big_b = _bigrams(tokens_a), _bigrams(tokens_b)
    if big_a and big_b:
        bigram = len(big_a & big_b) / len(big_a | big_b)
    else:
        bigram = jaccard

    # Containment protects against "Small Living Room Ideas" vs
    # "Small Living Room Ideas For Renters" scoring low on Jaccard alone.
    containment = len(set_a & set_b) / min(len(set_a), len(set_b))

    return round(0.45 * jaccard + 0.3 * bigram + 0.25 * containment, 4)


def is_too_similar(candidate: str, history: Iterable[str], threshold: float) -> tuple[bool, str, float]:
    """Return ``(rejected, closest_title, score)`` for a candidate title."""

    best_title, best_score = "", 0.0
    for previous in history:
        score = similarity(candidate, previous)
        if score > best_score:
            best_title, best_score = previous, score
    return best_score >= threshold, best_title, best_score


# ---------------------------------------------------------------------------
# Title grammar
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TopicTemplate:
    pattern: str
    angle: str
    counts: tuple[int, ...] = (15, 20, 25, 30)
    #: Which subject kinds this wording reads naturally with.
    kinds: tuple[str, ...] = ("place", "concept")


# A subject is either a PLACE (a room or a home you can walk into) or a
# CONCEPT (a design topic). Templates declare which kinds they read well with,
# which is what stops the generator producing titles like
# "Things Designers Always Notice In A Fall Home Decor".
PLACE, CONCEPT = "place", "concept"

SUBJECTS: dict[str, list[tuple[str, str]]] = {
    "living rooms": [("Living Room", PLACE), ("Modern Living Room", PLACE),
                     ("Cozy Living Room", PLACE), ("Small Living Room", PLACE)],
    "bedrooms": [("Bedroom", PLACE), ("Cozy Bedroom", PLACE), ("Small Bedroom", PLACE),
                 ("Modern Bedroom", PLACE), ("Master Bedroom", PLACE)],
    "kitchens": [("Kitchen", PLACE), ("Small Kitchen", PLACE), ("Modern Kitchen", PLACE),
                 ("Farmhouse Kitchen", PLACE)],
    "bathrooms": [("Bathroom", PLACE), ("Small Bathroom", PLACE), ("Modern Bathroom", PLACE),
                  ("Spa Style Bathroom", PLACE)],
    "small spaces": [("Small Space", PLACE), ("Tiny Home", PLACE), ("Small Apartment", PLACE),
                     ("Studio Apartment", PLACE)],
    "home organization": [("Home Organization", CONCEPT), ("Decluttering", CONCEPT),
                          ("Home Organizing", CONCEPT)],
    "lighting": [("Home Lighting", CONCEPT), ("Living Room Lighting", CONCEPT),
                 ("Bedroom Lighting", CONCEPT), ("Interior Lighting", CONCEPT)],
    "colors": [("Paint Color", CONCEPT), ("Interior Color", CONCEPT), ("Color Palette", CONCEPT)],
    "furniture placement": [("Furniture Placement", CONCEPT), ("Furniture Arrangement", CONCEPT),
                            ("Room Layout", CONCEPT)],
    "storage": [("Smart Storage", CONCEPT), ("Hidden Storage", CONCEPT), ("Home Storage", CONCEPT)],
    "expensive look": [("Home", PLACE), ("House", PLACE), ("Living Space", PLACE)],
    "interior design mistakes": [("Interior Design", CONCEPT), ("Decorating", CONCEPT),
                                 ("Home Decor", CONCEPT)],
    "budget decorating": [("Budget Decorating", CONCEPT), ("Affordable Decor", CONCEPT),
                          ("Cheap Home Upgrade", CONCEPT)],
    "renter-friendly decorating": [("Rental Apartment", PLACE), ("Rental Home", PLACE),
                                   ("Renter Friendly Decor", CONCEPT)],
    "cozy homes": [("Cozy Home", PLACE), ("Cozy Living Room", PLACE), ("Cozy Bedroom", PLACE)],
    "minimalist design": [("Minimalist Home", PLACE), ("Minimalist Living Room", PLACE),
                          ("Minimalist Bedroom", PLACE), ("Minimalist Design", CONCEPT)],
    "scandinavian design": [("Scandinavian Home", PLACE), ("Scandinavian Living Room", PLACE),
                            ("Nordic Interior", CONCEPT)],
    "modern homes": [("Modern Home", PLACE), ("Modern Interior", CONCEPT),
                     ("Contemporary Home", PLACE)],
    "luxury interiors": [("Luxury Home", PLACE), ("Luxury Living Room", PLACE),
                         ("Luxury Bedroom", PLACE)],
    "apartment decorating": [("Apartment", PLACE), ("Small Apartment", PLACE),
                             ("City Apartment", PLACE)],
    "farmhouse design": [("Farmhouse Home", PLACE), ("Modern Farmhouse", PLACE),
                         ("Country Kitchen", PLACE)],
    "mediterranean design": [("Mediterranean Home", PLACE), ("Mediterranean Living Room", PLACE),
                             ("Coastal Interior", CONCEPT)],
    "seasonal decorating": [("Seasonal Decor", CONCEPT), ("Fall Home Decor", CONCEPT),
                            ("Winter Home Decor", CONCEPT)],
    "timeless interiors": [("Timeless Interior", CONCEPT), ("Classic Home", PLACE),
                           ("Timeless Living Room", PLACE)],
    "diy decor": [("DIY Home Decor", CONCEPT), ("DIY Wall Decor", CONCEPT),
                  ("Weekend DIY Home Project", CONCEPT)],
    "design trends": [("Interior Design Trend", CONCEPT), ("Home Decor Trend", CONCEPT),
                      ("Modern Design Trend", CONCEPT)],
}

TEMPLATES: tuple[TopicTemplate, ...] = (
    TopicTemplate("{count} {subject} Ideas That Actually Work", "ideas", kinds=(PLACE, CONCEPT)),
    TopicTemplate("{count} {subject} Ideas For A Beautiful Home", "ideas", kinds=(PLACE, CONCEPT)),
    TopicTemplate("{count} {subject} Ideas You Will Want To Copy", "ideas", kinds=(PLACE, CONCEPT)),
    TopicTemplate("{count} {subject} Mistakes You Should Avoid", "mistakes", kinds=(PLACE, CONCEPT)),
    TopicTemplate("{count} {subject} Mistakes That Make A Space Look Cheap", "mistakes", kinds=(PLACE, CONCEPT)),
    TopicTemplate("{count} {subject} Rules Designers Never Break", "rules", kinds=(PLACE, CONCEPT)),
    TopicTemplate("{count} Budget Friendly {subject} Upgrades", "budget", kinds=(PLACE, CONCEPT)),
    TopicTemplate("{count} {subject} Ideas On A Small Budget", "budget", kinds=(PLACE, CONCEPT)),
    TopicTemplate("{count} Designer Tricks For A Better {subject}", "tricks", kinds=(PLACE,)),
    TopicTemplate("{count} Ways To Make Your {subject} Look More Expensive", "expensive", kinds=(PLACE,)),
    TopicTemplate("{count} Small Changes That Transform Any {subject}", "transform", kinds=(PLACE,)),
    TopicTemplate("{count} {subject} Ideas That Make Any Space Look Bigger", "space", kinds=(PLACE,)),
    TopicTemplate("{count} Cozy {subject} Ideas For A Warmer Home", "cozy", kinds=(PLACE,)),
    TopicTemplate("{count} Timeless {subject} Ideas That Never Go Out Of Style", "timeless", kinds=(PLACE,)),
    TopicTemplate("{count} Clever {subject} Storage Ideas", "storage", kinds=(PLACE,)),
    TopicTemplate("{count} Things Designers Always Notice In A {subject}", "observation", kinds=(PLACE,)),
)

# Templates whose wording only works with a singular subject noun.
_SINGULAR_TEMPLATES = {"expensive", "transform", "tricks", "storage", "observation", "cozy", "timeless"}


@dataclass
class Topic:
    """A concrete video subject ready to be turned into a script."""

    title: str
    category: str
    angle: str = "ideas"
    item_count: int = 25
    slug: str = ""
    source: str = "generated"
    keywords: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.slug:
            self.slug = slugify(self.title)
        if not self.keywords:
            self.keywords = _tokens(self.title)[:10]

    def to_dict(self) -> dict[str, object]:
        return {
            "title": self.title,
            "category": self.category,
            "angle": self.angle,
            "item_count": self.item_count,
            "slug": self.slug,
            "source": self.source,
            "keywords": self.keywords,
        }


class TopicEngine:
    """Generates non-repetitive topics and validates user-supplied ones."""

    def __init__(
        self,
        history: Sequence[str] | None = None,
        similarity_threshold: float = 0.62,
        rng: random.Random | None = None,
        language: Any = None,
    ) -> None:
        from .languages import resolve_language

        self.history = list(history or [])
        self.similarity_threshold = float(similarity_threshold)
        self.rng = rng or random.Random()
        self.language = resolve_language(language)

    # ------------------------------------------------------------------
    def category_usage(self) -> dict[str, int]:
        counts = {name: 0 for name in ALL_CATEGORIES}
        for title in self.history:
            category = normalize_category(title)
            if category:
                counts[category] = counts.get(category, 0) + 1
        return counts

    def available_categories(self) -> list[str]:
        """Categories this language actually has enough writing for."""

        if self.language.is_english:
            return list(ALL_CATEGORIES)
        from .knowledge_es import KNOWLEDGE_ES

        return sorted(KNOWLEDGE_ES)

    def _least_used_categories(self) -> list[str]:
        counts = self.category_usage()
        return sorted(
            self.available_categories(),
            key=lambda name: (counts.get(name, 0), self.rng.random()),
        )

    def _candidate(self, category: str) -> Topic:
        if not self.language.is_english:
            return self._candidate_es(category)
        subject, kind = self.rng.choice(SUBJECTS.get(category, [("Home Decor", CONCEPT)]))
        usable = [t for t in TEMPLATES if kind in t.kinds]
        template = self.rng.choice(usable or list(TEMPLATES))
        if template.angle in _SINGULAR_TEMPLATES and subject.endswith("s"):
            subject = subject[:-1]
        # "Cozy Cozy Living Room" and similar duplications read badly.
        for word in ("Cozy", "Timeless", "Small", "Modern", "Luxury", "Minimalist"):
            if word in template.pattern and subject.startswith(word + " "):
                subject = subject[len(word) + 1 :]
        count = self.rng.choice(template.counts)
        title = template.pattern.format(count=count, subject=subject)
        return Topic(title=title, category=category, angle=template.angle, item_count=count)

    def _candidate_es(self, category: str) -> Topic:
        """Un título en español, con el artículo que pide cada plantilla."""

        subject, kind = self.rng.choice(
            SUBJECTS_ES.get(category, [("la decoración de casa", CONCEPT)])
        )
        usable = [t for t in TEMPLATES_ES if kind in t.kinds]
        template = self.rng.choice(usable or list(TEMPLATES_ES))
        feminine = _es_is_feminine(subject)
        # Every Spanish pattern reads "... para {subject}", so the subject
        # always needs a determiner unless it already carries one.
        subject = _es_with_article(subject)
        pattern = template.pattern
        if feminine:
            pattern = _ES_FEMININE_PATTERNS.get(pattern, pattern)
        count = self.rng.choice(template.counts)
        title = pattern.format(count=count, subject=subject)
        return Topic(title=title, category=category, angle=template.angle, item_count=count)

    # ------------------------------------------------------------------
    def generate(self, category: str | None = None, attempts: int = 400) -> Topic:
        """Produce a topic that is not too similar to anything in the history."""

        preferred = normalize_category(category)
        categories = [preferred] if preferred else self._least_used_categories()
        rejected = 0

        for attempt in range(attempts):
            chosen = categories[attempt % len(categories)] if categories else None
            if chosen is None:
                chosen = self.rng.choice(self.available_categories())
            topic = self._candidate(chosen)
            too_similar, closest, score = is_too_similar(
                topic.title, self.history, self.similarity_threshold
            )
            if too_similar:
                rejected += 1
                log.debug(
                    "Rejected %r (%.2f similar to %r)", topic.title, score, closest
                )
                continue
            available = len(tips_for(topic.category, language=self.language.key))
            if available < 8:
                rejected += 1
                continue
            topic.item_count = min(topic.item_count, available)
            if rejected:
                log.info("Rejected %d near-duplicate candidates before settling", rejected)
            log.info("Selected: %s", topic.title)
            return topic

        # Every template collided: fall back to a guaranteed-unique variation.
        fallback_category = preferred or self.rng.choice(self.available_categories())
        topic = self._candidate(fallback_category)
        suffix = 2
        base_title = topic.title
        while any(similarity(topic.title, t) >= 0.95 for t in self.history):
            topic = Topic(
                title=(
                    f"{base_title} (parte {suffix})"
                    if not self.language.is_english
                    else f"{base_title} (Part {suffix})"
                ),
                category=fallback_category,
                angle=topic.angle,
                item_count=topic.item_count,
            )
            suffix += 1
        log.warning("Falling back to a variation title: %s", topic.title)
        return topic

    # ------------------------------------------------------------------
    def from_user_input(self, raw_title: str, allow_duplicate: bool = True) -> Topic:
        """Turn a manually supplied topic string into a :class:`Topic`."""

        title = " ".join(str(raw_title).split()).strip()
        if not title:
            raise ValueError("Topic text is empty")
        category = normalize_category(title) or "living rooms"
        match = re.match(r"^(\d{1,3})\b", title)
        item_count = int(match.group(1)) if match else 0
        angle = "ideas"
        lowered = title.lower()
        if "mistake" in lowered:
            angle = "mistakes"
        elif "expensive" in lowered:
            angle = "expensive"
        elif "trick" in lowered or "rule" in lowered:
            angle = "tricks"
        elif "storage" in lowered:
            angle = "storage"

        available = len(tips_for(category, language=self.language.key))
        if not item_count:
            item_count = min(25, available)
        item_count = max(5, min(item_count, available))

        too_similar, closest, score = is_too_similar(
            title, self.history, self.similarity_threshold
        )
        if too_similar:
            message = f"Requested topic is {score:.0%} similar to a previous video: {closest!r}"
            if allow_duplicate:
                log.warning("%s - continuing because the topic was requested manually", message)
            else:
                raise ValueError(message)

        topic = Topic(
            title=title,
            category=category,
            angle=angle,
            item_count=item_count,
            source="manual",
        )
        log.info("Selected: %s", topic.title)
        return topic


# ---------------------------------------------------------------------------
# Gramática de títulos en español
#
# No son traducciones de las plantillas inglesas: un título de YouTube en
# español que funciona no dice "5 Ideas de Salón Que Realmente Funcionan",
# dice "5 trucos para que un salón pequeño parezca mucho más grande". Cambia
# la construcción, no solo el idioma.
# ---------------------------------------------------------------------------

SUBJECTS_ES: dict[str, list[tuple[str, str]]] = {
    "living rooms": [("salón", PLACE), ("salón pequeño", PLACE),
                     ("salón moderno", PLACE), ("salón acogedor", PLACE)],
    "bedrooms": [("dormitorio", PLACE), ("dormitorio pequeño", PLACE),
                 ("dormitorio moderno", PLACE)],
    "kitchens": [("cocina", PLACE), ("cocina pequeña", PLACE), ("cocina moderna", PLACE)],
    "small spaces": [("espacio pequeño", PLACE), ("piso pequeño", PLACE),
                     ("estudio", PLACE)],
    "apartment decorating": [("piso", PLACE), ("piso de alquiler", PLACE)],
    "lighting": [("la iluminación de casa", CONCEPT), ("la luz del salón", CONCEPT)],
    "colors": [("el color en casa", CONCEPT), ("la paleta de tu casa", CONCEPT)],
    "storage": [("el almacenaje", CONCEPT), ("el orden en casa", CONCEPT)],
    "furniture placement": [("la distribución de los muebles", CONCEPT)],
    "expensive look": [("tu casa", PLACE), ("tu salón", PLACE)],
    "cozy homes": [("tu casa", PLACE), ("tu salón", PLACE)],
    "interior design mistakes": [("la decoración", CONCEPT), ("tu casa", PLACE)],
}

TEMPLATES_ES: tuple[TopicTemplate, ...] = (
    TopicTemplate("{count} trucos para que {subject} parezca mucho más grande", "space", kinds=(PLACE,)),
    TopicTemplate("{count} ideas para que {subject} parezca más amplio", "space", kinds=(PLACE,)),
    TopicTemplate("{count} ideas para aprovechar mejor {subject}", "space", kinds=(PLACE,)),
    TopicTemplate("{count} formas de ganar espacio en {subject}", "space", kinds=(PLACE,)),
    TopicTemplate("{count} trucos para que {subject} parezca más caro", "expensive", kinds=(PLACE,)),
    TopicTemplate("{count} detalles que hacen que {subject} parezca de lujo", "expensive", kinds=(PLACE,)),
    TopicTemplate("{count} errores de decoración que abaratan {subject}", "mistakes", kinds=(PLACE,)),
    TopicTemplate("{count} errores que casi todo el mundo comete con {subject}", "mistakes", kinds=(PLACE, CONCEPT)),
    TopicTemplate("{count} ideas para {subject} que sí funcionan", "ideas", kinds=(PLACE, CONCEPT)),
    TopicTemplate("{count} ideas para {subject} con poco presupuesto", "budget", kinds=(PLACE, CONCEPT)),
    TopicTemplate("{count} reglas de interiorismo para {subject}", "rules", kinds=(PLACE, CONCEPT)),
    TopicTemplate("{count} ideas para que {subject} se sienta más acogedor", "cozy", kinds=(PLACE,)),
    TopicTemplate("{count} formas de dar más luz a {subject}", "brighter", kinds=(PLACE,)),
    TopicTemplate("{count} ideas de almacenaje para {subject}", "storage", kinds=(PLACE,)),
    TopicTemplate("{count} cosas que un interiorista nota al entrar en {subject}", "observation", kinds=(PLACE,)),
)

#: Concordancia de género. El español no perdona "tu casa parezca más
#: amplio", así que las plantillas con adjetivo variable llevan su forma
#: femenina y se elige según el sujeto.
_ES_FEMININE_PATTERNS: dict[str, str] = {
    "{count} ideas para que {subject} parezca más amplio":
        "{count} ideas para que {subject} parezca más amplia",
    "{count} trucos para que {subject} parezca más caro":
        "{count} trucos para que {subject} parezca más cara",
    "{count} ideas para que {subject} se sienta más acogedor":
        "{count} ideas para que {subject} se sienta más acogedora",
}

#: Sujetos que ya traen su propio determinante.
_ES_HAS_DETERMINER = ("tu ", "la ", "el ", "los ", "las ")
_ES_HAS_DETERMINER_WORDS = {"tu", "la", "el", "los", "las"}

_ES_FEMININE_ENDINGS = ("a", "ción", "sión", "dad")


def _es_is_feminine(subject: str) -> bool:
    """Género del núcleo del sintagma, que es lo que rige la concordancia."""

    head = subject.split(" ")[0]
    if head in _ES_HAS_DETERMINER_WORDS:
        parts = subject.split(" ")
        head = parts[1] if len(parts) > 1 else head
        if head in ("casa", "cocina", "luz"):
            return True
    return head.endswith(_ES_FEMININE_ENDINGS)


def _es_with_article(subject: str) -> str:
    """Añade el artículo indefinido correcto, si el sujeto no trae ya uno."""

    if subject.startswith(_ES_HAS_DETERMINER):
        return subject
    return f"{'una' if _es_is_feminine(subject) else 'un'} {subject}"
