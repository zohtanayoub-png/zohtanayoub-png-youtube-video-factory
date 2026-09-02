"""Optional local LLM script generation through llama.cpp.

This module is entirely opt-in (``script.llm.enabled: true``). It exists so
the factory can produce fully model-written narration without any paid API,
but it is never required: every failure path degrades to the template engine.

How it works
------------
1. A prebuilt ``llama.cpp`` CPU binary is downloaded from the project's GitHub
   releases (or an existing ``llama-cli`` / ``llama-server`` on PATH is used).
2. A small quantized GGUF instruct model is downloaded from Hugging Face.
3. Each script section is generated with a bounded wall-clock budget. If a
   section times out or comes back unusable, that section falls back to the
   template engine, so a slow runner degrades gracefully instead of failing.

Both downloads are cached (``.cache/llm``) and the GitHub Actions workflow
caches that directory between runs.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, Sequence

from .logging_utils import get_logger
from .topic_engine import Topic

log = get_logger("LLM")

CACHE_DIR = Path(os.environ.get("VIDFACTORY_CACHE", ".cache")) / "llm"
LLAMA_RELEASE_API = "https://api.github.com/repos/ggml-org/llama.cpp/releases/latest"
HF_TEMPLATE = "https://huggingface.co/{repo}/resolve/main/{file}"


class LLMUnavailable(RuntimeError):
    """Raised when the local LLM cannot be prepared or used."""


# ---------------------------------------------------------------------------
# Binary + model provisioning
# ---------------------------------------------------------------------------

def _download(url: str, target: Path, timeout: int = 900) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and target.stat().st_size > 1024:
        return target
    tmp = target.with_suffix(target.suffix + ".part")
    log.info("Downloading %s", target.name)
    request = urllib.request.Request(url, headers={"User-Agent": "vidfactory/1.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response, open(tmp, "wb") as handle:
        shutil.copyfileobj(response, handle, length=1024 * 512)
    tmp.replace(target)
    return target


def find_llama_binary() -> Path | None:
    """Locate a usable ``llama-cli`` binary, downloading one if necessary."""

    for name in ("llama-cli", "llama", "main"):
        found = shutil.which(name)
        if found:
            return Path(found)

    cached = CACHE_DIR / "bin" / "llama-cli"
    if cached.exists():
        return cached

    try:
        request = urllib.request.Request(
            LLAMA_RELEASE_API, headers={"User-Agent": "vidfactory/1.0"}
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            release = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        log.warning("Could not query llama.cpp releases: %s", exc)
        return None

    asset_url = None
    for asset in release.get("assets", []):
        name = str(asset.get("name", "")).lower()
        if name.endswith(".zip") and "ubuntu" in name and "x64" in name and "cuda" not in name:
            asset_url = asset.get("browser_download_url")
            break
    if not asset_url:
        log.warning("No suitable prebuilt llama.cpp asset found for this runner")
        return None

    archive = CACHE_DIR / "llama.zip"
    try:
        _download(asset_url, archive)
        extract_dir = CACHE_DIR / "extract"
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(extract_dir)
    except Exception as exc:
        log.warning("Failed to unpack llama.cpp: %s", exc)
        return None

    for candidate in extract_dir.rglob("llama-cli"):
        cached.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(candidate, cached)
        cached.chmod(0o755)
        # Shared libraries ship alongside the binary.
        for lib in candidate.parent.glob("*.so*"):
            shutil.copy2(lib, cached.parent / lib.name)
        return cached

    log.warning("llama-cli was not present in the downloaded archive")
    return None


def find_model(repo: str, filename: str) -> Path | None:
    """Return a local GGUF path, downloading from Hugging Face when needed."""

    override = os.environ.get("VIDFACTORY_GGUF")
    if override and Path(override).exists():
        return Path(override)

    target = CACHE_DIR / "models" / filename
    if target.exists() and target.stat().st_size > 10 * 1024 * 1024:
        return target
    try:
        return _download(HF_TEMPLATE.format(repo=repo, file=filename), target)
    except Exception as exc:
        log.warning("Could not download the GGUF model: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class LlamaRunner:
    """Thin subprocess wrapper around ``llama-cli`` in single-shot mode."""

    def __init__(
        self,
        binary: Path,
        model: Path,
        context_size: int = 4096,
        threads: int = 0,
        temperature: float = 0.8,
    ) -> None:
        self.binary = Path(binary)
        self.model = Path(model)
        self.context_size = int(context_size)
        self.threads = int(threads) or (os.cpu_count() or 2)
        self.temperature = float(temperature)

    def complete(self, prompt: str, max_tokens: int = 512, timeout: float = 240.0) -> str:
        command = [
            str(self.binary),
            "-m", str(self.model),
            "-c", str(self.context_size),
            "-t", str(self.threads),
            "-n", str(int(max_tokens)),
            "--temp", str(self.temperature),
            "--no-display-prompt",
            "-no-cnv",
            "-p", prompt,
        ]
        env = dict(os.environ)
        env["LD_LIBRARY_PATH"] = f"{self.binary.parent}:{env.get('LD_LIBRARY_PATH', '')}"
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
                check=False,
            )
        except subprocess.TimeoutExpired:
            raise LLMUnavailable("llama-cli timed out") from None
        if result.returncode != 0:
            raise LLMUnavailable(
                f"llama-cli exited with {result.returncode}: {result.stderr[-400:]}"
            )
        return result.stdout.strip()


PROMPT_TEMPLATE = (
    "<|im_start|>system\n"
    "You are a professional YouTube scriptwriter for a US home decor and interior "
    "design channel. You write original, warm, practical narration in American "
    "English. You never use emoji, headings, stage directions, bullet points or "
    "engagement bait. You write flowing spoken prose only.<|im_end|>\n"
    "<|im_start|>user\n{instruction}<|im_end|>\n"
    "<|im_start|>assistant\n"
)


def _sanitize(text: str) -> str:
    """Strip anything that would sound wrong when spoken aloud."""

    text = re.sub(r"<\|.*?\|>", " ", text)
    text = re.sub(r"[*#`_>\[\]]+", " ", text)
    text = re.sub(r"^\s*[-•\d]+[.)]\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"\(.*?\)", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    text = re.sub(r"([,.;:!?]){2,}", r"\1", text)
    # Drop a trailing partial sentence caused by hitting the token limit.
    if text and text[-1] not in ".!?":
        cut = max(text.rfind("."), text.rfind("!"), text.rfind("?"))
        if cut > 40:
            text = text[: cut + 1]
    return text


class LLMScriptEngine:
    """Generates each script section with a local model, per-section fallback."""

    name = "llm"

    def __init__(self, settings: dict[str, Any], words_per_minute: float = 150.0) -> None:
        self.settings = settings or {}
        self.words_per_minute = float(words_per_minute)
        self.budget_seconds = float(self.settings.get("max_seconds_per_call", 240))

        binary = find_llama_binary()
        if binary is None:
            raise LLMUnavailable("no llama.cpp binary available on this runner")
        model = find_model(
            str(self.settings.get("model_repo", "")),
            str(self.settings.get("model_file", "")),
        )
        if model is None:
            raise LLMUnavailable("no GGUF model available on this runner")

        self.runner = LlamaRunner(
            binary,
            model,
            context_size=int(self.settings.get("context_size", 4096)),
            threads=int(self.settings.get("threads", 0)),
            temperature=float(self.settings.get("temperature", 0.8)),
        )
        log.info("Local model ready: %s", model.name)

    # ------------------------------------------------------------------
    def _write(self, instruction: str, words: int) -> str:
        prompt = PROMPT_TEMPLATE.format(instruction=instruction)
        raw = self.runner.complete(
            prompt,
            max_tokens=int(words * 2.0) + 80,
            timeout=self.budget_seconds,
        )
        return _sanitize(raw)

    def generate(self, topic: Topic, duration_minutes: float, fallback: Any) -> Any:
        """Rewrite a template-planned script section by section with the model.

        The template engine supplies the structure, the item list and the
        visual queries; the model supplies the prose. Any section the model
        fails on keeps its template text, so the result is always complete.
        """

        base = fallback.generate(topic, duration_minutes)
        started = time.time()
        total_budget = max(self.budget_seconds, 60.0) * 6
        rewritten = 0

        for section in base.sections:
            if time.time() - started > total_budget:
                log.warning("LLM time budget exhausted; keeping template text for the rest")
                break
            target_words = max(45, section.word_count)
            if section.kind == "item" and section.tip:
                instruction = (
                    f"Write about {target_words} words of narration for one numbered idea in a "
                    f"video called '{base.title}'. The idea is number {section.index}: "
                    f"{section.tip['title']}. Explain why it works and exactly how to do it. "
                    f"Start with 'Number {section.index}.' Use these facts and do not invent "
                    f"different ones: {section.tip['why']} {section.tip['how']}"
                )
            elif section.kind == "intro":
                instruction = (
                    f"Write about {target_words} words of opening narration for a video called "
                    f"'{base.title}'. Open with a hook, say what the viewer will learn, and "
                    f"mention that there are {len(base.items())} ideas. Do not greet the "
                    f"audience by name and do not ask for likes."
                )
            else:
                instruction = (
                    f"Write about {target_words} words of closing narration for a video called "
                    f"'{base.title}'. Summarise the underlying principle and end with one short, "
                    f"low-key invitation to subscribe."
                )
            try:
                text = self._write(instruction, target_words)
            except LLMUnavailable as exc:
                log.warning("Section %s fell back to the template (%s)", section.heading, exc)
                continue
            if len(text.split()) >= max(25, target_words * 0.4):
                section.text = text
                rewritten += 1
            else:
                log.debug("Model output too short for %s; keeping template text", section.heading)

        if rewritten == 0:
            raise LLMUnavailable("the model did not produce any usable sections")

        base.engine = f"llm+template ({rewritten}/{len(base.sections)} sections from the model)"
        log.info("Model wrote %d of %d sections", rewritten, len(base.sections))
        return base
