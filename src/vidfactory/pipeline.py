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
import math
import shutil
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from .config import Config
from .database import Database
from .downloader import ClipDownloader
from .editor import ShotPlan, VideoEditor, estimate_shot_count, plan_shots
from .editorial_qc import EditorialReport, build_report
from .ffmpeg_utils import ffmpeg_available, probe_media
from .logging_utils import get_logger
from .metadata import build_metadata, safe_filename
from .provenance import (
    Manifest,
    build_manifest,
    new_generation_id,
    prepare_directory,
)
from .quality_control import QualityReport, validate_output
from .ranking import (
    ClipRanker,
    DiversitySettings,
    RankingContext,
    VisualRankingSettings,
    diversify,
    diversity_report,
    metadata_visual_flags,
    rank_with_vision,
)
from .scene_planner import Scene, plan_scenes
from .script_generator import Script, generate_script
from .stock import StockClip, build_providers
from .visual_analysis import VisualAnalyzer
from .subtitles import generate_subtitles
from .title_alignment import detect_promise, score_alignment
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
    editorial: EditorialReport | None
    manifest: Manifest | None
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
            "generation_id": self.manifest.generation_id if self.manifest else "",
            "quality_passed": self.report.passed,
            "editorial_passed": self.editorial.passed if self.editorial else None,
            "artifact_provenance_passed": self.manifest.passed if self.manifest else None,
            "unique_source_ratio": (
                self.editorial.metrics.get("unique_source_ratio") if self.editorial else None
            ),
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
        # A run label may repeat (a re-run reuses the workflow run number), so
        # the generation id adds a timestamp and a random suffix. Every path
        # this run touches is derived from it, which is what makes artifacts
        # from two generations physically unable to share a directory.
        self.run_id = run_id or "run"
        self.generation_id = new_generation_id(self.run_id)
        self.database = database or Database("data/factory.db")
        self.output_root = Path(config.get("output.directory", "output"))
        self.workdir = (
            Path(workdir) / self.generation_id if workdir
            else Path("work") / self.generation_id
        )
        self.workdir.mkdir(parents=True, exist_ok=True)
        self.output_root.mkdir(parents=True, exist_ok=True)
        self.output_dir = prepare_directory(
            self.output_root / self.generation_id, self.generation_id
        )
        log.info("Generation %s -> %s", self.generation_id, self.output_dir)

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
        generation_id = self.database.start_generation(self.generation_id, topic_text)

        try:
            topic = self._choose_topic(topic_text)
            # Build the voice first: how fast it actually speaks decides how
            # many words a 20 minute video needs.
            tts_engine = self._build_tts()
            script = self._write_script(topic, tts_engine.speech_rate_wpm)
            scenes = self._plan_scenes(script)
            narration = self._narrate(scenes, tts_engine)

            # Work out the real shot count before searching, so the amount of
            # footage gathered matches what the edit will actually consume.
            scene_durations = self._scene_durations(scenes, narration)
            shots_needed = estimate_shot_count(
                scene_durations,
                min_shot=float(self.config.get("video.min_clip_seconds", 3)),
                max_shot=float(self.config.get("video.max_clip_seconds", 6)),
            )
            log.info("Timeline needs %d shots from %d unique source videos", shots_needed, shots_needed)

            clips, affinity, search_stats = self._gather_footage(
                scenes, narration, topic, shots_needed
            )
            result = self._render(
                topic, script, scenes, narration, clips,
                scene_durations=scene_durations,
                affinity=affinity,
                search_stats=search_stats,
            )
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

    def _write_script(self, topic: Topic, speech_rate_wpm: float | None = None) -> Script:
        configured = float(self.config.get("script.words_per_minute", 150))
        rate = float(speech_rate_wpm or configured)
        if speech_rate_wpm and abs(rate - configured) > 5:
            log.info(
                "Sizing the script for the actual voice rate (%.0f words per "
                "minute) rather than the configured %.0f",
                rate,
                configured,
            )
        return generate_script(
            topic,
            duration_minutes=float(self.config.get("video.duration_minutes", 20)),
            engine=str(self.config.get("script.engine", "auto")),
            words_per_minute=rate,
            llm_settings=dict(self.config.get("script.llm", {}) or {}),
        )

    def _plan_scenes(self, script: Script) -> list[Scene]:
        return plan_scenes(script)

    def _build_tts(self):
        return build_engine(
            engine=str(self.config.get("tts.engine", "auto")),
            voice=str(self.config.get("tts.voice", "en_US-hfc_female-medium")),
            speed=float(self.config.get("tts.speed", 1.0)),
            sample_rate=int(self.config.get("audio.sample_rate", 48000)),
            fallback_voices=list(self.config.get("tts.fallback_voices", []) or []),
        )

    def _narrate(self, scenes: Sequence[Scene], engine=None):
        engine = engine or self._build_tts()
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
        self, scenes: Sequence[Scene], narration: Any, topic: Topic, shots_needed: int
    ) -> tuple[list[Any], dict[str, list[str]], dict[str, Any]]:
        """Search metadata first, rank, then download only what was selected.

        Returns the downloaded clips, a scene-to-clip affinity map (so each
        idea's shots come from that idea's own searches), and search
        statistics for the editorial report.

        The search walks each scene's query ladder specific-first and only
        falls through to the generic category query when the specific ones
        genuinely came back empty. When the pool is still short of the number
        of shots the timeline needs, it broadens: more queries per scene, then
        deeper result pages, rather than accepting footage reuse.
        """

        sources = dict(self.config.get("sources", {}) or {})
        providers = build_providers(sources)
        if not providers:
            raise PipelineError(
                "No stock footage provider is usable. Set the PEXELS_API_KEY secret, "
                "or enable sources.local and add your own clips to assets/local_clips."
            )

        max_shot = float(self.config.get("video.max_clip_seconds", 6))
        min_shot = float(self.config.get("video.min_clip_seconds", 3))
        per_query = int(sources.get("per_query_results", 30))
        max_pages = max(1, int(sources.get("max_pages", 3)))

        # One unique source video per shot, plus headroom for clips that fail
        # validation on download. Under-counting here is what forced the
        # earlier videos to repeat footage.
        headroom = float(sources.get("candidate_headroom", 1.35))
        needed = max(3, int(math.ceil(shots_needed * headroom)))

        candidates: dict[str, StockClip] = {}
        affinity: dict[str, list[str]] = {}
        stats = {
            "queries_run": 0,
            "specific_queries_run": 0,
            "generic_queries_run": 0,
            "pages_fetched": 0,
            "empty_queries": 0,
        }

        def run(provider: Any, query_text: str, page: int) -> list[StockClip]:
            stats["queries_run"] += 1
            stats["pages_fetched"] += 1
            try:
                return provider.search(query_text, per_page=per_query, page=page)
            except Exception as exc:
                log.warning("%s search failed for %r: %s", provider.name, query_text, exc)
                return []

        def harvest(scene: Scene, pages: int, include_generic: bool) -> int:
            """Search one scene's ladder. Returns how many new clips it added."""

            added = 0
            found_specific = False
            bucket = affinity.setdefault(scene.scene_id, [])
            for query in scene.visual_queries:
                if query.is_generic and (found_specific or not include_generic):
                    continue
                for provider in providers:
                    provider_pages = pages if provider.supports_pagination else 1
                    for page in range(1, provider_pages + 1):
                        results = run(provider, query.text, page)
                        if query.is_generic:
                            stats["generic_queries_run"] += 1
                        else:
                            stats["specific_queries_run"] += 1
                        if not results:
                            stats["empty_queries"] += 1
                            break        # no point paging an empty query
                        for clip in results:
                            if clip.key not in candidates:
                                candidates[clip.key] = clip
                                added += 1
                            if clip.key not in bucket:
                                bucket.append(clip.key)
                        if not query.is_generic:
                            found_specific = True
                    # Enough footage for this idea; move to the next scene
                    # rather than burning rate limit on more of the same.
                    if found_specific and len(bucket) >= 12:
                        break
                if found_specific and len(bucket) >= 12:
                    break
            return added

        scene_order = self._scene_search_order(scenes)

        # A provider that has stopped returning anything new is exhausted, and
        # hammering it just burns rate limit. Track consecutive dry scenes.
        def sweep(
            pages: int,
            include_generic: bool,
            stop_after_dry: int = 6,
            visit_every_scene: bool = False,
        ) -> None:
            dry = 0
            for scene in scene_order:
                # The first pass always visits every scene even once there is
                # plenty of footage: each idea has to contribute its own
                # queries, or its shots end up drawn from another idea's
                # search results and stop illustrating the narration.
                if not visit_every_scene and len(candidates) >= needed * 2:
                    return
                before = len(candidates)
                harvest(scene, pages=pages, include_generic=include_generic)
                if len(candidates) == before:
                    dry += 1
                    if dry >= stop_after_dry:
                        log.info(
                            "Searches stopped returning new footage after %d scenes; "
                            "the available pool is %d clips",
                            dry,
                            len(candidates),
                        )
                        return
                else:
                    dry = 0

        # Pass 1: every scene's own specific queries, one page each.
        sweep(pages=1, include_generic=False, visit_every_scene=True)

        # Pass 2: still short, so go deeper before ever loosening the rules.
        if len(candidates) < needed * 1.5:
            log.info(
                "Only %d candidates after the first pass; searching deeper",
                len(candidates),
            )
            sweep(pages=max_pages, include_generic=False)

        # Pass 3: last resort, allow the generic category fallback.
        if len(candidates) < needed:
            log.warning(
                "Specific queries yielded %d candidates for %d shots; "
                "falling back to generic category queries",
                len(candidates),
                shots_needed,
            )
            sweep(pages=max_pages, include_generic=True, stop_after_dry=4)

        log.info(
            "%d candidates from %d searches (%d specific, %d generic, %d empty)",
            len(candidates),
            stats["queries_run"],
            stats["specific_queries_run"],
            stats["generic_queries_run"],
            stats["empty_queries"],
        )
        if not candidates:
            raise PipelineError(
                "No stock clips were found for any scene. Check the provider API keys."
            )

        history = self._clip_history()
        ranker = ClipRanker(
            weights=dict(self.config.get("ranking.weights", {}) or {}),
            min_score=float(self.config.get("ranking.min_score", 28)),
            max_uses_per_clip=int(self.config.get("ranking.max_uses_per_clip", 3)),
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
            enforce_aspirational=bool(self.config.get("ranking.enforce_aspirational", True)),
            enforce_premium=bool(self.config.get("ranking.enforce_premium", True)),
            min_interior_relevance=float(
                self.config.get("ranking.min_interior_relevance", 0.35)
            ),
        )

        # All ranking happens on metadata alone; nothing has been downloaded
        # yet, so rejected footage costs no bandwidth.
        ranked = ranker.rank(list(candidates.values()), context)
        log.info("%d clips passed ranking (of %d candidates)", len(ranked), len(candidates))

        if len(ranked) < shots_needed:
            log.warning("Relaxing the reuse cooldown to widen the pool")
            context.cooldown_days = 0.0
            ranked = ranker.rank(list(candidates.values()), context)

        # The premium gate is strict by design, and on a narrow topic it can
        # reject more than the timeline needs. Repeating footage is a worse
        # outcome than an occasional less-than-perfect clip, so relax the gate
        # rather than shipping a video that loops - and say so in the log and
        # in the editorial report.
        if len(ranked) < shots_needed and context.enforce_premium:
            context.enforce_premium = False
            relaxed = ranker.rank(list(candidates.values()), context)
            log.warning(
                "PREMIUM GATE RELAXED: only %d clips cleared it for %d shots; "
                "reranking without it yields %d. Expect a lower "
                "premium_visual_ratio in the editorial report.",
                len(ranked),
                shots_needed,
                len(relaxed),
            )
            stats["premium_gate_relaxed"] = True
            ranked = relaxed

        if not ranked:
            raise PipelineError("No stock clip met the minimum quality requirements")

        # ---- stage two: open the footage --------------------------------
        # Everything so far has been captions. Now the shortlist gets its
        # frames decoded and measured, and the order is rebuilt around what is
        # actually in them.
        ranked, visual_stats = self._inspect_footage(ranked, scenes, affinity, needed)
        stats["visual"] = visual_stats

        if not ranked:
            raise PipelineError(
                "Every candidate clip was rejected by frame inspection - "
                "no footage in this search actually shows the narration"
            )

        selected = diversify(
            ranked,
            needed,
            DiversitySettings(
                max_creator_share=float(self.config.get("ranking.max_creator_share", 0.18)),
                max_query_share=float(self.config.get("ranking.max_query_share", 0.22)),
            ),
        )
        stats["ranked"] = len(ranked)
        stats["selected"] = len(selected)
        log.info("%d clips selected for download (need %d shots)", len(selected), shots_needed)

        downloader = ClipDownloader(
            workdir=self.workdir / "clips",
            min_width=int(sources.get("min_width", 1280)),
            min_height=int(sources.get("min_height", 720)),
            min_seconds=min(float(sources.get("min_source_seconds", 5.0)), min_shot),
            max_mb=float(sources.get("max_download_mb", 90)),
            timeout=float(sources.get("download_timeout_seconds", 120)),
            retries=int(sources.get("retries", 3)),
            known_hashes=(),
        )
        results = downloader.fetch_many(selected, needed=needed)

        # Top up from the ranked remainder if downloads failed validation,
        # because being short of clips is what causes footage repetition.
        if len(results) < shots_needed and len(ranked) > len(selected):
            have = {r.clip.key for r in results}
            extra = [c for c in ranked if c.key not in have]
            log.info(
                "Downloaded %d of %d shots' worth; topping up from the ranked pool",
                len(results),
                shots_needed,
            )
            results.extend(
                downloader.fetch_many(extra, needed=shots_needed - len(results))
            )

        if not results:
            raise PipelineError("Every clip download failed - cannot build a video")

        if len(results) < shots_needed:
            log.warning(
                "FOOTAGE SHORTAGE: %d unique clips for %d shots. Some footage "
                "will have to be reused; consider raising sources.per_query_results "
                "or sources.max_pages.",
                len(results),
                shots_needed,
            )

        stats["downloaded"] = len(results)
        log.info("%d clips downloaded and validated", len(results))

        # The shortlist was judged on provider stills. These are the frames
        # that will actually be on screen, so the report is built from them.
        if bool(self.config.get("visual.verify_downloads", True)):
            self._verify_downloaded_frames(results, scenes)

        return results, affinity, stats

    # ------------------------------------------------------------------
    # Stage two: real frame inspection
    # ------------------------------------------------------------------
    def _visual_analyzer(self) -> VisualAnalyzer | None:
        """Build the analyzer once per generation, model included if it loads.

        Memoized: provisioning the model is the expensive part, and the
        shortlist pass and the post-download verification pass both need it.
        """

        if hasattr(self, "_analyzer_cache"):
            return self._analyzer_cache
        analyzer = self._build_visual_analyzer()
        self._analyzer_cache = analyzer
        return analyzer

    def _build_visual_analyzer(self) -> VisualAnalyzer | None:
        if not bool(self.config.get("visual.enabled", True)):
            log.info("Frame inspection is disabled; ranking on captions alone")
            return None
        model = None
        model_settings = dict(self.config.get("visual.model", {}) or {})
        if model_settings.get("enabled", True):
            from .visual_model import load_model

            model = load_model(model_settings)
        return VisualAnalyzer(
            model=model,
            frames_per_clip=int(self.config.get("visual.frames_per_clip", 3)),
            reject_confidence=float(self.config.get("visual.reject_confidence", 0.72)),
            penalty_confidence=float(self.config.get("visual.penalty_confidence", 0.42)),
            allow_remote_video=bool(self.config.get("visual.allow_remote_video", True)),
        )

    def _visual_settings(self) -> VisualRankingSettings:
        weights = dict(self.config.get("visual.weights", {}) or {})
        return VisualRankingSettings(
            semantic=float(weights.get("semantic", 45)),
            subject=float(weights.get("subject", 30)),
            quality=float(weights.get("quality", 18)),
            novelty=float(weights.get("novelty", 12)),
            technical=float(weights.get("technical", 8)),
            min_semantic=float(self.config.get("visual.min_semantic_match", 0.28)),
        )

    @staticmethod
    def _scene_context(
        scenes: Sequence[Scene], affinity: Mapping[str, Sequence[str]]
    ) -> dict[str, Scene]:
        """clip key -> the scene whose search returned it."""

        by_id = {scene.scene_id: scene for scene in scenes}
        context: dict[str, Scene] = {}
        for scene_id, keys in (affinity or {}).items():
            scene = by_id.get(scene_id)
            if scene is None:
                continue
            for key in keys:
                context.setdefault(key, scene)
        return context

    def _inspect_footage(
        self,
        ranked: Sequence[StockClip],
        scenes: Sequence[Scene],
        affinity: Mapping[str, Sequence[str]],
        needed: int,
    ) -> tuple[list[StockClip], dict[str, Any]]:
        """Decode frames for the shortlist and re-rank on what they contain.

        Only a shortlist is inspected, because decoding frames costs real time
        and the metadata ranking is a perfectly good filter for the obvious
        rejects. The shortlist is generous enough that the visual stage still
        has room to reorder rather than merely confirm.
        """

        analyzer = self._visual_analyzer()
        stats: dict[str, Any] = {
            "model": analyzer.model_name if analyzer else "disabled",
            "shortlisted": 0,
            "analyzed": 0,
            "frames": 0,
            "rejected": 0,
            "seconds": 0.0,
        }
        if analyzer is None or not ranked:
            return list(ranked), stats

        multiplier = float(self.config.get("visual.shortlist_multiplier", 1.6))
        cap = int(self.config.get("visual.max_clips_analyzed", 260))
        budget = float(self.config.get("visual.time_budget_seconds", 420))
        workers = max(1, int(self.config.get("visual.workers", 4)))

        size = min(len(ranked), cap, max(needed, int(math.ceil(needed * multiplier))))
        shortlist = list(ranked[:size])
        remainder = list(ranked[size:])
        stats["shortlisted"] = len(shortlist)

        context = self._scene_context(scenes, affinity)
        started = time.time()
        deadline = started + budget

        def inspect(clip: StockClip) -> StockClip:
            if time.time() > deadline:
                return clip
            scene = context.get(clip.key)
            analysis = analyzer.analyze_clip(
                clip,
                query=clip.query or (scene.primary_visual_query if scene else ""),
                narration=(scene.narration if scene else ""),
                metadata_flags=metadata_visual_flags(clip, clip.query),
            )
            clip.visual = analysis.to_dict()
            clip.visual_semantic_match = analysis.semantic_match
            return clip

        with ThreadPoolExecutor(max_workers=workers) as pool:
            for clip in pool.map(inspect, shortlist):
                if clip.visual.get("analyzed"):
                    stats["analyzed"] += 1
                    stats["frames"] += int(clip.visual.get("frame_count", 0))

        stats["seconds"] = round(time.time() - started, 1)
        timed_out = [c for c in shortlist if not c.visual]
        if timed_out:
            log.warning(
                "Frame inspection ran out of its %.0fs budget with %d clips "
                "unexamined; those keep their metadata ranking",
                budget, len(timed_out),
            )
        stats["not_inspected"] = len(timed_out) + len(remainder)

        settings = self._visual_settings()
        examined = [c for c in shortlist if c.visual]
        inspected = rank_with_vision(examined, settings)

        # Same safety valve as the premium gate: rejecting footage is the
        # right default, and shipping a video that repeats itself because the
        # gate was too strict is worse than shipping one with a couple of
        # weaker matches. Relax, and say so in the log and the report.
        if len(inspected) < needed and settings.min_semantic > 0:
            relaxed_settings = replace(settings, min_semantic=0.0)
            relaxed = rank_with_vision(examined, relaxed_settings)
            if len(relaxed) > len(inspected):
                log.warning(
                    "VISUAL RELEVANCE GATE RELAXED: only %d clips matched the "
                    "narration well enough for %d shots; keeping %d weaker "
                    "matches rather than repeating footage. Expect a lower "
                    "visual_semantic_match_average.",
                    len(inspected), needed, len(relaxed) - len(inspected),
                )
                stats["relevance_gate_relaxed"] = True
                inspected = relaxed

        stats["rejected"] = stats["analyzed"] - len(
            [c for c in inspected if c.visual.get("analyzed")]
        )
        log.info(
            "Frame inspection: %d clips, %d frames, %d rejected, %.1fs (%s)",
            stats["analyzed"], stats["frames"], stats["rejected"],
            stats["seconds"], stats["model"],
        )

        # Anything not inspected keeps its metadata score and queues behind
        # everything that was: an unexamined clip is not evidence of quality.
        tail = timed_out + remainder
        if inspected and tail:
            floor = min(c.score for c in inspected)
            for clip in tail:
                clip.score = min(clip.score, floor) - 1.0
        return inspected + tail, stats

    def _verify_downloaded_frames(
        self, results: Sequence[Any], scenes: Sequence[Scene]
    ) -> None:
        """Re-run the analysis on the real video files that will be edited.

        The shortlist was judged from provider stills, which are genuine
        frames of the clip but not necessarily the frames the edit will use.
        This pass reads the downloaded MP4 itself, so every number in the
        editorial report describes footage that is actually in the video.
        """

        analyzer = self._visual_analyzer()
        if analyzer is None or not results:
            return
        by_query = {scene.primary_visual_query: scene for scene in scenes}
        started = time.time()

        def verify(result: Any) -> None:
            clip = result.clip
            scene = by_query.get(clip.query)
            analysis = analyzer.analyze_clip(
                clip,
                query=clip.query or (scene.primary_visual_query if scene else ""),
                narration=(scene.narration if scene else ""),
                video=clip.local_path or result.path,
                metadata_flags=metadata_visual_flags(clip, clip.query),
            )
            if analysis.analyzed:
                clip.visual = analysis.to_dict()
                clip.visual_semantic_match = analysis.semantic_match

        workers = max(1, int(self.config.get("visual.workers", 4)))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            list(pool.map(verify, results))

        # Nothing is dropped here - the edit is already sized to this footage
        # and a short video is worse than an imperfect clip - but a clip whose
        # own frames disagree with its preview stills is worth saying out
        # loud, and it is counted in the editorial report either way.
        regressions = [
            r.clip for r in results if (r.clip.visual or {}).get("rejected")
        ]
        for clip in regressions:
            log.warning(
                "VERIFIED WORSE: %s - %s (it passed on its preview stills)",
                clip.key, (clip.visual or {}).get("reject_reason", ""),
            )
        log.info(
            "Verified %d downloaded clips against their own frames in %.1fs "
            "(%d disagreed with their preview stills)",
            len(results), time.time() - started, len(regressions),
        )

    @staticmethod
    def _scene_search_order(scenes: Sequence[Scene]) -> list[Scene]:
        """Search the first scene of each item first: those carry the topic."""

        leads = [s for s in scenes if s.scene_id.endswith("-00")]
        rest = [s for s in scenes if not s.scene_id.endswith("-00")]
        return leads + rest

    # ------------------------------------------------------------------
    def _scene_durations(
        self, scenes: Sequence[Scene], narration: Any
    ) -> list[tuple[str, float]]:
        """Real per-scene screen time, covering the whole audio track.

        Inter-scene pauses are spread across the scenes and the closing tail is
        added to the last one, so the visuals cover the entire narration and
        the final mux can stream-copy instead of re-encoding.
        """

        durations = [
            (scene.scene_id, narration.scene_duration(scene.scene_id))
            for scene in scenes
            if narration.scene_duration(scene.scene_id) > 0.05
        ]
        covered = sum(duration for _, duration in durations)
        shortfall = max(0.0, narration.duration - covered)
        if shortfall > 0.01 and durations:
            share = shortfall / len(durations)
            durations = [(sid, dur + share) for sid, dur in durations]
        tail_seconds = float(self.config.get("video.tail_seconds", 1.2))
        if durations and tail_seconds > 0:
            last_id, last_duration = durations[-1]
            durations[-1] = (last_id, last_duration + tail_seconds + 0.2)
        return durations

    def _render(
        self,
        topic: Topic,
        script: Script,
        scenes: Sequence[Scene],
        narration: Any,
        clips: Sequence[Any],
        scene_durations: list[tuple[str, float]] | None = None,
        affinity: dict[str, list[str]] | None = None,
        search_stats: dict[str, Any] | None = None,
    ) -> GenerationResult:
        output_dir = self.output_dir

        scene_durations = scene_durations or self._scene_durations(scenes, narration)
        tail_seconds = float(self.config.get("video.tail_seconds", 1.2))

        shot_plan = plan_shots(
            scene_durations,
            clips,
            min_shot=float(self.config.get("video.min_clip_seconds", 3)),
            max_shot=float(self.config.get("video.max_clip_seconds", 6)),
            motion=str(self.config.get("video.motion", "subtle")),
            scene_affinity=affinity,
        )
        shots = shot_plan.shots

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
            fast_mux=bool(self.config.get("video.fast_mux", True)),
        )
        video_track = editor.build_video_track(
            shots, fade_out=float(self.config.get("video.fade_out_seconds", 0.6))
        )

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
            tail_seconds=tail_seconds,
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

        # ---- editorial quality control ---------------------------------
        # Written before provenance so its file is one of the artifacts the
        # provenance check inspects; the verdict is folded back in below.
        # How many chosen ideas fail the title promise. Should be zero: the
        # script generator filters them out, so a non-zero count means a
        # filter regression rather than a content problem.
        promise = detect_promise(topic.title, topic.angle)
        alignment_failures = sum(
            1
            for section in script.items()
            if section.tip and not score_alignment(section.tip, promise).aligned
        )

        def _editorial(provenance_passed: bool | None) -> EditorialReport:
            report = build_report(
                shot_plan=shot_plan,
                clips=clips,
                scenes=scenes,
                script=script,
                search_stats=search_stats,
                diversity=diversity_report([c.clip for c in clips]),
                thresholds=dict(self.config.get("editorial", {}) or {}),
                provenance_passed=provenance_passed,
                promise_alignment_failures=alignment_failures,
                visual_stats=dict((search_stats or {}).get("visual", {}) or {}),
                causal=getattr(script, "causal", None),
            )
            report.save(output_dir / "editorial_quality_report.json")
            return report

        # Written once so the file exists for the provenance check to inspect,
        # then rewritten below carrying that check's verdict.
        editorial = _editorial(None)

        # ---- technical quality control ---------------------------------
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

        # ---- artifact provenance ---------------------------------------
        # Everything is on disk now, so re-read it and prove the files belong
        # to each other before any of them can be packaged or uploaded.
        manifest = build_manifest(
            output_dir,
            generation_id=self.generation_id,
            topic=topic.title,
            title=script.title,
            spoken_text=narration.spoken_text,
            duration=info.duration,
            source_count=len(clips),
            scene_count=len(scenes),
            shot_count=len(shots),
            scene_narrations=[scene.narration for scene in scenes],
            selected_clip_keys=[
                getattr(getattr(c, "clip", None), "key", "") for c in clips
            ],
        )
        manifest.save(output_dir)
        editorial = _editorial(manifest.passed)

        if not manifest.passed:
            details = "; ".join(
                f"{c.name}: {c.detail}" for c in manifest.checks if not c.passed
            )
            raise PipelineError(
                f"Artifact provenance check failed for generation "
                f"{self.generation_id} - {details}"
            )

        if not editorial.passed and bool(self.config.get("editorial.fail_on_error", True)):
            details = "; ".join(f"{c.name}: {c.detail}" for c in editorial.failures)
            raise PipelineError(f"Output failed editorial validation - {details}")

        return GenerationResult(
            video_path=final_path,
            subtitles_path=subtitles_path,
            script_path=script_path,
            metadata_path=metadata_path,
            sources_path=sources_path,
            report=report,
            editorial=editorial,
            manifest=manifest,
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
