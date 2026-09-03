"""Curated home decor / interior design knowledge base.

This module is the substance behind the free, offline script engine. Every
entry is an original, hand-written design idea with a reason, a practical
implementation note, an optional common mistake, and the visual search
queries that illustrate it.

Nothing here is scraped or copied - it is written as reusable editorial
building blocks that the script generator recombines and rephrases.

Entry shape::

    {
        "title":   short imperative idea used as the on-screen/narration item,
        "why":     one or two sentences explaining the design principle,
        "how":     concrete implementation advice (numbers where useful),
        "mistake": optional "what people get wrong" sentence,
        "queries": 3-5 stock-footage search queries for the visuals,
        "tags":    keywords for relevance scoring,
    }
"""

from __future__ import annotations

from typing import Any

Tip = dict[str, Any]

KNOWLEDGE: dict[str, list[Tip]] = {}


def _add(category: str, tips: list[Tip]) -> None:
    for tip in tips:
        tip.setdefault("category", category)
    KNOWLEDGE.setdefault(category, []).extend(tips)


_add("living rooms", [
    {
        "title": "Hang your curtains close to the ceiling, not to the window frame",
        "why": "The eye reads the top of the curtain rod as the top of the wall, so mounting the rod high stretches the whole room upward and makes a standard eight-foot ceiling feel far taller than it is.",
        "how": "Mount the rod four to six inches below the ceiling line and let the panels break just barely on the floor. Buy the longest ready-made length you can find, usually ninety-six or one hundred and eight inches, and widen the rod so the panels stack off the glass.",
        "mistake": "Short panels that stop at the windowsill are the single fastest way to make a living room look like a rental you never unpacked in.",
        "queries": ["floor to ceiling curtains living room", "tall curtains modern interior", "elegant living room window drapes", "linen curtains sunlight living room"],
        "tags": ["curtains", "windows", "height", "living room"],
    },
    {
        "title": "Buy a rug that is genuinely too big rather than slightly too small",
        "why": "A rug defines the seating zone. When it is undersized, the furniture floats on the floor with no visual anchor and the whole seating group reads as smaller and more scattered than it actually is.",
        "how": "Aim for a rug wide enough that at least the front legs of every seat sit on it. In most living rooms that means eight by ten feet, not five by seven, and it should extend roughly six to eight inches past the sides of the sofa.",
        "mistake": "The classic error is a small rug centered under the coffee table only, which shrinks the room and makes expensive furniture look accidental.",
        "queries": ["large living room rug sofa", "modern living room carpet interior", "area rug under coffee table", "neutral rug living room design"],
        "tags": ["rug", "layout", "living room", "floor"],
    },
    {
        "title": "Pull the sofa off the wall by a few inches",
        "why": "Pushing every piece flat against the perimeter is what designers call the skating rink layout. It leaves a dead void in the middle and, counterintuitively, makes the room feel emptier and less generous.",
        "how": "Float the sofa three to six inches off the wall and let the rug and a console table fill the gap behind it. Even that small amount of breathing room instantly reads as intentional.",
        "queries": ["floating sofa living room layout", "console table behind sofa", "spacious modern living room", "living room furniture arrangement"],
        "tags": ["layout", "sofa", "furniture placement"],
    },
    {
        "title": "Give the room a single, obvious focal point",
        "why": "Rooms feel restless when three or four elements compete for attention. One committed focal point gives the eye somewhere to land and everything else quietly supports it.",
        "how": "Pick the fireplace, the largest window, or one oversized piece of art, then angle the seating toward it. If the television has to be the focal point, build it into a wall of cabinetry so it stops looking like a black rectangle.",
        "queries": ["fireplace living room focal point", "large artwork above sofa", "built in media wall living room", "cozy fireplace interior design"],
        "tags": ["focal point", "composition", "living room"],
    },
    {
        "title": "Hang art at eye level and scale it to the furniture",
        "why": "Art that floats near the ceiling breaks the visual connection with the furniture below it, and undersized art above a large sofa makes the whole wall look unfinished.",
        "how": "Center the piece about fifty-seven to sixty inches from the floor, and choose something that spans roughly two-thirds of the width of whatever sits beneath it. Leave six to eight inches between the top of the sofa and the bottom of the frame.",
        "mistake": "A tiny frame stranded above a three-seat sofa is one of the most common and most avoidable mistakes in a living room.",
        "queries": ["large art above sofa living room", "gallery wall living room", "framed artwork interior wall", "minimalist wall art living room"],
        "tags": ["art", "walls", "scale"],
    },
    {
        "title": "Layer three types of light instead of relying on the ceiling fixture",
        "why": "A single overhead light flattens a room and casts hard shadows on faces and furniture. Layered light gives depth, and depth is most of what reads as expensive.",
        "how": "Combine ambient light overhead, task light beside seating, and accent light low to the ground. Three or four separate sources at different heights, all on warm bulbs around 2700 kelvin, will transform an ordinary room in an evening.",
        "queries": ["warm living room lamp lighting", "floor lamp beside sofa", "table lamp cozy interior", "evening living room ambient light"],
        "tags": ["lighting", "lamps", "atmosphere"],
    },
    {
        "title": "Vary the height of everything you place on a surface",
        "why": "When objects on a shelf or console are all the same height, the eye skims across them and registers clutter rather than composition.",
        "how": "Work in loose triangles: something tall like a lamp or a vase of branches, something medium like stacked books, and something low and organic like a bowl or a small plant. Odd numbers photograph and read better than even ones.",
        "queries": ["styled console table decor", "living room shelf styling", "vase books coffee table styling", "decorative objects interior shelf"],
        "tags": ["styling", "accessories", "composition"],
    },
    {
        "title": "Leave real walking paths through the room",
        "why": "Circulation is invisible when it works and unbearable when it does not. A room you have to sidestep through never feels relaxing, no matter how good the furniture is.",
        "how": "Keep at least thirty to thirty-six inches of clear path around the main routes, and fourteen to eighteen inches between the sofa and the coffee table so people can reach a drink without leaning.",
        "queries": ["open living room walkway", "spacious living room interior", "modern living room floor plan", "living room with clear circulation"],
        "tags": ["layout", "circulation", "space planning"],
    },
    {
        "title": "Repeat each accent color at least three times",
        "why": "A single burst of color looks like a mistake. The same color echoed around the room looks like a decision, and the eye travels around the space instead of stopping at one loud object.",
        "how": "If you bring in a deep olive cushion, echo it in a stem of greenery, a book spine, and a throw across an armchair. Small doses, spread apart, do more than one large statement piece.",
        "queries": ["color accent cushions living room", "green accents modern interior", "coordinated color palette living room", "throw pillows styled sofa"],
        "tags": ["color", "styling", "cohesion"],
    },
    {
        "title": "Mix at least three materials in every room",
        "why": "Rooms that use one material everywhere read flat, and rooms that use ten read chaotic. Three or four contrasting textures create the tactile richness people describe as warm.",
        "how": "Pair something soft, something hard, and something natural: a wool rug, a wood or stone table, and a woven basket or linen curtain. Add one small reflective element, like an aged brass lamp, to catch the light.",
        "queries": ["texture layering living room", "wood and linen interior", "woven basket living room decor", "natural materials modern home"],
        "tags": ["texture", "materials", "warmth"],
    },
    {
        "title": "Add one oversized plant instead of five small ones",
        "why": "A cluster of small pots reads as clutter and needs constant attention. One large plant reads as architecture and softens the hard corners of a room.",
        "how": "A fiddle leaf fig, a bird of paradise, or an olive tree in a floor basket fills vertical space beautifully. Put it where two walls meet, and if your light is poor, a good-quality faux tree is a completely legitimate choice.",
        "queries": ["large indoor plant living room", "fiddle leaf fig interior", "olive tree indoor pot", "green plants modern living room"],
        "tags": ["plants", "greenery", "scale"],
    },
    {
        "title": "Give the coffee table a job beyond holding remotes",
        "why": "The coffee table sits at the visual center of the seating group, so whatever happens there sets the tone for the entire room.",
        "how": "Use a tray to corral small items, stack two or three books to create height, and add one organic element like a low bowl or a small vase. Keep roughly a third of the surface empty so it still functions.",
        "queries": ["coffee table styling tray books", "modern coffee table decor", "living room center table design", "styled coffee table interior"],
        "tags": ["coffee table", "styling", "living room"],
    },
])

_add("bedrooms", [
    {
        "title": "Treat the headboard wall as the whole composition",
        "why": "In a bedroom the bed is the focal point whether you plan it or not, so anything unresolved on that wall is the first thing anyone notices.",
        "how": "Give the bed a headboard tall enough to be seen from the doorway, then balance it with matched lamps or sconces and one piece of art or a mirror centered above. Symmetry on this wall is genuinely calming.",
        "queries": ["upholstered headboard bedroom", "symmetrical bedroom nightstands", "modern bedroom headboard wall", "cozy bedroom bed styling"],
        "tags": ["bed", "headboard", "symmetry", "bedroom"],
    },
    {
        "title": "Match your bedding scale to your mattress, then go one size up",
        "why": "Most people buy a duvet that technically fits and then wonder why the bed looks thin and hotel-cheap instead of full and inviting.",
        "how": "Use a duvet one size larger than the mattress so it drapes generously down both sides, and layer a folded quilt across the lower third for depth. Two flat sleeping pillows, two euro shams, and one lumbar is enough.",
        "mistake": "Skipping the layer at the foot of the bed is why so many beds look flat in photos and in person.",
        "queries": ["layered bedding duvet bedroom", "made bed with quilt and pillows", "luxury bedding hotel style", "white linen bedding bedroom"],
        "tags": ["bedding", "layering", "bedroom"],
    },
    {
        "title": "Put a lamp on both sides, even in a small room",
        "why": "One nightstand lamp forces one person to get up in the dark and creates lopsided light that quietly unbalances the room.",
        "how": "If floor space is tight, use plug-in wall sconces or slim clamp lights mounted at about fifty inches from the floor. The point is a matched pair of warm light sources at bed height.",
        "queries": ["bedside lamps pair bedroom", "wall sconce beside bed", "warm bedroom lighting night", "nightstand lamp interior"],
        "tags": ["lighting", "nightstand", "bedroom"],
    },
    {
        "title": "Put your bedroom lights on dimmers",
        "why": "A bedroom has to do two completely different jobs, getting ready in the morning and winding down at night, and one fixed brightness level cannot serve both.",
        "how": "Swap the wall switch for a dimmer, or use smart bulbs if you rent. Aim for the ability to drop the room to roughly ten percent brightness in the evening.",
        "queries": ["dimmed bedroom lighting evening", "warm bedroom ambient light", "bedside lamp low light", "cozy bedroom night lighting"],
        "tags": ["lighting", "dimmer", "atmosphere"],
    },
    {
        "title": "Anchor the bed with a rug, even over carpet",
        "why": "A rug under the bed extends the visual footprint of the sleeping area and gives you something soft to step onto, which is a small daily luxury.",
        "how": "Run the rug perpendicular under the lower two-thirds of the bed so it extends at least eighteen to twenty-four inches on each side. Two narrow runners flanking the bed work when a single large rug is out of budget.",
        "queries": ["rug under bed bedroom", "bedroom area rug interior", "soft rug beside bed", "layered rug bedroom design"],
        "tags": ["rug", "bedroom", "floor"],
    },
    {
        "title": "Keep the palette quiet and let texture do the work",
        "why": "Bedrooms are the one room where visual stimulation actively works against the purpose of the space. Restraint here reads as expensive and helps you sleep.",
        "how": "Choose three to four related tones, usually a warm neutral base with one deeper accent, then build interest with linen, wool, boucle and wood rather than with pattern.",
        "queries": ["neutral bedroom interior design", "beige bedroom texture linen", "calm minimalist bedroom", "warm neutral bedroom palette"],
        "tags": ["color", "texture", "calm", "bedroom"],
    },
    {
        "title": "Hide the technology and the cables",
        "why": "Charging bricks, black cables and glowing standby lights are the fastest way to break the calm you are trying to build.",
        "how": "Use a nightstand with a drawer, run a single cable through a small grommet or clip, and move the work laptop out of the room entirely if you can. Cable sleeves cost a few dollars and change the whole feel of the wall.",
        "queries": ["tidy nightstand bedroom", "cable management bedroom desk", "clean minimal bedside table", "organized bedroom surface"],
        "tags": ["organization", "cables", "calm"],
    },
    {
        "title": "Add a bench or a chair at the end of the bed",
        "why": "It gives the composition a lower horizontal line that grounds the bed, and it solves the very real problem of where clothes land at eleven at night.",
        "how": "In a large room use an upholstered bench roughly three-quarters the width of the bed. In a smaller room a single armchair in the corner does the same job with less bulk.",
        "queries": ["bench at end of bed", "upholstered bedroom bench", "armchair corner bedroom", "bedroom seating interior"],
        "tags": ["furniture", "bedroom", "layout"],
    },
    {
        "title": "Do not push a double bed into a corner unless you must",
        "why": "A bed against two walls means one sleeper climbs over the other, and visually the room loses the symmetry that makes bedrooms feel resolved.",
        "how": "Center the bed on the longest uninterrupted wall and keep at least twenty-four inches of clearance on each side. If the room genuinely cannot take it, commit to the corner and use a single wall-mounted shelf instead of a nightstand.",
        "queries": ["small bedroom bed placement", "bedroom layout ideas", "bed centered on wall", "compact bedroom interior"],
        "tags": ["layout", "bed placement", "bedroom"],
    },
    {
        "title": "Block the light properly",
        "why": "Sheer curtains look lovely and do nothing at six in the morning in June. Sleep quality is part of bedroom design.",
        "how": "Layer a blackout liner or a roller blind behind decorative panels so you keep the softness of fabric and still get real darkness. Mount the blind inside the recess and the curtains outside it.",
        "queries": ["blackout curtains bedroom", "layered curtains and blinds", "dark bedroom window treatment", "bedroom curtains morning light"],
        "tags": ["curtains", "blackout", "sleep"],
    },
    {
        "title": "Give yourself one soft light at floor level",
        "why": "Low light reads as evening to the human eye. A single lamp near the floor makes a bedroom feel dramatically cozier than the same room lit from above.",
        "how": "Tuck a small lamp on a low stool, a plug-in uplight behind a plant, or a strip of warm LED under the bed frame. Keep it warm, around 2200 to 2700 kelvin.",
        "queries": ["low warm light bedroom floor", "cozy bedroom lamp glow", "under bed lighting warm", "soft evening bedroom light"],
        "tags": ["lighting", "cozy", "bedroom"],
    },
    {
        "title": "Choose nightstands that are level with the top of the mattress",
        "why": "A nightstand that is far too low means reaching down for a glass of water, and one that is too tall visually crowds the bed.",
        "how": "Aim for a surface within two inches of the mattress top, and pick something with at least one closed drawer so the surface can stay clear.",
        "queries": ["wooden nightstand bedroom", "bedside table styling", "modern nightstand interior", "bedroom side table drawer"],
        "tags": ["nightstand", "furniture", "bedroom"],
    },
])


_add("kitchens", [
    {
        "title": "Clear the counters and keep only three things out",
        "why": "Kitchens read as expensive when surfaces are visible. Every appliance left on the counter steals visual square footage and makes even a large kitchen feel cramped.",
        "how": "Choose three items that earn their place, usually the kettle or coffee machine, a wooden board, and a small plant or bowl. Everything else goes into a cabinet or an appliance garage.",
        "queries": ["clean minimal kitchen counter", "modern kitchen countertop styling", "tidy kitchen interior", "bright organized kitchen"],
        "tags": ["counters", "declutter", "kitchen"],
    },
    {
        "title": "Add light under the upper cabinets",
        "why": "Overhead kitchen lighting puts your own shadow on the work surface. Under-cabinet light removes that shadow and makes the counter material look twice as good.",
        "how": "Warm white LED strips or puck lights mounted toward the front edge of the upper cabinet. Battery or plug-in versions exist if you cannot hard-wire, and they take about twenty minutes to fit.",
        "queries": ["under cabinet kitchen lighting", "kitchen counter led light", "warm lit kitchen evening", "modern kitchen task lighting"],
        "tags": ["lighting", "task light", "kitchen"],
    },
    {
        "title": "Swap the cabinet hardware before you consider new cabinets",
        "why": "Handles are the jewelry of a kitchen and they are the cheapest thing in the room to change. New hardware can move a builder-grade kitchen forward by a decade.",
        "how": "Measure your existing hole spacing first, then choose one finish and use it everywhere. Longer pulls, roughly a third the width of the drawer, look far more current than small knobs.",
        "queries": ["brass cabinet handles kitchen", "modern kitchen hardware detail", "kitchen drawer pulls closeup", "black cabinet hardware kitchen"],
        "tags": ["hardware", "budget", "kitchen"],
    },
    {
        "title": "Hang pendants at the right height over an island",
        "why": "Pendants hung too high look like an afterthought and pendants hung too low block conversation across the island.",
        "how": "Aim for thirty to thirty-six inches between the countertop and the bottom of the pendant, and space multiple pendants at least thirty inches apart, centered on the island rather than on the room.",
        "queries": ["kitchen island pendant lights", "modern kitchen island lighting", "pendant lamp above counter", "bright kitchen island design"],
        "tags": ["lighting", "island", "kitchen"],
    },
    {
        "title": "Take open shelving seriously or skip it",
        "why": "Open shelves look beautiful in photographs because the objects on them are edited. In real life they become a display of mismatched mugs.",
        "how": "Limit open shelving to one short run, keep a consistent material palette on it, and store the everyday chaos behind doors. Two shelves styled well beat a whole wall styled badly.",
        "queries": ["open shelving kitchen styled", "wooden kitchen shelf dishes", "minimal kitchen shelf decor", "kitchen shelf ceramics"],
        "tags": ["shelving", "styling", "kitchen"],
    },
    {
        "title": "Use a runner to soften a galley kitchen",
        "why": "Kitchens are full of hard reflective surfaces, and hard surfaces bounce sound. A textile on the floor absorbs noise and adds the warmth the room is usually missing.",
        "how": "A flat-weave washable runner that spans most of the working length, in a low-contrast pattern that hides crumbs. Keep it clear of the oven door swing.",
        "queries": ["kitchen runner rug galley", "washable kitchen rug interior", "narrow rug kitchen floor", "cozy kitchen textile"],
        "tags": ["rug", "texture", "kitchen"],
    },
    {
        "title": "Give the backsplash one clear idea",
        "why": "The backsplash is a small area with a big visual impact, so it is either the quiet background or the feature. Trying to be both leaves it looking indecisive.",
        "how": "If your counters are busy, keep the backsplash plain and run it all the way to the underside of the uppers. If your counters are calm, this is the place for zellige tile, a slab, or a strong pattern.",
        "queries": ["kitchen backsplash tile detail", "zellige tile kitchen", "marble slab backsplash", "subway tile kitchen wall"],
        "tags": ["backsplash", "tile", "kitchen"],
    },
    {
        "title": "Store things where you actually use them",
        "why": "Most kitchen frustration is a layout problem, not a storage-volume problem. Walking three steps for a chopping board twenty times a day is a design failure.",
        "how": "Group by zone: prep tools near the main counter, cooking tools within arm's reach of the hob, and everyday plates near the dishwasher. Rearranging costs nothing and takes an afternoon.",
        "queries": ["organized kitchen drawer utensils", "kitchen cabinet organization", "functional kitchen storage", "kitchen drawer dividers"],
        "tags": ["organization", "zones", "kitchen"],
    },
    {
        "title": "Paint the lower cabinets darker than the uppers",
        "why": "A darker base visually grounds the room and a lighter top keeps it from closing in. It is a simple trick that makes standard cabinetry look custom.",
        "how": "Keep the uppers in the wall color or something close to it, and use a deeper, muted tone below. Test large samples in the actual room light before you commit.",
        "queries": ["two tone kitchen cabinets", "dark lower cabinets kitchen", "green kitchen cabinets interior", "painted kitchen cabinetry"],
        "tags": ["color", "cabinets", "kitchen"],
    },
    {
        "title": "Add one warm material to a cold kitchen",
        "why": "White cabinets, stainless appliances and a gray floor produce a kitchen that is easy to clean and unpleasant to spend time in.",
        "how": "Introduce wood in a real way, not a token cutting board: open shelves, a butcher-block section of counter, cane cabinet inserts, or wooden bar stools.",
        "queries": ["wood accents white kitchen", "butcher block counter kitchen", "warm modern kitchen wood", "wooden bar stools kitchen island"],
        "tags": ["warmth", "wood", "kitchen"],
    },
    {
        "title": "Extend the run of upper cabinets to the ceiling",
        "why": "The gap above kitchen cabinets collects dust and visually chops the wall in half, which lowers the whole room.",
        "how": "Either order taller cabinets, add a trim panel to close the gap, or box the space in with matching board. If you rent, storing matched baskets up there is the next best answer.",
        "queries": ["floor to ceiling kitchen cabinets", "tall kitchen cabinetry design", "kitchen cabinets to ceiling", "modern full height kitchen"],
        "tags": ["cabinets", "height", "kitchen"],
    },
    {
        "title": "Decant the things you look at every day",
        "why": "Commercial packaging is designed to shout on a shelf, which is the opposite of what you want in a calm kitchen.",
        "how": "Move oils, coffee, pasta and cereals into consistent glass or ceramic containers. Keep the labels simple, and only decant what you genuinely use often.",
        "queries": ["glass storage jars kitchen pantry", "decanted pantry containers", "organized kitchen pantry shelf", "minimal kitchen jars"],
        "tags": ["organization", "pantry", "kitchen"],
    },
])

_add("bathrooms", [
    {
        "title": "Buy hotel-weight towels in a single color",
        "why": "Mismatched towels are the loudest thing in most bathrooms. One color, one weight, folded the same way, instantly reads as a hotel rather than a hallway cupboard.",
        "how": "Choose six hundred gram per square meter cotton in a color that flatters your tile, and retire anything frayed. Two bath towels and two hand towels on display is plenty.",
        "queries": ["folded white towels bathroom", "hotel style bathroom towels", "spa bathroom interior", "neutral bathroom textiles"],
        "tags": ["towels", "textiles", "bathroom"],
    },
    {
        "title": "Light the mirror from the sides, not from above",
        "why": "A single fixture above the mirror throws shadows straight down onto your face, which is why bathroom lighting is famous for being unflattering.",
        "how": "Mount sconces at roughly sixty-six inches from the floor on either side of the mirror, or choose a mirror with an integrated backlight. Warm white, around 3000 kelvin, is kinder than daylight bulbs.",
        "queries": ["bathroom mirror sconces", "vanity lighting bathroom", "backlit mirror bathroom", "modern bathroom vanity light"],
        "tags": ["lighting", "mirror", "bathroom"],
    },
    {
        "title": "Replace the shower curtain rod with a longer one and hang it high",
        "why": "The same trick that works in a living room works even better in a small bathroom, because the shower is usually the tallest element in the room.",
        "how": "Mount the rod just under the ceiling and use an extra-long curtain. A curved rod adds several inches of elbow room inside the shower for about twenty dollars.",
        "queries": ["tall shower curtain bathroom", "small bathroom shower interior", "white bathroom curtain design", "bright compact bathroom"],
        "tags": ["shower", "height", "bathroom"],
    },
    {
        "title": "Give the bathroom something that is not waterproof",
        "why": "Bathrooms are all tile, glass and porcelain, which is why they so often feel clinical. One soft or organic element breaks the hardness.",
        "how": "A small washable mat, a wooden stool, a linen roman blind, or a plant that tolerates humidity such as a pothos or a fern will do it.",
        "queries": ["plant in bathroom interior", "wooden stool bathroom", "spa bathroom greenery", "cozy bathroom textiles"],
        "tags": ["texture", "plants", "bathroom"],
    },
    {
        "title": "Get everything off the edge of the bath and the sink",
        "why": "Bottles are visually noisy and they are the first thing people see. Clearing them is the single highest-impact five-minute change in any bathroom.",
        "how": "Use a recessed niche, a slim shower caddy that matches your fixtures, or refillable pump bottles in one material. Keep one item on the sink, not five.",
        "queries": ["minimal bathroom sink counter", "shower niche organized", "clean bathroom surfaces", "bathroom storage basket"],
        "tags": ["declutter", "storage", "bathroom"],
    },
    {
        "title": "Match your metals, or contrast them deliberately",
        "why": "Three accidental finishes in one small room look unresolved. Two chosen finishes look designed.",
        "how": "Pick a dominant finish for the taps and shower, then allow one secondary finish for smaller accents like the mirror frame. Changing a tap is often cheaper than living with the mismatch.",
        "queries": ["brass bathroom tap detail", "black bathroom fixtures", "modern bathroom faucet closeup", "bathroom hardware finish"],
        "tags": ["fixtures", "metals", "bathroom"],
    },
    {
        "title": "Use a big mirror",
        "why": "A mirror doubles the perceived depth of a small room and bounces whatever natural light you have back into it.",
        "how": "Go as wide as the vanity allows, and if the room is genuinely tiny, a full-wall mirror above the sink is one of the strongest small-bathroom moves there is.",
        "queries": ["large bathroom mirror interior", "wide vanity mirror bathroom", "bright small bathroom mirror", "modern bathroom mirror design"],
        "tags": ["mirror", "small space", "bathroom"],
    },
    {
        "title": "Upgrade the shower head before anything else",
        "why": "You experience a bathroom mostly through water pressure and temperature, not through tile choices. It is the highest daily-value upgrade in the room.",
        "how": "A decent rainfall or high-pressure head in your chosen finish takes fifteen minutes with a wrench and some tape, and costs less than a single tile order.",
        "queries": ["rainfall shower head bathroom", "modern shower interior", "shower water detail", "bathroom shower fixture"],
        "tags": ["fixtures", "shower", "upgrade"],
    },
    {
        "title": "Paint a small bathroom a deep color",
        "why": "Small dark rooms do not have to be a problem. A windowless bathroom fights the light no matter what you do, so leaning into moodiness often works better than fighting it.",
        "how": "A deep green, ink blue or clay tone on the walls and ceiling, with warm lighting and a brass or bronze fixture, turns a weak room into a deliberate one.",
        "queries": ["dark green bathroom interior", "moody bathroom design", "deep blue bathroom walls", "dramatic small bathroom"],
        "tags": ["color", "small space", "bathroom"],
    },
    {
        "title": "Add closed storage even if you have to build it up the wall",
        "why": "Bathrooms generate small ugly objects at a remarkable rate, and nothing looks tidy when it is all on display.",
        "how": "A tall narrow cabinet, an over-toilet unit, or a mirrored cabinet with real depth. Aim for one closed cubic foot of storage per person using the room.",
        "queries": ["bathroom storage cabinet", "over toilet shelving unit", "organized bathroom cupboard", "narrow bathroom storage"],
        "tags": ["storage", "organization", "bathroom"],
    },
    {
        "title": "Regrout and recaulk before you renovate",
        "why": "Discolored grout and yellowing silicone make an otherwise fine bathroom look old. Fixing them costs almost nothing and changes the impression of the whole room.",
        "how": "Cut out old silicone, clean thoroughly, let it dry completely, then apply a smooth new bead. Grout pens work well for touch-ups on wall tile.",
        "queries": ["clean white bathroom tile", "fresh grout bathroom", "bathroom tile detail clean", "renovated bathroom surfaces"],
        "tags": ["maintenance", "tile", "bathroom"],
    },
])


_add("small spaces", [
    {
        "title": "Choose furniture with visible legs",
        "why": "Seeing floor continue underneath a sofa or a cabinet tells your brain the room keeps going. Pieces that sit flat on the ground stop the eye and read as heavy.",
        "how": "Look for sofas and armchairs raised on slim legs, and wall-mount the console, the vanity or the media unit wherever plumbing and studs allow.",
        "queries": ["sofa with wooden legs small living room", "wall mounted console small apartment", "compact modern furniture interior", "airy small living space"],
        "tags": ["furniture", "visual weight", "small space"],
    },
    {
        "title": "Use fewer, larger pieces instead of many small ones",
        "why": "It feels intuitive to buy small furniture for a small room, but a scatter of tiny items creates visual noise and eats the floor in awkward fragments.",
        "how": "One generous sofa beats a loveseat plus two chairs. One large artwork beats nine small frames. Fewer outlines mean a calmer, larger-feeling room.",
        "mistake": "Filling a small room with doll-sized furniture is the most common reason a small space still feels cramped after it is decorated.",
        "queries": ["large sofa small apartment", "minimal small living room", "single large artwork small room", "spacious small apartment interior"],
        "tags": ["scale", "editing", "small space"],
    },
    {
        "title": "Take storage vertical",
        "why": "Small homes almost always have unused wall height. The square footage is fixed but the cubic footage is not.",
        "how": "Run shelving to the ceiling, use the top of wardrobes with matched boxes, and hang rails on the backs of doors. Vertical lines also stretch the room upward.",
        "queries": ["floor to ceiling shelving small room", "tall bookshelf apartment", "vertical storage small home", "wall shelves compact interior"],
        "tags": ["storage", "vertical", "small space"],
    },
    {
        "title": "Make every large piece do two jobs",
        "why": "In a small home, single-purpose furniture is a luxury you pay for in floor space every single day.",
        "how": "An ottoman that opens for storage, a bed with drawers underneath, a nesting side table, a dining table that doubles as a desk. Prioritize the pieces that are already there.",
        "queries": ["storage ottoman living room", "bed with under storage drawers", "folding dining table small apartment", "multifunctional furniture small home"],
        "tags": ["multifunction", "storage", "small space"],
    },
    {
        "title": "Keep one continuous flooring material",
        "why": "Changing floor finish between rooms chops a small home into visibly smaller boxes. Continuity is one of the strongest space-expanding tricks available.",
        "how": "If replacing floors is not possible, run a similar-toned rug through connected zones, or at minimum use the same color family throughout.",
        "queries": ["continuous wood flooring apartment", "open plan small apartment floor", "seamless flooring interior", "light wood floor small home"],
        "tags": ["flooring", "continuity", "small space"],
    },
    {
        "title": "Place a mirror opposite or beside a window",
        "why": "A mirror does not just reflect light, it reflects a view, and a view reads to the brain as depth.",
        "how": "Position a large mirror where it catches the window rather than a blank wall. Leaning a full-length mirror in a corner also works and needs no drilling.",
        "queries": ["large mirror reflecting window", "leaning floor mirror apartment", "mirror small room light", "bright reflective interior"],
        "tags": ["mirror", "light", "small space"],
    },
    {
        "title": "Define zones with rugs rather than walls",
        "why": "Open-plan small homes feel chaotic when everything blurs together, but adding partitions makes them smaller. Rugs give you separation without losing sightlines.",
        "how": "Use one rug for the seating zone and a different texture or tone for the dining or work zone. Keep a consistent color story so the two do not fight.",
        "queries": ["studio apartment zones rug", "open plan living dining rug", "small apartment layout zones", "defined seating area rug"],
        "tags": ["zoning", "rug", "small space"],
    },
    {
        "title": "Choose a light, low-contrast wall color",
        "why": "Strong contrast between walls, trim and furniture makes every edge in a room visible, and visible edges make small rooms feel boxed in.",
        "how": "Paint walls, trim and doors in the same color at slightly different sheens. The corners soften and the walls seem to recede.",
        "queries": ["white walls small apartment", "light neutral small room interior", "bright airy small space", "soft painted walls interior"],
        "tags": ["color", "paint", "small space"],
    },
    {
        "title": "Keep the sightline from the front door clear",
        "why": "The first three seconds inside a home set the impression of its size, and whatever blocks that first view makes the whole place feel tighter.",
        "how": "Nothing bulky in the entry path. Use wall hooks instead of a coat rack, a slim console instead of a chest, and keep the floor visible.",
        "queries": ["small entryway apartment interior", "narrow hallway design", "entry hooks small home", "clear apartment entrance"],
        "tags": ["entry", "sightlines", "small space"],
    },
    {
        "title": "Use furniture that can move",
        "why": "A small home has to be a dining room, an office and a lounge on the same day. Fixed layouts fight that.",
        "how": "Lightweight nesting tables, a wheeled cart, stackable chairs and a pouffe that becomes extra seating. Rearranging in ninety seconds is a genuine feature.",
        "queries": ["nesting tables small living room", "rolling cart apartment storage", "flexible furniture small space", "stackable chairs interior"],
        "tags": ["flexibility", "furniture", "small space"],
    },
    {
        "title": "Hang art higher and in a vertical stack",
        "why": "Vertical arrangements draw the eye upward and use the wall height that small rooms usually waste.",
        "how": "Two or three frames stacked in a column, or one tall narrow piece. Keep the frames slim so the wall does not get heavy.",
        "queries": ["vertical gallery wall small room", "tall narrow artwork interior", "stacked frames wall decor", "art in small apartment"],
        "tags": ["art", "vertical", "small space"],
    },
])

_add("home organization", [
    {
        "title": "Give every category one home and one only",
        "why": "Things become clutter when they have no assigned place. Two homes for the same category always turns into zero homes within a month.",
        "how": "Batteries live in one drawer. Chargers live in one box. Write it down for the first few weeks if you share the home with other people.",
        "queries": ["organized drawer household items", "labeled storage boxes home", "tidy home storage system", "organized closet shelves"],
        "tags": ["systems", "clutter", "organization"],
    },
    {
        "title": "Store by frequency, not by category",
        "why": "Perfectly grouped storage often fails because the things you use daily end up behind the things you use twice a year.",
        "how": "Everyday items at waist to shoulder height, weekly items lower, seasonal and rare items high or deep. Rotate as the seasons change.",
        "queries": ["organized cupboard shelves home", "storage shelves labeled boxes", "closet organization system", "practical home storage"],
        "tags": ["systems", "accessibility", "organization"],
    },
    {
        "title": "Use containers that fit the shelf, not the object",
        "why": "Mismatched bins leave gaps that swallow small items and make an otherwise tidy cupboard look chaotic.",
        "how": "Measure the shelf depth and height first, then buy a repeated container size that fills it edge to edge. Consistency does most of the visual work.",
        "queries": ["matching storage bins shelf", "organized pantry containers", "uniform storage baskets closet", "neat shelf organization"],
        "tags": ["containers", "visual order", "organization"],
    },
    {
        "title": "Build a landing zone by the door",
        "why": "Keys, post and bags are dropped within six feet of the entrance whether or not there is somewhere to put them.",
        "how": "One small tray, a hook rail and a basket. Anything more elaborate stops being used within a fortnight.",
        "queries": ["entryway hooks and tray", "hallway key organizer", "entry basket storage home", "organized entry table"],
        "tags": ["entry", "habits", "organization"],
    },
    {
        "title": "Keep a permanent outbox",
        "why": "Decluttering fails when it is an event. A standing container for things leaving the house turns it into a background process.",
        "how": "One box in a cupboard for donations and returns. When it is full, it goes. No decisions, no piles on the dining table.",
        "queries": ["donation box home decluttering", "storage box closet home", "tidy organized cupboard", "minimal home storage"],
        "tags": ["decluttering", "habits", "organization"],
    },
    {
        "title": "Use drawer dividers everywhere, not just in the kitchen",
        "why": "An undivided drawer becomes a mixed pile in about a week regardless of how carefully it was packed.",
        "how": "Adjustable dividers or small open boxes in bathroom, office and bedside drawers. Vertical filing works far better than stacking for clothes and documents.",
        "queries": ["drawer dividers organization", "organized bedroom drawer", "folded clothes drawer vertical", "desk drawer organizer"],
        "tags": ["drawers", "dividers", "organization"],
    },
    {
        "title": "Label anything that is not transparent",
        "why": "Opaque boxes are where possessions go to be forgotten. A label is the difference between storage and a time capsule.",
        "how": "Simple, consistent labels on the front face at eye level. Handwritten on a plain tag looks better than a jumble of printed fonts.",
        "queries": ["labeled storage boxes shelf", "organized labeled pantry", "storage bins with labels", "home organization labels"],
        "tags": ["labels", "systems", "organization"],
    },
    {
        "title": "Hang what you can",
        "why": "Vertical surfaces are the most underused storage in almost every home, and hung items are visible, which means they get used.",
        "how": "Pegboards in the utility room, rails in the kitchen, hooks inside cupboard doors, and a wall-mounted rack in the entry.",
        "queries": ["pegboard wall organization", "kitchen wall rail utensils", "hooks inside cabinet door", "wall mounted storage home"],
        "tags": ["vertical", "hooks", "organization"],
    },
    {
        "title": "Deal with paper the day it arrives",
        "why": "Paper is the fastest-accumulating clutter category in most homes and the hardest to face once it becomes a pile.",
        "how": "One tray for action, one folder for keep, and a bin next to where you open the post. Digitise anything you are keeping only out of anxiety.",
        "queries": ["organized desk paper tray", "home office filing system", "tidy desk documents", "paper organization home"],
        "tags": ["paper", "habits", "organization"],
    },
    {
        "title": "Leave twenty percent of every storage space empty",
        "why": "Storage packed to capacity has no tolerance for real life, and the first busy week collapses the system.",
        "how": "Treat a full shelf as a signal to remove something rather than to buy more containers. Slack is what makes a system survive.",
        "queries": ["spacious organized closet", "half empty shelf storage", "minimal organized cupboard", "clean storage space home"],
        "tags": ["capacity", "systems", "organization"],
    },
    {
        "title": "Run a five-minute reset before bed",
        "why": "Almost all visible mess is created in the last few hours of the day, and clearing it is much faster than a weekend cleanup.",
        "how": "Set a timer, return items to their homes, clear the main surfaces, and stop when it rings. Consistency matters more than thoroughness.",
        "queries": ["tidy living room evening", "clean home surfaces", "organized calm home interior", "tidying up living space"],
        "tags": ["habits", "routine", "organization"],
    },
])


_add("lighting", [
    {
        "title": "Put every bulb in the house at the same color temperature",
        "why": "Mixed bulb temperatures are the invisible reason a room feels wrong. One cool blue lamp beside three warm ones makes the whole space look accidental.",
        "how": "Standardize on 2700 kelvin for living spaces and bedrooms, and 3000 kelvin for kitchens and bathrooms. Replace the odd ones out in a single evening.",
        "queries": ["warm light bulbs interior", "cozy warm lighting home", "living room lamp glow evening", "warm white bulb lamp"],
        "tags": ["bulbs", "color temperature", "lighting"],
    },
    {
        "title": "Aim for at least three light sources per room",
        "why": "One ceiling light produces a flat, shadowless, institutional wash. Multiple pools of light create the depth that makes a room feel considered.",
        "how": "Ceiling for general light, a lamp near seating for reading, and something low or wall-mounted for atmosphere. In the evening, use only the lower two.",
        "queries": ["layered lighting living room", "multiple lamps interior evening", "floor lamp and table lamp", "ambient home lighting"],
        "tags": ["layers", "lamps", "lighting"],
    },
    {
        "title": "Install dimmers on everything you can",
        "why": "Brightness is the fastest way to change the mood of a room, and a fixed level means the room only works properly for part of the day.",
        "how": "Dimmable LED bulbs plus a compatible dimmer switch. If you rent, smart bulbs with a remote give you the same result with no wiring.",
        "queries": ["dimmed interior lighting evening", "adjustable warm lighting room", "soft lit living room night", "mood lighting home"],
        "tags": ["dimmers", "mood", "lighting"],
    },
    {
        "title": "Get some light down near the floor",
        "why": "We associate low, warm light with evening and rest. Rooms lit only from above never quite relax.",
        "how": "A small lamp on a low shelf, an uplight hidden behind a plant, or a lamp on the floor in a corner. One low source changes the entire feel of a room.",
        "queries": ["floor level lamp cozy corner", "uplight behind plant interior", "low warm light living room", "corner lamp glow home"],
        "tags": ["low light", "cozy", "lighting"],
    },
    {
        "title": "Light the walls, not just the middle of the room",
        "why": "Illuminated walls read as expanded space, while a bright center with dark edges makes a room feel like a cave.",
        "how": "Use wall sconces, picture lights, or simply aim a lamp so it washes a wall. Glossy or light-colored paint amplifies the effect.",
        "queries": ["wall sconce lighting interior", "picture light artwork wall", "wall wash lighting home", "illuminated wall living room"],
        "tags": ["walls", "sconces", "lighting"],
    },
    {
        "title": "Hang the dining pendant lower than feels right",
        "why": "A pendant hung too high stops being a light over a table and becomes a light in a room, which loses all the intimacy of dining together.",
        "how": "Thirty to thirty-four inches above the tabletop, centered on the table rather than the room, and always on a dimmer.",
        "queries": ["dining table pendant light", "low hanging lamp dining room", "warm dining room lighting", "pendant above table interior"],
        "tags": ["dining", "pendant", "lighting"],
    },
    {
        "title": "Choose shades that glow rather than shades that block",
        "why": "An opaque shade throws light only up and down. A linen or paper shade turns the whole fixture into a soft glowing object.",
        "how": "Fabric, paper or opal glass shades give diffuse light. Keep opaque metal shades for task lighting where you want a tight pool.",
        "queries": ["linen lampshade warm glow", "paper lantern light interior", "fabric shade table lamp", "soft glowing lamp home"],
        "tags": ["shades", "diffusion", "lighting"],
    },
    {
        "title": "Do not center the ceiling light by default",
        "why": "The middle of the ceiling is almost never where the light is needed, which is why so many rooms have a bright empty center and a dim sofa.",
        "how": "Move or swag the fixture over the actual activity zone, or leave it off entirely and light the room from the perimeter with lamps.",
        "queries": ["ceiling light living room interior", "pendant over seating area", "modern ceiling fixture home", "living room ceiling lamp"],
        "tags": ["placement", "ceiling", "lighting"],
    },
    {
        "title": "Use lighting to signal the end of the day",
        "why": "Light tells your body what time it is. Dropping the light level in the evening improves how a home feels and how well you sleep in it.",
        "how": "Set a habit or a smart schedule that switches off overheads after sunset and leaves only warm, low lamps running.",
        "queries": ["evening home lighting warm", "cozy night interior lamps", "relaxed evening living room", "dim warm home light"],
        "tags": ["routine", "evening", "lighting"],
    },
    {
        "title": "Maximize the daylight you already have",
        "why": "No fixture competes with a clean window. Most homes lose a surprising amount of daylight to heavy treatments and dirty glass.",
        "how": "Clean the windows, cut back anything blocking them outside, mount curtain rods wide so panels clear the glass, and keep sills clear.",
        "queries": ["bright sunlit living room window", "natural daylight interior", "clean window sunlight room", "airy bright home interior"],
        "tags": ["daylight", "windows", "lighting"],
    },
])

_add("colors", [
    {
        "title": "Use the sixty thirty ten split",
        "why": "It is an old rule because it works. It gives a room a dominant tone, a supporting tone and a small amount of energy, in proportions the eye finds restful.",
        "how": "Sixty percent walls and large surfaces, thirty percent upholstery and curtains, ten percent accessories and art. The ten percent is the only part you should change often.",
        "queries": ["balanced color palette living room", "neutral interior with accent color", "coordinated room colors", "modern interior color scheme"],
        "tags": ["palette", "proportion", "color"],
    },
    {
        "title": "Test paint on a board, not on the wall",
        "why": "Patches painted directly over an existing color are contaminated by what surrounds them, and paint reads completely differently on different walls at different times of day.",
        "how": "Paint two coats on a large piece of card, then move it around the room and look at it in morning light, afternoon light and lamp light before deciding.",
        "queries": ["paint color samples wall", "choosing paint swatches interior", "paint testing home wall", "color sample board room"],
        "tags": ["paint", "testing", "color"],
    },
    {
        "title": "Respect the direction your room faces",
        "why": "North-facing rooms receive cool light and will drag a gray or blue paint towards cold. South-facing rooms flood color with warmth all day.",
        "how": "In cool north light, choose colors with a warm base, even for neutrals. In warm south light, cooler and more muted colors hold their character.",
        "queries": ["north facing room natural light", "sunlit warm interior room", "daylight interior wall color", "bright room paint color"],
        "tags": ["light", "orientation", "color"],
    },
    {
        "title": "Choose neutrals with a deliberate undertone",
        "why": "There is no such thing as a neutral without a bias. Beige with a pink undertone next to beige with a green undertone is what makes a room feel muddy.",
        "how": "Hold your samples side by side against a sheet of pure white paper. The undertone becomes obvious immediately. Keep every neutral in the room on the same side.",
        "queries": ["warm neutral interior palette", "beige and cream room design", "greige walls interior", "soft neutral living room"],
        "tags": ["neutrals", "undertone", "color"],
    },
    {
        "title": "Paint the trim the same color as the walls",
        "why": "Bright white trim against a colored wall draws a hard outline around every door and window, which chops up the room.",
        "how": "Use the same color on walls and woodwork with a satin or eggshell finish on the trim. The room reads taller and much more expensive.",
        "queries": ["walls and trim same color", "color drenched room interior", "painted woodwork matching walls", "monochrome painted room"],
        "tags": ["trim", "paint", "color"],
    },
    {
        "title": "Bring the ceiling into the scheme",
        "why": "The ceiling is the largest uninterrupted surface in the room and defaulting it to brilliant white is a wasted opportunity and often a harsh contrast.",
        "how": "Try the wall color at fifty percent strength, or take the full color right over the ceiling in a small room for a cocooning effect.",
        "queries": ["painted ceiling color interior", "colored ceiling room design", "cozy painted room ceiling", "dark ceiling interior"],
        "tags": ["ceiling", "paint", "color"],
    },
    {
        "title": "Pull your palette from something you already own",
        "why": "Choosing colors in the abstract is hard and usually leads to a scheme that does not match anything in the room.",
        "how": "Take a rug, a painting or a favorite textile and lift three tones from it. The palette will already be tested by whoever designed that object.",
        "queries": ["patterned rug color inspiration", "textile color palette interior", "artwork colors room design", "coordinated interior colors"],
        "tags": ["palette", "inspiration", "color"],
    },
    {
        "title": "Add one deep tone to a pale room",
        "why": "All-light schemes can drift into blandness. A single dark element gives the eye a reference point and makes every other color read more clearly.",
        "how": "A charcoal armchair, a black metal lamp, an inky bookcase or a dark timber frame. One percent of the room is enough.",
        "queries": ["dark accent in light room", "black furniture neutral interior", "contrast accent living room", "moody accent bright room"],
        "tags": ["contrast", "accent", "color"],
    },
    {
        "title": "Keep the palette continuous between rooms",
        "why": "Homes feel bigger and calmer when one room flows into the next. A different scheme behind every door makes a house feel like a corridor of unrelated boxes.",
        "how": "Use one base color throughout and change only the accents room to room. Sightlines between spaces are where this matters most.",
        "queries": ["open plan cohesive color scheme", "connected rooms interior palette", "consistent home color design", "hallway into living room"],
        "tags": ["flow", "cohesion", "color"],
    },
    {
        "title": "Let saturated color appear in small doses",
        "why": "A strong color has more impact when it is rare. Spread over a whole room it turns into background noise, and often into regret.",
        "how": "Use your strongest color on cushions, ceramics, book spines, or the inside of a cabinet. It is easier to enjoy and much easier to change.",
        "queries": ["colorful cushions neutral sofa", "bright ceramic vase interior", "accent color detail home", "colorful decor small dose"],
        "tags": ["accents", "saturation", "color"],
    },
])


_add("furniture placement", [
    {
        "title": "Start from the focal point and work outward",
        "why": "Layouts that begin with where the sofa will fit produce rooms that function but never feel resolved. Layouts that begin with what you want to look at almost always work.",
        "how": "Identify the focal point, place the largest seat facing it, then add the secondary seating, then the tables, then the lighting.",
        "queries": ["living room seating facing fireplace", "furniture arrangement modern room", "sofa facing window interior", "living room layout design"],
        "tags": ["layout", "focal point", "placement"],
    },
    {
        "title": "Keep conversation distances under eight feet",
        "why": "Seats placed too far apart make people raise their voices, and rooms where conversation is uncomfortable never get used.",
        "how": "Aim for no more than eight feet between facing seats. In a long room, create two smaller groupings rather than one stretched circle.",
        "queries": ["conversational seating arrangement", "two armchairs facing sofa", "cozy seating group living room", "living room furniture circle"],
        "tags": ["conversation", "layout", "placement"],
    },
    {
        "title": "Give every seat a surface within reach",
        "why": "A chair with nowhere to put a cup is a chair nobody chooses. This one rule quietly determines which seats in your home get used.",
        "how": "A side table, a nesting table, a stool or a wide arm within about two feet of every seat. Height should be close to the arm height of the chair.",
        "queries": ["side table beside armchair", "small table next to sofa", "living room side tables", "stool as side table interior"],
        "tags": ["function", "side tables", "placement"],
    },
    {
        "title": "Angle one piece to break the grid",
        "why": "Rooms where everything is parallel to a wall can feel stiff. A single angled element introduces movement without creating chaos.",
        "how": "Angle one armchair towards the seating group, or turn a rug forty-five degrees in a square room. One angle only, never two.",
        "queries": ["angled armchair living room", "diagonal furniture arrangement", "dynamic living room layout", "corner chair interior design"],
        "tags": ["angles", "movement", "placement"],
    },
    {
        "title": "Balance visual weight across the room",
        "why": "If all the heavy, dark, tall pieces end up on one side, the room feels like it is tipping, even if nobody can name why.",
        "how": "Mentally split the room in half and check that each side carries a similar amount of mass. Balance a tall bookcase with a heavy sofa, not with a floor lamp.",
        "queries": ["balanced living room furniture", "symmetrical interior arrangement", "well proportioned living room", "furniture balance interior design"],
        "tags": ["balance", "composition", "placement"],
    },
    {
        "title": "Leave the corners of the room resolved",
        "why": "Empty, awkward corners are where a room visibly runs out of ideas, and stuffing them with random small objects makes it worse.",
        "how": "A tall plant, a floor lamp, a leaning mirror or a single chair with a small table. One considered object beats three leftovers.",
        "queries": ["corner plant floor lamp living room", "styled room corner interior", "reading nook corner chair", "living room corner decor"],
        "tags": ["corners", "composition", "placement"],
    },
    {
        "title": "Match the coffee table height to the sofa seat",
        "why": "A table much lower than the seat forces an uncomfortable reach, and one much higher blocks the view across the room.",
        "how": "Aim within an inch or two of the sofa seat height, and choose a length roughly two-thirds of the sofa. Round tables work better in tight or high-traffic rooms.",
        "queries": ["coffee table proportion sofa", "round coffee table living room", "wooden coffee table interior", "living room table height"],
        "tags": ["proportion", "coffee table", "placement"],
    },
    {
        "title": "Do not block the window",
        "why": "Daylight is the most valuable thing in a room, and a tall piece of furniture in front of the glass costs you light in every direction.",
        "how": "Keep anything above windowsill height away from the window wall. If a piece must go there, choose something low or open in construction.",
        "queries": ["clear window living room interior", "low furniture under window", "bright window natural light room", "unobstructed window interior"],
        "tags": ["windows", "daylight", "placement"],
    },
    {
        "title": "Plan the television into the room from the start",
        "why": "A screen bolted onto a finished room always looks like an intruder, and rooms designed around a screen alone are unpleasant when it is off.",
        "how": "Mount it at seated eye level, surround it with cabinetry or a dark wall so it disappears, and give the room a second reason to exist beyond the screen.",
        "queries": ["built in media wall television", "tv integrated cabinetry living room", "dark wall behind tv", "modern living room with tv"],
        "tags": ["television", "media", "placement"],
    },
    {
        "title": "Measure the room before you buy anything",
        "why": "Furniture almost always looks smaller in a showroom, and returning a sofa is one of the most expensive mistakes in home decorating.",
        "how": "Tape the outline of a piece on the floor with painter's tape and live with it for two days. Check doorways, stair turns and lift dimensions too.",
        "queries": ["measuring room floor plan", "tape measure interior planning", "empty room before furniture", "room layout planning"],
        "tags": ["measuring", "planning", "placement"],
    },
])

_add("storage", [
    {
        "title": "Build storage up to the ceiling on one wall",
        "why": "Full-height storage on a single wall gives you far more capacity than low units scattered around the room, and it reads as architecture rather than furniture.",
        "how": "Choose one wall, run cabinetry or shelving to the ceiling, and paint it the same color as the walls so it recedes.",
        "queries": ["floor to ceiling built in storage", "full height cabinets living room", "built in shelving wall", "white built in storage interior"],
        "tags": ["built ins", "vertical", "storage"],
    },
    {
        "title": "Use the space under the bed properly",
        "why": "It is often the single largest unused volume in a home, and it is already hidden.",
        "how": "Flat rolling boxes with lids, vacuum bags for seasonal bedding, or a bed frame with integrated drawers. Keep a written list of what is down there.",
        "queries": ["under bed storage drawers", "bed with storage boxes", "organized under bed containers", "bedroom storage solutions"],
        "tags": ["under bed", "hidden", "storage"],
    },
    {
        "title": "Choose closed storage for the mess and open storage for the good stuff",
        "why": "All-open storage forces you to curate constantly, and all-closed storage makes a room feel like a corridor of doors.",
        "how": "A roughly seventy thirty split, closed to open. Put books, ceramics and objects on show, and everything with a barcode behind a door.",
        "queries": ["mix open and closed shelving", "cabinet with open shelf living room", "styled shelving with cabinets", "storage unit interior design"],
        "tags": ["open vs closed", "balance", "storage"],
    },
    {
        "title": "Turn the space above doors into shelving",
        "why": "There is usually twelve to eighteen inches of dead wall above every internal door in a home.",
        "how": "A single shelf over the door in a hallway, office or utility room is ideal for rarely used items and looks deliberate when it runs wall to wall.",
        "queries": ["shelf above door storage", "high shelf hallway interior", "over door storage home", "narrow high shelf room"],
        "tags": ["vertical", "unused space", "storage"],
    },
    {
        "title": "Add a bench with storage in the entry",
        "why": "It solves shoes, bags and sitting down to put boots on in a single piece, in the room with the least space to spare.",
        "how": "A bench with baskets underneath or a hinged lid, plus hooks above at around sixty inches. Keep the floor beneath it clear.",
        "queries": ["entryway bench with baskets", "mudroom storage bench", "hallway bench hooks", "entry storage furniture"],
        "tags": ["entry", "bench", "storage"],
    },
    {
        "title": "Use the back of every cupboard door",
        "why": "That surface is free, invisible when closed, and perfectly sized for the flat items that clutter shelves.",
        "how": "Adhesive racks for foil and wraps, a small caddy for cleaning products, or a hook rail for measuring cups. Check the door clears the shelves first.",
        "queries": ["cabinet door organizer rack", "inside cupboard door storage", "kitchen door mounted storage", "organized cabinet interior"],
        "tags": ["doors", "hidden", "storage"],
    },
    {
        "title": "Double your wardrobe rail",
        "why": "A single rail wastes roughly half the height of most wardrobes, because shirts and folded trousers do not need six feet of hanging space.",
        "how": "Add a second rail below the first for short items, and reserve one full-height section for coats and dresses.",
        "queries": ["double hanging rail wardrobe", "organized closet clothes rail", "wardrobe interior organization", "closet system hanging"],
        "tags": ["wardrobe", "clothes", "storage"],
    },
    {
        "title": "Choose furniture that hides things",
        "why": "In a home without a spare room, storage has to be inside the furniture you already need.",
        "how": "Ottomans with lids, benches with cavities, beds with drawers, coffee tables with a lower shelf, and side tables with a cabinet rather than an open frame.",
        "queries": ["storage ottoman coffee table", "furniture with hidden storage", "bench with storage interior", "multifunctional storage furniture"],
        "tags": ["furniture", "hidden", "storage"],
    },
    {
        "title": "Keep the top of the wardrobe deliberate",
        "why": "It becomes a dumping ground by default, and a jumble of suitcases and boxes at eye level makes an entire bedroom look untidy.",
        "how": "Use matched boxes or baskets in a color close to the wall, all the same height, lined up front to back.",
        "queries": ["baskets on top of wardrobe", "matching storage boxes closet", "organized wardrobe top shelf", "neat bedroom storage"],
        "tags": ["wardrobe", "visual order", "storage"],
    },
    {
        "title": "Store seasonal items far away on purpose",
        "why": "Prime storage should hold what you use weekly. Christmas decorations do not deserve the hall cupboard.",
        "how": "Loft, garage, high shelves or under-bed boxes for anything used once or twice a year, clearly labeled with the season on the front.",
        "queries": ["seasonal storage boxes attic", "labeled storage containers garage", "long term home storage", "stacked storage boxes"],
        "tags": ["seasonal", "prioritisation", "storage"],
    },
])


_add("expensive look", [
    {
        "title": "Replace every visible plastic switch plate and vent",
        "why": "Yellowed plastic hardware is a small detail that the eye registers as cheapness across the whole room, usually without consciously noticing it.",
        "how": "Screwless metal or painted plates, matched throughout the home. It costs a few dollars per plate and takes a screwdriver and one afternoon.",
        "queries": ["modern light switch plate wall", "metal outlet cover interior", "clean wall detail home", "minimal switch plate design"],
        "tags": ["details", "hardware", "expensive"],
    },
    {
        "title": "Upgrade the door handles",
        "why": "You touch them dozens of times a day, and a solid metal lever feels and sounds completely different from a hollow builder-grade knob.",
        "how": "Choose one finish for the whole floor and check the backset measurement before ordering. Solid brass or stainless has real weight in the hand.",
        "queries": ["brass door handle detail", "modern door hardware interior", "door lever closeup home", "elegant door handle design"],
        "tags": ["hardware", "doors", "expensive"],
    },
    {
        "title": "Get rid of the shine",
        "why": "High-gloss surfaces read as inexpensive because most cheap materials are glossy, while genuinely expensive materials tend to be matte, honed or textured.",
        "how": "Choose matte or eggshell paint, honed stone rather than polished, brushed metal rather than chrome, and fabrics with visible weave.",
        "queries": ["matte finish interior surfaces", "honed stone countertop", "brushed metal detail interior", "textured fabric upholstery"],
        "tags": ["finishes", "materials", "expensive"],
    },
    {
        "title": "Make the window treatments oversized",
        "why": "Generous fabric is one of the clearest signals of money in a room, because skimpy curtains are the default in every rental.",
        "how": "Panels roughly twice the width of the window so they still look full when closed, hung high and wide, and hemmed to just kiss the floor.",
        "queries": ["full length curtains luxury interior", "generous drapes living room", "linen curtain panels window", "elegant window treatment"],
        "tags": ["curtains", "fabric", "expensive"],
    },
    {
        "title": "Invest in one real material and let the rest be simple",
        "why": "A room with one genuinely good piece and simple supporting elements reads far more expensive than a room full of imitations.",
        "how": "Real stone, solid wood, wool or leather in a single visible place. A solid oak table surrounded by simple chairs beats a full set of veneer.",
        "queries": ["solid wood dining table interior", "marble surface detail home", "leather armchair interior", "natural stone material interior"],
        "tags": ["materials", "investment", "expensive"],
    },
    {
        "title": "Hide the cables completely",
        "why": "Visible wiring is the fastest way to undo an otherwise carefully composed room, because no photographed interior ever has it.",
        "how": "Cable channels painted to match the wall, adhesive clips along the back of furniture, and a box for the power strip. Budget an hour per room.",
        "queries": ["hidden cable management interior", "clean wall no cables", "tidy tv wall setup", "organized home electronics"],
        "tags": ["details", "cables", "expensive"],
    },
    {
        "title": "Frame things properly",
        "why": "A wide mount and a decent frame transform an inexpensive print, while a cheap frame diminishes even a good piece of art.",
        "how": "Use a generous white mount, at least two to three inches, and a simple wood or metal frame. Consistent framing across a wall is what makes a gallery look curated.",
        "queries": ["framed art with wide mat", "gallery wall framed prints", "minimal frame artwork wall", "art framing interior detail"],
        "tags": ["art", "framing", "expensive"],
    },
    {
        "title": "Keep the surfaces mostly empty",
        "why": "Restraint reads as confidence. Expensive interiors are defined as much by what has been left out as by what has been bought.",
        "how": "Aim for roughly two-thirds of every horizontal surface to stay clear. Remove three things from each room and see whether you miss any of them.",
        "queries": ["minimal styled surfaces interior", "clean uncluttered living room", "empty console table styling", "calm minimal home"],
        "tags": ["editing", "minimalism", "expensive"],
    },
    {
        "title": "Buy one bigger thing instead of three medium things",
        "why": "Scale is expensive to fake. One oversized mirror, lamp or artwork will always look more considered than a wall of small purchases.",
        "how": "Set the budget you were going to spread across several items and spend it in one place, on the largest piece the wall can carry.",
        "queries": ["oversized mirror living room", "large statement lamp interior", "big artwork above sofa", "large scale decor interior"],
        "tags": ["scale", "investment", "expensive"],
    },
    {
        "title": "Add architectural detail to a plain room",
        "why": "Modern boxes lack the moldings, paneling and depth that make older rooms feel valuable, and that flatness reads as builder-grade.",
        "how": "Simple wall paneling, a slightly deeper skirting board, or a picture rail. Even a plain batten grid on one wall changes how a room is read.",
        "queries": ["wall paneling interior detail", "molding trim wall design", "wainscoting living room", "architectural wall detail home"],
        "tags": ["architecture", "detail", "expensive"],
    },
    {
        "title": "Keep every metal finish in the room to two at most",
        "why": "Random mixes of chrome, nickel, brass and black are the definition of an unplanned interior.",
        "how": "Choose a dominant finish and one accent. Spray paint is a legitimate fix for a single mismatched fixture you cannot replace.",
        "queries": ["brass and black hardware interior", "matching metal finishes home", "metal fixture detail interior", "coordinated hardware design"],
        "tags": ["metals", "consistency", "expensive"],
    },
])

_add("interior design mistakes", [
    {
        "title": "Pushing all the furniture against the walls",
        "why": "It feels like it creates space, but it actually creates a doughnut: a hollow middle with no gathering point and a room that feels like a waiting area.",
        "how": "Pull the seating in, let the rug define the group, and use the perimeter for storage and lighting rather than for seating.",
        "queries": ["furniture against wall living room", "empty center living room", "living room layout mistake", "spacious room arrangement"],
        "tags": ["layout", "mistake"],
    },
    {
        "title": "Buying a rug that is too small",
        "why": "It is the single most common decorating mistake, and it makes the whole seating arrangement look like it was assembled from leftovers.",
        "how": "Size up so at least the front legs of all seating rest on the rug. If budget is the problem, layer a smaller good rug over a large inexpensive jute one.",
        "queries": ["small rug under coffee table", "large area rug living room", "layered rugs interior", "correct rug size room"],
        "tags": ["rug", "scale", "mistake"],
    },
    {
        "title": "Relying on a single ceiling light",
        "why": "One overhead source flattens everything, drains color, and makes an evening room feel like an office.",
        "how": "Add at least two lamps at different heights and put the overhead on a dimmer or switch it off entirely after dark.",
        "queries": ["single ceiling light room", "layered lamp lighting interior", "dim evening living room", "warm lamps home"],
        "tags": ["lighting", "mistake"],
    },
    {
        "title": "Hanging art too high",
        "why": "Art floating near the ceiling detaches from the furniture and leaves an awkward gap that the eye keeps returning to.",
        "how": "Center at fifty-seven to sixty inches from the floor, and no more than eight inches above the back of a sofa.",
        "queries": ["art hung above sofa correct height", "wall art placement interior", "framed picture wall living room", "gallery wall height"],
        "tags": ["art", "mistake"],
    },
    {
        "title": "Matching every piece from one collection",
        "why": "A complete matching set looks like a showroom floor rather than a home, and it removes all the tension that makes a room interesting.",
        "how": "Keep one or two pieces from the set and swap the rest for something with a different wood tone, era or material.",
        "queries": ["mixed furniture styles living room", "eclectic interior design", "vintage and modern mix room", "varied wood tones interior"],
        "tags": ["matching", "mistake"],
    },
    {
        "title": "Choosing the paint color first",
        "why": "Paint is the most flexible element in the room and there are thousands of options, so choosing it before anything else makes everything after it harder.",
        "how": "Pick the rug, the sofa fabric or the tile first, because those have far fewer options, then find a paint that supports them.",
        "queries": ["paint samples and fabric swatches", "interior design mood board", "choosing materials interior", "fabric and paint selection"],
        "tags": ["process", "paint", "mistake"],
    },
    {
        "title": "Ignoring scale entirely",
        "why": "A tiny lamp on a large console, a huge sectional in a small room, or a narrow rug in a wide space all read as errors even to people who cannot explain why.",
        "how": "Work in proportions: art two-thirds of the furniture width, coffee table two-thirds of the sofa, lamp roughly one and a half times the table height.",
        "queries": ["proportion in interior design", "correctly scaled furniture room", "large lamp on console", "well proportioned interior"],
        "tags": ["scale", "proportion", "mistake"],
    },
    {
        "title": "Leaving the room without any texture",
        "why": "A room can have a perfect palette and correct proportions and still feel cold if every surface is smooth and flat.",
        "how": "Add wool, linen, rattan, unglazed ceramic or raw wood. Texture is what photographs cannot fully capture and what people feel when they walk in.",
        "queries": ["textured interior materials", "wool throw linen cushions", "rattan basket interior", "natural texture living room"],
        "tags": ["texture", "mistake"],
    },
    {
        "title": "Decorating every surface",
        "why": "Filling every shelf and table with objects creates visual noise, and visual noise is the enemy of the calm that makes a home feel good.",
        "how": "Style in clusters with real gaps between them. Negative space is a design element, not an unfinished area.",
        "queries": ["minimal shelf styling interior", "uncluttered surfaces home", "negative space interior design", "simple styled console"],
        "tags": ["clutter", "editing", "mistake"],
    },
    {
        "title": "Forgetting about the ceiling and the floor",
        "why": "Most people decorate a band of wall between three and six feet high and leave the two largest surfaces in the room untouched.",
        "how": "Consider a paint color above, a substantial rug below, and lighting that connects the two. It changes rooms more than another cushion ever will.",
        "queries": ["painted ceiling interior design", "large rug and ceiling color", "full room design floor ceiling", "complete interior scheme"],
        "tags": ["ceiling", "floor", "mistake"],
    },
    {
        "title": "Buying everything at once",
        "why": "A room furnished in a single weekend has no depth, and it usually locks in decisions that a few weeks of living in the space would have changed.",
        "how": "Buy the largest anchor pieces first, live with them, and add the layers over months. The room will be better and cheaper.",
        "queries": ["partially furnished room interior", "evolving living room design", "minimal furnished apartment", "new home empty room"],
        "tags": ["process", "patience", "mistake"],
    },
])


_add("budget decorating", [
    {
        "title": "Paint is still the best value in decorating",
        "why": "Nothing else changes a room this much for this little. A hundred dollars of paint outperforms a thousand dollars of accessories every time.",
        "how": "Prioritize the room you spend the most waking hours in, buy the better paint rather than the cheaper one, and do the prep properly.",
        "queries": ["painting a room interior", "paint roller wall home", "freshly painted living room", "wall painting renovation"],
        "tags": ["paint", "value", "budget"],
    },
    {
        "title": "Shop secondhand for solid wood",
        "why": "Older furniture is frequently built from solid timber that no longer exists at entry-level prices, and it can be refinished indefinitely.",
        "how": "Search for sideboards, dressers, dining tables and desks. Check the joints and the drawer runners, ignore the finish, and budget for new hardware.",
        "queries": ["vintage wooden sideboard interior", "secondhand furniture restored", "antique dresser modern room", "wooden furniture detail"],
        "tags": ["secondhand", "wood", "budget"],
    },
    {
        "title": "Change the legs, the knobs, or the top",
        "why": "Flat-pack furniture is usually let down by one component. Replacing that component costs a fraction of replacing the piece.",
        "how": "Tapered wooden legs, solid metal handles or a new timber top can make a basic cabinet look like a considered piece.",
        "queries": ["furniture upgrade wooden legs", "cabinet with new hardware", "diy furniture makeover", "modified flat pack furniture"],
        "tags": ["hacks", "upgrade", "budget"],
    },
    {
        "title": "Spend the money where you touch it",
        "why": "Budget goes furthest in the things your body contacts daily: the mattress, the sofa seat, the towels, the taps.",
        "how": "Buy well once for those, and save on anything decorative that can be swapped cheaply later, such as cushions, art and vases.",
        "queries": ["comfortable sofa interior", "quality bedding bedroom", "soft towels bathroom", "cozy home comfort"],
        "tags": ["priorities", "value", "budget"],
    },
    {
        "title": "Use large-format inexpensive art",
        "why": "Scale costs almost nothing when the artwork is a print, and one large piece has more impact than a dozen small purchases.",
        "how": "Print an open-licence image or your own photograph at a large size, then spend the money on the frame and the mount instead.",
        "queries": ["large framed print living room", "poster art frame interior", "big artwork budget decor", "print above sofa"],
        "tags": ["art", "scale", "budget"],
    },
    {
        "title": "Buy plants small and let them grow",
        "why": "A mature indoor tree costs several hundred dollars. The same plant at two feet tall costs a fraction and gets there on its own.",
        "how": "Choose fast growers such as monstera, rubber plant or golden pothos, put them in the best light you have, and repot once a year.",
        "queries": ["small indoor plants growing", "potted plants living room", "houseplants interior decor", "green plants windowsill"],
        "tags": ["plants", "patience", "budget"],
    },
    {
        "title": "Shop your own home before you shop anywhere else",
        "why": "Most homes contain the raw material for a much better arrangement, and moving things between rooms costs nothing.",
        "how": "Take everything decorative off the surfaces in three rooms, pile it in one place, and redistribute deliberately. It reliably produces at least two improvements.",
        "queries": ["rearranging home decor items", "styled shelf with objects", "home decor accessories", "restyled living room"],
        "tags": ["free", "restyling", "budget"],
    },
    {
        "title": "Look for end-of-line and floor models",
        "why": "The same piece is often forty percent cheaper simply because the color is being discontinued or a corner has a scuff.",
        "how": "Ask directly about clearance and ex-display stock in store, and check outlet sections online. Inspect carefully and negotiate on visible marks.",
        "queries": ["furniture showroom display", "sofa in store interior", "modern furniture shop", "living room furniture selection"],
        "tags": ["shopping", "deals", "budget"],
    },
    {
        "title": "Use peel-and-stick where the risk is low",
        "why": "Removable film has become genuinely convincing for small areas, and it lets you test a bold idea for the price of a takeaway.",
        "how": "Best on a small backsplash, inside a bookcase, or on drawer fronts. Clean and dry the surface first, and work from the center outward.",
        "queries": ["peel and stick backsplash kitchen", "removable wallpaper interior", "diy wall covering home", "renter friendly wall decor"],
        "tags": ["diy", "temporary", "budget"],
    },
    {
        "title": "Improve what you already own before adding anything",
        "why": "Cleaning, repairing and tightening what is already in the room often delivers more than a new purchase, and it costs an afternoon.",
        "how": "Wash the curtains, deep-clean the rug, tighten every screw in the dining chairs, and oil the wooden surfaces. The room will look noticeably better.",
        "queries": ["cleaning home interior surfaces", "restored wooden furniture", "fresh clean living room", "home maintenance interior"],
        "tags": ["maintenance", "free", "budget"],
    },
])

_add("renter-friendly decorating", [
    {
        "title": "Use tension rods instead of drilling",
        "why": "Most of the highest-impact renter changes involve hanging something, and tension rods remove the permission problem entirely.",
        "how": "Tension rods work for curtains inside a recess, for a small closet rail, and under the sink for spray bottles. Check the weight rating.",
        "queries": ["tension rod curtains window", "renter friendly curtain solution", "no drill window treatment", "apartment window curtains"],
        "tags": ["no drill", "renting", "renter"],
    },
    {
        "title": "Cover the floor you cannot change",
        "why": "Bad flooring is the most common complaint in rented homes, and it is also one of the easiest things to hide.",
        "how": "A very large low-pile rug covering most of the visible floor, or interlocking wood-effect tiles in a small room. Keep the original underneath intact.",
        "queries": ["large rug covering carpet", "renter apartment floor rug", "layered rug over carpet", "temporary floor covering"],
        "tags": ["flooring", "cover", "renter"],
    },
    {
        "title": "Replace the light fixtures and keep the originals in a box",
        "why": "Rental light fittings are chosen for price, and swapping them is the fastest way to make a generic apartment feel like yours.",
        "how": "Turn the power off at the breaker, swap the fitting, and store the original carefully to reinstall when you leave. Plug-in pendants avoid wiring altogether.",
        "queries": ["pendant lamp apartment interior", "replacing ceiling light fixture", "plug in pendant light room", "modern apartment lighting"],
        "tags": ["lighting", "reversible", "renter"],
    },
    {
        "title": "Use removable wallpaper on one wall only",
        "why": "One wall gives you the character change without the removal risk of a whole room, and it is the cheapest way to add architecture.",
        "how": "Choose a wall without many outlets or corners, clean it thoroughly, and test a small strip in a hidden area first for paint adhesion.",
        "queries": ["removable wallpaper accent wall", "patterned wall apartment", "peel and stick wallpaper bedroom", "feature wall interior"],
        "tags": ["wallpaper", "temporary", "renter"],
    },
    {
        "title": "Add freestanding storage that leaves with you",
        "why": "Built-ins are not an option, but tall freestanding units can do the same job and become an asset in the next home.",
        "how": "Choose full-height shelving or wardrobes on adjustable feet, and secure them with an anti-tip strap that needs only one small screw.",
        "queries": ["freestanding tall shelving unit", "portable wardrobe apartment", "modular storage renter", "bookshelf apartment interior"],
        "tags": ["storage", "portable", "renter"],
    },
    {
        "title": "Swap the shower head and the tap aerators",
        "why": "Two small components change the daily experience of a rented bathroom and kitchen more than anything decorative can.",
        "how": "Both unscrew by hand or with a wrench. Keep the originals, use plumber's tape on the threads, and take yours with you when you move.",
        "queries": ["shower head replacement bathroom", "kitchen tap aerator detail", "modern shower fixture", "bathroom upgrade renter"],
        "tags": ["fixtures", "reversible", "renter"],
    },
    {
        "title": "Hide the countertop you dislike",
        "why": "Rental worktops are often the ugliest surface in the home, and they are also the largest visible one in the kitchen.",
        "how": "Large wooden boards, a butcher-block offcut sized to the run, or a removable cover film. Even a wide chopping board changes the visual weight.",
        "queries": ["wooden board over kitchen counter", "butcher block counter cover", "kitchen counter styling", "renter kitchen upgrade"],
        "tags": ["kitchen", "cover", "renter"],
    },
    {
        "title": "Hang art without a single hole",
        "why": "The rules about wall damage are the main reason rented homes stay bare, and bare walls are what make them feel temporary.",
        "how": "Adhesive hanging strips rated well above the frame weight, picture ledges fixed with heavy-duty strips, or large pieces simply leaned on furniture.",
        "queries": ["leaning artwork against wall", "picture ledge shelf art", "art without nails apartment", "framed art on console"],
        "tags": ["art", "no damage", "renter"],
    },
    {
        "title": "Make the entry yours in one square meter",
        "why": "The entrance sets the tone for the whole home, and it is small enough that a complete change costs very little.",
        "how": "A freestanding hook rail or coat stand, a small rug, a mirror leaned or hung with adhesive, and a tray for keys.",
        "queries": ["small apartment entryway decor", "coat rack hallway home", "entry mirror and rug", "apartment entrance interior"],
        "tags": ["entry", "impact", "renter"],
    },
    {
        "title": "Take photographs on the day you move in",
        "why": "Beyond protecting your deposit, having the original state on record makes you far more willing to make temporary changes.",
        "how": "Photograph every wall, every fixture and every mark, timestamped, and store the originals of anything you replace in one labeled box.",
        "queries": ["empty apartment interior room", "moving into new apartment", "bare rental room", "apartment before decorating"],
        "tags": ["practical", "deposit", "renter"],
    },
])


_add("cozy homes", [
    {
        "title": "Turn off the big light",
        "why": "Coziness is mostly a lighting phenomenon. Low, warm, multiple sources tell the nervous system that the day is over.",
        "how": "Three to five small warm lamps, none of them on the ceiling, all around 2200 to 2700 kelvin. Add candles for the last hour of the evening.",
        "queries": ["cozy lamp lit living room", "candles warm interior evening", "hygge home lighting", "warm glow living room night"],
        "tags": ["lighting", "evening", "cozy"],
    },
    {
        "title": "Put something soft within reach of every seat",
        "why": "Coziness is tactile before it is visual. A room without anything to touch reads as a showroom no matter how good it looks.",
        "how": "A wool or mohair throw on the sofa arm, a sheepskin over a hard chair, a cushion with real depth. Choose fibers that feel good rather than fibers that photograph well.",
        "queries": ["wool throw blanket sofa", "soft cushions cozy living room", "sheepskin on chair interior", "textured blanket home"],
        "tags": ["textiles", "touch", "cozy"],
    },
    {
        "title": "Lower the ceiling visually",
        "why": "Very tall rooms can feel grand and cold at the same time. Bringing the perceived ceiling down creates intimacy.",
        "how": "Hang pendants lower, paint the ceiling a deeper tone, add a picture rail, or use tall bookshelves that stop below the ceiling line.",
        "queries": ["low hanging pendant lamp room", "dark ceiling cozy interior", "picture rail wall detail", "intimate room interior"],
        "tags": ["ceiling", "intimacy", "cozy"],
    },
    {
        "title": "Create one enclosed corner",
        "why": "People instinctively prefer seats with something solid behind them and a view out. It is why the corner table in a restaurant goes first.",
        "how": "Put a chair in a corner with a lamp, a small table and something at your back, facing into the room or towards a window.",
        "queries": ["reading nook corner chair", "cozy corner armchair lamp", "window seat with cushions", "quiet corner interior"],
        "tags": ["nook", "seating", "cozy"],
    },
    {
        "title": "Soften the hard surfaces",
        "why": "Rooms that echo feel cold, and echo comes from bare floors, glass and plaster with nothing to absorb sound.",
        "how": "Rugs, curtains, upholstery and books all absorb sound. A full bookshelf is one of the most effective acoustic treatments there is.",
        "queries": ["bookshelf full of books interior", "curtains and rug cozy room", "upholstered furniture warm room", "soft furnishings living room"],
        "tags": ["acoustics", "textiles", "cozy"],
    },
    {
        "title": "Use warm wood tones rather than gray ones",
        "why": "Cool gray timbers were everywhere for a decade and they read as cold under artificial light, which is exactly when you want warmth.",
        "how": "Look for oak, walnut and pine with honey or amber undertones, and mix two tones rather than matching everything exactly.",
        "queries": ["warm wood furniture interior", "oak table cozy room", "walnut wood detail home", "natural wood tones interior"],
        "tags": ["wood", "warmth", "cozy"],
    },
    {
        "title": "Add scent and sound deliberately",
        "why": "Two of the five senses are usually ignored in decorating, and both change how a room feels far faster than furniture does.",
        "how": "One consistent scent for the home, and a low background of music or nothing at all. Avoid stacking several competing fragrances.",
        "queries": ["scented candle interior detail", "cozy home atmosphere", "warm living room ambience", "relaxing home interior"],
        "tags": ["senses", "atmosphere", "cozy"],
    },
    {
        "title": "Let the room look lived in",
        "why": "Perfectly staged rooms are impressive and unwelcoming. A little visible life is what separates a home from a display.",
        "how": "Leave the book you are reading out, the blanket half folded, the flowers slightly past their peak. Curated imperfection is a real technique.",
        "queries": ["lived in cozy living room", "open book on sofa", "casual home interior", "relaxed styled living room"],
        "tags": ["styling", "authenticity", "cozy"],
    },
])

_add("minimalist design", [
    {
        "title": "Minimalism is about editing, not about buying white things",
        "why": "The look is a by-product of removing what does not earn its place. Buying a minimalist-styled object to add to a full room is the opposite of the idea.",
        "how": "Start by removing rather than adding. Take everything off a surface, then put back only what you use or genuinely love.",
        "queries": ["minimalist living room interior", "uncluttered white room", "simple modern interior", "clean minimal space"],
        "tags": ["philosophy", "editing", "minimalist"],
    },
    {
        "title": "Give minimal rooms real texture",
        "why": "Without pattern and color to carry interest, texture has to do all the work, otherwise the room looks unfinished rather than restrained.",
        "how": "Plaster, linen, oak, wool, unglazed ceramic and stone. Keep the palette narrow and let the surfaces vary.",
        "queries": ["textured minimal interior plaster", "linen and wood minimal room", "natural materials minimalist home", "warm minimalist interior"],
        "tags": ["texture", "materials", "minimalist"],
    },
    {
        "title": "Hide the storage completely",
        "why": "Minimal interiors are not homes with fewer possessions, they are usually homes with better concealment.",
        "how": "Handleless full-height cabinetry, push-to-open fronts, and cupboards painted the wall color so they disappear.",
        "queries": ["handleless cabinets minimal interior", "concealed storage wall", "flush cabinetry modern home", "hidden storage minimalist"],
        "tags": ["storage", "concealment", "minimalist"],
    },
    {
        "title": "Choose one object per surface",
        "why": "A single well-chosen object reads as intentional. Three read as a collection. Seven read as clutter.",
        "how": "One sculptural piece, one stack of books, or one branch in a vessel. Rotate rather than accumulate.",
        "queries": ["single vase on table minimal", "sculptural object interior", "minimal styled surface", "one object shelf styling"],
        "tags": ["styling", "restraint", "minimalist"],
    },
    {
        "title": "Keep the palette to three tones",
        "why": "Color restraint is what makes minimal rooms feel calm rather than sparse. More tones need more visual management.",
        "how": "A warm off-white, a mid natural tone, and one deeper grounding color. Everything else comes from material, not from pigment.",
        "queries": ["neutral minimal color palette", "monochrome interior design", "beige and white minimal room", "quiet color scheme interior"],
        "tags": ["color", "restraint", "minimalist"],
    },
    {
        "title": "Let light be the decoration",
        "why": "In a minimal room, the moving shadow of a window frame across a wall is genuinely the most interesting thing in the space.",
        "how": "Keep windows unobstructed, use sheer or no curtains where privacy allows, and choose surfaces that show the way light falls across them.",
        "queries": ["sunlight shadows on wall interior", "bright minimal room daylight", "light through window minimal", "sunlit empty room"],
        "tags": ["light", "shadow", "minimalist"],
    },
    {
        "title": "Buy fewer things of better quality",
        "why": "When there is very little in a room, everything present is examined closely, and poor construction becomes obvious.",
        "how": "Spend the same total budget on half as many pieces. Solid joinery, natural fibers and honest materials age well under scrutiny.",
        "queries": ["quality wooden furniture minimal", "well made chair interior", "craftsmanship furniture detail", "solid wood minimal design"],
        "tags": ["quality", "investment", "minimalist"],
    },
    {
        "title": "Leave negative space on purpose",
        "why": "Empty wall and empty floor are not failures to decorate, they are what give the remaining objects room to be seen.",
        "how": "Resist the urge to fill the last blank wall. Give at least one wall in every room nothing at all.",
        "queries": ["empty wall minimal interior", "negative space room design", "spacious minimal living room", "bare wall modern interior"],
        "tags": ["space", "restraint", "minimalist"],
    },
])

_add("scandinavian design", [
    {
        "title": "Start with a warm white, not a cool one",
        "why": "Scandinavian interiors are bright because the daylight is scarce, but the whites used are almost always warm to compensate for cold northern light.",
        "how": "Choose whites with a hint of yellow or gray-green rather than blue, and use them on walls, ceilings and trim alike.",
        "queries": ["scandinavian white interior room", "bright nordic living room", "white walls wooden floor", "airy scandinavian home"],
        "tags": ["color", "white", "scandinavian"],
    },
    {
        "title": "Use pale wood generously",
        "why": "Light oak, ash and birch are the signature of the style and they add warmth without darkening the room.",
        "how": "Floors, chair frames, table tops and shelving in the same pale timber family. Avoid mixing in heavy dark woods.",
        "queries": ["light oak floor scandinavian", "birch wood furniture interior", "pale wood dining table", "nordic wooden interior"],
        "tags": ["wood", "materials", "scandinavian"],
    },
    {
        "title": "Keep the furniture legs slim and visible",
        "why": "The lightness of Scandinavian rooms comes as much from the silhouettes as from the color. Bulky bases fight the whole look.",
        "how": "Tapered wooden legs, thin metal frames, and pieces that sit clear of the floor. Nothing should look heavier than it needs to be.",
        "queries": ["scandinavian sofa slim legs", "mid century wooden chair interior", "light furniture nordic room", "minimal furniture design"],
        "tags": ["furniture", "silhouette", "scandinavian"],
    },
    {
        "title": "Add one black element per room",
        "why": "Pure light schemes need an anchor. A single black line gives the eye a reference and stops the room reading as washed out.",
        "how": "A black pendant, a black window frame, a slim black shelf bracket or a dark picture frame. Keep it graphic and small.",
        "queries": ["black pendant lamp white room", "black frame window interior", "monochrome scandinavian detail", "black accent nordic interior"],
        "tags": ["contrast", "accent", "scandinavian"],
    },
    {
        "title": "Layer natural textiles rather than patterns",
        "why": "The warmth in these rooms comes from wool, sheepskin and linen, not from decorative pattern, which is used very sparingly.",
        "how": "Undyed wool throws, linen cushions, a flatweave or sheepskin over pale flooring. Keep pattern to one small geometric if any.",
        "queries": ["wool throw scandinavian sofa", "linen cushions nordic interior", "sheepskin chair scandinavian", "natural textiles bright room"],
        "tags": ["textiles", "texture", "scandinavian"],
    },
    {
        "title": "Bring in living greenery",
        "why": "A few plants supply the only strong color in an otherwise pale room and are a core part of the style rather than an afterthought.",
        "how": "Simple green foliage in plain ceramic or terracotta pots, or a branch of eucalyptus in a clear glass vessel.",
        "queries": ["plant in white ceramic pot interior", "green plant scandinavian room", "branches in vase minimal", "indoor greenery nordic home"],
        "tags": ["plants", "green", "scandinavian"],
    },
    {
        "title": "Keep window treatments minimal",
        "why": "Every bit of daylight matters in the original climate this style comes from, and heavy drapes contradict the entire idea.",
        "how": "Sheer linen panels, simple roller blinds, or bare windows where privacy allows. Never anything that covers the glass during the day.",
        "queries": ["bare window scandinavian interior", "sheer linen curtain daylight", "simple roller blind window", "bright window nordic room"],
        "tags": ["windows", "light", "scandinavian"],
    },
    {
        "title": "Choose function-first objects that happen to be beautiful",
        "why": "The tradition is rooted in everyday usefulness, so purely decorative objects sit awkwardly in these rooms.",
        "how": "A good stool, a well-made basket, an enamel jug, a wooden bowl. Things that get used and look right doing it.",
        "queries": ["wooden stool scandinavian interior", "woven basket nordic home", "ceramic bowl on table", "functional objects minimal interior"],
        "tags": ["function", "objects", "scandinavian"],
    },
])


_add("modern homes", [
    {
        "title": "Keep the lines long and uninterrupted",
        "why": "Modern interiors read as calm because the eye can travel across a surface without being stopped by handles, joins and moldings.",
        "how": "Full-height doors, continuous worktops, flush cabinetry and skirting that is either very slim or shadow-gapped.",
        "queries": ["modern interior clean lines", "flush cabinetry modern home", "full height doors interior", "seamless modern architecture interior"],
        "tags": ["lines", "architecture", "modern"],
    },
    {
        "title": "Let one material carry the room",
        "why": "Modern design tends to use fewer materials in larger areas, which is what makes it read as confident rather than busy.",
        "how": "One stone, one timber and one metal, each used generously. Resist adding a fourth for variety.",
        "queries": ["stone surface modern interior", "concrete wall modern home", "single material modern kitchen", "material palette modern interior"],
        "tags": ["materials", "restraint", "modern"],
    },
    {
        "title": "Use recessed and integrated lighting",
        "why": "Visible fixtures interrupt the clean planes that define the style, so modern rooms tend to hide the source and show only the effect.",
        "how": "Recessed spots on a dimmer, LED strips in a shadow gap, and one sculptural pendant where a statement is wanted.",
        "queries": ["recessed lighting modern ceiling", "led strip cove lighting", "modern interior lighting design", "minimal ceiling lights home"],
        "tags": ["lighting", "integration", "modern"],
    },
    {
        "title": "Choose furniture with a strong silhouette",
        "why": "When ornament is removed, shape becomes the only decoration, so the outline of each piece matters far more.",
        "how": "A single well-shaped chair or lamp can carry an entire modern room. Look for pieces that read clearly as a shape from across the space.",
        "queries": ["sculptural chair modern interior", "designer lamp silhouette", "modern furniture shape", "statement chair living room"],
        "tags": ["form", "furniture", "modern"],
    },
    {
        "title": "Warm the palette so it does not feel clinical",
        "why": "The most common failure of modern interiors is coldness, and it almost always comes from too much white, gray and glass together.",
        "how": "Add wood, wool, leather and one earth tone. Warm the artificial lighting to 2700 kelvin regardless of how cool the palette is.",
        "queries": ["warm modern living room wood", "modern interior with leather chair", "earth tones modern home", "warm minimal modern interior"],
        "tags": ["warmth", "color", "modern"],
    },
    {
        "title": "Treat the doorway as a frame",
        "why": "Modern layouts rely on views between spaces, so what you see through an opening is a composition that deserves planning.",
        "how": "Line up a piece of art, a plant or a window at the end of each sightline, and keep the intervening floor clear.",
        "queries": ["view through doorway interior", "framed sightline modern home", "open plan modern interior view", "doorway composition interior"],
        "tags": ["sightlines", "composition", "modern"],
    },
    {
        "title": "Design the storage before the decoration",
        "why": "Modern rooms have nowhere for clutter to hide, so the storage plan has to come first or the look collapses within a month.",
        "how": "Work out what lives in the room, then build or buy for that volume plus twenty percent, then start decorating.",
        "queries": ["built in storage modern living room", "concealed storage modern interior", "modern cabinetry wall", "organized modern home"],
        "tags": ["storage", "planning", "modern"],
    },
    {
        "title": "Use fewer, larger tiles and panels",
        "why": "Grout lines and joins are visual noise. Larger formats give the continuous surfaces the style depends on.",
        "how": "Large format tiles, slab backsplashes, and wide-plank flooring, all laid with the narrowest joint the material allows.",
        "queries": ["large format tile modern interior", "slab backsplash modern kitchen", "wide plank flooring modern", "seamless surface interior"],
        "tags": ["surfaces", "detail", "modern"],
    },
])

_add("luxury interiors", [
    {
        "title": "Luxury is mostly generosity of space and material",
        "why": "What reads as expensive is rarely a logo. It is a wider walkway, a thicker stone edge, a fuller curtain, a bigger piece of art.",
        "how": "Where you have a choice between more items and more generous items, choose generosity every time.",
        "queries": ["luxury living room spacious interior", "thick stone countertop detail", "generous drapery luxury room", "high end interior design"],
        "tags": ["generosity", "scale", "luxury"],
    },
    {
        "title": "Add a second seating group",
        "why": "A room with one sofa is furnished. A room with a sofa and a separate pair of chairs reads as a room designed for people rather than for television.",
        "how": "Two chairs and a small table near a window, angled towards each other. It works in surprisingly modest rooms.",
        "queries": ["two armchairs by window", "secondary seating area living room", "luxury living room seating groups", "elegant chairs interior"],
        "tags": ["seating", "layout", "luxury"],
    },
    {
        "title": "Use natural stone somewhere visible",
        "why": "Stone has depth and variation that printed surfaces cannot reproduce, and the eye picks up the difference immediately.",
        "how": "A small area is enough: a side table top, a fireplace surround, a bathroom vanity. Remnant offcuts are far cheaper than full slabs.",
        "queries": ["marble side table detail", "stone fireplace surround interior", "natural stone vanity bathroom", "veined marble surface"],
        "tags": ["stone", "materials", "luxury"],
    },
    {
        "title": "Layer the lighting like a hotel",
        "why": "Hotels sell atmosphere, and they achieve it with many low-output sources rather than a few bright ones.",
        "how": "Count the light sources in your favorite hotel room. It is usually six or more, all dimmable, none of them a bare ceiling fixture.",
        "queries": ["hotel style bedroom lighting", "layered luxury lighting interior", "warm hotel room ambience", "elegant lamps interior"],
        "tags": ["lighting", "atmosphere", "luxury"],
    },
    {
        "title": "Upholster something",
        "why": "Upholstered surfaces absorb sound and add softness, and they are strongly associated with expensive interiors because they cost labour.",
        "how": "A headboard, a bench, a dining chair seat, or a padded panel behind a bed. A local upholsterer is often cheaper than expected.",
        "queries": ["upholstered headboard luxury bedroom", "fabric dining chairs interior", "padded bench luxury interior", "velvet upholstery detail"],
        "tags": ["upholstery", "softness", "luxury"],
    },
    {
        "title": "Add depth with a mirror or a glazed door",
        "why": "Luxury interiors almost always give you a view into another space, which suggests that the home continues beyond what you can see.",
        "how": "A large mirror reflecting an adjacent room, or internal glazed doors that let one space read into the next.",
        "queries": ["large mirror reflecting room interior", "glazed internal doors home", "layered interior view", "elegant hallway mirror"],
        "tags": ["depth", "mirrors", "luxury"],
    },
    {
        "title": "Pay attention to the edges",
        "why": "Cost shows at junctions: where the floor meets the wall, where the counter ends, where the tile stops. These are what separate finished from nearly finished.",
        "how": "Use proper trims, mitred edges and clean silicone lines. If a junction looks awkward, it will keep looking awkward.",
        "queries": ["detailed trim junction interior", "clean tile edge detail", "mitred stone edge counter", "interior finishing detail"],
        "tags": ["detail", "finish", "luxury"],
    },
    {
        "title": "Keep flowers or branches in the main room",
        "why": "Fresh greenery is the cheapest luxury signal there is, and it is the one detail that hotels and showhouses never skip.",
        "how": "A single type in a plain vessel, cut to a generous height. Branches last for weeks and cost almost nothing.",
        "queries": ["fresh flowers vase luxury interior", "branches in tall vase", "floral arrangement living room", "elegant flower display home"],
        "tags": ["flowers", "styling", "luxury"],
    },
])

_add("apartment decorating", [
    {
        "title": "Give an open-plan apartment a clear circulation spine",
        "why": "Studios and open plans fail when the route through the home cuts across every zone, so nothing feels settled.",
        "how": "Decide the main path from the door to the window and keep it clear, then arrange all the zones off to the sides of it.",
        "queries": ["open plan apartment layout", "studio apartment interior design", "small apartment zones", "modern apartment living space"],
        "tags": ["layout", "circulation", "apartment"],
    },
    {
        "title": "Use the back of a sofa as a room divider",
        "why": "It separates lounge from dining without adding a wall or losing any light, and it costs nothing if the sofa is already there.",
        "how": "Float the sofa with a slim console behind it, and use the console for lamps so the divide is lit from both sides.",
        "queries": ["sofa dividing open plan room", "console table room divider", "studio apartment sofa layout", "open plan living dining"],
        "tags": ["zoning", "divider", "apartment"],
    },
    {
        "title": "Take the dining table seriously even if it is small",
        "why": "Apartments often skip the table, and that removes the one piece of furniture that makes a home feel like a home rather than a hotel room.",
        "how": "A round table for two to four takes less room than it looks and has no corners to bruise hips in a tight space.",
        "queries": ["small round dining table apartment", "compact dining area interior", "apartment dining space", "two person dining table"],
        "tags": ["dining", "furniture", "apartment"],
    },
    {
        "title": "Work with the balcony or window as an extra room",
        "why": "Even a two-foot balcony or a deep sill adds perceived square footage, because the eye reads it as more space beyond the glass.",
        "how": "Put something inviting out there: a small chair, plants, a light. Keep the view through the glass uncluttered.",
        "queries": ["small apartment balcony decor", "plants on balcony city", "window sill plants apartment", "apartment outdoor space small"],
        "tags": ["outdoor", "windows", "apartment"],
    },
    {
        "title": "Deal with the noise",
        "why": "Apartment living is defined by shared walls, and acoustic comfort affects how a home feels more than most decorative decisions.",
        "how": "Rugs with underlay, curtains, upholstered furniture and full bookshelves all absorb sound. Soft materials on hard surfaces do most of the work.",
        "queries": ["rug and curtains apartment interior", "bookshelf wall apartment", "soft furnishings apartment", "quiet cozy apartment"],
        "tags": ["acoustics", "comfort", "apartment"],
    },
    {
        "title": "Create a work zone that closes down",
        "why": "In an apartment, the desk is usually in a living space, and a visible workstation at eight in the evening keeps the whole home in work mode.",
        "how": "A desk that tidies into a cupboard, a lidded box for the laptop, or simply a rule that the desk clears at the end of the day.",
        "queries": ["small home office corner apartment", "desk in living room interior", "compact workspace apartment", "tidy home desk setup"],
        "tags": ["workspace", "boundaries", "apartment"],
    },
    {
        "title": "Use the hallway",
        "why": "Apartment corridors are usually treated as dead space, and they often contain several unused square meters of wall.",
        "how": "Shallow shelving, a run of hooks, a gallery wall, or a narrow console. Anything less than ten inches deep will not obstruct the route.",
        "queries": ["narrow hallway decor apartment", "corridor gallery wall", "slim console hallway", "apartment hallway interior"],
        "tags": ["hallway", "unused space", "apartment"],
    },
    {
        "title": "Choose one thing that fixes the whole apartment feeling generic",
        "why": "Most apartments share the same white walls, same flooring and same fittings, so a single distinctive move is what makes yours memorable.",
        "how": "One painted wall, one unusual light, one large piece of art, or one antique among the new. Just one, done properly.",
        "queries": ["statement lamp apartment interior", "painted accent wall apartment", "unique decor piece modern home", "distinctive apartment interior"],
        "tags": ["character", "identity", "apartment"],
    },
])


_add("farmhouse design", [
    {
        "title": "Let the materials be honest",
        "why": "Farmhouse style comes from buildings where everything was practical, so surfaces that pretend to be something else undermine it immediately.",
        "how": "Real timber, painted board, stone, cast iron and unglazed ceramic. Choose finishes that are allowed to wear.",
        "queries": ["rustic farmhouse kitchen wood", "reclaimed wood interior detail", "cast iron farmhouse detail", "natural materials rustic home"],
        "tags": ["materials", "authenticity", "farmhouse"],
    },
    {
        "title": "Use a warm off-white rather than a bright one",
        "why": "Brilliant white looks modern and slightly clinical, which fights the softness that makes farmhouse interiors comfortable.",
        "how": "Choose creamy or slightly gray-green whites and take them across walls, ceiling and joinery for a soft, enveloping effect.",
        "queries": ["cream white farmhouse interior", "warm white kitchen rustic", "soft neutral farmhouse room", "painted board walls interior"],
        "tags": ["color", "white", "farmhouse"],
    },
    {
        "title": "Add one piece with real age",
        "why": "New furniture styled to look old is the fastest way to make the whole room look like a catalogue. One genuinely old piece anchors everything else.",
        "how": "An old table, a worn bench, a vintage cabinet or a piece of salvaged timber. Let the marks stay.",
        "queries": ["antique wooden table rustic interior", "vintage cabinet farmhouse", "worn wooden bench interior", "old furniture rustic room"],
        "tags": ["antiques", "patina", "farmhouse"],
    },
    {
        "title": "Keep the kitchen at the center",
        "why": "This style is rooted in kitchens that were the working heart of a house, and the layout should reflect that rather than treat cooking as a service function.",
        "how": "A large central table or island with real seating, open sightlines, and storage that is used rather than displayed.",
        "queries": ["farmhouse kitchen table center", "rustic kitchen island seating", "country kitchen interior", "large kitchen table home"],
        "tags": ["kitchen", "layout", "farmhouse"],
    },
    {
        "title": "Use simple utilitarian hardware",
        "why": "Ornate handles and shiny chrome look out of place. The original references are cup pulls, bin handles and plain black iron.",
        "how": "Cup pulls on drawers, simple knobs on doors, aged brass or matte black. Keep it consistent across the whole kitchen.",
        "queries": ["cup pull cabinet hardware kitchen", "black iron handles rustic", "simple kitchen hardware detail", "farmhouse cabinet knobs"],
        "tags": ["hardware", "detail", "farmhouse"],
    },
    {
        "title": "Bring in checks, stripes and ticking",
        "why": "Farmhouse pattern comes from workwear and utility textiles, not from florals, and the simple woven patterns age much better.",
        "how": "Ticking stripe cushions, gingham in small doses, a plain linen tablecloth. Keep the palette to two colors.",
        "queries": ["striped cushions rustic interior", "gingham textile farmhouse", "linen tablecloth country kitchen", "simple patterned fabric home"],
        "tags": ["textiles", "pattern", "farmhouse"],
    },
    {
        "title": "Display things you actually use",
        "why": "The style falls apart when the open shelves are full of decorative objects bought to look rustic. The originals held working crockery.",
        "how": "Everyday plates, mugs, pans and boards on show. Utility is the aesthetic.",
        "queries": ["open shelf with everyday crockery", "hanging pans rustic kitchen", "displayed dishes farmhouse", "practical kitchen shelf"],
        "tags": ["display", "utility", "farmhouse"],
    },
    {
        "title": "Keep the modern conveniences but hide them",
        "why": "Nobody wants an actual nineteenth-century kitchen, but a large glossy appliance in the middle of a rustic room breaks the spell.",
        "how": "Integrate the dishwasher and fridge behind panels, and choose appliances in matte finishes rather than mirror stainless.",
        "queries": ["integrated appliances rustic kitchen", "paneled fridge farmhouse kitchen", "hidden appliances interior", "country kitchen design"],
        "tags": ["appliances", "integration", "farmhouse"],
    },
])

_add("mediterranean design", [
    {
        "title": "Use lime plaster or a textured wall finish",
        "why": "The soft, slightly uneven wall surface is the single most recognizable element of the style and it changes how light behaves in the room.",
        "how": "Lime wash, tadelakt or a textured mineral paint applied with visible movement. Even a matt paint with a brushed application helps.",
        "queries": ["textured plaster wall interior", "lime wash wall mediterranean", "tadelakt wall finish", "warm textured interior wall"],
        "tags": ["walls", "texture", "mediterranean"],
    },
    {
        "title": "Build the palette from earth and sun",
        "why": "The colors come from the landscape: clay, sand, olive, terracotta and the particular white of buildings in strong sunlight.",
        "how": "Warm off-white base, terracotta or clay mid-tones, and olive or deep ochre accents. Avoid gray entirely.",
        "queries": ["terracotta and cream interior", "earthy mediterranean color palette", "olive and clay tones room", "warm neutral mediterranean home"],
        "tags": ["color", "earth tones", "mediterranean"],
    },
    {
        "title": "Use terracotta or stone underfoot",
        "why": "Hard, warm-toned floors are practical in hot climates and they give the whole interior a grounded, sun-worn quality.",
        "how": "Terracotta tile, travertine or a warm-toned porcelain in a large format, softened with flatweave or jute rugs.",
        "queries": ["terracotta tile floor interior", "travertine floor mediterranean", "stone floor warm interior", "rustic tiled floor home"],
        "tags": ["flooring", "materials", "mediterranean"],
    },
    {
        "title": "Add arches wherever the architecture allows",
        "why": "Curved openings soften a room and are strongly associated with the style, which is why they have become so popular again.",
        "how": "A curved doorway, an arched niche, a rounded mirror or an arched headboard if structural changes are not possible.",
        "queries": ["arched doorway interior", "curved niche wall interior", "arch mirror mediterranean room", "rounded architecture interior"],
        "tags": ["arches", "form", "mediterranean"],
    },
    {
        "title": "Choose furniture with visible craft",
        "why": "The tradition is handmade, so machine-perfect furniture sits awkwardly against textured plaster and hand-thrown ceramics.",
        "how": "Rush or cane seats, carved timber, wrought iron and heavy solid tables. Slight irregularity is a feature.",
        "queries": ["rush seat wooden chair interior", "carved wood furniture mediterranean", "wrought iron detail interior", "handmade furniture rustic"],
        "tags": ["furniture", "craft", "mediterranean"],
    },
    {
        "title": "Use linen everywhere",
        "why": "Linen suits the climate, the palette and the informality of the style, and its slight crumple is part of the look rather than a flaw.",
        "how": "Loose linen curtains, unironed linen bedding, linen slipcovers. Choose oatmeal, sand and off-white before anything bright.",
        "queries": ["linen curtains sunlight interior", "linen bedding neutral bedroom", "natural linen fabric home", "relaxed linen slipcover sofa"],
        "tags": ["textiles", "linen", "mediterranean"],
    },
    {
        "title": "Keep olive, citrus or dried branches in the room",
        "why": "The planting is part of the architecture in the regions this style comes from, and even a single branch carries the reference indoors.",
        "how": "An olive tree in a terracotta pot, a lemon tree by a bright window, or dried grasses in a heavy ceramic vessel.",
        "queries": ["olive tree in terracotta pot indoor", "dried grasses ceramic vase", "lemon tree indoor plant", "mediterranean plants interior"],
        "tags": ["plants", "greenery", "mediterranean"],
    },
    {
        "title": "Let sunlight be uncontrolled in one room",
        "why": "The whole style is built around strong light and hard shadow, which is lost if every window is diffused.",
        "how": "Leave one window bare or use shutters that fold fully back, and let the light move across the textured wall through the day.",
        "queries": ["sunlight shadow textured wall", "bright mediterranean room window", "wooden shutters interior light", "sunlit warm interior"],
        "tags": ["light", "shadow", "mediterranean"],
    },
])

_add("seasonal decorating", [
    {
        "title": "Change the textiles, not the furniture",
        "why": "Seasonal decorating goes wrong when it becomes a shopping event. The cheapest and most effective seasonal change is what you can wash and fold away.",
        "how": "Heavier throws and deeper cushion covers for autumn and winter, lighter linen and cotton for spring and summer. Store the off-season set flat.",
        "queries": ["seasonal cushions throws sofa", "cozy autumn living room textiles", "light summer interior linens", "changing home textiles"],
        "tags": ["textiles", "seasons", "seasonal"],
    },
    {
        "title": "Follow the light through the year",
        "why": "The same room needs different lighting in December than in June, and most homes never adjust for it.",
        "how": "Add extra low lamps for the dark months and pull them out again in summer. Move seating towards the window in winter and away from it in high summer.",
        "queries": ["winter cozy lamp lighting home", "summer bright living room", "seasonal home lighting", "sunlit room seasonal change"],
        "tags": ["lighting", "seasons", "seasonal"],
    },
    {
        "title": "Use what is actually in season outside",
        "why": "Natural seasonal material is free, looks right automatically, and avoids the plastic quality of themed decorations.",
        "how": "Branches in spring, grasses in summer, foliage and dried seed heads in autumn, evergreens in winter. One large arrangement beats many small ones.",
        "queries": ["branches in vase seasonal decor", "dried grasses autumn interior", "evergreen branches winter home", "natural seasonal arrangement"],
        "tags": ["natural", "free", "seasonal"],
    },
    {
        "title": "Keep seasonal color to ten percent of the room",
        "why": "Rooms that change completely with the season feel unstable, and the decorations end up fighting the permanent scheme.",
        "how": "Keep the base neutral and let seasonal color appear only in cushions, throws, ceramics and greenery.",
        "queries": ["neutral room with seasonal accents", "autumn accent colors interior", "subtle holiday decor living room", "seasonal accessories home"],
        "tags": ["color", "restraint", "seasonal"],
    },
    {
        "title": "Store seasonal decorations properly or they will not be reused",
        "why": "Most seasonal items are discarded because they were crushed in a bag, not because they went out of style.",
        "how": "One labeled box per season, rigid, with fragile items wrapped. Store it where you can reach it without moving everything else.",
        "queries": ["labeled storage box seasonal decor", "organized holiday decoration storage", "stacked storage boxes home", "seasonal storage organization"],
        "tags": ["storage", "reuse", "seasonal"],
    },
    {
        "title": "Do the seasonal reset in the same order each time",
        "why": "Turning the change into a short routine keeps it enjoyable instead of becoming an all-day project you start avoiding.",
        "how": "Clear, clean, swap textiles, add greenery, adjust lighting. An hour per season for the whole home is realistic.",
        "queries": ["tidying and restyling living room", "seasonal home refresh", "cleaning and decorating home", "styled seasonal interior"],
        "tags": ["routine", "process", "seasonal"],
    },
])

_add("timeless interiors", [
    {
        "title": "Buy the big pieces plain and the small pieces with character",
        "why": "The sofa, the bed and the dining table are the expensive items and the hardest to replace, so they are the wrong place to date a room.",
        "how": "Simple shapes and neutral fabrics on the large pieces, then all the personality in cushions, art, lamps and ceramics.",
        "queries": ["neutral sofa timeless living room", "simple upholstered furniture interior", "classic furniture shapes home", "understated living room design"],
        "tags": ["investment", "neutral", "timeless"],
    },
    {
        "title": "Choose materials that improve as they age",
        "why": "Timelessness is partly a material question. Solid wood, wool, leather, stone and brass all look better after ten years, while most synthetics look worse.",
        "how": "Where a natural version exists within budget, take it, even at a smaller size. Avoid anything with a printed surface pattern.",
        "queries": ["aged leather chair interior", "solid wood table patina", "brass detail aged interior", "natural materials home"],
        "tags": ["materials", "patina", "timeless"],
    },
    {
        "title": "Avoid furnishing entirely from one trend cycle",
        "why": "A room bought in a single season carries a visible date stamp, because everything in it comes from the same eighteen-month window.",
        "how": "Deliberately mix eras: something old, something contemporary, something handmade. The friction between them is what makes rooms interesting.",
        "queries": ["mixed era interior design", "vintage and modern furniture room", "eclectic timeless interior", "layered interior styles"],
        "tags": ["mixing", "eras", "timeless"],
    },
    {
        "title": "Get the architecture right before the decoration",
        "why": "Proportion, light and flow do not go out of fashion. Decorative trends layered onto a badly proportioned room never fix it.",
        "how": "Spend on door heights, window treatments, lighting positions and floor finishes before spending on accessories.",
        "queries": ["well proportioned interior architecture", "classic interior proportions room", "natural light architecture home", "architectural interior detail"],
        "tags": ["architecture", "priorities", "timeless"],
    },
    {
        "title": "Use pattern sparingly and at small scale",
        "why": "Large statement patterns are the most easily dated element in any room, and they are usually the most expensive to remove.",
        "how": "Keep bold pattern to cushions and small textiles that cost little to replace. Save the permanent surfaces for plain or textured finishes.",
        "queries": ["subtle patterned cushions interior", "plain walls textured fabric", "small scale pattern home", "understated pattern interior"],
        "tags": ["pattern", "restraint", "timeless"],
    },
    {
        "title": "Let the room hold things you actually care about",
        "why": "The rooms that still look good in twenty years are the ones filled with objects that mean something, not the ones assembled from a single shopping list.",
        "how": "Books you have read, art you chose, objects from places you have been. Personality is the one thing a trend cannot supply.",
        "queries": ["personal objects styled shelf", "books and art living room", "collected objects interior", "personal home decor"],
        "tags": ["personality", "meaning", "timeless"],
    },
])

_add("diy decor", [
    {
        "title": "Build a picture ledge instead of hanging a gallery wall",
        "why": "It gives you the gallery look with two screws instead of twenty, and you can rearrange the art in seconds.",
        "how": "A length of timber with a small lip, painted the wall color, fixed into studs. Layer frames of different sizes front to back.",
        "queries": ["picture ledge shelf with frames", "diy wall shelf art display", "layered artwork on ledge", "gallery shelf interior"],
        "tags": ["diy", "art", "easy"],
    },
    {
        "title": "Make a slat wall from standard timber",
        "why": "Vertical battens add architecture and texture to a flat wall for the price of a few lengths of pine, and the effect is disproportionate to the cost.",
        "how": "Fix a painted backing board, then space identical battens using an offcut as a spacer so the gaps stay perfectly even.",
        "queries": ["wooden slat feature wall", "vertical batten wall interior", "timber slat panel room", "diy wood wall detail"],
        "tags": ["diy", "walls", "texture"],
    },
    {
        "title": "Reupholster a seat pad in an afternoon",
        "why": "Drop-in dining chair seats are the easiest upholstery job there is, and new fabric changes the whole dining area.",
        "how": "Unscrew the pad, staple new fabric over the old one keeping the tension even, and trim. Half a meter of fabric per chair is usually enough.",
        "queries": ["reupholstered dining chair fabric", "diy chair seat cushion", "fabric upholstery detail", "restored dining chairs"],
        "tags": ["diy", "upholstery", "furniture"],
    },
    {
        "title": "Paint the inside of a bookcase",
        "why": "It creates depth behind the objects on the shelves and turns an ordinary unit into something that looks built in.",
        "how": "Choose a deeper tone than the walls, paint only the back panel, and keep the shelves and frame in the wall color.",
        "queries": ["painted back of bookcase interior", "colored shelf interior detail", "styled bookcase with color", "shelving unit design"],
        "tags": ["diy", "paint", "shelving"],
    },
    {
        "title": "Make a headboard from a padded panel",
        "why": "A headboard is one of the most expensive items per square inch in a bedroom and one of the simplest to build.",
        "how": "Plywood cut to width, foam and wadding, fabric stapled around the back, then hung on two French cleats. Under a hundred dollars in most cases.",
        "queries": ["diy upholstered headboard bedroom", "padded headboard fabric detail", "handmade headboard interior", "bedroom headboard design"],
        "tags": ["diy", "bedroom", "upholstery"],
    },
    {
        "title": "Add trim to a plain door",
        "why": "Flat hollow doors are one of the biggest builder-grade giveaways, and applied molding turns them into paneled doors convincingly.",
        "how": "Simple rectangles of molding, glued and pinned, filled at the joints, then the whole door painted one color. Measure once for the first door and repeat.",
        "queries": ["paneled door molding detail", "diy door trim upgrade", "painted interior door design", "door detail interior"],
        "tags": ["diy", "doors", "architecture"],
    },
    {
        "title": "Turn a plain lamp into a good one with a new shade",
        "why": "The shade is most of what you see, and a well-proportioned linen or paper shade transforms an inexpensive base.",
        "how": "Match the shade width roughly to the height of the base, and check the fitting type before ordering.",
        "queries": ["linen lampshade table lamp", "new lamp shade interior", "warm lamp glow living room", "lamp detail interior"],
        "tags": ["diy", "lighting", "easy"],
    },
    {
        "title": "Frame textiles instead of buying art",
        "why": "A piece of fabric, a scarf or a botanical print in a large frame gives you scale and texture at a fraction of the cost of original art.",
        "how": "Mount the textile on a plain backing board, use a deep frame so the fabric does not touch the glass, and go large.",
        "queries": ["framed textile wall art", "fabric in frame interior", "large framed artwork wall", "textile art living room"],
        "tags": ["diy", "art", "budget"],
    },
])


_add("design trends", [
    {
        "title": "Curves are replacing hard edges",
        "why": "After a decade of rectilinear gray interiors, rounded arms, arched openings and circular mirrors read as softer and more welcoming.",
        "how": "Use one curved element per room rather than a whole set. A round mirror or a curved chair is enough to shift the feel.",
        "queries": ["curved sofa modern interior", "round mirror wall interior", "arched doorway modern home", "rounded furniture design"],
        "tags": ["curves", "shape", "trends"],
    },
    {
        "title": "Warm neutrals have replaced cool gray",
        "why": "Gray schemes dominated for years and now read as dated, mostly because they look cold under warm artificial light.",
        "how": "Move towards oatmeal, clay, mushroom and warm off-white. If you have a gray room, changing the textiles and bulbs is often enough.",
        "queries": ["warm neutral interior palette", "beige and cream modern room", "earthy neutral living room", "warm toned interior design"],
        "tags": ["color", "neutrals", "trends"],
    },
    {
        "title": "Color drenching a whole room",
        "why": "Painting walls, trim, doors and ceiling in one color removes every hard outline and makes a room feel enveloping and much more considered.",
        "how": "Choose a mid to deep muted tone, use eggshell on the woodwork and matt on the walls, and keep the furniture simple.",
        "queries": ["color drenched room interior", "monochrome painted room", "dark painted walls and ceiling", "immersive color interior"],
        "tags": ["paint", "color", "trends"],
    },
    {
        "title": "Textured and imperfect wall finishes",
        "why": "Flat modern plaster is being replaced by limewash and mineral finishes because they give a wall depth that changes with the light.",
        "how": "Limewash paint is applied with a wide brush in crossing strokes. Test on a board first because the effect varies a lot with technique.",
        "queries": ["limewash textured wall interior", "plaster finish wall detail", "mineral paint wall texture", "soft textured interior wall"],
        "tags": ["walls", "texture", "trends"],
    },
    {
        "title": "Vintage and secondhand mixed with new",
        "why": "Interest in older pieces is partly aesthetic and partly practical, since a solid wood cabinet from decades ago often costs less than a new veneer one.",
        "how": "Aim for roughly a quarter of the furniture in any room to be older than you are. Mix eras rather than recreating one.",
        "queries": ["vintage furniture modern room", "antique piece contemporary interior", "secondhand furniture styled", "mixed era living room"],
        "tags": ["vintage", "mixing", "trends"],
    },
    {
        "title": "Statement lighting as sculpture",
        "why": "As rooms have become simpler, the light fitting has become the object people look at, which is why oversized and sculptural fixtures have taken over.",
        "how": "One sculptural fixture per space, sized generously. Keep the rest of the lighting recessed or discreet so it has room to be seen.",
        "queries": ["sculptural pendant light interior", "statement lamp modern room", "oversized light fixture home", "designer lighting interior"],
        "tags": ["lighting", "statement", "trends"],
    },
    {
        "title": "Quiet luxury over visible branding",
        "why": "The prevailing direction is towards materials, proportion and craft rather than recognizable design pieces, which ages far better.",
        "how": "Spend on the things you touch and the surfaces you see every day, and skip anything whose main value is being identifiable.",
        "queries": ["understated luxury interior", "quality materials modern home", "refined simple interior design", "elegant restrained room"],
        "tags": ["luxury", "restraint", "trends"],
    },
    {
        "title": "Bringing the outside in with real greenery",
        "why": "Plants have moved from accessory to structural element, used to soften architecture rather than to fill a corner.",
        "how": "Fewer, larger plants placed where the architecture is hardest, and one climbing or trailing plant to break a straight line.",
        "queries": ["large indoor plants modern interior", "trailing plant shelf interior", "indoor greenery living room", "plants softening architecture"],
        "tags": ["plants", "biophilia", "trends"],
    },
])


# ---------------------------------------------------------------------------
# Category aliases and relationships
# ---------------------------------------------------------------------------

#: Human phrasings that map onto a canonical knowledge category.
CATEGORY_ALIASES: dict[str, str] = {
    "living room": "living rooms",
    "livingroom": "living rooms",
    "lounge": "living rooms",
    "bedroom": "bedrooms",
    "kitchen": "kitchens",
    "bathroom": "bathrooms",
    "small space": "small spaces",
    "tiny homes": "small spaces",
    "organization": "home organization",
    "organization": "home organization",
    "decluttering": "home organization",
    "decorating mistakes": "interior design mistakes",
    "design mistakes": "interior design mistakes",
    "mistakes": "interior design mistakes",
    "affordable decorating": "budget decorating",
    "budget": "budget decorating",
    "cheap decorating": "budget decorating",
    "look expensive": "expensive look",
    "expensive": "expensive look",
    "luxury": "luxury interiors",
    "luxury homes": "luxury interiors",
    "modern": "modern homes",
    "modern interiors": "modern homes",
    "cozy": "cozy homes",
    "cozy homes": "cozy homes",
    "minimalist": "minimalist design",
    "minimalism": "minimalist design",
    "scandinavian": "scandinavian design",
    "nordic": "scandinavian design",
    "mediterranean": "mediterranean design",
    "farmhouse": "farmhouse design",
    "rustic": "farmhouse design",
    "apartment": "apartment decorating",
    "apartments": "apartment decorating",
    "renter friendly": "renter-friendly decorating",
    "rental": "renter-friendly decorating",
    "renting": "renter-friendly decorating",
    "diy": "diy decor",
    "diy decor concepts": "diy decor",
    "seasonal": "seasonal decorating",
    "trends": "design trends",
    "timeless": "timeless interiors",
    "lighting ideas": "lighting",
    "color": "colors",
    "colors": "colors",
    "paint": "colors",
    "furniture": "furniture placement",
    "layout": "furniture placement",
    "home improvement": "expensive look",
}

#: Categories that supply extra material when a primary category runs dry.
RELATED_CATEGORIES: dict[str, list[str]] = {
    "living rooms": ["furniture placement", "lighting", "colors", "cozy homes", "expensive look"],
    "bedrooms": ["lighting", "colors", "storage", "cozy homes", "timeless interiors"],
    "kitchens": ["storage", "lighting", "home organization", "expensive look", "modern homes"],
    "bathrooms": ["storage", "lighting", "expensive look", "small spaces"],
    "small spaces": ["storage", "furniture placement", "apartment decorating", "colors", "lighting"],
    "home organization": ["storage", "small spaces", "kitchens", "minimalist design"],
    "lighting": ["living rooms", "cozy homes", "expensive look", "modern homes"],
    "colors": ["living rooms", "bedrooms", "timeless interiors", "design trends"],
    "furniture placement": ["living rooms", "small spaces", "interior design mistakes"],
    "storage": ["home organization", "small spaces", "kitchens", "bedrooms"],
    "expensive look": ["luxury interiors", "lighting", "colors", "timeless interiors", "living rooms"],
    "interior design mistakes": ["furniture placement", "lighting", "colors", "living rooms", "bedrooms"],
    "budget decorating": ["diy decor", "renter-friendly decorating", "expensive look", "storage"],
    "renter-friendly decorating": ["apartment decorating", "budget decorating", "diy decor", "small spaces"],
    "cozy homes": ["lighting", "living rooms", "bedrooms", "farmhouse design"],
    "minimalist design": ["storage", "modern homes", "colors", "timeless interiors"],
    "scandinavian design": ["minimalist design", "cozy homes", "colors", "lighting"],
    "modern homes": ["minimalist design", "lighting", "storage", "design trends"],
    "luxury interiors": ["expensive look", "lighting", "timeless interiors", "colors"],
    "apartment decorating": ["small spaces", "renter-friendly decorating", "storage", "furniture placement"],
    "farmhouse design": ["cozy homes", "kitchens", "timeless interiors", "colors"],
    "mediterranean design": ["colors", "timeless interiors", "modern homes", "cozy homes"],
    "seasonal decorating": ["cozy homes", "colors", "storage", "living rooms"],
    "timeless interiors": ["colors", "expensive look", "furniture placement", "design trends"],
    "diy decor": ["budget decorating", "renter-friendly decorating", "storage", "colors"],
    "design trends": ["colors", "modern homes", "timeless interiors", "lighting"],
}

ALL_CATEGORIES: list[str] = sorted(KNOWLEDGE)

#: Room and space categories win over topic categories when a title mentions
#: both. "Bedroom Decorating Mistakes" is a bedroom video first, so the tips
#: should come from the bedroom pool with mistakes as a related source.
ROOM_CATEGORIES: frozenset[str] = frozenset(
    {
        "living rooms",
        "bedrooms",
        "kitchens",
        "bathrooms",
        "small spaces",
        "apartment decorating",
    }
)


def _match_aliases(key: str, allowed: frozenset[str] | None) -> str | None:
    """Longest-alias-first substring match, optionally limited to a category set."""

    for alias in sorted(CATEGORY_ALIASES, key=len, reverse=True):
        target = CATEGORY_ALIASES[alias]
        if allowed is not None and target not in allowed:
            continue
        if alias in key:
            return target
    for category in sorted(KNOWLEDGE, key=len, reverse=True):
        if allowed is not None and category not in allowed:
            continue
        if category in key or category.rstrip("s") in key:
            return category
    return None


def normalize_category(name: str | None) -> str | None:
    """Map a loose category phrase onto a canonical knowledge category."""

    if not name:
        return None
    key = str(name).strip().lower()
    if key in KNOWLEDGE:
        return key
    if key in CATEGORY_ALIASES:
        return CATEGORY_ALIASES[key]
    return _match_aliases(key, ROOM_CATEGORIES) or _match_aliases(key, None)


def tips_for(
    category: str | None,
    include_related: bool = True,
    language: str = "en",
) -> list[Tip]:
    """Return the tip pool for a category, optionally widened with related ones.

    ``language`` selects which body of writing is used. The Spanish pool is
    written natively in :mod:`vidfactory.knowledge_es` rather than translated,
    and it carries its own English ``queries``/``tags``/``search`` so the stock
    searches stay in English regardless of what the viewer hears.
    """

    from .languages import resolve_language

    resolved = resolve_language(language)
    if not resolved.is_english:
        from .knowledge_es import KNOWLEDGE_ES

        source: dict[str, list[Tip]] = KNOWLEDGE_ES
    else:
        source = KNOWLEDGE

    canonical = normalize_category(category)
    pool: list[Tip] = []
    seen: set[str] = set()

    def extend(name: str) -> None:
        for tip in source.get(name, []):
            key = tip["title"]
            if key not in seen:
                seen.add(key)
                pool.append(tip)

    if canonical:
        extend(canonical)
        if include_related:
            for related in RELATED_CATEGORIES.get(canonical, []):
                extend(related)
    else:
        for name in sorted(source):
            extend(name)
    return pool


def total_tips() -> int:
    return sum(len(v) for v in KNOWLEDGE.values())
