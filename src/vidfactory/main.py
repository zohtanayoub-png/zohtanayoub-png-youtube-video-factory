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

from .config import Config, ConfigError, load_config, parse_bool
from .database import Database
from .logging_utils import get_logger, setup_logging

log = get_logger("MAIN")


def _overrides_from_args(args: argparse.Namespace) -> dict[str, object]:
    overrides: dict[str, object] = {}
    if getattr(args, "duration", None):
        overrides["video.duration_minutes"] = float(args.duration)
    if getattr(args, "voice", None):
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
            handle.write(f"title={result.script.title}\n")
            handle.write(f"duration_seconds={result.duration:.1f}\n")
            handle.write(f"youtube_id={result.youtube_id}\n")
    return 0


def command_demo(args: argparse.Namespace) -> int:
    """Render a short video from synthetic clips - no API keys required."""

    from .testassets import build_test_library

    clips_dir = Path(args.workdir or "work") / "demo_clips"
    build_test_library(clips_dir, seconds=12.0, width=1920, height=1080)

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


def command_state(args: argparse.Namespace) -> int:
    database = Database(args.database)
    database.import_state(Path(args.state))
    database.export_state(Path(args.state))
    print(json.dumps(database.stats(), indent=2))
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
        sub.add_argument("--voice", default=None, help="TTS voice name")
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
