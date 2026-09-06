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
        "Las fresas suelen aportar menos carbohidratos por racion que muchas "
        "otras frutas"
    ),
    why="y su fibra puede hacer que la subida sea mas gradual",
    query="fresh strawberries in a white bowl",
    search_text="a bowl of fresh red strawberries",
    sources=("harvard_carbs", "harvard_fiber", "ada_nutrition"),
)

FRAMBUESAS = Item(
    key="frambuesas",
    display="las frambuesas",
    claim=(
        "Las frambuesas destacan por su fibra: aportan bastante para los "
        "carbohidratos que llevan"
    ),
    why="y la fibra es justo lo que suele moderar la respuesta",
    query="fresh raspberries close up bowl",
    search_text="a bowl of fresh raspberries",
    sources=("harvard_fiber", "ada_nutrition"),
)

ARANDANOS = Item(
    key="arandanos",
    display="los arandanos",
    claim=(
        "Los arandanos suelen encajar bien en raciones pequenas, aunque "
        "concentran algo mas de azucar que otras bayas"
    ),
    why="asi que aqui la cantidad importa mas de lo que parece",
    query="fresh blueberries in a bowl",
    search_text="a bowl of fresh blueberries",
    sources=("harvard_carbs", "diabetes_uk_food"),
)

KIWI = Item(
    key="kiwi",
    display="el kiwi",
    claim=(
        "El kiwi aporta fibra y suele tener un impacto moderado en una racion "
        "normal"
    ),
    why="ademas de mucha vitamina C para las calorias que tiene",
    query="sliced kiwi fruit on a plate",
    search_text="sliced green kiwi fruit",
    sources=("harvard_fiber", "who_diet"),
)

MANZANA = Item(
    key="manzana",
    display="la manzana con piel",
    claim=(
        "La manzana con piel conserva la fibra, y eso puede hacer que se "
        "absorba mas despacio que en zumo"
    ),
    why="al quitar la piel o exprimirla, esa ventaja se pierde",
    query="whole red apple with skin on a wooden table",
    search_text="a whole red apple on a wooden table",
    sources=("harvard_fiber", "ada_nutrition", "fundacion_diabetes"),
)

PERA = Item(
    key="pera",
    display="la pera",
    claim=(
        "La pera tambien es una fruta con bastante fibra, y suele sentar bien "
        "en raciones medidas"
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
        "El aguacate apenas aporta carbohidratos, asi que su efecto sobre la "
        "glucosa suele ser muy pequeno"
    ),
    why="por eso funciona tan bien acompanando a otros alimentos",
    query="halved avocado on a wooden board",
    search_text="a halved fresh avocado",
    sources=("harvard_carbs", "ada_nutrition"),
)

PLATANO_MADURO = Item(
    key="platano",
    display="el platano muy maduro",
    claim=(
        "El platano muy maduro suele tener mas azucares libres que el poco "
        "maduro"
    ),
    why="cuanto mas madura la fruta, mas rapido se absorbe normalmente",
    query="ripe yellow bananas on a table",
    search_text="ripe yellow bananas",
    sources=("harvard_carbs", "diabetes_uk_food"),
)

UVAS = Item(
    key="uvas",
    display="las uvas",
    claim=(
        "Las uvas se comen de una en una y es muy facil pasarse de racion sin "
        "darse cuenta"
    ),
    why="y la cantidad es lo que mas suele pesar en la respuesta",
    query="bunch of green grapes close up",
    search_text="a bunch of fresh grapes",
    sources=("ada_nutrition", "diabetes_uk_food"),
)

DATILES = Item(
    key="datiles",
    display="los datiles",
    claim=(
        "Los datiles concentran mucho azucar en muy poco volumen, asi que una "
        "racion pequena ya cuenta bastante"
    ),
    why="al secarse se va el agua y queda el azucar concentrado",
    query="dried dates in a bowl",
    search_text="a bowl of dried dates",
    sources=("harvard_carbs", "who_diet"),
)

FRUTA_DESHIDRATADA = Item(
    key="deshidratada",
    display="la fruta deshidratada",
    claim=(
        "La fruta deshidratada concentra los azucares porque pierde el agua, "
        "y suele comerse en mas cantidad"
    ),
    why="un punado equivale a bastante mas fruta de la que parece",
    query="dried apricots and raisins in a bowl",
    search_text="a bowl of dried fruit",
    sources=("harvard_carbs", "who_diet", "fundacion_diabetes"),
)

ZUMO = Item(
    key="zumo",
    display="el zumo de naranja",
    claim=(
        "Al exprimir la naranja se pierde casi toda la fibra y el azucar pasa "
        "a estar libre en el vaso"
    ),
    why="por eso suele absorberse mas rapido que la fruta entera",
    query="glass of fresh orange juice on a table",
    search_text="a glass of orange juice",
    sources=("who_diet", "harvard_fiber", "ada_nutrition"),
)

NARANJA_ENTERA = Item(
    key="naranja",
    display="la naranja entera",
    claim=(
        "La naranja entera mantiene la fibra y ademas llena mas, asi que suele "
        "costar mas pasarse"
    ),
    why="hacen falta dos o tres naranjas para un vaso de zumo",
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
        title="5 frutas que suelen tener un impacto mas moderado en la glucosa",
        format="list",
        top_title="FRUTAS Y GLUCOSA 🍓",
        accent="GLUCOSA",
        promise=(
            "Estas son cinco opciones que suelen tener un impacto mas moderado "
            "cuando cuidamos tambien la cantidad"
        ),
        conclusion=(
            "La fruta no tiene por que desaparecer de tu dieta: el tipo, la "
            "cantidad y con que la acompanas importan mucho"
        ),
        items=_fruit_list_items(),
        hashtags=("#diabetes", "#glucosa", "#alimentacionsaludable", "#fruta",
                  "#diabetestipo2", "#saludable"),
        hooks=(
            "Si tienes diabetes, no todas las frutas afectan igual a tu glucosa.",
            "Antes de dejar la fruta por miedo al azucar, mira esto.",
            "El problema no suele ser la fruta: muchas veces es la cantidad.",
            "Estas cinco frutas suelen tener un impacto mas moderado en la glucosa.",
            "Si te cuesta elegir fruta sin complicarte, apunta estas cinco.",
            "La fruta no tiene por que desaparecer de tu dieta, y estas cinco lo demuestran.",
        ),
        opening_query="fresh fruit assortment on a kitchen table",
        opening_search_text="an assortment of fresh fruit on a table",
    ),
    Topic(
        slug="frutas-suben-mas-rapido",
        title="5 frutas que pueden subir la glucosa mas rapidamente",
        format="list",
        top_title="CUIDADO CON ESTAS FRUTAS ⚠️",
        accent="CUIDADO",
        promise=(
            "No hay que eliminarlas, pero conviene medir la racion y saber con "
            "que las acompanas"
        ),
        conclusion=(
            "Ninguna de estas frutas esta descartada: cambia mucho la racion, "
            "la madurez y con que la comes"
        ),
        items=(PLATANO_MADURO, UVAS, DATILES, FRUTA_DESHIDRATADA, ZUMO),
        hashtags=("#diabetes", "#glucosa", "#fruta", "#nutricion",
                  "#diabetestipo2"),
        hooks=(
            "Estas frutas parecen saludables, pero algunas pueden subir tu glucosa mas rapido.",
            "No hace falta eliminarlas: con estas cinco, lo que cambia todo es la racion.",
            "Si sueles picar fruta sin mirar la cantidad, presta atencion a estas cinco.",
            "Cinco frutas que conviene medir un poco mas que el resto.",
            "La madurez y la racion cambian mucho como te sienta la fruta.",
        ),
        opening_query="ripe fruit bowl on a kitchen counter",
        opening_search_text="a bowl of ripe fruit on a counter",
    ),
    Topic(
        slug="errores-comer-fruta",
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
        items=(
            Item(
                key="fruta_sola",
                display="comerla sola con mucha hambre",
                claim=(
                    "Comer fruta sola y con mucha hambre puede hacer que la "
                    "subida sea mas marcada"
                ),
                why=(
                    "prueba a acompanarla con algo de proteina o grasa, como "
                    "un yogur natural o unas nueces"
                ),
                query="yogurt with nuts and berries in a bowl",
                search_text="a bowl of yogurt with nuts and berries",
                sources=("ada_nutrition", "harvard_carbs"),
            ),
            Item(
                key="zumo_por_fruta",
                display="cambiar la fruta por zumo",
                claim=(
                    "Sustituir la fruta entera por zumo suele quitarle la "
                    "fibra y dejar el azucar libre"
                ),
                why="la fruta entera es casi siempre la mejor version",
                query="glass of orange juice next to whole oranges",
                search_text="a glass of juice beside whole oranges",
                sources=("who_diet", "harvard_fiber"),
            ),
            Item(
                key="sin_medir",
                display="no mirar nunca la racion",
                claim=(
                    "Comer directamente del bol sin medir hace que la racion "
                    "se dispare sin darte cuenta"
                ),
                why="servir en un plato pequeno ya cambia bastante la cantidad",
                query="small plate of cut fruit portion",
                search_text="a small plate with a portion of cut fruit",
                sources=("ada_nutrition", "fundacion_diabetes"),
            ),
            Item(
                key="quitar_piel",
                display="quitarle siempre la piel",
                claim=(
                    "Quitar la piel a frutas como la manzana o la pera elimina "
                    "buena parte de su fibra"
                ),
                why="y la fibra es justo lo que suele suavizar la respuesta",
                query="apple with skin sliced on a board",
                search_text="a sliced apple with its skin on a board",
                sources=("harvard_fiber",),
            ),
            Item(
                key="deshidratada_punado",
                display="los punados de fruta seca",
                claim=(
                    "Un punado de fruta deshidratada puede equivaler a mucha "
                    "mas fruta fresca de la que crees"
                ),
                why="al perder el agua, el azucar queda concentrado",
                query="handful of raisins and dried fruit",
                search_text="a handful of dried fruit",
                sources=("harvard_carbs", "who_diet"),
            ),
        ),
        hashtags=("#diabetes", "#glucosa", "#errores", "#fruta", "#nutricion"),
        hooks=(
            "El problema no siempre es la fruta. Muchas veces es como te la comes.",
            "Si tu glucosa sube mas de lo que esperas despues de la fruta, mira estos cinco fallos.",
            "Cinco errores con la fruta que se cometen casi sin darse cuenta.",
            "Comes fruta a diario y quiza estas repitiendo alguno de estos cinco fallos.",
            "Aqui es donde mucha gente se equivoca al comer fruta.",
        ),
    ),
    Topic(
        slug="desayunos-picos",
        title="5 desayunos que pueden provocar picos de glucosa",
        format="list",
        top_title="DESAYUNOS Y GLUCOSA",
        accent="GLUCOSA",
        promise=(
            "Cinco desayunos muy habituales que suelen dar una subida mas "
            "marcada, y por que"
        ),
        conclusion=(
            "Un desayuno con proteina, grasa buena y fibra suele sostener mucho "
            "mejor la manana"
        ),
        items=(
            Item(
                key="cereales_azucarados",
                display="los cereales azucarados",
                claim=(
                    "Muchos cereales de desayuno llevan azucar anadido y poca "
                    "fibra, y suelen absorberse rapido"
                ),
                why="mira la etiqueta: azucares por cien gramos y fibra",
                query="bowl of breakfast cereal with milk",
                search_text="a bowl of breakfast cereal with milk",
                sources=("who_diet", "harvard_carbs"),
            ),
            Item(
                key="bolleria",
                display="la bolleria",
                claim=(
                    "La bolleria combina harina refinada, azucar y grasa, y "
                    "suele dar una subida bastante rapida"
                ),
                why="ademas sacia poco, asi que se vuelve a tener hambre pronto",
                query="croissants and pastries on a plate",
                search_text="pastries and croissants on a plate",
                sources=("who_diet", "harvard_carbs"),
            ),
            Item(
                key="zumo_desayuno",
                display="el zumo de la manana",
                claim=(
                    "El zumo aporta el azucar de varias piezas de fruta sin su "
                    "fibra, y suele absorberse rapido"
                ),
                why="la fruta entera hace mejor ese trabajo",
                query="glass of orange juice at breakfast table",
                search_text="a glass of orange juice on a breakfast table",
                sources=("who_diet", "harvard_fiber"),
            ),
            Item(
                key="pan_blanco_mermelada",
                display="la tostada de pan blanco con mermelada",
                claim=(
                    "Pan blanco con mermelada son casi solo carbohidratos de "
                    "absorcion rapida"
                ),
                why=(
                    "con pan integral y algo de proteina encima, la cosa suele "
                    "cambiar"
                ),
                query="white bread toast with jam on a plate",
                search_text="toast with jam on a plate",
                sources=("harvard_carbs", "diabetes_uk_food"),
            ),
            Item(
                key="yogur_sabores",
                display="los yogures de sabores",
                claim=(
                    "Los yogures de sabores suelen llevar azucar anadido, a "
                    "veces bastante"
                ),
                why="el yogur natural con fruta fresca hace lo mismo sin ese extra",
                query="flavoured yogurt cups on a table",
                search_text="cups of flavoured yogurt",
                sources=("who_diet", "ada_nutrition"),
            ),
        ),
        hashtags=("#diabetes", "#desayuno", "#glucosa", "#nutricion"),
        hooks=(
            "Si tu glucosa sube mucho despues del desayuno, puede que estes tomando uno de estos cinco.",
            "Este desayuno parece saludable, pero puede no ser la mejor opcion para tu glucosa.",
            "Cinco desayunos muy habituales que suelen dar una subida bastante marcada.",
            "Si desayunas siempre lo mismo, comprueba que no sea ninguno de estos cinco.",
            "Parecen desayunos ligeros y suelen comportarse justo al reves.",
        ),
        opening_query="breakfast table with coffee and toast",
        opening_search_text="a breakfast table with coffee and toast",
    ),
    Topic(
        slug="desayunos-equilibrados",
        title="5 desayunos mas equilibrados para personas con diabetes",
        format="list",
        top_title="DESAYUNOS MAS EQUILIBRADOS",
        accent="EQUILIBRADOS",
        promise=(
            "Cinco desayunos sencillos que suelen sostener mejor la manana, sin "
            "complicarse"
        ),
        conclusion=(
            "La formula que suele funcionar es sencilla: proteina, grasa buena "
            "y fibra en el mismo plato"
        ),
        items=(
            Item(
                key="yogur_nueces",
                display="yogur natural con nueces y fresas",
                claim=(
                    "El yogur natural con nueces y fresas junta proteina, grasa "
                    "y fibra en un solo bol"
                ),
                why="esa combinacion suele suavizar la respuesta glucemica",
                query="greek yogurt with walnuts and strawberries bowl",
                search_text="a bowl of yogurt with nuts and strawberries",
                sources=("ada_nutrition", "harvard_fiber"),
            ),
            Item(
                key="tostada_aguacate",
                display="tostada integral con aguacate y huevo",
                claim=(
                    "El pan integral con aguacate y huevo aporta fibra, grasa y "
                    "proteina a la vez"
                ),
                why="y suele saciar bastante mas que la tostada sola",
                query="avocado toast with egg on a plate",
                search_text="avocado toast topped with an egg",
                sources=("ada_nutrition", "harvard_fiber"),
            ),
            Item(
                key="avena",
                display="avena con canela y frutos rojos",
                claim=(
                    "La avena en copos aporta fibra soluble y suele absorberse "
                    "mas despacio que los cereales refinados"
                ),
                why="mejor en copos que instantanea y sin azucar anadido",
                query="oatmeal bowl with berries and cinnamon",
                search_text="a bowl of oatmeal with berries",
                sources=("harvard_fiber", "harvard_carbs"),
            ),
            Item(
                key="huevos_verduras",
                display="huevos revueltos con verduras",
                claim=(
                    "Unos huevos con verduras aportan muy pocos carbohidratos y "
                    "bastante saciedad"
                ),
                why="suele ser de los desayunos con menos impacto sobre la glucosa",
                query="scrambled eggs with vegetables on a plate",
                search_text="scrambled eggs with vegetables",
                sources=("ada_nutrition", "harvard_carbs"),
            ),
            Item(
                key="requeson_kiwi",
                display="requeson con kiwi",
                claim=(
                    "El requeson aporta proteina y, con un kiwi, sumas fibra sin "
                    "mucha carga de carbohidratos"
                ),
                why="una opcion rapida cuando hay poco tiempo",
                query="cottage cheese with kiwi in a bowl",
                search_text="a bowl of cottage cheese with fruit",
                sources=("ada_nutrition",),
            ),
        ),
        hashtags=("#diabetes", "#desayuno", "#glucosa", "#recetassaludables"),
        hooks=(
            "Si a media manana ya tienes hambre otra vez, prueba con uno de estos cinco desayunos.",
            "Cinco desayunos sencillos que suelen sostener mucho mejor la manana.",
            "Cambiar el desayuno es de los ajustes que mas se notan durante el dia.",
            "Estos cinco desayunos se preparan en minutos y suelen sentar mejor.",
            "No hace falta complicarse: proteina, grasa buena y fibra en el mismo plato.",
        ),
        opening_query="healthy breakfast bowl on a table",
        opening_search_text="a healthy breakfast on a table",
    ),
    Topic(
        slug="snacks-carbohidratos",
        title="5 snacks sencillos para controlar mejor los carbohidratos",
        format="list",
        top_title="SNACKS SIN PICOS",
        accent="SNACKS",
        promise=(
            "Cinco ideas rapidas para cuando entra hambre entre horas, sin "
            "complicarse"
        ),
        conclusion=(
            "Un snack con proteina o grasa suele sostener mucho mejor que uno "
            "solo de carbohidratos"
        ),
        items=(
            Item(
                key="nueces",
                display="un punado de nueces",
                claim=(
                    "Las nueces aportan grasa y fibra con muy pocos "
                    "carbohidratos disponibles"
                ),
                why="un punado pequeno basta, porque son muy densas",
                query="handful of walnuts in a bowl",
                search_text="a small bowl of walnuts",
                sources=("ada_nutrition", "harvard_fiber"),
            ),
            Item(
                key="yogur_natural",
                display="yogur natural sin azucar",
                claim=(
                    "El yogur natural sin azucar anadido aporta proteina y "
                    "suele saciar bien"
                ),
                why="si te sabe soso, mejor anadir fruta que azucar",
                query="plain natural yogurt in a bowl",
                search_text="a bowl of plain white yogurt",
                sources=("ada_nutrition", "who_diet"),
            ),
            Item(
                key="hummus_zanahoria",
                display="hummus con zanahoria",
                claim=(
                    "El hummus con verdura cruda suma fibra y proteina vegetal "
                    "en una racion pequena"
                ),
                why="y se prepara en un minuto",
                query="hummus with carrot sticks on a plate",
                search_text="hummus with carrot sticks",
                sources=("harvard_fiber", "ada_nutrition"),
            ),
            Item(
                key="huevo_duro",
                display="un huevo duro",
                claim=(
                    "Un huevo duro apenas aporta carbohidratos y suele quitar "
                    "el hambre bastante bien"
                ),
                why="facil de llevar y de tener preparado",
                query="boiled eggs cut in half on a plate",
                search_text="boiled eggs on a plate",
                sources=("ada_nutrition",),
            ),
            Item(
                key="manzana_crema",
                display="manzana con crema de cacahuete",
                claim=(
                    "Anadir una cucharada de crema de cacahuete a la manzana "
                    "suma grasa y proteina a la fruta"
                ),
                why="que sea crema de cacahuete sin azucar anadido",
                query="apple slices with peanut butter on a plate",
                search_text="apple slices with peanut butter",
                sources=("ada_nutrition", "harvard_carbs"),
            ),
        ),
        hashtags=("#diabetes", "#snacks", "#glucosa", "#meriendasaludable"),
        hooks=(
            "Si entre horas siempre acabas picando lo primero que pillas, apunta estos cinco.",
            "Cinco snacks que se preparan en un minuto y suelen sostener de verdad.",
            "El picoteo no es el problema: lo que picas si marca la diferencia.",
            "Estos cinco snacks aportan proteina o grasa, y eso se nota en la saciedad.",
            "Tener dos de estos preparados evita muchas decisiones malas a media tarde.",
        ),
        opening_query="healthy snack plate on a table",
        opening_search_text="a plate of healthy snacks",
    ),
    Topic(
        slug="combinar-fruta",
        title="Como combinar la fruta para moderar la respuesta glucemica",
        format="combination",
        top_title="COMBINA ASI TU FRUTA 🍏",
        accent="COMBINA",
        promise=(
            "Cuatro combinaciones sencillas que suelen moderar la subida sin "
            "quitar la fruta"
        ),
        conclusion=(
            "La fruta sola no es un error, pero acompanarla suele hacer que la "
            "curva sea mas suave"
        ),
        items=(
            Item(
                key="fruta_proteina",
                display="fruta con proteina",
                claim=(
                    "Anadir proteina, como yogur natural o requeson, suele "
                    "hacer la digestion mas lenta"
                ),
                why="y una digestion mas lenta suele significar una subida mas suave",
                query="yogurt bowl with fresh fruit",
                search_text="a bowl of yogurt with fresh fruit",
                sources=("ada_nutrition", "harvard_carbs"),
            ),
            Item(
                key="fruta_grasa",
                display="fruta con grasa buena",
                claim=(
                    "Un punado de frutos secos junto a la fruta anade grasa y "
                    "suele moderar la respuesta"
                ),
                why="con un punado pequeno es suficiente",
                query="almonds and fruit on a wooden board",
                search_text="almonds beside fresh fruit",
                sources=("ada_nutrition", "harvard_fiber"),
            ),
            Item(
                key="fruta_entera",
                display="la fruta entera antes que en zumo",
                claim=(
                    "Mantener la fruta entera conserva la fibra, que es parte "
                    "de lo que suaviza la absorcion"
                ),
                why="masticar tambien ayuda a saciarse antes",
                query="whole apples and pears on a table",
                search_text="whole fruit on a table",
                sources=("harvard_fiber", "who_diet"),
            ),
            Item(
                key="fruta_postre",
                display="la fruta despues de comer",
                claim=(
                    "Tomarla despues de una comida completa suele dar una "
                    "subida menor que tomarla sola en ayunas"
                ),
                why="porque el resto del plato ya esta ralentizando la digestion",
                query="plate of fruit after a meal on a table",
                search_text="a plate of fruit on a dining table",
                sources=("ada_nutrition", "diabetes_uk_food"),
            ),
        ),
        hashtags=("#diabetes", "#glucosa", "#fruta", "#nutricion"),
        hooks=(
            "Si comes fruta sola cuando tienes mucha hambre, presta atencion a esto.",
            "No tomes solo la manzana: prueba a combinarla asi.",
            "Con la fruta, lo que la acompana cambia bastante el resultado.",
            "Cuatro combinaciones sencillas para tomar fruta sin renunciar a ella.",
            "La fruta sola y la fruta acompanada no suelen comportarse igual.",
        ),
    ),
    Topic(
        slug="naranja-vs-zumo",
        title="Naranja entera o zumo de naranja: que cambia para tu glucosa",
        format="comparison",
        top_title="NARANJA VS ZUMO 🍊",
        accent="VS",
        promise=(
            "La diferencia practica entre las dos, y cuando conviene cada una"
        ),
        conclusion=(
            "La naranja entera suele ser la mejor opcion del dia a dia; el zumo, "
            "algo puntual y en vaso pequeno"
        ),
        items=(NARANJA_ENTERA, ZUMO),
        hashtags=("#diabetes", "#glucosa", "#zumo", "#fruta", "#nutricion"),
        hooks=(
            "Naranja entera o zumo de naranja: parecen lo mismo y no lo son.",
            "Un vaso de zumo lleva el azucar de varias naranjas y casi nada de su fibra.",
            "Si desayunas zumo cada manana, esta diferencia te interesa.",
            "La misma fruta, dos formas de tomarla y dos respuestas distintas.",
            "Antes de exprimir la naranja de manana, mira esto.",
        ),
        opening_query="oranges and a glass of juice side by side",
        opening_search_text="oranges next to a glass of orange juice",
    ),
    Topic(
        slug="fruta-deshidratada",
        title="Que ocurre cuando comemos fruta deshidratada",
        format="error_solution",
        top_title="FRUTA SECA: OJO A ESTO",
        accent="OJO",
        promise=(
            "Que cambia al secar la fruta y como seguir tomandola sin sustos"
        ),
        conclusion=(
            "La fruta deshidratada no esta descartada: cambia mucho si mides la "
            "racion y la acompanas"
        ),
        items=(
            FRUTA_DESHIDRATADA,
            DATILES,
            Item(
                key="racion_seca",
                display="la racion de referencia",
                claim=(
                    "Una racion suele ser bastante pequena, del orden de un "
                    "punado corto"
                ),
                why="servirla en un platito en vez de comer de la bolsa ayuda mucho",
                query="small bowl of dried fruit portion",
                search_text="a small bowl with a portion of dried fruit",
                sources=("ada_nutrition", "fundacion_diabetes"),
            ),
            Item(
                key="seca_con_nueces",
                display="acompanarla",
                claim=(
                    "Combinarla con frutos secos o yogur suele suavizar la "
                    "respuesta frente a tomarla sola"
                ),
                why="la grasa y la proteina ralentizan la digestion",
                query="dried fruit and nuts mixed in a bowl",
                search_text="a bowl of mixed nuts and dried fruit",
                sources=("ada_nutrition", "harvard_carbs"),
            ),
        ),
        hashtags=("#diabetes", "#glucosa", "#frutosecos", "#nutricion"),
        hooks=(
            "Un punado de pasas y un punado de uvas no son lo mismo, ni de lejos.",
            "Si picas fruta deshidratada entre horas, esto te va a interesar.",
            "Al secar la fruta se va el agua y queda el azucar concentrado.",
            "La fruta seca no esta descartada, pero la racion aqui cuenta el doble.",
            "Parece fruta y se comporta de otra manera.",
        ),
    ),
    Topic(
        slug="cereales-desayuno",
        title="Errores comunes con los cereales del desayuno",
        format="error_solution",
        top_title="CEREALES: 4 ERRORES",
        accent="ERRORES",
        promise=(
            "Cuatro cosas que suelen pasarse por alto en el pasillo de los "
            "cereales"
        ),
        conclusion=(
            "Con mirar dos numeros en la etiqueta, azucares y fibra, ya se "
            "decide mucho mejor"
        ),
        items=(
            Item(
                key="etiqueta_azucares",
                display="no mirar los azucares",
                claim=(
                    "Muchos cereales llevan bastante azucar anadido aunque el "
                    "envase parezca saludable"
                ),
                why="mira los azucares por cien gramos, no solo la imagen",
                query="breakfast cereal nutrition label close up",
                search_text="a cereal box nutrition label",
                sources=("who_diet",),
            ),
            Item(
                key="poca_fibra",
                display="ignorar la fibra",
                claim=(
                    "Un cereal con poca fibra suele absorberse mas rapido que "
                    "uno integral"
                ),
                why="a partir de unos seis gramos de fibra por cien ya es otra cosa",
                query="whole grain cereal in a bowl",
                search_text="a bowl of whole grain cereal",
                sources=("harvard_fiber",),
            ),
            Item(
                key="racion_cereal",
                display="servir a ojo",
                claim=(
                    "La racion real suele ser mucho menor que el bol que "
                    "solemos llenar"
                ),
                why="pesarlo una vez cambia la referencia para siempre",
                query="measuring a small bowl of cereal",
                search_text="a small bowl of cereal being served",
                sources=("ada_nutrition", "fundacion_diabetes"),
            ),
            Item(
                key="cereal_solo",
                display="tomarlo solo",
                claim=(
                    "Tomarlo solo, sin proteina ni grasa, suele dar una subida "
                    "mas marcada"
                ),
                why="con yogur natural o un punado de nueces la cosa cambia",
                query="cereal bowl with yogurt and nuts",
                search_text="a bowl of cereal with yogurt and nuts",
                sources=("ada_nutrition", "harvard_carbs"),
            ),
        ),
        hashtags=("#diabetes", "#desayuno", "#cereales", "#etiquetas"),
        hooks=(
            "El envase dice saludable y la etiqueta suele contar otra cosa.",
            "Si desayunas cereales casi a diario, revisa estos cuatro detalles.",
            "Cuatro errores con los cereales del desayuno que se repiten mucho.",
            "Con mirar dos numeros de la etiqueta ya eliges bastante mejor.",
            "El cereal integral y el que solo lo parece no se comportan igual.",
        ),
    ),
    Topic(
        slug="yogur-natural-vs-azucarado",
        title="Yogur natural o yogur azucarado: que cambia de verdad",
        format="comparison",
        top_title="YOGUR: NATURAL VS AZUCARADO",
        accent="VS",
        promise="La diferencia real entre los dos, en la etiqueta y en el plato",
        conclusion=(
            "El yogur natural con fruta fresca da el mismo gusto sin el azucar "
            "anadido del de sabores"
        ),
        items=(
            Item(
                key="yogur_nat",
                display="el yogur natural",
                claim=(
                    "El yogur natural aporta proteina y solo el azucar propio "
                    "de la leche"
                ),
                why="sin azucares anadidos en la lista de ingredientes",
                query="plain yogurt in a glass bowl",
                search_text="a bowl of plain yogurt",
                sources=("ada_nutrition", "who_diet"),
            ),
            Item(
                key="yogur_azucarado",
                display="el yogur de sabores",
                claim=(
                    "Los de sabores suelen sumar varios gramos de azucar "
                    "anadido por unidad"
                ),
                why="aparece en la etiqueta como azucar, jarabe o sirope",
                query="flavoured fruit yogurt pots",
                search_text="pots of flavoured yogurt",
                sources=("who_diet",),
            ),
        ),
        hashtags=("#diabetes", "#yogur", "#azucar", "#etiquetas"),
        hooks=(
            "Yogur natural o yogur de sabores: la diferencia esta en la etiqueta.",
            "Si compras yogures de sabores pensando que son iguales, mira esto.",
            "El mismo tarro, dos versiones y una diferencia clara de azucar anadido.",
            "Anadir fruta al yogur natural sale mejor que comprarlo ya endulzado.",
            "Dice yogur en la tapa, y la lista de ingredientes cuenta el resto.",
        ),
    ),
    Topic(
        slug="azucar-oculto",
        title="Alimentos que parecen saludables y llevan bastante azucar anadido",
        format="list",
        top_title="AZUCAR DONDE NO LO ESPERAS",
        accent="AZUCAR",
        promise=(
            "Cinco productos del carro de la compra que suelen sorprender al "
            "leer la etiqueta"
        ),
        conclusion=(
            "Leer la linea de azucares en la etiqueta es el habito que mas "
            "cambia la compra"
        ),
        items=(
            Item(
                key="granola",
                display="la granola",
                claim=(
                    "La granola suele llevar miel o sirope para quedar "
                    "crujiente, y eso es azucar anadido"
                ),
                why="la avena en copos sola no lleva nada de eso",
                query="granola in a bowl with milk",
                search_text="a bowl of granola",
                sources=("who_diet",),
            ),
            Item(
                key="barritas",
                display="las barritas de cereales",
                claim=(
                    "Muchas barritas llevan tanto azucar anadido como una "
                    "galleta"
                ),
                why="la lista de ingredientes lo dice en las tres primeras lineas",
                query="cereal bars on a table",
                search_text="cereal bars on a table",
                sources=("who_diet",),
            ),
            Item(
                key="salsas",
                display="las salsas preparadas",
                claim=(
                    "Salsas como el ketchup o las de tomate preparadas suelen "
                    "llevar azucar anadido"
                ),
                why="poca cantidad, pero se usan todos los dias",
                query="ketchup and sauce bottles on a table",
                search_text="bottles of sauce on a table",
                sources=("who_diet",),
            ),
            Item(
                key="zumos_envasados",
                display="los zumos envasados",
                claim=(
                    "Aunque digan sin azucares anadidos, el azucar de la fruta "
                    "sigue estando libre en el vaso"
                ),
                why="sin la fibra que lo acompanaba en la pieza entera",
                query="packaged fruit juice cartons",
                search_text="cartons of fruit juice",
                sources=("who_diet", "harvard_fiber"),
            ),
            Item(
                key="lacteos_sabor",
                display="los lacteos de sabores",
                claim=(
                    "Batidos y postres lacteos de sabores suelen sumar azucar "
                    "anadido por racion"
                ),
                why="la version natural cuesta lo mismo y no lo lleva",
                query="flavoured milk drinks on a shelf",
                search_text="flavoured milk drinks",
                sources=("who_diet",),
            ),
        ),
        hashtags=("#diabetes", "#azucar", "#etiquetas", "#compra", "#glucosa"),
        hooks=(
            "Estos cinco productos parecen saludables y suelen llevar bastante azucar anadido.",
            "Si compras alguno de estos cada semana, merece la pena leer la etiqueta.",
            "El azucar anadido aparece donde menos te lo esperas.",
            "Cinco habituales del carro de la compra que sorprenden al leerlos.",
            "No hace falta eliminarlos, pero si saber lo que llevan.",
        ),
        opening_query="supermarket shelf with packaged food",
        opening_search_text="packaged food on a supermarket shelf",
    ),
    Topic(
        slug="tamano-racion",
        title="Como influye el tamano de la racion en la glucosa",
        format="list",
        top_title="LA RACION LO CAMBIA TODO",
        accent="RACION",
        promise=(
            "Cuatro ideas practicas para que la cantidad deje de ser una "
            "loteria"
        ),
        conclusion=(
            "El mismo alimento puede sentar de formas muy distintas solo por la "
            "cantidad que te sirves"
        ),
        items=(
            Item(
                key="mismo_alimento",
                display="el mismo alimento, distinta cantidad",
                claim=(
                    "Un mismo alimento puede dar respuestas muy distintas segun "
                    "la cantidad que se tome"
                ),
                why="por eso hablar de alimentos buenos o malos se queda corto",
                query="two plates with different portion sizes",
                search_text="two plates with different portion sizes",
                sources=("ada_nutrition", "harvard_carbs"),
            ),
            Item(
                key="plato_pequeno",
                display="el plato pequeno",
                claim=(
                    "Servir en un plato mas pequeno suele reducir la racion sin "
                    "esfuerzo"
                ),
                why="y sin sensacion de estar renunciando a nada",
                query="small plate with a served meal",
                search_text="a small plate with a served meal",
                sources=("diabetes_uk_food",),
            ),
            Item(
                key="pesar_una_vez",
                display="pesarlo una sola vez",
                claim=(
                    "Pesar una vez la racion habitual suele cambiar la "
                    "referencia para siempre"
                ),
                why="despues ya se calcula a ojo con bastante acierto",
                query="kitchen scale weighing food",
                search_text="food being weighed on a kitchen scale",
                sources=("fundacion_diabetes", "ada_nutrition"),
            ),
            Item(
                key="del_paquete_no",
                display="no comer del paquete",
                claim=(
                    "Comer directamente del paquete suele acabar en una racion "
                    "mucho mayor de la prevista"
                ),
                why="servir antes en un bol pone un limite visible",
                query="bowl of snacks served from a package",
                search_text="a bowl of snacks on a table",
                sources=("diabetes_uk_food",),
            ),
        ),
        hashtags=("#diabetes", "#raciones", "#glucosa", "#habitos"),
        hooks=(
            "Muchas veces no es el alimento: es cuanto te sirves.",
            "El mismo plato puede sentar de dos formas muy distintas solo por la cantidad.",
            "Cuatro ideas para que la racion deje de ser una loteria.",
            "Si nunca has pesado tu racion habitual, esto te va a sorprender un poco.",
            "Servir en un plato mas pequeno ya cambia bastante la cantidad.",
        ),
    ),
    Topic(
        slug="carbohidratos-y-fibra",
        title="Carbohidratos y fibra explicados de forma sencilla",
        format="list",
        top_title="CARBOHIDRATOS Y FIBRA",
        accent="FIBRA",
        promise="Cuatro ideas basicas para leer cualquier etiqueta con criterio",
        conclusion=(
            "Con entender carbohidratos y fibra ya se decide mucho mejor en el "
            "supermercado"
        ),
        items=(
            Item(
                key="que_son_carbos",
                display="que son los carbohidratos",
                claim=(
                    "Los carbohidratos son, en general, el nutriente que mas "
                    "influye en la glucosa despues de comer"
                ),
                why="estan en cereales, fruta, legumbres, leche y azucares",
                query="bread pasta rice and legumes on a table",
                search_text="bread, pasta and rice on a table",
                sources=("harvard_carbs", "ada_nutrition"),
            ),
            Item(
                key="fibra_no_sube",
                display="la fibra",
                claim=(
                    "La fibra es un carbohidrato que apenas se absorbe, y suele "
                    "ralentizar la digestion del resto"
                ),
                why="por eso los alimentos integrales suelen comportarse distinto",
                query="whole grain bread and vegetables",
                search_text="whole grain bread and vegetables",
                sources=("harvard_fiber",),
            ),
            Item(
                key="etiqueta",
                display="como leer la etiqueta",
                claim=(
                    "En la etiqueta interesa mirar carbohidratos totales, de "
                    "los cuales azucares, y fibra"
                ),
                why="esas tres lineas dan casi toda la informacion util",
                query="nutrition facts label close up",
                search_text="a nutrition facts label",
                sources=("who_diet", "ada_nutrition"),
            ),
            Item(
                key="integral",
                display="integral de verdad",
                claim=(
                    "Que ponga integral en el envase no siempre significa que "
                    "la harina lo sea"
                ),
                why="en los ingredientes debe aparecer harina integral la primera",
                query="whole grain bread loaf on a board",
                search_text="a loaf of whole grain bread",
                sources=("who_diet", "harvard_fiber"),
            ),
        ),
        hashtags=("#diabetes", "#carbohidratos", "#fibra", "#etiquetas"),
        hooks=(
            "Con entender dos conceptos, carbohidratos y fibra, lees cualquier etiqueta.",
            "Si las etiquetas te suenan a chino, empieza por estas cuatro ideas.",
            "Carbohidratos y fibra explicados sin tecnicismos y en cuatro pasos.",
            "Saber que mirar en una etiqueta cambia la compra entera.",
            "No todos los carbohidratos se comportan igual, y la fibra es la clave.",
        ),
    ),
    Topic(
        slug="respuesta-individual",
        title="Por que dos personas pueden responder distinto al mismo alimento",
        format="myth",
        top_title="CADA PERSONA ES DISTINTA",
        accent="DISTINTA",
        promise=(
            "Por que las listas generales son solo un punto de partida y que "
            "hacer con eso"
        ),
        conclusion=(
            "Las listas orientan, pero tu propia experiencia y tu equipo "
            "sanitario mandan sobre cualquier lista"
        ),
        items=(
            Item(
                key="variabilidad",
                display="la variabilidad entre personas",
                claim=(
                    "La respuesta a un mismo alimento puede variar bastante de "
                    "una persona a otra"
                ),
                why="influyen el tratamiento, la actividad y muchos otros factores",
                query="two people eating a meal at a table",
                search_text="two people sharing a meal at a table",
                sources=("ada_nutrition", "who_diabetes"),
            ),
            Item(
                key="contexto",
                display="el contexto de la comida",
                claim=(
                    "El mismo alimento puede comportarse distinto segun con que "
                    "se combine y a que hora se tome"
                ),
                why="no es lo mismo solo, en ayunas, que dentro de una comida",
                query="balanced meal plate with vegetables and protein",
                search_text="a balanced plate of food",
                sources=("ada_nutrition", "harvard_carbs"),
            ),
            Item(
                key="medir",
                display="comprobarlo en tu caso",
                claim=(
                    "Comprobar como te sienta a ti un alimento concreto suele "
                    "ser mas util que cualquier lista general"
                ),
                why="siempre dentro de lo que te haya indicado tu equipo sanitario",
                query="person using a glucose meter at home",
                search_text="a glucose meter on a table",
                sources=("who_diabetes", "redgdps"),
            ),
        ),
        hashtags=("#diabetes", "#glucosa", "#educaciondiabetologica"),
        hooks=(
            "El mismo alimento puede sentarte a ti de una forma y a otra persona de otra.",
            "Si una lista general no te cuadra con lo que ves, hay una explicacion.",
            "Dos personas, el mismo desayuno y dos respuestas distintas.",
            "Las listas orientan, pero tu caso concreto manda sobre cualquier lista.",
            "Por que lo que le funciona a otra persona quiza no te funcione a ti.",
        ),
        opening_query="two people having breakfast together",
        opening_search_text="two people at a breakfast table",
    ),
    Topic(
        slug="mito-dejar-fruta",
        title="Hay que dejar de comer fruta si tienes diabetes",
        format="myth",
        top_title="MITO: DEJAR LA FRUTA",
        accent="MITO",
        promise="Que dicen las guias y que se puede hacer en la practica",
        conclusion=(
            "La fruta cabe en la alimentacion de la mayoria de personas con "
            "diabetes: manda la cantidad, la forma y el conjunto del dia"
        ),
        items=(
            Item(
                key="mito_respuesta",
                display="la respuesta corta",
                claim=(
                    "Las guias de alimentacion en diabetes suelen incluir la "
                    "fruta dentro de una dieta equilibrada"
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
                    "Lo que suele cambiar la respuesta es la cantidad, la forma "
                    "y con que se acompana"
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
                    "Cada persona puede responder distinto, y el tratamiento "
                    "tambien influye"
                ),
                why="tu equipo sanitario es quien ajusta eso contigo",
                query="doctor talking with a patient at a desk",
                search_text="a healthcare professional talking with a person",
                sources=("who_diabetes", "redgdps"),
            ),
        ),
        hashtags=("#diabetes", "#mitos", "#fruta", "#glucosa"),
        hooks=(
            "Antes de dejar la fruta por miedo al azucar, mira lo que dicen las guias.",
            "Se repite mucho que hay que renunciar a la fruta, y no es exactamente asi.",
            "Si te han dicho que con diabetes no se puede comer fruta, esto te interesa.",
            "La fruta suele caber en la alimentacion de la mayoria de personas con diabetes.",
            "Lo que suele decirse sobre la fruta no cuenta toda la historia.",
        ),
    ),
    Topic(
        slug="ranking-frutas",
        title="5 frutas ordenadas de menor a mayor impacto aproximado",
        format="ranking",
        top_title="DE MENOR A MAYOR IMPACTO",
        accent="IMPACTO",
        promise=(
            "Un orden orientativo por racion habitual, que cambia segun la "
            "cantidad y la madurez"
        ),
        conclusion=(
            "Es un orden aproximado, no una regla: la racion y la madurez "
            "pueden cambiarlo por completo"
        ),
        items=(AGUACATE, FRESAS, FRAMBUESAS, MANZANA, PLATANO_MADURO),
        hashtags=("#diabetes", "#fruta", "#glucosa", "#nutricion"),
        hooks=(
            "Cinco frutas ordenadas de menor a mayor impacto aproximado.",
            "Un orden orientativo, no una regla: la racion puede cambiarlo entero.",
            "Si quieres una referencia rapida para elegir fruta, este orden ayuda.",
            "De la mas suave a la mas fuerte, con la racion habitual como referencia.",
            "No todas las frutas estan al mismo nivel, y este es el orden aproximado.",
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
