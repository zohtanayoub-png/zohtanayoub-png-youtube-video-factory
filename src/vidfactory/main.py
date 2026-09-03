"""Command line entry point.

Examples::

    python -m vidfactory generate --topic "25 Small Living Room Ideas" --duration 20
    python -m vidfactory generate --auto-topic
    python -m vidfactory doctor
    python -m vidfactory topics --count 10
    python -m vidfactory demo --duration 0.75
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import Config, ConfigError, load_config, parse_bool
from .database import Database
from .logging_utils import get_logger, setup_logging

log = get_logger("MAIN")


def _overrides_from_args(args: argparse.Namespace) -> dict[str, object]:
    overrides: dict[str, object] = {}
    if getattr(args, "language", None):
        from .languages import resolve_language

        overrides["channel.language"] = resolve_language(args.language).code
    if getattr(args, "subtitle_style", None):
        overrides["subtitles.style"] = str(args.subtitle_style).strip().lower()
    if getattr(args, "duration", None):
        overrides["video.duration_minutes"] = float(args.duration)
    # "Automatic" is the dropdown's way of saying "no explicit voice", which
    # lets the content language choose one.
    if getattr(args, "voice", None) and str(args.voice).strip().lower() not in (
        "automatic", "auto",
    ):
        overrides["tts.voice"] = str(args.voice)
    if getattr(args, "tts_engine", None):
        overrides["tts.engine"] = str(args.tts_engine)
    if getattr(args, "script_engine", None):
        overrides["script.engine"] = str(args.script_engine)
    if getattr(args, "subtitles", None) is not None:
        overrides["subtitles.enabled"] = parse_bool(args.subtitles, True)
    if getattr(args, "burn_in", None) is not None:
        overrides["subtitles.burn_in"] = parse_bool(args.burn_in, False)
    if getattr(args, "resolution", None):
        overrides["video.resolution"] = str(args.resolution)
    if getattr(args, "fps", None):
        overrides["video.fps"] = int(args.fps)
    if getattr(args, "preset", None):
        overrides["video.preset"] = str(args.preset)
    if getattr(args, "transition", None):
        overrides["video.transition"] = str(args.transition)
    if getattr(args, "output", None):
        overrides["output.directory"] = str(args.output)
    if getattr(args, "local_clips", None):
        overrides["sources.local"] = True
        overrides["sources.local_directory"] = str(args.local_clips)
    if getattr(args, "only_local", False):
        overrides["sources.pexels"] = False
        overrides["sources.pixabay"] = False
        overrides["sources.local"] = True
    if getattr(args, "upload", None) is not None:
        overrides["youtube.upload_enabled"] = parse_bool(args.upload, False)
    if getattr(args, "items", None) and str(args.items).strip().isdigit():
        overrides["script.item_count"] = int(str(args.items).strip())
    if getattr(args, "mode", None):
        overrides["generation.mode"] = str(args.mode).strip().lower()
    if getattr(args, "privacy", None):
        overrides["youtube.privacy_status"] = str(args.privacy)
    return overrides


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def command_generate(args: argparse.Namespace) -> int:
    from .pipeline import PipelineError, VideoPipeline

    config = load_config(args.config, _overrides_from_args(args))
    database = Database(args.database)
    database.import_state(Path(args.state))

    run_id = args.run_id or datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    pipeline = VideoPipeline(
        config,
        database=database,
        run_id=run_id,
        workdir=args.workdir,
        state_dir=args.state,
    )

    topic = args.topic.strip() if args.topic else ""
    if args.auto_topic:
        topic = ""

    try:
        result = pipeline.run(topic_text=topic or None, upload=None)
    except PipelineError as exc:
        log.error("Generation failed: %s", exc)
        return 2

    print(json.dumps(result.summary(), indent=2))
    if args.github_output and os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as handle:
            handle.write(f"video_path={result.video_path}\n")
            handle.write(f"output_dir={result.output_dir}\n")
            handle.write(
                f"generation_id="
                f"{result.manifest.generation_id if result.manifest else ''}\n"
            )
            handle.write(f"title={result.script.title}\n")
            handle.write(f"duration_seconds={result.duration:.1f}\n")
            handle.write(f"youtube_id={result.youtube_id}\n")
    return 0


def command_demo(args: argparse.Namespace) -> int:
    """Render a short video from synthetic clips - no API keys required."""

    from .testassets import build_test_library, clips_needed_for

    clips_dir = Path(args.workdir or "work") / "demo_clips"
    # Generate one distinct clip per shot the timeline will need, so the demo
    # can satisfy the same zero-reuse rule a real run is held to.
    needed = clips_needed_for(float(args.duration or 1.0))
    build_test_library(clips_dir, count=needed, seconds=12.0, width=1920, height=1080)

    args.local_clips = str(clips_dir)
    args.only_local = True
    args.auto_topic = not bool(args.topic)
    return command_generate(args)


def command_topics(args: argparse.Namespace) -> int:
    from .topic_engine import TopicEngine

    config = load_config(args.config)
    database = Database(args.database)
    database.import_state(Path(args.state))
    engine = TopicEngine(
        history=database.topic_titles(),
        similarity_threshold=float(config.get("topics.similarity_threshold", 0.62)),
    )
    for _ in range(int(args.count)):
        topic = engine.generate()
        engine.history.append(topic.title)
        print(f"{topic.title}   [{topic.category}]")
    return 0


def command_doctor(args: argparse.Namespace) -> int:
    """Report whether this machine or runner can actually produce a video."""

    from .ffmpeg_utils import ffmpeg_available, ffmpeg_version
    from .knowledge import total_tips
    from .stock import build_providers
    from .tts import build_engine

    problems = 0
    print("=" * 62)
    print(" HOME DECOR VIDEO FACTORY - environment check")
    print("=" * 62)

    try:
        config = load_config(args.config)
        print(f"[ok]   config.yaml loaded ({config.get('channel.name')})")
        print(f"       target duration : {config.get('video.duration_minutes')} minutes")
        print(f"       resolution      : {config.get('video.resolution')} @ {config.fps} fps")
        print(f"       background music: {'ENABLED - INVALID' if config.music_enabled else 'disabled (correct)'}")
    except ConfigError as exc:
        print(f"[FAIL] config.yaml is invalid: {exc}")
        return 1

    if ffmpeg_available():
        print(f"[ok]   {ffmpeg_version()[:60]}")
    else:
        print("[FAIL] FFmpeg/ffprobe not found - install ffmpeg")
        problems += 1

    print(f"[ok]   knowledge base  : {total_tips()} curated ideas")

    try:
        engine = build_engine(
            engine=str(config.get("tts.engine", "auto")),
            voice=str(config.get("tts.voice")),
            fallback_voices=list(config.get("tts.fallback_voices", []) or []),
        )
        label = {"piper": "neural (best)", "espeak": "robotic fallback", "silent": "SILENT - no speech"}
        print(f"[{'ok' if engine.name != 'silent' else 'warn'}]   text to speech  : {engine.name} - {label.get(engine.name, '')}")
        if engine.name == "silent":
            problems += 1
    except Exception as exc:
        print(f"[FAIL] no TTS engine available: {exc}")
        problems += 1

    llm_settings = dict(config.get("script.llm", {}) or {})
    if llm_settings.get("enabled"):
        print(f"[ok]   script engine   : local model preferred "
              f"({llm_settings.get('model_file', '?')}), template fallback")
    else:
        print("[ok]   script engine   : template (deterministic, always works)")
        print("       local model     : disabled - run 'vidfactory llm-check' to test it here")

    if bool(config.get("visual.enabled", True)):
        model = dict(config.get("visual.model", {}) or {})
        backend = model.get("repo", "?") if model.get("enabled", True) else "off"
        print(f"[ok]   frame analysis  : on, {config.get('visual.frames_per_clip', 3)} "
              f"frames per candidate (CLIP backend: {backend})")
        print("       run 'vidfactory visual-check' to confirm the model loads here")
    else:
        print("[warn] frame analysis  : disabled - clips will be judged by caption only")

    providers = build_providers(dict(config.get("sources", {}) or {}))
    if providers:
        print(f"[ok]   stock providers : {', '.join(p.name for p in providers)}")
    else:
        print("[warn] no stock provider is usable - set PEXELS_API_KEY or enable sources.local")
        problems += 1

    for name in ("PEXELS_API_KEY", "PIXABAY_API_KEY"):
        print(f"       {name:<22}: {'set' if os.environ.get(name) else 'not set'}")
    youtube_ready = all(
        os.environ.get(k) for k in ("YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN")
    )
    print(f"       YouTube upload keys   : {'set' if youtube_ready else 'not set (upload disabled)'}")

    database = Database(args.database)
    database.import_state(Path(args.state))
    stats = database.stats()
    print(f"[ok]   history         : {stats['videos']} videos, {stats['topics']} topics, {stats['clips']} clips")

    print("=" * 62)
    print("READY" if problems == 0 else f"{problems} problem(s) found - see above")
    return 0 if problems == 0 else 1


def command_llm_check(args: argparse.Namespace) -> int:
    """Provision and benchmark the local model, then report whether it is viable.

    This is what decides whether ``script.llm`` is worth enabling: it downloads
    the llama.cpp binary and the GGUF, runs one real rewrite, and prints the
    measured speed. Run it in CI rather than guessing.
    """

    from .llm import benchmark

    config = load_config(args.config)
    settings = dict(config.get("script.llm", {}) or {})
    print("Benchmarking the local script model. The first run downloads ~1 GB.")
    result = benchmark(settings)

    print(json.dumps(result, indent=2)[:2000])
    if result.get("available"):
        seconds = float(result.get("rewrite_seconds", 0))
        print()
        print(f"[ok]   local model works: {result.get('model_mb')} MB, "
              f"{seconds:.1f}s for a 45 word rewrite "
              f"({result.get('words_per_second')} words/second)")
        budget = float(args.section_budget)
        if seconds <= budget:
            print(f"[ok]   within the {budget:.0f}s per-section budget - "
                  f"llm mode is practical on this machine")
            return 0
        print(f"[warn] slower than the {budget:.0f}s per-section budget - "
              f"llm mode would time out often here")
        return 3
    print(f"[FAIL] local model unavailable: {result.get('reason', 'unknown')}")
    return 1


def command_visual_check(args: argparse.Namespace) -> int:
    """Report what frame inspection can actually do on this machine.

    Pixel statistics always work. The CLIP backend has to be downloaded and
    executed, and whether that succeeds on a given runner is a fact to be
    measured rather than assumed - the same lesson ``llm-check`` exists for.
    """

    from .visual_model import benchmark

    config = load_config(args.config)
    settings = dict(config.get("visual.model", {}) or {})
    print("Checking frame inspection. The first run downloads the CLIP export.")
    result = benchmark(settings)
    print(json.dumps(result, indent=2)[:2000])
    print()
    if result.get("model"):
        print(f"[ok]   CLIP backend works: {result['model']} "
              f"(provisioned in {result.get('provision_seconds')}s, "
              f"{result.get('analysis_seconds')}s per frame batch)")
        print("       concept scoring and scene-to-clip matching are both live")
        return 0
    if result.get("ok"):
        print("[warn] no CLIP backend here, so frames are judged by pixel "
              "statistics alone.")
        print("       Empty rooms, dark scenes and floor plans are still "
              "detected; plastic covers, pets and room types are weaker.")
        print(f"       reason: {result.get('error', 'model could not be loaded')}")
        return 3
    print("[FAIL] frame inspection is not working at all - check FFmpeg")
    return 1


def command_entity_check(args: argparse.Namespace) -> int:
    """Measure the entity probes against real footage instead of guessing.

    ``ENTITY_DOMINANCE_FAIL`` and the ramp bounds around it were set by analogy
    with the concept flags, never measured, and run 26 duly failed 57 of 88
    shots with scores of exactly 0.0 - which is not a statement about how many
    Pexels interiors contain a lamp. A threshold on a measurement has to come
    from the measurement.

    For each entity this searches with the entity's own queries, which should
    return footage containing it, and with another entity's queries, which
    should not. Both sets go through the real probes and the separation
    between them is printed. If the two distributions overlap completely the
    prompts are wrong; if they separate, the crossing point is the threshold.

    Preview stills are used where the provider publishes them, so this costs a
    few hundred kilobytes rather than a few hundred megabytes.
    """

    from .entities import ENTITIES, BY_NAME, grounding_prompts, score_from_similarities
    from .stock.registry import build_providers
    from .visual_analysis import PROMPT_TEMPLATE, VisualAnalyzer, _cosine, _ramp
    from .visual_model import load_model

    config = load_config(args.config)
    model = load_model(dict(config.get("visual.model", {}) or {}))
    if model is None:
        print("[FAIL] no CLIP backend here, so the probes cannot be measured.")
        print("       run this where 'vidfactory visual-check' reports ok.")
        return 1

    providers = build_providers(dict(config.get("sources", {}) or {}))
    providers = [p for p in providers if p.name != "local"]
    if not providers:
        print("[FAIL] no stock provider - set PEXELS_API_KEY")
        return 1
    provider = providers[0]

    analyzer = VisualAnalyzer(
        model=model,
        frames_per_clip=int(config.get("visual.frames_per_clip", 3)),
        allow_remote_video=False,        # stills only; this is a cheap probe
    )
    wanted = [n.strip() for n in str(args.entities or "").split(",") if n.strip()]
    entities = [BY_NAME[n] for n in wanted if n in BY_NAME] or list(ENTITIES)
    per_entity = max(2, int(args.samples))

    def scores_for(entity, query: str) -> list[float]:
        """This entity's probes against whatever ``query`` returns.

        The entity is passed in rather than re-derived from the query text.
        The first version of this let the analyzer infer it, so scoring rug
        footage "as if it were lighting" silently scored it as rug footage and
        every entity's control row came back byte-identical - which is exactly
        the tell that said the harness, not only the probe, was wrong.
        """

        try:
            results = provider.search(query, per_page=per_entity, page=1)
        except Exception as exc:
            print(f"       search failed for {query!r}: {exc}")
            return []
        prompts, _ = grounding_prompts(entity)
        try:
            text_vectors = analyzer._encode_texts(
                [PROMPT_TEMPLATE.format(p) for p in prompts]
            )
        except Exception as exc:
            print(f"       prompt encoding failed: {exc}")
            return []
        out: list[float] = []
        for clip in results[:per_entity]:
            frames = [f for f in analyzer.sample(clip) if f and f.ok]
            if not frames:
                continue
            try:
                image_vectors = list(model.encode_images(frames))
            except Exception:
                continue
            per_frame = [
                [_cosine(image, t) for t in text_vectors] for image in image_vectors
            ]
            grounding = score_from_similarities(entity, per_frame, _ramp)
            if grounding.checked:
                out.append(grounding.score)
        return out

    report: dict[str, Any] = {}
    for index, entity in enumerate(entities):
        # A different entity each time, so the control is genuinely footage of
        # something else rather than the first entity in the list every time.
        other = entities[(index + len(entities) // 2) % len(entities)]
        if other.name == entity.name:
            other = entities[(index + 1) % len(entities)]
        present = scores_for(entity, entity.queries[0])
        absent = scores_for(entity, other.queries[0])
        report[entity.name] = {"present": present, "absent": absent}
        def summary(values: list[float]) -> str:
            if not values:
                return "no samples"
            values = sorted(values)
            return (f"n={len(values)} min={values[0]:.2f} "
                    f"median={values[len(values) // 2]:.2f} max={values[-1]:.2f}")
        print(f"{entity.name:16} containing it : {summary(present)}")
        print(f"{'':16} something else: {summary(absent)}")

    from .entities import ENTITY_DOMINANCE_FAIL

    present_all = sorted(v for r in report.values() for v in r["present"])
    absent_all = sorted(v for r in report.values() for v in r["absent"])
    print("=" * 62)
    if present_all and absent_all:
        # The number the gate actually uses: how often each side is rejected.
        # A probe worth having rejects the control far more often than the
        # real thing, and the gap between those two rates is the whole story.
        kept = sum(1 for v in present_all if v > 1.0 - ENTITY_DOMINANCE_FAIL)
        culled = sum(1 for v in absent_all if v <= 1.0 - ENTITY_DOMINANCE_FAIL)
        print(f"present  n={len(present_all)} "
              f"median={present_all[len(present_all) // 2]:.3f} "
              f"kept={kept} ({100.0 * kept / len(present_all):.0f}%)")
        print(f"absent   n={len(absent_all)} "
              f"median={absent_all[len(absent_all) // 2]:.3f} "
              f"rejected={culled} ({100.0 * culled / len(absent_all):.0f}%)")
        print(f"threshold {1.0 - ENTITY_DOMINANCE_FAIL:.2f}: keeps "
              f"{100.0 * kept / len(present_all):.0f}% of real footage and "
              f"rejects {100.0 * culled / len(absent_all):.0f}% of the control")
        print()
        print("sweep (cut = the score at or below which a shot is rejected):")
        print(f"{'cut':>6}  {'good culled':>12}  {'control culled':>15}")
        for cut in (0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50, 0.60):
            good = sum(1 for v in present_all if v <= cut)
            bad = sum(1 for v in absent_all if v <= cut)
            print(f"{cut:>6.2f}  {good:>4} ({100.0 * good / len(present_all):>3.0f}%)  "
                  f"{bad:>6} ({100.0 * bad / len(absent_all):>3.0f}%)")
        print()
        print("The control is other interior footage, which usually contains the")
        print("object too, so 'control culled' is a floor on the false-positive")
        print("rate rather than a recall figure. What matters is 'good culled':")
        print("every one of those is a shot the repair pass has to replace.")
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"raw scores written to {args.json_out}")
    return 0


def command_state(args: argparse.Namespace) -> int:
    database = Database(args.database)
    database.import_state(Path(args.state))
    database.export_state(Path(args.state))
    print(json.dumps(database.stats(), indent=2))
    return 0


def command_merge_state(args: argparse.Namespace) -> int:
    """Union two divergent copies of the persistent history.

    git cannot merge ``data/state/*.json`` - both sides rewrite every line -
    and picking a side deletes real renders. This unions them on the natural
    keys the schema already declares, then checks the result for orphans.
    """

    from .state_merge import find_orphans, merge_state

    report = merge_state(args.base, args.ours, args.theirs, args.out)
    orphans = find_orphans(args.out)
    print(json.dumps({**report.to_dict(), "orphans": orphans}, indent=2))
    return 1 if any(orphans.values()) else 0


def command_cooldown(args: argparse.Namespace) -> int:
    """Inspect, and if asked repair, the long-term footage cooldown.

    Development renders used to record their footage exactly like published
    ones, so sixteen test videos put their Pexels IDs beyond reach for
    forty-five days each. ``--release`` moves that usage into development
    history: the rows and their counts stay, the cooldown stops seeing them.
    """

    database = Database(args.database)
    database.import_state(Path(args.state))
    before = database.clip_mode_stats()
    if not args.release:
        print(json.dumps(before, indent=2))
        return 0

    result = database.reclassify_clip_history(
        before=args.before, topics=args.topics, dry_run=args.dry_run
    )
    if args.dry_run:
        print(json.dumps({**before, **result}, indent=2))
        return 0
    database.export_state(Path(args.state))
    print(json.dumps({**database.clip_mode_stats(), **result}, indent=2))
    return 0


# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vidfactory",
        description="Automated long-form home decor YouTube video factory",
    )
    parser.add_argument("--config", default=None, help="path to config.yaml")
    parser.add_argument("--database", default="data/factory.db", help="SQLite database path")
    parser.add_argument("--state", default="data/state", help="JSON state snapshot directory")
    parser.add_argument("--verbose", action="store_true", help="debug logging")
    parser.add_argument("--log-file", default=None, help="also write logs to this file")

    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_generate_arguments(sub: argparse.ArgumentParser) -> None:
        sub.add_argument("--topic", default="", help="video topic; empty means generate one")
        sub.add_argument("--auto-topic", action="store_true", help="always generate the topic")
        sub.add_argument("--duration", type=float, default=None, help="target minutes")
        sub.add_argument(
            "--language", default=None,
            help='content language: "Spanish" (default) or "English"',
        )
        sub.add_argument(
            "--voice", default=None,
            help='TTS voice name, or "Automatic" to let the language choose',
        )
        sub.add_argument(
            "--subtitle-style", default=None, choices=["premium", "clean", "none"],
            help="styled captions burned into the picture",
        )
        sub.add_argument("--tts-engine", default=None, choices=["auto", "piper", "espeak", "silent"])
        sub.add_argument("--script-engine", default=None, choices=["auto", "llm", "template"])
        sub.add_argument("--subtitles", default=None, help="true/false")
        sub.add_argument("--burn-in", default=None, help="burn subtitles into the video: true/false")
        sub.add_argument("--resolution", default=None, help="e.g. 1920x1080")
        sub.add_argument("--fps", type=int, default=None)
        sub.add_argument("--preset", default=None, help="x264 preset")
        sub.add_argument("--transition", default=None, choices=["cut", "crossfade"])
        sub.add_argument("--upload", default=None, help="upload to YouTube: true/false")
        sub.add_argument("--privacy", default=None, choices=["private", "unlisted", "public"])
        sub.add_argument("--output", default=None, help="output directory")
        sub.add_argument("--workdir", default=None, help="temporary working directory")
        sub.add_argument("--run-id", default=None, help="identifier for this run")
        sub.add_argument("--local-clips", default=None, help="use your own clips from this folder")
        sub.add_argument("--only-local", action="store_true", help="disable online providers")
        sub.add_argument("--github-output", action="store_true", help="write GITHUB_OUTPUT values")
        sub.add_argument(
            "--items", default=None,
            help="how many tips; a number in the topic always wins "
                 "(Automatic, or 5/7/10/15/20)",
        )
        sub.add_argument(
            "--mode", default=None, choices=["test", "production"],
            help="production renders claim their footage for the cooldown; "
                 "test renders do not (default: whatever config.yaml says)",
        )

    generate = subparsers.add_parser("generate", help="generate one video")
    add_generate_arguments(generate)
    generate.set_defaults(func=command_generate)

    demo = subparsers.add_parser(
        "demo", help="render a short video from synthetic clips (no API keys)"
    )
    add_generate_arguments(demo)
    demo.set_defaults(func=command_demo)

    topics = subparsers.add_parser("topics", help="preview generated topics")
    topics.add_argument("--count", type=int, default=10)
    topics.set_defaults(func=command_topics)

    doctor = subparsers.add_parser("doctor", help="check that this environment can render")
    doctor.set_defaults(func=command_doctor)

    state = subparsers.add_parser("state", help="sync and report persistent history")
    state.set_defaults(func=command_state)

    cooldown = subparsers.add_parser(
        "cooldown",
        help="show or repair the footage cooldown after development renders",
    )
    cooldown.add_argument(
        "--release", action="store_true",
        help="move recorded production footage usage into development history, "
             "so the clips become available again",
    )
    cooldown.add_argument(
        "--before", default=None,
        help="only release usage recorded before this ISO timestamp",
    )
    cooldown.add_argument(
        "--topic", action="append", default=None, dest="topics",
        help="only release usage recorded for this topic slug (repeatable)",
    )
    cooldown.add_argument(
        "--dry-run", action="store_true", help="report what would move, change nothing"
    )
    cooldown.set_defaults(func=command_cooldown)

    merge_state_cmd = subparsers.add_parser(
        "merge-state",
        help="resolve a data/state conflict by unioning two histories",
    )
    merge_state_cmd.add_argument("--base", required=True, help="merge-base snapshot directory")
    merge_state_cmd.add_argument("--ours", required=True, help="this branch's snapshot directory")
    merge_state_cmd.add_argument("--theirs", required=True, help="the other branch's directory")
    merge_state_cmd.add_argument("--out", required=True, help="where to write the merged files")
    merge_state_cmd.set_defaults(func=command_merge_state)

    llm_check = subparsers.add_parser(
        "llm-check", help="download and benchmark the optional local script model"
    )
    llm_check.add_argument(
        "--section-budget", type=float, default=120.0,
        help="seconds per section the runner can afford (default 120)",
    )
    llm_check.set_defaults(func=command_llm_check)

    visual_check = subparsers.add_parser(
        "visual-check",
        help="check whether real frame inspection (and the CLIP backend) works here",
    )
    visual_check.set_defaults(func=command_visual_check)

    entity_check = subparsers.add_parser(
        "entity-check",
        help="measure the required-entity probes against real footage",
    )
    entity_check.add_argument(
        "--entities", default="", help="comma-separated entity names (default: all)"
    )
    entity_check.add_argument("--samples", type=int, default=6)
    entity_check.add_argument("--json-out", default="")
    entity_check.set_defaults(func=command_entity_check)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    setup_logging(verbose=args.verbose, logfile=args.log_file)
    try:
        return int(args.func(args))
    except ConfigError as exc:
        log.error("Configuration error: %s", exc)
        return 1
    except KeyboardInterrupt:  # pragma: no cover
        log.error("Interrupted")
        return 130


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
