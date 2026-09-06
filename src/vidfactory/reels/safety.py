"""What a reel about diabetes is not allowed to say.

The long-form side learned that a plausible sentence and a true one are
different things, and built ``contradiction``, ``concepts`` and ``principles``
to tell them apart. The stakes here are higher: someone watching a forty
second video about food may act on it, and the failure mode is not a
repetitive edit, it is a person changing what they eat - or worse, what they
inject - because a script wanted a stronger hook.

So three separate checks, and all three are errors in production.

**Forbidden claims.** Cure, reversal, guaranteed results, immediate glucose
drops, universal prohibitions, and anything touching medication or insulin
dosing. These are not softened, hedged or rewritten into a milder version:
the pattern matching here refuses the sentence and the generator never had a
template that produces one.

**Missing hedges.** "Las fresas bajan la glucosa" is false. "Las fresas
suelen aportar menos carbohidratos por racion que muchas otras frutas" is
true and is the same information. A sentence that asserts a glucose effect
without a hedge is a claim the evidence does not support at that strength,
so the hedge is not decoration - it is the part that makes it correct.

**Fear as a retention device.** A hook may be surprising; it may not be
frightening. "Esto puede estar destrozando tu glucosa" is the kind of
sentence that keeps people watching and makes them worse off.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

from .sources import SOURCES

#: Anything that claims the disease itself can be cured, reversed or removed
#: by food, plus guaranteed outcomes and immediate effects.
FORBIDDEN: tuple[tuple[str, str, str], ...] = (
    (r"\bcura(?:r|n)?\b[^.]{0,30}\bdiabetes\b", "cure",
     "no food cures diabetes"),
    (r"\bdiabetes\b[^.]{0,30}\bse cura\b", "cure", "no food cures diabetes"),
    (r"\brevierte|\brevertir\b[^.]{0,30}\bdiabetes\b", "reversal",
     "reversal is not something a reel may promise"),
    (r"\belimina(?:r)?\b[^.]{0,30}\bdiabetes\b", "cure",
     "no food eliminates diabetes"),
    (r"\bgarantizad[oa]s?\b", "guarantee", "no outcome here is guaranteed"),
    (r"\b(baja|bajan|reduce|reducen)\b[^.]{0,25}\b(glucosa|az[uú]car)\b"
     r"[^.]{0,25}\b(inmediatamente|al instante|en minutos|ya)\b",
     "immediate_effect", "no food lowers glucose immediately"),
    (r"\b(deja|dejar|suspende|suspender|abandona|abandonar)\b[^.]{0,25}"
     r"\b(medicaci[oó]n|tratamiento|pastillas|insulina|metformina)\b",
     "medication", "never tell anyone to stop treatment"),
    (r"\b(sube|subir|baja|bajar|ajusta|ajustar|cambia|cambiar)\b[^.]{0,20}"
     r"\b(dosis|unidades)\b", "dosing", "dosing is not a reel's business"),
    (r"\btu (dosis|insulina|tratamiento|medicaci[oó]n)\b", "dosing",
     "individual medical instruction"),
    (r"\b(prohibid[oa]s?|proh[ií]be)\b", "prohibition",
     "no food is universally forbidden"),
    (r"\bno (puedes|debes|podr[ií]as) (comer|tomar|probar)\b", "prohibition",
     "no food is universally forbidden"),
    (r"\bnunca (comas|tomes|vuelvas a comer)\b", "prohibition",
     "no food is universally forbidden"),
    (r"\bmilagro|milagros[oa]s?\b", "miracle", "not a miracle"),
    (r"\bdesintoxica|detox\b", "pseudoscience", "not a supported mechanism"),
)

#: Fear used to hold attention. Surprise is allowed; alarm is not.
FEAR: tuple[tuple[str, str, str], ...] = (
    (r"\bdestro(?:za|zando|zar)\b", "fear", "alarmist"),
    (r"\barruina(?:ndo)?\b", "fear", "alarmist"),
    (r"\bpeligros[oa]s?\b", "fear", "alarmist"),
    (r"\bte est[aá]s? (matando|envenenando)\b", "fear", "alarmist"),
    (r"\bveneno\b", "fear", "alarmist"),
    (r"\bmortal\b", "fear", "alarmist"),
)

#: The words that make a statement about glucose honest. A claim asserting an
#: effect without one of these is asserting more than the evidence supports.
HEDGES: tuple[str, ...] = (
    "suele", "suelen", "puede", "pueden", "podr[ií]a", "podr[ií]an",
    "tiende", "tienden", "en general", "por lo general", "normalmente",
    "habitualmente", "aproximad", "suele ser", "a menudo", "muchas veces",
    "con frecuencia", "depende", "seg[uú]n", "orientativ", "moderad",
    "quiz[aá]", "posiblemente", "en muchas personas", "para algunas personas",
)

#: What makes a sentence a *claim* rather than a subject line.
#:
#: Deliberately directional, and deliberately not bare "glucosa". "Como
#: influye el tamano de la racion en la glucosa" names the subject and
#: asserts nothing, so demanding a hedge from it would be asking a title to
#: apologise for existing. "Diez frutas que bajan el azucar" asserts a
#: direction the evidence does not support at that strength, and that is the
#: sentence this exists to refuse - it is the exact phrasing the brief calls
#: out. A comparative impact claim counts too: "menos impacto en la glucosa"
#: is a real assertion about magnitude.
EFFECT_WORDS: tuple[str, ...] = (
    r"\bsube[ns]?\b", r"\bsubir\b", r"\bsubida\b",
    r"\bbaja[ns]?\b", r"\bbajar\b", r"\bbajada\b",
    r"\bdispara[ns]?\b", r"\baumenta[ns]?\b", r"\breduce[ns]?\b",
    r"\beleva[ns]?\b", r"\bpicos?\b",
    r"\b(m[aá]s|menos|mayor|menor) impacto\b",
)

#: Individual variation, portion size and preparation are the three caveats
#: that make almost every statement in this niche correct rather than
#: misleading. A reel is expected to carry at least one of them.
CAVEATS: tuple[str, ...] = (
    "cantidad", "raci[oó]n", "raciones", "porci[oó]n", "cada persona",
    "cada uno", "individual", "depende", "preparaci[oó]n", "acompa[nñ]a",
    "combina", "medicaci[oó]n", "tu m[eé]dico", "profesional",
)


def _flat(text: str) -> str:
    return " " + re.sub(r"\s+", " ", str(text or "").lower()).strip() + " "


@dataclass
class MedicalRisk:
    """One sentence that must not be said the way it is said."""

    code: str
    why: str
    sentence: str
    kind: str = "forbidden"       # forbidden | fear | unhedged

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "kind": self.kind,
            "why": self.why,
            "sentence": self.sentence[:200],
        }


_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_SPLIT.split(str(text or "")) if s.strip()]


def find_forbidden(text: str) -> list[MedicalRisk]:
    """Claims a reel may never make, whatever the topic."""

    found: list[MedicalRisk] = []
    for sentence in sentences(text):
        haystack = _flat(sentence)
        for pattern, code, why in FORBIDDEN:
            if re.search(pattern, haystack):
                found.append(MedicalRisk(code, why, sentence, "forbidden"))
        for pattern, code, why in FEAR:
            if re.search(pattern, haystack):
                found.append(MedicalRisk(code, why, sentence, "fear"))
    return found


def is_hedged(sentence: str) -> bool:
    haystack = _flat(sentence)
    return any(re.search(h, haystack) for h in HEDGES)


def makes_effect_claim(sentence: str) -> bool:
    haystack = _flat(sentence)
    return any(re.search(w, haystack) for w in EFFECT_WORDS)


def find_unhedged(text: str) -> list[MedicalRisk]:
    """Effect claims stated more strongly than the evidence allows.

    A question is exempt: "?Hay que dejar la fruta?" asserts nothing, and it
    is how the myth format has to open.
    """

    found: list[MedicalRisk] = []
    for sentence in sentences(text):
        if sentence.strip().startswith("¿") or sentence.strip().endswith("?"):
            continue
        if makes_effect_claim(sentence) and not is_hedged(sentence):
            found.append(
                MedicalRisk(
                    "unhedged",
                    "states a glucose effect without the hedge that makes it true",
                    sentence,
                    "unhedged",
                )
            )
    return found


def find_risks(text: str) -> list[MedicalRisk]:
    return [*find_forbidden(text), *find_unhedged(text)]


def mentions_caveat(text: str) -> bool:
    haystack = _flat(text)
    return any(re.search(c, haystack) for c in CAVEATS)


@dataclass
class UnsupportedClaim:
    """A factual sentence with nothing behind it."""

    sentence: str
    reason: str = "no source"

    def to_dict(self) -> dict[str, Any]:
        return {"sentence": self.sentence[:200], "reason": self.reason}


def find_unsupported(claims: Sequence[Any]) -> list[UnsupportedClaim]:
    """Claims carrying no source, or a source that does not resolve.

    ``claims`` are ``(sentence, source_keys)`` pairs. A typo in a key counts
    as unsupported rather than being skipped, because a claim whose source
    was mistyped is precisely the one that would otherwise ship unbacked.
    """

    out: list[UnsupportedClaim] = []
    for sentence, keys in claims:
        keys = [str(k) for k in (keys or [])]
        if not keys:
            out.append(UnsupportedClaim(str(sentence), "no source"))
            continue
        missing = [k for k in keys if k not in SOURCES]
        if missing:
            out.append(
                UnsupportedClaim(str(sentence), f"unknown source {missing[0]!r}")
            )
    return out


def summarise(
    risks: Iterable[MedicalRisk], unsupported: Iterable[UnsupportedClaim]
) -> dict[str, Any]:
    risks, unsupported = list(risks), list(unsupported)
    return {
        "medical_claim_risk_count": len(risks),
        "medical_claim_risks": [r.to_dict() for r in risks[:10]],
        "unsupported_claim_count": len(unsupported),
        "unsupported_claims": [u.to_dict() for u in unsupported[:10]],
    }
