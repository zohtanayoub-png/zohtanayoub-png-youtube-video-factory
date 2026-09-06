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

import pytest

from vidfactory.reels import hooks, safety
from vidfactory.reels.captions import (
    BOTTOM_UNSAFE,
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
from vidfactory.reels.script import ALLOWED_SECONDS, CTA_VARIANTS, build
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
        script = build(topic, target_seconds=45)
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


def test_the_briefs_own_examples_all_clear_the_bar():
    """The bar was read off these eight, not chosen."""

    topic = BY_SLUG[FIRST]
    examples = [
        "Si tienes diabetes, no todas las frutas afectan igual a tu glucosa.",
        "Estas frutas parecen saludables, pero algunas pueden subir tu glucosa mucho mas rapido.",
        "Si tu glucosa se dispara despues del desayuno, puede que estes cometiendo uno de estos errores.",
        "Antes de dejar de comer fruta por miedo al azucar, mira esto.",
        "El problema no siempre es la fruta. Muchas veces es como te la comes.",
        "Tres cambios muy simples pueden ayudarte a evitar picos innecesarios despues de comer.",
        "Si comes fruta sola cuando tienes hambre, presta atencion a esto.",
        "Este desayuno parece saludable, pero puede no ser la mejor opcion para tu glucosa.",
    ]
    for example in examples:
        candidate = hooks.score_hook(example, topic)
        assert not candidate.rejected, example
        assert candidate.total >= hooks.HOOK_PASS, (example, candidate.total)


def test_between_five_and_ten_candidates_are_generated_and_one_is_chosen():
    for topic in TOPICS:
        candidates = hooks.generate(topic)
        assert 5 <= len(candidates) <= 10, (topic.slug, len(candidates))
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
        script = build(topic, target_seconds=45)
        assert _shared_run(script.hook.hook, topic.conclusion) < 5, topic.slug


# ---------------------------------------------------------------------------
# The shape of a reel
# ---------------------------------------------------------------------------

def test_the_six_beats_arrive_in_order():
    script = build(BY_SLUG[FIRST], target_seconds=45)
    kinds = [b.kind for b in script.beats]
    assert kinds[0] == "hook"
    assert kinds[1] == "promise"
    assert kinds[-1] == "cta"
    assert kinds[-2] == "conclusion"
    assert "item" in kinds


def test_the_cta_is_one_of_the_allowed_variations():
    for topic in TOPICS:
        assert build(topic, target_seconds=45).cta in CTA_VARIANTS


def test_the_cta_never_asks_for_a_purchase():
    for variant in CTA_VARIANTS:
        flat = variant.lower()
        for word in ("compra", "compre", "vende", "link", "enlace", "descuento"):
            assert word not in flat


@pytest.mark.parametrize("seconds", ALLOWED_SECONDS)
def test_the_duration_request_is_honoured_or_the_content_wins(seconds):
    """A shorter reel drops items; it never drops the claim inside one, and
    it never ends up empty."""

    script = build(BY_SLUG[FIRST], target_seconds=seconds)
    assert script.item_beats, seconds
    assert script.cta
    for beat in script.item_beats:
        assert len(beat.text.split()) >= 8


def test_explanations_are_dropped_before_items_are():
    """The long-form trim rule, applied here: optional material first, the
    substance last."""

    long_reel = build(BY_SLUG[FIRST], target_seconds=60)
    short_reel = build(BY_SLUG[FIRST], target_seconds=30)
    assert len(long_reel.item_beats) >= len(short_reel.item_beats)
    assert long_reel.word_count > short_reel.word_count


def test_retention_lines_are_used_sparingly_and_never_twice():
    for topic in TOPICS:
        script = build(topic, target_seconds=60)
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
        script = build(topic, target_seconds=45)
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
        script = build(topic, target_seconds=45)
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
        script = build(topic, target_seconds=45)
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

    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1] / "src" / "vidfactory"
    for path in root.glob("*.py"):
        body = path.read_text(encoding="utf-8")
        if path.name == "main.py":
            # The CLI dispatches to both, inside the command function.
            continue
        assert "reels" not in body.replace("reels/", ""), path.name


def test_the_reels_package_reuses_rather_than_reimplements():
    """It should be importing the shared machinery, not copying it."""

    import pathlib

    body = (
        pathlib.Path(__file__).resolve().parents[1]
        / "src" / "vidfactory" / "reels" / "pipeline.py"
    ).read_text(encoding="utf-8")
    for shared in ("..downloader", "..editor", "..ranking", "..tts",
                   "..stock.registry", "..subtitles"):
        assert shared in body, shared
