"""Narration chunking, engine selection, timings and SRT generation."""

from __future__ import annotations

from pathlib import Path

import pytest

from vidfactory.ffmpeg_utils import format_timestamp, probe_media
from vidfactory.subtitles import (
    Cue,
    cues_from_chunks,
    generate_subtitles,
    split_into_cues,
    wrap_lines,
)
from vidfactory.tts import (
    EspeakEngine,
    NarrationBuilder,
    NarrationChunk,
    SilentEngine,
    TTSUnavailable,
    build_engine,
    chunk_text,
    normalize_for_speech,
)


class FakeScene:
    def __init__(self, scene_id: str, narration: str) -> None:
        self.scene_id = scene_id
        self.narration = narration


# ----------------------------------------------------------------- text prep

def test_normalize_expands_abbreviations():
    # The channel's default language is Spanish now, so an English
    # expectation has to say which language it means.
    text = normalize_for_speech(
        "Use LED strips, e.g. warm white, on the TV wall.", language="en"
    )
    assert "LED" not in text
    assert "e.g." not in text
    assert "L E D" in text


def test_normalize_collapses_whitespace_and_dashes():
    assert normalize_for_speech("a   b  —  c") == "a b, c"


def test_normalize_handles_empty():
    assert normalize_for_speech(None) == ""


def test_chunking_respects_the_limit():
    text = " ".join(["This is a sentence about home decor."] * 40)
    chunks = chunk_text(text, max_chars=200)
    assert chunks
    assert all(len(c) <= 220 for c in chunks)
    assert "".join(chunks).replace(" ", "") == text.replace(" ", "")


def test_chunking_does_not_split_short_text():
    assert chunk_text("Short sentence.", 320) == ["Short sentence."]


def test_chunking_splits_a_very_long_sentence():
    long_sentence = "word, " * 200
    chunks = chunk_text(long_sentence, max_chars=100)
    assert len(chunks) > 1


# -------------------------------------------------------------------- engines

def test_silent_engine_produces_timed_audio(tmp_path, has_ffmpeg):
    if not has_ffmpeg:
        pytest.skip("ffmpeg required")
    engine = SilentEngine()
    out = engine.synthesize("one two three four five six seven eight nine ten", tmp_path / "a.wav")
    info = probe_media(out)
    assert info.has_audio
    assert 3.0 <= info.duration <= 6.0


def test_build_engine_falls_back_when_a_specific_engine_is_missing(monkeypatch):
    import vidfactory.tts as tts

    monkeypatch.setattr(tts.shutil, "which", lambda name: None)
    monkeypatch.setattr(
        tts.PiperEngine, "_locate_piper", staticmethod(lambda: (_ for _ in ()).throw(TTSUnavailable("no piper")))
    )
    engine = tts.build_engine("auto")
    assert engine.name in ("espeak", "silent")


def test_explicit_silent_engine_is_honoured():
    assert build_engine("silent").name == "silent"


def test_narration_builder_produces_a_timeline(tmp_path, has_ffmpeg):
    if not has_ffmpeg:
        pytest.skip("ffmpeg required")
    scenes = [
        FakeScene("s1", "Hang your curtains close to the ceiling."),
        FakeScene("s2", "A rug that is too small shrinks the seating area."),
    ]
    builder = NarrationBuilder(SilentEngine(), tmp_path / "work", scene_pause=0.5)
    narration = builder.build(scenes, tmp_path / "narration.wav")

    assert narration.audio_path.exists()
    assert narration.duration > 1.0
    assert set(narration.scene_timings) == {"s1", "s2"}
    assert narration.scene_timings["s1"][0] == 0.0
    assert narration.scene_timings["s2"][0] > narration.scene_timings["s1"][1] - 0.01
    assert len(narration.chunks) >= 2
    # The chunk timeline must never run past the real audio length.
    assert narration.chunks[-1].end <= narration.duration + 0.05


def test_narration_skips_empty_scenes(tmp_path, has_ffmpeg):
    if not has_ffmpeg:
        pytest.skip("ffmpeg required")
    scenes = [FakeScene("s1", ""), FakeScene("s2", "Real narration here.")]
    builder = NarrationBuilder(SilentEngine(), tmp_path / "work")
    narration = builder.build(scenes, tmp_path / "n.wav")
    assert list(narration.scene_timings) == ["s2"]


def test_narration_raises_when_everything_is_empty(tmp_path, has_ffmpeg):
    if not has_ffmpeg:
        pytest.skip("ffmpeg required")
    builder = NarrationBuilder(SilentEngine(), tmp_path / "work")
    with pytest.raises(RuntimeError):
        builder.build([FakeScene("s1", "")], tmp_path / "n.wav")


def test_a_failing_tts_chunk_becomes_silence_not_a_crash(tmp_path, has_ffmpeg):
    if not has_ffmpeg:
        pytest.skip("ffmpeg required")

    class BrokenEngine(SilentEngine):
        name = "broken"

        def synthesize(self, text, destination):
            raise RuntimeError("engine exploded")

    builder = NarrationBuilder(BrokenEngine(), tmp_path / "work")
    narration = builder.build([FakeScene("s1", "Some narration text here.")], tmp_path / "n.wav")
    assert narration.duration > 0.5


# ------------------------------------------------------------------ subtitles

def test_wrap_lines_respects_the_line_length():
    wrapped = wrap_lines("a " * 40, max_line_chars=20, max_lines=2)
    assert len(wrapped.split("\n")) <= 2


def test_split_into_cues_breaks_long_text():
    pieces = split_into_cues("First sentence here. " * 8, max_chars=60)
    assert len(pieces) > 1
    assert all(len(p) <= 70 for p in pieces)


def test_split_into_cues_keeps_short_text_whole():
    assert split_into_cues("Short line.", 84) == ["Short line."]


def test_cues_are_ordered_and_do_not_overlap():
    chunks = [
        NarrationChunk("First chunk of narration text.", 0.0, 4.0, "s1"),
        NarrationChunk("Second chunk of narration text.", 4.3, 9.0, "s1"),
    ]
    cues = cues_from_chunks(chunks)
    assert cues
    for previous, current in zip(cues, cues[1:]):
        assert current.start >= previous.end - 0.001
        assert current.end > current.start


def test_cue_times_match_the_narration_timeline():
    chunks = [NarrationChunk("Some spoken words here.", 12.5, 16.0, "s1")]
    cues = cues_from_chunks(chunks)
    assert cues[0].start == pytest.approx(12.5, abs=0.01)
    assert cues[-1].end == pytest.approx(16.0, abs=0.01)


def test_empty_chunks_are_skipped():
    assert cues_from_chunks([NarrationChunk("", 0.0, 2.0, "s1")]) == []
    assert cues_from_chunks([NarrationChunk("text", 5.0, 5.0, "s1")]) == []


def test_srt_file_format(tmp_path):
    chunks = [
        NarrationChunk("Hang your curtains close to the ceiling.", 0.0, 3.5, "s1"),
        NarrationChunk("A rug that is too small shrinks the area.", 4.0, 8.0, "s2"),
    ]
    path, cues = generate_subtitles(chunks, tmp_path / "subtitles.srt")
    content = path.read_text(encoding="utf-8")
    assert content.startswith("1\n")
    assert "-->" in content
    assert "00:00:00,000" in content
    blocks = [b for b in content.strip().split("\n\n") if b.strip()]
    assert len(blocks) == len(cues)
    for position, block in enumerate(blocks, start=1):
        assert block.splitlines()[0] == str(position)


def test_timestamp_formatting():
    assert format_timestamp(0) == "00:00:00,000"
    assert format_timestamp(3661.5) == "01:01:01,500"
    assert format_timestamp(-5) == "00:00:00,000"


def test_cue_renders_srt_block():
    block = Cue(3, 1.0, 2.0, "Hello").to_srt()
    assert block.startswith("3\n00:00:01,000 --> 00:00:02,000\nHello")
