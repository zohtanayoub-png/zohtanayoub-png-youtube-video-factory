"""Title-promise validation.

A title is a promise. "25 Small Living Room Ideas That Make Any Space Look
Bigger" promises that every idea makes a room look bigger - not that every
idea is merely good interior design advice.

Before the script is written, each candidate idea is scored against the
promise the title makes. Ideas that do not directly support it are rejected
and replaced. Matching the coffee table height to the sofa seat is sound
advice and has nothing to do with perceived space, so it does not belong in a
"look bigger" video.

The scoring is deliberately transparent - keyword concepts and explicit
counter-signals - so a rejection can always be explained in the log and in the
editorial quality report.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

from .logging_utils import get_logger

log = get_logger("ALIGN")

Tip = dict[str, Any]


@dataclass(frozen=True)
class Mechanism:
    """One concrete way an idea can actually cause the promised outcome.

    ``because`` states the causal chain in plain narration. It is what
    :mod:`vidfactory.causal_alignment` writes into a paragraph that performs
    the action but never explains why it produces the result the title
    promised - "measure before you buy" is good advice and, on its own, not an
    explanation of why the room will look bigger.
    """

    name: str
    words: tuple[str, ...]
    because: str = ""
    #: Alternate phrasings. One mechanism can end up explaining six items in a
    #: twenty-five item video, and hearing the identical sentence six times is
    #: exactly the template-like writing this project is trying to avoid.
    also_because: tuple[str, ...] = ()

    @property
    def explanations(self) -> tuple[str, ...]:
        return tuple(x for x in (self.because, *self.also_because) if x)


@dataclass(frozen=True)
class Promise:
    """What a title commits every idea in the video to deliver."""

    key: str
    label: str
    #: Phrases in a title that mean the video is making this promise.
    title_signals: tuple[str, ...]
    #: Concept groups. An idea must touch at least ``required_groups`` of them.
    concepts: tuple[tuple[str, ...], ...]
    #: Signals that an idea is about something else entirely.
    counter_signals: tuple[str, ...] = ()
    required_groups: int = 1

    # ------------------------------------------------------------------
    # Direct-causation gate.
    #
    # Concept groups alone proved too permissive: the 60-30-10 color rule
    # matched "proportion" and "the eye" and so passed a "make the room look
    # bigger" title, even though nothing about it makes a room look bigger.
    #
    # ``mechanisms`` are the concrete ways an idea can actually cause the
    # promised outcome. When a promise defines any, an idea must match at
    # least one of them - supporting concepts on their own are not enough.
    # ------------------------------------------------------------------
    mechanisms: tuple[Mechanism, ...] = ()
    #: Generic design principles that do not, by themselves, cause the
    #: outcome. Matching one is disqualifying...
    deny_signals: tuple[str, ...] = ()
    #: ...unless the idea explicitly claims the outcome in its own words.
    rescue_signals: tuple[str, ...] = ()
    #: Subjects that can never deliver this promise, however the idea is
    #: written. Unlike ``deny_signals`` these are matched against the idea's
    #: title and tags only - its *primary* subject - and cannot be rescued.
    #:
    #: Run 16 put "Mix at least three materials in every room" into a video
    #: about making a small living room look bigger. It got in because its body
    #: mentions "one small reflective element", which matched the mirror
    #: mechanism, and a rescue sentence about reflection was enough to keep it.
    #: But the idea is a warmth-and-texture tip; no amount of secondary
    #: sentences make its primary mechanism a spatial one.
    subject_deny_signals: tuple[str, ...] = ()
    #: Which language this promise's vocabulary is written in.
    language: str = "en"

    def describe(self) -> str:
        return f"{self.label} ({self.key})"


#: Phrases that state a perceived-size outcome outright. An idea containing
#: one of these is explaining how it changes how big a room feels, which is
#: what rescues an otherwise generic principle.
SPACE_OUTCOMES: tuple[str, ...] = (
    "look bigger", "looks bigger", "feel bigger", "feels bigger",
    "look larger", "looks larger", "feel larger", "feels larger",
    "appear bigger", "appears bigger", "appear larger", "appears larger",
    "appear taller", "appears taller", "look taller", "looks taller",
    "reads as larger", "reads taller", "read as larger",
    "more spacious", "spacious", "expands", "expand the",
    "recede", "recedes", "receding",
    "shrink", "shrinks", "smaller than it", "feel smaller", "feels smaller",
    "cramped", "boxed in", "keeps going", "room keeps",
    "stretches", "stretch the", "perceived", "visually",
    "sense of space", "feeling of space", "square footage",
)

#: Subjects that are simply not spatial. An idea whose *title or tags* are
#: about one of these is a styling, warmth or material idea; it may be excellent
#: advice and it does not belong in a video promising a room will look bigger.
#: Matched against the idea's subject only, so a passing mention of texture in
#: the body of a genuine space trick is harmless.
#: Matched on whole words, so "Keep one continuous flooring material" - a
#: genuine space trick - is not caught by the plural "materials" that marks a
#: texture-mixing tip.
NON_SPATIAL_SUBJECTS: tuple[str, ...] = (
    "texture", "textures", "materials", "tactile",
    "warmth", "cozy", "cosy", "scent", "sound", "acoustic",
    "metal finish", "metals", "colour rule", "color rule",
    "palette", "color formula", "colour formula", "seasonal",
    "personality", "sentimental",
)


#: Generic colour-theory and styling principles. Useful advice, but they do
#: not by themselves change how large a room reads.
GENERIC_DESIGN_PRINCIPLES: tuple[str, ...] = (
    "sixty thirty ten", "60 30 10", "sixty percent walls",
    "dominant tone", "supporting tone", "accent color", "accent colour",
    "color rule", "colour rule", "color palette", "colour palette",
    "three colors", "three colours", "undertone", "color scheme",
    "colour scheme", "saturated color", "repeat each accent",
    "pull your palette", "color story",
)

#: Ordered by specificity - the first title signal that matches wins.
PROMISES: tuple[Promise, ...] = (
    Promise(
        key="bigger",
        label="make the space look or feel bigger",
        title_signals=(
            "look bigger", "feel bigger", "look larger", "feel larger",
            "appear bigger", "space look bigger", "maximize space",
            "look more spacious", "feel more spacious", "make any space",
        ),
        # The concrete ways a room can actually be made to read as larger.
        # Anything that matches none of these is not a space trick, however
        # good the advice is.
        mechanisms=(
            Mechanism(
                "vertical_emphasis",
                ("ceiling", "taller", "height", "vertical", "upward", "floor to ceiling",
                 "high on the wall", "up to the ceiling", "full height"),
                "Carrying the eye upward makes the walls read taller, and taller "
                "walls make the whole room feel bigger than its floor area says "
                "it is.",
                also_because=(
                    "Your eye follows the tallest line in a room, so carrying that line all "
                "the way up makes the ceiling read higher and the room feel bigger.",
                    "Height is the one dimension a small room usually has to spare, and "
                "using it makes the space feel larger without moving a wall.",
                ),
            ),
            Mechanism(
                "clear_sightlines",
                ("interrupts the view", "view across", "route through", "runs straight to", "sightline", "sight line", "continuous", "uninterrupted", "unobstructed",
                 "flow", "walkway", "pathway", "circulation", "clear path", "keeps going"),
                "An uninterrupted line of sight lets your eye travel all the way to "
                "the far wall without stopping, and a room the eye can cross in one "
                "go reads as larger than one it has to pick its way across.",
                also_because=(
                    "When nothing interrupts the view across a room, your eye runs straight "
                "to the far wall, so the space reads as larger than its floor plan.",
                    "A clear route through a room lets the eye finish the journey in one "
                "go, which makes even a narrow space feel bigger.",
                ),
            ),
            # ------------------------------------------------------------------
            # Two different things that both used to be called "scale".
            #
            # A large mirror, artwork or lamp and an oversized sofa do opposite
            # things to a small room, and run 16 shipped the sofa explanation
            # under the artwork advice because one mechanism owned both. They
            # are separate families now and neither one's sentences are
            # available to the other.
            # ------------------------------------------------------------------
            Mechanism(
                "statement_piece_scale",
                ("single generous", "a wall of small", "settle on", "statement piece", "one bigger", "bigger thing", "one large",
                 "larger piece", "larger pieces", "fewer, larger", "fewer larger",
                 "one oversized", "one big", "large artwork", "artwork",
                 "substantial", "focal point", "single large"),
                "A dozen small objects give the eye a dozen things to process, so "
                "swapping them for one substantial piece cuts the visual clutter "
                "and the room reads as calmer and more spacious.",
                also_because=(
                    "One piece the eye can settle on beats a wall of small ones it has to "
                "count, which is why a single generous object makes a room feel "
                "more spacious rather than busier.",
                    "Fewer, larger objects break the room into fewer pieces, so the space "
                "reads as one calm whole and feels bigger for it.",
                ),
            ),
            Mechanism(
                "wall_art_scale",
                ("art", "artwork", "print", "canvas", "gallery wall", "framed",
                 "picture", "poster", "wall art"),
                # Art has its own reason for making a wall read larger, and it
                # is not the curtain one. Run 22 explained a picture with a
                # sentence about uncovered glass because both mechanisms are
                # called vertical_emphasis.
                "Artwork scaled to the furniture beneath it anchors the wall "
                "instead of floating on it, so the eye reads one composed "
                "surface and the room feels larger and more deliberate.",
                also_because=(
                    "A picture too small for its wall leaves the surface looking "
                "fragmented and half-finished, while one sized to the furniture "
                "below pulls the whole wall together and the room reads as more "
                "spacious.",
                    "Hanging art so it relates to what sits under it gives the wall a "
                "single centre of gravity, which makes the space feel calmer and "
                "more spacious than a scatter of small frames.",
                ),
            ),
            Mechanism(
                "furniture_footprint_scale",
                # "undersized" and "too small" are deliberately absent: they
                # describe whatever object is undersized, which is usually the
                # rug, and claiming them here made the sofa mechanism outrank
                # the rug mechanism on rug advice.
                ("oversized sofa", "oversized furniture", "too big for the room",
                 "footprint", "visual weight", "bulky", "measure", "measurement",
                 "dimensions", "tape measure", "seat depth", "deep sofa"),
                # Cautionary: this family is about the mistake, so its sentences
                # blame the oversized piece. The contradiction check keeps them
                # away from advice that recommends going larger.
                "Oversized furniture eats visible floor area and narrows the walking "
                "paths, so a small room feels cramped even though its footprint "
                "never changed.",
                also_because=(
                    "A sofa that is too big for the room steals the floor around it, so "
                "what is left over feels cramped even though nothing else changed.",
                    "Getting the scale right leaves room to walk and room to look, which "
                "makes a small space read as larger than it measures.",
                ),
            ),
            Mechanism(
                "rug_scale",
                ("rug", "carpet", "area rug"),
                # A rug is not furniture and not a statement piece: the failure
                # mode is a rug too small to reach the seating, so the sentences
                # blame the undersized one and argue for the generous one.
                "A rug too small to reach the furniture leaves the seating floating "
                "in separate pieces, so one large enough to catch the front legs "
                "pulls the group into a single zone and the floor reads as more "
                "spacious.",
                also_because=(
                    "An undersized rug cuts the floor into a small island surrounded by "
                "leftovers, while a generously sized one lets the whole floor read "
                "as one surface and the room feel bigger.",
                    "When the rug reaches under the seats, the eye reads one connected "
                "area instead of scattered furniture, which makes the space feel "
                "larger than it measures.",
                ),
            ),
            Mechanism(
                "less_clutter",
                ("object on a surface", "clearing them", "fewer things", "clutter", "declutter", "negative space", "clear surfaces",
                 "surfaces stay clear", "empty", "edited", "remove"),
                "Clear surfaces give the eye somewhere to rest, and a room with "
                "fewer things competing for attention reads as more spacious.",
                also_because=(
                    "Every object on a surface is one more thing the eye has to process, so "
                "clearing them makes the room feel more spacious straight away.",
                    "Empty surface is what the eye reads as space, so leaving some makes the "
                "room feel bigger without removing a single piece of furniture.",
                ),
            ),
            Mechanism(
                "visible_floor",
                ("visible floor", "floor you can see", "floor visible", "square foot of floor", "off the ground", "visible legs", "slim legs", "raised on", "floats", "floating",
                 "wall-mount", "wall mounted", "floor continue", "see floor",
                 "sits flat on the ground"),
                "Every square foot of floor you can actually see is square footage "
                "your eye counts, so keeping the floor visible under and around "
                "furniture makes the room feel larger.",
                also_because=(
                    "Floor you can see is floor the eye counts, so lifting furniture off the "
                "ground makes the room read as larger.",
                    "A continuous run of visible floor tells the eye how deep the room goes, "
                "which makes the space feel bigger than a floor broken up by solid "
                "bases.",
                ),
            ),
            Mechanism(
                "mirrors_and_reflection",
                ("mirror", "reflect", "reflection", "glazed", "glass"),
                "A reflection adds depth your eye reads as real, so the far wall stops "
                "behaving like the end of the room and the space feels bigger "
                "than it measures.",
                also_because=(
                    "A mirror gives the eye somewhere further to look, so the room stops "
                "ending at the wall and feels bigger.",
                    "Reflected light and reflected depth both read as real space, which "
                "makes a small room feel larger than its walls allow.",
                ),
            ),
            Mechanism(
                "light_distribution",
                ("light reaching", "light on the walls", "boundaries of the room", "walls and corners", "natural light", "daylight", "sunlight", "bright", "pale",
                 "light colour", "light color", "airy", "window", "perimeter light",
                 "wash the walls", "lamp", "sconce", "lighting", "ceiling light",
                 "overhead light", "downlight", "light fitting", "light source",
                 "single fitting"),
                "Light reaching the walls and corners shows your eye exactly where "
                "the room ends, and a room whose boundaries are visible reads as "
                "larger than one that fades into shadow a few feet in.",
                also_because=(
                    "A room lit only in the middle fades out at the edges, so lighting the "
                "perimeter shows the eye where the walls are and the space reads as "
                "larger.",
                    "Light on the walls makes the boundaries of the room visible, which "
                "makes the whole space feel bigger than a single pool of light in "
                "the centre.",
                ),
            ),
            Mechanism(
                "window_geometry",
                ("the fabric high", "fabric hung", "the track", "the glass",
                 "beyond the frame", "the window frame", "curtain", "drape", "rod", "panel", "blind"),
                "Hanging the fabric high and wide leaves the glass itself "
                "uncovered, so more daylight reaches the room and the wall reads "
                "taller than it measures.",
                also_because=(
                    "Fabric hung above and beyond the frame leaves the glass clear, so more "
                "daylight gets in and the wall reads taller.",
                    "Mounting the track close to the ceiling stretches the window upward, "
                "which makes the wall read as taller and the room feel bigger.",
                ),
            ),
            Mechanism(
                "furniture_placement",
                ("against the wall", "push", "float the sofa", "placement",
                 "arrangement", "layout", "perimeter"),
                "A deliberate arrangement opens up the routes you walk, so clear "
                "pathways make a small room feel bigger to move through.",
                also_because=(
                    "Where the furniture sits decides where you can walk, so an arrangement "
                "that keeps the routes clear makes a small room feel bigger.",
                    "Pushing everything to the perimeter is not always the answer, but an "
                "arrangement that leaves the paths open reads as more spacious.",
                ),
            ),
            Mechanism(
                "continuous_flooring",
                ("the floor into", "floor running", "different finishes", "flooring", "same floor", "one continuous", "floor finish"),
                "One continuous floor finish stops the eye counting separate small "
                "zones, so the whole space reads as larger than a floor broken "
                "into sections.",
                also_because=(
                    "Breaking the floor into different finishes tells the eye it is looking "
                "at several small areas, so keeping it continuous makes the space "
                "read as larger.",
                    "One floor running through the whole room gives the eye nothing to "
                "divide, which makes the space feel bigger than the same area cut "
                "into zones.",
                ),
            ),
            Mechanism(
                "low_contrast_edges",
                ("chop", "chops", "fragment", "break up", "outline", "hard edge",
                 "edges", "same color as the walls", "same colour as the walls",
                 "low-contrast", "low contrast"),
                "Low-contrast edges stop chopping the wall into pieces, so the surface "
                "reads as one large plane and the room feels bigger for it.",
                also_because=(
                    "Strong outlines chop a wall into pieces, so matching the tones lets the "
                "surface read as one large plane and the room feel bigger.",
                    "When the trim disappears into the wall, the eye stops counting edges "
                "and the room reads as larger.",
                ),
            ),
            Mechanism(
                "vertical_storage",
                ("storage that stops", "height for storage", "carrying it to the ceiling", "vertical storage", "up to the ceiling", "storage to the ceiling"),
                "Taking storage up to the ceiling uses the height instead of the floor, "
                "so the same belongings leave more visible floor behind and the "
                "room feels more spacious.",
                also_because=(
                    "Storage that stops at waist height wastes the wall above it, so "
                "carrying it to the ceiling leaves more visible floor and the room "
                "feels bigger.",
                    "Using the height for storage keeps the floor free, which makes a small "
                "room feel considerably more spacious.",
                ),
            ),
        ),
        # Supporting evidence, counted only once a mechanism is present.
        concepts=(
            ("ceiling", "tall", "taller", "height", "vertical", "upward", "high"),
            ("mirror", "reflect", "reflection", "glass", "transparent"),
            ("light", "daylight", "bright", "sunlight", "window", "pale", "airy"),
            ("legs", "floor", "visible floor", "float", "raised", "wall mount"),
            ("scale", "oversized", "larger", "fewer", "bigger", "proportion"),
            ("clutter", "declutter", "surfaces", "empty", "negative space", "edited"),
            ("sightline", "continuous", "flow", "uninterrupted", "open", "path"),
            ("contrast", "outline", "edges", "recede", "same color", "low-contrast"),
            ("storage", "vertical storage", "hidden", "conceal"),
            ("visual weight", "heavy", "heavier", "lighter", "weight", "bulky",
             "reads as", "the eye", "your brain", "perceived"),
        ),
        required_groups=1,
        deny_signals=GENERIC_DESIGN_PRINCIPLES,
        rescue_signals=SPACE_OUTCOMES,
        subject_deny_signals=NON_SPATIAL_SUBJECTS,
        counter_signals=(
            "conversation", "comfort", "cozy", "scent", "sound", "acoustic",
            "seasonal", "maintenance", "regrout", "towel", "water pressure",
            "shower head", "reach", "arm's reach", "within reach",
        ),
    ),
    Promise(
        key="expensive",
        label="make the home look more expensive",
        title_signals=(
            "look more expensive", "look expensive", "high end", "luxury",
            "look cheap", "make a space look cheap", "designer",
        ),
        mechanisms=(
            Mechanism("materials",
                      ("material", "stone", "marble", "brass", "solid wood", "leather",
                       "wool", "linen", "oak", "walnut"),
                      "Real materials age instead of wearing out, and that is the "
                      "difference the eye reads as expensive."),
            Mechanism("finishes",
                      ("finish", "matte", "honed", "gloss", "sheen", "brushed", "polished"),
                      "A considered finish catches light the way costly surfaces do, "
                      "so the whole piece reads as more expensive."),
            Mechanism("hardware",
                      ("hardware", "handle", "lever", "knob", "tap", "faucet", "switch plate"),
                      "Hardware is what your hand touches, so upgrading it changes "
                      "how expensive the room feels every single day."),
            Mechanism("generous_scale",
                      ("oversized", "generous", "fuller", "larger", "wider", "scale"),
                      "Generous proportions read as chosen for the room rather than "
                      "chosen to a price, which makes the whole arrangement look "
                      "more expensive."),
            Mechanism("layered_light",
                      ("dimmer", "sconce", "layered", "warm light", "lamp", "picture light"),
                      "Layered, dimmable light models the room the way a showroom "
                      "does, which is most of what makes a space look expensive."),
            Mechanism("architectural_detail",
                      ("moulding", "molding", "panelling", "paneling", "skirting",
                       "architectural", "trim", "detail", "junction", "mitred", "edge"),
                      "Crisp architectural detail is the mark of work that was "
                      "finished properly, and that is what reads as high end."),
            Mechanism("concealment",
                      ("cable", "cables", "wiring", "conceal", "hidden", "tidy", "plastic"),
                      "Visible cables and plastic are what make an otherwise good "
                      "room look cheap, so hiding them lifts everything around them."),
            Mechanism("upholstery",
                      ("upholster", "upholstery", "headboard", "padded", "velvet"),
                      "Upholstery adds the depth and weight cheap furniture is missing, so "
                      "the piece reads as far more expensive than it cost."),
            Mechanism("framing",
                      ("frame", "framed", "mount", "gallery", "artwork"),
                      "Proper framing and mounting turn an ordinary print into something "
                      "that looks bought from a gallery, which makes cheap art "
                      "read as considered."),
            Mechanism("greenery",
                      ("flowers", "branches", "greenery", "plant"),
                      "Fresh greenery is the cheapest thing in the room and the one "
                      "that most reliably reads as expensive."),
            Mechanism("window_dressing",
                      ("curtain", "drape", "panel", "hem"),
                      "Curtains that break at the floor look made to measure, so the whole "
                      "window reads as custom rather than cheap."),
            Mechanism("restraint",
                      ("empty", "clear", "editing", "restraint", "remove"),
                      "Editing leaves the good pieces room to be seen, which is why "
                      "restraint reads as expensive."),
        ),
        deny_signals=("acoustic", "water pressure", "scent"),
        rescue_signals=(
            "expensive", "high end", "luxury", "cheap", "designed",
            "considered", "custom", "bespoke", "showroom",
        ),
        concepts=(
            ("material", "stone", "marble", "brass", "solid wood", "leather", "wool", "linen"),
            ("finish", "matte", "honed", "gloss", "sheen", "hardware", "handle", "trim"),
            ("scale", "oversized", "generous", "larger", "full", "fuller"),
            ("light", "lighting", "lamp", "sconce", "dimmer", "warm", "layered"),
            ("detail", "edge", "junction", "moulding", "panelling", "architectural"),
            ("cable", "clutter", "plastic", "tidy", "conceal", "hidden"),
            ("curtain", "drapery", "fabric", "upholster", "upholstery"),
            ("art", "frame", "mount", "gallery"),
            ("flowers", "greenery", "plant", "branches"),
        ),
        counter_signals=("acoustic", "sound", "scent", "seasonal", "quota"),
    ),
    Promise(
        key="cozy",
        label="make the home feel warmer and cozier",
        title_signals=("cozy", "cosy", "warmer home", "feel warmer", "inviting"),
        mechanisms=(
            Mechanism("warm_low_light",
                      ("warm", "glow", "evening", "low light", "lamp", "candle", "dimmer",
                       "kelvin", "2700", "2200"),
                      "Warm light low in the room reads as evening, and evening is "
                      "what your body understands as cozy."),
            Mechanism("soft_texture",
                      ("soft", "wool", "throw", "cushion", "sheepskin", "linen", "boucle",
                       "upholster", "texture", "tactile"),
                      "Soft texture invites touch, and that makes a room feel warm rather "
                      "than merely furnished."),
            Mechanism("natural_material",
                      ("wood", "timber", "oak", "natural material", "honey", "amber"),
                      "Natural materials carry warmth in their colour, so they make "
                      "the whole room feel less clinical."),
            Mechanism("enclosure",
                      ("enclos", "nook", "corner", "intimate", "lower", "ceiling",
                       "at your back", "window seat"),
                      "Something solid at your back is what makes a seat feel safe, "
                      "and a seat that feels safe feels cozy."),
            Mechanism("acoustics",
                      ("acoustic", "sound", "absorb", "echo", "rug", "curtain", "books"),
                      "Soft surfaces absorb the echo, so a quiet room feels warm in a way "
                      "a bright one that rings never does."),
            Mechanism("personal_traces",
                      ("scent", "senses", "lived in", "personal", "candle"),
                      "Signs of being lived in are what separate a home from a "
                      "showroom, and that is most of what cozy means."),
        ),
        deny_signals=("resale", "declutter quota", "sixty thirty ten"),
        rescue_signals=("cozy", "cosy", "warm", "inviting", "relax", "comfortable"),
        concepts=(
            ("warm", "warmth", "glow", "evening", "low light", "lamp", "candle", "dimmer"),
            ("soft", "texture", "wool", "throw", "cushion", "sheepskin", "linen", "upholster"),
            ("wood", "natural", "material", "tactile"),
            ("enclos", "nook", "corner", "intimate", "ceiling", "lower"),
            ("acoustic", "sound", "absorb", "rug", "curtain", "books"),
            ("scent", "senses", "lived in", "personal"),
        ),
        counter_signals=("declutter quota", "resale"),
    ),
    Promise(
        key="storage",
        label="add storage or reduce clutter",
        title_signals=("storage", "organiz", "organis", "declutter", "clutter"),
        concepts=(
            ("storage", "store", "stored", "storing"),
            ("shelf", "shelving", "cabinet", "cupboard", "drawer", "wardrobe", "closet"),
            ("basket", "box", "container", "bin", "label"),
            ("hidden", "conceal", "under bed", "ottoman", "bench", "hook", "rail"),
            ("vertical", "ceiling", "above", "door", "wall"),
            ("clutter", "declutter", "tidy", "system", "sort", "outbox"),
        ),
        counter_signals=("paint color", "curtain length", "scent"),
    ),
    Promise(
        key="mistakes",
        label="identify a mistake worth fixing",
        title_signals=("mistake", "avoid", "never break", "designers never", "wrong"),
        # Almost any idea can be framed as a mistake, so the bar is a concrete,
        # correctable, physical decision rather than a vague principle.
        concepts=(
            ("too small", "too high", "too low", "too far", "wrong", "avoid", "mistake"),
            ("instead", "rather than", "should", "never", "stop"),
            ("size", "scale", "height", "proportion", "placement", "position"),
            ("light", "color", "rug", "curtain", "art", "furniture", "storage"),
        ),
    ),
    Promise(
        key="budget",
        label="deliver the result on a small budget",
        title_signals=("budget", "affordable", "cheap", "under", "for less", "on a small budget"),
        concepts=(
            ("budget", "cost", "cheap", "affordable", "inexpensive", "free", "spend"),
            ("secondhand", "vintage", "diy", "paint", "swap", "replace", "upgrade"),
            ("dollars", "price", "value", "worth"),
            ("already own", "shop your own", "rearrange", "move", "clean", "repair"),
        ),
        counter_signals=("bespoke", "custom joinery"),
    ),
    Promise(
        key="timeless",
        label="stay in style for years",
        title_signals=("timeless", "never go out of style", "classic", "always"),
        concepts=(
            ("timeless", "classic", "age", "ages", "aging", "decade", "years", "lasting"),
            ("neutral", "plain", "simple", "restraint", "understated"),
            ("material", "solid wood", "stone", "leather", "wool", "brass", "patina"),
            ("trend", "dated", "era", "cycle", "fashion"),
            ("proportion", "architecture", "light", "flow"),
        ),
        counter_signals=("trend of the year", "seasonal"),
    ),
    Promise(
        key="renter",
        label="work in a rental without permanent changes",
        title_signals=("rental", "renter", "without drilling", "landlord", "temporary"),
        concepts=(
            ("rent", "rental", "renter", "landlord", "deposit", "move"),
            ("removable", "temporary", "reversible", "no drill", "tension", "adhesive", "peel"),
            ("freestanding", "portable", "leaning", "swap", "store the original"),
        ),
        counter_signals=("built in", "knock through", "replace the floor"),
    ),
    Promise(
        key="brighter",
        label="bring more light into the room",
        title_signals=("brighter", "more light", "lighting", "dark room", "light up"),
        mechanisms=(
            Mechanism("more_light_sources",
                      ("light source", "lamp", "bulb", "sconce", "pendant", "dimmer",
                       "fixture", "uplight", "led"),
                      "More separate light sources fill the gaps one ceiling fitting "
                      "leaves, so the room is brighter everywhere rather than under "
                      "one spot."),
            Mechanism("daylight",
                      ("daylight", "window", "sunlight", "natural light", "glass"),
                      "Anything that lets more daylight in raises the light level of "
                      "the whole room for free."),
            Mechanism("reflection",
                      ("mirror", "reflect", "reflection", "gloss", "sheen"),
                      "Reflective surfaces bounce the light you already have back into the "
                      "room, so the same fittings leave the space noticeably "
                      "brighter."),
            Mechanism("pale_surfaces",
                      ("pale", "light colour", "light color", "white", "bright"),
                      "Pale surfaces reflect far more of the light that hits them, "
                      "so the same bulbs go further."),
            Mechanism("colour_temperature",
                      ("kelvin", "warm white", "colour temperature", "color temperature",
                       "layer", "layered", "shade", "diffuse"),
                      "Getting the colour temperature and the shade right stops the "
                      "light being swallowed before it reaches the room."),
            Mechanism("unobstructed_windows",
                      ("curtain", "blind", "clear the sill", "unobstructed",
                       "clearing the window"),
                      "Clearing the window itself is the single largest change you can "
                      "make, so the room receives far more daylight and stops "
                      "feeling dark by mid-afternoon."),
        ),
        deny_signals=GENERIC_DESIGN_PRINCIPLES,
        rescue_signals=("bright", "brighter", "light", "dark", "gloomy", "dim"),
        concepts=(
            ("light", "lighting", "lamp", "bulb", "sconce", "pendant", "dimmer"),
            ("daylight", "window", "sunlight", "natural light", "curtain"),
            ("mirror", "reflect", "pale", "bright", "white", "gloss"),
            ("layer", "warm", "kelvin", "shade", "glow"),
        ),
    ),
)

#: When a title makes no specific promise, every idea in the category is fair
#: game and the stage passes everything through.
GENERAL = Promise(
    key="general",
    label="useful ideas for this room or topic",
    title_signals=(),
    concepts=(),
    required_groups=0,
)


def detect_promise(title: str, angle: str = "", language: str = "en") -> Promise:
    """Work out what a title actually commits the video to.

    The promise carries its own language's vocabulary, so everything
    downstream - the idea filter, the causal check on the written paragraph,
    the repair sentences - works in whatever language the script is written
    in without any of them testing a locale code.
    """

    from .languages import resolve_language

    resolved = resolve_language(language)
    catalogue = PROMISES if resolved.is_english else PROMISES_ES
    general = GENERAL if resolved.is_english else GENERAL_ES

    # Spanish keeps its accents: stripping them would break "salón" and "más".
    text = f" {re.sub(r'[^a-záéíóúüñ ]+', ' ', str(title or '').lower())} "
    for promise in catalogue:
        for signal in promise.title_signals:
            if signal in text:
                return promise
    # The topic engine's angle is a weaker second opinion.
    angle_map = {
        "space": "bigger",
        "expensive": "expensive",
        "cozy": "cozy",
        "storage": "storage",
        "mistakes": "mistakes",
        "budget": "budget",
        "timeless": "timeless",
    }
    key = angle_map.get(str(angle or "").lower())
    if key:
        for promise in catalogue:
            if promise.key == key:
                return promise
    return general


def _tip_text(tip: Tip) -> str:
    """All the text that describes an idea, including its visual queries.

    The queries are hand-written descriptions of what the idea looks like
    ("airy small living space"), so they carry real signal about what the idea
    is for and are included deliberately.
    """

    parts = [
        str(tip.get("title", "")),
        str(tip.get("why", "")),
        str(tip.get("how", "")),
        str(tip.get("mistake", "")),
        " ".join(str(t) for t in tip.get("tags", [])),
        " ".join(str(q) for q in tip.get("queries", [])),
    ]
    return " ".join(parts).lower()


def _tip_subject(tip: Tip) -> str:
    """What the idea is *primarily* about: its title and its tags.

    Deliberately not the body. An idea's ``why`` and ``how`` mention whatever
    they need to, and judging the subject by them is how a texture tip that
    happens to name a brass lamp ends up counting as a lighting idea.
    """

    return " ".join(
        [str(tip.get("title", "")), " ".join(str(t) for t in tip.get("tags", []))]
    ).lower()


#: An idea must clear this to be considered "supports the title promise".
DEFAULT_THRESHOLD = 0.5


@dataclass
class AlignmentResult:
    tip: Tip
    score: float
    matched_groups: list[str] = field(default_factory=list)
    counters: list[str] = field(default_factory=list)
    #: Names of the direct causal mechanism(s) by which this idea delivers
    #: the promise, e.g. ``furniture_footprint_scale``.
    mechanisms: list[str] = field(default_factory=list)
    #: The exact words that matched, for the log and the report.
    mechanism_words: list[str] = field(default_factory=list)
    #: Generic-principle signals that disqualified it, if any.
    denied_by: list[str] = field(default_factory=list)

    def is_aligned(self, threshold: float = DEFAULT_THRESHOLD) -> bool:
        return self.score >= threshold

    @property
    def aligned(self) -> bool:
        return self.is_aligned()

    def explain(self) -> str:
        if self.denied_by:
            return (
                "generic design principle ("
                + ", ".join(self.denied_by[:2])
                + ") with no stated effect on the promised outcome"
            )
        if self.mechanisms:
            reason = "mechanism: " + ", ".join(self.mechanisms[:3])
        elif self.matched_groups:
            reason = (
                "no direct mechanism; only loosely related via "
                + ", ".join(self.matched_groups[:3])
            )
        else:
            reason = "no supporting concept"
        if self.counters:
            reason += "; about " + ", ".join(self.counters[:3]) + " instead"
        return reason


def _hits(text: str, phrases: Sequence[str]) -> list[str]:
    return [p for p in phrases if p in text]


def _word_hits(text: str, phrases: Sequence[str]) -> list[str]:
    """Whole-word matches only.

    Substring matching is right for the body of an idea, where "reflective"
    should count as reflection. It is wrong for the subject, where "material"
    inside "flooring material" would disqualify a continuous-flooring tip.
    """

    return [
        p for p in phrases
        if p.strip() and re.search(rf"\b{re.escape(p.strip())}\b", text)
    ]


def score_alignment(tip: Tip, promise: Promise) -> AlignmentResult:
    """How strongly one idea supports the promise a title makes (0.0 - 1.0).

    Where a promise defines ``mechanisms``, the idea must contain at least one
    of them: a direct causal route from the idea to the promised outcome.
    Loose topical overlap is deliberately not enough, because that is what let
    the 60-30-10 colour rule into a video about making a room look bigger.
    """

    if promise.key == GENERAL.key or not (promise.concepts or promise.mechanisms):
        return AlignmentResult(tip=tip, score=1.0)

    text = _tip_text(tip)

    # An explicit override on the tip always wins over keyword inference.
    declared = {str(p).lower() for p in tip.get("promises", [])}
    if promise.key in declared:
        return AlignmentResult(tip=tip, score=1.0, mechanisms=["declared"])
    if declared and promise.key not in declared:
        return AlignmentResult(tip=tip, score=0.0, counters=["declared elsewhere"])

    counters = _hits(text, promise.counter_signals)

    # 0. Some subjects simply cannot deliver some promises. This is checked
    #    against the idea's title and tags, and there is no rescue: an idea
    #    about mixing textures is a texture idea even if a sentence in it
    #    mentions reflection.
    off_subject = _word_hits(_tip_subject(tip), promise.subject_deny_signals)
    if off_subject:
        return AlignmentResult(
            tip=tip, score=0.0, counters=counters, denied_by=off_subject
        )

    # 1. Generic design principles are rejected unless the idea itself
    #    explains that it produces the promised outcome.
    denied = _hits(text, promise.deny_signals)
    if denied:
        rescued = _hits(text, promise.rescue_signals)
        if not rescued:
            return AlignmentResult(
                tip=tip, score=0.0, counters=counters, denied_by=denied
            )

    # 2. Direct-causation gate.
    mechanisms: list[str] = []
    mechanism_words: list[str] = []
    if promise.mechanisms:
        for family in promise.mechanisms:
            hit = next((word for word in family.words if word in text), None)
            if hit:
                mechanisms.append(family.name)
                mechanism_words.append(hit)
        if not mechanisms:
            return AlignmentResult(tip=tip, score=0.0, counters=counters)

    # 3. Supporting concepts refine the score once causation is established.
    matched: list[str] = []
    for group in promise.concepts:
        hit = next((word for word in group if word in text), None)
        if hit:
            matched.append(hit)

    if len(matched) < max(1, promise.required_groups):
        return AlignmentResult(
            tip=tip, score=0.0, matched_groups=matched,
            counters=counters, mechanisms=mechanisms,
            mechanism_words=mechanism_words,
        )

    if promise.mechanisms:
        # Causation established: score on how many independent mechanisms and
        # supporting concepts back it up.
        strength = min(1.0, 0.42 + 0.16 * len(mechanisms) + 0.06 * len(matched))
    else:
        # Promises without a mechanism list keep the older concept-count rule.
        strength = min(1.0, 0.18 + 0.26 * len(matched))

    score = max(0.0, strength - 0.3 * len(counters))
    return AlignmentResult(
        tip=tip,
        score=round(score, 3),
        matched_groups=matched,
        counters=counters,
        mechanisms=mechanisms,
        mechanism_words=mechanism_words,
    )


def filter_aligned(
    tips: Sequence[Tip],
    promise: Promise,
    threshold: float = DEFAULT_THRESHOLD,
    minimum: int = 3,
) -> tuple[list[Tip], list[AlignmentResult]]:
    """Keep only ideas that support the promise; report the ones dropped.

    If filtering leaves too little material to build a video, the threshold is
    relaxed once - a short honest video beats a crash - and the relaxation is
    logged rather than hidden.
    """

    scored = [score_alignment(tip, promise) for tip in tips]
    kept = [r for r in scored if r.score >= threshold]
    rejected = [r for r in scored if r.score < threshold]

    if len(kept) < minimum:
        relaxed = sorted(scored, key=lambda r: r.score, reverse=True)[:minimum]
        if relaxed and relaxed[0].score > 0:
            log.warning(
                "Only %d of %d ideas clearly support '%s'; relaxing the "
                "threshold to keep the video viable",
                len(kept),
                len(scored),
                promise.label,
            )
            kept = relaxed
            rejected = [r for r in scored if r not in kept]

    kept.sort(key=lambda r: r.score, reverse=True)
    return [r.tip for r in kept], rejected


def alignment_ratio(
    tips: Sequence[Tip], promise: Promise, threshold: float = DEFAULT_THRESHOLD
) -> float:
    """Share of the chosen ideas that actually support the title."""

    if not tips:
        return 0.0
    hits = sum(1 for tip in tips if score_alignment(tip, promise).score >= threshold)
    return round(hits / len(tips), 3)


def mechanisms_for(promise: Promise, text: str) -> list[Mechanism]:
    """Every mechanism family a piece of text touches, in declaration order."""

    haystack = str(text or "").lower()
    return [
        family
        for family in promise.mechanisms
        if any(word in haystack for word in family.words)
    ]


def rank_mechanisms(promise: Promise, text: str) -> list[Mechanism]:
    """Mechanisms a text touches, most specifically matched first.

    Declaration order is the wrong order for repairing a paragraph: "do not
    center the ceiling light" matches ``vertical_emphasis`` on the bare word
    "ceiling" and ``light_distribution`` on the whole phrase "ceiling light",
    and the second is the mechanism the idea is actually about.
    """

    haystack = str(text or "").lower()
    scored: list[tuple[int, int, int, int, Mechanism]] = []
    for position, family in enumerate(promise.mechanisms):
        matched = [word for word in family.words if word in haystack]
        if not matched:
            continue
        # How often the subject actually comes up, not just whether it does.
        # Rug advice says "rug" four times and "floats" once; ranking on the
        # longest matched word alone made a passing mention of floating
        # furniture outrank the thing the paragraph is about.
        occurrences = sum(haystack.count(word) for word in matched)
        scored.append(
            (occurrences, len(matched), max(len(w) for w in matched), -position, family)
        )
    scored.sort(key=lambda item: item[:4], reverse=True)
    return [family for *_, family in scored]


def mechanism_by_name(promise: Promise, name: str) -> Mechanism | None:
    for family in promise.mechanisms:
        if family.name == name:
            return family
    return None


# ---------------------------------------------------------------------------
# Spanish promises
#
# Written in Spanish rather than translated from the English table above,
# because the vocabulary that signals a mechanism is idiomatic: "se lee más
# alta", "se come el paso", "queda despejado". A word-for-word translation of
# the English keyword list would match almost nothing in a natural Spanish
# script.
# ---------------------------------------------------------------------------

#: Frases que declaran directamente un resultado de espacio percibido.
SPACE_OUTCOMES_ES: tuple[str, ...] = (
    "parece más grande", "parezca más grande", "parecer más grande",
    "se ve más grande", "se vea más grande", "se lee como más grande",
    "más grande de lo que", "más pequeño de lo que", "más pequeña de lo que",
    "más amplio", "más amplia", "más espacioso", "más espaciosa",
    "se sienta más grande", "se siente más grande", "sienta más amplia",
    "sienta más amplio", "se sienta más amplia", "se sienta más amplio",
    "sensación de amplitud", "sensación de espacio", "amplitud",
    "parece más alto", "parezca más alto", "parece más alta", "más alta de lo que",
    "más alto de lo que", "se lee más alta", "se lee más alto",
    "estira", "agranda", "ensancha", "abre el espacio", "abre la habitación",
    "encoge", "empequeñece", "cierra visualmente", "cierran visualmente",
    "agobiante", "apretado", "apretada", "metros cuadrados",
    "visualmente", "percibe", "percibida", "profundidad",
)

#: Principios genéricos de decoración: buenos consejos que por sí solos no
#: hacen que una habitación se vea más grande.
GENERIC_DESIGN_PRINCIPLES_ES: tuple[str, ...] = (
    "sesenta treinta diez", "60 30 10", "regla del color", "regla de color",
    "paleta de color", "tono dominante", "color de acento", "tres colores",
    "subtono", "gama cromática", "círculo cromático", "combinación de colores",
)


def _m(name: str, words: tuple[str, ...], because: str, *alt: str) -> Mechanism:
    return Mechanism(name, words, because, tuple(alt))


PROMISES_ES: tuple[Promise, ...] = (
    Promise(
        key="bigger",
        label="hacer que el espacio parezca o se sienta más grande",
        language="es",
        title_signals=(
            "parezca más grande", "parece más grande", "más grande",
            "más amplio", "más amplia", "más espacioso", "amplitud",
            "aprovechar el espacio", "ganar espacio", "espacio pequeño",
            "salón pequeño", "piso pequeño", "habitación pequeña",
        ),
        mechanisms=(
            _m("vertical_emphasis",
               ("techo", "más alto", "altura", "vertical", "hacia arriba",
                "del suelo al techo", "a ras de techo", "toda la altura", "arriba"),
               "Llevar la mirada hacia arriba hace que la pared se lea más alta, "
               "y una pared más alta hace que la habitación entera parezca más "
               "grande de lo que dicen sus metros.",
               "El ojo sigue la línea más alta de la habitación, así que subirla "
               "hace que el techo se lea más alto y el espacio se sienta más amplio.",
               "La altura es la dimensión que casi siempre le sobra a una "
               "habitación pequeña, y usarla hace que se vea más grande sin tocar "
               "un solo tabique."),
            _m("clear_sightlines",
               ("interrumpe la vista", "hasta la pared del fondo", "línea de visión", "líneas de visión", "despejado", "despejada",
                "ininterrumpid", "sin obstáculos", "paso", "recorrido",
                "circulación", "camino", "continuo", "continua"),
               "Cuando nada interrumpe la vista, el ojo llega de una vez hasta la "
               "pared del fondo, así que el espacio se lee como más grande de lo "
               "que dice el plano.",
               "Un recorrido despejado deja que la mirada termine el viaje sin "
               "pararse, lo que hace que hasta una habitación estrecha parezca "
               "más amplia."),
            _m("furniture_scale",
               ("escala", "sobredimensionad", "demasiado grande", "demasiado pequeñ",
                "peso visual", "voluminos", "medir", "medida", "medidas",
                "dimensiones", "fondo del sofá", "piezas grandes", "tamaño"),
               "Los muebles que se pasan de tamaño se comen el suelo visible y "
               "estrechan el paso, así que lo que queda se siente agobiante aunque "
               "la habitación no haya cambiado ni un centímetro.",
               "Acertar con la escala deja sitio para andar y sitio para mirar, lo "
               "que hace que un espacio pequeño se lea como más grande de lo que mide."),
            _m("less_clutter",
               ("desorden", "superficies", "vacío", "quitar", "editar",
                "menos objetos", "despejar", "recoger"),
               "Las superficies despejadas le dan al ojo dónde descansar, así que "
               "una habitación con menos cosas compitiendo se lee como más amplia.",
               "El vacío es lo que el ojo interpreta como espacio, así que dejar "
               "algo libre hace que la habitación parezca más grande sin sacar un "
               "solo mueble."),
            _m("visible_floor",
               ("suelo que se ve", "suelo a la vista", "suelo continuo y visible", "patas", "suelo visible", "ver suelo", "se ve suelo", "volad",
                "colgad", "elevad", "levantad", "apoya en el suelo"),
               "Cada metro de suelo que se ve es un metro que el ojo cuenta, así "
               "que dejar el suelo a la vista bajo los muebles hace que la "
               "habitación parezca más grande.",
               "Un suelo continuo y visible le dice al ojo hasta dónde llega la "
               "habitación, lo que hace que el espacio se sienta más amplio que "
               "con muebles que apoyan a ras."),
            _m("mirrors_and_reflection",
               ("espejo", "reflej", "cristal", "vidrio", "transparente"),
               "Un reflejo añade una profundidad que el ojo lee como real, así que "
               "la pared deja de comportarse como el final de la habitación y el "
               "espacio parece más grande.",
               "La luz reflejada y la profundidad reflejada se leen las dos como "
               "espacio real, lo que hace que una habitación pequeña se vea más "
               "grande de lo que es."),
            _m("light_distribution",
               ("luz natural", "luz del día", "claridad", "lámpara", "aplique",
                "iluminar", "iluminación", "perímetro", "esquinas", "luz cálida",
                "punto de luz", "fuentes de luz", "luz cenital"),
               "La luz que llega a las paredes y a las esquinas le enseña al ojo "
               "dónde termina la habitación, y una habitación con los límites "
               "visibles se lee como más grande que otra que se apaga a dos metros.",
               "Iluminar el perímetro hace visibles los límites del espacio, lo "
               "que hace que la habitación entera se perciba más amplia que con un "
               "único foco en el centro."),
            _m("window_geometry",
               ("la tela alta", "el cristal", "cortina", "cortinas", "barra", "estor", "persiana", "visillo"),
               "Colgar la tela alta y ancha deja el cristal despejado, así que "
               "entra más luz y la pared se lee más alta de lo que mide.",
               "Sacar las cortinas fuera del vano deja la ventana entera libre, lo "
               "que hace que el hueco parezca más grande y la habitación más amplia."),
            _m("furniture_placement",
               ("contra la pared", "separa", "colocación", "distribución",
                "reparto", "perímetro", "orienta", "coloca"),
               "Una distribución pensada abre los recorridos, así que los pasos "
               "libres hacen que una habitación pequeña se sienta más grande al "
               "moverte por ella.",
               "Dónde se coloca cada mueble decide por dónde se puede andar, y una "
               "habitación que se cruza sin esquivar nada se percibe más amplia."),
            _m("continuous_flooring",
               ("cambiar de material", "mantenerlo igual", "mismo suelo", "suelo continuo", "tarima", "pavimento",
                "un solo suelo", "flooring"),
               "Un único suelo continuo evita que el ojo cuente zonas pequeñas por "
               "separado, así que el conjunto se lee como más grande que un suelo "
               "partido en tramos.",
               "Cambiar de material parte la superficie en trozos, y mantenerlo "
               "igual hace que toda la vivienda se perciba más amplia."),
            _m("low_contrast_edges",
               ("contraste", "borde", "bordes", "rodapié", "carpintería", "marco",
                "mismo color que la pared", "línea dura", "trocea", "parte la pared"),
               "Los bordes de bajo contraste dejan de trocear la pared, así que la "
               "superficie se lee como un solo plano grande y la habitación parece "
               "más amplia.",
               "Cuando la carpintería desaparece en la pared, el ojo deja de contar "
               "bordes y el muro entero se percibe más grande."),
            _m("vertical_storage",
               ("guardar en vertical", "deja el suelo libre", "almacenaje vertical", "hasta el techo", "hasta arriba",
                "estantería alta", "armario alto", "sube el almacenaje"),
               "Subir el almacenaje hasta el techo usa la altura en lugar del "
               "suelo, así que las mismas cosas dejan más suelo visible y la "
               "habitación se siente más amplia.",
               "Guardar en vertical deja el suelo libre, lo que hace que una "
               "habitación pequeña se lea como bastante más espaciosa."),
        ),
        concepts=(
            ("techo", "alto", "altura", "vertical", "arriba"),
            ("espejo", "reflej", "cristal", "transparente"),
            ("luz", "claridad", "ventana", "clar", "día"),
            ("patas", "suelo", "volad", "elevad"),
            ("escala", "tamaño", "grande", "proporción", "medida"),
            ("desorden", "despejad", "superficies", "vacío"),
            ("línea de visión", "continuo", "paso", "recorrido", "abierto"),
            ("contraste", "borde", "rodapié", "mismo color"),
            ("almacenaje", "guardar", "ocultar"),
            ("peso visual", "el ojo", "la mirada", "percib", "se lee"),
        ),
        required_groups=1,
        deny_signals=GENERIC_DESIGN_PRINCIPLES_ES,
        rescue_signals=SPACE_OUTCOMES_ES,
        counter_signals=(
            "conversación", "acústic", "olor", "aroma", "estacional",
            "mantenimiento", "toalla", "presión del agua", "al alcance",
        ),
    ),
    Promise(
        key="expensive",
        label="hacer que la casa parezca más cara",
        language="es",
        title_signals=(
            "más cara", "parezca cara", "parecer caro", "de lujo", "lujoso",
            "gama alta", "parece barato", "aspecto caro", "más lujosa",
        ),
        mechanisms=(
            _m("materials", ("material", "piedra", "mármol", "latón", "madera maciza",
                             "cuero", "lana", "lino", "roble", "nogal"),
               "Los materiales de verdad envejecen en lugar de estropearse, y esa "
               "diferencia es lo que hace que la habitación se lea como cara."),
            _m("finishes", ("acabado", "mate", "satinado", "brillo", "cepillado", "pulido"),
               "Un acabado bien elegido recoge la luz como lo hacen las superficies "
               "caras, así que la pieza entera se lee como más cara de lo que costó."),
            _m("hardware", ("tirador", "tiradores", "manilla", "pomo", "grifo",
                            "grifería", "interruptor", "herraje"),
               "Los herrajes son lo que toca la mano todos los días, así que "
               "cambiarlos hace que la habitación se perciba más cara sin tocar "
               "nada más."),
            _m("generous_scale", ("sobredimensionad", "generos", "más grande",
                                  "más ancho", "escala", "amplio"),
               "Las proporciones generosas se leen como elegidas para la casa y no "
               "para el presupuesto, lo que hace que el conjunto parezca más caro."),
            _m("layered_light", ("regulador", "aplique", "capas de luz", "luz cálida", "luz repartida",
                                 "lámpara", "luz indirecta"),
               "La luz repartida y regulable modela la habitación como lo hace un "
               "escaparate, así que el espacio se percibe bastante más caro."),
            _m("architectural_detail", ("moldura", "panelado", "zócalo", "rodapié",
                                        "arquitectónico", "detalle", "junta", "remate"),
               "Un detalle arquitectónico limpio es la señal de un trabajo bien "
               "terminado, lo que hace que la habitación se lea como de gama alta."),
            _m("concealment", ("cable", "cables", "ocultar", "esconder", "plástico", "recoger"),
               "Los cables y el plástico a la vista son lo que abarata una "
               "habitación por lo demás correcta, así que esconderlos sube todo lo "
               "que hay alrededor."),
            _m("upholstery", ("tapiza", "tapicería", "cabecero", "acolchad", "terciopelo"),
               "La tapicería aporta el fondo y el peso que le faltan al mueble "
               "barato, de modo que la pieza se lee como mucho más cara."),
            _m("framing", ("marco", "enmarca", "paspartú", "galería", "cuadro"),
               "Un buen marco convierte una lámina corriente en algo que parece "
               "comprado en una galería, lo que hace que el arte barato se lea "
               "como elegido con criterio."),
            _m("greenery", ("flores", "ramas", "planta", "verde"),
               "Las ramas frescas son lo más barato de la habitación y lo que más "
               "fiablemente se lee como cuidado, así que la casa entera parece más cara."),
            _m("window_dressing", ("cortina", "cortinas", "dobladillo", "bajo", "tela"),
               "Unas cortinas que rozan el suelo parecen hechas a medida, de modo "
               "que la ventana entera se lee como cara en lugar de barata."),
            _m("restraint", ("quitar", "editar", "vacío", "contención", "menos"),
               "Editar deja sitio para que se vean las piezas buenas, y por eso la "
               "contención se lee como cara."),
        ),
        concepts=(
            ("material", "piedra", "mármol", "latón", "madera", "cuero", "lino"),
            ("acabado", "mate", "tirador", "herraje", "remate"),
            ("escala", "generos", "grande", "amplio"),
            ("luz", "lámpara", "aplique", "regulador", "cálida"),
            ("detalle", "moldura", "panelado", "arquitectónico"),
            ("cable", "plástico", "ocultar", "recoger"),
            ("cortina", "tela", "tapiza"),
            ("marco", "cuadro", "galería"),
            ("flores", "ramas", "planta"),
        ),
        deny_signals=("acústic", "presión del agua", "olor"),
        rescue_signals=(
            "más cara", "más caro", "cara", "caro", "de lujo", "lujoso",
            "barato", "barata", "gama alta", "a medida", "cuidado", "elegido",
        ),
        counter_signals=("estacional", "cuota"),
    ),
    Promise(
        key="cozy",
        label="hacer que la casa se sienta más cálida y acogedora",
        language="es",
        title_signals=("acogedor", "acogedora", "más cálido", "más cálida",
                       "calidez", "cómodo", "hogareño"),
        mechanisms=(
            _m("warm_low_light", ("cálida", "cálido", "luz baja", "lámpara", "vela",
                                  "regulador", "kelvin", "2700", "2200", "tarde", "noche"),
               "La luz cálida y baja se lee como final del día, y eso es lo que el "
               "cuerpo entiende como acogedor."),
            _m("soft_texture", ("suave", "lana", "manta", "cojín", "lino", "textura",
                                "tapiza", "borreguito"),
               "La textura suave invita a tocar, y eso hace que una habitación se "
               "sienta cálida en lugar de solo amueblada."),
            _m("natural_material", ("madera", "roble", "material natural", "materiales naturales", "fibra"),
               "Los materiales naturales llevan el color cálido en el propio "
               "material, así que la habitación entera se siente menos fría."),
            _m("enclosure", ("rincón", "esquina", "resguard", "respaldo", "íntimo",
                             "a la espalda", "refugio"),
               "Tener algo sólido a la espalda es lo que hace que un asiento se "
               "sienta seguro, y un asiento seguro se siente acogedor."),
            _m("acoustics", ("acústic", "sonido", "eco", "absorb", "alfombra", "libros"),
               "Las superficies blandas absorben el eco, así que una habitación "
               "silenciosa se siente más cálida que una que resuena."),
            _m("personal_traces", ("vivid", "personal", "uso", "vela", "libro"),
               "Las señales de uso son lo que separa una casa de un piso piloto, y "
               "eso es buena parte de lo que significa acogedor."),
        ),
        concepts=(
            ("cálida", "luz baja", "vela", "lámpara", "tarde"),
            ("suave", "lana", "manta", "cojín", "textura", "lino"),
            ("madera", "natural", "fibra"),
            ("rincón", "esquina", "resguard", "íntimo"),
            ("acústic", "sonido", "alfombra", "libros"),
            ("personal", "vivid", "uso"),
        ),
        deny_signals=("reventa", "sesenta treinta diez"),
        rescue_signals=("acogedor", "acogedora", "cálida", "cálido", "calidez",
                        "cómodo", "relaj", "hogar"),
        counter_signals=("reventa",),
    ),
    Promise(
        key="brighter",
        label="traer más luz a la habitación",
        language="es",
        title_signals=("más luz", "más luminoso", "más luminosa", "iluminar",
                       "habitación oscura", "luminosidad"),
        mechanisms=(
            _m("more_light_sources", ("punto de luz", "fuentes de luz", "lámpara",
                                      "bombilla", "aplique", "regulador", "led"),
               "Más puntos de luz separados rellenan los huecos que deja una sola "
               "lámpara de techo, así que la habitación queda más luminosa en todas "
               "partes en vez de bajo un único foco."),
            _m("daylight", ("luz natural", "luz del día", "ventana", "cristal", "sol"),
               "Todo lo que deja entrar más luz natural sube el nivel de luz de la "
               "habitación entera sin gastar nada."),
            _m("reflection", ("espejo", "reflej", "brillo", "satinado", "superficies reflectantes"),
               "Las superficies reflectantes devuelven a la habitación la luz que "
               "ya tienes, de modo que las mismas bombillas dejan el espacio "
               "notablemente más luminoso."),
            _m("pale_surfaces", ("clar", "pálid", "blanco", "luminos"),
               "Las superficies claras reflejan mucha más luz de la que reciben, "
               "así que la habitación se ve más luminosa con la misma instalación."),
            _m("colour_temperature", ("kelvin", "temperatura de color", "cálida",
                                      "pantalla", "difus", "capas"),
               "Acertar con la temperatura de color y con la pantalla evita que la "
               "luz se pierda antes de llegar a la habitación, que es lo que la "
               "deja oscura."),
            _m("unobstructed_windows", ("cortina", "estor", "alféizar", "despejar",
                                        "sin obstáculos"),
               "Despejar la propia ventana es el cambio que más luz devuelve, de "
               "modo que la habitación deja de estar oscura a media tarde."),
        ),
        concepts=(
            ("luz", "lámpara", "bombilla", "aplique", "led"),
            ("ventana", "natural", "día", "sol", "cortina"),
            ("espejo", "reflej", "clar", "blanco"),
            ("kelvin", "cálida", "pantalla", "capas"),
        ),
        deny_signals=GENERIC_DESIGN_PRINCIPLES_ES,
        rescue_signals=("luminos", "más luz", "oscura", "oscuro", "clar", "sombra"),
    ),
    Promise(
        key="storage",
        label="ganar almacenaje o reducir el desorden",
        language="es",
        title_signals=("almacenaje", "organiza", "orden", "desorden", "guardar"),
        concepts=(
            ("almacenaje", "guardar", "guardado"),
            ("estante", "balda", "armario", "cajón", "mueble"),
            ("cesta", "caja", "recipiente", "etiqueta"),
            ("oculto", "esconder", "banco", "puf"),
            ("vertical", "techo", "altura", "pared"),
            ("desorden", "recoger", "sistema", "salida"),
        ),
        counter_signals=("color de pared", "largo de cortina", "olor"),
    ),
    Promise(
        key="mistakes",
        label="identificar un error que merece la pena corregir",
        language="es",
        title_signals=("error", "errores", "fallo", "fallos", "evitar", "nunca"),
        concepts=(
            ("demasiado", "error", "mal", "evitar", "falla"),
            ("en lugar de", "en vez de", "mejor", "nunca", "deja de"),
            ("tamaño", "escala", "altura", "proporción", "colocación"),
            ("luz", "color", "alfombra", "cortina", "arte", "mueble"),
        ),
    ),
)

GENERAL_ES = Promise(
    key="general",
    label="ideas útiles para esta estancia",
    language="es",
    title_signals=(),
    concepts=(),
    required_groups=0,
)
