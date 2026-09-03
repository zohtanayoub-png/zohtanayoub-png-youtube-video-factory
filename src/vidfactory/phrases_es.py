"""Repertorio de frases en español para el motor de guion.

No es una traducción del módulo inglés. Está escrito en español pensando en
cómo habla alguien que explica interiorismo en YouTube: frases de longitud
desigual, alguna pregunta, alguna concesión, y ninguna estructura que se repita
lo bastante como para que el espectador la anticipe.

Los grupos son los mismos que en :mod:`vidfactory.script_generator` porque el
motor elige el repertorio por idioma y no cambia nada más.
"""

from __future__ import annotations

PROMISE_HOOKS: dict[str, list[str]] = {
    "bigger": [
        "Si tu {room} parece más pequeño de lo que realmente es, puede que el problema no sean los metros cuadrados. Hay decisiones de decoración muy normales que cierran visualmente un espacio, y deshacerlas hace que exactamente la misma habitación se sienta mucho más amplia.",
        "Dos habitaciones pueden medir lo mismo y sentirse completamente distintas al entrar. La que parece más grande casi nunca es la que tiene menos muebles, y eso sorprende a casi todo el mundo.",
        "Existe una versión de tu {room} que se siente bastante más grande, y para llegar a ella no hace falta tirar ni un tabique. Hace falta deshacer media docena de decisiones que te están costando espacio sin que te des cuenta.",
        "La mayoría de las habitaciones pequeñas no van cortas de metros. Van cortas de líneas de visión, de luz y de altura aprovechada, y las tres cosas se arreglan en un fin de semana.",
        "Hay una diferencia enorme entre lo que mide una habitación y lo que parece que mide. Lo segundo depende de unas pocas decisiones, y todas están a tu alcance esta semana.",
    ],
    "expensive": [
        "Las casas que parecen caras rara vez son casas caras. Entra en cualquier vivienda que se sienta de gama alta y encontrarás las mismas decisiones pequeñas repetidas, y casi ninguna tiene que ver con el precio.",
        "Hay razones muy concretas por las que una habitación se lee como barata, y casi nunca son los muebles. Es una lista corta de detalles que cuestan poco de arreglar y que ya no puedes dejar de ver.",
        "Puedes gastarte veinte mil euros en un salón y que quede del montón, o gastarte una fracción de eso y que parezca pensado. La diferencia está en cosas en las que casi nadie repara.",
        "La distancia entre un {room} de promotora y uno que parece de estudio de interiorismo es más corta de lo que crees, y se mide en milímetros y acabados, no en dinero.",
    ],
    "cozy": [
        "Lo acogedor no es un estilo que se compra. Es un conjunto de condiciones físicas, y una vez sabes cuáles son puedes reproducirlas en casi cualquier habitación, incluso en una moderna y fría.",
        "Hay casas que te dan ganas de sentarte y otras en las que te quedas de pie sin saber por qué. La diferencia es medible, y tiene poco que ver con el presupuesto.",
        "Un {room} acogedor no es un {room} lleno de cosas. Es uno con la luz a la altura adecuada, superficies blandas y algo de vida a la vista.",
    ],
    "brighter": [
        "Si tu {room} está oscuro a las cinco de la tarde, la solución casi nunca es una bombilla más potente. Es cambiar dónde está la luz y qué superficies la devuelven.",
        "Una habitación puede tener una ventana grande y seguir sintiéndose apagada. Lo que falla suele ser lo que hay delante del cristal y lo que hay en las paredes.",
        "La luz es lo que más cambia la percepción de una casa y lo último en lo que la gente invierte. Vamos a darle la vuelta a ese orden.",
    ],
    "storage": [
        "El desorden casi nunca es un problema de cantidad de armarios. Es un problema de que las cosas no tienen un sitio a menos de dos pasos de donde se usan.",
        "Si recoges la casa y a los tres días vuelve a estar igual, el sistema está mal planteado, no tu fuerza de voluntad.",
    ],
    "mistakes": [
        "Casi todas las habitaciones que se sienten raras están cometiendo uno de un número muy pequeño de errores, y todos tienen arreglo.",
        "Hay una lista corta de fallos que se repiten en la mayoría de las casas. Ninguno es grave y todos son reversibles.",
    ],
}

GENERAL_HOOKS = [
    "Hay habitaciones que se sienten bien desde el momento en que entras, y casi nunca es por lo que costaron los muebles.",
    "Existe una razón por la que una habitación decorada se siente distinta a una habitación amueblada, y casi toda la diferencia está en un puñado de decisiones que cualquiera puede tomar.",
    "La mayoría de las casas están a unas pocas decisiones de verse muchísimo mejor de lo que se ven ahora, y ninguna de esas decisiones implica una reforma.",
    "Entra en cualquier casa bien resuelta y encontrarás las mismas decisiones discretas repetidas una y otra vez, fuera cual fuera el presupuesto.",
    "Se puede gastar una fortuna en una habitación y que siga pareciendo sin terminar, y se puede gastar muy poco y que parezca cuidada.",
]

PROMISES = [
    "En este vídeo vamos a ver {count}, una por una, con el motivo que hay detrás de cada una y cómo aplicarla en una casa real.",
    "En los próximos {duration} {minutes} repasamos {count} {ideas}, y de cada una te cuento por qué funciona y cómo hacerla de verdad.",
    "Vamos a cubrir {count} {changes} concretos, por qué los repiten los interioristas y qué hacer si tu casa no acompaña.",
    "Aquí van {count} {ideas} que merece la pena conocer, cada una con el principio que la sostiene y una forma práctica de aplicarla esta misma semana.",
    "Lo que viene son {count} {ideas} prácticas. Sin listas de compra imposibles y sin obras: solo decisiones que cambian cómo se lee una habitación.",
]

PROMISE_TAILS = [
    "Algunas de ellas no cuestan absolutamente nada.",
    "Varias se hacen en una tarde y sin herramientas especiales.",
    "Unas cuantas son gratis y consisten en mover lo que ya tienes.",
    "No hace falta hacerlas todas. Con dos o tres ya se nota.",
    "Quédate con las que encajen en tu casa y olvida el resto.",
]

STATEMENT_FRAMES = [
    "{title}.",
    "{title}.",
    "{title}.",
    "Vamos con esta: {title_lower}.",
    "{title}, y pesa más de lo que parece.",
    "Esta es sencilla: {title_lower}.",
    "Empieza por aquí: {title_lower}.",
    "La regla es corta: {title_lower}.",
    "{title}, que es más fácil de lo que suena.",
]

QUESTION_FRAMES = [
    "¿Te has fijado en que unas casas aciertan con esto y otras no? {title}.",
    "¿Qué marca realmente la diferencia aquí? {title}.",
    "¿Qué cambiarías primero en una habitación así? Casi siempre esto: {title_lower}.",
    "¿Por qué se repite esto en todas las casas bien resueltas? {title}.",
    "¿Quieres la versión que usan de verdad los interioristas? {title}.",
    "¿Cuál es el arreglo más barato de toda la lista? Probablemente este: {title_lower}.",
    "Piensa en qué es lo primero que mira tu ojo al entrar. Y entonces: {title}.",
    "¿Cuál de estas notarías si faltara? Seguramente esta: {title_lower}.",
]

WARNING_FRAMES = [
    "Esta es la que más se falla. {title}.",
    "Si solo vas a corregir una cosa de la lista, plantéate que sea esta. {title}.",
    "Aquí va un error que conviene pillar pronto. {title}.",
    "Ojo con esta, porque es fácil hacerla al revés. {title}.",
    "Esto estropea más habitaciones que casi ninguna otra cosa. {title}.",
    "Si fallas aquí, todo lo demás que hagas irá en contra. {title}.",
    "Merece la pena pararse, porque el arreglo es fácil y el error sale caro. {title}.",
]

SCENARIO_FRAMES = [
    "Imagina la habitación antes y después de este único cambio. {title}.",
    "Imagina entrar dos veces en la misma habitación, una con esto hecho y otra sin ello. {title}.",
    "Ponte en la puerta y mira tu propia habitación mientras escuchas esta. {title}.",
    "Piensa en la última casa en la que entraste que se sintiera realmente terminada. Casi seguro hacía esto: {title_lower}.",
    "Pruébalo primero como experimento mental y luego como proyecto. {title}.",
    "Dos habitaciones idénticas a una decisión de distancia. {title}.",
    "Piensa en la misma habitación fotografiada por una inmobiliaria y por una revista. La diferencia suele ser esta: {title_lower}.",
]

NUMBER_FRAMES = [
    "Número {n}.",
    "Idea número {n}.",
    "La número {n} de la lista.",
    "Esto nos lleva a la número {n}.",
    "Vamos con la número {n}.",
    "Número {n}, y esta me gusta especialmente.",
]

TRANSITIONS = [
    "La siguiente va directamente ligada a eso.",
    "Esta idea resuelve un problema parecido.",
    "Aquí va otra que se infravalora bastante.",
    "La que viene es de las más fáciles de toda la lista.",
    "Este punto aparece en casi todas las casas.",
    "Una vez resuelto eso, mira lo siguiente.",
    "Hay una idea relacionada que merece la pena contar aquí.",
    "Esta es menos evidente, pero importa igual.",
    "La siguiente es donde se tuercen muchas habitaciones.",
    "Aquí va algo que cambia una habitación más rápido de lo que la gente espera.",
    "Seguimos, y esta es rápida.",
    "Ahora algo que puedes hacer en una tarde.",
    "Esta no cuesta absolutamente nada.",
    "Relacionado con lo anterior, y igual de útil.",
    "Aquí es donde la cosa se pone interesante.",
    "Eso enlaza bien con lo siguiente.",
    "La otra cara de eso también conviene conocerla.",
    "Y luego está esta, que casi todo el mundo se salta.",
    "Esta sorprende bastante.",
    "Ten eso en mente mientras vemos lo siguiente.",
]

WHY_LEADS = [
    "Te explico por qué importa.",
    "El motivo es sencillo.",
    "El razonamiento detrás de esto es simple.",
    "Esto funciona por una razón concreta.",
    "Hay un principio real debajo de esto.",
    "",
    "",
]

HOW_LEADS = [
    "En la práctica, se hace así.",
    "Para aplicarlo en tu casa,",
    "En términos prácticos,",
    "Así es como se lleva a cabo.",
    "La forma de hacerlo de verdad es simple.",
    "",
    "",
]

MISTAKE_LEADS = [
    "El error que hay que evitar:",
    "Donde suele torcerse esto:",
    "Una cosa que conviene no hacer:",
    "Aquí es donde patina la mayoría de las habitaciones.",
]

ITEM_CLOSERS = [
    "Es un cambio pequeño que cambia la lectura completa de la habitación.",
    "Una vez lo ves, ya no puedes dejar de verlo en casa de los demás.",
    "Ese único ajuste hace más que otra ronda de compras.",
    "Es de esos detalles que solo se notan cuando faltan.",
    "Merece la pena aunque no cambies nada más de la lista.",
    "Haz solo eso y el resto de la habitación empieza a tener más sentido.",
    "Escrito suena a poco. En la habitación no lo es.",
    "Es de esas cosas que la gente no sabe nombrar pero siempre nota.",
]

CONCLUSION_LEADS = [
    "Y hasta aquí la lista.",
    "Con esto llegamos al final.",
    "Esas son las {count}.",
    "Ahí lo tienes: {count} {ideas} con las que trabajar.",
]

CONCLUSION_BODIES = [
    "Si te quedas con una sola idea de todo esto, que sea esta: las habitaciones buenas se editan, no se llenan. Casi todo lo que hemos visto consiste en quitar una distracción o en darle a un elemento el espacio suficiente para funcionar.",
    "El hilo que une todo esto es la contención. La escala, la luz y el material hacen casi todo el trabajo, y los accesorios hacen mucho menos de lo que la gente cree.",
    "Nada de esto tiene que pasar de golpe. Elige los dos cambios que más te hayan sonado a tu casa, hazlos bien, y vive con la habitación un par de semanas antes de decidir el siguiente.",
    "Lo que tienen en común es que ninguno depende de un presupuesto grande. Dependen de mirar la proporción, la luz y lo que ya tienes.",
    "Si después de todo esto tu habitación sigue sin encajar, vuelve a lo básico: la luz, si es cálida y está repartida; la alfombra, si es lo bastante grande; y si hay algo encima de una superficie que no necesita estar ahí.",
]

CTAS = [
    "Si te ha servido, suscribirte ayuda a que te llegue el siguiente.",
    "Si has encontrado algo que quieras probar, en el canal hay más vídeos de este estilo.",
    "Gracias por verlo, y nos vemos en el siguiente.",
    "Si tienes una habitación que se te resiste, déjala en los comentarios y puede acabar en un vídeo.",
    "Esto es todo por hoy. Gracias por el rato.",
]

ELABORATIONS: dict[str, list[str]] = {
    "lighting": [
        "Pruébalo por la tarde y no a mediodía, porque es cuando más se nota la diferencia.",
        "Si no sabes si está funcionando, haz una foto antes y otra después. La cámara perdona menos que el ojo.",
    ],
    "curtains": [
        "Mide dos veces antes de taladrar: una barra mal colocada se nota desde la puerta.",
        "Si la tela llega justa, un dobladillo con cinta termoadhesiva resuelve el problema en media hora.",
    ],
    "rug": [
        "Marca el tamaño con cinta de pintor en el suelo antes de comprar nada.",
        "Una alfombra de lana aguanta años; una sintética se apelmaza en un par de temporadas.",
    ],
    "storage": [
        "Un sistema de guardado solo funciona si es más fácil de seguir que de ignorar.",
        "Compra los recipientes después de saber qué vas a guardar, no antes.",
    ],
    "color": [
        "Mira el color a las tres de la tarde y a las diez de la noche antes de decidir.",
        "Pinta una cartulina grande en lugar de una mancha en la pared: verás el color mucho mejor.",
    ],
    "small space": [
        "En pocos metros, cada decisión pesa el doble que en una habitación grande.",
        "Vacía la habitación mentalmente y vuelve a meter solo lo que de verdad usas.",
    ],
    "furniture": [
        "Antes de comprar, dibuja la silueta en el suelo con cinta y vive con ella dos días.",
        "Un mueble bien elegido dura veinte años; uno elegido con prisa dura dos.",
    ],
    "plants": [
        "Elige la planta según la luz que tengas, no según la foto que te guste.",
        "Una planta cuidada suma; una seca resta más de lo que aportaba.",
    ],
    "art": [
        "Sujeta la pieza con las manos en la pared y pide una segunda opinión antes de clavar.",
        "Un marco ancho hace más por una lámina que la propia lámina.",
    ],
    "kitchen": [
        "Empieza por la encimera. Es lo que más se ve y lo que menos cuesta cambiar.",
        "Guarda por frecuencia de uso: lo diario a la altura de la mano.",
    ],
}

GENERIC_ELABORATIONS = [
    "Es de esos cambios que escritos parecen menores y en la habitación se leen como importantes.",
    "Dale una semana antes de juzgarlo, porque el ojo se acostumbra despacio.",
    "Si solo vas a hacer un par de cosas de esta lista, esta es un buen punto de partida.",
    "Haz una foto antes y después. La diferencia casi siempre se ve mejor en la pantalla que en persona.",
    "Nada de esto necesita un profesional. Necesita decidir y estar dispuesto a mover las cosas dos veces.",
    "Aquí el coste es tiempo y no dinero, que es justo por lo que se salta tan a menudo.",
    "Hazlo bien una vez en lugar de mal dos, y ya no tendrás que volver a pensarlo.",
    "Si vives con más gente, acordad esta antes de empezar a mover nada.",
    "Mide primero. Casi todos los arrepentimientos en decoración vienen de una medida que nadie tomó.",
    "Sepárate y mira desde la puerta, no desde el centro de la habitación.",
    "Merece la pena hacerlo una tarde tranquila y no encajarlo en una tarde ocupada.",
    "Fíjate en cómo queda la habitación por la noche además de con luz de día, porque pueden no parecerse.",
    "No hay prisa. Las habitaciones mejoran más rápido cuando las decisiones se toman despacio.",
    "Guarda un mes lo que quites antes de deshacerte de ello, por si la habitación te dice otra cosa.",
]

INTRO_CONTEXT: dict[str, str] = {
    "living rooms": "El salón suele ser el espacio compartido más grande de la casa y el que sale en las fotos, que es exactamente por lo que sus problemas se ven tanto.",
    "bedrooms": "El dormitorio tiene un encargo raro. Tiene que verse bien y tiene que ayudarte a desconectar, y esas dos cosas tiran en direcciones distintas más a menudo de lo que parece.",
    "kitchens": "La cocina es la estancia más cara por metro cuadrado de casi cualquier casa, y por eso frustra tanto que aun así se sienta incompleta.",
    "small spaces": "Los espacios pequeños no son un problema que resolver. Son un conjunto de restricciones, y las restricciones suelen dar mejores habitaciones que los metros de sobra.",
    "lighting": "La luz es el elemento más infravalorado de una casa. Cambia el color, el ánimo, el tamaño percibido y hasta lo cansado que te sientes por la tarde.",
    "colors": "El color es la decisión que más se sufre y que más se falla, casi siempre porque se elige la primera en lugar de la última.",
    "furniture placement": "Colocar los muebles es gratis. También es lo que más fiablemente separa una habitación que funciona de una que no.",
    "storage": "El almacenaje no consiste en tener más armarios. Consiste en ajustar el espacio a lo que realmente vive en la habitación.",
    "expensive look": "Las casas que parecen caras rara vez son caras. Son casas donde un número pequeño de detalles está bien resuelto.",
    "interior design mistakes": "Ninguno de estos errores es raro. La mayoría de las casas están cometiendo al menos tres ahora mismo, y todos son reversibles.",
    "cozy homes": "Lo acogedor no es un estilo, es un conjunto de condiciones físicas: luz cálida y baja, superficies blandas, un poco de resguardo y algo de vida a la vista.",
    "apartment decorating": "Un piso viene con una envolvente fija y muchas restricciones compartidas, así que las victorias están en la distribución, la luz y el sonido antes que en la estructura.",
}

ROOM_WORDS: dict[str, str] = {
    "living rooms": "salón",
    "bedrooms": "dormitorio",
    "kitchens": "cocina",
    "bathrooms": "baño",
    "small spaces": "espacio",
    "apartment decorating": "piso",
    "renter-friendly decorating": "piso de alquiler",
    "home organization": "hogar",
    "storage": "hogar",
}

DEFAULT_ROOM = "hogar"
INTRO_HEADING = "Introducción"
CONCLUSION_HEADING = "Para terminar"

#: Números escritos, para que un guion nunca diga "1 ideas".
_NUMBER_WORDS = {
    1: "una", 2: "dos", 3: "tres", 4: "cuatro", 5: "cinco", 6: "seis",
    7: "siete", 8: "ocho", 9: "nueve", 10: "diez", 11: "once", 12: "doce",
}


def count_words(count: int) -> dict[str, str]:
    """Concordancia en español: género femenino, porque son "ideas"."""

    singular = count == 1
    return {
        "count": _NUMBER_WORDS.get(count, str(count)) if count <= 12 else str(count),
        "ideas": "idea" if singular else "ideas",
        "changes": "cambio" if singular else "cambios",
        "them": "la" if singular else "las",
        "it": "la",
    }
