"""DIABETES REELS: the rules that make this product safe to publish.

The long-form suite protects an edit. This one protects a claim. A reel about
food and glucose is watched by people who may act on it, so the tests that
matter most here are the ones that refuse sentences: no cure, no reversal, no
guarantees, no dosing, no universal prohibition, and no effect stated more
strongly than the evidence supports.

The second half of the file pins the shape - the six beats, the fixed title,
the caption safe area, the vertical frame - and the last test pins the thing
that actually matters about the separation: nothing in ``reels`` is reachable
from the long-form pipeline.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from vidfactory.reels import hooks, safety
from vidfactory.reels.captions import (
    BOTTOM_UNSAFE,
    title_renders,
    REEL_CAPTIONS,
    REEL_HEIGHT,
    REEL_TITLE,
    REEL_WIDTH,
    TOP_UNSAFE,
    accented,
    safe_area_report,
    write_reel_ass,
)
from vidfactory.reels.knowledge import BY_SLUG, FORMATS, TOPICS, claims_of, find_topic
from vidfactory.reels.metadata import DISCLAIMER, caption, hashtags
from vidfactory.reels.qc import build_report, explains_something, value_density
from vidfactory.reels.script import (
    ALLOWED_SECONDS,
    CTA_VARIANTS,
    build,
    build_fitted,
)


def fitted(topic, target_seconds=45, **kw):
    """The script the pipeline would render, at the duration it would use.

    ``build`` is strict: it refuses to ship four items under a title that
    says five. The pipeline answers that by rendering longer, so a test
    sweeping every topic has to do the same or it is testing a code path
    production never takes.
    """

    return build_fitted(topic, target_seconds=target_seconds, **kw)[0]

from vidfactory.reels.sources import SOURCES, bibliography

FIRST = "frutas-impacto-moderado"


# ---------------------------------------------------------------------------
# Safety. These are the tests this product exists to pass.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("sentence, code", [
    ("Esta fruta cura la diabetes.", "cure"),
    ("Con esto puedes revertir la diabetes.", "reversal"),
    ("Resultado garantizado en dos semanas.", "guarantee"),
    ("Este alimento baja tu glucosa inmediatamente.", "immediate_effect"),
    ("Puedes dejar la medicacion si comes asi.", "medication"),
    ("Ajusta tu dosis de insulina segun esto.", "dosing"),
    ("La fruta esta prohibida si tienes diabetes.", "prohibition"),
    ("Nunca comas platano.", "prohibition"),
    ("Un alimento milagroso para la diabetes.", "miracle"),
])
def test_the_forbidden_claims_are_refused(sentence, code):
    found = safety.find_forbidden(sentence)
    assert found, sentence
    assert any(r.code == code for r in found), [r.code for r in found]


@pytest.mark.parametrize("sentence", [
    "Este desayuno esta destrozando tu glucosa.",
    "El azucar es un veneno para ti.",
    "Es peligroso comer fruta por la noche.",
])
def test_fear_is_not_a_retention_device(sentence):
    """Surprise is allowed. Alarm is not - it keeps people watching and
    makes them worse off, which is the trade this brief refuses."""

    assert any(r.kind == "fear" for r in safety.find_forbidden(sentence))


def test_the_phrasing_the_brief_calls_out_is_refused():
    """"10 frutas que bajan el azucar" against the phrasing that replaces it."""

    assert safety.find_unhedged("10 frutas que bajan el azucar")
    assert not safety.find_unhedged(
        "10 frutas que suelen tener un impacto mas moderado en la glucosa"
    )


def test_naming_a_subject_is_not_claiming_an_effect():
    """A title may say what it is about without apologising for existing."""

    assert not safety.find_unhedged("Como influye el tamano de la racion en la glucosa")
    assert not safety.find_unhedged("Naranja entera o zumo: que cambia para tu glucosa")


def test_every_claim_in_the_knowledge_base_is_supported():
    for topic in TOPICS:
        assert not safety.find_unsupported(claims_of(topic)), topic.slug


def test_every_source_key_resolves_to_a_real_organisation():
    for topic in TOPICS:
        for key in topic.all_sources:
            assert key in SOURCES, f"{topic.slug} cites unknown {key!r}"
            assert SOURCES[key].url.startswith("https://")


def test_a_mistyped_source_counts_as_unsupported():
    """Not skipped. A claim whose source was typed wrong is exactly the one
    that would otherwise ship with nothing behind it."""

    assert safety.find_unsupported([("Las fresas tienen fibra.", ("no_such_source",))])


def test_no_topic_says_anything_it_should_not():
    for topic in TOPICS:
        script = fitted(topic, 45)
        assert not safety.find_risks(script.narration), topic.slug


# ---------------------------------------------------------------------------
# The hook gate
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("opener", [
    "Hoy vamos a hablar de la fruta y la diabetes.",
    "En este video veremos cinco frutas.",
    "Hola amigos, bienvenidos al canal.",
    "Sabias que la fruta tiene azucar?",
])
def test_the_banned_openers_are_rejected_outright(opener):
    """Refused rather than scored low. "Hoy vamos a hablar de..." is not a
    weak hook, it is a wasted second - and it is the only second guaranteed
    to be watched."""

    candidate = hooks.score_hook(opener, BY_SLUG[FIRST])
    assert candidate.rejected and candidate.total == 0.0


@pytest.mark.parametrize("opener", [
    "Estas frutas curan la diabetes.",
    "No vas a creer lo que hace esta fruta.",
    "Estas cinco frutas bajan la glucosa.",
])
def test_a_dishonest_hook_cannot_win_on_being_punchy(opener):
    assert hooks.score_hook(opener, BY_SLUG[FIRST]).rejected


#: The hooks the brief lists under "Prefer hooks like", each with the topic
#: it belongs to. The bar was read off these: scored against their own topics
#: they land between 0.491 and 0.692, and a generic opening scores 0.376.
PROBLEM_FIRST = [
    ("frutas-impacto-moderado",
     "Si tienes diabetes y te preocupa que la fruta te dispare la glucosa, escucha esto."),
    ("desayunos-picos",
     "Tu glucosa sube mucho despues del desayuno? Puede que el problema este aqui."),
    ("mito-dejar-fruta",
     "Si tienes diabetes, dejar toda la fruta por miedo al azucar puede no ser necesario."),
    ("ranking-frutas",
     "Si nunca sabes que fruta elegir para no disparar tu glucosa, guarda estas cinco opciones."),
    ("desayunos-picos",
     "Este desayuno parece saludable, pero puede hacer que tu glucosa suba mucho mas rapido de lo que esperas."),
    ("combinar-fruta",
     "Si comes fruta sola y despues ves un pico grande, hay algo importante que debes saber."),
    # The one the brief writes out in its timeline example.
    ("frutas-impacto-moderado",
     "Si tienes diabetes y te preocupa que la fruta te dispare la glucosa, apunta estas cinco opciones."),
]


@pytest.mark.parametrize("slug,example", PROBLEM_FIRST)
def test_the_briefs_problem_first_examples_clear_the_bar(slug, example):
    """The bar was read off these, not chosen."""

    candidate = hooks.score_hook(example, BY_SLUG[slug])
    assert not candidate.rejected, example
    assert candidate.total >= hooks.HOOK_PASS, (example, candidate.total)


def test_a_hook_that_names_a_subject_no_longer_clears_a_problem_first_bar():
    """The first brief's openings are still legal, and no longer enough.

    "Si tienes diabetes, no todas las frutas afectan igual a tu glucosa" is a
    true, on-topic, perfectly grammatical sentence, and it is about fruit
    rather than about the viewer's problem with fruit. It used to pass at
    0.54; under a scoring that leads with problem recognition it scores 0.32,
    which is the same as a deliberately generic opening. That is the change
    the second brief asked for, so it is asserted rather than tolerated -
    but it is scored low, not refused, because refusing it would be a claim
    that it is dishonest, and it is not.
    """

    topic = BY_SLUG[FIRST]
    subject_first = hooks.score_hook(
        "Si tienes diabetes, no todas las frutas afectan igual a tu glucosa.", topic
    )
    generic = hooks.score_hook(
        "Estas son cinco ideas sencillas para el dia a dia.", topic
    )
    problem_first = hooks.score_hook(
        "Si tienes diabetes y te preocupa que la fruta te dispare la glucosa, "
        "escucha esto.", topic
    )
    assert not subject_first.rejected
    assert subject_first.total < hooks.HOOK_PASS
    assert generic.total < hooks.HOOK_PASS
    assert problem_first.total > generic.total
    assert problem_first.total > subject_first.total


def test_between_eight_and_twelve_candidates_are_generated_and_one_is_chosen():
    for topic in TOPICS:
        candidates = hooks.generate(topic)
        assert hooks.MIN_CANDIDATES <= len(candidates) <= hooks.MAX_CANDIDATES, (
            topic.slug, len(candidates)
        )
        choice = hooks.choose(topic)
        assert choice.hook in candidates
        assert choice.strength >= hooks.HOOK_PASS, topic.slug


def test_the_hook_must_be_about_what_the_reel_delivers():
    """The failure a "pick the strongest candidate" rule makes *more* likely:
    the best-sounding line is often the one that drifts furthest."""

    topic = BY_SLUG[FIRST]
    drifted = hooks.alignment(
        "Si duermes mal, tu descanso puede empeorar bastante.", topic
    )
    on_topic = hooks.alignment(
        "Si tienes diabetes, no todas las frutas afectan igual a tu glucosa.", topic
    )
    assert on_topic > drifted


def test_the_hook_is_not_the_conclusion_said_twice():
    from vidfactory.reels.script import _shared_run

    for topic in TOPICS:
        script = fitted(topic, 45)
        assert _shared_run(script.hook.hook, topic.takeaway_line) < 5, topic.slug


# ---------------------------------------------------------------------------
# The shape of a reel
# ---------------------------------------------------------------------------

def test_the_six_beats_arrive_in_order():
    script = build(BY_SLUG[FIRST], target_seconds=45)
    kinds = [b.kind for b in script.beats]
    assert kinds[0] == "hook"
    assert kinds[1] == "answer"
    assert kinds[-1] == "cta"
    assert kinds[-2] == "takeaway"
    assert "item" in kinds


def test_the_answer_is_an_answer_and_not_a_trailer_for_one():
    """The third second carries the reel's point, not a description of it."""

    for topic in TOPICS:
        answer = fitted(topic, 45).beats[1]
        assert answer.kind == "answer"
        flat = answer.text.lower()
        for trailer in ("en este video", "en este reel", "te voy a contar",
                        "vamos a ver", "hoy hablamos"):
            assert trailer not in flat, (topic.slug, answer.text)


def test_every_item_says_why_it_is_true():
    """The reason is no longer the first thing the duration trim throws away."""

    for topic in TOPICS:
        script = fitted(topic, 45)
        assert script.items_without_a_reason == [], topic.slug


def test_a_number_in_the_title_is_delivered():
    """"5 frutas" that ships four has a false line burned into every frame."""

    for topic in TOPICS:
        promised = topic.required_item_count
        if not promised:
            continue
        script = fitted(topic, 45)
        assert len(script.item_beats) == promised, topic.slug


def test_an_impossible_count_raises_rather_than_shipping_a_short_list():
    topic = BY_SLUG["frutas-impacto-moderado"]
    assert topic.required_item_count == 5
    # The strict builder, not the fitting one: build_fitted answers this by
    # rendering longer, which is the pipeline's job and is tested below.
    with pytest.raises(ValueError, match="promises 5 items"):
        build(topic, target_seconds=20)


def test_the_duration_grows_rather_than_the_promise_shrinking():
    """A five item title at a slow rate is a longer reel, not a shorter list."""

    topic = BY_SLUG["errores-comer-fruta"]
    script, seconds = build_fitted(topic, target_seconds=45)
    assert len(script.item_beats) == topic.required_item_count
    assert seconds in ALLOWED_SECONDS and seconds > 45


def test_an_answer_that_names_every_item_is_a_promise_too():
    """"Granola, barritas, salsas, zumos envasados y lacteos de sabores"
    commits the reel to five things as surely as a title that says five."""

    topic = BY_SLUG["azucar-oculto"]
    assert topic.promises_all_items
    assert topic.required_item_count == len(topic.items)
    script, _seconds = build_fitted(topic, target_seconds=45)
    assert len(script.item_beats) == len(topic.items)


def test_dos_personas_in_a_title_is_not_an_item_count():
    """The count is a promise of a list, not any number in the sentence."""

    assert BY_SLUG["respuesta-individual"].required_item_count == 0


def test_the_cta_is_one_of_the_allowed_variations():
    for topic in TOPICS:
        assert fitted(topic, 45).cta in CTA_VARIANTS


def test_the_cta_never_asks_for_a_purchase():
    for variant in CTA_VARIANTS:
        flat = variant.lower()
        for word in ("compra", "compre", "vende", "link", "enlace", "descuento"):
            assert word not in flat


@pytest.mark.parametrize("seconds", ALLOWED_SECONDS)
def test_the_duration_request_is_honoured_or_the_content_wins(seconds):
    """A shorter reel drops whole items; it never drops the reason inside one,
    and it never ends up empty.

    A topic whose title promises a count is the exception and raises instead,
    because there is no honest short version of "5 frutas" - see
    :func:`test_an_impossible_count_raises_rather_than_shipping_a_short_list`.
    """

    topic = next(t for t in TOPICS if not t.required_item_count)
    script = fitted(topic, seconds)
    assert script.item_beats, seconds
    assert script.cta
    assert script.items_without_a_reason == []
    for beat in script.item_beats:
        assert len(beat.text.split()) >= 8


def test_items_are_dropped_before_their_reasons_are():
    """The reverse of the rule this started with, and deliberately.

    The first version paid for the duration by stripping the "why" off the
    items, which is how five assertions with nothing behind them came to be a
    reel. An item the viewer cannot act on is not shorter value, so the
    budget now buys fewer items and every survivor keeps its reason.
    """

    topic = next(t for t in TOPICS if not t.required_item_count and len(t.items) >= 4)
    long_reel = fitted(topic, 60)
    short_reel = fitted(topic, 30)
    assert len(long_reel.item_beats) > len(short_reel.item_beats)
    assert long_reel.word_count > short_reel.word_count
    assert long_reel.items_without_a_reason == []
    assert short_reel.items_without_a_reason == []


def test_retention_lines_are_used_sparingly_and_never_twice():
    for topic in TOPICS:
        script = fitted(topic, 60)
        lines = [b.text for b in script.beats if b.kind == "retention"]
        assert len(lines) <= 2, topic.slug
        assert len(set(lines)) == len(lines), topic.slug


def test_every_beat_carries_its_own_picture():
    """"Si dice fresas, quiero ver fresas" is decided here: the shot planner
    downstream can only choose from what each beat asked to be searched."""

    script = build(BY_SLUG[FIRST], target_seconds=45)
    for beat in script.item_beats:
        assert beat.query and beat.search_text
    queries = [b.query for b in script.item_beats]
    assert len(set(queries)) == len(queries)


def test_the_reel_always_carries_a_caveat():
    """Quantity, preparation, combination or individual variation. Almost
    every statement in this niche is only correct with one attached."""

    for topic in TOPICS:
        script = fitted(topic, 45)
        assert safety.mentions_caveat(script.narration), topic.slug


def test_all_six_content_formats_exist_and_are_used():
    used = {t.format for t in TOPICS}
    assert set(FORMATS) == used


def test_a_topic_can_be_found_by_title_or_slug():
    assert find_topic(FIRST).slug == FIRST
    assert find_topic(
        "5 frutas que suelen tener un impacto mas moderado en la glucosa"
    ).slug == FIRST


# ---------------------------------------------------------------------------
# The vertical frame
# ---------------------------------------------------------------------------

def test_the_frame_is_nine_by_sixteen():
    assert (REEL_WIDTH, REEL_HEIGHT) == (1080, 1920)
    assert REEL_HEIGHT / REEL_WIDTH == pytest.approx(16 / 9, abs=0.01)


def test_the_title_is_top_aligned():
    """Field 18 is Alignment. The first version wrote into field 19 - MarginL
    - so the title rendered at the bottom of the frame, on top of the
    captions, and every check that read the .ass file said it was fine."""

    from vidfactory.reels.captions import _title_style

    parts = _title_style("DejaVu Sans").split(",")
    assert parts[18] == "8"


def test_captions_and_title_stay_out_of_the_platform_furniture():
    report = safe_area_report([])
    assert report["caption_clears_platform_ui"]
    assert report["title_clears_status_bar"]
    assert report["title_and_captions_do_not_overlap"]
    assert REEL_CAPTIONS.margin_v > BOTTOM_UNSAFE
    assert REEL_TITLE.margin_v > TOP_UNSAFE


def test_reel_captions_are_bigger_and_shorter_than_long_form():
    from vidfactory.ass_subtitles import PREMIUM

    assert REEL_CAPTIONS.font_size > PREMIUM.font_size
    assert REEL_CAPTIONS.max_words < PREMIUM.max_words
    assert REEL_CAPTIONS.margin_v > PREMIUM.margin_v


def test_the_burned_in_title_carries_no_emoji():
    """The first real render put a missing-glyph box where the strawberry
    should have been. Inter, Montserrat and DejaVu carry no emoji, and libass
    does not fall back to a colour-emoji font the way a browser does - so a
    tofu box sat in the one element that is on screen for the whole reel.

    The emoji stays in the topic and in the caption, where the platform draws
    it natively.
    """

    from vidfactory.reels.captions import strip_emoji, title_renders

    assert strip_emoji("FRUTAS Y GLUCOSA 🍓") == "FRUTAS Y GLUCOSA"
    assert strip_emoji("CUIDADO CON ESTAS FRUTAS ⚠️") == "CUIDADO CON ESTAS FRUTAS"
    assert not title_renders("FRUTAS Y GLUCOSA 🍓")
    assert title_renders("DESAYUNOS Y GLUCOSA")
    for topic in TOPICS:
        assert "\U0001F300" not in accented(topic.top_title, topic.accent)
    assert "🍓" not in accented("FRUTAS Y GLUCOSA 🍓", "GLUCOSA")


def test_the_emoji_survives_where_it_can_be_drawn():
    """Only the burned-in title loses it."""

    emoji_topics = [t for t in TOPICS if not title_renders(t.top_title)]
    assert emoji_topics, "no topic uses an emoji, so this test proves nothing"
    script = build(emoji_topics[0], target_seconds=45)
    assert any(ord(c) > 0x1F000 for c in script.top_title)


def test_one_word_of_the_title_takes_the_accent_colour():
    marked = accented("FRUTAS Y GLUCOSA", "GLUCOSA")
    assert REEL_TITLE.accent in marked
    assert marked.count(REEL_TITLE.accent) == 1


def test_the_title_spans_the_whole_reel(tmp_path):
    from vidfactory.tts import NarrationChunk

    chunks = [NarrationChunk(text="Las fresas aportan fibra.", start=0.0, end=4.0)]
    path, events, _font = write_reel_ass(
        chunks, tmp_path / "s.ass", "FRUTAS Y GLUCOSA", "GLUCOSA", 41.5
    )
    body = path.read_text(encoding="utf-8")
    assert "PlayResX: 1080" in body and "PlayResY: 1920" in body
    title_lines = [l for l in body.splitlines() if ",ReelTitle,," in l]
    assert len(title_lines) == 1
    assert title_lines[0].startswith("Dialogue: 0,0:00:00.00,0:00:41.50,")


def test_caption_lines_fit_the_narrower_frame(tmp_path):
    """22 characters at 76px ran off both edges of a 1080 frame. Caught by
    looking at a rendered frame; pinned here so it stays caught."""

    from vidfactory.tts import NarrationChunk

    chunks = [
        NarrationChunk(
            text=(
                "Las fresas suelen aportar menos carbohidratos por racion que "
                "muchas otras frutas."
            ),
            start=0.0,
            end=8.0,
        )
    ]
    _path, events, _font = write_reel_ass(
        chunks, tmp_path / "s.ass", "FRUTAS", "FRUTAS", 8.0
    )
    for event in events:
        for line in event.text.split("\\N"):
            assert len(line) <= 26, line
        assert len(event.text.split("\\N")) <= 2


# ---------------------------------------------------------------------------
# Quality control
# ---------------------------------------------------------------------------

def _report(topic_slug: str = FIRST, seconds: float = 45.0):
    script = build(BY_SLUG[topic_slug], target_seconds=seconds)
    return script, build_report(
        script,
        actual_seconds=script.estimated_seconds,
        cta_start=max(0.0, script.estimated_seconds - 4.0),
        audio_seconds=script.estimated_seconds,
        sources=bibliography(script.source_keys),
    )


def test_the_seven_metrics_the_brief_names_are_all_reported():
    _script, report = _report()
    for name in (
        "hook_strength_score",
        "hook_content_alignment",
        "medical_claim_risk_count",
        "unsupported_claim_count",
        "value_density_score",
        "cta_present",
        "cta_position_ok",
    ):
        assert name in report.metrics, name


def test_production_requires_zero_risk_and_zero_unsupported():
    for topic in TOPICS:
        script = fitted(topic, 45)
        report = build_report(
            script,
            production=True,
            actual_seconds=script.estimated_seconds,
            cta_start=max(0.0, script.estimated_seconds - 4.0),
            audio_seconds=script.estimated_seconds,
            sources=bibliography(script.source_keys),
        )
        assert report.metrics["medical_claim_risk_count"] == 0, topic.slug
        assert report.metrics["unsupported_claim_count"] == 0, topic.slug
        assert report.passed, (topic.slug, [c.name for c in report.failures])


def test_a_cta_in_the_middle_of_the_reel_fails():
    script, _ = _report()
    report = build_report(
        script, actual_seconds=45.0, cta_start=12.0, audio_seconds=45.0,
        sources=bibliography(script.source_keys),
    )
    assert not report.metrics["cta_position_ok"]
    assert "cta_in_the_last_seconds" in [c.name for c in report.failures]


def test_an_empty_endorsement_is_not_a_value_beat():
    """The brief's own pair of examples."""

    assert not explains_something("Las fresas son muy buenas.")
    assert explains_something(
        "Las fresas aportan fibra y suelen contener menos carbohidratos por racion."
    )


def test_value_density_counts_filler_against_the_reel():
    script, report = _report()
    assert 0.0 < report.metrics["value_density_score"] <= 1.0
    assert value_density(script) == report.metrics["value_density_score"]


def test_a_reel_with_no_source_is_refused():
    script, _ = _report()
    report = build_report(script, actual_seconds=45.0, cta_start=41.0, sources=())
    assert "sources_recorded" in [c.name for c in report.failures]


# ---------------------------------------------------------------------------
# What gets published
# ---------------------------------------------------------------------------

def test_the_caption_carries_the_sources_and_the_disclaimer():
    script = build(BY_SLUG[FIRST], target_seconds=45)
    body = caption(script, bibliography(script.source_keys))
    assert script.hook.hook in body
    assert script.cta in body
    assert DISCLAIMER in body
    assert "https://" in body
    assert body.strip().endswith(hashtags(script)[-1])


def test_hashtags_are_deduplicated_and_bounded():
    for topic in TOPICS:
        script = fitted(topic, 45)
        tags = hashtags(script)
        assert len(tags) == len(set(t.lower() for t in tags))
        assert 1 <= len(tags) <= 12
        assert all(t.startswith("#") for t in tags)


# ---------------------------------------------------------------------------
# The separation
# ---------------------------------------------------------------------------

def test_the_long_form_pipeline_does_not_import_the_reels_package():
    """The whole point of a second product in one repo: it can be wrong
    without the first one noticing."""

    import ast
    import pathlib

    # Imports, read from the syntax tree rather than grepped for the word.
    # The string search also fired on prose - entities.py explains that its
    # scorer is shared with reels.foods, which is documentation of the very
    # separation this test defends, not a violation of it.
    root = pathlib.Path(__file__).resolve().parents[1] / "src" / "vidfactory"
    for path in root.glob("*.py"):
        if path.name == "main.py":
            # The CLI dispatches to both, inside the command function.
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert "reels" not in alias.name.split("."), (path.name, alias.name)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                assert "reels" not in module.split("."), (path.name, module)


def test_the_reels_package_reuses_rather_than_reimplements():
    """It should be importing the shared machinery, not copying it.

    Across the package rather than out of one file: the reel reaches Piper
    through reels/voice.py now, which is still reuse - voice.py's whole job
    is to try Kokoro and hand back what vidfactory.tts already builds when it
    cannot. Asserting on pipeline.py alone would call that a regression.
    """

    import pathlib

    package = pathlib.Path(__file__).resolve().parents[1] / "src" / "vidfactory" / "reels"
    body = "\n".join(p.read_text(encoding="utf-8") for p in package.glob("*.py"))
    for shared in ("..downloader", "..editor", "..ranking", "..tts",
                   "..stock.registry", "..subtitles"):
        assert shared in body, shared


# ---------------------------------------------------------------------------
# The voice: delivery, and what it ships under
# ---------------------------------------------------------------------------

class _RecordingEngine:
    """A TTS engine that writes silence and remembers how it was asked to."""

    name = "recording"
    voice = "test"
    speech_rate_wpm = 170.0

    def __init__(self):
        self.calls = []

    def synthesize(self, text, destination, speed: float = 1.0):
        from vidfactory.ffmpeg_utils import make_silence

        self.calls.append((text, speed))
        make_silence(destination, max(0.2, len(text.split()) / 3.0), 48000)
        return destination


class _OnePaceEngine:
    """The other kind: no speed argument at all."""

    name = "onepace"
    voice = "test"

    def __init__(self):
        self.calls = []

    def synthesize(self, text, destination):
        from vidfactory.ffmpeg_utils import make_silence

        self.calls.append(text)
        make_silence(destination, max(0.2, len(text.split()) / 3.0), 48000)
        return destination


def test_every_beat_kind_the_builder_emits_has_a_delivery(tmp_path):
    """A beat with no entry in the tables is read at the default pace, which
    is the bug that would make a new beat kind silently sound wrong."""

    from vidfactory.reels import narration as narration_module

    kinds = {b.kind for topic in TOPICS for b in fitted(topic, 45).beats}
    assert kinds <= set(narration_module.BEAT_SPEED), kinds
    assert kinds <= set(narration_module.BEAT_PAUSE), kinds


@pytest.mark.integration
def test_the_reel_is_not_read_at_one_pace(tmp_path):
    from vidfactory.reels.narration import BEAT_SPEED, narrate

    script = build(BY_SLUG[FIRST], target_seconds=45)
    engine = _RecordingEngine()
    result = narrate(
        script.beats, engine, workdir=tmp_path / "w", destination=tmp_path / "n.wav"
    )
    speeds = {speed for _text, speed in engine.calls}
    assert len(speeds) > 1, speeds
    # The takeaway is the line to remember, so it is the slowest thing said.
    assert BEAT_SPEED["takeaway"] == min(BEAT_SPEED.values())
    assert result.duration > 0
    assert len(result.scene_timings) == len(script.beats)


@pytest.mark.integration
def test_an_engine_without_a_speed_argument_still_works(tmp_path):
    """Piper takes one; eSpeak does not. Neither may break the reel."""

    from vidfactory.reels.narration import narrate

    script = build(BY_SLUG[FIRST], target_seconds=45)
    engine = _OnePaceEngine()
    result = narrate(
        script.beats, engine, workdir=tmp_path / "w", destination=tmp_path / "n.wav"
    )
    assert len(engine.calls) >= len(script.beats)
    assert result.duration > 0


def test_an_explicit_engine_request_is_not_silently_downgraded(monkeypatch):
    """The A/B comparison is worthless if "piper" can quietly mean Kokoro."""

    from vidfactory.reels import voice as voice_module

    seen = {}

    def fake_build_engine(engine, voice, speed, sample_rate, language, **kw):
        seen["engine"] = engine
        return _RecordingEngine()

    monkeypatch.setattr(voice_module, "build_engine", fake_build_engine)
    voice_module.build_reel_engine(engine="piper", language="es")
    assert seen["engine"] == "piper"


def test_the_licence_of_the_voice_that_spoke_is_reachable_from_its_name():
    from vidfactory.reels.voice import licence_report

    report = licence_report()
    assert report["kokoro"]["model"] == "hexgrad/Kokoro-82M"
    assert report["kokoro"]["model_licence"] == "Apache-2.0"
    # The Piper runtime and the Piper voices are separate artefacts with
    # separate terms, and the voice is the one that ends up in the video.
    assert report["piper"]["voice_licences"]["es_ES-sharvard-medium"] == "MIT"


def test_piper_is_still_here():
    """Kokoro is the default; Piper is the fallback and stays in the project."""

    from vidfactory import tts
    from vidfactory.reels.voice import build_reel_engine

    assert hasattr(tts, "PiperEngine")
    assert "piper" in build_reel_engine.__doc__.lower()


# ---------------------------------------------------------------------------
# Shot-to-item grounding: the apple beat may not show an orange
# ---------------------------------------------------------------------------

def test_a_beat_naming_one_food_requires_that_food():
    from vidfactory.reels.foods import required_food

    assert required_food("Las fresas suelen aportar menos carbohidratos").name == "fresas"
    assert required_food(
        "La manzana con piel conserva la fibra y suele absorberse mas despacio "
        "que en zumo.", "manzana"
    ).name == "manzana"


def test_a_beat_naming_several_foods_requires_none():
    """The answer beat lists five fruits, and the right picture for a list is
    the mixed bowl that demanding any single one of them would reject."""

    from vidfactory.reels.foods import required_food

    assert required_food(
        "Fresas, frambuesas, kiwi, manzana con piel y aguacate, en raciones normales."
    ) is None


def test_the_item_key_decides_when_the_sentence_names_two():
    """"Cambiar la fruta entera por zumo" names both and is about the juice."""

    from vidfactory.reels.foods import required_food

    assert required_food(
        "Cambiar la fruta entera por zumo le quita la fibra", "zumo_por_fruta"
    ).name == "zumo"


def test_abstract_advice_requires_no_food():
    from vidfactory.reels.foods import required_food_for
    from vidfactory.reels.script import Beat

    for text, key in (
        ("En la etiqueta mira carbohidratos, de los cuales azucares, y fibra", "etiqueta"),
        ("Pesa una vez tu racion habitual", "pesar_una_vez"),
    ):
        assert required_food_for(Beat("item", text, item_key=key)) is None


def test_only_item_beats_require_a_food():
    """The hook, the answer, the takeaway and the CTA are about the reel."""

    from vidfactory.reels.foods import required_food_for
    from vidfactory.reels.script import Beat

    for kind in ("hook", "answer", "takeaway", "cta", "retention", "lead"):
        assert required_food_for(Beat(kind, "Las fresas aportan fibra")) is None


def test_every_mapped_item_key_names_a_real_food():
    from vidfactory.reels.foods import BY_NAME, ITEM_FOOD
    from vidfactory.reels.knowledge import TOPICS

    known = {item.key for topic in TOPICS for item in topic.items}
    for key, food in ITEM_FOOD.items():
        assert food in BY_NAME, (key, food)
        assert key in known, key


def test_the_apple_beat_rejects_orange_footage():
    """The exact failure the last render shipped, as a scoring question.

    Frames that look like an orange and not like an apple must fail the
    manzana beat. Built from similarities rather than pixels so the test needs
    no model: what it pins is the verdict, which is what shipped the orange.
    """

    from vidfactory.reels.foods import BY_NAME, score_food
    from vidfactory.visual_analysis import _ramp

    apple = BY_NAME["manzana"]
    positives = len(apple.positives)
    # An orange owns the frame: every competitor prompt beats every positive.
    orange_frames = [
        [0.18] * positives + [0.34] + [0.20] * (len(apple.competitors) - 1)
        for _ in range(3)
    ]
    verdict = score_food(apple, orange_frames, _ramp)
    assert verdict.checked
    assert not verdict.passed, verdict.detail
    assert verdict.top_distractor == "an orange"

    # Real apple footage: the positives lead and nothing displaces them.
    apple_frames = [
        [0.31] * positives + [0.19] * len(apple.competitors) for _ in range(3)
    ]
    kept = score_food(apple, apple_frames, _ramp)
    assert kept.checked and kept.passed, kept.detail


def test_the_inspector_maps_a_frame_to_the_beat_it_lands_in():
    """The manzana frame was reported as the fresas line.

    kind -> first beat of that kind is the bug; timestamp against the beat's
    own span is the fix, and this is the exact timestamp from run 34093462658.
    """

    import importlib.util
    import pathlib

    tool = pathlib.Path(__file__).resolve().parents[1] / "tools" / "inspect_reel_frames.py"
    spec = importlib.util.spec_from_file_location("inspect_reel_frames", tool)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    beats = [
        {"kind": "hook", "text": "Si te preocupa...", "start": 0.0, "end": 4.5},
        {"kind": "answer", "text": "Fresas, frambuesas...", "start": 4.5, "end": 8.3},
        {"kind": "item", "item_key": "fresas", "text": "Las fresas...",
         "start": 8.3, "end": 14.0},
        {"kind": "item", "item_key": "manzana", "text": "La manzana con piel...",
         "start": 26.0, "end": 32.0},
    ]
    position, beat = module.beat_at(beats, 27.9)
    assert position == 3 and beat["item_key"] == "manzana"

    grounding = {"beat-03": {
        "beat": "beat-03", "item": "manzana", "required_entity": "manzana",
        "sources": ["pexels:99"], "score": 0.21, "passed": False,
        "looked_like": "an orange",
    }}
    line = module.describe(position, beat, grounding)
    assert "manzana" in line and "an orange" in line and "FAIL" in line
    assert "fresas" not in line


def test_a_frozen_tail_is_reported_and_gated():
    from vidfactory.reels.qc import FROZEN_TAIL_LIMIT, build_report

    script = fitted(BY_SLUG[FIRST], 45)
    report = build_report(
        script, production=True, sources=[{"key": "x"}],
        cta_start=script.estimated_seconds - 3,
        visual={"frozen_tail_duration": 1.7},
    )
    assert report.metrics["frozen_tail_duration"] == 1.7
    assert "the_cta_is_not_a_frozen_frame" in [c.name for c in report.failures]
    assert FROZEN_TAIL_LIMIT <= 0.2


def test_production_fails_on_a_wrong_food_and_test_only_warns():
    from vidfactory.reels.qc import build_report

    script = fitted(BY_SLUG[FIRST], 45)
    wrong = {"item_grounding_results": [{
        "beat": "beat-05", "item": "manzana", "required_entity": "manzana",
        "checked": True, "passed": False, "score": 0.2, "looked_like": "an orange",
    }]}
    kwargs = dict(sources=[{"key": "x"}], cta_start=script.estimated_seconds - 3)

    strict = build_report(script, production=True, visual=dict(wrong), **kwargs)
    assert strict.metrics["entity_grounding_failure_count"] == 1
    assert strict.metrics["entity_grounding_pass_percentage"] == 0.0
    assert "every_item_shows_its_food" in [c.name for c in strict.failures]

    loose = build_report(script, production=False, visual=dict(wrong), **kwargs)
    assert "every_item_shows_its_food" in [c.name for c in loose.warnings]


# ---------------------------------------------------------------------------
# Spanish orthography
# ---------------------------------------------------------------------------

def test_the_narration_is_written_in_correct_spanish():
    """Accents reach the voice and the burned-in captions.

    Kokoro is given the script verbatim, and "racion" and "ración" are not
    the same word to a Spanish G2P front end. The four the brief names are
    asserted by hand; the sweep below catches the rest.
    """

    script = fitted(BY_SLUG[FIRST], 45)
    spoken = script.narration
    for word in ("ración", "más", "proteína", "síguenos", "día", "última", "así"):
        assert word in spoken, word


def test_no_reel_text_is_missing_its_accents():
    """The accentless spellings must not come back."""

    import re

    wrong = (
        "racion", "azucar", "siguenos", "ultima", "proteina", "despues",
        "mas rapido", "manana", "tambien", "pequena", "pequeno", "punado",
        "dia:", "asi que", "segun", "opcion", "digestion", "platano",
    )
    for topic in TOPICS:
        script = fitted(topic, 45)
        flat = script.narration.lower()
        for token in wrong:
            assert not re.search(rf"\b{re.escape(token)}\b", flat), (topic.slug, token)


def test_the_provider_queries_stay_english():
    """Rule 8: a Spanish string must never reach a stock provider."""

    import re

    for topic in TOPICS:
        for field in (topic.opening_query, topic.opening_search_text):
            assert not re.search(r"[áéíóúñ]", field), (topic.slug, field)
        for item in topic.items:
            assert not re.search(r"[áéíóúñ]", item.query + item.search_text), item.key


def test_the_medical_checks_still_see_accented_spanish():
    """A safety layer that stops matching when a word is spelled correctly is
    not a safety layer. The vocabularies are accentless; the scripts are not."""

    assert [r.code for r in safety.find_risks("El azúcar cura la diabetes.")] == ["cure"]
    assert [r.code for r in safety.find_risks("La fruta baja el azúcar en sangre.")] == [
        "unhedged"
    ]
    assert safety.find_risks("La fruta suele bajar el azúcar en sangre.") == []


def test_the_identification_probe_names_the_food_that_won():
    """Which fruit is this, not how displaced is it.

    The dominance probe the interiors use was measured at chance on food: over
    28 correct and 28 wrong clips, kept% and rejected% summed to ~100 at every
    cut, and manzana came back *inverted* - real apple footage at a median of
    0.131 against orange footage at 0.508. Apple, orange and pear are mutually
    exclusive in a way a wall and a sofa are not, so the answerable question
    is plain identification.
    """

    from vidfactory.reels.foods import BY_NAME, identify_food

    apple = BY_NAME["manzana"]
    positives = len(apple.positives)

    orange = [[0.18] * positives + [0.34] + [0.20] * (len(apple.competitors) - 1)] * 3
    verdict = identify_food(apple, orange)
    assert verdict.checked and not verdict.passed
    assert verdict.score == 0.0
    assert verdict.top_distractor == "an orange"

    good = [[0.31] * positives + [0.19] * len(apple.competitors)] * 3
    assert identify_food(apple, good).passed
    assert identify_food(apple, good).score == 1.0


def test_a_mostly_right_clip_still_passes():
    """One frame where the camera has panned off the fruit is not a failure."""

    from vidfactory.reels.foods import FOOD_IDENTIFY_PASS, BY_NAME, identify_food

    kiwi = BY_NAME["kiwi"]
    positives = len(kiwi.positives)
    right = [0.30] * positives + [0.19] * len(kiwi.competitors)
    wrong = [0.18] * positives + [0.33] + [0.20] * (len(kiwi.competitors) - 1)
    verdict = identify_food(kiwi, [right, right, wrong])
    assert verdict.score == pytest.approx(2 / 3, abs=0.01)
    assert verdict.passed is (2 / 3 >= FOOD_IDENTIFY_PASS)


def test_the_shot_plan_covers_the_pauses_between_beats():
    """The picture is continuous; the narration is not.

    A beat's timing spans only its own spoken chunks, so the pause that
    follows it belongs to no beat and a plan built from the spans is short by
    every pause in the reel. That is where run 34100918235's 1.52s of frozen
    frame came from - not from the tail, which had already been extended.
    Each beat's picture must run to the *next* beat's first word.
    """

    from vidfactory.reels.narration import BEAT_PAUSE, SENTENCE_PAUSE
    from vidfactory.reels.pipeline import TAIL_SECONDS

    script = fitted(BY_SLUG[FIRST], 45)
    spans, clock = [], 0.0
    for beat in script.beats:
        span = max(0.6, beat.word_count / 2.62)
        spans.append((clock, clock + span))
        clock += span + SENTENCE_PAUSE + BEAT_PAUSE.get(beat.kind, 0.12)
    timeline_end = clock + TAIL_SECONDS
    starts = [s for s, _e in spans]

    naive = sum(end - start for start, end in spans)
    assert timeline_end - naive > 1.0, "the pauses should add up to a real gap"

    covered = 0.0
    for index, (start, end) in enumerate(spans):
        last = index == len(spans) - 1
        covered += (timeline_end if last else max(end, starts[index + 1])) - start
    assert covered == pytest.approx(timeline_end, abs=0.01)


# ---------------------------------------------------------------------------
# Entity + state + context: the shot has to be the right *picture*, not only
# the right noun. Three renders shipped an apple cake, a peeled apple, a dog
# and a coconut, and every one of them scores the food at 1.00.
# ---------------------------------------------------------------------------

def _matrix(requirement, wins: dict, frames: int = 3):
    """Similarities where the named prompt indexes lead and nothing else does.

    Built from numbers rather than pixels so the test needs no model: what is
    being pinned is the verdict, and the verdict is what shipped the cake.
    """

    from vidfactory.reels.foods import requirement_prompts

    prompts, _ = requirement_prompts(requirement)
    return [[wins.get(i, 0.10) for i in range(len(prompts))] for _ in range(frames)]


def test_an_apple_cake_is_not_an_apple_beat():
    """The brief's own example: apple = 1.00, state = fail, FINAL = REJECT."""

    from vidfactory.reels.foods import (
        REQUIREMENTS, requirement_prompts, score_requirement,
    )

    apple = REQUIREMENTS["manzana"]
    _prompts, offset = requirement_prompts(apple)
    cake = offset["state"] + len(apple.required_attributes) + 1
    assert "pastry" in apple.forbidden_attributes[1]

    verdict = score_requirement(apple, _matrix(apple, {0: 0.9, cake: 0.9,
                                                       offset["context"]: 0.9}))
    assert verdict.checked
    # The entity probe is right and it is not enough. That is the whole layer.
    assert verdict.entity_presence_score == 1.0
    assert verdict.state_match_score == 0.0
    assert not verdict.passed
    assert verdict.failed_on == ("state",)
    assert "pastry" in verdict.top_distractor
    # A conjunction, not an average: a perfect food score may not buy a pass.
    assert verdict.score == 0.0


def test_a_peeled_apple_fails_a_beat_that_says_con_piel():
    from vidfactory.reels.foods import (
        REQUIREMENTS, requirement_prompts, score_requirement,
    )

    apple = REQUIREMENTS["manzana"]
    _prompts, offset = requirement_prompts(apple)
    peeled = offset["state"] + len(apple.required_attributes)
    # The benchmark's wording: the cut flesh, not the absent skin.
    assert apple.forbidden_attributes[0] == "pale wet apple flesh being cut"

    verdict = score_requirement(apple, _matrix(apple, {0: 0.9, peeled: 0.9,
                                                       offset["context"]: 0.9}))
    assert not verdict.passed and verdict.failed_on == ("state",)


def test_a_dog_owning_the_frame_fails_the_strawberry_beat():
    """Strawberries visible, dog dominant. The brief rejects it; so does this."""

    from vidfactory.reels.foods import (
        REQUIREMENTS, requirement_prompts, score_requirement,
    )

    fresas = REQUIREMENTS["fresas"]
    _prompts, offset = requirement_prompts(fresas)
    verdict = score_requirement(fresas, _matrix(fresas, {
        0: 0.40,                       # the strawberries are there
        offset["state"]: 0.9,          # and they are raw
        offset["context"]: 0.9,        # in a kitchen
        offset["dominant"]: 0.95,      # and the dog is bigger than all of it
    }))
    assert not verdict.passed
    assert verdict.failed_on == ("dominant_subject",)
    assert verdict.top_distractor == "a dog"
    assert verdict.dominant_subject_score == 0.0
    assert verdict.distractor_dominance_score == 1.0


def test_a_coconut_fails_the_kiwi_beat():
    from vidfactory.reels.foods import (
        REQUIREMENTS, requirement_prompts, score_requirement,
    )

    kiwi = REQUIREMENTS["kiwi"]
    _prompts, offset = requirement_prompts(kiwi)
    coconut = offset["dominant"] + kiwi.forbidden_dominant_entities.index("a coconut")
    verdict = score_requirement(kiwi, _matrix(kiwi, {
        0: 0.40, offset["state"]: 0.9, offset["context"]: 0.9, coconut: 0.95,
    }))
    assert not verdict.passed and verdict.top_distractor == "a coconut"


def test_the_right_shot_passes_every_probe():
    from vidfactory.reels.foods import (
        REQUIREMENTS, requirement_prompts, score_requirement,
    )

    for name in ("manzana", "fresas", "kiwi", "aguacate", "frambuesas"):
        requirement = REQUIREMENTS[name]
        _prompts, offset = requirement_prompts(requirement)
        verdict = score_requirement(requirement, _matrix(requirement, {
            0: 0.9, offset["state"]: 0.9, offset["context"]: 0.9,
        }))
        assert verdict.passed, (name, verdict.detail)
        assert verdict.score == 1.0
        assert verdict.failed_on == ()


def test_a_food_with_no_state_written_down_is_not_gated_on_a_guess():
    """An unmeasured probe abstains. It does not pass, and it does not fail.

    Requiring a state nobody has observed going wrong would reject good
    footage for a rule written from imagination, which is what
    ``entities.py`` says about abstract advice and is true here too.
    """

    from vidfactory.reels.foods import (
        BY_NAME, requirement_for_food, requirement_prompts, score_requirement,
    )

    grapes = requirement_for_food(BY_NAME["uvas"])
    assert grapes.required_attributes == ()
    assert grapes.context_requirements == ()
    # The dominance list is not a guess about grapes - it is a list of what
    # actually turned up owning a food frame - so it still applies.
    assert "a dog" in grapes.forbidden_dominant_entities

    _prompts, offset = requirement_prompts(grapes)
    verdict = score_requirement(grapes, _matrix(grapes, {0: 0.9}))
    assert verdict.passed
    assert not verdict.state_checked and not verdict.context_checked
    assert verdict.subject_checked


def test_a_strong_entity_score_cannot_compensate_for_a_failed_state():
    """The scoring property the brief states, on every food that declares one."""

    from vidfactory.reels.foods import (
        REQUIREMENTS, requirement_prompts, score_requirement,
    )

    for name, requirement in REQUIREMENTS.items():
        if not requirement.forbidden_attributes:
            continue
        _prompts, offset = requirement_prompts(requirement)
        forbidden = offset["state"] + len(requirement.required_attributes)
        verdict = score_requirement(requirement, _matrix(requirement, {
            0: 0.99,                   # a perfect food score
            forbidden: 0.98,           # and the wrong state
            offset["context"]: 0.9,
        }))
        assert verdict.entity_presence_score == 1.0, name
        assert not verdict.passed, name
        assert verdict.score == 0.0, name


def test_the_juice_item_wants_the_glass_and_not_the_fruit():
    """The one requirement whose state is inverted.

    "Cambiar la fruta entera por zumo le quita la fibra" is a warning about
    the juice, and a bowl of oranges is the picture of the thing it warns
    against.
    """

    from vidfactory.reels.foods import (
        REQUIREMENTS, requirement_prompts, score_requirement,
    )

    zumo = REQUIREMENTS["zumo"]
    _prompts, offset = requirement_prompts(zumo)
    whole = offset["state"] + len(zumo.required_attributes)
    verdict = score_requirement(zumo, _matrix(zumo, {
        0: 0.9, whole: 0.95, offset["context"]: 0.9,
    }))
    assert not verdict.passed and "state" in verdict.failed_on


def test_the_repair_searches_the_state_before_the_food():
    """"manzana" is what found the cake, so it is not what the repair asks."""

    from vidfactory.reels.foods import REQUIREMENTS, state_repair_queries

    queries = state_repair_queries(REQUIREMENTS["manzana"])
    assert queries[0] == "whole raw red apple with skin close up"
    assert any("unpeeled" in q for q in queries)
    # The entity's own searches follow rather than disappear.
    assert "red apple close up" in queries
    # Nothing is searched twice.
    assert len(queries) == len(set(queries))
    assert "red apple close up" not in state_repair_queries(
        REQUIREMENTS["manzana"], ["red apple close up"]
    )


def test_every_requirement_names_a_food_that_exists():
    from vidfactory.reels.foods import BY_NAME, REQUIREMENTS

    for name, requirement in REQUIREMENTS.items():
        assert requirement.required_entity == name
        assert name in BY_NAME
        assert requirement.entity is BY_NAME[name]
        # Prompts are English, like every other prompt that reaches CLIP.
        for prompt in (*requirement.required_attributes,
                       *requirement.forbidden_attributes,
                       *requirement.context_requirements,
                       *requirement.forbidden_dominant_entities,
                       *requirement.queries):
            assert prompt == prompt.encode("ascii", "ignore").decode(), prompt


def test_the_five_fruits_of_the_test_reel_all_have_a_state():
    """The brief writes out five and this is the check that none was skipped."""

    from vidfactory.reels.foods import REQUIREMENTS

    for name in ("fresas", "frambuesas", "kiwi", "manzana", "aguacate"):
        requirement = REQUIREMENTS[name]
        assert requirement.required_attributes, name
        assert requirement.context_requirements, name
        assert requirement.queries, name
    # The rejections the brief lists, in the wording the benchmark chose:
    # peeled reads as cut flesh, cake and pie as pastry, juice as a drink.
    apple = REQUIREMENTS["manzana"].forbidden_attributes
    assert any("flesh being cut" in p for p in apple)
    assert any("pastry" in p for p in apple)
    assert any("drink" in p for p in apple)
    # And whole, halved and sliced avocado all have to survive, which is why
    # the avocado state no longer describes a cut at all.
    avocado = REQUIREMENTS["aguacate"]
    assert any("whole" in p for p in avocado.required_attributes)
    assert all("smoothie" not in p for p in avocado.forbidden_attributes)
    assert "a coconut" in REQUIREMENTS["kiwi"].forbidden_dominant_entities
    assert any("dog" in p for p in REQUIREMENTS["fresas"].forbidden_dominant_entities)


def test_the_shot_plan_covers_every_pause_and_the_tail():
    """The frozen frame was between the beats, not after the last one.

    A beat's ``scene_timings`` span covers only its own spoken chunks, so a
    plan summed from the spans is short by every pause in the reel: run
    34093462658 held its last frame for 1.7s and stretching only the final
    beat still left 1.52s.
    """

    from vidfactory.reels.pipeline import shot_spans

    beats = [object() for _ in range(4)]
    timings = {
        "beat-00": (0.0, 2.0), "beat-01": (2.4, 6.0),
        "beat-02": (6.3, 9.0), "beat-03": (9.4, 12.0),
    }
    spans = shot_spans(beats, timings, 12.4)
    # No gap and no overlap: the picture tiles the whole audio plus the tail.
    assert spans[0][0] == 0.0
    assert spans[-1][1] == 12.4
    for (_first, end), (start, _last) in zip(spans, spans[1:]):
        assert end == start
    assert round(sum(end - start for start, end in spans), 3) == 12.4


def test_a_beat_that_was_never_spoken_gets_no_picture():
    """``(0.0, 0.0)`` used to mean "the whole reel" rather than "nothing"."""

    from vidfactory.reels.pipeline import shot_spans

    beats = [object() for _ in range(4)]
    spans = shot_spans(beats, {"beat-00": (0.0, 2.0), "beat-02": (3.0, 5.0)}, 6.0)
    assert spans[1] == (0.0, 0.0) and spans[3] == (0.0, 0.0)
    assert spans[0] == (0.0, 3.0) and spans[2] == (3.0, 6.0)
    assert round(sum(end - start for start, end in spans), 3) == 6.0


def test_the_report_says_which_probe_refused_the_shot():
    """One failure count cannot tell an orange from an apple cake."""

    from vidfactory.reels.qc import build_report

    script = fitted(BY_SLUG[FIRST], 45)
    visual = {"item_grounding_results": [
        {"beat": "beat-05", "item": "manzana", "required_entity": "manzana",
         "checked": True, "passed": False, "score": 0.0, "failed_on": ["state"],
         "looked_like": "a slice of apple cake"},
        {"beat": "beat-07", "item": "fresas", "required_entity": "fresas",
         "checked": True, "passed": False, "score": 0.0,
         "failed_on": ["dominant_subject"], "looked_like": "a dog"},
        {"beat": "beat-09", "item": "kiwi", "required_entity": "kiwi",
         "checked": True, "passed": True, "score": 1.0, "failed_on": []},
    ]}
    report = build_report(
        script, production=True, visual=visual, sources=[{"key": "x"}],
        cta_start=script.estimated_seconds - 3,
    )
    assert report.metrics["entity_grounding_failure_count"] == 2
    assert report.metrics["wrong_state_failure_count"] == 1
    assert report.metrics["distractor_dominance_failure_count"] == 1
    assert report.metrics["wrong_food_failure_count"] == 0
    assert report.metrics["entity_grounding_pass_percentage"] == 33.3
    detail = [c for c in report.checks if c.name == "every_item_shows_its_food"][0]
    assert "state" in detail.detail and "apple cake" in detail.detail


def test_the_inspector_prints_the_four_probes():
    import importlib.util
    import pathlib

    tool = pathlib.Path(__file__).resolve().parents[1] / "tools" / "inspect_reel_frames.py"
    spec = importlib.util.spec_from_file_location("inspect_reel_frames", tool)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    row = {
        "beat": "beat-05", "required_entity": "manzana", "sources": ["pexels:1"],
        "score": 0.0, "passed": False, "entity_presence_score": 1.0,
        "state_match_score": 0.0, "state_checked": True,
        "context_match_score": 1.0, "context_checked": True,
        "dominant_subject_score": 1.0, "failed_on": ["state"],
        "looked_like": "a slice of apple cake",
        "required_attributes": ["a fresh raw apple with its skin on"],
    }
    line = module.describe(
        5, {"kind": "item", "text": "La manzana con piel..."}, {"beat-05": row}
    )
    assert "entity=1.00" in line and "state=0.00" in line
    assert "FAILED ON state" in line and "apple cake" in line


# ---------------------------------------------------------------------------
# A still that demonstrates the claim beats a video that does not.
# ---------------------------------------------------------------------------

def test_a_photograph_renders_as_a_shot_and_not_a_freeze():
    """A still has no timeline to seek into; it is looped and crawled across.

    Everything after the input is identical to a video shot, which is what
    lets the concat demuxer stream-copy a photograph and a clip into one
    track. Rendered rather than asserted about, because the argument order
    around ``-loop 1`` is exactly the kind of thing that is right in a
    comment and wrong in the command.
    """

    import subprocess

    from vidfactory.editor import Shot, VideoEditor
    from vidfactory.ffmpeg_utils import probe_media

    work = Path(tempfile.mkdtemp(prefix="reel-still-"))
    image = work / "apple.png"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "lavfi",
         "-i", "testsrc=size=540x960:duration=1:rate=1", "-frames:v", "1", str(image)],
        check=True,
    )
    editor = VideoEditor(workdir=work, width=540, height=960, fps=24)
    shot = Shot(source=image, start=0.0, duration=2.5, motion="zoom_in",
                still=True, scene_id="beat-05")
    rendered = editor.render_shot(shot, 1)

    info = probe_media(rendered)
    assert info.has_video
    assert abs(info.duration - 2.5) < 0.15
    assert (info.width, info.height) == (540, 960)
    assert shot.to_dict()["media_type"] == "image"
    # A video shot is unchanged: no -loop, and its in-point is still honoured.
    assert Shot(source=image, start=1.0, duration=2.0).to_dict()["media_type"] == "video"


def test_a_photo_search_is_parsed_into_a_still_clip():
    from vidfactory.stock.pexels import PexelsProvider
    from vidfactory.stock.pixabay import PixabayProvider

    pexels = PexelsProvider.parse_photos({"photos": [{
        "id": 7, "width": 4000, "height": 6000,
        "url": "https://www.pexels.com/photo/red-apple-7/",
        "photographer": "A", "photographer_url": "u",
        "alt": "Red Apple With Skin",
        "src": {"large": "l.jpg", "large2x": "l2.jpg"},
    }]}, "raw apple")[0]
    assert pexels.media_type == "image"
    assert pexels.duration == 0.0
    assert pexels.key == "pexels:photo-7"
    # The alt text is the thing a photo has and a video does not.
    assert pexels.description == "red apple with skin"

    pixabay = PixabayProvider.parse_photos({"hits": [{
        "id": 9, "imageWidth": 3000, "imageHeight": 2000,
        "largeImageURL": "big.jpg", "webformatURL": "small.jpg",
        "pageURL": "p", "user": "B", "tags": "apple, fruit",
    }]}, "raw apple")[0]
    assert pixabay.media_type == "image" and pixabay.key == "pixabay:photo-9"
    assert pixabay.tags == ["apple", "fruit"]


def test_a_provider_with_no_image_api_offers_nothing_rather_than_failing():
    """The fallback asks every provider; one that cannot answer says so."""

    from vidfactory.stock.base import StockClip, StockProvider

    class Bare(StockProvider):
        name = "bare"

        def search(self, query, per_page=20, **filters):
            return [StockClip(provider="bare", provider_id="1", download_url="u",
                              width=1920, height=1080, duration=5.0)]

    assert Bare(api_key="k").search_images("apples") == []


def test_the_report_counts_the_stills_and_the_last_resort_separately():
    """A beat carried by a still is fine; a beat carried by nothing is not."""

    from vidfactory.reels.qc import build_report

    script = fitted(BY_SLUG[FIRST], 45)
    visual = {
        "image_fallback_shot_count": 2,
        "item_grounding_results": [
            {"beat": "beat-05", "item": "manzana", "required_entity": "manzana",
             "checked": True, "passed": True, "score": 1.0, "failed_on": [],
             "media": "image", "ungrounded_fallback": False},
            {"beat": "beat-07", "item": "fresas", "required_entity": "fresas",
             "checked": True, "passed": False, "score": 0.0, "failed_on": [],
             "media": "video", "ungrounded_fallback": True},
        ],
    }
    report = build_report(
        script, production=True, visual=visual, sources=[{"key": "x"}],
        cta_start=script.estimated_seconds - 3,
    )
    assert report.metrics["image_fallback_shot_count"] == 2
    assert report.metrics["ungrounded_fallback_count"] == 1
    # The still beat passes; the ungrounded one is a failure, so production
    # refuses the render rather than shipping a picture nobody verified.
    assert report.metrics["entity_grounding_failure_count"] == 1
    assert "every_item_shows_its_food" in [c.name for c in report.failures]


def test_a_pile_that_has_been_spent_cannot_be_spent_again():
    """The freeze is the whole point: a number about seen footage is not one.

    What this pins is not which set happens to be fresh today - that changes
    every cycle - but the two properties that have to hold in every cycle.
    A command is either wholly fresh or wholly spent, because a table mixing
    new piles with re-used ones is the exact confusion the manifest exists to
    prevent; and the tool refuses a spent command rather than quietly
    re-measuring it.
    """

    import importlib.util
    import sys

    tool = Path(__file__).resolve().parents[1] / "tools" / "reel_holdout_check.py"
    spec = importlib.util.spec_from_file_location("reel_holdout_check", tool)
    module = importlib.util.module_from_spec(spec)
    # Registered before it is executed: a dataclass built under
    # ``from __future__ import annotations`` resolves its own annotations
    # through sys.modules, and a module that is not in there raises.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    manifest = json.loads(
        (Path(__file__).resolve().parents[1] / "data" / "calibration"
         / "reel_grounding_dev_clips.json").read_text(encoding="utf-8")
    )
    burned = {q.strip().lower() for q in manifest["burned_queries"]}
    assert len(manifest["clips"]) == 54
    assert len(manifest["runs"]) >= 4

    clips, queries = module.frozen()
    assert len(clips) == 54 and queries == burned

    for command, piles in module.PILES_FOR.items():
        spent = module.spent_piles(command, burned)
        assert len(spent) in (0, len(piles)), (
            f"{command} mixes {len(spent)} spent piles with "
            f"{len(piles) - len(spent)} fresh ones"
        )

    # A query nobody has spent is not flagged, which is what makes the check
    # a gate rather than a wall.
    fresh = module.Pile("invented", "a query no run has ever issued", "raw",
                        True, "manzana")
    module.PILES_FOR["invented"] = (fresh,)
    try:
        assert module.spent_piles("invented", burned) == []
    finally:
        del module.PILES_FOR["invented"]

    # Every food a pile names has to be one the registry knows.
    from vidfactory.reels.foods import BY_NAME
    for piles in module.PILES_FOR.values():
        for pile in piles:
            assert not pile.food or pile.food in BY_NAME, pile.name


def test_every_command_the_cli_offers_has_piles_recorded():
    """A command the freeze check does not know about is unprotected.

    So the CLI takes its choices *from* the pile map rather than repeating
    them, and this is the check that it still does.
    """

    import importlib.util
    import sys

    tool = Path(__file__).resolve().parents[1] / "tools" / "reel_holdout_check.py"
    source = tool.read_text(encoding="utf-8")
    assert 'parser.add_argument("command", choices=sorted(PILES_FOR))' in source

    spec = importlib.util.spec_from_file_location("reel_holdout_check_cli", tool)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    # Every command has a runner, and every runner has piles.
    assert set(module.PILES_FOR) == {
        "berries", "entity", "presentation", "avocado", "apple",
        "apple-state", "apple-holdout", "apple-final", "sharpness", "holdout",
    }
    for command, piles in module.PILES_FOR.items():
        assert piles, command
        # And a command with no runner is an argparse choice that crashes on
        # the dispatch table, which is a worse failure than a missing choice.
        dispatch = source.split("runner = {", 1)[1].split("}[args.command]", 1)[0]
        assert f'"{command}"' in dispatch or f'== "{command}"' in source, command


def test_no_context_prompt_describes_the_crockery():
    """The context is about the food, not what it is served on.

    "In a bowl as the main subject" rejected strawberries on linen and
    raspberries in a glass jar - valid footage, wrong furniture - and the
    prompt was the reason. The one exception is the juice, where the glass
    *is* the food: "cambiar la fruta entera por zumo" is a warning about the
    drink, and a picture of it has to contain the drink.
    """

    from vidfactory.reels.foods import REQUIREMENTS

    furniture = ("bowl", "plate", "kitchen table", "wooden board", "board",
                 "counter", "tray", "basket", "punnet", "jar")
    allowed = {"zumo"}
    for name, requirement in REQUIREMENTS.items():
        if name in allowed:
            continue
        for prompt in requirement.context_requirements:
            lowered = prompt.lower()
            for word in furniture:
                assert word not in lowered, f"{name} context names the {word}: {prompt!r}"


def test_the_wrong_context_list_can_be_varied_for_a_measurement():
    """One of the shared negatives is a supermarket shelf, and a supermarket
    box of strawberries is footage worth keeping - so whether that prompt
    costs anything has to be answerable without editing the module."""

    from vidfactory.reels.foods import (
        REQUIREMENTS, requirement_prompts, score_requirement,
    )

    requirement = REQUIREMENTS["fresas"]
    full, _ = requirement_prompts(requirement)
    fewer, offsets = requirement_prompts(requirement, ("a printed logo",))
    assert len(fewer) == len(full) - 2
    # And the scorer reads the same list it was given, so the two cannot
    # silently disagree about where the context block ends.
    rows = [[0.1] * len(fewer) for _ in range(3)]
    for row in rows:
        row[0] = 0.9
        row[offsets["state"]] = 0.9
        row[offsets["context"]] = 0.9
    verdict = score_requirement(requirement, rows, ("a printed logo",))
    assert verdict.checked and verdict.passed


def test_the_ranker_scores_the_food_and_not_the_furniture():
    """``visual_semantic_match`` compared a fruit prompt against *rooms*.

    Run 34165114277 averaged 0.217 over a whole reel with nineteen of
    twenty-three clips called low relevance, and the reason is in the
    analyzer's own alternatives: "a kitchen counter", "a bedroom with a made
    bed", "a close-up of a potted plant". A macro shot of raspberries on a
    board genuinely does look like a kitchen counter, so the fruit prompt kept
    losing to furniture. The reel now supplies the alternatives a *food*
    search returns instead.

    This is the ranking score and not the gate: the four-probe conjunction is
    untouched, and the long-form analyzer keeps its own list byte-for-byte.
    """

    from vidfactory.reels.foods import FOOD_SEMANTIC_DISTRACTORS
    from vidfactory.visual_analysis import DISTRACTOR_PROMPTS, VisualAnalyzer

    # Nothing in the food list describes a room.
    rooms = ("living room", "bedroom", "bathroom", "hallway", "office", "sofa")
    for prompt in FOOD_SEMANTIC_DISTRACTORS:
        for room in rooms:
            assert room not in prompt.lower(), prompt

    # And the default is unchanged, so the long-form verdict cannot move.
    assert VisualAnalyzer().semantic_distractors is None
    assert DISTRACTOR_PROMPTS[0] == "a kitchen counter"
    chosen = VisualAnalyzer(semantic_distractors=FOOD_SEMANTIC_DISTRACTORS)
    assert chosen.semantic_distractors == FOOD_SEMANTIC_DISTRACTORS


def test_every_food_states_the_intent_the_ranker_scores():
    """A prompt naming the table is a prompt about the table.

    The beat's ``search_text`` was written to *find* footage and says "a whole
    red apple on a wooden table"; scoring against it asks the ranker how
    table-like the frame is. ``visual_intent`` names the food and its state,
    and the same words that were banned from the context prompts are banned
    here for the same reason.
    """

    from vidfactory.reels.foods import REQUIREMENTS

    furniture = ("bowl", "plate", "table", "board", "counter", "basket",
                 "punnet", "jar", "kitchen")
    for name, requirement in REQUIREMENTS.items():
        assert requirement.visual_intent, name
        lowered = requirement.visual_intent.lower()
        for word in furniture:
            assert word not in lowered, f"{name} intent names the {word}"


def test_the_report_says_which_provider_reached_the_screen():
    """"16 shots from 16 sources" is true of a one-provider reel too.

    Two renders drew on Pexels alone because Pixabay had no key, and no
    metric in the report said so. These are popped by name rather than left
    to the ``visual_`` prefix, because they are what someone asking "is the
    second provider actually being used" reads.
    """

    import inspect
    from vidfactory.reels import qc

    source = inspect.getsource(qc)
    for name in ("pexels_shot_count", "pixabay_video_shot_count",
                 "pixabay_image_shot_count", "animated_still_count",
                 "providers_on_screen"):
        assert name in source, name


def test_the_provider_counts_survive_the_trip_to_the_report():
    """The first version of these counters reported zero for a sixteen-shot reel.

    They were computed in ``_plan_visuals`` and returned in its dict - but
    ``_visual_summary`` is an explicit allow-list, so a key it does not name
    is dropped on the floor, and ``build_report`` then popped an absent key
    and got the default. Every number was 0 while the same report said
    ``visual_shot_count: 16`` and listed real Pexels asset ids per beat.

    So the counts are taken where the shots are, and this asserts the whole
    trip rather than the arithmetic: a shot list in, named metrics out.
    """

    from vidfactory.editor import Shot
    from vidfactory.reels.pipeline import ReelPipeline, _provider_counts

    def shot(key: str, still: bool = False) -> Shot:
        return Shot(scene_id="beat-00", clip_key=key, source="x", start=0.0,
                    duration=2.0, motion="zoom_in", still=still)

    shots = [shot("pexels:1"), shot("pexels:2"), shot("pixabay:3"),
             shot("pixabay:4", still=True), shot("pexels:5", still=True)]

    counts = _provider_counts(shots)
    assert counts["pexels_shot_count"] == 2
    assert counts["pexels_image_shot_count"] == 1
    assert counts["pixabay_video_shot_count"] == 1
    assert counts["pixabay_image_shot_count"] == 1
    assert counts["animated_still_count"] == 2
    assert counts["providers_on_screen"] == ["pexels", "pixabay"]

    # And the summary the report is actually built from carries them, which is
    # the half that was broken.
    summary = ReelPipeline._visual_summary(shots, {})
    for name, value in counts.items():
        assert summary[name] == value, name

    # A reel that really is one-provider says so rather than saying nothing.
    alone = _provider_counts([shot("pexels:1"), shot("pexels:2")])
    assert alone["providers_on_screen"] == ["pexels"]
    assert alone["pixabay_video_shot_count"] == 0


def test_a_window_is_sampled_inside_itself_and_never_outside():
    """The whole failure, as an assertion.

    Run 34324481463 shipped a manzana beat scoring 1.00 on all four probes
    over a crop showing a blurred hand, because the frames that answered came
    from elsewhere in the source clip. A window judged on somebody else's
    frames is not judged.
    """

    from vidfactory.visual_analysis import segment_positions

    start, length = 12.4, 2.9
    positions = segment_positions(start, length)
    assert len(positions) == 3
    for t in positions:
        assert start < t < start + length, t
    # And ordered, with nothing sitting on an edge where a cut lives.
    assert positions == sorted(positions)
    assert positions[0] > start + length * 0.15
    assert positions[-1] < start + length * 0.85

    # A degenerate segment still answers rather than raising.
    assert segment_positions(5.0, 0.0) == [5.0, 5.0, 5.0]
    assert segment_positions(0.0, 3.0, 1) == [1.5]


def test_the_crop_moves_before_the_clip_is_thrown_away():
    """A source is not unusable because its first three seconds are."""

    from vidfactory.reels.pipeline import MAX_WINDOWS, window_starts

    # The opening leads, because that is where the editor has always started
    # and a source that is fine as it stands must cost one grounding pass.
    assert window_starts(10.0, 3.0)[0] == 0.0
    assert len(window_starts(10.0, 3.0)) > 1

    # A long source does not turn into an unbounded scan.
    assert len(window_starts(600.0, 3.0)) <= MAX_WINDOWS + 1

    # A source with no room to move offers exactly the one window it has.
    assert window_starts(3.05, 3.0) == [0.0]
    assert window_starts(2.0, 3.0) == [0.0]

    # Every start leaves a whole window inside the source.
    for seconds in (4.0, 7.5, 31.0):
        for start in window_starts(seconds, 3.0):
            assert start + 3.0 <= seconds + 0.05, (seconds, start)


def test_the_report_separates_the_clip_from_the_crop():
    """"The source contains an apple" and "the viewer saw an apple" are two
    different claims, and only the second one ships."""

    import inspect
    from vidfactory.reels import pipeline, qc

    report = inspect.getsource(qc)
    for name in ("used_segment_results", "segment_grounding_failure_count",
                 "segment_window_repair_count",
                 "the_seconds_on_screen_show_the_food"):
        assert name in report, name

    # The allow-list has to name them or they never arrive - the mistake the
    # provider counters already made once.
    summary = inspect.getsource(pipeline.ReelPipeline._visual_summary)
    for name in ("used_segment_results", "segment_grounding_failure_count",
                 "segment_window_repair_count"):
        assert name in summary, name


def test_the_editor_no_longer_starts_every_reel_shot_at_zero():
    """``start=0.0`` was hardcoded, so the viewer always got the opening
    seconds of a clip that had been judged on frames from anywhere in it."""

    import inspect
    from vidfactory.reels import pipeline

    source = inspect.getsource(pipeline.ReelPipeline._plan_visuals)
    assert "start=0.0" not in source
    assert "start=round(in_point, 3)" in source


def test_no_undefined_names_in_the_reel_code_or_its_probes():
    """A name that only resolves at call time is a crash waiting for a runner.

    Two of these shipped in one afternoon. ``run_sharpness`` called
    ``ground_requirement`` without importing it and died on the first clip of
    a probe that had already spent five minutes downloading models. Worse,
    ``_plan_visuals`` referenced ``probe_media`` that was never imported at
    module level - a botched edit put the import inside another method - and
    the reel render *passed*, because the branch only runs for a clip whose
    duration the provider did not report.

    Importing the module catches neither: both names are looked up when the
    line executes. So the whole reel surface and every probe is checked for
    undefined names, which is exactly the question a linter answers and the
    test suite did not ask.
    """

    import subprocess
    import sys

    pytest.importorskip("pyflakes", reason="pyflakes is the linter this uses")

    root = Path(__file__).resolve().parents[1]
    targets = [
        *sorted((root / "src" / "vidfactory" / "reels").glob("*.py")),
        root / "src" / "vidfactory" / "visual_analysis.py",
        root / "tools" / "reel_holdout_check.py",
        root / "tools" / "inspect_reel_frames.py",
    ]
    result = subprocess.run(
        [sys.executable, "-m", "pyflakes", *[str(t) for t in targets]],
        capture_output=True, text=True, check=False,
    )
    # Unused imports are style; an undefined name is a crash. Only the second
    # kind fails, so this cannot become a reason to churn imports.
    undefined = [
        line for line in result.stdout.splitlines()
        if "undefined name" in line or "redefinition" in line
    ]
    assert not undefined, "\n".join(undefined)
