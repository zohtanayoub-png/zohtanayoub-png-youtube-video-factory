"""Optional CPU image/text model for zero-shot frame understanding.

:mod:`vidfactory.visual_analysis` measures pixels and always works. This
module adds the other half: a small CLIP-family model that scores the same
frames against *written* concepts, so "furniture covered with plastic
sheeting" and "an empty unfurnished room" can be recognised as ideas rather
than inferred from a histogram.

Design constraints, all of them the same ones the rest of the project lives
under:

* **Free and open source.** CLIP weights under an MIT / Apache licence,
  executed locally with ONNX Runtime. No paid vision API, ever.
* **CPU only.** MobileCLIP-S0 is about 12 MB of quantized vision weights and
  scores a 224x224 frame in tens of milliseconds on a GitHub Actions runner.
* **Never required.** Provisioning a model on a runner is exactly the kind of
  thing that fails - the llama.cpp experience in :mod:`vidfactory.llm` is the
  cautionary tale - so every failure path here returns ``None`` and the
  pipeline carries on with pixel statistics, saying so in the report.

Nothing is downloaded unless ``visual.model.enabled`` is true. The cache
directory is shared with the rest of the project (``.cache/visual``) and the
GitHub Actions workflows cache it between runs.
"""

from __future__ import annotations

import json
import math
import os
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Sequence

from .logging_utils import get_logger

log = get_logger("VISMODEL")

CACHE_DIR = Path(os.environ.get("VIDFACTORY_CACHE", ".cache")) / "visual"
HF_TEMPLATE = "https://huggingface.co/{repo}/resolve/main/{file}"

#: Default model. Apple publishes MobileCLIP under an Apple-ASCL licence that
#: permits research and commercial use; the ONNX export used here is the
#: transformers.js one. It is small enough to download and cache on a runner
#: in a few seconds.
DEFAULT_REPO = "Xenova/mobileclip_s0"
DEFAULT_VISION_FILE = "onnx/vision_model_quantized.onnx"
DEFAULT_TEXT_FILE = "onnx/text_model_quantized.onnx"
DEFAULT_TOKENIZER_FILE = "tokenizer.json"
DEFAULT_IMAGE_SIZE = 256

#: A well-known fallback with the same interface, in case the default repo
#: layout changes. Both are CLIP-architecture dual encoders.
FALLBACK_REPO = "Xenova/clip-vit-base-patch32"
FALLBACK_VISION_FILE = "onnx/vision_model_quantized.onnx"
FALLBACK_TEXT_FILE = "onnx/text_model_quantized.onnx"
FALLBACK_IMAGE_SIZE = 224

#: CLIP's image normalization constants.
IMAGE_MEAN = (0.48145466, 0.4578275, 0.40821073)
IMAGE_STD = (0.26862954, 0.26130258, 0.27577711)
CONTEXT_LENGTH = 77


class VisualModelUnavailable(RuntimeError):
    """Raised internally when a model cannot be prepared. Never escapes."""


# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _byte_encoder() -> dict[int, str]:
    """CLIP's reversible byte-to-unicode mapping."""

    printable = (
        list(range(ord("!"), ord("~") + 1))
        + list(range(ord("\xa1"), ord("\xac") + 1))
        + list(range(ord("\xae"), ord("\xff") + 1))
    )
    mapping = {b: chr(b) for b in printable}
    spare = 0
    for b in range(256):
        if b not in mapping:
            mapping[b] = chr(256 + spare)
            spare += 1
    return mapping


class ClipTokenizer:
    """The CLIP byte-pair tokenizer, read from a Hugging Face tokenizer.json.

    Implemented here rather than pulled from ``transformers`` because the only
    thing needed at runtime is ``text -> 77 token ids``, and adding a 40 MB
    dependency tree (plus torch) to a pipeline that must survive on a free
    runner is a poor trade.
    """

    #: CLIP's pre-tokenizer, restricted to ASCII (the concept prompts and the
    #: narration this project generates are American English).
    PATTERN = re.compile(
        r"<\|startoftext\|>|<\|endoftext\|>|'s|'t|'re|'ve|'m|'ll|'d"
        r"|[a-z]+|[0-9]|[^\sa-z0-9]+",
        re.IGNORECASE,
    )

    def __init__(self, vocab: dict[str, int], merges: Sequence[str]) -> None:
        self.vocab = dict(vocab)
        self.ranks = {tuple(m.split(" ")): i for i, m in enumerate(merges) if " " in m}
        self.byte_encoder = _byte_encoder()
        self.start = self.vocab.get("<|startoftext|>", 49406)
        self.end = self.vocab.get("<|endoftext|>", 49407)
        self.cache: dict[str, list[str]] = {}

    # ------------------------------------------------------------------
    @classmethod
    def from_file(cls, path: str | Path) -> "ClipTokenizer":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        model = payload.get("model") or {}
        vocab = model.get("vocab") or {}
        merges = model.get("merges") or []
        if merges and isinstance(merges[0], list):
            merges = [" ".join(pair) for pair in merges]
        if not vocab or not merges:
            raise VisualModelUnavailable(f"{path} is not a usable BPE tokenizer")
        return cls(vocab, merges)

    # ------------------------------------------------------------------
    def _bpe(self, token: str) -> list[str]:
        if token in self.cache:
            return self.cache[token]
        word = list(token[:-1]) + [token[-1] + "</w>"]
        while len(word) > 1:
            pairs = {(word[i], word[i + 1]) for i in range(len(word) - 1)}
            candidate = min(pairs, key=lambda p: self.ranks.get(p, math.inf))
            if candidate not in self.ranks:
                break
            first, second = candidate
            merged: list[str] = []
            index = 0
            while index < len(word):
                if (
                    index < len(word) - 1
                    and word[index] == first
                    and word[index + 1] == second
                ):
                    merged.append(first + second)
                    index += 2
                else:
                    merged.append(word[index])
                    index += 1
            word = merged
        self.cache[token] = word
        return word

    def encode(self, text: str) -> list[int]:
        cleaned = unicodedata.normalize("NFC", str(text or "")).lower().strip()
        cleaned = re.sub(r"\s+", " ", cleaned)
        ids: list[int] = [self.start]
        for match in self.PATTERN.findall(cleaned):
            token = "".join(self.byte_encoder[b] for b in match.encode("utf-8"))
            for piece in self._bpe(token):
                if piece in self.vocab:
                    ids.append(self.vocab[piece])
        ids.append(self.end)
        if len(ids) > CONTEXT_LENGTH:
            ids = ids[: CONTEXT_LENGTH - 1] + [self.end]
        return ids + [0] * (CONTEXT_LENGTH - len(ids))


# ---------------------------------------------------------------------------
# Provisioning
# ---------------------------------------------------------------------------

@dataclass
class ModelFiles:
    repo: str
    vision: Path
    text: Path
    tokenizer: Path
    image_size: int


def _download(url: str, target: Path, timeout: float = 900.0) -> Path:
    from .http import download_file

    if target.exists() and target.stat().st_size > 0:
        return target
    download_file(url, target, timeout=timeout)
    log.info("cached %s (%.1f MB)", target.name, target.stat().st_size / 1e6)
    return target


def provision(
    repo: str = DEFAULT_REPO,
    vision_file: str = DEFAULT_VISION_FILE,
    text_file: str = DEFAULT_TEXT_FILE,
    tokenizer_file: str = DEFAULT_TOKENIZER_FILE,
    image_size: int = DEFAULT_IMAGE_SIZE,
    cache_dir: Path | None = None,
) -> ModelFiles:
    """Fetch (or reuse) the three files the backend needs."""

    root = Path(cache_dir or CACHE_DIR) / repo.replace("/", "__")
    files = ModelFiles(
        repo=repo,
        vision=_download(HF_TEMPLATE.format(repo=repo, file=vision_file), root / "vision.onnx"),
        text=_download(HF_TEMPLATE.format(repo=repo, file=text_file), root / "text.onnx"),
        tokenizer=_download(
            HF_TEMPLATE.format(repo=repo, file=tokenizer_file), root / "tokenizer.json"
        ),
        image_size=int(image_size),
    )
    return files


# ---------------------------------------------------------------------------
# The backend
# ---------------------------------------------------------------------------

class OnnxClipModel:
    """A CLIP dual encoder running on ONNX Runtime.

    The ONNX exports published for the same architecture differ in input
    names and in whether they want an attention mask, so the sessions are
    introspected rather than assumed. That is the difference between a
    backend that works with whatever export is current and one that breaks
    the day a repository is re-exported.
    """

    def __init__(self, files: ModelFiles, threads: int = 2) -> None:
        import onnxruntime                              # noqa: F401  (optional)

        options = onnxruntime.SessionOptions()
        options.intra_op_num_threads = max(1, int(threads))
        options.inter_op_num_threads = 1
        options.log_severity_level = 3
        self.vision = onnxruntime.InferenceSession(
            str(files.vision), options, providers=["CPUExecutionProvider"]
        )
        self.text = onnxruntime.InferenceSession(
            str(files.text), options, providers=["CPUExecutionProvider"]
        )
        self.tokenizer = ClipTokenizer.from_file(files.tokenizer)
        self.repo = files.repo
        self.image_size = self._detect_image_size(files.image_size)

    # ------------------------------------------------------------------
    @property
    def name(self) -> str:
        return f"onnx-clip:{self.repo}"

    def _detect_image_size(self, fallback: int) -> int:
        for meta in self.vision.get_inputs():
            shape = list(getattr(meta, "shape", []) or [])
            if len(shape) == 4 and isinstance(shape[-1], int) and shape[-1] > 32:
                return int(shape[-1])
        return int(fallback)

    @staticmethod
    def _pick(session: Any, *preferred: str) -> str:
        names = [i.name for i in session.get_inputs()]
        for candidate in preferred:
            if candidate in names:
                return candidate
        return names[0]

    @staticmethod
    def _embedding(outputs: Sequence[Any], session: Any) -> Any:
        """The pooled embedding, whichever position the export puts it in."""

        names = [o.name for o in session.get_outputs()]
        for wanted in ("image_embeds", "text_embeds", "embeds", "pooler_output"):
            if wanted in names:
                return outputs[names.index(wanted)]
        # Otherwise the first 2-D output is the embedding.
        for value in outputs:
            if getattr(value, "ndim", 0) == 2:
                return value
        return outputs[0]

    # ------------------------------------------------------------------
    def encode_images(self, frames: Sequence[Any]) -> list[list[float]]:
        import numpy as np

        edge = self.image_size
        batch = np.empty((len(frames), 3, edge, edge), dtype=np.float32)
        for index, frame in enumerate(frames):
            array = np.frombuffer(frame.pixels, dtype=np.uint8).astype(np.float32)
            array = array.reshape(frame.height, frame.width, 3) / 255.0
            if (frame.height, frame.width) != (edge, edge):
                rows = (np.arange(edge) * frame.height // edge).clip(0, frame.height - 1)
                cols = (np.arange(edge) * frame.width // edge).clip(0, frame.width - 1)
                array = array[rows][:, cols]
            for channel in range(3):
                array[:, :, channel] = (
                    array[:, :, channel] - IMAGE_MEAN[channel]
                ) / IMAGE_STD[channel]
            batch[index] = array.transpose(2, 0, 1)

        key = self._pick(self.vision, "pixel_values", "input", "images")
        outputs = self.vision.run(None, {key: batch})
        return [list(map(float, row)) for row in self._embedding(outputs, self.vision)]

    def encode_texts(self, texts: Sequence[str]) -> list[list[float]]:
        import numpy as np

        ids = np.array([self.tokenizer.encode(t) for t in texts], dtype=np.int64)
        feed: dict[str, Any] = {
            self._pick(self.text, "input_ids", "text", "input"): ids
        }
        names = [i.name for i in self.text.get_inputs()]
        if "attention_mask" in names:
            feed["attention_mask"] = (ids != 0).astype(np.int64)
        outputs = self.text.run(None, feed)
        return [list(map(float, row)) for row in self._embedding(outputs, self.text)]


# ---------------------------------------------------------------------------
# Loading, with every failure turned into "carry on without it"
# ---------------------------------------------------------------------------

#: Settings fingerprints that have already failed, so a second call in the
#: same process does not repeat a download that is not going to work.
_FAILED: set[str] = set()


def load_model(settings: dict[str, Any] | None = None) -> Any | None:
    """Return a usable backend, or ``None``. Never raises."""

    settings = dict(settings or {})
    fingerprint = json.dumps(settings, sort_keys=True, default=str)
    if fingerprint in _FAILED:
        return None
    if not settings.get("enabled", True):
        log.info("visual model disabled by configuration")
        return None
    try:
        import onnxruntime  # noqa: F401
    except Exception:
        _FAILED.add(fingerprint)
        log.warning(
            "onnxruntime is not installed, so frames will be judged by pixel "
            "statistics alone. Install it with 'pip install onnxruntime' to "
            "enable CLIP concept scoring."
        )
        return None

    attempts = [
        (
            str(settings.get("repo", DEFAULT_REPO)),
            str(settings.get("vision_file", DEFAULT_VISION_FILE)),
            str(settings.get("text_file", DEFAULT_TEXT_FILE)),
            str(settings.get("tokenizer_file", DEFAULT_TOKENIZER_FILE)),
            int(settings.get("image_size", DEFAULT_IMAGE_SIZE)),
        )
    ]
    if settings.get("fallback", True):
        attempts.append(
            (FALLBACK_REPO, FALLBACK_VISION_FILE, FALLBACK_TEXT_FILE,
             DEFAULT_TOKENIZER_FILE, FALLBACK_IMAGE_SIZE)
        )

    for repo, vision_file, text_file, tokenizer_file, image_size in attempts:
        try:
            files = provision(
                repo, vision_file, text_file, tokenizer_file, image_size,
                cache_dir=settings.get("cache_dir"),
            )
            model = OnnxClipModel(files, threads=int(settings.get("threads", 2)))
            log.info("visual model ready: %s (%dpx)", model.name, model.image_size)
            return model
        except Exception as exc:
            log.warning("could not load visual model %s: %s", repo, exc)
    _FAILED.add(fingerprint)
    log.warning(
        "No CLIP backend available; frames will still be inspected, but with "
        "pixel statistics only."
    )
    return None


def benchmark(settings: dict[str, Any] | None = None) -> dict[str, Any]:
    """What actually happens on this machine - for ``vidfactory visual-check``."""

    import time

    from .visual_analysis import Frame, VisualAnalyzer

    report: dict[str, Any] = {"onnxruntime": False, "model": None, "ok": False}
    try:
        import onnxruntime

        report["onnxruntime"] = onnxruntime.__version__
    except Exception as exc:
        report["error"] = f"onnxruntime not importable: {exc}"

    started = time.time()
    model = load_model(settings)
    report["provision_seconds"] = round(time.time() - started, 2)
    report["model"] = getattr(model, "name", None)

    edge = int(getattr(model, "image_size", 64) or 64)
    frame = Frame(edge, edge, bytes(range(256)) * ((edge * edge * 3) // 256 + 1), "probe")
    frame = Frame(edge, edge, frame.pixels[: edge * edge * 3], "probe")
    analyzer = VisualAnalyzer(model=model, frames_per_clip=1)
    started = time.time()
    analysis = analyzer.analyze([frame], query="a bright living room")
    report["analysis_seconds"] = round(time.time() - started, 3)
    report["analysis_model"] = analysis.model
    report["semantic_source"] = analysis.semantic_source
    report["ok"] = analysis.analyzed
    return report
