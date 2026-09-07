"""Turning a diabetes topic into a finished vertical reel.

Deliberately its own orchestration rather than a branch inside
:mod:`vidfactory.pipeline`. The two products share the machinery that is
genuinely general - TTS, stock search, ranking, frame inspection, the
downloader, the FFmpeg editor, the caption renderer - and share none of the
editorial logic, because forty vertical seconds about food and twenty five
horizontal minutes about living rooms disagree about almost everything:
shot length, frame shape, what a good opening is, and what a false statement
costs.

Three places where that difference is load-bearing:

**The interior gates are switched off.** ``enforce_premium``,
``enforce_aspirational`` and ``min_interior_relevance`` exist to reject
footage that is not a photograph of a styled room. A bowl of strawberries is
not a photograph of a styled room. Leaving them on would reject the entire
subject matter, and turning them off here is not a lowered standard - it is
the standard belonging to a different product.

**Shots are two to four seconds.** The brief asks for a reel that moves, and
the beat structure gives it somewhere to move to: the picture changes when
the sentence does, so "las fresas" is on screen exactly while the narration
says it.

**Zero source reuse still holds.** It is the one editorial rule that
transfers unchanged, and in forty seconds it is easier to keep.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from ..downloader import ClipDownloader
from ..editor import Shot, VideoEditor
from ..languages import resolve_language
from ..logging_utils import get_logger
from ..ranking import ClipRanker, RankingContext
from ..stock.registry import build_providers
from ..subtitles import generate_subtitles
from .narration import narrate
from .voice import build_reel_engine, licence_report, prosody
from .captions import REEL_HEIGHT, REEL_WIDTH, safe_area_report, write_reel_ass
from .knowledge import BY_SLUG, Topic, find_topic
from .metadata import caption as build_caption
from .metadata import publish_metadata
from .qc import ReelReport, build_report
from .script import ALLOWED_SECONDS, DEFAULT_SECONDS, ReelScript, build as build_script
from .sources import bibliography

log = get_logger("REEL")

#: Shot length. The brief's "2-4 segundos", and short enough that a beat of
#: narration usually gets its own picture.
MIN_SHOT = 2.0
MAX_SHOT = 4.0

#: A short hold after the last word. Long enough not to cut the CTA off,
#: short enough that the loop comes round quickly.
TAIL_SECONDS = 0.4


@dataclass
class ReelResult:
    """Everything one generation produced."""

    output_dir: Path
    video: Path | None = None
    srt: Path | None = None
    ass: Path | None = None
    script_txt: Path | None = None
    caption_txt: Path | None = None
    metadata_json: Path | None = None
    qc_json: Path | None = None
    sources_json: Path | None = None
    report: ReelReport | None = None
    script: ReelScript | None = None
    duration: float = 0.0
    shots: list[dict[str, Any]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return bool(self.video and self.video.exists() and self.report and self.report.passed)

    def to_dict(self) -> dict[str, Any]:
        return {
            "output_dir": str(self.output_dir),
            "video": str(self.video) if self.video else "",
            "duration": round(self.duration, 2),
            "shots": len(self.shots),
            "passed": bool(self.report and self.report.passed),
        }


class ReelPipeline:
    """DIABETES REELS, end to end."""

    def __init__(
        self,
        config: Any,
        output_dir: str | Path = "output/reels",
        database: Any | None = None,
        visual_analyzer: Any | None = None,
    ) -> None:
        self.config = config
        self.output_dir = Path(output_dir)
        self.database = database
        self._injected_analyzer = visual_analyzer
        self.language = resolve_language("es")

    # ------------------------------------------------------------------
    def _speech_rate(self, voice: str) -> float:
        """Words per second, measured if this voice has ever spoken here.

        Same rule the long-form generator follows: the engine's declared rate
        is a constant, and the rate this voice actually speaks at is a
        measurement. A reel is short enough that a ten percent error is three
        or four seconds, which is the difference between fitting a format and
        not.
        """

        declared = float(self.language.words_per_minute or 170.0) / 60.0
        if self.database is None:
            return declared
        try:
            measured = self.database.measured_speech_rate("piper", voice)
        except Exception:                                  # pragma: no cover
            return declared
        if measured and measured > 0:
            log.info("Sizing the reel for the measured rate: %.0f wpm", measured)
            return float(measured) / 60.0
        return declared

    # ------------------------------------------------------------------
    def run(
        self,
        topic: str = "",
        seconds: float = DEFAULT_SECONDS,
        content_format: str = "",
        items: int = 0,
        voice: str = "",
        mode: str = "test",
        tts: str = "",
    ) -> ReelResult:
        started = time.time()
        chosen = self._resolve_topic(topic, content_format)
        seconds = self._resolve_seconds(seconds)
        voice = voice or (self.language.voices[0] if self.language.voices else "")
        production = str(mode).strip().lower() == "production"

        run_dir = self.output_dir / f"{chosen.slug}-{int(started)}"
        run_dir.mkdir(parents=True, exist_ok=True)
        work = run_dir / "work"
        work.mkdir(exist_ok=True)

        script = build_script(
            chosen,
            target_seconds=seconds,
            words_per_second=self._speech_rate(voice),
            max_items=int(items or 0),
        )
        log.info(
            "%s | %s | %d beats, %d items, ~%.1fs (%s)",
            chosen.title, chosen.format, len(script.beats),
            len(script.item_beats), script.estimated_seconds,
            "production" if production else "test",
        )
        log.info("Hook: %s", script.hook.hook)

        narration = self._narrate(script, work, voice, tts)
        shots, clips = self._plan_visuals(script, narration, work)

        # Captions and the fixed title are written *before* the render,
        # because the render burns them in. The title's span comes from the
        # narration plus the tail rather than from the finished file, which
        # does not exist yet - and it is the same number the mux pins the
        # output length to.
        ass_path, events, font = write_reel_ass(
            narration.chunks,
            work / "subtitles.ass",
            chosen.top_title,
            chosen.accent,
            narration.duration + TAIL_SECONDS,
            language=self.language,
        )
        video = self._render(script, shots, narration, run_dir, work)
        duration = self._duration(video)
        srt, _cues = generate_subtitles(narration.chunks, run_dir / "subtitles.srt")
        # The burned-in copy lives in the work folder; the published one is a
        # plain artifact beside the video.
        published_ass = run_dir / "subtitles.ass"
        published_ass.write_text(ass_path.read_text(encoding="utf-8"), encoding="utf-8")

        sources = bibliography(script.source_keys)
        report = build_report(
            script,
            production=production,
            actual_seconds=duration,
            cta_start=self._cta_start(narration),
            value_start=self._beat_start(narration, script, "answer"),
            audio_seconds=narration.duration,
            visual=self._visual_summary(shots, clips),
            captions=safe_area_report(events),
            sources=sources,
        )
        result = self._write_outputs(
            run_dir, script, report, sources, video, srt, published_ass,
            duration, shots,
        )
        report.metrics["tts_engine"] = narration.engine
        report.metrics["tts_voice"] = narration.voice
        report.metrics["tts_licence"] = licence_report().get(narration.engine, {})
        # What "sounds robotic" actually is, as numbers: how much the loudness
        # moves, how much of the track is pause, and whether the pauses are all
        # the same length. Recorded rather than gated - this is a description
        # of a voice, not a threshold anybody has calibrated.
        report.metrics["voice_prosody"] = prosody(narration.audio_path)
        report.metrics["caption_font"] = font
        report.save(run_dir / "reel_quality_report.json")

        for check in report.checks:
            if check.passed:
                continue
            log.error("%s: %s", check.name, check.detail) if check.severity == "error" \
                else log.warning("%s: %s", check.name, check.detail)
        log.info(
            "Reel finished in %.0fs: %s (%.1fs, %d shots, %s)",
            time.time() - started, video, duration, len(shots),
            "PASSED" if report.passed else "FAILED",
        )
        return result

    # ------------------------------------------------------------------
    def _resolve_topic(self, topic: str, content_format: str) -> Topic:
        chosen = find_topic(topic) if topic else None
        if chosen is None and content_format:
            from .knowledge import topics_for

            candidates = topics_for(content_format)
            chosen = candidates[0] if candidates else None
        if chosen is None:
            chosen = BY_SLUG["frutas-impacto-moderado"]
        if content_format and chosen.format != content_format:
            log.info(
                "Topic %r is a %s; the requested format %r does not apply to it",
                chosen.slug, chosen.format, content_format,
            )
        return chosen

    @staticmethod
    def _resolve_seconds(seconds: float) -> float:
        value = float(seconds or DEFAULT_SECONDS)
        if value in ALLOWED_SECONDS or 20 <= value <= 60:
            return value
        nearest = min(ALLOWED_SECONDS, key=lambda a: abs(a - value))
        log.info("Duration %.0fs is outside 20-60s; using %ds", value, nearest)
        return float(nearest)

    # ------------------------------------------------------------------
    def _narrate(
        self, script: ReelScript, work: Path, voice: str, tts: str = ""
    ) -> Any:
        """The reel's own narrator: same words, delivery that varies by beat.

        :class:`NarrationBuilder` reads a script at one pace with one pause
        between scenes, which is right for twenty-five minutes and is most of
        why forty seconds sounded like an audiobook. It stays exactly where it
        is - the long-form side still uses it - and the reel walks its beats
        instead.
        """

        engine = build_reel_engine(
            engine=str(tts or self.config.get("reels.tts.engine", "auto")),
            voice=voice,
            speed=float(self.config.get("tts.speed", 1.0)),
            sample_rate=int(self.config.get("audio.sample_rate", 48000)),
            language=self.language,
        )
        narration = narrate(
            script.beats,
            engine,
            workdir=work / "tts",
            destination=work / "narration.wav",
            language=self.language,
            loudness_lufs=float(self.config.get("audio.loudness_lufs", -16.0)),
            sample_rate=int(self.config.get("audio.sample_rate", 48000)),
            max_chunk_chars=int(self.config.get("tts.max_chunk_chars", 320)),
        )
        log.info(
            "Narration: %.1fs, %s / %s", narration.duration,
            narration.engine, narration.voice,
        )
        return narration

    @staticmethod
    def _cta_start(narration: Any) -> float:
        timings = getattr(narration, "scene_timings", {}) or {}
        if not timings:
            return 0.0
        last = sorted(timings)[-1]
        return float(timings[last][0])

    @staticmethod
    def _beat_start(narration: Any, script: ReelScript, kind: str) -> float:
        """When a beat actually begins, measured from the synthesized track.

        The word estimate is what the report falls back to; this is the real
        number, and for "does the value start immediately" the real number is
        the only one worth reporting.
        """

        timings = getattr(narration, "scene_timings", {}) or {}
        for index, beat in enumerate(script.beats):
            if beat.kind == kind:
                span = timings.get(f"beat-{index:02d}")
                return float(span[0]) if span else 0.0
        return 0.0

    # ------------------------------------------------------------------
    def _ranking_context(self, query: str, used: Sequence[str]) -> RankingContext:
        sources = dict(self.config.get("sources", {}) or {})
        return RankingContext(
            query=query,
            keywords=[w for w in query.split() if len(w) > 3],
            min_shot_seconds=MIN_SHOT,
            max_shot_seconds=MAX_SHOT,
            prefer_width=int(sources.get("prefer_width", 1920)),
            min_width=int(sources.get("min_width", 1280)),
            min_source_seconds=MIN_SHOT,
            # The three interior gates are off. They reject anything that is
            # not a photograph of a styled room, which is every clip this
            # product needs. See the module docstring.
            enforce_aspirational=False,
            enforce_premium=False,
            min_interior_relevance=0.0,
            already_selected=list(used),
        )

    def _plan_visuals(
        self, script: ReelScript, narration: Any, work: Path
    ) -> tuple[list[Shot], dict[str, Any]]:
        """One or more 2-4 second shots per beat, all from distinct sources."""

        providers = [
            p for p in build_providers(dict(self.config.get("sources", {}) or {}))
        ]
        if not providers:
            raise RuntimeError("no stock provider is available for the reel")

        ranker = ClipRanker(
            weights=dict(self.config.get("ranking.weights", {}) or {}),
            min_score=0.0,
            max_uses_per_clip=1,
        )
        downloader = ClipDownloader(
            workdir=work / "clips",
            min_width=int(self.config.get("sources.min_width", 1280)),
            min_height=int(self.config.get("sources.min_height", 720)),
            min_seconds=MIN_SHOT,
            max_mb=float(self.config.get("sources.max_download_mb", 90)),
            timeout=float(self.config.get("sources.download_timeout_seconds", 120)),
            retries=int(self.config.get("sources.retries", 3)),
        )

        used_keys: list[str] = []
        shots: list[Shot] = []
        analyzer = self._analyzer()
        analysed: list[dict[str, Any]] = []

        for index, beat in enumerate(script.beats):
            scene_id = f"beat-{index:02d}"
            start, end = narration.scene_timings.get(scene_id, (0.0, 0.0))
            span = max(0.6, end - start)
            wanted = max(1, int(round(span / MAX_SHOT + 0.35)))

            candidates: list[Any] = []
            for provider in providers:
                try:
                    candidates.extend(
                        provider.search(beat.query, per_page=20, page=1)
                    )
                except Exception as exc:
                    log.warning("search failed for %r: %s", beat.query, exc)
            fresh = [c for c in candidates if c.key not in used_keys]
            ranked = ranker.rank(fresh, self._ranking_context(beat.query, used_keys))
            if not ranked:
                ranked = fresh[:wanted]

            chosen: list[Any] = []
            for clip in ranked:
                if len(chosen) >= wanted:
                    break
                fetched = downloader.fetch_many([clip], needed=1)
                if not fetched:
                    continue
                result = fetched[0]
                if analyzer is not None:
                    analysis = analyzer.analyze_clip(
                        result.clip,
                        query=beat.search_text,
                        narration=beat.search_text,
                        video=result.clip.local_path or result.path,
                    )
                    result.clip.visual = analysis.to_dict()
                    result.clip.visual_semantic_match = analysis.semantic_match
                    analysed.append(
                        {
                            "beat": scene_id,
                            "kind": beat.kind,
                            "query": beat.query,
                            "semantic_match": analysis.semantic_match,
                            "analyzed": analysis.analyzed,
                        }
                    )
                chosen.append(result)
                used_keys.append(result.clip.key)

            if not chosen:
                log.warning("no footage for beat %s (%r)", scene_id, beat.query)
                continue

            per = span / len(chosen)
            offset = start
            for position, result in enumerate(chosen):
                length = min(MAX_SHOT, max(MIN_SHOT * 0.6, per))
                if position == len(chosen) - 1:
                    length = max(0.5, end - offset)
                shots.append(
                    Shot(
                        scene_id=scene_id,
                        clip_key=result.clip.key,
                        source=Path(result.path),
                        start=0.0,
                        duration=round(length, 3),
                        motion="zoom_in" if position % 2 == 0 else "pan_left",
                    )
                )
                offset += length

        log.info(
            "%d shots from %d distinct sources across %d beats",
            len(shots), len(set(s.clip_key for s in shots)), len(script.beats),
        )
        return shots, {"analysed": analysed}

    def _analyzer(self) -> Any | None:
        if self._injected_analyzer is not None:
            return self._injected_analyzer
        if not bool(self.config.get("visual.enabled", True)):
            return None
        from ..visual_analysis import VisualAnalyzer
        from ..visual_model import load_model

        settings = dict(self.config.get("visual.model", {}) or {})
        model = load_model(settings) if settings.get("enabled", True) else None
        return VisualAnalyzer(
            model=model,
            frames_per_clip=int(self.config.get("visual.frames_per_clip", 3)),
            allow_remote_video=False,
        )

    @staticmethod
    def _visual_summary(shots: Sequence[Shot], clips: Mapping[str, Any]) -> dict[str, Any]:
        rows = list(clips.get("analysed", []) or [])
        scored = [float(r["semantic_match"]) for r in rows if r.get("analyzed")]
        keys = [s.clip_key for s in shots]
        return {
            "shot_count": len(shots),
            "unique_sources": len(set(keys)),
            "source_reuse_count": len(keys) - len(set(keys)),
            "inspected_clip_count": len(scored),
            "semantic_match_average": (
                round(sum(scored) / len(scored), 3) if scored else 0.0
            ),
            "low_relevance_count": sum(1 for v in scored if v < 0.35),
            "average_shot_seconds": (
                round(sum(s.duration for s in shots) / len(shots), 2) if shots else 0.0
            ),
        }

    # ------------------------------------------------------------------
    def _render(
        self,
        script: ReelScript,
        shots: Sequence[Shot],
        narration: Any,
        run_dir: Path,
        work: Path,
    ) -> Path:
        editor = VideoEditor(
            workdir=work / "edit",
            width=REEL_WIDTH,
            height=REEL_HEIGHT,
            fps=int(self.config.get("video.fps", 30)),
            crf=int(self.config.get("video.crf", 20)),
            preset=str(self.config.get("video.preset", "veryfast")),
            transition="cut",
            sample_rate=int(self.config.get("audio.sample_rate", 48000)),
            aac_bitrate=str(self.config.get("audio.aac_bitrate", "192k")),
            fast_mux=False,          # the captions are burned in
        )
        track = editor.build_video_track(list(shots), fade_out=0.0)
        return editor.mux(
            track,
            narration.audio_path,
            run_dir / "reel.mp4",
            # A short tail, not the long-form 1.2s: a reel that hangs on a
            # still frame is a reel that loses the loop.
            tail_seconds=TAIL_SECONDS,
            subtitles=work / "subtitles.ass",
        )

    @staticmethod
    def _duration(video: Path) -> float:
        from ..ffmpeg_utils import probe_media

        try:
            return float(probe_media(video).duration or 0.0)
        except Exception:                                  # pragma: no cover
            return 0.0

    # ------------------------------------------------------------------
    def _write_outputs(
        self,
        run_dir: Path,
        script: ReelScript,
        report: ReelReport,
        sources: Sequence[dict[str, Any]],
        video: Path,
        srt: Path,
        ass_path: Path,
        duration: float,
        shots: Sequence[Shot],
    ) -> ReelResult:
        script_txt = run_dir / "guion.txt"
        script_txt.write_text(
            "\n".join(f"[{b.kind}] {b.text}" for b in script.beats) + "\n",
            encoding="utf-8",
        )
        caption_txt = run_dir / "caption.txt"
        caption_txt.write_text(build_caption(script, sources), encoding="utf-8")

        metadata = publish_metadata(script, sources, duration)
        metadata_json = run_dir / "metadata.json"
        metadata_json.write_text(
            json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        sources_json = run_dir / "fuentes.json"
        sources_json.write_text(
            json.dumps(sources, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        (run_dir / "script.json").write_text(
            json.dumps(script.to_dict(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return ReelResult(
            output_dir=run_dir,
            video=video,
            srt=srt,
            ass=ass_path,
            script_txt=script_txt,
            caption_txt=caption_txt,
            metadata_json=metadata_json,
            qc_json=run_dir / "reel_quality_report.json",
            sources_json=sources_json,
            report=report,
            script=script,
            duration=duration,
            shots=[s.to_dict() for s in shots],
        )
