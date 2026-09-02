"""Original narration script generation - no paid API, ever.

Two engines are available:

``template``
    The default. Assembles an original script from the curated knowledge base
    using a large pool of varied phrasings, transitions and structures. It is
    deterministic for a given topic seed, needs no network, no model download
    and no GPU, and it always works on a GitHub Actions CPU runner.

``llm``
    Optional. Runs a small quantized instruct model locally through
    llama.cpp (see :mod:`vidfactory.llm`). It is opt-in because a CPU-only
    runner is slow and the download is large; when it is unavailable or too
    slow the generator falls back to the template engine rather than failing.

Either way, the output is an original editorial script: a hook, a promise,
numbered ideas with real explanation and implementation advice, natural
transitions, a conclusion and a light call to action.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass, field
from typing import Any, Sequence

from .knowledge import ALL_CATEGORIES, Tip, tips_for
from .title_alignment import (
    AlignmentResult,
    Promise,
    alignment_ratio,
    detect_promise,
    filter_aligned,
)
from .logging_utils import get_logger
from .topic_engine import Topic

log = get_logger("SCRIPT")

WORDS_PER_ITEM_TARGET = 105
#: Below this length the intro and outro are compacted so short videos
#: (used by the integration test and for quick previews) stay on target.
COMPACT_BELOW_MINUTES = 3.0


# ---------------------------------------------------------------------------
# Script data model
# ---------------------------------------------------------------------------

@dataclass
class ScriptSection:
    """One structural block of the finished narration."""

    kind: str                     # intro | item | outro
    heading: str                  # used for YouTube chapters
    text: str
    index: int = 0
    tip: Tip | None = None
    #: Set when the local model disagrees that this idea serves the title.
    flagged_off_promise: bool = False

    @property
    def word_count(self) -> int:
        return len(self.text.split())


@dataclass
class Script:
    """A complete narration script plus the metadata the pipeline needs."""

    title: str
    topic: Topic
    sections: list[ScriptSection] = field(default_factory=list)
    engine: str = "template"
    #: What the title commits every idea to deliver.
    promise_key: str = "general"
    promise_label: str = ""
    #: Ideas dropped because they did not support the title promise.
    rejected_ideas: list[dict[str, Any]] = field(default_factory=list)
    #: Share of the chosen ideas that support the promise (0.0 - 1.0).
    title_idea_alignment: float = 1.0

    @property
    def text(self) -> str:
        return "\n\n".join(section.text for section in self.sections)

    @property
    def word_count(self) -> int:
        return len(self.text.split())

    @property
    def estimated_seconds(self) -> float:
        return self.word_count / 150.0 * 60.0

    def items(self) -> list[ScriptSection]:
        return [s for s in self.sections if s.kind == "item"]

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "engine": self.engine,
            "word_count": self.word_count,
            "promise": {"key": self.promise_key, "label": self.promise_label},
            "title_idea_alignment": self.title_idea_alignment,
            "rejected_ideas": list(self.rejected_ideas),
            "topic": self.topic.to_dict(),
            "sections": [
                {
                    "kind": s.kind,
                    "heading": s.heading,
                    "index": s.index,
                    "text": s.text,
                    "queries": (s.tip or {}).get("queries", []),
                }
                for s in self.sections
            ],
        }


# ---------------------------------------------------------------------------
# Phrase pools - the variation that keeps consecutive videos from sounding alike
# ---------------------------------------------------------------------------

HOOKS = [
    "Some rooms just feel right the moment you walk into them, and it is almost never because of how much the furniture cost.",
    "There is a reason a designed room feels different from a decorated one, and most of that difference comes down to a handful of decisions.",
    "You can spend a fortune on a room and still have it feel unfinished, and you can spend very little and have it feel considered.",
    "Most homes are only a few small decisions away from looking dramatically better than they do right now.",
    "If your home looks fine in real life but strange in photographs, the problem is almost always one of the things we are about to go through.",
    "The difference between a room that works and a room that does not is rarely money. It is usually scale, light and restraint.",
    "Walk into any well-designed home and you will find the same quiet decisions repeated over and over again.",
    "Almost every room that feels wrong is making one of a very small number of mistakes, and every one of them is fixable.",
]

PROMISES = [
    "In this video we are going through {count} of them, one at a time, with the reasoning behind each one and exactly how to apply it in a real home.",
    "Over the next {duration} {minutes} we will work through {count} {ideas}, and for each one I will explain why it works and how to actually do it.",
    "We are going to cover {count} specific {changes}, why designers rely on {them}, and what to do if your space does not cooperate.",
    "Here are {count} {ideas} worth knowing, each with the principle behind {it} and a practical way to put {it} into your own home this week.",
    "What follows is {count} practical {ideas}. No shopping lists you cannot afford, no renovations, just decisions that change how a room reads.",
]

PROMISE_TAILS = [
    "Some of these cost nothing at all.",
    "Several of them take an afternoon and no special tools.",
    "A few of them are free and just involve moving what you already own.",
    "You do not need to do all of them. Two or three will already be noticeable.",
    "Take the ones that fit your home and ignore the rest.",
]

ITEM_OPENERS = [
    "Number {n}.",
    "Idea number {n}.",
    "Number {n} on the list.",
    "That brings us to number {n}.",
    "Next, number {n}.",
]

TRANSITIONS = [
    "The next one follows directly from that.",
    "This next idea solves a related problem.",
    "Here is another one that people underestimate.",
    "The following idea is one of the easiest on this list.",
    "This next point comes up in almost every home.",
    "Once that is sorted, the next thing to look at is this.",
    "There is a related idea worth covering here.",
    "This one is less obvious, but it matters just as much.",
    "The next idea is where a lot of rooms go wrong.",
    "Here is something that changes a room faster than most people expect.",
]

WHY_LEADS = [
    "Here is why that matters.",
    "The reason is straightforward.",
    "The thinking behind this is simple.",
    "This works for a specific reason.",
    "There is a real principle underneath this.",
    "",
    "",
]

HOW_LEADS = [
    "In practice, here is how to do it.",
    "To put this into your own home,",
    "Practically speaking,",
    "Here is how to apply it.",
    "The way to actually do this is simple.",
    "",
    "",
]

MISTAKE_LEADS = [
    "The mistake to watch out for:",
    "Where this usually goes wrong:",
    "One thing to avoid:",
    "This is where most rooms slip up.",
]

MICRO_SUMMARIES = [
    "It is a small change, but it changes the whole read of the room.",
    "It costs very little and it is difficult to unsee once you notice it.",
    "That single adjustment does more than another round of shopping ever will.",
    "It is one of those details you only notice when it is missing.",
    "Do this one thing and the rest of the room starts to make more sense.",
    "It is worth doing even if you change nothing else.",
]

CONCLUSION_LEADS = [
    "So that is the full list.",
    "That brings us to the end of the list.",
    "That is all {count} of them.",
    "So there you have it, {count} {ideas} to work with.",
]

CONCLUSION_BODIES = [
    "If you take one thing away from all of this, make it the idea that good rooms are edited rather than filled. Almost every point we covered is really about removing a distraction or giving one element enough space to work properly.",
    "The common thread through all of this is restraint. Scale, light and material do most of the work, and the accessories do far less than people expect.",
    "None of this needs to happen at once. Pick the two changes that felt most relevant to your own home, do those properly, and then live with the room for a couple of weeks before deciding what is next.",
    "What ties these together is that none of them depend on a big budget. They depend on paying attention to proportion, to light, and to what you have already got.",
    "If your room still feels off after all of this, go back to the basics: is the lighting warm and layered, is the rug big enough, and is there anything on a surface that does not need to be there.",
]

CTAS = [
    "If this was useful, subscribing helps you catch the next one.",
    "If you found something here worth trying, there are more videos like this on the channel.",
    "Thanks for watching, and I will see you in the next one.",
    "If you have a room you are stuck with, leave it in the comments and it might end up in a future video.",
    "That is it for today. Thanks for spending the time.",
]

# Extra sentences used to expand an item when the script needs to reach a
# longer target duration. They are selected by the tip's own tags so the
# expansion stays on topic rather than becoming filler.
ELABORATIONS: dict[str, list[str]] = {
    "lighting": [
        "Try it in the evening rather than in daylight, because that is when the difference is most obvious.",
        "If you are not sure whether it is working, photograph the room before and after. The camera is less forgiving than your eye.",
    ],
    "color": [
        "Look at it again at three different times of day before you commit, because color shifts more than people expect.",
        "If two options feel equally good, take the warmer one. Warm reads as welcoming under artificial light.",
    ],
    "rug": [
        "Measure the seating area with tape on the floor before ordering, because rug sizes are difficult to judge from a listing.",
        "A rug pad is worth the extra cost. It stops movement and makes an inexpensive rug feel considerably more substantial underfoot.",
    ],
    "storage": [
        "Whatever you decide, leave some room to grow. Storage that is full on day one stops working within a month.",
        "Take everything out first and sort it before you buy any containers, otherwise you end up storing things you do not need.",
    ],
    "layout": [
        "Try it before committing. Furniture can be moved back, and most layout improvements are obvious within a day of living with them.",
        "Sit in every seat afterwards and check the view from each one. That is the fastest way to spot what still needs adjusting.",
    ],
    "texture": [
        "Touch matters as much as appearance here. If a surface feels good under your hand, it will usually read well in the room too.",
        "Mix the scale of the textures as well as the type, so a chunky weave sits next to something smooth.",
    ],
    "curtains": [
        "Steam or press the panels once they are hung. Creases from the packaging are what make new curtains look cheap.",
        "Weighted hems hang far better, and you can add small drapery weights to inexpensive panels yourself.",
    ],
    "art": [
        "Lay the arrangement out on the floor first and photograph it. It is much easier to judge on screen than on the wall.",
        "Use painter's tape to mark the outline on the wall before you drill anything.",
    ],
    "plants": [
        "Match the plant to the light you actually have rather than to the one you wish you had, and it will look after itself.",
        "Put the pot on a saucer or in a cachepot so watering never becomes a reason to move it.",
    ],
    "budget": [
        "Spread the cost over a few months rather than doing it all at once. The room will end up better considered as well as cheaper.",
        "Check secondhand listings first. This is exactly the category where used items are barely distinguishable from new.",
    ],
    "declutter": [
        "Work in one small area at a time and finish it. A half-cleared room feels worse than an untouched one.",
        "Put anything you are unsure about in a box for a month. If you have not opened it, the decision has been made for you.",
    ],
    "organization": [
        "Set it up so that putting things away is easier than leaving them out, and it will maintain itself.",
        "Give it two weeks before you judge the system, because the first few days always feel awkward.",
    ],
    "furniture": [
        "Check the dimensions against your doorways and stairwell before ordering anything large.",
        "Sit in it for longer than feels necessary in the showroom. Comfort problems only appear after ten minutes.",
    ],
    "materials": [
        "Choose the version that will age well rather than the one that looks best on day one. Those are rarely the same product.",
        "Ask for a sample and live with it in the room for a week before committing.",
    ],
    "mistake": [
        "It is worth walking through your own home specifically looking for this one. It shows up more often than you would think.",
        "If you spot it, fix it before adding anything new, because everything else will look better once it is resolved.",
    ],
}

GENERIC_ELABORATIONS = [
    "It is the kind of change that seems minor written down and reads as significant once it is in the room.",
    "Give it a week before you judge it, because the eye adjusts to a room slowly.",
    "If you only do a handful of things from this list, this is a reasonable one to start with.",
    "Photograph the room before and after. The difference is usually clearer on a screen than in person.",
    "None of this requires a professional. It requires deciding, and then being willing to move things twice.",
    "The cost here is time rather than money, which is why it is so often skipped.",
    "Do it once properly rather than twice cheaply, and you will not have to think about it again.",
    "If you live with other people, agree on this one before you start moving things.",
    "Measure first. Almost every regret in decorating traces back to a measurement nobody took.",
    "Stand back and look from the doorway rather than from the middle of the room.",
    "It is worth doing on a quiet afternoon rather than squeezing it into a busy one.",
    "Notice how the room feels in the evening as well as in daylight, because the two can differ sharply.",
    "There is no rush on this. Rooms improve faster when decisions are made slowly.",
    "Keep whatever you remove for a month before letting it go, in case the room tells you otherwise.",
]



# ---------------------------------------------------------------------------
# Promise-aware hooks
#
# The first fifteen seconds have to create curiosity, not introduce a channel.
# Each hook names a problem the viewer recognises and implies that it is
# fixable, then the script goes straight into the ideas.
# ---------------------------------------------------------------------------

PROMISE_HOOKS: dict[str, list[str]] = {
    "bigger": [
        "If your {room} feels smaller than it really is, the problem may not be the square footage. A handful of ordinary decorating choices can visually shrink a room, and reversing them can make the exact same space feel dramatically bigger.",
        "Two rooms can have identical dimensions and feel completely different to stand in. The one that feels bigger is almost never the one with less furniture in it, and that surprises people.",
        "There is a version of your {room} that feels noticeably larger, and reaching it does not involve knocking down a single wall. It involves undoing about six decisions that are quietly costing you space.",
        "Most small rooms are not actually short of space. They are short of sightlines, light and vertical thinking, and all three are things you can fix this weekend.",
    ],
    "expensive": [
        "Expensive-looking rooms are rarely expensive rooms. Walk into any home that feels high end and you will find the same small decisions repeated, and almost none of them are about how much anything cost.",
        "There is a specific reason a room reads as cheap, and it is almost never the furniture. It is a short list of details that are cheap to fix and impossible to unsee once you know them.",
        "You can spend twenty thousand on a room and have it look ordinary, or spend a fraction of that and have it look considered. The difference comes down to things most people never think about.",
        "The gap between a builder-grade {room} and one that looks designed is smaller than you think, and most of it is measured in millimetres and finishes rather than money.",
    ],
    "cozy": [
        "Cosiness is not a style you buy. It is a set of physical conditions, and once you know what they are you can produce them in almost any room, including a cold modern one.",
        "Some rooms make you want to sit down and stay. It is not the furniture, and it is not the size, and it is almost entirely something you can change tonight.",
        "If your {room} looks good in photographs but nobody actually relaxes in it, there is usually one culprit, and it is hanging from the middle of your ceiling.",
    ],
    "storage": [
        "Most homes do not have a storage problem. They have a storage-in-the-wrong-place problem, and the difference is what makes one house feel calm and another feel permanently untidy.",
        "If you have run out of space, there is a good chance you still have unused cubic metres in every room. They are just above your head, behind your doors and under your bed.",
        "Buying more containers almost never fixes clutter. What fixes it is a small number of decisions about where things live, and they cost nothing at all.",
    ],
    "mistakes": [
        "Almost every room that feels slightly wrong is making the same small number of mistakes. None of them are obvious, all of them are common, and every single one is reversible.",
        "You can follow every rule you have read and still end up with a room that feels off. Usually it is because of something nobody warned you about, and it is probably on this list.",
        "These are the mistakes that show up in real homes constantly, and the frustrating part is that they are cheap to fix once somebody points at them.",
    ],
    "budget": [
        "The most effective changes you can make to a home are usually not the expensive ones. Some of the best cost nothing beyond an afternoon and a willingness to move things twice.",
        "A small budget forces better decisions, because you cannot solve a design problem by buying your way out of it. That constraint tends to produce better rooms.",
        "If your budget is tight, the good news is that the things that most affect how a {room} feels are mostly cheap. The expensive parts matter far less than people assume.",
    ],
    "timeless": [
        "Some rooms still look right twenty years later, and others date within a season. The difference is decided by a handful of choices made early, and most of them are about restraint.",
        "You can tell what year a room was decorated within about eighteen months. Unless it was done in a way that deliberately avoids that, which is what this comes down to.",
    ],
    "renter": [
        "Renting does not mean living in a beige box for three years. Nearly everything that makes a home feel like yours is reversible, and a surprising amount of it needs no permission at all.",
        "The reason most rented homes feel temporary is not the lease. It is that people stop at the point where they think they need permission, and that point is much further away than they think.",
    ],
    "brighter": [
        "A dark room is rarely as dark as it feels. Most of the light already reaching it is being absorbed, blocked or wasted before it ever gets to where you are sitting.",
        "If you have ever wondered why a room feels gloomy at four in the afternoon despite having a perfectly good window, the answer is usually a combination of about four things.",
    ],
}

#: Used when a title makes no specific promise.
GENERAL_HOOKS = [
    "Some rooms just feel right the moment you walk into them, and it is almost never because of how much anything in them cost.",
    "There is a reason a designed room feels different from a decorated one, and most of that difference comes down to a handful of decisions anyone can make.",
    "Most homes are only a few small decisions away from looking dramatically better than they do right now, and none of those decisions require a renovation.",
    "Walk into any well-designed home and you will find the same quiet decisions repeated over and over, whatever the budget was.",
]

#: How the idea itself is introduced. Deliberately varied in shape so the
#: script does not settle into one rhythm.
STATEMENT_FRAMES = [
    "{title}.",
    "{title}.",
    "{title}.",
    "Here is the one: {title_lower}.",
    "{title}, and it matters more than it sounds like it should.",
    "This one is simple: {title_lower}.",
    "Start here: {title_lower}.",
    "The rule is short: {title_lower}.",
    "{title}, which is easier than it sounds.",
]

QUESTION_FRAMES = [
    "Ever wondered why some rooms get this right and others do not? {title}.",
    "So what actually makes the difference here? {title}.",
    "What would you change first in a room like that? Almost always this: {title_lower}.",
    "Why does this keep coming up in well-designed homes? {title}.",
    "Want the version of this that designers actually use? {title}.",
    "What is the cheapest fix on this whole list? Arguably this one: {title_lower}.",
    "Ask yourself what your eye lands on first in that room. Then: {title}.",
    "Which of these would you notice if it were missing? Probably this: {title_lower}.",
]

WARNING_FRAMES = [
    "This is the one people get wrong most often. {title}.",
    "If you only fix one thing on this list, consider making it this one. {title}.",
    "Here is a mistake worth catching early. {title}.",
    "Be careful with this one, because it is easy to get backwards. {title}.",
    "This trips up more rooms than almost anything else. {title}.",
    "Get this wrong and everything else you do will fight it. {title}.",
    "Worth pausing on, because the fix is easy and the mistake is expensive. {title}.",
]

SCENARIO_FRAMES = [
    "Picture the room before and after this single change. {title}.",
    "Imagine walking into the same room twice, once with this done and once without. {title}.",
    "Stand in the doorway and look at your own room while you listen to this one. {title}.",
    "Think about the last home you walked into that felt genuinely finished. It almost certainly did this: {title_lower}.",
    "Try this as a thought experiment before you try it as a project. {title}.",
    "Two identical rooms, one decision apart. {title}.",
    "Picture the same room photographed by an estate agent and by a magazine. The difference is often this: {title_lower}.",
]

#: Numbered call-outs, kept short and varied. Some items skip the number
#: entirely and let the transition carry it, which reads far more naturally.
NUMBER_FRAMES = [
    "Number {n}.",
    "Idea number {n}.",
    "Number {n} on the list.",
    "That takes us to number {n}.",
    "Next, number {n}.",
    "Number {n}, and this one is a favorite.",
]

#: Transitions. Long enough a pool that a twenty minute video never repeats.
TRANSITIONS_V2 = [
    "The next one follows directly from that.",
    "This next idea solves a related problem.",
    "Here is another one people underestimate.",
    "The following idea is one of the easiest on this list.",
    "This next point comes up in almost every home.",
    "Once that is sorted, look at this next.",
    "There is a related idea worth covering here.",
    "This one is less obvious, but it matters just as much.",
    "The next idea is where a lot of rooms go wrong.",
    "Here is something that changes a room faster than most people expect.",
    "Moving on, and this one is quick.",
    "Now for something you can do in an afternoon.",
    "This next one costs nothing at all.",
    "Related to that, and just as useful.",
    "Here is where it gets interesting.",
    "That leads neatly into the next one.",
    "The flip side of that is worth knowing too.",
    "And then there is this, which people almost always skip.",
    "This next one surprises people.",
    "Keep that in mind while we look at this.",
]

#: Closers for an item. Used sparingly and never twice in a row.
ITEM_CLOSERS = [
    "It is a small change that changes the whole read of the room.",
    "Once you have seen it, you cannot unsee it in other people's homes either.",
    "That single adjustment does more than another round of shopping ever will.",
    "It is one of those details you only notice when it is missing.",
    "Worth doing even if you change nothing else on this list.",
    "Do that much and the rest of the room starts to make more sense.",
    "It sounds minor written down. It is not minor in the room.",
    "This is the sort of thing people cannot name but always notice.",
]

INTRO_CONTEXT = {
    "living rooms": "The living room is usually the largest shared space in a home and the one that gets photographed, which is exactly why its problems are so visible.",
    "bedrooms": "A bedroom has an unusual job. It has to look good and it has to help you switch off, and those two goals pull in different directions more often than people realize.",
    "kitchens": "Kitchens are the most expensive rooms per square foot in most homes, which makes it frustrating when they still feel like they are missing something.",
    "bathrooms": "Bathrooms are small, hard-surfaced and full of function, which is exactly why small decisions have such a large effect in them.",
    "small spaces": "Small spaces are not a design problem to be solved. They are a set of constraints, and constraints usually produce better rooms than unlimited square footage does.",
    "home organization": "Organization fails when it depends on discipline. The systems that survive are the ones that are easier to follow than to ignore.",
    "lighting": "Lighting is the single most underrated element in a home. It changes color, mood, perceived size and how tired you feel in the evening.",
    "colors": "Color is the decision people agonise over most and get wrong most often, usually because they choose it first instead of last.",
    "furniture placement": "Furniture placement is free. It is also the thing that most reliably separates a room that works from a room that does not.",
    "storage": "Storage is not about having more cupboards. It is about matching the space to what actually lives in the room.",
    "expensive look": "Expensive-looking rooms are rarely expensive rooms. They are rooms where a small number of details have been handled properly.",
    "interior design mistakes": "None of these mistakes are unusual. Most homes are making at least three of them right now, and every one of them is reversible.",
    "budget decorating": "A small budget forces better decisions, because it removes the option of solving a design problem by buying something.",
    "renter-friendly decorating": "Renting does not mean living in a beige box. Almost everything that makes a home feel personal is reversible.",
    "cozy homes": "Coziness is not a style, it is a set of physical conditions: low warm light, soft surfaces, enclosure and a bit of visible life.",
    "minimalist design": "Minimalism is widely misunderstood as a shopping category. It is actually a discipline of removal.",
    "scandinavian design": "Scandinavian interiors come from a climate with very little winter daylight, and almost every element of the style is a response to that.",
    "modern homes": "Modern interiors live or die on their detailing, because there is no ornament to hide behind.",
    "luxury interiors": "Luxury in a home is mostly generosity: more space around things, more fabric, thicker material, better light.",
    "apartment decorating": "Apartments come with a fixed shell and a lot of shared constraints, so the wins come from layout, light and sound rather than from structure.",
    "farmhouse design": "Farmhouse interiors come from working buildings, which is why honest materials matter so much more than decorative references.",
    "mediterranean design": "Mediterranean interiors are built around strong sunlight and hard shadow, and the materials all come from the same landscape.",
    "seasonal decorating": "Seasonal decorating works best when it is a small adjustment to a stable room, not a complete reinvention four times a year.",
    "timeless interiors": "Timelessness is not a style. It is a set of choices about where to spend, what to keep plain and what to allow to age.",
    "diy decor": "The best home projects are the ones where a small amount of work produces a change out of all proportion to the effort.",
    "design trends": "Trends are useful as a signal of where taste is moving, as long as you apply them to the cheap and changeable parts of a room.",
}


# ---------------------------------------------------------------------------
# Template engine
# ---------------------------------------------------------------------------

def count_words(count: int) -> dict[str, str]:
    """Grammar helpers so a one-item script never says "1 ideas"."""

    singular = count == 1
    return {
        "count": "one" if singular else str(count),
        "ideas": "idea" if singular else "ideas",
        "changes": "change" if singular else "changes",
        "them": "it" if singular else "them",
        "it": "it",
    }


#: Natural-language room word used inside hooks.
_ROOM_WORDS: dict[str, str] = {
    "living rooms": "living room",
    "bedrooms": "bedroom",
    "kitchens": "kitchen",
    "bathrooms": "bathroom",
    "small spaces": "space",
    "apartment decorating": "apartment",
    "renter-friendly decorating": "rental",
    "home organization": "home",
    "storage": "home",
}


def _room_word(category: str) -> str:
    return _ROOM_WORDS.get(str(category or ""), "home")


def _clean(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    return text


def _join_lead(lead: str, body: str) -> str:
    """Join an optional lead-in phrase with a sentence, keeping grammar sane."""

    lead = lead.strip()
    if not lead:
        return body
    if lead.endswith((".", "!", "?")):
        return f"{lead} {body}"
    # Lead ends mid-sentence ("In practice," / "Practically speaking,")
    return f"{lead} {body[0].lower() + body[1:]}"


def retitle_for_count(title: str, count: int) -> str:
    """Keep the number in the title honest without producing "1 ... Ideas".

    A single-item video drops the leading number entirely, which reads
    naturally ("Small Living Room Ideas") instead of ungrammatically.
    """

    promised = re.match(r"^(\d{1,3})\s+", title)
    if not promised:
        return title
    if int(promised.group(1)) == count:
        return title
    if count < 2:
        return re.sub(r"^\d{1,3}\s+", "", title, count=1)
    return re.sub(r"^\d{1,3}\b", str(count), title, count=1)


class TemplateScriptEngine:
    """Assembles an original script from curated knowledge blocks."""

    name = "template"

    def __init__(self, words_per_minute: float = 150.0, seed: int | None = None) -> None:
        self.words_per_minute = float(words_per_minute)
        self.seed = seed

    # ------------------------------------------------------------------
    def plan_item_count(self, topic: Topic, duration_minutes: float, pool_size: int) -> int:
        target_words = duration_minutes * self.words_per_minute
        compact = duration_minutes < COMPACT_BELOW_MINUTES
        overhead = 70 if compact else 260                  # intro + outro words
        body_words = max(target_words - overhead, 60 if compact else 200)
        floor = 1 if duration_minutes < 1.5 else 3
        wanted = max(floor, int(round(body_words / WORDS_PER_ITEM_TARGET)))
        promised = topic.item_count
        # Honor the number promised in the title, but only when it is close
        # enough to the requested duration to be achievable. A 5 minute video
        # cannot honestly deliver 25 ideas, so the title gets renumbered.
        if promised and pool_size >= promised:
            tolerance = max(3, int(0.35 * wanted))
            if abs(promised - wanted) <= tolerance:
                wanted = promised
        return max(floor, min(wanted, pool_size))

    # ------------------------------------------------------------------
    def generate(self, topic: Topic, duration_minutes: float) -> Script:
        rng = random.Random(self.seed if self.seed is not None else hash(topic.slug) & 0xFFFFFFFF)
        promise = detect_promise(topic.title, topic.angle)

        pool = tips_for(topic.category) or tips_for(None)
        rng.shuffle(pool)

        wanted = self.plan_item_count(topic, duration_minutes, len(pool))
        aligned, rejected = filter_aligned(pool, promise, minimum=min(3, wanted))

        # If validating against the title promise leaves too little material,
        # widen the search across every category before giving up on the
        # promise - a broader pool is always better than a weaker promise.
        if len(aligned) < wanted and promise.key != "general":
            widened = [t for t in tips_for(None) if t not in pool]
            rng.shuffle(widened)
            extra, extra_rejected = filter_aligned(
                widened, promise, minimum=0
            )
            if extra:
                log.info(
                    "Widened the idea pool across all categories to satisfy "
                    "the '%s' promise (+%d aligned ideas)",
                    promise.key,
                    len(extra),
                )
            aligned = aligned + extra
            rejected = rejected + extra_rejected

        if rejected:
            log.info(
                "Rejected %d idea(s) that do not support '%s'; kept %d that do",
                len(rejected),
                promise.label,
                len(aligned),
            )
            for result in rejected[:3]:
                log.debug("  dropped %r - %s", result.tip["title"], result.explain())

        pool = aligned or pool
        count = self.plan_item_count(topic, duration_minutes, len(pool))
        chosen = pool[:count]

        # Retitle the video honestly when the pool could not fill the promise.
        title = retitle_for_count(topic.title, count)
        if title != topic.title:
            log.info("Adjusted the title to match the %d ideas available", count)

        compact = duration_minutes < COMPACT_BELOW_MINUTES
        sections: list[ScriptSection] = [
            self._intro(topic, title, count, duration_minutes, rng, compact=compact)
        ]

        recent_patterns: list[str] = []
        used_transitions: set[str] = set()
        used_phrases: set[str] = set()
        for index, tip in enumerate(chosen, start=1):
            sections.append(
                self._item(
                    index, count, tip, rng, recent_patterns, used_transitions, used_phrases
                )
            )

        sections.append(self._outro(count, rng, compact=compact))

        script = Script(
            title=title,
            topic=topic,
            sections=sections,
            engine=self.name,
            promise_key=promise.key,
            promise_label=promise.label,
            rejected_ideas=[
                {"title": r.tip["title"], "score": r.score, "reason": r.explain()}
                for r in rejected[:25]
            ],
            title_idea_alignment=alignment_ratio(chosen, promise),
        )
        self._fit_to_duration(script, duration_minutes, rng)
        log.info(
            "%s words across %d sections (%s engine); title promise '%s' "
            "satisfied by %.0f%% of the ideas",
            f"{script.word_count:,}",
            len(sections),
            self.name,
            promise.key,
            script.title_idea_alignment * 100,
        )
        return script

    # ------------------------------------------------------------------
    def _intro(
        self,
        topic: Topic,
        title: str,
        count: int,
        duration_minutes: float,
        rng: random.Random,
        compact: bool = False,
    ) -> ScriptSection:
        promise = detect_promise(topic.title, topic.angle)
        room = _room_word(topic.category)
        hooks = PROMISE_HOOKS.get(promise.key) or GENERAL_HOOKS
        parts = [rng.choice(hooks).format(room=room)]
        context = INTRO_CONTEXT.get(topic.category)
        if context and not compact:
            parts.append(context)
        minutes = max(1, int(round(duration_minutes)))
        promise = rng.choice(PROMISES).format(
            duration=minutes,
            minutes="minute" if minutes == 1 else "minutes",
            **count_words(count),
        )
        parts.append(promise)
        if not compact:
            parts.append(rng.choice(PROMISE_TAILS))
        return ScriptSection(kind="intro", heading="Introduction", text=_clean(" ".join(parts)))

    #: How an idea can be structured. Choosing between these is what stops
    #: every section following the identical sentence pattern.
    ITEM_PATTERNS = (
        ("statement", 26),   # idea -> why -> how
        ("question", 16),    # rhetorical question -> idea -> why -> how
        ("warning", 14),     # what goes wrong -> idea -> fix
        ("scenario", 14),    # before/after framing -> idea -> how
        ("how_first", 16),   # concrete instruction -> why it works
        ("bare", 14),        # idea -> why -> how with no lead-ins at all
    )

    @staticmethod
    def _pick_fresh(pool: Sequence[str], used: set[str], rng: random.Random) -> str:
        """Choose from a pool without repeating until it is exhausted.

        Long videos have many sections, and a phrase that shows up three times
        in twenty minutes is exactly what makes a script sound generated.
        """

        fresh = [item for item in pool if item not in used]
        if not fresh:
            used.difference_update(pool)      # exhausted; start the cycle again
            fresh = list(pool)
        choice = rng.choice(fresh)
        used.add(choice)
        return choice

    def _pick_pattern(self, rng: random.Random, recent: list[str]) -> str:
        """Weighted choice that never repeats the last two patterns."""

        options = [(name, w) for name, w in self.ITEM_PATTERNS if name not in recent[-2:]]
        if not options:
            options = list(self.ITEM_PATTERNS)
        total = sum(w for _, w in options)
        roll = rng.uniform(0, total)
        upto = 0.0
        for name, weight in options:
            upto += weight
            if roll <= upto:
                return name
        return options[-1][0]

    def _item(
        self,
        index: int,
        total: int,
        tip: Tip,
        rng: random.Random,
        recent_patterns: list[str] | None = None,
        used_transitions: set[str] | None = None,
        used_phrases: set[str] | None = None,
    ) -> ScriptSection:
        """Write one numbered idea, varying the structure from item to item."""

        recent_patterns = recent_patterns if recent_patterns is not None else []
        used_transitions = used_transitions if used_transitions is not None else set()
        used_phrases = used_phrases if used_phrases is not None else set()

        pattern = self._pick_pattern(rng, recent_patterns)
        recent_patterns.append(pattern)

        title = str(tip["title"]).rstrip(".")
        title_lower = title[0].lower() + title[1:]
        why = str(tip["why"])
        how = str(tip["how"])
        mistake = str(tip.get("mistake") or "")

        parts: list[str] = []

        # A transition, but never the same one twice in one video.
        if index > 1 and rng.random() < 0.4:
            fresh = [t for t in TRANSITIONS_V2 if t not in used_transitions]
            if fresh:
                transition = rng.choice(fresh)
                used_transitions.add(transition)
                parts.append(transition)

        # The number is announced most of the time, but not always - always
        # announcing it is a large part of what makes list videos feel robotic.
        if rng.random() < 0.78:
            parts.append(self._pick_fresh(NUMBER_FRAMES, used_phrases, rng).format(n=index))

        if pattern == "question":
            parts.append(self._pick_fresh(QUESTION_FRAMES, used_phrases, rng).format(title=title, title_lower=title_lower))
            parts.append(why)
            parts.append(how)
        elif pattern == "warning":
            if mistake:
                parts.append(mistake)
                parts.append(self._pick_fresh(WARNING_FRAMES, used_phrases, rng).format(title=title, title_lower=title_lower))
                parts.append(how)
                mistake = ""      # already used, do not repeat it below
            else:
                parts.append(self._pick_fresh(WARNING_FRAMES, used_phrases, rng).format(title=title, title_lower=title_lower))
                parts.append(why)
                parts.append(how)
        elif pattern == "scenario":
            parts.append(self._pick_fresh(SCENARIO_FRAMES, used_phrases, rng).format(title=title, title_lower=title_lower))
            parts.append(why)
            parts.append(how)
        elif pattern == "how_first":
            parts.append(f"{title}.")
            parts.append(how)
            parts.append(why)
        elif pattern == "bare":
            parts.append(f"{title}.")
            parts.append(why)
            parts.append(how)
        else:  # statement
            parts.append(self._pick_fresh(STATEMENT_FRAMES, used_phrases, rng).format(title=title, title_lower=title_lower))
            parts.append(why)
            parts.append(how)

        if mistake and rng.random() < 0.6:
            parts.append(mistake)
        elif rng.random() < 0.3:
            parts.append(self._pick_fresh(ITEM_CLOSERS, used_phrases, rng))

        heading = title
        if len(heading) > 64:
            heading = heading[:61].rstrip(" ,;:") + "..."
        return ScriptSection(
            kind="item",
            heading=f"{index}. {heading}",
            text=_clean(" ".join(p for p in parts if p)),
            index=index,
            tip=tip,
        )

    # ------------------------------------------------------------------
    def _elaborations_for(self, tip: Tip, rng: random.Random) -> list[str]:
        """Collect on-topic expansion sentences for a tip, best match first."""

        options: list[str] = []
        for tag in tip.get("tags", []):
            for key, sentences in ELABORATIONS.items():
                if key in str(tag).lower():
                    options.extend(sentences)
        category = str(tip.get("category", "")).lower()
        for key, sentences in ELABORATIONS.items():
            if key in category:
                options.extend(sentences)
        deduped = list(dict.fromkeys(options))
        rng.shuffle(deduped)
        generic = list(GENERIC_ELABORATIONS)
        rng.shuffle(generic)
        return deduped + generic

    def _fit_to_duration(
        self, script: Script, duration_minutes: float, rng: random.Random
    ) -> None:
        """Grow the script towards the requested duration with on-topic detail.

        Items are expanded round-robin so the extra material is spread evenly
        instead of bloating the first few ideas.
        """

        target_words = duration_minutes * self.words_per_minute
        items = script.items()
        if not items or script.word_count >= target_words * 0.95:
            return

        pools = {id(item): self._elaborations_for(item.tip or {}, rng) for item in items}
        usage: dict[str, int] = {}
        per_item: dict[int, set[str]] = {id(item): set() for item in items}
        added = 0
        max_reuse = 2

        for _round in range(6):
            if script.word_count >= target_words * 0.98:
                break
            for item in items:
                if script.word_count >= target_words * 0.98:
                    break
                candidates = [
                    sentence
                    for sentence in pools[id(item)]
                    if sentence not in per_item[id(item)]
                    and usage.get(sentence, 0) < max_reuse
                ]
                if not candidates:
                    continue
                # Least-used first keeps repeated sentences far apart.
                sentence = min(candidates, key=lambda s: usage.get(s, 0))
                usage[sentence] = usage.get(sentence, 0) + 1
                per_item[id(item)].add(sentence)
                item.text = _clean(f"{item.text} {sentence}")
                added += 1

        if added:
            log.debug("Expanded %d items to reach the target duration", added)
        shortfall = 1.0 - (script.word_count / target_words) if target_words else 0.0
        if shortfall > 0.15:
            log.warning(
                "Script is %.0f%% shorter than the %.0f minute target "
                "(not enough distinct material for this topic)",
                shortfall * 100,
                duration_minutes,
            )

    def _outro(self, count: int, rng: random.Random, compact: bool = False) -> ScriptSection:
        if compact:
            parts = [
                rng.choice(CONCLUSION_LEADS).format(**count_words(count)),
                rng.choice(CTAS),
            ]
        else:
            parts = [
                rng.choice(CONCLUSION_LEADS).format(**count_words(count)),
                rng.choice(CONCLUSION_BODIES),
                rng.choice(CTAS),
            ]
        return ScriptSection(kind="outro", heading="Final thoughts", text=_clean(" ".join(parts)))


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def generate_script(
    topic: Topic,
    duration_minutes: float,
    engine: str = "auto",
    words_per_minute: float = 150.0,
    llm_settings: dict[str, Any] | None = None,
    seed: int | None = None,
) -> Script:
    """Generate a script, preferring the requested engine but never crashing.

    ``engine`` may be ``template`` (always available), ``llm`` (local
    llama.cpp), or ``auto`` which uses the LLM only when it is enabled and
    ready, and silently falls back to the template engine otherwise.
    """

    template_engine = TemplateScriptEngine(words_per_minute=words_per_minute, seed=seed)
    settings = llm_settings or {}
    wants_llm = engine == "llm" or (engine == "auto" and bool(settings.get("enabled")))

    if wants_llm:
        try:
            from .llm import LLMScriptEngine, LLMUnavailable

            llm_engine = LLMScriptEngine(settings, words_per_minute=words_per_minute)
            script = llm_engine.generate(topic, duration_minutes, fallback=template_engine)
            return script
        except Exception as exc:  # pragma: no cover - depends on runner capability
            log.warning("Local LLM engine unavailable (%s); using the template engine", exc)

    return template_engine.generate(topic, duration_minutes)
