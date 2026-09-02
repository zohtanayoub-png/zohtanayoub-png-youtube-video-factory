"""The end-to-end generation pipeline.

    TOPIC -> TITLE -> SCRIPT -> SCENES -> NARRATION -> SHOT PLAN ->
    VISUAL SEARCH -> RANK -> DOWNLOAD -> EDIT -> SUBTITLES -> RENDER ->
    QUALITY CHECK -> METADATA -> SAVE -> (OPTIONAL UPLOAD)

Narration is generated before footage is searched. That is deliberate: once
the narration exists, every scene's exact duration is known, so shots can be
cut to the words instead of the words being stretched to fit the shots.
"""

from __future__ import annotations

import json
import shutil
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from .config import Config
from .database import Database
from .downloader import ClipDownloader
from .editor import VideoEditor, plan_shots
from .ffmpeg_utils import ffmpeg_available, probe_media
from .logging_utils import get_logger
from .metadata import build_metadata, safe_filename
from .quality_control import QualityReport, validate_output
from .ranking import ClipRanker, RankingContext, diversify
from .scene_planner import Scene, plan_scenes
from .script_generator import Script, generate_script
from .stock import StockClip, build_providers
from .subtitles import generate_subtitles
from .topic_engine import Topic, TopicEngine
from .tts import NarrationBuilder, build_engine

log = get_logger("RUN")


class PipelineError(RuntimeError):
    """Raised when the pipeline cannot produce a valid video."""


@dataclass
class GenerationResult:
    """Everything one successful run produced."""

    video_path: Path
    subtitles_path: Path | None
    script_path: Path
    metadata_path: Path
    sources_path: Path
    report: QualityReport
    topic: Topic
    script: Script
    duration: float
    youtube_id: str = ""
    output_dir: Path = field(default_factory=Path)

    def summary(self) -> dict[str, Any]:
        return {
            "title": self.script.title,
            "topic": self.topic.to_dict(),
            "video": str(self.video_path),
            "duration_seconds": round(self.duration, 2),
            "subtitles": str(self.subtitles_path) if self.subtitles_path else "",
            "metadata": str(self.metadata_path),
            "sources": str(self.sources_path),
            "quality_passed": self.report.passed,
            "youtube_id": self.youtube_id,
        }


class VideoPipeline:
    """Runs one complete video generation."""

    def __init__(
        self,
        config: Config,
        database: Database | None = None,
        workdir: str | Path | None = None,
        run_id: str | None = None,
        state_dir: str | Path = "data/state",
    ) -> None:
        self.config = config
        self.state_dir = Path(state_dir)
        self.run_id = run_id or datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        self.database = database or Database("data/factory.db")
        self.output_root = Path(config.get("output.directory", "output"))
        self.workdir = Path(workdir) if workdir else Path("work") / self.run_id
        self.workdir.mkdir(parents=True, exist_ok=True)
        self.output_root.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    def run(
        self,
        topic_text: str | None = None,
        upload: bool | None = None,
    ) -> GenerationResult:
        if not ffmpeg_available():
            raise PipelineError(
                "FFmpeg and ffprobe are required but were not found on this machine"
            )
        if self.config.music_enabled:  # pragma: no cover - config validation blocks this
            raise PipelineError("background music is not supported by this project")

        started = time.time()
        generation_id = self.database.start_generation(self.run_id, topic_text)

        try:
            topic = self._choose_topic(topic_text)
            script = self._write_script(topic)
            scenes = self._plan_scenes(script)
            narration = self._narrate(scenes)
            clips = self._gather_footage(scenes, narration, topic)
            result = self._render(topic, script, scenes, narration, clips)
            self._persist(topic, script, scenes, result)

            if upload is None:
                upload = bool(self.config.get("youtube.upload_enabled", False))
            if upload:
                result.youtube_id = self._upload(result)

            self.database.finish_generation(
                generation_id, "success", json.dumps(result.summary())
            )
            log.info(
                "DONE %s (%.1f minutes of video in %.1f minutes of compute)",
                result.video_path.name,
                result.duration / 60.0,
                (time.time() - started) / 60.0,
            )
            return result
        except Exception as exc:
            self.database.finish_generation(generation_id, "failed", str(exc))
            raise
        finally:
            self._export_state()

    # ------------------------------------------------------------------
    # Stages
    # ------------------------------------------------------------------
    def _choose_topic(self, topic_text: str | None) -> Topic:
        history = self.database.topic_titles(int(self.config.get("topics.history_limit", 500)))
        engine = TopicEngine(
            history=history,
            similarity_threshold=float(self.config.get("topics.similarity_threshold", 0.62)),
        )
        topic = (
            engine.from_user_input(topic_text)
            if topic_text and topic_text.strip()
            else engine.generate()
        )
        self.database.add_topic(
            slug=topic.slug,
            title=topic.title,
            category=topic.category,
            angle=topic.angle,
            item_count=topic.item_count,
        )
        return topic

    def _write_script(self, topic: Topic) -> Script:
        return generate_script(
            topic,
            duration_minutes=float(self.config.get("video.duration_minutes", 20)),
            engine=str(self.config.get("script.engine", "auto")),
            words_per_minute=float(self.config.get("script.words_per_minute", 150)),
            llm_settings=dict(self.config.get("script.llm", {}) or {}),
        )

    def _plan_scenes(self, script: Script) -> list[Scene]:
        return plan_scenes(script)

    def _narrate(self, scenes: Sequence[Scene]):
        engine = build_engine(
            engine=str(self.config.get("tts.engine", "auto")),
            voice=str(self.config.get("tts.voice", "en_US-hfc_female-medium")),
            speed=float(self.config.get("tts.speed", 1.0)),
            sample_rate=int(self.config.get("audio.sample_rate", 48000)),
            fallback_voices=list(self.config.get("tts.fallback_voices", []) or []),
        )
        builder = NarrationBuilder(
            engine=engine,
            workdir=self.workdir / "audio",
            sentence_pause=float(self.config.get("tts.sentence_pause_seconds", 0.28)),
            scene_pause=float(self.config.get("tts.scene_pause_seconds", 0.45)),
            max_chunk_chars=int(self.config.get("tts.max_chunk_chars", 320)),
            loudness_lufs=float(self.config.get("audio.loudness_lufs", -16.0)),
            sample_rate=int(self.config.get("audio.sample_rate", 48000)),
        )
        return builder.build(scenes, self.workdir / "narration.wav")

    # ------------------------------------------------------------------
    def _clip_history(self) -> dict[str, tuple[int, float | None]]:
        """Load per-clip usage so the ranker can prefer unseen footage."""

        history: dict[str, tuple[int, float | None]] = {}
        now = datetime.now(timezone.utc)
        for row in self.database.query("SELECT provider, provider_id, use_count, last_used_at FROM clips"):
            days: float | None = None
            if row["last_used_at"]:
                try:
                    last = datetime.fromisoformat(row["last_used_at"])
                    if last.tzinfo is None:
                        last = last.replace(tzinfo=timezone.utc)
                    days = (now - last).total_seconds() / 86400.0
                except ValueError:
                    days = None
            history[f"{row['provider']}:{row['provider_id']}"] = (int(row["use_count"] or 0), days)
        return history

    def _gather_footage(
        self, scenes: Sequence[Scene], narration: Any, topic: Topic
    ) -> list[Any]:
        """Search, rank and download enough clips to cover the whole timeline."""

        sources = dict(self.config.get("sources", {}) or {})
        providers = build_providers(sources)
        if not providers:
            raise PipelineError(
                "No stock footage provider is usable. Set the PEXELS_API_KEY secret, "
                "or enable sources.local and add your own clips to assets/local_clips."
            )

        max_shot = float(self.config.get("video.max_clip_seconds", 8))
        min_shot = float(self.config.get("video.min_clip_seconds", 4))
        total_seconds = narration.duration + float(self.config.get("video.tail_seconds", 1.2))
        needed = max(3, int(total_seconds / max(max_shot, 1.0)) + 2)

        history = self._clip_history()
        ranker = ClipRanker(
            weights=dict(self.config.get("ranking.weights", {}) or {}),
            min_score=float(self.config.get("ranking.min_score", 28)),
            max_uses_per_clip=int(self.config.get("ranking.max_uses_per_clip", 3)),
        )

        # Search scene by scene so the footage follows the narration, and stop
        # once there is comfortably more material than the timeline needs.
        candidates: dict[str, StockClip] = {}
        query_count = 0
        per_query = int(sources.get("per_query_results", 20))
        scene_order = self._scene_search_order(scenes)

        for scene in scene_order:
            if len(candidates) >= needed * 3:
                break
            for provider in providers:
                for query in scene.queries[:2]:
                    query_count += 1
                    try:
                        found = provider.search(query, per_page=per_query)
                    except Exception as exc:
                        log.warning("%s search failed for %r: %s", provider.name, query, exc)
                        continue
                    for clip in found:
                        candidates.setdefault(clip.key, clip)
                    if found:
                        break        # a query that worked is enough for this scene

        log.info("%d candidates found across %d queries", len(candidates), query_count)
        if not candidates:
            raise PipelineError(
                "No stock clips were found for any scene. Check the provider API keys."
            )

        context = RankingContext(
            query=topic.title,
            keywords=topic.keywords,
            min_shot_seconds=min_shot,
            max_shot_seconds=max_shot,
            prefer_width=int(sources.get("prefer_width", 1920)),
            min_width=int(sources.get("min_width", 1280)),
            min_height=int(sources.get("min_height", 720)),
            min_source_seconds=float(sources.get("min_source_seconds", 5.0)),
            cooldown_days=float(self.config.get("ranking.clip_reuse_cooldown_days", 45)),
            history=history,
        )
        ranked = ranker.rank(list(candidates.values()), context)
        log.info("%d clips passed ranking (of %d candidates)", len(ranked), len(candidates))

        if not ranked:
            # Relax the cooldown rather than failing the whole render.
            log.warning("No clip cleared the ranking threshold; retrying without the cooldown")
            context.cooldown_days = 0.0
            ranked = ranker.rank(list(candidates.values()), context)
        if not ranked:
            raise PipelineError("No stock clip met the minimum quality requirements")

        selected = diversify(ranked, needed)
        log.info("%d clips selected for download", len(selected))

        downloader = ClipDownloader(
            workdir=self.workdir / "clips",
            min_width=int(sources.get("min_width", 1280)),
            min_height=int(sources.get("min_height", 720)),
            min_seconds=min(float(sources.get("min_source_seconds", 5.0)), min_shot),
            max_mb=float(sources.get("max_download_mb", 90)),
            timeout=float(sources.get("download_timeout_seconds", 120)),
            retries=int(sources.get("retries", 3)),
            # Only byte-identical duplicates within this run are rejected here;
            # reuse across videos is governed by the ranking cooldown instead.
            known_hashes=(),
        )
        results = downloader.fetch_many(selected, needed=needed)

        if len(results) < 3 and len(ranked) > len(selected):
            log.warning("Only %d clips downloaded; trying the next ranked batch", len(results))
            extra = [c for c in ranked if c.key not in {r.clip.key for r in results}]
            results.extend(downloader.fetch_many(extra[:needed], needed=needed - len(results)))

        if not results:
            raise PipelineError("Every clip download failed - cannot build a video")

        log.info("%d clips downloaded and validated", len(results))
        return results

    @staticmethod
    def _scene_search_order(scenes: Sequence[Scene]) -> list[Scene]:
        """Search the first scene of each item first: those carry the topic."""

        leads = [s for s in scenes if s.scene_id.endswith("-00")]
        rest = [s for s in scenes if not s.scene_id.endswith("-00")]
        return leads + rest

    # ------------------------------------------------------------------
    def _render(
        self,
        topic: Topic,
        script: Script,
        scenes: Sequence[Scene],
        narration: Any,
        clips: Sequence[Any],
    ) -> GenerationResult:
        output_dir = self.output_root / self.run_id
        output_dir.mkdir(parents=True, exist_ok=True)

        scene_durations = [
            (scene.scene_id, narration.scene_duration(scene.scene_id))
            for scene in scenes
            if narration.scene_duration(scene.scene_id) > 0.05
        ]
        # Distribute inter-scene pauses so the visuals cover the entire track.
        covered = sum(duration for _, duration in scene_durations)
        shortfall = max(0.0, narration.duration - covered)
        if shortfall > 0.01 and scene_durations:
            share = shortfall / len(scene_durations)
            scene_durations = [(sid, dur + share) for sid, dur in scene_durations]

        shots = plan_shots(
            scene_durations,
            clips,
            min_shot=float(self.config.get("video.min_clip_seconds", 4)),
            max_shot=float(self.config.get("video.max_clip_seconds", 8)),
            motion=str(self.config.get("video.motion", "subtle")),
        )

        editor = VideoEditor(
            workdir=self.workdir / "render",
            width=self.config.width,
            height=self.config.height,
            fps=self.config.fps,
            crf=int(self.config.get("video.crf", 20)),
            preset=str(self.config.get("video.preset", "veryfast")),
            transition=str(self.config.get("video.transition", "cut")),
            transition_seconds=float(self.config.get("video.transition_seconds", 0.4)),
            sample_rate=int(self.config.get("audio.sample_rate", 48000)),
            aac_bitrate=str(self.config.get("audio.aac_bitrate", "192k")),
        )
        video_track = editor.build_video_track(shots)

        # Subtitles come from the narration timeline, so they are exact.
        subtitles_path: Path | None = None
        cues: list[Any] = []
        if bool(self.config.get("subtitles.enabled", True)):
            subtitles_path, cues = generate_subtitles(
                narration.chunks,
                output_dir / "subtitles.srt",
                max_line_chars=int(self.config.get("subtitles.max_line_chars", 42)),
                max_lines=int(self.config.get("subtitles.max_lines", 2)),
            )

        burn_in = bool(self.config.get("subtitles.burn_in", False))
        final_path = output_dir / "final_video.mp4"
        editor.mux(
            video_track,
            narration.audio_path,
            final_path,
            tail_seconds=float(self.config.get("video.tail_seconds", 1.2)),
            subtitles=subtitles_path if (burn_in and subtitles_path) else None,
            video_bitrate=str(self.config.get("video.video_bitrate", "")) or None,
        )

        info = probe_media(final_path)

        # ---- artifacts -------------------------------------------------
        script_path = output_dir / "script.txt"
        script_path.write_text(f"{script.title}\n\n{script.text}\n", encoding="utf-8")
        (output_dir / "script.json").write_text(
            json.dumps(script.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        (output_dir / "scenes.json").write_text(
            json.dumps([s.to_dict() for s in scenes], indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        sources_payload = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "title": script.title,
            "note": (
                "Supporting footage is licensed stock video. Narration and editorial "
                "content are original. No ownership of the stock footage is claimed."
            ),
            "clips": [
                {**result.clip.to_dict(), "used_seconds": round(
                    sum(s.duration for s in shots if s.source == result.path), 2
                )}
                for result in clips
            ],
        }
        sources_path = output_dir / "video_sources.json"
        sources_path.write_text(
            json.dumps(sources_payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )

        metadata = build_metadata(
            script=script,
            scenes=scenes,
            scene_timings=narration.scene_timings,
            duration_seconds=info.duration,
            sources=sources_payload["clips"],
            channel_name=str(self.config.get("channel.name", "")),
            language=str(self.config.get("channel.language", "en-US")),
            category_id=str(self.config.get("youtube.category_id", "26")),
            privacy_status=str(self.config.get("youtube.privacy_status", "private")),
            made_for_kids=bool(self.config.get("youtube.made_for_kids", False)),
        )
        metadata_path = metadata.save(output_dir / "metadata.json")

        # ---- quality control -------------------------------------------
        report = validate_output(
            final_path,
            expected_duration=narration.duration + float(self.config.get("video.tail_seconds", 1.2)),
            expected_width=self.config.width,
            expected_height=self.config.height,
            expected_fps=self.config.fps,
            min_file_mb=float(self.config.get("quality.min_file_mb", 1.0)),
            duration_tolerance=float(self.config.get("quality.duration_tolerance_seconds", 12.0)),
            subtitles_path=subtitles_path,
            metadata_path=metadata_path,
            subtitles_required=bool(self.config.get("subtitles.enabled", True)),
        )
        report.save(output_dir / "quality_report.json")

        if not report.passed:
            attempts = int(self.config.get("quality.max_repair_attempts", 1))
            if attempts > 0:
                log.warning("Quality check failed; attempting one clean re-render")
                editor.mux(
                    video_track,
                    narration.audio_path,
                    final_path,
                    tail_seconds=float(self.config.get("video.tail_seconds", 1.2)),
                    subtitles=None,
                )
                info = probe_media(final_path)
                report = validate_output(
                    final_path,
                    expected_duration=narration.duration
                    + float(self.config.get("video.tail_seconds", 1.2)),
                    expected_width=self.config.width,
                    expected_height=self.config.height,
                    expected_fps=self.config.fps,
                    min_file_mb=float(self.config.get("quality.min_file_mb", 1.0)),
                    duration_tolerance=float(
                        self.config.get("quality.duration_tolerance_seconds", 12.0)
                    ),
                    subtitles_path=subtitles_path,
                    metadata_path=metadata_path,
                    subtitles_required=bool(self.config.get("subtitles.enabled", True)),
                )
                report.save(output_dir / "quality_report.json")

        if not report.passed:
            details = "; ".join(f"{c.name}: {c.detail}" for c in report.failures)
            raise PipelineError(f"Output failed validation - {details}")

        return GenerationResult(
            video_path=final_path,
            subtitles_path=subtitles_path,
            script_path=script_path,
            metadata_path=metadata_path,
            sources_path=sources_path,
            report=report,
            topic=topic,
            script=script,
            duration=info.duration,
            output_dir=output_dir,
        )

    # ------------------------------------------------------------------
    def _persist(
        self,
        topic: Topic,
        script: Script,
        scenes: Sequence[Scene],
        result: GenerationResult,
    ) -> None:
        """Record the run so future videos avoid repeating topics and clips."""

        self.database.mark_topic_used(topic.slug)
        video_id = self.database.add_video(
            topic_slug=topic.slug,
            title=script.title,
            filename=result.video_path.name,
            duration=result.duration,
            word_count=script.word_count,
            scene_count=len(scenes),
            clip_count=len(json.loads(result.sources_path.read_text(encoding="utf-8"))["clips"]),
        )
        self.database.add_scenes(video_id, [s.to_dict() for s in scenes])

        payload = json.loads(result.sources_path.read_text(encoding="utf-8"))
        for clip in payload["clips"]:
            self.database.record_clip_use(
                provider=clip["provider"],
                provider_id=clip["provider_id"],
                url=clip.get("page_url") or clip.get("download_url"),
                width=clip.get("width"),
                height=clip.get("height"),
                duration=clip.get("duration"),
                content_hash=clip.get("content_hash"),
                topic=topic.slug,
            )
        result.video_id = video_id  # type: ignore[attr-defined]

        if not bool(self.config.get("output.keep_workdir", False)):
            shutil.rmtree(self.workdir / "clips", ignore_errors=True)
            shutil.rmtree(self.workdir / "render", ignore_errors=True)
            shutil.rmtree(self.workdir / "audio", ignore_errors=True)
            log.info("Temporary footage removed")

    def _export_state(self) -> None:
        try:
            self.database.export_state(self.state_dir)
        except Exception as exc:  # pragma: no cover - defensive
            log.warning("Could not export persistent state: %s", exc)

    # ------------------------------------------------------------------
    def _upload(self, result: GenerationResult) -> str:
        from .youtube_upload import UploadError, upload_video

        metadata = json.loads(result.metadata_path.read_text(encoding="utf-8"))
        try:
            video_id = upload_video(
                result.video_path,
                metadata,
                subtitles_path=result.subtitles_path,
            )
        except UploadError as exc:
            # The video itself is fine; an upload problem must not discard it.
            log.error("YouTube upload failed: %s", exc)
            return ""
        video_row = getattr(result, "video_id", None)
        if video_row:
            self.database.set_video_youtube_id(int(video_row), video_id)
        return video_id
