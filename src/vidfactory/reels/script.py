"""The reel itself: hook, promise, value, retention, conclusion, CTA.

Six beats in a fixed order, because the order is the format. What varies is
how much of each fits, and that is arithmetic rather than taste: a forty
second reel at the rate this voice actually speaks is about a hundred and
thirty words, the fixed beats take roughly fifty of them, and what is left
divides between the items. When the budget is tight the *why* clause goes
first and the claim never does - "las fresas suelen aportar menos
carbohidratos por racion" is the content; "y su fibra puede hacer que la
subida sea mas gradual" is the explanation, and a reel with the explanation
and no claim says nothing.

That is the same rule ``_trim_to_duration`` follows on the long-form side:
optional material first, the substance last, and never the part that makes
the sentence true.

Every beat carries its own visual query, so the picture changes when the
narration does. If the line says "las fresas", the query says strawberries.
This is where the brief's "si dice fresas, quiero ver fresas" is decided -
the shot planner downstream can only pick from what was searched for.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Sequence

from .hooks import HookChoice, choose as choose_hook
from .knowledge import Item, Topic

#: The durations the brief allows, and the default band.
ALLOWED_SECONDS: tuple[int, ...] = (20, 30, 45, 60)
#: The brief's default band is 35-45 seconds and 45 is the value that lands
#: inside it: a five item list at this voice's rate comes out near 44.8s.
DEFAULT_SECONDS = 45

#: The CTA, with the natural variations the brief lists. Never a purchase,
#: never a demand.
CTA_VARIANTS: tuple[str, ...] = (
    "Siguenos para mas consejos sobre diabetes.",
    "Siguenos para aprender mas sobre diabetes y alimentacion.",
    "Si te ha servido, siguenos para mas consejos sobre diabetes.",
    "Siguenos para mas ideas sencillas para cuidar tu glucosa.",
)

#: Small lines that buy attention across a list without promising anything.
#: Used sparingly - two at most - because a retention line that arrives every
#: item stops being a signal and starts being filler, which is the one thing
#: the brief rules out by name.
#: Two lines' worth of words, reserved before the items are chosen.
_RETENTION_ALLOWANCE = 11

RETENTION_LINES: tuple[str, ...] = (
    "Pero atencion con la siguiente.",
    "Y la ultima suele sorprender bastante.",
    "Aqui es donde mucha gente se equivoca.",
    "La cantidad sigue siendo importante.",
)

#: How the value section introduces itself in each format. The spine of the
#: reel changes with the format, not just its wording.
FORMAT_LEADS: dict[str, str] = {
    "list": "",
    "error_solution": "Vamos con el primero.",
    "comparison": "Vamos a compararlas.",
    "ranking": "De menor a mayor impacto aproximado.",
    "myth": "Vamos por partes.",
    "combination": "Estas son las combinaciones.",
}

#: A reel with no items is not a short reel, it is an empty one. Below this
#: the duration request loses to the content.
MIN_ITEMS = 2

#: Words per second, at the rate the Spanish voice actually speaks. Overridden
#: by the measured rate when the database has one, exactly as the long-form
#: script generator does.
DEFAULT_WORDS_PER_SECOND = 2.9


@dataclass
class Beat:
    """One narrated line and the picture that goes with it."""

    kind: str                 # hook | promise | lead | item | retention | conclusion | cta
    text: str
    query: str = ""
    search_text: str = ""
    index: int = 0
    sources: tuple[str, ...] = ()
    item_key: str = ""

    @property
    def word_count(self) -> int:
        return len(self.text.split())

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "text": self.text,
            "query": self.query,
            "search_text": self.search_text,
            "index": self.index,
            "item_key": self.item_key,
            "sources": list(self.sources),
        }


@dataclass
class ReelScript:
    """A finished reel script, ready to be spoken and shot."""

    topic: Topic
    hook: HookChoice
    beats: list[Beat] = field(default_factory=list)
    target_seconds: float = DEFAULT_SECONDS
    words_per_second: float = DEFAULT_WORDS_PER_SECOND
    dropped_items: list[str] = field(default_factory=list)

    @property
    def format(self) -> str:
        return self.topic.format

    @property
    def title(self) -> str:
        return self.topic.title

    @property
    def top_title(self) -> str:
        return self.topic.top_title

    @property
    def accent(self) -> str:
        return self.topic.accent

    @property
    def narration(self) -> str:
        return " ".join(b.text for b in self.beats)

    @property
    def word_count(self) -> int:
        return sum(b.word_count for b in self.beats)

    @property
    def estimated_seconds(self) -> float:
        return round(self.word_count / max(0.5, self.words_per_second), 2)

    @property
    def cta(self) -> str:
        return next((b.text for b in self.beats if b.kind == "cta"), "")

    @property
    def item_beats(self) -> list[Beat]:
        return [b for b in self.beats if b.kind == "item"]

    @property
    def source_keys(self) -> list[str]:
        keys: list[str] = []
        for beat in self.beats:
            keys.extend(beat.sources)
        return keys

    def claims(self) -> list[tuple[str, tuple[str, ...]]]:
        """Every factual sentence and what backs it, for the safety check."""

        return [(b.text, b.sources) for b in self.beats if b.kind == "item"]

    def to_dict(self) -> dict[str, Any]:
        return {
            "slug": self.topic.slug,
            "title": self.title,
            "format": self.format,
            "top_title": self.top_title,
            "accent": self.accent,
            "target_seconds": self.target_seconds,
            "estimated_seconds": self.estimated_seconds,
            "word_count": self.word_count,
            "words_per_second": round(self.words_per_second, 2),
            "hook": self.hook.to_dict(),
            "cta": self.cta,
            "beats": [b.to_dict() for b in self.beats],
            "dropped_items": list(self.dropped_items),
        }


def _stable_index(seed: str, size: int) -> int:
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    return digest[0] % max(1, size)


def cta_for(topic: Topic) -> str:
    """One of the allowed variations, stable for a given topic.

    Stable rather than random so two renders of the same topic do not
    disagree, and varied across topics so a feed of reels does not end with
    the identical sentence every time.
    """

    if "glucosa" in topic.title.lower() and "fruta" not in topic.title.lower():
        return CTA_VARIANTS[3]
    return CTA_VARIANTS[_stable_index(topic.slug, len(CTA_VARIANTS))]


def _shared_run(left: str, right: str) -> int:
    """The longest run of words these two sentences have in common.

    A bag-of-words overlap is the wrong measure here: a hook is *supposed* to
    share its subject with the conclusion - both are about fruit - and
    penalising that would reject every on-topic opening. What must not happen
    is the same clause twice, and a shared run of words is exactly that.
    """

    import re
    import unicodedata

    def words(text: str) -> list[str]:
        flat = unicodedata.normalize("NFKD", str(text or "").lower())
        flat = "".join(c for c in flat if not unicodedata.combining(c))
        return re.findall(r"[a-z0-9]+", flat)

    a, b = words(left), words(right)
    best = 0
    for i in range(len(a)):
        for j in range(len(b)):
            run = 0
            while (
                i + run < len(a) and j + run < len(b) and a[i + run] == b[j + run]
            ):
                run += 1
            best = max(best, run)
    return best


#: At or above this the hook and the conclusion are the same clause twice.
_HOOK_ECHO_WORDS = 5


def _distinct_hook(topic: Topic, extra: Sequence[str] = ()) -> HookChoice:
    """The best hook that is not already the conclusion.

    The fruit topic's strongest candidate was "la fruta no tiene por que
    desaparecer de tu dieta" - which is also, word for word, how that reel
    ends. A reel that opens and closes on the same sentence has spent its
    conclusion in the first two seconds.
    """

    choice = choose_hook(topic, extra=extra)
    if _shared_run(choice.hook, topic.conclusion) < _HOOK_ECHO_WORDS:
        return choice
    for candidate in choice.candidates:
        if candidate.rejected:
            continue
        if _shared_run(candidate.text, topic.conclusion) < _HOOK_ECHO_WORDS:
            return HookChoice(
                hook=candidate.text,
                strength=candidate.total,
                alignment=candidate.scores.get("alignment", 0.0),
                candidates=choice.candidates,
            )
    return choice


def _item_text(item: Item, with_why: bool) -> str:
    claim = item.claim.rstrip(" .")
    if with_why and item.why:
        why = item.why.strip()
        joiner = "" if why.startswith(("y ", "asi ", "pero ", "aunque ")) else ", "
        if joiner:
            return f"{claim}{joiner}{why.rstrip(' .')}."
        return f"{claim} {why.rstrip(' .')}."
    return claim + "."


#: Added to the conclusion when nothing else in the reel says it. Almost
#: every statement in this niche is only correct with one of these attached,
#: so a trimmed script that has lost them all gets one back rather than a
#: warning: the warning tells an operator the reel is weaker, and the viewer
#: is the one who needed the sentence.
CAVEAT_LINE = "Recuerda que la cantidad y la respuesta de cada persona tambien cuentan."


def _ensure_caveat(beats: list[Beat]) -> None:
    from .safety import mentions_caveat

    if mentions_caveat(" ".join(b.text for b in beats)):
        return
    for beat in beats:
        if beat.kind == "conclusion":
            beat.text = beat.text.rstrip() + " " + CAVEAT_LINE
            return


def build(
    topic: Topic,
    target_seconds: float = DEFAULT_SECONDS,
    words_per_second: float = DEFAULT_WORDS_PER_SECOND,
    max_items: int = 0,
    extra_hooks: Sequence[str] = (),
) -> ReelScript:
    """Fit this topic into the requested duration without losing the point.

    The fixed beats are non-negotiable: a reel without a hook has no opening,
    and one without a CTA is the whole reason the account exists. So the
    items absorb the budget - first by losing their explanations, then, only
    if that is still not enough, by being fewer.
    """

    words_per_second = max(1.5, float(words_per_second))
    target_seconds = float(target_seconds or DEFAULT_SECONDS)
    budget_words = target_seconds * words_per_second

    hook = _distinct_hook(topic, extra_hooks)
    cta = cta_for(topic)
    lead = FORMAT_LEADS.get(topic.format, "")

    fixed = [
        Beat("hook", hook.hook, topic.opening_query, topic.opening_search_text),
        Beat("promise", topic.promise.rstrip(" .") + ".",
             topic.opening_query, topic.opening_search_text),
    ]
    tail = [
        Beat("conclusion", topic.conclusion.rstrip(" .") + ".",
             topic.opening_query, topic.opening_search_text),
        Beat("cta", cta, topic.opening_query, topic.opening_search_text),
    ]
    fixed_words = sum(b.word_count for b in (*fixed, *tail))
    if lead:
        fixed_words += len(lead.split())
    # The retention lines are decided later, from the item count, but they are
    # spoken words like any other and the first version of this forgot to
    # budget for them - which is why a 45 second reel came out at 48.6.
    if len(topic.items) >= 4:
        fixed_words += _RETENTION_ALLOWANCE

    items = list(topic.items)
    if max_items > 0:
        items = items[:max_items]
    dropped: list[str] = []
    floor = min(MIN_ITEMS, len(items))

    def words_of(chosen: Sequence[Item], explained: set[str]) -> int:
        return sum(
            len(_item_text(i, i.key in explained).split()) for i in chosen
        )

    # Claims first. Drop whole items only when the bare claims still do not
    # fit, and never below the floor: a twenty second reel with two items is
    # a reel, and one with none is a caption read aloud.
    while (
        len(items) > floor
        and fixed_words + words_of(items, set()) > budget_words * 1.02
    ):
        dropped.append(items[-1].key)
        items = items[:-1]

    # Then spend whatever is left on explanations, item by item, because the
    # brief asks for the "por que" wherever the format allows it. Partial is
    # fine: four explained items and one bare beats five bare ones.
    explained: set[str] = set()
    for item in items:
        candidate = explained | {item.key}
        if fixed_words + words_of(items, candidate) <= budget_words * 1.02:
            explained = candidate

    beats: list[Beat] = list(fixed)
    if lead and items:
        beats.append(
            Beat("lead", lead, topic.opening_query, topic.opening_search_text)
        )

    # Two retention lines at most, and only where they earn their place: one
    # about a third of the way in, one before the last item.
    retention_at: set[int] = set()
    if len(items) >= 4:
        retention_at = {max(1, len(items) // 3), len(items) - 1}

    # Two distinct lines. The first version picked each slot independently and
    # duly said "la cantidad sigue siendo importante" twice in the same reel,
    # which is exactly the filler this is supposed to avoid.
    used_lines: set[str] = set()

    def retention_line(index: int, last: bool) -> str:
        preferred = RETENTION_LINES[1] if last else RETENTION_LINES[
            _stable_index(f"{topic.slug}:{index}", len(RETENTION_LINES))
        ]
        if preferred not in used_lines:
            used_lines.add(preferred)
            return preferred
        for candidate in RETENTION_LINES:
            if candidate not in used_lines:
                used_lines.add(candidate)
                return candidate
        return preferred                                  # pragma: no cover

    for index, item in enumerate(items):
        if index in retention_at:
            line = retention_line(index, index == len(items) - 1)
            beats.append(
                Beat("retention", line, item.query, item.search_text, index=index)
            )
        beats.append(
            Beat(
                kind="item",
                text=_item_text(item, item.key in explained),
                query=item.query,
                search_text=item.search_text,
                index=index,
                sources=item.sources,
                item_key=item.key,
            )
        )

    beats.extend(tail)
    _ensure_caveat(beats)
    return ReelScript(
        topic=topic,
        hook=hook,
        beats=beats,
        target_seconds=target_seconds,
        words_per_second=words_per_second,
        dropped_items=dropped,
    )
