"""The optional CLIP backend, tested without downloading a CLIP model.

The backend has to survive two things: a runner where it cannot be
provisioned at all, and an ONNX export whose input names are not the ones we
guessed. Both are covered here with a stub session, so the logic is verified
on every run rather than only on a machine that happens to have the weights.
"""

from __future__ import annotations

import json

import pytest

pytest.importorskip("numpy", reason="the ONNX backend needs numpy")

from vidfactory import visual_model
from vidfactory.visual_analysis import Frame, VisualAnalyzer
from vidfactory.visual_model import CONTEXT_LENGTH, ClipTokenizer, OnnxClipModel


# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------

def _tokenizer() -> ClipTokenizer:
    vocab = {
        "<|startoftext|>": 49406,
        "<|endoftext|>": 49407,
        "a</w>": 320,
        "bright</w>": 1000,
        "living</w>": 1001,
        "room</w>": 1002,
        "bri": 2000,
        "ght</w>": 2001,
    }
    return ClipTokenizer(vocab, ["b r", "br i", "bri ght</w>", "l i"])


def test_the_tokenizer_produces_a_fixed_length_context():
    ids = _tokenizer().encode("A bright living room")
    assert len(ids) == CONTEXT_LENGTH
    assert ids[0] == 49406
    assert 49407 in ids


def test_the_tokenizer_lowercases_and_collapses_whitespace():
    tokenizer = _tokenizer()
    assert tokenizer.encode("A  BRIGHT   room") == tokenizer.encode("a bright room")


def test_a_very_long_prompt_is_truncated_but_still_terminated():
    ids = _tokenizer().encode("a bright living room " * 60)
    assert len(ids) == CONTEXT_LENGTH
    assert ids[-1] == 49407


def test_reading_a_tokenizer_file(tmp_path):
    path = tmp_path / "tokenizer.json"
    path.write_text(json.dumps({
        "model": {"vocab": {"a</w>": 1, "<|endoftext|>": 2}, "merges": ["a b"]}
    }))
    assert ClipTokenizer.from_file(path).vocab["a</w>"] == 1


def test_a_tokenizer_file_without_merges_is_rejected(tmp_path):
    path = tmp_path / "tokenizer.json"
    path.write_text(json.dumps({"model": {"vocab": {"a": 1}}}))
    with pytest.raises(visual_model.VisualModelUnavailable):
        ClipTokenizer.from_file(path)


# ---------------------------------------------------------------------------
# The ONNX wrapper, against a stub session
# ---------------------------------------------------------------------------

class _Meta:
    def __init__(self, name, shape=None):
        self.name = name
        self.shape = shape or []


class _StubSession:
    """Stands in for onnxruntime.InferenceSession."""

    def __init__(self, inputs, outputs, vector):
        self._inputs = [_Meta(*i) if isinstance(i, tuple) else _Meta(i) for i in inputs]
        self._outputs = [_Meta(o) for o in outputs]
        self._vector = vector
        self.seen: dict = {}

    def get_inputs(self):
        return self._inputs

    def get_outputs(self):
        return self._outputs

    def run(self, _, feed):
        import numpy as np

        self.seen = feed
        rows = len(next(iter(feed.values())))
        embedding = np.tile(np.array(self._vector, dtype=np.float32), (rows, 1))
        return [np.zeros((rows, 4, 4), dtype=np.float32), embedding]


def _model(vision_inputs=("pixel_values",), text_inputs=("input_ids",)) -> OnnxClipModel:
    model = OnnxClipModel.__new__(OnnxClipModel)
    model.vision = _StubSession(
        [(vision_inputs[0], [1, 3, 224, 224])], ["logits", "image_embeds"], [1.0, 0.0, 0.0]
    )
    model.text = _StubSession(list(text_inputs), ["logits", "text_embeds"], [1.0, 0.0, 0.0])
    model.tokenizer = _tokenizer()
    model.repo = "stub/clip"
    model.image_size = 224
    return model


def test_image_encoding_normalizes_and_reshapes():
    model = _model()
    frame = Frame(8, 8, bytes([128]) * (8 * 8 * 3), "probe")
    vectors = model.encode_images([frame])
    assert len(vectors) == 1 and len(vectors[0]) == 3
    batch = model.vision.seen["pixel_values"]
    assert batch.shape == (1, 3, 224, 224)
    # 128/255 put through CLIP's own mean and std: (0.502 - 0.4815) / 0.2686.
    assert float(batch[0][0][0][0]) == pytest.approx(0.0763, abs=1e-3)


def test_the_export_input_names_are_discovered_not_assumed():
    model = _model(vision_inputs=("input",), text_inputs=("text",))
    model.encode_images([Frame(4, 4, bytes(4 * 4 * 3), "probe")])
    assert "input" in model.vision.seen
    model.encode_texts(["a bright living room"])
    assert "text" in model.text.seen


def test_an_attention_mask_is_supplied_when_the_export_wants_one():
    model = _model(text_inputs=("input_ids", "attention_mask"))
    model.encode_texts(["a bright living room"])
    assert "attention_mask" in model.text.seen
    assert model.text.seen["attention_mask"].shape == (1, CONTEXT_LENGTH)


def test_the_pooled_embedding_is_picked_out_of_several_outputs():
    model = _model()
    assert model.encode_texts(["a room"])[0] == [1.0, 0.0, 0.0]


# ---------------------------------------------------------------------------
# Degrading, which is the property that actually matters
# ---------------------------------------------------------------------------

def test_load_model_returns_none_when_it_is_switched_off():
    assert visual_model.load_model({"enabled": False}) is None


def test_load_model_never_raises_when_provisioning_fails(monkeypatch):
    monkeypatch.setattr(
        visual_model, "provision",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no network")),
    )
    visual_model._FAILED.clear()
    assert visual_model.load_model({"enabled": True, "repo": "x/y"}) is None


def test_a_failed_load_is_not_retried_in_the_same_process(monkeypatch):
    calls = []

    def _boom(*a, **k):
        calls.append(1)
        raise RuntimeError("no network")

    monkeypatch.setattr(visual_model, "provision", _boom)
    visual_model._FAILED.clear()
    settings = {"enabled": True, "repo": "x/y", "fallback": False}
    visual_model.load_model(settings)
    visual_model.load_model(settings)
    assert len(calls) == 1


def test_the_analyzer_uses_the_model_when_it_is_there():
    """A model that answers changes the semantic source, and nothing else
    about how the analyzer is driven."""

    class _Backend:
        name = "stub-clip"
        image_size = 224

        def encode_images(self, frames):
            return [[1.0, 0.0]] * len(frames)

        def encode_texts(self, texts):
            # The scene prompt is the first entry; give it the matching vector.
            return [[1.0, 0.0]] + [[0.0, 1.0]] * (len(texts) - 1)

    analyzer = VisualAnalyzer(model=_Backend(), frames_per_clip=1)
    frame = Frame(8, 8, bytes([120, 100, 90]) * 64, "probe")
    analysis = analyzer.analyze([frame], query="a styled living room")
    assert analysis.semantic_source == "clip-embeddings"
    assert analysis.model.startswith("stub-clip")
    assert analysis.semantic_match > 0.5


def test_a_model_that_throws_does_not_stop_the_analysis():
    class _Broken:
        name = "broken"
        image_size = 224

        def encode_images(self, frames):
            raise RuntimeError("segfault, basically")

        def encode_texts(self, texts):
            raise RuntimeError("same")

    analyzer = VisualAnalyzer(model=_Broken(), frames_per_clip=1)
    frame = Frame(8, 8, bytes([120, 100, 90]) * 64, "probe")
    analysis = analyzer.analyze([frame], query="a styled living room")
    assert analysis.analyzed
    assert analysis.semantic_source == "pixel-expectations"


# ---------------------------------------------------------------------------
# Concept and semantic scoring at realistic CLIP scales
#
# The first real render measured a semantic match of 0.01 across forty clips
# and flagged five renovations and four plastic covers among ordinary Pexels
# interiors. Both came from scoring with CLIP's temperature-100 softmax, which
# is winner-take-all over similarities that differ by hundredths. These tests
# pin the margin-based replacement at the scales CLIP actually produces.
# ---------------------------------------------------------------------------

import math

from vidfactory.visual_analysis import (
    DISTRACTOR_PROMPTS,
    NEGATIVE_CONCEPTS,
    POSITIVE_CONCEPTS,
)


def _unit(angle: float) -> list[float]:
    return [math.cos(angle), math.sin(angle)]


class _AngleBackend:
    """A model where every prompt sits at a chosen angle from the image."""

    name = "angles"
    image_size = 224

    def __init__(self, angles: dict[str, float]):
        self.angles = angles

    def encode_images(self, frames):
        return [_unit(0.0)] * len(frames)

    def encode_texts(self, texts):
        # Every prompt reaches the model through PROMPT_TEMPLATE, so the test
        # looks its angle up by the bare concept.
        def bare(text: str) -> str:
            return text[len("a photo of ") :] if text.startswith("a photo of ") else text

        return [_unit(self.angles.get(bare(t), 1.2)) for t in texts]


def _textured_frame():
    """A frame with enough structure that the pixel statistics stay quiet.

    A flat probe frame is, quite correctly, measured as an empty room, and
    that would mask what these tests are about.
    """

    from vidfactory.visual_analysis import Frame

    width = height = 48
    data = bytearray()
    for y in range(height):
        for x in range(width):
            seed = (x * 37 + y * 91) % 255
            data += bytes((
                60 + (seed * 3) % 180,
                50 + (seed * 7) % 170,
                40 + (seed * 11) % 160,
            ))
    return Frame(width, height, bytes(data), "probe")


def _analysis(angles, query="a styled living room"):
    from vidfactory.visual_analysis import VisualAnalyzer

    analyzer = VisualAnalyzer(model=_AngleBackend(angles), frames_per_clip=1)
    return analyzer.analyze([_textured_frame()], query=query)


def test_a_clip_matching_its_own_prompt_scores_high():
    prompt = "a styled living room"
    angles = {prompt: 0.30}
    angles.update({d: 0.55 for d in DISTRACTOR_PROMPTS})
    assert _analysis(angles).semantic_match > 0.75


def test_a_clip_matching_a_distractor_better_scores_low():
    prompt = "a styled living room"
    angles = {prompt: 0.60}
    angles.update({d: 0.58 for d in DISTRACTOR_PROMPTS})
    angles[DISTRACTOR_PROMPTS[0]] = 0.30
    assert _analysis(angles).semantic_match < 0.35


def test_an_ordinary_interior_does_not_collect_negative_flags():
    """The failure this replaces: hundredths of a cosine becoming certainty."""

    angles = {c: 0.50 for c in POSITIVE_CONCEPTS}
    # Every negative concept is very slightly closer than the best positive,
    # which under a temperature-100 softmax was enough to read as certain.
    angles.update({text: 0.499 for text, _ in NEGATIVE_CONCEPTS})
    angles["a styled living room"] = 0.50
    angles.update({d: 0.60 for d in DISTRACTOR_PROMPTS})
    analysis = _analysis(angles)
    assert not analysis.penalised_flags, analysis.flags


def test_a_clearly_negative_frame_is_still_flagged():
    angles = {c: 0.90 for c in POSITIVE_CONCEPTS}
    angles.update({text: 0.85 for text, _ in NEGATIVE_CONCEPTS})
    plastic = NEGATIVE_CONCEPTS[1][0]
    assert NEGATIVE_CONCEPTS[1][1] == "plastic_covered_furniture"
    angles[plastic] = 0.05          # far closer to the image than anything else
    angles["a styled living room"] = 0.9
    angles.update({d: 0.9 for d in DISTRACTOR_PROMPTS})
    analysis = _analysis(angles)
    assert analysis.flags.get("plastic_covered_furniture", 0) > 0.6


def test_a_negative_concept_that_merely_ties_a_positive_is_not_evidence():
    """The floor bug: every clip carried construction at 0.2 to 0.44.

    A margin ramp that starts below zero turns "no better than the positives"
    into a fifth of a flag, and eleven of those multiply premium_visual_score
    down to nothing.
    """

    angles = {c: 0.50 for c in POSITIVE_CONCEPTS}
    angles.update({text: 0.50 for text, _ in NEGATIVE_CONCEPTS})
    angles["a styled living room"] = 0.50
    angles.update({d: 0.50 for d in DISTRACTOR_PROMPTS})
    analysis = _analysis(angles)
    assert not any(
        analysis.flags.get(flag, 0) for _, flag in NEGATIVE_CONCEPTS
    ), analysis.flags
    assert analysis.premium_visual_score > 0.5
