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
from .foods import (
    ground_requirement,
    required_visual_for,
    state_repair_queries,
)
from .script import (
    ALLOWED_SECONDS,
    DEFAULT_SECONDS,
    DEFAULT_WORDS_PER_SECOND,
    MEASURED_WORDS_PER_SECOND,
    ReelScript,
    build_fitted,
)
from .sources import bibliography

log = get_logger("REEL")

#: Shot length. The brief's "2-4 segundos", and short enough that a beat of
#: narration usually gets its own picture.
MIN_SHOT = 2.0
MAX_SHOT = 4.0

#: A short hold after the last word. Long enough not to cut the CTA off,
#: short enough that the loop comes round quickly.
TAIL_SECONDS = 0.4


def shot_spans(
    beats: Sequence[Any],
    scene_timings: Mapping[str, tuple[float, float]],
    timeline_end: float,
) -> list[tuple[float, float]]:
    """When each beat's *picture* is on screen, from the synthesized audio.

    Not when the beat is spoken - that is what ``scene_timings`` says, and
    building the shot plan from it is what froze the last frame. A beat's
    span covers only its own chunks: the sentence pause inside it, the beat
    pause after it and the tail the reel ends on belong to no beat at all, so
    the spans sum to less than the audio by *every pause in the reel*. Run
    34093462658 held its final frame for 1.7 seconds, and stretching only the
    last beat still left 1.52.

    So the picture is continuous by construction: each beat holds the screen
    until the next beat's first word, the last one until the end of the
    audio plus the tail, and the first one from zero whatever its own timing
    says. A beat that was never synthesized - an empty line - gets no time
    rather than getting the whole reel, which is what ``(0.0, 0.0)`` used to
    turn into.

    The result tiles ``[0, timeline_end]`` exactly: no gap, no overlap, and
    no frozen frame at the end.
    """

    end = max(0.0, float(timeline_end))
    known: list[tuple[int, float]] = []
    for index in range(len(beats)):
        timing = scene_timings.get(f"beat-{index:02d}")
        if timing is not None:
            known.append((index, float(timing[0])))
    spans = [(0.0, 0.0)] * len(beats)
    for position, (index, start) in enumerate(known):
        first = 0.0 if position == 0 else start
        last = known[position + 1][1] if position + 1 < len(known) else end
        spans[index] = (min(first, end), max(min(first, end), min(last, end)))
    return spans



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
    def _speech_rate(self, engine: str, voice: str) -> float:
        """Words per second, measured if this engine and voice have spoken here.

        Same rule the long-form generator follows: the engine's declared rate
        is a constant, and the rate it actually speaks at is a measurement. A
        reel is short enough that a ten percent error is three or four
        seconds, which is the difference between fitting a format and not.

        Keyed on the engine as well as the voice, and that is not pedantry:
        the first Kokoro render was refused because the rate on file was a
        Piper measurement of 2.37 words a second, taken with the long-form
        pauses, and applying it to a different narrator with different pauses
        cost the reel two of its five items before a word was spoken.
        """

        # The reel's own rate, not the content language's. See
        # DEFAULT_WORDS_PER_SECOND: 142 wpm describes long-form narration and
        # under-counts a reel's budget by a fifth.
        declared = MEASURED_WORDS_PER_SECOND.get(
            str(engine or "").strip().lower(), DEFAULT_WORDS_PER_SECOND
        )
        if self.database is None:
            return declared
        try:
            measured = self.database.measured_speech_rate(engine, voice)
        except Exception:                                  # pragma: no cover
            return declared
        if measured and measured > 0:
            log.info(
                "Sizing the reel for %s's measured rate: %.0f wpm", engine, measured
            )
            return float(measured) / 60.0
        return declared

    def _fit(
        self, topic: Any, seconds: float, rate: float, items: int
    ) -> tuple[ReelScript, float]:
        """The script, at a duration that keeps the topic's promise."""

        script, actual = build_fitted(
            topic, target_seconds=seconds, words_per_second=rate,
            max_items=int(items or 0),
        )
        if actual != seconds:
            promised = (
                "the answer names" if topic.promises_all_items
                else "the title promises"
            )
            log.warning(
                "%.0fs cannot hold the %d items %s at %.2f words/second; "
                "rendering %.0fs instead",
                seconds, topic.required_item_count, promised, rate, actual,
            )
        return script, actual

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

        # The narrator is chosen before the script, because how fast it
        # speaks decides how much script there is room for.
        engine = self._engine(voice, tts)
        requested_seconds = seconds
        script, seconds = self._fit(
            chosen, seconds, self._speech_rate(getattr(engine, "name", ""), voice), items
        )
        log.info(
            "%s | %s | %d beats, %d items, ~%.1fs (%s)",
            chosen.title, chosen.format, len(script.beats),
            len(script.item_beats), script.estimated_seconds,
            "production" if production else "test",
        )
        log.info("Hook: %s", script.hook.hook)

        narration = self._narrate(script, work, engine)
        # Stamp each beat with when it is actually spoken, so everything
        # downstream - the planner, the report and the frame inspector - maps
        # a moment in the reel to the sentence being said at that moment.
        for index, beat in enumerate(script.beats):
            span = narration.scene_timings.get(f"beat-{index:02d}")
            if span:
                beat.start, beat.end = float(span[0]), float(span[1])
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
        report.metrics["requested_seconds"] = float(requested_seconds)
        report.metrics["duration_grew_for_the_item_count"] = (
            float(requested_seconds) != float(seconds)
        )
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
    def _engine(self, voice: str, tts: str = "") -> Any:
        """The narrator this reel will use."""

        return build_reel_engine(
            engine=str(tts or self.config.get("reels.tts.engine", "auto")),
            voice=voice,
            speed=float(self.config.get("tts.speed", 1.0)),
            sample_rate=int(self.config.get("audio.sample_rate", 48000)),
            language=self.language,
        )

    def _narrate(self, script: ReelScript, work: Path, engine: Any) -> Any:
        """The reel's own narrator: same words, delivery that varies by beat.

        :class:`NarrationBuilder` reads a script at one pace with one pause
        between scenes, which is right for twenty-five minutes and is most of
        why forty seconds sounded like an audiobook. It stays exactly where it
        is - the long-form side still uses it - and the reel walks its beats
        instead.
        """

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

    #: How many times a beat may go back out to search for its food.
    REPAIR_ROUNDS = 3

    def _plan_visuals(
        self, script: ReelScript, narration: Any, work: Path
    ) -> tuple[list[Shot], dict[str, Any]]:
        """One or more 2-4 second shots per beat, all from distinct sources.

        Every shot belongs to exactly one beat and is judged against *that*
        beat. A correct strawberry clip earlier in the reel does not excuse an
        orange during the apple beat: the last render shipped precisely that,
        and no whole-reel average would have seen it.
        """

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
        grounding_rows: list[dict[str, Any]] = []
        repaired_shots = 0
        rounds_used = 0

        # The picture has to cover the whole narration plus the hold at the
        # end. Falling short is what made the editor freeze the final frame
        # over the CTA, and a still image is not a shot.
        timeline_end = float(narration.duration) + TAIL_SECONDS

        def search(query: str) -> list[Any]:
            found: list[Any] = []
            for provider in providers:
                try:
                    found.extend(provider.search(query, per_page=20, page=1))
                except Exception as exc:
                    log.warning("search failed for %r: %s", query, exc)
            return [c for c in found if c.key not in used_keys]

        def take(
            query: str, wanted: int, beat: Any, requirement: Any, scene_id: str
        ) -> tuple[list[tuple[Any, Any]], list[dict[str, Any]]]:
            """Download and judge candidates until ``wanted`` of them pass.

            Returns (clip, grounding) pairs. The grounding rides alongside
            rather than on the download result, which is shared machinery and
            has no business growing a reels-only attribute.
            """

            ranked = ranker.rank(search(query), self._ranking_context(query, used_keys))
            kept: list[tuple[Any, Any]] = []
            rejected: list[dict[str, Any]] = []
            for clip in ranked:
                if len(kept) >= wanted:
                    break
                fetched = downloader.fetch_many([clip], needed=1)
                if not fetched:
                    continue
                result = fetched[0]
                grounding = None
                if analyzer is not None:
                    frames = analyzer.sample(
                        result.clip, video=result.clip.local_path or result.path
                    )
                    analysis = analyzer.analyze(
                        frames, query=beat.search_text, narration=beat.search_text
                    )
                    result.clip.visual = analysis.to_dict()
                    result.clip.visual_semantic_match = analysis.semantic_match
                    analysed.append({
                        "beat": scene_id,
                        "kind": beat.kind,
                        "query": query,
                        "semantic_match": analysis.semantic_match,
                        "analyzed": analysis.analyzed,
                    })
                    if requirement is not None:
                        grounding = ground_requirement(
                            analyzer, frames, requirement
                        )
                        if grounding.failed:
                            # Not this beat's shot. Put the clip back rather
                            # than shipping it: the apple beat may not settle
                            # for an orange, and it may not settle for an
                            # apple cake either.
                            rejected.append({
                                "source": result.clip.key,
                                "score": grounding.score,
                                "failed_on": list(grounding.failed_on),
                                "looked_like": grounding.top_distractor,
                            })
                            used_keys.append(result.clip.key)
                            continue
                kept.append((result, grounding))
                used_keys.append(result.clip.key)
            return kept, rejected

        # The picture is continuous; the narration is not. Built against the
        # synthesized audio - pauses, tail and all - by ``shot_spans``.
        spans = shot_spans(script.beats, narration.scene_timings, timeline_end)

        for index, beat in enumerate(script.beats):
            scene_id = f"beat-{index:02d}"
            start, end = spans[index]
            if end <= start:
                continue                     # never synthesized; no picture owed
            span = end - start
            wanted = max(1, int(round(span / MAX_SHOT + 0.35)))
            requirement = required_visual_for(beat)
            entity = requirement.entity if requirement is not None else None

            chosen, rejected = take(beat.query, wanted, beat, requirement, scene_id)

            # Repair: the beat's own query is what returned the wrong food, so
            # repeating it deeper would return it again. Search the object,
            # and the state - "manzana" is what found the cake.
            used_queries = [beat.query]
            attempts = 0
            if requirement is not None:
                for query in state_repair_queries(requirement, used_queries):
                    if len(chosen) >= wanted or attempts >= self.REPAIR_ROUNDS:
                        break
                    attempts += 1
                    used_queries.append(query)
                    log.info(
                        "repair %d for %s: searching %r for %s",
                        attempts, scene_id, query, entity.name,
                    )
                    more, also = take(
                        query, wanted - len(chosen), beat, requirement, scene_id
                    )
                    rejected.extend(also)
                    repaired_shots += len(more)
                    chosen.extend(more)
                rounds_used = max(rounds_used, attempts)

            if not chosen and requirement is not None:
                # Nothing showed the food. Take the best available rather than
                # leaving a hole, and let the report say so - a missing beat is
                # a worse reel than a flagged one.
                log.warning(
                    "no footage showing %s for %s; falling back", entity.name, scene_id
                )
                chosen, _ = take(beat.query, wanted, beat, None, scene_id)

            if not chosen:
                log.warning("no footage for beat %s (%r)", scene_id, beat.query)
                continue

            if requirement is not None:
                # The weakest shot the beat kept, not the strongest. Every
                # shot in a beat is on screen while the line is spoken, so a
                # good first clip cannot excuse a bad second one - the same
                # reason the reel is graded per beat rather than per reel.
                judged = [g for _clip, g in chosen if g is not None and g.checked]
                worst = min(judged, key=lambda g: g.score, default=None)
                grounding_rows.append({
                    "beat": scene_id,
                    "item": beat.item_key,
                    "narration": beat.text,
                    "required_entity": entity.name,
                    "required_labels": list(entity.labels),
                    "required_attributes": list(requirement.required_attributes),
                    "forbidden_attributes": list(requirement.forbidden_attributes),
                    "sources": [c.clip.key for c, _g in chosen],
                    "score": round(worst.score, 3) if worst else 0.0,
                    "entity_presence_score": (
                        round(worst.entity_presence_score, 3) if worst else 0.0),
                    "state_match_score": (
                        round(worst.state_match_score, 3) if worst else 0.0),
                    "state_checked": bool(worst and worst.state_checked),
                    "context_match_score": (
                        round(worst.context_match_score, 3) if worst else 0.0),
                    "context_checked": bool(worst and worst.context_checked),
                    "dominant_subject_score": (
                        round(worst.dominant_subject_score, 3) if worst else 0.0),
                    "distractor_dominance_score": (
                        round(worst.distractor_dominance_score, 3) if worst else 0.0),
                    "failed_on": list(worst.failed_on) if worst else [],
                    "checked": bool(worst and worst.checked),
                    "passed": bool(worst and worst.passed),
                    "looked_like": worst.top_distractor if worst else "",
                    "rejected_candidates": rejected,
                    "repair_rounds": attempts,
                })

            per = span / len(chosen)
            offset = start
            for position, (result, _grounding) in enumerate(chosen):
                length = min(MAX_SHOT, max(MIN_SHOT * 0.6, per))
                if position == len(chosen) - 1:
                    # The beat's last shot runs to the exact second the next
                    # beat speaks. A floor here would make the picture longer
                    # than the audio and push every later beat off its words,
                    # which is the same defect as the frozen tail wearing a
                    # different hat.
                    length = max(0.1, end - offset)
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

        covered = sum(s.duration for s in shots)
        frozen_tail = round(max(0.0, timeline_end - covered), 3)
        log.info(
            "%d shots from %d distinct sources across %d beats "
            "(%.1fs of picture for %.1fs of reel)",
            len(shots), len(set(s.clip_key for s in shots)), len(script.beats),
            covered, timeline_end,
        )
        if frozen_tail > 0.05:
            log.warning(
                "the picture is %.2fs short of the narration; the last frame "
                "would be held", frozen_tail,
            )
        elif covered > timeline_end + 0.05:
            log.warning(
                "the picture runs %.2fs past the narration; the later beats "
                "are off their words", covered - timeline_end,
            )
        return shots, {
            "analysed": analysed,
            "item_grounding_results": grounding_rows,
            "repaired_item_shot_count": repaired_shots,
            "repair_rounds_used": rounds_used,
            "frozen_tail_duration": frozen_tail,
        }

    def _analyzer(self) -> Any | None:
        if self._injected_analyzer is not None:
            return self._injected_analyzer
        if not bool(self.config.get("visual.enabled", True)):
            return None
        from ..visual_analysis import VisualAnalyzer
        from ..visual_model import load_model

        settings = dict(self.config.get("visual.model", {}) or {})
        model = load_model(settings) if settings.get("enabled", True) else None

        # Two models, for the reason the long-form side runs two: MobileCLIP-S0
        # is the broad ranker and is measured at chance on "which fruit is
        # this", so the food grounding asks the validated ViT-L/14 instead. It
        # sees only the handful of candidates a beat actually downloads, not
        # the whole shortlist. If it will not load, grounding goes unmeasured
        # and the render carries on - like every other optional model here.
        claim_settings = dict(self.config.get("visual.claim_model", {}) or {})
        claim_model = (
            load_model(claim_settings)
            if claim_settings.get("enabled", True) else None
        )
        if claim_model is None:
            log.warning(
                "the claim model did not load; the food each beat names will "
                "not be checked"
            )
        return VisualAnalyzer(
            model=model,
            claim_model=claim_model,
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
            # Carried through rather than recomputed: these are per-beat facts
            # the planner established while it was choosing, and nothing
            # downstream can reconstruct them from the finished shot list.
            "item_grounding_results": list(clips.get("item_grounding_results", []) or []),
            "repaired_item_shot_count": int(clips.get("repaired_item_shot_count", 0) or 0),
            "repair_rounds_used": int(clips.get("repair_rounds_used", 0) or 0),
            "frozen_tail_duration": float(clips.get("frozen_tail_duration", 0.0) or 0.0),
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
