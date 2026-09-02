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

def _api_headers() -> dict[str, str]:
    """Authenticate GitHub API calls when a token is available.

    Unauthenticated API access from a GitHub Actions runner shares a 60
    requests/hour quota across the whole runner pool, so it returns 403 far
    more often than not. ``GITHUB_TOKEN`` is always present in Actions.
    """

    headers = {"User-Agent": "vidfactory/1.0", "Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _latest_release_tag() -> str | None:
    """Find the newest llama.cpp release tag without using the API.

    ``/releases/latest`` on github.com redirects to ``/releases/tag/bNNNN``,
    which needs no authentication and is not rate limited, so it works when
    the API refuses.
    """

    request = urllib.request.Request(
        "https://github.com/ggml-org/llama.cpp/releases/latest",
        headers={"User-Agent": "vidfactory/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            final_url = response.geturl()
    except Exception as exc:
        log.debug("Could not resolve the latest release tag: %s", exc)
        return None
    match = re.search(r"/releases/tag/([A-Za-z0-9._-]+)", final_url or "")
    return match.group(1) if match else None


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

    asset_url = _find_release_asset()
    if not asset_url:
        log.warning(
            "Could not locate a prebuilt llama.cpp build for this runner; "
            "the optional local model will be skipped"
        )
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


def _rank_asset(name: str) -> int:
    """Score a release asset for "prebuilt CPU build for x86-64 Linux".

    llama.cpp renames its release assets from time to time, so this scores
    candidates instead of pattern-matching one exact filename. Anything
    scoring zero is unusable here.
    """

    name = name.lower()
    if not name.endswith(".zip"):
        return 0
    if any(bad in name for bad in ("arm64", "aarch64", "macos", "win", "android", "musl")):
        return 0
    if "ubuntu" not in name and "linux" not in name:
        return 0

    score = 10
    if "x64" in name or "x86_64" in name or "amd64" in name:
        score += 5
    # A plain CPU build is ideal; accelerator builds still run on CPU but
    # carry driver dependencies a runner may not have.
    if any(gpu in name for gpu in ("cuda", "hip", "sycl", "musa")):
        score -= 8
    elif "vulkan" in name:
        score -= 4
    return max(0, score)


def _find_release_asset() -> str | None:
    """URL of a prebuilt CPU llama.cpp build for x86-64 Linux, or None."""

    # Strategy 1: the API, authenticated when a token is available.
    try:
        request = urllib.request.Request(LLAMA_RELEASE_API, headers=_api_headers())
        with urllib.request.urlopen(request, timeout=60) as response:
            release = json.loads(response.read().decode("utf-8"))
        names = [str(a.get("name", "")) for a in release.get("assets", [])]
        ranked = sorted(
            ((_rank_asset(n), n, a) for n, a in zip(names, release.get("assets", []))),
            key=lambda row: row[0],
            reverse=True,
        )
        if ranked and ranked[0][0] > 0:
            log.info("Using llama.cpp asset %s", ranked[0][1])
            return str(ranked[0][2].get("browser_download_url"))
        log.warning(
            "No usable Linux x86-64 asset in llama.cpp release %s. Available: %s",
            release.get("tag_name", "?"),
            ", ".join(names[:12]) or "none",
        )
    except Exception as exc:
        log.info("llama.cpp release API unavailable (%s); trying the direct URL", exc)

    # Strategy 2: construct the download URL from the redirect tag. No API,
    # no authentication, no rate limit.
    tag = _latest_release_tag()
    if not tag:
        log.debug("Could not determine the latest llama.cpp tag")
        return None
    for pattern in (
        f"llama-{tag}-bin-ubuntu-x64.zip",
        f"llama-{tag}-bin-ubuntu-vulkan-x64.zip",
        f"llama-{tag}-bin-linux-x64.zip",
    ):
        url = f"https://github.com/ggml-org/llama.cpp/releases/download/{tag}/{pattern}"
        try:
            probe = urllib.request.Request(
                url, method="HEAD", headers={"User-Agent": "vidfactory/1.0"}
            )
            with urllib.request.urlopen(probe, timeout=30) as response:
                if response.status < 400:
                    log.info("Using llama.cpp asset %s", pattern)
                    return url
        except Exception:
            continue
    log.debug("None of the constructed asset URLs resolved for tag %s", tag)
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
    "<|im_start|>system\n{system}<|im_end|>\n"
    "<|im_start|>user\n{instruction}<|im_end|>\n"
    "<|im_start|>assistant\n"
)

WRITER_SYSTEM = (
    "You are a professional YouTube scriptwriter for a US home decor and "
    "interior design channel. You write original, warm, practical narration in "
    "American English. You never use emoji, headings, stage directions, bullet "
    "points or engagement bait. You write flowing spoken prose only."
)

ANALYST_SYSTEM = (
    "You are a precise editorial assistant. You answer exactly in the format "
    "requested, with no preamble, no explanation and no extra words."
)


def _sanitize(text: str) -> str:
    """Strip anything that would sound wrong when spoken aloud."""

    text = re.sub(r"<\|.*?\|>", " ", text)
    text = re.sub(r"[*#`_>\[\]]+", " ", text)
    text = re.sub(r"^\s*[-\u2022\d]+[.)]\s*", "", text, flags=re.MULTILINE)
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


class LLMAssistant:
    """Small, focused jobs a local model does better than a template.

    Every method is best-effort: on timeout, refusal or unusable output the
    caller keeps whatever the deterministic engine produced. Nothing here is
    allowed to fail a render.
    """

    def __init__(self, runner: "LlamaRunner", budget_seconds: float = 90.0) -> None:
        self.runner = runner
        self.budget_seconds = float(budget_seconds)
        self.calls = 0
        self.failures = 0

    # ------------------------------------------------------------------
    def _ask(
        self,
        instruction: str,
        system: str,
        max_tokens: int,
        timeout: float | None = None,
    ) -> str:
        self.calls += 1
        prompt = PROMPT_TEMPLATE.format(system=system, instruction=instruction)
        try:
            return self.runner.complete(
                prompt,
                max_tokens=max_tokens,
                timeout=timeout or self.budget_seconds,
            )
        except LLMUnavailable as exc:
            self.failures += 1
            log.debug("Model call failed: %s", exc)
            return ""

    # ------------------------------------------------------------------
    def rewrite_section(self, text: str, context: str, target_words: int) -> str:
        """Rephrase one section so consecutive videos do not sound identical."""

        instruction = (
            f"Rewrite the following home decor narration in about {target_words} "
            f"words. Keep every fact, measurement and recommendation exactly as "
            f"given - do not invent new ones. Vary the sentence rhythm so it does "
            f"not sound templated. {context}\n\nNarration:\n{text}"
        )
        out = _sanitize(self._ask(instruction, WRITER_SYSTEM, int(target_words * 2.0) + 80))
        # Guard against the model truncating or padding badly.
        if len(out.split()) < max(20, target_words * 0.45):
            return ""
        if len(out.split()) > target_words * 2.2:
            return ""
        return out

    def strengthen_hook(self, title: str, current: str, promise: str) -> str:
        """Rewrite the opening so the first fifteen seconds create curiosity."""

        instruction = (
            f"Write the opening 45 to 65 words of narration for a video titled "
            f"'{title}'. The video promises to {promise}. Open with a specific, "
            f"concrete observation that makes the viewer curious - name the "
            f"problem they recognize. Do not greet the audience, do not mention "
            f"the channel, do not ask for likes or subscriptions, and do not say "
            f"'in this video'. Go straight into the idea.\n\n"
            f"For reference, the current opening is:\n{current}"
        )
        out = _sanitize(self._ask(instruction, WRITER_SYSTEM, 180))
        words = len(out.split())
        if not 25 <= words <= 130:
            return ""
        lowered = out.lower()
        if any(bad in lowered for bad in ("subscribe", "like and", "welcome back", "hey guys")):
            return ""
        return out

    def check_alignment(self, title: str, idea: str, promise: str) -> bool | None:
        """Ask whether an idea really delivers the title's promise.

        Returns True, False, or None when the model gave no usable answer, in
        which case the caller keeps the deterministic verdict.
        """

        instruction = (
            f"A video is titled '{title}'. It promises to {promise}.\n"
            f"Idea: {idea}\n\n"
            f"Does this idea directly deliver that promise? "
            f"Answer with exactly one word: YES or NO."
        )
        out = self._ask(instruction, ANALYST_SYSTEM, 6, timeout=min(self.budget_seconds, 45.0))
        text = re.sub(r"[^a-z]", " ", out.lower())
        if " yes " in f" {text} ":
            return True
        if " no " in f" {text} ":
            return False
        return None

    def suggest_queries(self, narration: str, existing: Sequence[str], count: int = 4) -> list[str]:
        """Propose extra stock-footage search phrases for one narration line."""

        instruction = (
            f"Narration line: {narration}\n\n"
            f"Write {count} short stock-footage search phrases that would find "
            f"video clips showing exactly what this line describes. Each phrase "
            f"is three to six words, lowercase, one per line, no numbering, no "
            f"punctuation. Be specific about the object and the room. "
            f"Do not repeat these: {', '.join(existing[:4])}"
        )
        out = self._ask(instruction, ANALYST_SYSTEM, 90, timeout=min(self.budget_seconds, 60.0))
        queries: list[str] = []
        for line in out.splitlines():
            cleaned = re.sub(r"[^a-z0-9 ]+", " ", line.lower())
            cleaned = re.sub(r"\s+", " ", cleaned).strip()
            if 2 <= len(cleaned.split()) <= 8 and cleaned not in queries:
                queries.append(cleaned)
        return queries[:count]


class LLMScriptEngine:
    """Uses a local model to raise script quality, never to enable it.

    The deterministic template engine still supplies the structure, the ideas,
    the facts and the visual queries. The model rewrites prose, sharpens the
    hook and second-guesses title alignment. Every one of those is optional and
    individually recoverable, which is what keeps a slow runner from turning
    into a failed render.
    """

    name = "llm"

    def __init__(self, settings: dict[str, Any], words_per_minute: float = 150.0) -> None:
        self.settings = settings or {}
        self.words_per_minute = float(words_per_minute)
        self.budget_seconds = float(self.settings.get("max_seconds_per_call", 120))
        self.total_budget = float(self.settings.get("max_total_seconds", 900))

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
        self.assistant = LLMAssistant(self.runner, self.budget_seconds)
        log.info("Local model ready: %s", model.name)

    # ------------------------------------------------------------------
    def generate(self, topic: Topic, duration_minutes: float, fallback: Any) -> Any:
        """Improve a template-planned script section by section."""

        base = fallback.generate(topic, duration_minutes)
        started = time.time()
        rewritten = 0
        checked = 0
        dropped = 0

        def remaining() -> float:
            return self.total_budget - (time.time() - started)

        # 1. The hook earns the most from a model, so it goes first while
        #    there is definitely budget left.
        if remaining() > 60 and base.sections:
            intro = base.sections[0]
            improved = self.assistant.strengthen_hook(
                base.title, intro.text, base.promise_label or "help the viewer"
            )
            if improved:
                # Keep whatever the template said after the opening hook.
                tail = " ".join(intro.text.split(". ")[2:]).strip()
                intro.text = f"{improved} {tail}".strip()
                rewritten += 1
                log.info("Model strengthened the opening hook")

        # 2. Second-guess title alignment on the ideas that scored lowest.
        if bool(self.settings.get("check_alignment", True)) and base.promise_key != "general":
            items = base.items()
            for section in items:
                if remaining() < 90 or checked >= int(self.settings.get("max_alignment_checks", 12)):
                    break
                tip = section.tip or {}
                checked += 1
                verdict = self.assistant.check_alignment(
                    base.title, str(tip.get("title", "")), base.promise_label
                )
                if verdict is False:
                    section.flagged_off_promise = True
                    dropped += 1
            if dropped:
                log.info(
                    "Model flagged %d of %d checked ideas as off-promise", dropped, checked
                )

        # 3. Rewrite item prose while budget allows, longest sections first so
        #    the most template-sounding parts benefit most.
        for section in sorted(base.items(), key=lambda s: -s.word_count):
            if remaining() < self.budget_seconds + 20:
                break
            improved = self.assistant.rewrite_section(
                section.text,
                context=f"This is idea number {section.index} in '{base.title}'.",
                target_words=section.word_count,
            )
            if improved:
                section.text = improved
                rewritten += 1

        if rewritten == 0:
            raise LLMUnavailable("the model did not produce any usable output")

        base.engine = f"llm+template ({rewritten} sections improved by the model)"
        log.info(
            "Model improved %d sections in %.0fs (%d calls, %d failed)",
            rewritten,
            time.time() - started,
            self.assistant.calls,
            self.assistant.failures,
        )
        return base


# ---------------------------------------------------------------------------
# Feasibility benchmark
# ---------------------------------------------------------------------------

def benchmark(settings: dict[str, Any] | None = None) -> dict[str, Any]:
    """Measure whether this machine can realistically run the local model.

    Used by CI to decide whether ``script.llm`` is worth enabling by default,
    and by ``vidfactory doctor`` to explain why it is or is not being used.
    """

    settings = dict(settings or {})
    result: dict[str, Any] = {"available": False}
    started = time.time()

    binary = find_llama_binary()
    result["binary"] = str(binary) if binary else ""
    if binary is None:
        result["reason"] = (
            "no llama.cpp binary could be obtained (release lookup failed - "
            "set GITHUB_TOKEN, or check outbound access to github.com)"
        )
        return result

    model = find_model(
        str(settings.get("model_repo", "Qwen/Qwen2.5-1.5B-Instruct-GGUF")),
        str(settings.get("model_file", "qwen2.5-1.5b-instruct-q4_k_m.gguf")),
    )
    result["model"] = str(model) if model else ""
    if model is None:
        result["reason"] = (
            "no GGUF model could be obtained (check outbound access to "
            "huggingface.co)"
        )
        return result
    result["model_mb"] = round(model.stat().st_size / 1_000_000, 1)
    result["provision_seconds"] = round(time.time() - started, 1)

    runner = LlamaRunner(
        binary,
        model,
        context_size=int(settings.get("context_size", 2048)),
        threads=int(settings.get("threads", 0)),
    )
    assistant = LLMAssistant(runner, budget_seconds=float(settings.get("benchmark_timeout", 240)))

    sample = (
        "Hang your curtains close to the ceiling rather than to the window "
        "frame. The eye reads the top of the rod as the top of the wall, so a "
        "high rod stretches the whole room upward."
    )
    call_started = time.time()
    rewritten = assistant.rewrite_section(sample, context="Test call.", target_words=45)
    elapsed = time.time() - call_started

    result["rewrite_seconds"] = round(elapsed, 1)
    result["rewrite_words"] = len(rewritten.split())
    result["words_per_second"] = round(len(rewritten.split()) / elapsed, 2) if elapsed else 0.0
    result["sample_output"] = rewritten[:300]
    result["available"] = bool(rewritten)
    if not rewritten:
        result["reason"] = "the model produced no usable output within the timeout"
    return result
