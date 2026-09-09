"""What the reels are allowed to say, and what each statement rests on.

Written natively in Spanish, like ``knowledge_es`` on the long-form side and
for the same reason: a translated nutrition line reads like a translated
nutrition line, and this audience is being asked to trust it.

Every ``claim`` is phrased at the strength the evidence actually supports.
That is not a stylistic preference. "Diez frutas que bajan el azucar" is a
false sentence; "diez frutas que suelen tener un impacto mas moderado en la
glucosa" is a true one carrying the same useful information, and the
difference is the whole point of :mod:`vidfactory.reels.safety`. Three
caveats recur because they are what make almost anything in this niche
correct rather than misleading: **la cantidad, la preparacion, y con que se
combina** - plus the fact that people genuinely differ.

``query`` and ``search_text`` are English, because Pexels is indexed in
English and CLIP scores frames against English. The narration is Spanish and
never reaches a stock provider. Same rule as ``languages.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable


@dataclass(frozen=True)
class Item:
    """One beat of the reel's value section."""

    key: str
    #: What the narration calls it, used in the spoken line.
    display: str
    #: The claim, already hedged. This is narrated close to verbatim.
    claim: str
    #: The mechanism in one short clause - the "por que" the brief asks for.
    why: str
    #: English, for the stock provider.
    query: str
    #: English, for CLIP to score the frames against.
    search_text: str
    sources: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "display": self.display,
            "claim": self.claim,
            "why": self.why,
            "query": self.query,
            "sources": list(self.sources),
        }


#: The six shapes a reel can take. Each one changes the script's spine, not
#: just its wording: a comparison has two sides, a myth has a question and an
#: answer, a list has items and an error has a fix.
FORMATS: tuple[str, ...] = (
    "list", "error_solution", "comparison", "ranking", "myth", "combination",
)


@dataclass(frozen=True)
class Topic:
    """One reel's subject, in the format it should be told in."""

    slug: str
    #: The reel's own title. Correct at the strength the evidence allows.
    title: str
    format: str
    #: The fixed on-screen title. Three to seven words, one emoji at most.
    top_title: str
    #: The word inside ``top_title`` that gets the accent colour.
    accent: str
    #: What the viewer is about to get, in one sentence. No medical promise.
    promise: str
    #: The practical idea to leave them with, before the CTA.
    conclusion: str
    items: tuple[Item, ...]
    hashtags: tuple[str, ...] = ()
    #: The viewer's actual worry, as a clause that follows "te preocupa".
    #: This is what the hook attacks in the first two seconds, and it is
    #: written per topic because "te preocupa la glucosa" is nobody's real
    #: concern - "que la fruta te dispare la glucosa" is.
    worry: str = ""
    #: The moment it happens, when the topic has one: "despues del desayuno".
    moment: str = ""
    #: The answer, delivered in the third second. Not a description of what
    #: the reel contains: the reel's own point, said immediately. Falls back
    #: to ``promise`` for a topic that has not been given one.
    answer: str = ""
    #: The one practical thing to do, said just before the CTA. Falls back to
    #: ``conclusion``.
    takeaway: str = ""
    #: Set when the answer names every item, so trimming one makes the third
    #: second a lie. "Granola, barritas, salsas, zumos envasados y lacteos de
    #: sabores" promises five things as surely as a title that says five, and
    #: the reel has to deliver them or run longer.
    promises_all_items: bool = False
    #: Candidate openings, written for this topic rather than generated from
    #: a template. Five to eight each: :mod:`vidfactory.reels.hooks` scores
    #: them and picks one, and a real choice needs real alternatives. Generic
    #: templates produce grammatical accidents ("no las frutas afectan igual")
    #: and, worse, interchangeable openings - the one part of a reel that
    #: must not be interchangeable.
    hooks: tuple[str, ...] = ()
    #: An establishing shot for the hook and the promise, before the first
    #: item has been named.
    opening_query: str = "healthy food on a kitchen table"
    opening_search_text: str = "a bowl of fresh fruit on a kitchen counter"
    #: The closing call to action, when this topic wants a particular one of
    #: the allowed variations rather than the stable pick. Left empty for
    #: almost every topic: varying the ending across a feed is the point, and
    #: an override exists so a named reel can be asked for by name without
    #: the variation rule being rewritten around it. It still has to be one
    #: of ``script.CTA_VARIANTS`` - a test checks that - because the CTA is
    #: the one sentence in the reel that is never allowed to become a sale.
    cta: str = ""

    @property
    def required_item_count(self) -> int:
        """The number the title promises, if it names one.

        A reel titled "5 frutas" that lists four has a false first line, and
        the title is burned into the frame for the whole reel saying so. The
        same rule the long-form side applies to "10 Small Living Room Tricks".
        """

        words = {
            "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6,
            "siete": 7, "ocho": 8, "nueve": 9, "diez": 10,
        }
        # Only a number the title *opens* with. Scanning further in reads
        # "Por que dos personas pueden responder distinto" as a promise of two
        # items, and that title promises no list at all.
        head = self.title.lower().split()
        if self.promises_all_items:
            return len(self.items)
        first = head[0] if head else ""
        if first.isdigit():
            return int(first)
        return words.get(first, 0)

    @property
    def answer_line(self) -> str:
        return (self.answer or self.promise).rstrip(" .") + "."

    @property
    def takeaway_line(self) -> str:
        return (self.takeaway or self.conclusion).rstrip(" .") + "."

    @property
    def all_sources(self) -> list[str]:
        keys: list[str] = []
        for item in self.items:
            keys.extend(item.sources)
        return keys


# ---------------------------------------------------------------------------
# Reusable food beats. Several topics need the same fruit, and writing it
# twice is how two reels end up disagreeing with each other.
# ---------------------------------------------------------------------------

FRESAS = Item(
    key="fresas",
    display="las fresas",
    claim=(
        "Las fresas suelen aportar menos carbohidratos por ración"
    ),
    why="y su fibra suaviza la subida",
    query="fresh strawberries in a white bowl",
    search_text="a bowl of fresh red strawberries",
    sources=("harvard_carbs", "harvard_fiber", "ada_nutrition"),
)

FRAMBUESAS = Item(
    key="frambuesas",
    display="las frambuesas",
    claim=(
        "Las frambuesas aportan mucha fibra y pocos carbohidratos"
    ),
    why="y la fibra suele moderar la respuesta",
    query="fresh raspberries close up bowl",
    search_text="a bowl of fresh raspberries",
    sources=("harvard_fiber", "ada_nutrition"),
)

ARANDANOS = Item(
    key="arandanos",
    display="los arandanos",
    claim=(
        (
            "Los arandanos suelen encajar bien en raciones pequenas, "
            "aunque concentran algo más de azúcar que otras bayas"
        )
    ),
    why="así que aquí la cantidad importa más de lo que parece",
    query="fresh blueberries in a bowl",
    search_text="a bowl of fresh blueberries",
    sources=("harvard_carbs", "diabetes_uk_food"),
)

KIWI = Item(
    key="kiwi",
    display="el kiwi",
    claim=(
        "El kiwi aporta fibra y suele tener un impacto moderado"
    ),
    why="en una ración de una pieza",
    query="sliced kiwi fruit on a plate",
    search_text="sliced green kiwi fruit",
    sources=("harvard_fiber", "who_diet"),
)

MANZANA = Item(
    key="manzana",
    display="la manzana con piel",
    claim=(
        "La manzana con piel conserva la fibra"
    ),
    why="y suele absorberse más despacio que en zumo",
    query="whole red apple with skin on a wooden table",
    search_text="a whole red apple on a wooden table",
    sources=("harvard_fiber", "ada_nutrition", "fundacion_diabetes"),
)

PERA = Item(
    key="pera",
    display="la pera",
    claim=(
        (
            "La pera también es una fruta con bastante fibra, y suele "
            "sentar bien en raciones medidas"
        )
    ),
    why="sobre todo si se come entera y no en almibar",
    query="fresh green pear on a kitchen counter",
    search_text="a fresh whole pear",
    sources=("harvard_fiber", "diabetes_uk_food"),
)

AGUACATE = Item(
    key="aguacate",
    display="el aguacate",
    claim=(
        "El aguacate apenas aporta carbohidratos"
    ),
    why="así que su efecto suele ser mínimo",
    query="halved avocado on a wooden board",
    search_text="a halved fresh avocado",
    sources=("harvard_carbs", "ada_nutrition"),
)

PLATANO_MADURO = Item(
    key="platano",
    display="el plátano muy maduro",
    claim=(
        "El plátano maduro suele llevar más azúcares libres"
    ),
    why="y cuanto más maduro, más rápido se absorbe",
    query="ripe yellow bananas on a table",
    search_text="ripe yellow bananas",
    sources=("harvard_carbs", "diabetes_uk_food"),
)

UVAS = Item(
    key="uvas",
    display="las uvas",
    claim=(
        "Con las uvas es muy fácil pasarse de ración"
    ),
    why="porque se comen de una en una",
    query="bunch of green grapes close up",
    search_text="a bunch of fresh grapes",
    sources=("ada_nutrition", "diabetes_uk_food"),
)

DATILES = Item(
    key="datiles",
    display="los dátiles",
    claim=(
        "Los dátiles concentran mucho azúcar en poco volumen"
    ),
    why="así que una ración pequeña ya cuenta",
    query="dried dates in a bowl",
    search_text="a bowl of dried dates",
    sources=("harvard_carbs", "who_diet"),
)

FRUTA_DESHIDRATADA = Item(
    key="deshidratada",
    display="la fruta deshidratada",
    claim=(
        "La fruta deshidratada pierde el agua y concentra el azúcar"
    ),
    why="y suele comerse en más cantidad",
    query="dried apricots and raisins in a bowl",
    search_text="a bowl of dried fruit",
    sources=("harvard_carbs", "who_diet", "fundacion_diabetes"),
)

ZUMO = Item(
    key="zumo",
    display="el zumo de naranja",
    claim=(
        "Al exprimir la naranja se pierde casi toda la fibra"
    ),
    why="y el azúcar suele absorberse más rápido",
    query="glass of fresh orange juice on a table",
    search_text="a glass of orange juice",
    sources=("who_diet", "harvard_fiber", "ada_nutrition"),
)

NARANJA_ENTERA = Item(
    key="naranja",
    display="la naranja entera",
    claim=(
        "La naranja entera mantiene la fibra y llena más"
    ),
    why="y hacen falta dos o tres para un vaso",
    query="whole oranges and orange segments on a table",
    search_text="whole oranges on a table",
    sources=("who_diet", "harvard_fiber"),
)


def _fruit_list_items() -> tuple[Item, ...]:
    return (FRESAS, FRAMBUESAS, KIWI, MANZANA, AGUACATE)


# ---------------------------------------------------------------------------
# Topics
# ---------------------------------------------------------------------------

TOPICS: tuple[Topic, ...] = (
    Topic(
        slug="frutas-impacto-moderado",
        worry="que la fruta te dispare la glucosa",
        moment="después de comer fruta",
        title="5 frutas que suelen tener un impacto más moderado en la glucosa",
        format="list",
        top_title="FRUTAS Y GLUCOSA 🍓",
        accent="GLUCOSA",
        promise=(
            (
                "Estas son cinco opciones que suelen tener un impacto más "
                "moderado cuando cuidamos también la cantidad"
            )
        ),
        conclusion=(
            (
                "La fruta no tiene por que desaparecer de tu dieta: el tipo, "
                "la cantidad y con que la acompañas importan mucho"
            )
        ),
        answer=(
                   "Fresas, frambuesas, kiwi, manzana con piel y aguacate, en "
                   "raciones normales"
               ),
        takeaway=(
                     "Mide la ración y acompaña la fruta con algo de proteína"
                 ),
        items=_fruit_list_items(),
        hashtags=("#diabetes", "#glucosa", "#alimentacionsaludable", "#fruta",
                  "#diabetestipo2", "#saludable"),
        hooks=(
            "Si tienes diabetes y te preocupa que la fruta te dispare la glucosa, escucha esto.",
            "Te preocupa que la fruta te suba la glucosa y ya no sabes cual elegir? Empieza por estas cinco.",
            (
                "Si has dejado la fruta por miedo al azúcar, esto te interesa "
                "más de lo que crees."
            ),
            "Si te cuesta elegir fruta sin complicarte, apunta estas cinco.",
            "Antes de dejar la fruta por miedo al azúcar, mira esto.",
        ),
        opening_query="fresh fruit assortment on a kitchen table",
        opening_search_text="an assortment of fresh fruit on a table",
        cta="Síguenos para más consejos claros y sencillos sobre diabetes.",
    ),
    Topic(
        slug="frutas-suben-mas-rapido",
        worry="elegir una fruta que te suba mucho la glucosa",
        moment="después de la merienda",
        title="5 frutas que pueden subir la glucosa más rápidamente",
        format="list",
        top_title="CUIDADO CON ESTAS FRUTAS ⚠️",
        accent="CUIDADO",
        promise=(
            (
                "No hay que eliminarlas, pero conviene medir la ración y "
                "saber con que las acompañas"
            )
        ),
        conclusion=(
            (
                "Ninguna de estas frutas está descartada: cambia mucho la "
                "ración, la madurez y con que la comes"
            )
        ),
        answer=(
                   (
                       "Plátano muy maduro, uvas, dátiles, fruta seca y zumo: vigila "
                       "la ración"
                   )
               ),
        takeaway=(
                     "No las quites: pesa una ración una vez y úsala de referencia"
                 ),
        items=(PLATANO_MADURO, UVAS, DATILES, FRUTA_DESHIDRATADA, ZUMO),
        hashtags=("#diabetes", "#glucosa", "#fruta", "#nutricion",
                  "#diabetestipo2"),
        hooks=(
            (
                "Si eliges fruta a ojo y luego tu glucosa sube más de lo que "
                "esperas, mira estas cinco."
            ),
            (
                "Estas frutas parecen saludables, pero algunas pueden subir "
                "tu glucosa más rápido."
            ),
            (
                "Te preocupa pasarte con la fruta sin darte cuenta? Estas "
                "cinco piden más cuidado."
            ),
            (
                "Si sueles picar fruta sin mirar la cantidad, presta atención "
                "a estas cinco."
            ),
            (
                "Si comes fruta a diario y no sabes cual vigilar más, empieza "
                "por estas cinco."
            ),
        ),
        opening_query="ripe fruit bowl on a kitchen counter",
        opening_search_text="a bowl of ripe fruit on a counter",
    ),
    Topic(
        slug="errores-comer-fruta",
        worry="que la fruta te suba más de lo que esperas",
        moment="después de comer fruta",
        title="5 errores al comer fruta si tienes diabetes",
        format="error_solution",
        top_title="ERRORES CON LA FRUTA",
        accent="ERRORES",
        promise=(
            "Cinco fallos muy comunes y que se puede hacer en su lugar, sin "
            "renunciar a la fruta"
        ),
        conclusion=(
            "Casi siempre el problema no es la fruta, sino la cantidad, la "
            "forma y el momento en que la tomamos"
        ),
        answer=(
                   (
                       "Comerla sola, cambiarla por zumo, no medir, pelarla y "
                       "pasarte con la seca"
                   )
               ),
        takeaway=(
                     "Empieza por uno: sírvete la fruta en un plato, no del bol"
                 ),
        items=(
            Item(
                key="fruta_sola",
                display="comerla sola con mucha hambre",
                claim=(
                    "Comer fruta sola con mucha hambre suele subir más"
                ),
                why=(
                    "acompáñala con yogur o nueces"
                ),
                query="yogurt with nuts and berries in a bowl",
                search_text="a bowl of yogurt with nuts and berries",
                sources=("ada_nutrition", "harvard_carbs"),
            ),
            Item(
                key="zumo_por_fruta",
                display="cambiar la fruta por zumo",
                claim=(
                    "Cambiar la fruta entera por zumo le quita la fibra"
                ),
                why="y la entera casi siempre gana",
                query="glass of orange juice next to whole oranges",
                search_text="a glass of juice beside whole oranges",
                sources=("who_diet", "harvard_fiber"),
            ),
            Item(
                key="sin_medir",
                display="no mirar nunca la ración",
                claim=(
                    "Comer del bol infla la ración sin darte cuenta"
                ),
                why="sírvete en un plato pequeño",
                query="small plate of cut fruit portion",
                search_text="a small plate with a portion of cut fruit",
                sources=("ada_nutrition", "fundacion_diabetes"),
            ),
            Item(
                key="quitar_piel",
                display="quitarle siempre la piel",
                claim=(
                    "Pelar la manzana o la pera le quita fibra"
                ),
                why="y la fibra suele suavizar la respuesta",
                query="apple with skin sliced on a board",
                search_text="a sliced apple with its skin on a board",
                sources=("harvard_fiber",),
            ),
            Item(
                key="deshidratada_punado",
                display="los puñados de fruta seca",
                claim=(
                    "Un puñado de fruta seca equivale a mucha más fresca"
                ),
                why="porque al perder agua el azúcar se concentra",
                query="handful of raisins and dried fruit",
                search_text="a handful of dried fruit",
                sources=("harvard_carbs", "who_diet"),
            ),
        ),
        hashtags=("#diabetes", "#glucosa", "#errores", "#fruta", "#nutricion"),
        hooks=(
            (
                "Si tu glucosa sube más de lo que esperas después de la "
                "fruta, mira esto."
            ),
            (
                "Comes fruta y después ves un pico que no te cuadra? Suele "
                "estar en uno de estos cinco fallos."
            ),
            (
                "Si te preocupa que la fruta te suba más de lo normal, el "
                "problema puede estar en como te la comes."
            ),
            (
                "Si comes fruta a diario, es fácil que estés repitiendo "
                "alguno de estos cinco fallos."
            ),
            "Si la fruta te sube más de lo que esperas, mira estos cinco fallos.",
        ),
    ),
    Topic(
        slug="errores-desayuno",
        worry="que el desayuno te dispare la glucosa",
        moment="a media mañana, después de desayunar",
        title="3 errores en el desayuno que pueden provocar picos de glucosa",
        format="error_solution",
        top_title="ERRORES DEL DESAYUNO",
        accent="ERRORES",
        promise=(
            "Tres fallos muy repetidos en el desayuno y que se puede poner "
            "en su lugar cada mañana"
        ),
        conclusion=(
            "Un desayuno con proteína, grasa buena y fibra suele sostener "
            "mucho mejor toda la mañana"
        ),
        answer=(
            "Desayunar solo hidratos, empezar por el zumo y comer de pie "
            "en dos minutos"
        ),
        takeaway=(
            "Elige uno para mañana: añade un huevo o un yogur natural a lo "
            "que ya desayunas"
        ),
        promises_all_items=True,
        items=(
            Item(
                key="solo_hidratos",
                display="desayunar solo hidratos",
                claim=(
                    "Tostada, galletas o cereales solos suelen subir más"
                ),
                why="añade huevo, queso fresco o yogur natural",
                query="scrambled eggs with wholegrain toast on a plate",
                search_text="a plate of eggs beside wholegrain bread",
                sources=("ada_nutrition", "harvard_carbs"),
            ),
            Item(
                key="empezar_por_zumo",
                display="empezar por el zumo",
                claim=(
                    "El zumo llega sin fibra y suele entrar muy rápido"
                ),
                why="toma la fruta entera y bebe agua",
                query="glass of orange juice next to whole oranges",
                search_text="a glass of juice beside whole oranges",
                sources=("who_diet", "harvard_fiber"),
            ),
            Item(
                key="desayuno_de_pie",
                display="desayunar de pie en dos minutos",
                claim=(
                    "Comer muy rápido puede dar una subida más marcada"
                ),
                why="siéntate y dale diez minutos de reloj",
                query="person sitting at a table having breakfast slowly",
                search_text="a person seated at a table eating breakfast",
                sources=("fundacion_diabetes", "redgdps"),
            ),
        ),
        hashtags=("#diabetes", "#glucosa", "#desayuno", "#errores", "#nutricion"),
        hooks=(
            (
                "Si tu glucosa se dispara después del desayuno, mira estos "
                "tres errores."
            ),
            (
                "Si tu glucosa se dispara después del desayuno, puede que sea "
                "uno de estos tres errores."
            ),
            (
                "Si te preocupa que el desayuno te dispare la glucosa, suelen "
                "ser estos tres errores."
            ),
            (
                "Si desayunas y a media mañana ves un pico que no te cuadra, "
                "mira estos tres fallos."
            ),
            (
                "Si te preocupa que el desayuno te dispare la glucosa, el "
                "problema suele estar en tres detalles."
            ),
            (
                "Desayunas parecido cada día y la glucosa no acompaña: casi "
                "siempre es uno de estos tres errores."
            ),
            (
                "Si el desayuno te sube más de lo que esperas, revisa estos "
                "tres fallos antes que la comida."
            ),
            (
                "Tres errores muy comunes en el desayuno, y que poner en su "
                "lugar desde mañana."
            ),
        ),
        opening_query="healthy breakfast table with eggs bread and fruit",
        opening_search_text="a breakfast table with eggs, bread and fruit",
    ),
    Topic(
        slug="desayunos-picos",
        worry="que el desayuno te dispare la glucosa",
        moment="después del desayuno",
        title="5 desayunos que pueden provocar picos de glucosa",
        format="list",
        top_title="DESAYUNOS Y GLUCOSA",
        accent="GLUCOSA",
        promise=(
            (
                "Cinco desayunos muy habituales que suelen dar una subida más "
                "marcada, y por que"
            )
        ),
        conclusion=(
            (
                "Un desayuno con proteína, grasa buena y fibra suele sostener "
                "mucho mejor la mañana"
            )
        ),
        answer=(
                   "Cereales azucarados, bolleria, zumo, pan blanco con "
                   "mermelada y yogures de sabores"
               ),
        takeaway=(
                     (
                         (
                             "Cambia una sola cosa mañana: añade proteína a lo que ya "
                             "desayunas, y vigila la cantidad"
                         )
                     )
                 ),
        items=(
            Item(
                key="cereales_azucarados",
                display="los cereales azucarados",
                claim=(
                    "Muchos cereales llevan azúcar añadido y poca fibra"
                ),
                why="mira azúcares y fibra por cien gramos",
                query="bowl of breakfast cereal with milk",
                search_text="a bowl of breakfast cereal with milk",
                sources=("who_diet", "harvard_carbs"),
            ),
            Item(
                key="bolleria",
                display="la bolleria",
                claim=(
                    "La bolleria junta harina refinada, azúcar y grasa"
                ),
                why="y suele saciar poco, vuelves a tener hambre pronto",
                query="croissants and pastries on a plate",
                search_text="pastries and croissants on a plate",
                sources=("who_diet", "harvard_carbs"),
            ),
            Item(
                key="zumo_desayuno",
                display="el zumo de la mañana",
                claim=(
                    "El zumo lleva el azúcar de varias piezas sin su fibra"
                ),
                why="y suele absorberse más rápido",
                query="glass of orange juice at breakfast table",
                search_text="a glass of orange juice on a breakfast table",
                sources=("who_diet", "harvard_fiber"),
            ),
            Item(
                key="pan_blanco_mermelada",
                display="la tostada de pan blanco con mermelada",
                claim=(
                    "Pan blanco con mermelada es casi solo carbohidrato rápido"
                ),
                why=(
                    "mejor integral y algo de proteína encima"
                ),
                query="white bread toast with jam on a plate",
                search_text="toast with jam on a plate",
                sources=("harvard_carbs", "diabetes_uk_food"),
            ),
            Item(
                key="yogur_sabores",
                display="los yogures de sabores",
                claim=(
                    "Los yogures de sabores suelen llevar azúcar añadido"
                ),
                why="el natural con fruta hace lo mismo",
                query="flavoured yogurt cups on a table",
                search_text="cups of flavoured yogurt",
                sources=("who_diet", "ada_nutrition"),
            ),
        ),
        hashtags=("#diabetes", "#desayuno", "#glucosa", "#nutricion"),
        hooks=(
            "Si tu glucosa sube mucho después del desayuno, mira estos cinco.",
            (
                "Te preocupa que el desayuno te dispare la glucosa? Estos "
                "cinco son los más habituales."
            ),
            (
                "Si desayunas siempre lo mismo y tu glucosa sube más de lo "
                "que esperas, comprueba esta lista."
            ),
            (
                "Este desayuno parece saludable, pero puede no ser la mejor "
                "opción para tu glucosa."
            ),
            "Si a media mañana vuelves a tener hambre, mira qué estás desayunando.",
        ),
        opening_query="breakfast table with coffee and toast",
        opening_search_text="a breakfast table with coffee and toast",
    ),
    Topic(
        slug="desayunos-equilibrados",
        worry="no saber qué desayunar sin que te suba la glucosa",
        moment="a media mañana",
        title="5 desayunos más equilibrados para personas con diabetes",
        format="list",
        top_title="DESAYUNOS MÁS EQUILIBRADOS",
        accent="EQUILIBRADOS",
        promise=(
            (
                "Cinco desayunos sencillos que suelen sostener mejor la "
                "mañana, sin complicarse"
            )
        ),
        conclusion=(
            (
                "La fórmula que suele funcionar es sencilla: proteína, grasa "
                "buena y fibra en el mismo plato"
            )
        ),
        answer=(
                   (
                       "Junta proteína, grasa buena y fibra: estos cinco lo hacen en "
                       "dos minutos"
                   )
               ),
        takeaway=(
                     "Elige uno y déjalo preparado esta noche; la cantidad también "
                     "cuenta"
                 ),
        items=(
            Item(
                key="yogur_nueces",
                display="yogur natural con nueces y fresas",
                claim=(
                    (
                        (
                            "Yogur natural con nueces y fresas junta proteína, grasa y "
                            "fibra"
                        )
                    )
                ),
                why="y suele sostener mejor la mañana",
                query="greek yogurt with walnuts and strawberries bowl",
                search_text="a bowl of yogurt with nuts and strawberries",
                sources=("ada_nutrition", "harvard_fiber"),
            ),
            Item(
                key="tostada_aguacate",
                display="tostada integral con aguacate y huevo",
                claim=(
                    (
                        (
                            (
                                "Pan integral con aguacate y huevo suma fibra, grasa y "
                                "proteína"
                            )
                        )
                    )
                ),
                why="y sacia más que la tostada sola",
                query="avocado toast with egg on a plate",
                search_text="avocado toast topped with an egg",
                sources=("ada_nutrition", "harvard_fiber"),
            ),
            Item(
                key="avena",
                display="avena con canela y frutos rojos",
                claim=(
                    "La avena en copos aporta fibra soluble"
                ),
                why="y suele absorberse más despacio que los refinados",
                query="oatmeal bowl with berries and cinnamon",
                search_text="a bowl of oatmeal with berries",
                sources=("harvard_fiber", "harvard_carbs"),
            ),
            Item(
                key="huevos_verduras",
                display="huevos revueltos con verduras",
                claim=(
                    "Unos huevos con verduras aportan muy pocos carbohidratos"
                ),
                why="y suelen quitarte el hambre un buen rato",
                query="scrambled eggs with vegetables on a plate",
                search_text="scrambled eggs with vegetables",
                sources=("ada_nutrition", "harvard_carbs"),
            ),
            Item(
                key="requeson_kiwi",
                display="requesón con kiwi",
                claim=(
                    "El requesón con kiwi suma proteína y fibra"
                ),
                why="y lo tienes listo en dos minutos",
                query="cottage cheese with kiwi in a bowl",
                search_text="a bowl of cottage cheese with fruit",
                sources=("ada_nutrition",),
            ),
        ),
        hashtags=("#diabetes", "#desayuno", "#glucosa", "#recetassaludables"),
        hooks=(
            (
                "Si no sabes qué desayunar sin que te suba la glucosa, apunta "
                "estos cinco."
            ),
            "Te preocupa el desayuno y siempre acabas tomando lo mismo? Prueba con uno de estos cinco.",
            (
                "Si a media mañana ya tienes hambre otra vez, prueba con uno "
                "de estos cinco desayunos."
            ),
            "Si tienes diabetes y quieres desayunar sin complicarte, estos cinco se preparan en minutos.",
            "Si el desayuno se te queda corto y acabas picando, mira estas cinco opciones.",
        ),
        opening_query="healthy breakfast bowl on a table",
        opening_search_text="a healthy breakfast on a table",
    ),
    Topic(
        slug="snacks-carbohidratos",
        worry="picar entre horas y que se te descontrole la glucosa",
        moment="a media tarde",
        title="5 snacks sencillos para controlar mejor los carbohidratos",
        format="list",
        top_title="SNACKS SIN PICOS",
        accent="SNACKS",
        promise=(
            (
                "Cinco ideas rápidas para cuando entra hambre entre horas, "
                "sin complicarse"
            )
        ),
        conclusion=(
            (
                "Un snack con proteína o grasa suele sostener mucho mejor que "
                "uno solo de carbohidratos"
            )
        ),
        answer=(
                   "Nueces, yogur natural, hummus con zanahoria, huevo duro y "
                   "manzana con crema de cacahuete"
               ),
        takeaway="Ten dos de estos a mano y el picoteo deja de decidirse solo; cuida la cantidad",
        items=(
            Item(
                key="nueces",
                display="un puñado de nueces",
                claim=(
                    "Las nueces aportan grasa y fibra con pocos carbohidratos"
                ),
                why="y con un puñado pequeño te sobra",
                query="handful of walnuts in a bowl",
                search_text="a small bowl of walnuts",
                sources=("ada_nutrition", "harvard_fiber"),
            ),
            Item(
                key="yogur_natural",
                display="yogur natural sin azúcar",
                claim=(
                    "El yogur natural sin azúcar añadido aporta proteína"
                ),
                why="y suele saciar bastante bien",
                query="plain natural yogurt in a bowl",
                search_text="a bowl of plain white yogurt",
                sources=("ada_nutrition", "who_diet"),
            ),
            Item(
                key="hummus_zanahoria",
                display="hummus con zanahoria",
                claim=(
                    "El hummus con zanahoria suma fibra y proteína vegetal"
                ),
                why="y lo preparas en un minuto",
                query="hummus with carrot sticks on a plate",
                search_text="hummus with carrot sticks",
                sources=("harvard_fiber", "ada_nutrition"),
            ),
            Item(
                key="huevo_duro",
                display="un huevo duro",
                claim=(
                    "Un huevo duro apenas aporta carbohidratos"
                ),
                why="y suele quitarte el hambre bastante bien",
                query="boiled eggs cut in half on a plate",
                search_text="boiled eggs on a plate",
                sources=("ada_nutrition",),
            ),
            Item(
                key="manzana_crema",
                display="manzana con crema de cacahuete",
                claim=(
                    (
                        "La manzana con crema de cacahuete suma grasa y proteína"
                    )
                ),
                why="que sea sin azúcar añadido",
                query="apple slices with peanut butter on a plate",
                search_text="apple slices with peanut butter",
                sources=("ada_nutrition", "harvard_carbs"),
            ),
        ),
        hashtags=("#diabetes", "#snacks", "#glucosa", "#meriendasaludable"),
        hooks=(
            "Si entre horas siempre acabas picando lo primero que pillas, apunta estos cinco.",
            "Te preocupa picar entre horas y que se te descontrole la glucosa? Ten preparados estos cinco.",
            "Si a media tarde te entra hambre y acabas tirando de galletas, mira estas cinco opciones.",
            (
                "Si picas entre horas y luego ves números que no te cuadran, "
                "cambia lo que picas."
            ),
            (
                "Si tienes diabetes y el picoteo es tu punto débil, estos "
                "cinco te lo ponen fácil."
            ),
        ),
        opening_query="healthy snack plate on a table",
        opening_search_text="a plate of healthy snacks",
    ),
    Topic(
        slug="combinar-fruta",
        worry="ver un pico grande después de comer fruta sola",
        moment="después de la fruta",
        title="Cómo combinar la fruta para moderar la respuesta glucémica",
        format="combination",
        top_title="COMBINA ASÍ TU FRUTA 🍏",
        accent="COMBINA",
        promise=(
            "Cuatro combinaciones sencillas que suelen moderar la subida sin "
            "quitar la fruta"
        ),
        conclusion=(
            (
                "La fruta sola no es un error, pero acompañarla suele hacer "
                "que la curva sea más suave"
            )
        ),
        answer=(
                   (
                       "Acompáñala con proteína o con grasa, tomala entera y mejor "
                       "de postre"
                   )
               ),
        takeaway=(
                     (
                         "La próxima vez que tomes fruta, añade un yogur natural o un "
                         "puñado de nueces"
                     )
                 ),
        promises_all_items=True,
        items=(
            Item(
                key="fruta_proteina",
                display="fruta con proteína",
                claim=(
                    "Añade proteína, como yogur natural o requesón"
                ),
                why="porque suele hacer la digestión más lenta",
                query="yogurt bowl with fresh fruit",
                search_text="a bowl of yogurt with fresh fruit",
                sources=("ada_nutrition", "harvard_carbs"),
            ),
            Item(
                key="fruta_grasa",
                display="fruta con grasa buena",
                claim=(
                    "Un puñado de frutos secos junto a la fruta añade grasa"
                ),
                why="y suele moderar la respuesta",
                query="almonds and fruit on a wooden board",
                search_text="almonds beside fresh fruit",
                sources=("ada_nutrition", "harvard_fiber"),
            ),
            Item(
                key="fruta_entera",
                display="la fruta entera antes que en zumo",
                claim=(
                    "Toma la fruta entera y conserva su fibra"
                ),
                why="que es parte de lo que suaviza la absorción",
                query="whole apples and pears on a table",
                search_text="whole fruit on a table",
                sources=("harvard_fiber", "who_diet"),
            ),
            Item(
                key="fruta_postre",
                display="la fruta después de comer",
                claim=(
                    "Tomarla de postre suele subir menos que tomarla sola en ayunas"
                ),
                why="porque el resto del plato ya ralentiza la digestión",
                query="plate of fruit after a meal on a table",
                search_text="a plate of fruit on a dining table",
                sources=("ada_nutrition", "diabetes_uk_food"),
            ),
        ),
        hashtags=("#diabetes", "#glucosa", "#fruta", "#nutricion"),
        hooks=(
            (
                "Si comes fruta sola y después ves un pico más grande de lo "
                "que esperas, prueba a combinarla así."
            ),
            "Te preocupa que la fruta sola te suba la glucosa? Con estas cuatro combinaciones cambia bastante.",
            (
                "Si comes fruta sola cuando tienes mucha hambre, presta "
                "atención a esto."
            ),
            "Cuatro combinaciones sencillas para tomar fruta sin renunciar a ella.",
            (
                "Si quieres seguir comiendo fruta sin que te suba tanto, lo "
                "que la acompaña importa."
            ),
        ),
    ),
    Topic(
        slug="naranja-vs-zumo",
        worry="que el zumo del desayuno te suba la glucosa",
        moment="después del desayuno",
        title="Naranja entera o zumo de naranja: qué cambia para tu glucosa",
        format="comparison",
        top_title="NARANJA VS ZUMO 🍊",
        accent="VS",
        promise=(
            "La diferencia práctica entre las dos, y cuando conviene cada una"
        ),
        conclusion=(
            (
                "La naranja entera suele ser la mejor opción del día a día; "
                "el zumo, algo puntual y en vaso pequeño"
            )
        ),
        answer="La naranja entera conserva la fibra y el zumo la pierde casi toda",
        takeaway=(
                     (
                         "Mañana desayuna la naranja entera y deja el zumo para algo "
                         "puntual"
                     )
                 ),
        items=(NARANJA_ENTERA, ZUMO),
        hashtags=("#diabetes", "#glucosa", "#zumo", "#fruta", "#nutricion"),
        hooks=(
            (
                "Si te preocupa que el zumo te suba la glucosa: misma fruta, "
                "distinta respuesta."
            ),
            (
                "Si te preocupa el zumo del desayuno: misma fruta, pero tu "
                "glucosa no la recibe igual."
            ),
            (
                "Una naranja y un vaso de zumo vienen de la misma fruta, pero "
                "tu cuerpo no los recibe igual."
            ),
            (
                "Si desayunas zumo cada mañana y te preocupa que te suba la "
                "glucosa, mira esta diferencia."
            ),
            "Te preocupa el zumo del desayuno? La naranja entera y el zumo no se comportan igual.",
            "Si crees que el zumo natural es lo mismo que la naranja, esto te interesa.",
            "Si desayunas zumo cada mañana, esta diferencia te interesa.",
            "Antes de exprimir la naranja de mañana, mira esto.",
        ),
        opening_query="oranges and a glass of juice side by side",
        opening_search_text="oranges next to a glass of orange juice",
    ),
    Topic(
        slug="fruta-deshidratada",
        worry="pasarte de ración con la fruta seca",
        moment="entre horas",
        title="Qué ocurre cuando comemos fruta deshidratada",
        format="error_solution",
        top_title="FRUTA SECA: OJO A ESTO",
        accent="OJO",
        promise=(
            "Qué cambia al secar la fruta y como seguir tomandola sin sustos"
        ),
        conclusion=(
            (
                "La fruta deshidratada no está descartada: cambia mucho si "
                "mides la ración y la acompañas"
            )
        ),
        answer=(
                   (
                       "Al perder agua concentra el azúcar, así que mide el puñado y "
                       "acompáñala"
                   )
               ),
        takeaway="Sírvete un puñado corto en un platito y guarda la bolsa",
        items=(
            FRUTA_DESHIDRATADA,
            DATILES,
            Item(
                key="racion_seca",
                display="la ración de referencia",
                claim=(
                    "Una ración es bastante pequeña, un puñado corto"
                ),
                why="sírvela en un platito y no comas de la bolsa",
                query="small bowl of dried fruit portion",
                search_text="a small bowl with a portion of dried fruit",
                sources=("ada_nutrition", "fundacion_diabetes"),
            ),
            Item(
                key="seca_con_nueces",
                display="acompañarla",
                claim=(
                    "Combínala con frutos secos o yogur natural"
                ),
                why="porque la grasa y la proteína ralentizan la digestión",
                query="dried fruit and nuts mixed in a bowl",
                search_text="a bowl of mixed nuts and dried fruit",
                sources=("ada_nutrition", "harvard_carbs"),
            ),
        ),
        hashtags=("#diabetes", "#glucosa", "#frutosecos", "#nutricion"),
        hooks=(
            (
                "Si picas fruta deshidratada entre horas y te preocupa "
                "pasarte de ración, mira esto."
            ),
            (
                "Te preocupa pasarte con las pasas o los dátiles sin darte "
                "cuenta? Esta es la referencia."
            ),
            (
                "Si comes fruta seca pensando que es igual que la fresca, "
                "aquí la ración cuenta el doble."
            ),
            "Si llevas fruta deshidratada para picar, revisa cuánta estás tomando.",
            "Un puñado de pasas y un puñado de uvas no son lo mismo, ni de lejos.",
        ),
    ),
    Topic(
        slug="cereales-desayuno",
        worry="que tus cereales de siempre te suban la glucosa",
        moment="después del desayuno",
        title="Errores comunes con los cereales del desayuno",
        format="error_solution",
        top_title="CEREALES: 4 ERRORES",
        accent="ERRORES",
        promise=(
            "Cuatro cosas que suelen pasarse por alto en el pasillo de los "
            "cereales"
        ),
        conclusion=(
            (
                "Con mirar dos números en la etiqueta, azúcares y fibra, ya "
                "se decide mucho mejor"
            )
        ),
        answer="Mira los azúcares, la fibra, la ración real y con que lo acompañas",
        takeaway=(
                     (
                         "Antes de comprar, mira dos números: azúcares y fibra por "
                         "cien gramos"
                     )
                 ),
        promises_all_items=True,
        items=(
            Item(
                key="etiqueta_azucares",
                display="no mirar los azúcares",
                claim=(
                    (
                        (
                            "Muchos cereales llevan azúcar añadido aunque el envase "
                            "parezca saludable"
                        )
                    )
                ),
                why="mira los azúcares por cien gramos",
                query="breakfast cereal nutrition label close up",
                search_text="a cereal box nutrition label",
                sources=("who_diet",),
            ),
            Item(
                key="poca_fibra",
                display="ignorar la fibra",
                claim=(
                    (
                        (
                            "Un cereal con poca fibra suele absorberse más rápido que uno "
                            "integral"
                        )
                    )
                ),
                why="busca al menos seis gramos por cien",
                query="whole grain cereal in a bowl",
                search_text="a bowl of whole grain cereal",
                sources=("harvard_fiber",),
            ),
            Item(
                key="racion_cereal",
                display="servir a ojo",
                claim=(
                    "La ración real suele ser mucho menor que el bol que llenas"
                ),
                why="pésala una vez y te queda la referencia",
                query="measuring a small bowl of cereal",
                search_text="a small bowl of cereal being served",
                sources=("ada_nutrition", "fundacion_diabetes"),
            ),
            Item(
                key="cereal_solo",
                display="tomarlo solo",
                claim=(
                    "Tomarlo solo, sin proteína ni grasa, suele subir más"
                ),
                why="añade yogur natural o un puñado de nueces",
                query="cereal bowl with yogurt and nuts",
                search_text="a bowl of cereal with yogurt and nuts",
                sources=("ada_nutrition", "harvard_carbs"),
            ),
        ),
        hashtags=("#diabetes", "#desayuno", "#cereales", "#etiquetas"),
        hooks=(
            "Si desayunas cereales y te preocupa que te suban la glucosa, revisa estos cuatro detalles.",
            (
                "Te preocupa que tus cereales de siempre no sean tan "
                "integrales como parecen? Mira la etiqueta así."
            ),
            "Si desayunas cereales casi a diario, revisa estos cuatro detalles.",
            "Si compras cereales por lo que dice el envase, esto te va a interesar.",
            "Cuatro errores con los cereales del desayuno que se repiten mucho.",
        ),
    ),
    Topic(
        slug="yogur-natural-vs-azucarado",
        worry="llevarte azúcar añadido sin darte cuenta",
        title="Yogur natural o yogur azucarado: qué cambia de verdad",
        format="comparison",
        top_title="YOGUR: NATURAL VS AZUCARADO",
        accent="VS",
        promise="La diferencia real entre los dos, en la etiqueta y en el plato",
        conclusion=(
            (
                "El yogur natural con fruta fresca da el mismo gusto sin el "
                "azúcar añadido del de sabores"
            )
        ),
        answer=(
                   (
                       "El natural solo lleva el azúcar de la leche y el de sabores "
                       "suma añadido"
                   )
               ),
        takeaway=(
                     (
                         "Compra natural y añádele tu la fruta: mismo gusto sin azúcar "
                         "añadido"
                     )
                 ),
        items=(
            Item(
                key="yogur_nat",
                display="el yogur natural",
                claim=(
                    "El yogur natural aporta proteína y solo el azúcar de la leche"
                ),
                why="sin azúcares añadidos en los ingredientes",
                query="plain yogurt in a glass bowl",
                search_text="a bowl of plain yogurt",
                sources=("ada_nutrition", "who_diet"),
            ),
            Item(
                key="yogur_azucarado",
                display="el yogur de sabores",
                claim=(
                    "Los de sabores suelen sumar varios gramos de azúcar añadido"
                ),
                why="aparece como azúcar, jarabe o sirope",
                query="flavoured fruit yogurt pots",
                search_text="pots of flavoured yogurt",
                sources=("who_diet",),
            ),
        ),
        hashtags=("#diabetes", "#yogur", "#azucar", "#etiquetas"),
        hooks=(
            (
                "Si compras yogures de sabores y te preocupa llevarte azúcar "
                "añadido sin darte cuenta, mira esto."
            ),
            (
                "Te preocupa el azúcar añadido del yogur? La diferencia esta "
                "en dos líneas de la etiqueta."
            ),
            "Si crees que todos los yogures son parecidos, compara estas dos etiquetas.",
            "Si compras yogures de sabores pensando que son iguales, mira esto.",
            "Si quieres yogur con sabor sin azúcar añadido, hay una forma fácil.",
        ),
    ),
    Topic(
        slug="azucar-oculto",
        worry="estar tomando azúcar añadido sin saberlo",
        title="Alimentos que parecen saludables y llevan bastante azúcar añadido",
        format="list",
        top_title="AZÚCAR DONDE NO LO ESPERAS",
        accent="AZÚCAR",
        promise=(
            "Cinco productos del carro de la compra que suelen sorprender al "
            "leer la etiqueta"
        ),
        conclusion=(
            (
                "Leer la línea de azúcares en la etiqueta es el hábito que "
                "más cambia la compra"
            )
        ),
        answer=(
                   (
                       "Granola, barritas, salsas preparadas, zumos envasados y "
                       "lácteos de sabores"
                   )
               ),
        takeaway=(
                     (
                         "Dale la vuelta al envase y lee la línea de azúcares antes de "
                         "echarlo al carro"
                     )
                 ),
        promises_all_items=True,
        items=(
            Item(
                key="granola",
                display="la granola",
                claim=(
                    "La granola suele llevar miel o sirope para quedar crujiente"
                ),
                why="y eso es azúcar añadido",
                query="granola in a bowl with milk",
                search_text="a bowl of granola",
                sources=("who_diet",),
            ),
            Item(
                key="barritas",
                display="las barritas de cereales",
                claim=(
                    "Muchas barritas llevan tanto azúcar añadido como una galleta"
                ),
                why="lo ves en las tres primeras líneas",
                query="cereal bars on a table",
                search_text="cereal bars on a table",
                sources=("who_diet",),
            ),
            Item(
                key="salsas",
                display="las salsas preparadas",
                claim=(
                    (
                        (
                            "El ketchup y las salsas de tomate preparadas suelen llevar "
                            "azúcar"
                        )
                    )
                ),
                why="poca cantidad, pero la usas a diario",
                query="ketchup and sauce bottles on a table",
                search_text="bottles of sauce on a table",
                sources=("who_diet",),
            ),
            Item(
                key="zumos_envasados",
                display="los zumos envasados",
                claim=(
                    "Aunque digan sin azúcares añadidos, el de la fruta sigue libre"
                ),
                why="sin la fibra que llevaba la pieza entera",
                query="packaged fruit juice cartons",
                search_text="cartons of fruit juice",
                sources=("who_diet", "harvard_fiber"),
            ),
            Item(
                key="lacteos_sabor",
                display="los lácteos de sabores",
                claim=(
                    (
                        (
                            "Batidos y postres lácteos de sabores suelen sumar azúcar "
                            "añadido"
                        )
                    )
                ),
                why="y la versión natural cuesta lo mismo",
                query="flavoured milk drinks on a shelf",
                search_text="flavoured milk drinks",
                sources=("who_diet",),
            ),
        ),
        hashtags=("#diabetes", "#azucar", "#etiquetas", "#compra", "#glucosa"),
        hooks=(
            (
                "Si te preocupa estar tomando azúcar añadido sin saberlo, "
                "revisa estos cinco productos."
            ),
            (
                "Estos cinco productos parecen saludables y suelen llevar "
                "bastante azúcar añadido."
            ),
            (
                "Te preocupa el azúcar que no ves en la etiqueta? Empieza por "
                "estos cinco del carro."
            ),
            "Si compras alguno de estos cada semana, merece la pena leer la etiqueta.",
            "Si crees que no tomas azúcar añadido, mira estos cinco habituales.",
        ),
        opening_query="supermarket shelf with packaged food",
        opening_search_text="packaged food on a supermarket shelf",
    ),
    Topic(
        slug="tamano-racion",
        worry="no tener claro cuánta cantidad es demasiada",
        title="Cómo influye el tamaño de la ración en la glucosa",
        format="list",
        top_title="LA RACIÓN LO CAMBIA TODO",
        accent="RACIÓN",
        promise=(
            "Cuatro ideas prácticas para que la cantidad deje de ser una lotería"
        ),
        conclusion=(
            "El mismo alimento puede sentar de formas muy distintas solo por la "
            "cantidad que te sirves"
        ),
        answer=(
                   (
                       "La cantidad cambia la respuesta: plato pequeño, pesar una "
                       "vez y no comer del paquete"
                   )
               ),
        takeaway=(
                     (
                         "Pesa una vez tu ración habitual y tendrás la referencia para "
                         "siempre"
                     )
                 ),
        promises_all_items=True,
        items=(
            Item(
                key="mismo_alimento",
                display="el mismo alimento, distinta cantidad",
                claim=(
                    "El mismo alimento puede responder distinto según la cantidad"
                ),
                why="por eso hablar de alimentos buenos o malos se queda corto",
                query="two plates with different portion sizes",
                search_text="two plates with different portion sizes",
                sources=("ada_nutrition", "harvard_carbs"),
            ),
            Item(
                key="plato_pequeno",
                display="el plato pequeño",
                claim=(
                    "Servir en un plato más pequeño suele reducir la ración"
                ),
                why="y sin sensación de estar renunciando a nada",
                query="small plate with a served meal",
                search_text="a small plate with a served meal",
                sources=("diabetes_uk_food",),
            ),
            Item(
                key="pesar_una_vez",
                display="pesarlo una sola vez",
                claim=(
                    "Pesa una vez tu ración habitual"
                ),
                why="y después la calculas a ojo con bastante acierto",
                query="kitchen scale weighing food",
                search_text="food being weighed on a kitchen scale",
                sources=("fundacion_diabetes", "ada_nutrition"),
            ),
            Item(
                key="del_paquete_no",
                display="no comer del paquete",
                claim=(
                    "Comer del paquete suele acabar en mucha más cantidad"
                ),
                why="sírvete antes en un bol",
                query="bowl of snacks served from a package",
                search_text="a bowl of snacks on a table",
                sources=("diabetes_uk_food",),
            ),
        ),
        hashtags=("#diabetes", "#raciones", "#glucosa", "#habitos"),
        hooks=(
            (
                "Si te preocupa no tener claro cuánta cantidad es demasiada, "
                "empieza por estas cuatro ideas."
            ),
            (
                "Te preocupa pasarte de ración sin darte cuenta? Estas cuatro "
                "referencias lo hacen fácil."
            ),
            (
                "Si comes bien y aun así tu glucosa sube más de lo que "
                "esperas, mira la cantidad."
            ),
            (
                "Si nunca has mirado cuánto te sirves, estas cuatro ideas te "
                "van a servir."
            ),
            "Muchas veces no es el alimento: es cuánto te sirves.",
        ),
    ),
    Topic(
        slug="carbohidratos-y-fibra",
        worry="no entender las etiquetas y elegir a ciegas",
        title="Carbohidratos y fibra explicados de forma sencilla",
        format="list",
        top_title="CARBOHIDRATOS Y FIBRA",
        accent="FIBRA",
        promise="Cuatro ideas básicas para leer cualquier etiqueta con criterio",
        conclusion=(
            "Con entender carbohidratos y fibra ya se decide mucho mejor en el "
            "supermercado"
        ),
        answer=(
                   "Los carbohidratos influyen en tu glucosa y la fibra suele "
                   "frenar esa subida"
               ),
        takeaway="En la etiqueta mira tres líneas: carbohidratos, azúcares y fibra",
        items=(
            Item(
                key="que_son_carbos",
                display="que son los carbohidratos",
                claim=(
                    (
                        (
                            "Los carbohidratos son lo que más influye en tu glucosa "
                            "después de comer"
                        )
                    )
                ),
                why="están en cereales, fruta, legumbres y leche",
                query="bread pasta rice and legumes on a table",
                search_text="bread, pasta and rice on a table",
                sources=("harvard_carbs", "ada_nutrition"),
            ),
            Item(
                key="fibra_no_sube",
                display="la fibra",
                claim=(
                    (
                        (
                            "La fibra apenas se absorbe y suele ralentizar la digestión "
                            "del resto"
                        )
                    )
                ),
                why="por eso lo integral se comporta distinto",
                query="whole grain bread and vegetables",
                search_text="whole grain bread and vegetables",
                sources=("harvard_fiber",),
            ),
            Item(
                key="etiqueta",
                display="cómo leer la etiqueta",
                claim=(
                    (
                        (
                            "En la etiqueta mira carbohidratos, de los cuales azúcares, y "
                            "fibra"
                        )
                    )
                ),
                why="esas tres líneas dan casi toda la información",
                query="nutrition facts label close up",
                search_text="a nutrition facts label",
                sources=("who_diet", "ada_nutrition"),
            ),
            Item(
                key="integral",
                display="integral de verdad",
                claim=(
                    "Que ponga integral no siempre significa que la harina lo sea"
                ),
                why="debe aparecer la primera en los ingredientes",
                query="whole grain bread loaf on a board",
                search_text="a loaf of whole grain bread",
                sources=("who_diet", "harvard_fiber"),
            ),
        ),
        hashtags=("#diabetes", "#carbohidratos", "#fibra", "#etiquetas"),
        hooks=(
            "Si te preocupa no entender las etiquetas y elegir a ciegas, con dos conceptos te sobra.",
            (
                "Te preocupa mirar una etiqueta y no saber qué número "
                "importa? Empieza por estos dos."
            ),
            "Si las etiquetas te suenan a chino, empieza por estas cuatro ideas.",
            "Si eliges pan o pasta sin saber qué mirar, esto te lo simplifica.",
            "Carbohidratos y fibra explicados sin tecnicismos y en cuatro pasos.",
        ),
    ),
    Topic(
        slug="respuesta-individual",
        worry="que lo que le funciona a otros a ti no te funcione",
        title="Por qué dos personas pueden responder distinto al mismo alimento",
        format="myth",
        top_title="CADA PERSONA ES DISTINTA",
        accent="DISTINTA",
        promise=(
            (
                "Por qué las listas generales son solo un punto de partida y "
                "que hacer con eso"
            )
        ),
        conclusion=(
            "Las listas orientan, pero tu propia experiencia y tu equipo "
            "sanitario mandan sobre cualquier lista"
        ),
        answer="Influyen tu actividad, el momento del día y con que lo combinas",
        takeaway="Comprueba como te sienta a ti y coméntalo con tu equipo sanitario",
        items=(
            Item(
                key="variabilidad",
                display="la variabilidad entre personas",
                claim=(
                    (
                        "La respuesta a un mismo alimento puede variar bastante entre "
                        "personas"
                    )
                ),
                why="influyen el tratamiento, la actividad y muchos factores",
                query="two people eating a meal at a table",
                search_text="two people sharing a meal at a table",
                sources=("ada_nutrition", "who_diabetes"),
            ),
            Item(
                key="contexto",
                display="el contexto de la comida",
                claim=(
                    (
                        (
                            "El mismo alimento puede comportarse distinto según con que "
                            "lo combines"
                        )
                    )
                ),
                why="no es lo mismo solo que dentro de una comida",
                query="balanced meal plate with vegetables and protein",
                search_text="a balanced plate of food",
                sources=("ada_nutrition", "harvard_carbs"),
            ),
            Item(
                key="medir",
                display="comprobarlo en tu caso",
                claim=(
                    (
                        (
                            "Comprobar como te sienta a ti suele ser más útil que "
                            "cualquier lista"
                        )
                    )
                ),
                why="siempre dentro de lo que te indique tu equipo sanitario",
                query="person using a glucose meter at home",
                search_text="a glucose meter on a table",
                sources=("who_diabetes", "redgdps"),
            ),
        ),
        hashtags=("#diabetes", "#glucosa", "#educaciondiabetologica"),
        hooks=(
            "Te preocupa que un mismo alimento suba la glucosa distinto en cada persona? Esto te interesa.",
            (
                "Si a otra persona le sienta bien el mismo desayuno y a ti te "
                "sube la glucosa más de lo que esperas, esto lo explica."
            ),
            (
                "Si sigues una lista de alimentos y tu glucosa sube más de lo "
                "que esperas, hay una explicación."
            ),
            (
                "Si tienes diabetes y el mismo alimento te sube la glucosa "
                "más que a otra persona, esto lo explica."
            ),
            "Si comes lo mismo que otra persona y tu glucosa responde distinto, no es cosa tuya.",
        ),
        opening_query="two people having breakfast together",
        opening_search_text="two people at a breakfast table",
    ),
    Topic(
        slug="mito-dejar-fruta",
        worry="tener que renunciar a la fruta por miedo al azúcar",
        title="Hay que dejar de comer fruta si tienes diabetes",
        format="myth",
        top_title="MITO: DEJAR LA FRUTA",
        accent="MITO",
        promise="Qué dicen las guías y que se puede hacer en la práctica",
        conclusion=(
            (
                "La fruta cabe en la alimentación de la mayoría de personas "
                "con diabetes: manda la cantidad, la forma y el conjunto del "
                "día"
            )
        ),
        answer=(
                   (
                       "No: las guías suelen incluirla, y lo que manda es la "
                       "cantidad y la forma"
                   )
               ),
        takeaway=(
                     (
                         "Sigue tomando fruta entera en raciones medidas y consúltalo "
                         "con tu equipo sanitario"
                     )
                 ),
        items=(
            Item(
                key="mito_respuesta",
                display="la respuesta corta",
                claim=(
                    "Las guías de alimentación en diabetes suelen incluir la fruta"
                ),
                why="no aparece como un alimento a eliminar",
                query="fresh fruit bowl on a kitchen table",
                search_text="a bowl of fresh fruit on a table",
                sources=("ada_nutrition", "who_diet", "diabetes_uk_food"),
            ),
            Item(
                key="mito_matiz",
                display="el matiz importante",
                claim=(
                    "Lo que suele cambiar la respuesta es la cantidad y la forma"
                ),
                why="entera mejor que en zumo, y en raciones medidas",
                query="portion of cut fruit on a small plate",
                search_text="a small plate with cut fruit",
                sources=("harvard_fiber", "ada_nutrition"),
            ),
            Item(
                key="mito_individual",
                display="y tu caso concreto",
                claim=(
                    (
                        "Cada persona puede responder distinto, y el tratamiento "
                        "influye"
                    )
                ),
                why="tu equipo sanitario lo ajusta contigo",
                query="doctor talking with a patient at a desk",
                search_text="a healthcare professional talking with a person",
                sources=("who_diabetes", "redgdps"),
            ),
        ),
        hashtags=("#diabetes", "#mitos", "#fruta", "#glucosa"),
        hooks=(
            "Si te han dicho que con diabetes hay que renunciar a la fruta, esto te interesa.",
            (
                "Te preocupa tener que dejar la fruta por miedo al azúcar? "
                "Mira lo qué dicen las guías."
            ),
            (
                "Antes de dejar la fruta por miedo al azúcar, mira lo qué "
                "dicen las guías."
            ),
            (
                "Si tienes diabetes, dejar toda la fruta por miedo al azúcar "
                "puede no ser necesario."
            ),
            (
                "Si crees que la fruta está descartada con diabetes, esto te "
                "va a sorprender."
            ),
        ),
    ),
    Topic(
        slug="ranking-frutas",
        worry="no saber qué fruta elegir para no disparar tu glucosa",
        title="5 frutas ordenadas de menor a mayor impacto aproximado",
        format="ranking",
        top_title="DE MENOR A MAYOR IMPACTO",
        accent="IMPACTO",
        promise=(
            (
                "Un orden orientativo por ración habitual, que cambia según "
                "la cantidad y la madurez"
            )
        ),
        conclusion=(
            (
                "Es un orden aproximado, no una regla: la ración y la madurez "
                "pueden cambiarlo por completo"
            )
        ),
        answer=(
                   (
                       "Aguacate, fresas, frambuesas, manzana con piel y plátano "
                       "maduro, en ese orden"
                   )
               ),
        takeaway=(
                     (
                         (
                             "Usa el orden como referencia, pero mide la ración: eso pesa "
                             "más"
                         )
                     )
                 ),
        items=(AGUACATE, FRESAS, FRAMBUESAS, MANZANA, PLATANO_MADURO),
        hashtags=("#diabetes", "#fruta", "#glucosa", "#nutricion"),
        hooks=(
            "Si te preocupa que la fruta te suba la glucosa, guarda este orden de menor a mayor.",
            "Te preocupa elegir mal la fruta? Esta es la lista de menor a mayor impacto aproximado.",
            (
                "Si te preocupa elegir mal la fruta, este orden te da una "
                "referencia rápida."
            ),
            (
                "Si nunca sabes qué fruta elegir para no disparar tu glucosa, "
                "guarda estas cinco opciones."
            ),
            (
                "Si comparas frutas y no tienes claro cual pesa más en tu "
                "glucosa, mira este orden."
            ),
        ),
    ),
)

BY_SLUG: dict[str, Topic] = {t.slug: t for t in TOPICS}


def find_topic(text: str) -> Topic | None:
    """The topic a request names, by slug or by a loose title match."""

    wanted = str(text or "").strip().lower()
    if not wanted:
        return None
    if wanted in BY_SLUG:
        return BY_SLUG[wanted]
    for topic in TOPICS:
        if topic.title.lower() == wanted:
            return topic
    scored: list[tuple[int, Topic]] = []
    words = {w for w in _words(wanted) if len(w) > 3}
    for topic in TOPICS:
        overlap = len(words & {w for w in _words(topic.title) if len(w) > 3})
        if overlap:
            scored.append((overlap, topic))
    if not scored:
        return None
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return scored[0][1]


def _words(text: str) -> set[str]:
    import re
    import unicodedata

    flat = unicodedata.normalize("NFKD", str(text or "").lower())
    flat = "".join(c for c in flat if not unicodedata.combining(c))
    return set(re.findall(r"[a-z0-9]+", flat))


def topics_for(fmt: str = "") -> list[Topic]:
    key = str(fmt or "").strip().lower()
    if not key:
        return list(TOPICS)
    return [t for t in TOPICS if t.format == key]


def claims_of(topic: Topic) -> list[tuple[str, tuple[str, ...]]]:
    """Every factual sentence in the topic, with the sources behind it."""

    return [(item.claim, item.sources) for item in topic.items]


def all_items() -> Iterable[Item]:
    for topic in TOPICS:
        yield from topic.items
