"""The reel itself: hook, answer, value, retention, takeaway, CTA.

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
#: never a demand, and only ever at the end.
CTA_VARIANTS: tuple[str, ...] = (
    "Síguenos para más consejos claros y sencillos sobre diabetes.",
    "Si esto te ha aclarado algo, síguenos para más.",
    "Síguenos si quieres entender mejor tu alimentación.",
    "Te lo explicamos claro cada día: síguenos.",
)

#: Small lines that buy attention across a list without promising anything.
#: Used sparingly - two at most - because a retention line that arrives every
#: item stops being a signal and starts being filler, which is the one thing
#: the brief rules out by name.
#: Words reserved for the retention lines before the items are chosen. They
#: are spoken words like any other and the first version forgot to budget for
#: them, which is why a 45 second reel came out at 48.6.
_RETENTION_WORDS = 6

RETENTION_LINES: tuple[str, ...] = (
    "Pero atención con la siguiente.",
    "Y la última suele sorprender bastante.",
    "Aquí es donde mucha gente se equivoca.",
    "La cantidad sigue siendo importante.",
)

#: How the value section introduces itself in each format. The spine of the
#: reel changes with the format, not just its wording.
FORMAT_LEADS: dict[str, str] = {
    "list": "",
    # No lead. The answer beat has just named all five, so "vamos con el
    # primero" is four words spent announcing a list the viewer already has.
    "error_solution": "",
    "comparison": "Vamos a compararlas.",
    "ranking": "De menor a mayor impacto aproximado.",
    "myth": "Vamos por partes.",
    "combination": "Estas son las combinaciones.",
}

#: A reel with no items is not a short reel, it is an empty one. Below this
#: the duration request loses to the content.
MIN_ITEMS = 2

#: Words per second, at the rate a reel narrator actually speaks.
#:
#: Measured, on the runner, from the voice comparison: the same 126 word
#: script came out at 48.05s under Kokoro and 46.79s under Piper, which is
#: 2.62 and 2.69 words a second including every pause. The slower of the two
#: is the default because Kokoro is.
#:
#: This is deliberately *not* the content language's words-per-minute. That
#: number is 142 wpm for Spanish and it describes long-form narration, with
#: long-form pauses between scenes; applying it to a reel under-counts the
#: budget by a fifth, which is two items of a five item list. The first
#: Kokoro render was refused for exactly that reason.
DEFAULT_WORDS_PER_SECOND = 2.62

#: What each narrator was measured at, when it is the one speaking.
MEASURED_WORDS_PER_SECOND: dict[str, float] = {
    "kokoro": 2.62,
    "piper": 2.69,
}


@dataclass
class Beat:
    """One narrated line and the picture that goes with it."""

    kind: str                 # hook | answer | lead | item | retention | takeaway | cta
    text: str
    query: str = ""
    search_text: str = ""
    index: int = 0
    sources: tuple[str, ...] = ()
    item_key: str = ""
    #: Whether this beat states why it is true. Recorded rather than inferred,
    #: because "does this sentence contain a reason" is not a question a
    #: keyword search answers, and the builder already knows.
    has_reason: bool = False
    #: When this beat is spoken, filled in once the narration exists. The
    #: frame inspector needs it: mapping a sampled timestamp back to a beat by
    #: kind picks the *first* beat of that kind, which is how a frame showing
    #: the manzana line came to be reported as the fresas line.
    start: float = 0.0
    end: float = 0.0

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
            "has_reason": self.has_reason,
            "start": round(self.start, 3),
            "end": round(self.end, 3),
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
    def takeaway(self) -> str:
        return next((b.text for b in self.beats if b.kind == "takeaway"), "")

    @property
    def items_without_a_reason(self) -> list[str]:
        return [b.text for b in self.item_beats if not b.has_reason]

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
    the identical sentence every time. A topic may name the variation it
    wants; that is still one of the four, so the rule about what a CTA may
    say holds either way.
    """

    if topic.cta:
        return topic.cta
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


#: At or above this the hook and the takeaway are the same clause twice.
_HOOK_ECHO_WORDS = 5

#: The answer has to have started by here, so this is the hook's time budget.
#: The gate in :mod:`.qc` reads the same number from here: a builder that can
#: hand out a hook the report then refuses is two rules, not one.
HOOK_SECONDS = 6.5

#: A hook scoring within this of the best is treated as its equal, and the
#: shortest of them wins.
#:
#: Because the hook has a *time* budget as well as a quality one. The brief
#: puts it in the first two seconds; at this voice's rate that is six words,
#: and the strongest-scoring candidate is regularly eighteen - five seconds
#: of a forty second reel, paid for out of the items. Within a margin this
#: small the candidates are not meaningfully different in quality, and the
#: shorter one is better for a reason the score does not measure.
_HOOK_LENGTH_MARGIN = 0.06

#: The report fails a reel whose hook is not about its content; the builder
#: should not hand it one. Kept equal to the gate in :mod:`.qc` on purpose.
_HOOK_MIN_ALIGNMENT = 0.5


def _hook_pass() -> float:
    from .hooks import HOOK_PASS

    return HOOK_PASS


def _distinct_hook(
    topic: Topic,
    extra: Sequence[str] = (),
    words_per_second: float = DEFAULT_WORDS_PER_SECOND,
) -> HookChoice:
    """The best hook that is not already the conclusion.

    The fruit topic's strongest candidate was "la fruta no tiene por que
    desaparecer de tu dieta" - which is also, word for word, how that reel
    ends. A reel that opens and closes on the same sentence has spent its
    conclusion in the first two seconds.
    """

    choice = choose_hook(topic, extra=extra)
    usable = [
        c for c in choice.candidates
        if not c.rejected
        and _shared_run(c.text, topic.takeaway_line) < _HOOK_ECHO_WORDS
    ]
    if not usable:
        return choice
    # Three things the report will gate on, applied together rather than in
    # sequence. In sequence they fight: filtering by strength first can throw
    # away the only candidate that fits the time budget, and then the builder
    # hands out a hook its own report refuses. Only if nothing satisfies all
    # three does this fall back - and then the report says which one gave.
    budget = max(6, int(HOOK_SECONDS * max(1.0, words_per_second)))

    def viable(candidate: Any) -> bool:
        return (
            candidate.scores.get("alignment", 0.0) >= _HOOK_MIN_ALIGNMENT
            and candidate.total >= _hook_pass()
            and len(candidate.text.split()) <= budget
        )

    usable = [c for c in usable if viable(c)] or usable
    best = max(c.total for c in usable)
    close = [c for c in usable if c.total >= best - _HOOK_LENGTH_MARGIN]
    winner = min(close, key=lambda c: (len(c.text.split()), -c.total))
    return HookChoice(
        hook=winner.text,
        strength=winner.total,
        alignment=winner.scores.get("alignment", 0.0),
        candidates=choice.candidates,
    )


def _retention_count(items: int) -> int:
    """How many retention lines a reel with this many items earns.

    One, until the list is long enough that a viewer needs a second push. A
    line that arrives every other item stops being a signal and becomes the
    filler the brief rules out by name - and in a forty second reel each one
    costs an item's worth of words, which is a bad trade: the items are the
    reason anyone is still watching.
    """

    if items >= 6:
        return 2
    return 1 if items >= 4 else 0


def _retention_slots(items: int) -> set[int]:
    """Where they go: two thirds in, and for a long list also a third in."""

    if items >= 6:
        return {max(1, items // 3), items - 1}
    return {items - 1} if items >= 4 else set()


def _item_text(item: Item) -> str:
    """One item: the claim and the reason it is true, always both.

    The reason used to be optional - the first thing dropped when the duration
    got tight - and dropping it is what produced a list of five assertions with
    nothing behind any of them. An item the viewer cannot act on because they
    were not told *why* is not shorter value, it is a different and worse reel,
    so the budget now buys fewer items rather than emptier ones.
    """

    claim = item.claim.rstrip(" .")
    why = str(item.why or "").strip()
    if not why:
        return claim + "."
    joiner = "" if why.startswith(("y ", "asi ", "pero ", "aunque ", "porque ")) else ", "
    return f"{claim}{joiner}{why.rstrip(' .')}." if joiner else f"{claim} {why.rstrip(' .')}."


#: Added to the conclusion when nothing else in the reel says it. Almost
#: every statement in this niche is only correct with one of these attached,
#: so a trimmed script that has lost them all gets one back rather than a
#: warning: the warning tells an operator the reel is weaker, and the viewer
#: is the one who needed the sentence.
CAVEAT_LINE = (
                  "Recuerda que la cantidad y la respuesta de cada persona "
                  "también cuentan."
              )


def _ensure_caveat(beats: list[Beat]) -> None:
    from .safety import mentions_caveat

    if mentions_caveat(" ".join(b.text for b in beats)):
        return
    for beat in beats:
        if beat.kind == "takeaway":
            beat.text = beat.text.rstrip() + " " + CAVEAT_LINE
            return


def _assemble(
    topic: Topic,
    hook: HookChoice,
    cta: str,
    lead: str,
    items: Sequence[Item],
) -> list[Beat]:
    """The finished beat list for exactly these items.

    Assembled rather than estimated, because the estimate was wrong in a way
    that cost items: the caveat line is added *after* the script is written,
    so a trim that budgeted for everything except it produced a 45 second
    request at 50.0 seconds. Counting the words of the real thing is both
    simpler and exact.
    """

    query, search = topic.opening_query, topic.opening_search_text
    beats = [
        Beat("hook", hook.hook, query, search),
        # The answer, not a trailer for one. "En este reel vas a ver cinco
        # frutas" spends the third second describing the reel to someone who
        # is already watching it; "fresas, frambuesas, kiwi, manzana con piel
        # y aguacate" is the same length and is already the value.
        Beat("answer", topic.answer_line, query, search),
    ]
    if lead and items:
        beats.append(Beat("lead", lead, query, search))

    slots = _retention_slots(len(items))
    used: set[str] = set()

    def retention_line(index: int, last: bool) -> str:
        preferred = RETENTION_LINES[1] if last else RETENTION_LINES[
            _stable_index(f"{topic.slug}:{index}", len(RETENTION_LINES))
        ]
        if preferred not in used:
            used.add(preferred)
            return preferred
        for candidate in RETENTION_LINES:
            if candidate not in used:
                used.add(candidate)
                return candidate
        return preferred                                  # pragma: no cover

    for index, item in enumerate(items):
        if index in slots:
            beats.append(
                Beat("retention", retention_line(index, index == len(items) - 1),
                     item.query, item.search_text, index=index)
            )
        beats.append(
            Beat(
                kind="item",
                text=_item_text(item),
                query=item.query,
                search_text=item.search_text,
                index=index,
                sources=item.sources,
                item_key=item.key,
                has_reason=bool(str(item.why or "").strip()),
            )
        )

    beats.append(Beat("takeaway", topic.takeaway_line, query, search))
    beats.append(Beat("cta", cta, query, search))
    _ensure_caveat(beats)
    return beats


def build(
    topic: Topic,
    target_seconds: float = DEFAULT_SECONDS,
    words_per_second: float = DEFAULT_WORDS_PER_SECOND,
    max_items: int = 0,
    extra_hooks: Sequence[str] = (),
) -> ReelScript:
    """Fit this topic into the requested duration without losing the point.

    The fixed beats are non-negotiable: a reel without a hook has no opening,
    and one without a CTA is the whole reason the account exists. So the items
    absorb the budget - and they absorb it as whole items, because every item
    keeps the reason it is true.
    """

    words_per_second = max(1.5, float(words_per_second))
    target_seconds = float(target_seconds or DEFAULT_SECONDS)
    budget_words = target_seconds * words_per_second

    hook = _distinct_hook(topic, extra_hooks, words_per_second)
    cta = cta_for(topic)
    lead = FORMAT_LEADS.get(topic.format, "")

    items = list(topic.items)
    if max_items > 0:
        items = items[:max_items]
    dropped: list[str] = []
    floor = min(MIN_ITEMS, len(items))
    required = topic.required_item_count

    def words(chosen: Sequence[Item]) -> int:
        return sum(b.word_count for b in _assemble(topic, hook, cta, lead, chosen))

    while len(items) > floor and words(items) > budget_words * 1.02:
        dropped.append(items[-1].key)
        items = items[:-1]

    # A number in the title is a requirement, exactly as it is on the
    # long-form side. "5 frutas" that delivers four is not a shorter reel, it
    # is a reel whose first line is false - and the title is on screen for the
    # whole forty seconds saying so. Renaming it silently would be worse, so
    # this raises and names the duration that would fit.
    if required and len(items) < required:
        where = "in its answer" if topic.promises_all_items else "in its title"
        raise ValueError(
            f"{topic.slug!r} promises {required} items {where} and only "
            f"{len(items)} fit in {target_seconds:.0f}s at "
            f"{words_per_second:.2f} words/second. Render it longer "
            f"({_smallest_fit(topic, words, words_per_second, required)}) or "
            f"shorten the items."
        )

    return ReelScript(
        topic=topic,
        hook=hook,
        beats=_assemble(topic, hook, cta, lead, items),
        target_seconds=target_seconds,
        words_per_second=words_per_second,
        dropped_items=dropped,
    )


def build_fitted(
    topic: Topic,
    target_seconds: float = DEFAULT_SECONDS,
    words_per_second: float = DEFAULT_WORDS_PER_SECOND,
    max_items: int = 0,
    extra_hooks: Sequence[str] = (),
) -> tuple[ReelScript, float]:
    """The script, at the shortest allowed duration that keeps its promise.

    :func:`build` is strict on purpose - it will not quietly ship four items
    under a title that says five - but strictness in a pure function is not a
    reason for the pipeline to produce nothing. A number in the title is not
    negotiable and the duration is a request from a fixed menu, so when the
    two collide the duration moves, loudly, and both numbers reach the report.

    Returns the script and the duration it was actually built for.
    """

    wanted = [s for s in ALLOWED_SECONDS if s >= target_seconds]
    attempts = [target_seconds, *[s for s in wanted if s != target_seconds]]
    last: ValueError | None = None
    for candidate in attempts:
        try:
            script = build(
                topic,
                target_seconds=candidate,
                words_per_second=words_per_second,
                max_items=max_items,
                extra_hooks=extra_hooks,
            )
        except ValueError as exc:
            last = exc
            continue
        return script, float(candidate)
    raise last if last else RuntimeError("no script could be built")


def _smallest_fit(
    topic: Topic, words: Any, words_per_second: float, required: int
) -> str:
    """The shortest allowed duration that would hold the promised items."""

    needed = words(list(topic.items)[:required]) / words_per_second
    for allowed in ALLOWED_SECONDS:
        if allowed * 1.02 >= needed:
            return f"--seconds {allowed}"
    return f"about {needed:.0f}s, which is longer than the allowed durations"
