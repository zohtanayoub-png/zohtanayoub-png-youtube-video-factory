"""Content language, and why it is not the same thing as search language.

The channel narrates in Spanish. Pexels does not. A stock library indexed by
English-speaking contributors returns markedly better interior footage for
``floor to ceiling curtains living room`` than for ``cortinas de suelo a
techo``, and translating the query is the wrong instinct: the narration is
what the viewer hears, the query is a lookup key into someone else's index.

So this module holds two separate ideas:

* **content language** - the language of the title, script, subtitles,
  metadata, chapters and voice. Configurable, Spanish by default.
* **search language** - the language the stock providers are queried in.
  English, always, built from each idea's canonical English metadata rather
  than from the narration the viewer hears.

Everything downstream asks this registry rather than testing string equality
against a locale code, so adding a third language is a table entry and a
phrase pool, not a hunt through the pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from .logging_utils import get_logger

log = get_logger("LANG")


@dataclass(frozen=True)
class Language:
    """Everything the pipeline needs to know to produce a video in one language."""

    #: BCP-47 code used for YouTube metadata and the report.
    code: str
    #: Short key used to select phrase pools and knowledge ("es", "en").
    key: str
    #: What a human calls it, and what the workflow dropdown shows.
    label: str
    #: Piper voices, best first. The first that provisions wins.
    voices: tuple[str, ...]
    #: eSpeak NG voice used when Piper cannot be provisioned.
    espeak_voice: str
    #: Roughly how fast this language is spoken, words per minute, used to
    #: size the script before a single word has been synthesized. Spanish runs
    #: more syllables per word than English at the same speaking rate.
    words_per_minute: float
    #: Average characters per word, used when allocating subtitle time.
    subtitle_chars_per_word: float
    #: Words that must never end a subtitle line - articles, prepositions and
    #: conjunctions that belong with whatever follows them.
    clinging_words: frozenset[str] = field(default_factory=frozenset)

    @property
    def is_english(self) -> bool:
        return self.key == "en"


#: Articles, prepositions and conjunctions that must stay attached to the word
#: after them, so a caption never ends on "de" or "the".
_ES_CLINGING = frozenset("""
el la los las un una unos unas lo al del
de en con por para sin sobre entre hasta desde hacia tras ante bajo
y e o u ni que qué si tu tus su sus mi mis
más muy tan como cuando donde porque aunque
se le les me te nos os
""".split())

_EN_CLINGING = frozenset("""
a an the of in on at to for with from by into over under
and or but nor so yet than that which who whose
your our their its his her my this these those
is are was were be been being
""".split())


SPANISH = Language(
    code="es-ES",
    key="es",
    label="Spanish",
    # es_ES-sharvard-medium is the female Castilian voice in the Piper
    # catalogue; the Mexican and MLS voices are the fallbacks, in that order,
    # because a neutral Latin American voice is a better failure mode for a
    # Spanish channel than an English one.
    voices=(
        "es_ES-sharvard-medium",
        "es_MX-claude-high",
        "es_ES-davefx-medium",
        "es_ES-mls_9972-low",
    ),
    espeak_voice="es+f3",
    # Spanish is spoken at a higher syllable rate but with longer words, and
    # Piper's Spanish voices land slightly slower than the English ones.
    words_per_minute=142.0,
    subtitle_chars_per_word=5.6,
    clinging_words=_ES_CLINGING,
)

ENGLISH = Language(
    code="en-US",
    key="en",
    label="English",
    voices=(
        "en_US-hfc_female-medium",
        "en_US-amy-medium",
        "en_US-lessac-medium",
    ),
    espeak_voice="en-us+f3",
    words_per_minute=150.0,
    subtitle_chars_per_word=5.1,
    clinging_words=_EN_CLINGING,
)

LANGUAGES: dict[str, Language] = {SPANISH.key: SPANISH, ENGLISH.key: ENGLISH}

#: The channel's default. Changing this changes the language of every artifact
#: a run produces; nothing else in the pipeline hard-codes a language.
DEFAULT_LANGUAGE = SPANISH

#: Everything a person might reasonably type or pick in a dropdown.
_ALIASES: dict[str, str] = {
    "es": "es", "es-es": "es", "es_es": "es", "es-mx": "es", "es-419": "es",
    "spanish": "es", "espanol": "es", "español": "es", "castellano": "es",
    "en": "en", "en-us": "en", "en_us": "en", "en-gb": "en",
    "english": "en", "ingles": "en", "inglés": "en",
}


def resolve_language(value: Any = None) -> Language:
    """Accept a code, a key or a dropdown label. Never raise.

    An unrecognised value falls back to the default and says so, because a
    typo in a workflow input should not stop a render - it should produce the
    channel's normal language and a line in the log.
    """

    if isinstance(value, Language):
        return value
    text = str(value or "").strip().lower().replace(" ", "")
    if not text:
        return DEFAULT_LANGUAGE
    key = _ALIASES.get(text)
    if key is None:
        key = _ALIASES.get(text.split("-")[0].split("_")[0], "")
    if key and key in LANGUAGES:
        return LANGUAGES[key]
    log.warning(
        "Unknown language %r; using %s. Known: %s",
        value, DEFAULT_LANGUAGE.label,
        ", ".join(sorted({l.label for l in LANGUAGES.values()})),
    )
    return DEFAULT_LANGUAGE


def language_from_config(config: Mapping[str, Any] | Any) -> Language:
    """Read ``channel.language`` from a Config-like object."""

    getter = getattr(config, "get", None)
    value = getter("channel.language", None) if callable(getter) else None
    return resolve_language(value)
