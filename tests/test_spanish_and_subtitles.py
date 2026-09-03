"""Spanish as the production language, and the premium caption system.

Two features, one test module, because they meet in the same place: the
captions are burned in the language the script was written in, and both are
wrong in the same way if the language plumbing leaks.

The rule this module exists to defend is the separation in
:mod:`vidfactory.languages`: the *content* language is Spanish and the
*search* language is English. Everything the viewer hears or reads is Spanish;
every string sent to Pexels is English, built from each idea's canonical
English metadata rather than from the narration.
"""

from __future__ import annotations

import json
import re
import subprocess
import unicodedata
from dataclasses import dataclass

import pytest

from vidfactory.ass_subtitles import (
    CLEAN,
    MIN_EVENT_SECONDS,
    PREMIUM,
    available_font,
    emphasis_spans,
    events_from_chunks,
    format_ass_time,
    render_ass,
    report,
    split_phrases,
    style_for,
    write_ass,
)
from vidfactory.causal_alignment import score_paragraph
from vidfactory.config import ConfigError, load_config, validate
from vidfactory.editor import subtitle_filter
from vidfactory.ffmpeg_utils import ffmpeg_available, ffmpeg_path
from vidfactory.knowledge import tips_for
from vidfactory.languages import DEFAULT_LANGUAGE, ENGLISH, SPANISH, resolve_language
from vidfactory.metadata import build_metadata
from vidfactory.scene_planner import plan_scenes
from vidfactory.script_generator import generate_script
from vidfactory.subtitles import generate_subtitles
from vidfactory.title_alignment import detect_promise
from vidfactory.topic_engine import TopicEngine
from vidfactory.tts import normalize_spanish, spanish_number, voices_for_language

SPANISH_TOPIC = "Trucos para que un salón pequeño parezca mucho más grande"


@dataclass
class Chunk:
    """Stands in for a NarrationChunk: text plus its measured span."""

    text: str
    start: float
    end: float


@pytest.fixture(scope="module")
def spanish_script():
    topic = TopicEngine(language="es").from_user_input(SPANISH_TOPIC)
    return generate_script(topic, duration_minutes=6.0, language="es")


# ---------------------------------------------------------------------------
# 1. The language itself
# ---------------------------------------------------------------------------

def test_spanish_is_the_default_language():
    assert DEFAULT_LANGUAGE is SPANISH
    assert DEFAULT_LANGUAGE.code == "es-ES"
    assert resolve_language(None).code == "es-ES"


def test_the_dropdown_labels_resolve():
    assert resolve_language("Spanish") is SPANISH
    assert resolve_language("English") is ENGLISH
    assert resolve_language("es-ES") is SPANISH
    assert resolve_language("en_US") is ENGLISH


def test_an_unknown_language_falls_back_rather_than_raising():
    """A typo in a workflow input should cost a log line, not a render."""

    assert resolve_language("Portuguese") is DEFAULT_LANGUAGE
    assert resolve_language("") is DEFAULT_LANGUAGE


def test_the_config_ships_spanish_and_premium_burned_in_captions():
    config = load_config("config.yaml")
    assert config.get("channel.language") == "es-ES"
    assert config.get("subtitles.style") == "premium"
    assert config.get("subtitles.burn_in") is True
    assert config.get("subtitles.enabled") is True


# ---------------------------------------------------------------------------
# 2. Spanish writing
# ---------------------------------------------------------------------------

def test_the_spanish_knowledge_base_is_written_in_spanish():
    tips = tips_for(None, language="es")
    assert len(tips) >= 100
    accented = sum(1 for t in tips if _has_spanish_marks(t["why"] + t["how"]))
    # Accents and ñ are not decoration in Spanish; a pool without them would
    # mean the text is English wearing a Spanish label.
    assert accented > len(tips) * 0.9


def _has_spanish_marks(text: str) -> bool:
    return any(c in text for c in "áéíóúüñ¿¡")


def test_a_spanish_script_is_spanish_all_the_way_through(spanish_script):
    text = spanish_script.text
    assert spanish_script.language == "es"
    assert _has_spanish_marks(text)
    # English function words would give away a leaked template. "ideas" is
    # deliberately not in this list: it is the same word in both languages.
    leaks = re.findall(
        r"\b(the|and|with|your|room|because|which|that|from)\b", text.lower()
    )
    assert not leaks, leaks[:6]


def test_accents_and_enye_survive_generation(spanish_script):
    text = spanish_script.text
    assert "ñ" in text or "Ñ" in text
    # NFC, not decomposed: a decomposed "n" plus a combining tilde breaks
    # both the TTS phonemizer and the caption font metrics.
    assert unicodedata.normalize("NFC", text) == text


def test_spanish_hooks_do_not_all_start_the_same_way():
    topics = [
        "Trucos para que un salón pequeño parezca mucho más grande",
        "Ideas para que tu casa parezca más cara",
        "Errores de decoración que abaratan un salón",
    ]
    openings = set()
    for title in topics:
        topic = TopicEngine(language="es").from_user_input(title)
        script = generate_script(topic, duration_minutes=3.0, language="es")
        openings.add(script.sections[0].text[:40])
    assert len(openings) == len(topics)


def test_spanish_promise_alignment_works(spanish_script):
    assert spanish_script.promise_key == "bigger"
    assert spanish_script.title_idea_alignment >= 0.8


def test_the_causal_check_runs_in_spanish(spanish_script):
    assert spanish_script.causal.results
    assert spanish_script.causal_promise_alignment_score >= 0.85
    assert min(spanish_script.section_alignment_scores) >= 0.85


def test_a_spanish_paragraph_without_a_reason_fails_the_causal_check():
    promise = detect_promise(SPANISH_TOPIC, language="es")
    bad = (
        "Mide la habitación antes de comprar nada. Mide antes de comprar "
        "muebles porque las devoluciones son caras y nadie quiere bajar un "
        "sofá por la escalera."
    )
    good = (
        "Mide la habitación antes de comprar nada. Mide antes de comprar "
        "muebles porque las piezas sobredimensionadas se comen el suelo "
        "visible y estrechan el paso, así que el salón se siente agobiante."
    )
    assert score_paragraph(bad, promise).score == 0.0
    assert score_paragraph(good, promise).passed


def test_english_still_produces_an_english_script():
    topic = TopicEngine(language="en").from_user_input(
        "Small Living Room Tricks That Make Your Space Look Bigger"
    )
    script = generate_script(topic, duration_minutes=4.0, language="en")
    assert script.language == "en"
    assert not _has_spanish_marks(script.text)
    assert script.promise_key == "bigger"
    assert script.causal_promise_alignment_score >= 0.85


def test_spanish_titles_agree_in_gender_and_carry_a_determiner():
    import random

    engine = TopicEngine(rng=random.Random(3), language="es")
    titles = [engine.generate().title for _ in range(15)]
    for title in titles:
        assert not re.search(r"\bpara (salón|cocina|dormitorio|estudio)\b", title), title
        assert not re.search(r"\b(tu casa|una cocina) \w+ más amplio\b", title), title


# ---------------------------------------------------------------------------
# 3. The search language stays English
# ---------------------------------------------------------------------------

def test_every_pexels_query_is_english_even_though_the_script_is_spanish(spanish_script):
    """The rule the whole language split exists for.

    Pexels is indexed in English. Translating the query is the wrong instinct:
    the narration is what the viewer hears, the query is a lookup key into
    somebody else's index.
    """

    scenes = plan_scenes(spanish_script)
    queries = [q.text for scene in scenes for q in scene.visual_queries]
    assert queries
    non_english = [q for q in queries if not q.isascii()]
    assert not non_english, non_english[:5]


def test_scenes_carry_an_english_search_text_beside_spanish_narration(spanish_script):
    scenes = plan_scenes(spanish_script)
    items = [s for s in scenes if s.section_kind == "item"]
    assert items
    for scene in items:
        assert scene.search_text.isascii(), scene.search_text
        assert scene.narration


def test_spanish_tips_keep_their_english_search_metadata():
    for tip in tips_for(None, language="es"):
        for query in tip["queries"]:
            assert query.isascii(), (tip["title"], query)
        assert tip["search"].isascii()
        assert all(str(tag).isascii() for tag in tip["tags"])


# ---------------------------------------------------------------------------
# 4. Voice and pronunciation
# ---------------------------------------------------------------------------

def test_spanish_selects_a_spanish_female_voice_without_being_asked():
    voice, fallbacks = voices_for_language("Spanish")
    assert voice == "es_ES-sharvard-medium"
    assert all(v.startswith("es_") for v in fallbacks)


def test_english_keeps_its_existing_voice():
    voice, fallbacks = voices_for_language("English")
    assert voice == "en_US-hfc_female-medium"
    assert all(v.startswith("en_") for v in fallbacks)


def test_a_voice_from_the_wrong_language_is_refused():
    """An English voice reading Spanish is not a degraded video, it is an
    unusable one, so the request is ignored rather than honoured."""

    voice, _ = voices_for_language("es", "en_US-amy-medium")
    assert voice.startswith("es_")


def test_an_explicit_spanish_voice_is_honoured():
    voice, _ = voices_for_language("es", "es_MX-claude-high")
    assert voice == "es_MX-claude-high"


@pytest.mark.parametrize(
    "number,expected",
    [(0, "cero"), (1, "uno"), (15, "quince"), (16, "dieciséis"), (21, "veintiuno"),
     (30, "treinta"), (45, "cuarenta y cinco"), (100, "cien"), (145, "ciento cuarenta y cinco"),
     (200, "doscientos"), (2700, "dos mil setecientos")],
)
def test_spanish_numbers_are_written_out(number, expected):
    assert spanish_number(number) == expected


@pytest.mark.parametrize(
    "raw,expected_fragment",
    [
        ("Deja 2,4 metros libres.", "dos coma cuatro metros"),
        ("Mide 60 cm.", "sesenta centímetros"),
        ("Añade un 10 %.", "diez por ciento"),
        ("A 1,5 metros del suelo.", "uno coma cinco metros"),
        ("Cuesta 100 €.", "cien euros"),
        ("Bombillas de 2700 K.", "dos mil setecientos kelvin"),
    ],
)
def test_spanish_measurements_are_spoken_not_spelled(raw, expected_fragment):
    assert expected_fragment in normalize_spanish(raw)


def test_normalisation_keeps_the_sentence_boundary():
    """Eating the full stop after a unit costs the voice its pause."""

    spoken = normalize_spanish("Son 250 cm. Nada más.")
    assert spoken.endswith("Nada más.")
    assert "centímetros. Nada" in spoken


def test_normalisation_preserves_accents_and_enye():
    spoken = normalize_spanish("El salón pequeño y el alféizar de 40 cm.")
    assert "salón" in spoken and "pequeño" in spoken and "alféizar" in spoken


# ---------------------------------------------------------------------------
# 5. Spanish metadata
# ---------------------------------------------------------------------------

def test_metadata_is_spanish_end_to_end(spanish_script):
    scenes = plan_scenes(spanish_script)
    timings = {s.scene_id: (float(i) * 3, float(i) * 3 + 3) for i, s in enumerate(scenes)}
    metadata = build_metadata(
        script=spanish_script,
        scenes=scenes,
        scene_timings=timings,
        duration_seconds=len(scenes) * 3.0,
        sources=[{"provider": "pexels"}],
        channel_name="HomeeDeeco",
        language="es-ES",
    )
    assert metadata.language == "es-ES"
    assert metadata.title == spanish_script.title
    assert "En este vídeo" in metadata.description
    assert "Capítulos:" in metadata.description or "Lo que vemos:" in metadata.description
    assert any(_has_spanish_marks(tag) or " " in tag for tag in metadata.tags)
    assert "decoración" in metadata.tags or "interiorismo" in metadata.tags
    # No English boilerplate leaking into a Spanish description.
    assert "In this video" not in metadata.description
    assert "Chapters:" not in metadata.description
    payload = json.loads(json.dumps(metadata.to_dict(), ensure_ascii=False))
    assert payload["language"] == "es-ES"


# ---------------------------------------------------------------------------
# 6. Caption phrasing
# ---------------------------------------------------------------------------

def test_phrases_are_three_to_seven_words():
    text = (
        "Si tu salón parece más pequeño de lo que realmente es, puede que el "
        "problema no sean los metros cuadrados."
    )
    phrases = split_phrases(text, "es", PREMIUM.min_words, PREMIUM.max_words)
    assert phrases
    for phrase in phrases:
        assert 1 <= len(phrase.split()) <= PREMIUM.max_words + 2, phrase


def test_a_caption_never_ends_on_a_preposition_or_article():
    text = (
        "Coloca las cortinas lo más cerca posible del techo y deja que la tela "
        "roce el suelo de la habitación."
    )
    phrases = split_phrases(text, "es")
    clinging = SPANISH.clinging_words
    for phrase in phrases[:-1]:
        last = re.sub(r"[^\w]", "", phrase.split()[-1], flags=re.UNICODE).lower()
        assert last not in clinging, phrase


def test_english_phrasing_uses_english_clinging_words():
    phrases = split_phrases(
        "Hang your curtains close to the ceiling rather than to the window frame.",
        "en",
    )
    for phrase in phrases[:-1]:
        last = re.sub(r"[^\w]", "", phrase.split()[-1]).lower()
        assert last not in ENGLISH.clinging_words, phrase


def test_a_measurement_is_never_split_from_its_unit():
    phrases = split_phrases("Monta la barra a 15 cm del techo y abre la barra 20 cm.", "es")
    for phrase in phrases:
        assert not re.search(r"\b\d+$", phrase.strip()), phrase


# ---------------------------------------------------------------------------
# 7. Emphasis
# ---------------------------------------------------------------------------

def test_emphasis_marks_measurements_and_outcomes():
    assert emphasis_spans("sube la barra 15 cm", "es")
    assert emphasis_spans("el techo parece más alto", "es")


def test_emphasis_ignores_ordinary_words():
    assert not emphasis_spans("y deja que la tela roce", "es")


def test_clean_style_has_no_emphasis_and_no_animation():
    assert CLEAN.emphasis is False
    assert CLEAN.fade_in_ms == 0 and CLEAN.fade_out_ms == 0
    rendered = render_ass(
        events_from_chunks([Chunk("sube la barra 15 cm ahora mismo", 0.0, 3.0)], CLEAN, "es"),
        CLEAN, "es",
    )
    assert "\\fad(" not in rendered
    assert CLEAN.accent not in rendered


# ---------------------------------------------------------------------------
# 8. The .ass file
# ---------------------------------------------------------------------------

@pytest.fixture
def spanish_events():
    chunks = [
        Chunk("Si tu salón parece más pequeño de lo que realmente es, "
              "puede que el problema no sean los metros cuadrados.", 0.0, 7.0),
        Chunk("Sube la barra 15 cm y el techo parecerá más alto.", 7.0, 11.5),
    ]
    return events_from_chunks(chunks, PREMIUM, "es")


def test_ass_events_never_exceed_two_lines(spanish_events):
    assert spanish_events
    assert max(e.lines for e in spanish_events) <= 2


def test_ass_events_do_not_overlap_or_flash(spanish_events):
    metrics = report(spanish_events, PREMIUM)
    assert metrics["subtitle_overlap_count"] == 0
    assert metrics["subtitle_flash_count"] == 0
    assert metrics["subtitle_timing_passed"] is True
    for event in spanish_events:
        assert event.duration >= MIN_EVENT_SECONDS - 1e-6


def test_captions_stay_inside_the_safe_area(spanish_events):
    metrics = report(spanish_events, PREMIUM, height=1080)
    assert metrics["subtitle_safe_area_passed"] is True
    # Well clear of the player controls and of the frame edge.
    assert PREMIUM.margin_v >= 1080 * 0.06
    assert PREMIUM.margin_h >= 120


def test_ass_timing_format_is_valid(spanish_events):
    assert format_ass_time(0) == "0:00:00.00"
    assert format_ass_time(1.999) == "0:00:02.00"
    assert format_ass_time(3661.5) == "1:01:01.50"
    for event in spanish_events:
        assert re.fullmatch(r"\d:\d{2}:\d{2}\.\d{2}", format_ass_time(event.start))


def test_the_outline_is_opaque_enough_to_read_on_a_pale_wall():
    """ASS alpha is inverted: 00 is opaque, FF is invisible.

    The first burned-in captions used &HC8 for the outline, which is 78%
    transparent rather than 78% opaque, and white text on a pale wall had
    almost nothing holding it.
    """

    for style in (PREMIUM, CLEAN):
        alpha = int(style.outline_colour[2:4], 16)
        assert alpha <= 0x30, (style.name, style.outline_colour)


def test_written_ass_is_utf8_and_carries_the_style(tmp_path):
    chunks = [Chunk("El alféizar del salón pequeño mide 60 cm.", 0.0, 4.0)]
    path, events, font = write_ass(chunks, tmp_path / "subtitles.ass",
                                   style="premium", language="es")
    body = path.read_text(encoding="utf-8")
    assert path.name == "subtitles.ass"
    assert "[V4+ Styles]" in body and "Style: Premium," in body
    assert "PlayResX: 1920" in body and "PlayResY: 1080" in body
    assert "alféizar" in body
    assert font
    assert events


def test_style_selection_and_none(tmp_path):
    assert style_for("premium") is PREMIUM
    assert style_for("clean") is CLEAN
    assert style_for("nonsense") is PREMIUM


def test_an_available_font_is_always_returned():
    font = available_font()
    assert font and isinstance(font, str)


# ---------------------------------------------------------------------------
# 9. The SRT is still a plain SRT
# ---------------------------------------------------------------------------

def test_srt_is_still_exported_unstyled(tmp_path):
    chunks = [Chunk("El salón pequeño parece más grande con cortinas altas.", 0.0, 5.0)]
    path, cues = generate_subtitles(chunks, tmp_path / "subtitles.srt")
    body = path.read_text(encoding="utf-8")
    assert cues
    assert "-->" in body
    # No styling of any kind leaks into the accessibility file.
    assert "{\\" not in body and "Dialogue:" not in body
    assert "más grande" in body


# ---------------------------------------------------------------------------
# 10. Burning them in
# ---------------------------------------------------------------------------

def test_the_filter_uses_libass_for_ass_and_the_srt_renderer_for_srt(tmp_path):
    ass = tmp_path / "a.ass"
    srt = tmp_path / "a.srt"
    ass.write_text("x", encoding="utf-8")
    srt.write_text("x", encoding="utf-8")
    assert subtitle_filter(ass).startswith("ass=")
    assert subtitle_filter(srt).startswith("subtitles=")
    assert "force_style" in subtitle_filter(srt)


@pytest.mark.skipif(not ffmpeg_available(), reason="FFmpeg is required")
def test_premium_captions_are_actually_burned_into_the_picture(tmp_path):
    """Not "the filter was in the command line" - pixels that changed.

    A pale wall is the hardest case for white text, so that is what this
    renders against.
    """

    chunks = [Chunk("Muchas macetas pequeñas tapan la luz del alféizar.", 0.0, 4.0)]
    ass_path, _, _ = write_ass(chunks, tmp_path / "subtitles.ass",
                               style="premium", language="es")

    plain = tmp_path / "plain.mp4"
    burned = tmp_path / "burned.mp4"
    subprocess.run(
        [ffmpeg_path(), "-nostdin", "-v", "error", "-f", "lavfi",
         "-i", "color=c=0xD8D2C6:s=640x360:r=15", "-t", "3",
         "-pix_fmt", "yuv420p", str(plain), "-y"], check=True, timeout=120,
    )
    subprocess.run(
        [ffmpeg_path(), "-nostdin", "-v", "error", "-i", str(plain),
         "-vf", subtitle_filter(ass_path), "-c:v", "libx264", "-preset", "ultrafast",
         "-pix_fmt", "yuv420p", str(burned), "-y"], check=True, timeout=300,
    )

    def frame(path, at):
        out = subprocess.run(
            [ffmpeg_path(), "-nostdin", "-v", "error", "-ss", str(at), "-i", str(path),
             "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
            capture_output=True, timeout=120, check=True,
        )
        return out.stdout

    before, after = frame(plain, 1.5), frame(burned, 1.5)
    assert len(before) == len(after) > 0
    assert before != after, "no pixels changed - the captions were not burned in"

    # The change belongs in the lower third, not scattered over the room.
    width, height = 640, 360
    rows = [
        sum(1 for x in range(width) if before[y * width + x] != after[y * width + x])
        for y in range(height)
    ]
    changed_rows = [y for y, count in enumerate(rows) if count > 3]
    assert changed_rows, "the captions produced no legible mark"
    assert min(changed_rows) > height * 0.55, "captions are too high in the frame"
    assert max(changed_rows) < height * 0.97, "captions touch the bottom edge"


# ---------------------------------------------------------------------------
# 11. The rule that never changes
# ---------------------------------------------------------------------------

def test_music_is_still_impossible():
    config = load_config("config.yaml")
    assert config.music_enabled is False
    with pytest.raises(ConfigError):
        validate({"audio": {"music": True}, "video": {"duration_minutes": 5}})


def test_an_invalid_subtitle_style_is_rejected():
    with pytest.raises(ConfigError):
        validate({
            "audio": {"music": False},
            "video": {"duration_minutes": 5},
            "subtitles": {"style": "tiktok"},
        })
