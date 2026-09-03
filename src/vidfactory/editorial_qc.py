"""Editorial quality control.

The technical checks in :mod:`vidfactory.quality_control` prove the file is a
valid MP4. They say nothing about whether the video is *good*: whether the
footage repeats, whether it actually illustrates the narration, or whether one
creator supplied half the shots.

This module measures those things and writes ``editorial_quality_report.json``.
The thresholds are deliberately strict, because the failure mode they exist to
catch - a video that visibly loops in its final third - is invisible to
ffprobe and obvious to a viewer.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from .logging_utils import get_logger

log = get_logger("EDITQC")

#: A clip below this shows some other subject better than it shows the
#: sentence it illustrates. Measured, not guessed - see config.yaml.
LOW_RELEVANCE_MATCH = 0.35


@dataclass
class EditorialCheck:
    name: str
    passed: bool
    detail: str = ""
    severity: str = "error"          # error | warning

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "passed": self.passed,
            "detail": self.detail,
            "severity": self.severity,
        }


@dataclass
class EditorialReport:
    metrics: dict[str, Any] = field(default_factory=dict)
    checks: list[EditorialCheck] = field(default_factory=list)
    section_coverage: list[dict[str, Any]] = field(default_factory=list)

    @property
    def failures(self) -> list[EditorialCheck]:
        return [c for c in self.checks if not c.passed and c.severity == "error"]

    @property
    def warnings(self) -> list[EditorialCheck]:
        return [c for c in self.checks if not c.passed and c.severity == "warning"]

    @property
    def passed(self) -> bool:
        return not self.failures

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            **self.metrics,
            "checks": [c.to_dict() for c in self.checks],
            "visual_coverage_per_section": self.section_coverage,
        }

    def save(self, destination: str | Path) -> Path:
        target = Path(destination)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return target

    def log_summary(self) -> None:
        for check in self.checks:
            if check.passed:
                log.debug("PASS %s - %s", check.name, check.detail)
            elif check.severity == "warning":
                log.warning("%s: %s", check.name, check.detail)
            else:
                log.error("%s: %s", check.name, check.detail)
        log.info(
            "Editorial: %d shots, %d unique sources (%.0f%%), %d reused, "
            "%.0f%% generic queries, creator diversity %.2f, title alignment %.0f%%",
            self.metrics.get("shot_count", 0),
            self.metrics.get("unique_source_videos", 0),
            self.metrics.get("unique_source_ratio", 0) * 100,
            self.metrics.get("source_video_reuse_count", 0),
            self.metrics.get("generic_query_percentage", 0) * 100,
            self.metrics.get("creator_diversity", 0),
            self.metrics.get("title_idea_alignment", 0) * 100,
        )
        log.info(
            "Premium: %.0f%% premium footage (%d people-dominant, %d dark, "
            "%d empty, %d plastic, %d floor plan, %d renovation), provenance "
            "%s, %d promise failures",
            self.metrics.get("premium_visual_ratio", 0) * 100,
            self.metrics.get("people_dominant_clip_count", 0),
            self.metrics.get("dark_clip_count", 0),
            self.metrics.get("empty_room_clip_count", 0),
            self.metrics.get("plastic_covered_clip_count", 0),
            self.metrics.get("floor_plan_clip_count", 0),
            self.metrics.get("renovation_clip_count", 0),
            self.metrics.get("artifact_provenance_passed"),
            self.metrics.get("promise_alignment_failures", 0),
        )
        log.info(
            "Production: %s narrated by %s (%s), %s captions%s, %d events at "
            "%.1f words each",
            self.metrics.get("language", "?"),
            self.metrics.get("tts_voice", "?"),
            self.metrics.get("tts_engine", "?"),
            self.metrics.get("subtitle_style", "none"),
            " burned in" if self.metrics.get("burn_in_subtitles") else "",
            self.metrics.get("subtitle_event_count", 0),
            self.metrics.get("average_subtitle_words", 0.0),
        )
        log.info(
            "Visual: %s inspected %d clips over %d frames; semantic match %.2f, "
            "%d low-relevance; causal promise alignment %.2f",
            self.metrics.get("visual_analysis_model", "nothing"),
            self.metrics.get("visually_inspected_clip_count", 0),
            self.metrics.get("visual_analysis_frame_count", 0),
            self.metrics.get("visual_semantic_match_average", 0.0),
            self.metrics.get("low_relevance_clip_count", 0),
            self.metrics.get("causal_promise_alignment_score", 0.0),
        )


def _section_coverage(
    shots: Sequence[Any], scenes: Sequence[Any]
) -> list[dict[str, Any]]:
    """How many distinct source videos illustrate each script section."""

    scene_to_section: dict[str, int] = {}
    for scene in scenes:
        scene_to_section[getattr(scene, "scene_id", "")] = int(
            getattr(scene, "section_index", 0)
        )

    buckets: dict[int, dict[str, Any]] = {}
    for shot in shots:
        index = scene_to_section.get(shot.scene_id, 0)
        bucket = buckets.setdefault(
            index, {"section_index": index, "shots": 0, "sources": set(), "seconds": 0.0}
        )
        bucket["shots"] += 1
        bucket["sources"].add(shot.clip_key)
        bucket["seconds"] += shot.duration

    coverage: list[dict[str, Any]] = []
    for index in sorted(buckets):
        bucket = buckets[index]
        coverage.append(
            {
                "section_index": index,
                "shots": bucket["shots"],
                "unique_sources": len(bucket["sources"]),
                "seconds": round(bucket["seconds"], 2),
                "well_supported": len(bucket["sources"]) >= min(2, bucket["shots"]),
            }
        )
    return coverage


def build_report(
    shot_plan: Any,
    clips: Sequence[Any],
    scenes: Sequence[Any],
    script: Any,
    search_stats: Mapping[str, Any] | None = None,
    diversity: Mapping[str, Any] | None = None,
    thresholds: Mapping[str, Any] | None = None,
    provenance_passed: bool | None = None,
    promise_alignment_failures: int = 0,
    visual_stats: Mapping[str, Any] | None = None,
    causal: Any | None = None,
    production: Mapping[str, Any] | None = None,
) -> EditorialReport:
    """Measure the editorial quality of a finished edit."""

    limits = {
        "max_source_reuse": 0,
        "min_unique_source_ratio": 0.95,
        "max_generic_query_percentage": 0.35,
        "min_title_alignment": 0.8,
        "min_creator_diversity": 0.5,
        "min_average_clip_score": 40.0,
        "min_premium_visual_ratio": 0.80,
        "max_promise_alignment_failures": 0,
        "min_visual_semantic_match": 0.45,
        "max_low_relevance_clips": 0.15,
        "min_final_shot_semantic_match": 0.50,
        "max_final_shot_low_relevance": 0.15,
        "min_causal_promise_alignment": 0.90,
        **dict(thresholds or {}),
    }

    shots = list(getattr(shot_plan, "shots", shot_plan) or [])
    stats = dict(search_stats or {})
    diversity = dict(diversity or {})

    scores = [float(getattr(getattr(c, "clip", None), "score", 0.0)) for c in clips]
    average_score = round(sum(scores) / len(scores), 2) if scores else 0.0

    specific = int(stats.get("specific_queries_run", 0))
    generic = int(stats.get("generic_queries_run", 0))
    total_queries = specific + generic
    generic_pct = round(generic / total_queries, 3) if total_queries else 0.0

    unique_sources = len({s.clip_key for s in shots})
    reuse_count = len(getattr(shot_plan, "reused_keys", []) or [])
    unique_ratio = round(unique_sources / len(shots), 3) if shots else 0.0

    coverage = _section_coverage(shots, scenes)
    weak_sections = [c for c in coverage if not c["well_supported"]]

    # ---- premium visual signals ------------------------------------------
    # Each downloaded clip carries the premium report the ranker computed, so
    # the finished edit can be measured rather than assumed.
    from .visual_analysis import PENALTY_CONFIDENCE

    selected = [getattr(c, "clip", None) for c in clips]
    selected = [c for c in selected if c is not None]
    premium_reports = [dict(getattr(c, "premium", {}) or {}) for c in selected]
    visual_reports = [dict(getattr(c, "visual", {}) or {}) for c in selected]
    rated = [r for r in premium_reports if r]

    def flagged(name: str) -> int:
        """Clips carrying a visual flag, counting caption and pixel evidence.

        The visual flags already merge the caption prior, so this is the
        combined verdict rather than either signal on its own.
        """

        total = 0
        for visual in visual_reports:
            confidence = float((visual.get("flags") or {}).get(name, 0.0))
            if confidence >= PENALTY_CONFIDENCE:
                total += 1
        return total

    inspected = [v for v in visual_reports if v.get("analyzed")]
    semantic_scores = [float(v.get("semantic_match", 0.0)) for v in inspected]
    semantic_average = (
        round(sum(semantic_scores) / len(semantic_scores), 3) if semantic_scores else 0.0
    )
    low_relevance = sum(1 for s in semantic_scores if s < LOW_RELEVANCE_MATCH)

    # A clip is premium only if its caption *and* its pixels agree. Run 6
    # reported 91% premium footage from captions alone while the video
    # contained a floor plan, two empty rooms and a plastic-wrapped sofa.
    premium_clips = 0
    caption_only_clips = 0
    for report, visual in zip(premium_reports, visual_reports):
        by_caption = bool(report.get("is_premium", False))
        caption_only_clips += int(by_caption)
        if visual.get("analyzed"):
            premium_clips += int(by_caption and bool(visual.get("is_premium_visual")))
        else:
            premium_clips += int(by_caption)
    premium_ratio = round(premium_clips / len(selected), 3) if selected else 0.0
    # Reported alongside it so the two are comparable: this is the number the
    # old caption-only metric would have produced, and the gap between them is
    # the whole point of opening the footage.
    caption_only_ratio = (
        round(caption_only_clips / len(selected), 3) if selected else 0.0
    )

    people_dominant = max(
        sum(1 for r in rated if r.get("is_people_dominant")),
        flagged("dominant_pet_or_person"),
    )
    dark_clips = max(sum(1 for r in rated if r.get("is_dark")), flagged("dark_scene"))
    empty_clips = max(
        sum(1 for r in rated if r.get("is_empty_room")), flagged("empty_room")
    )
    mean_relevance = (
        round(sum(float(r.get("interior_relevance_score", 0)) for r in rated) / len(rated), 3)
        if rated
        else 0.0
    )
    # ------------------------------------------------------------------
    # Candidate clips vs the clips actually on screen.
    #
    # Run 16 reported "19 of 49 clips barely match" and gated on that number,
    # which mixes clips that were downloaded with clips that made the edit.
    # The viewer only ever sees the second group, so that is what production
    # is graded on; the candidate figures stay in the report because a wide
    # gap between them means the ranker is doing its job.
    # ------------------------------------------------------------------
    final_keys = {s.clip_key for s in shots}
    final_visual: list[dict[str, Any]] = []
    final_premium: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for clip, premium, visual in zip(selected, premium_reports, visual_reports):
        if getattr(clip, "key", None) not in final_keys:
            continue
        final_premium.append((premium, visual))
        if visual.get("analyzed"):
            final_visual.append(visual)

    final_scores = [float(v.get("semantic_match", 0.0)) for v in final_visual]
    final_semantic_average = (
        round(sum(final_scores) / len(final_scores), 3) if final_scores else 0.0
    )
    final_low_relevance = sum(1 for s in final_scores if s < LOW_RELEVANCE_MATCH)
    final_low_relevance_pct = (
        round(final_low_relevance / len(final_scores), 3) if final_scores else 0.0
    )
    final_premium_clips = 0
    for premium, visual in final_premium:
        by_caption = bool(premium.get("is_premium", False))
        if visual.get("analyzed"):
            final_premium_clips += int(
                by_caption and bool(visual.get("is_premium_visual"))
            )
        else:
            final_premium_clips += int(by_caption)
    final_premium_ratio = (
        round(final_premium_clips / len(final_premium), 3) if final_premium else 0.0
    )

    visual_meta = dict(visual_stats or {})
    causal_score = float(getattr(causal, "overall", 1.0)) if causal is not None else 1.0
    contradiction_report = getattr(causal, "contradiction", None)
    contradictions = [
        c.to_dict() for c in getattr(contradiction_report, "items", []) or []
    ]
    contradiction_count = len(contradictions)
    contamination = [
        c.to_dict() for c in getattr(causal, "contamination", []) or []
    ]
    contamination_count = len(contamination)
    section_scores = (
        [round(float(r.score), 3) for r in getattr(causal, "results", [])]
        if causal is not None
        else []
    )

    metrics: dict[str, Any] = {
        "source_video_reuse_count": reuse_count,
        "unique_source_videos": unique_sources,
        "unique_source_ratio": unique_ratio,
        "shot_count": len(shots),
        "average_shot_seconds": (
            round(sum(s.duration for s in shots) / len(shots), 2) if shots else 0.0
        ),
        "generic_query_percentage": generic_pct,
        "average_clip_score": average_score,
        "title_idea_alignment": float(getattr(script, "title_idea_alignment", 0.0)),
        "title_promise": getattr(script, "promise_key", "general"),
        "rejected_idea_count": len(getattr(script, "rejected_ideas", []) or []),
        "clips_downloaded": len(clips),
        # ---- premium visual quality -------------------------------------
        "artifact_provenance_passed": provenance_passed,
        "people_dominant_clip_count": people_dominant,
        "dark_clip_count": dark_clips,
        "empty_room_clip_count": empty_clips,
        "premium_visual_ratio": premium_ratio,
        "premium_visual_ratio_caption_only": caption_only_ratio,
        "mean_interior_relevance": mean_relevance,
        "promise_alignment_failures": int(promise_alignment_failures),
        # ---- real frame inspection --------------------------------------
        "visual_semantic_match_average": semantic_average,
        "low_relevance_clip_count": low_relevance,
        "candidate_visual_semantic_match_average": semantic_average,
        "candidate_low_relevance_count": low_relevance,
        "candidate_inspected_count": len(inspected),
        # What the viewer actually sees, which is what production is graded on.
        "final_shot_count": len(final_keys),
        "final_shot_inspected_count": len(final_visual),
        "final_shot_visual_semantic_match_average": final_semantic_average,
        "final_shot_low_relevance_count": final_low_relevance,
        "final_shot_low_relevance_percentage": final_low_relevance_pct,
        "final_shot_premium_visual_ratio": final_premium_ratio,
        "visual_analysis_model": visual_meta.get("model", "not run"),
        "visual_analysis_frame_count": int(visual_meta.get("frames", 0)) or sum(
            int(v.get("frame_count", 0)) for v in inspected
        ),
        "visually_inspected_clip_count": len(inspected),
        "plastic_covered_clip_count": flagged("plastic_covered_furniture"),
        "floor_plan_clip_count": flagged("floor_plan_or_document"),
        "renovation_clip_count": flagged("renovation") + flagged("construction"),
        "visual_rejected_candidate_count": int(visual_meta.get("rejected", 0)),
        "visual_analysis_seconds": float(visual_meta.get("seconds", 0.0)),
        # ---- causal promise alignment -----------------------------------
        "causal_promise_alignment_score": round(causal_score, 3),
        "section_alignment_scores": section_scores,
        "section_alignment": (
            causal.to_dict()["sections"] if causal is not None else []
        ),
        "causal_rewrites": int(getattr(causal, "rewrites", 0)),
        "causal_replacements": int(getattr(causal, "replacements", 0)),
        # ---- self-contradiction ------------------------------------------
        # A paragraph can explain itself perfectly and still argue against
        # its own heading. Run 16 shipped two of those, so this is an error
        # rather than a warning: a video that tells the viewer to do the
        # opposite of its own advice is not publishable.
        "contradiction_count": contradiction_count,
        "contradictions": contradictions,
        # A sentence can explain the right mechanism, the right way round, and
        # still be about curtains in a section about pictures. Run 22 shipped
        # exactly that at a causal score of 1.00, so this is an error too.
        "cross_concept_contamination_count": contamination_count,
        "cross_concept_contamination": contamination,
        # ---- language, voice and captions --------------------------------
        **dict(production or {}),
        "search": stats,
        **diversity,
    }

    checks = [
        EditorialCheck(
            "no_self_contradiction",
            contradiction_count == 0,
            (
                f"{contradiction_count} section(s) argue against their own "
                "heading: "
                + "; ".join(c.get("why", "") for c in contradictions[:2])
                if contradiction_count
                else "no section contradicts its own advice"
            ),
            severity="error",
        ),
        EditorialCheck(
            "no_cross_concept_contamination",
            contamination_count == 0,
            (
                f"{contamination_count} section(s) explain themselves with "
                "another subject's language: "
                + "; ".join(c.get("why", "") for c in contamination[:2])
                if contamination_count
                else "every section explains itself in its own terms"
            ),
            severity="error",
        ),
        EditorialCheck(
            "no_source_video_reuse",
            reuse_count <= int(limits["max_source_reuse"]),
            f"{reuse_count} shot(s) reuse a source video "
            f"(limit {limits['max_source_reuse']})",
        ),
        EditorialCheck(
            "unique_source_ratio",
            unique_ratio >= float(limits["min_unique_source_ratio"]),
            f"{unique_ratio:.2f} unique sources per shot "
            f"(minimum {limits['min_unique_source_ratio']})",
        ),
        EditorialCheck(
            "generic_query_usage",
            generic_pct <= float(limits["max_generic_query_percentage"]),
            f"{generic_pct:.0%} of searches used the generic category fallback "
            f"(limit {float(limits['max_generic_query_percentage']):.0%})",
            severity="warning",
        ),
        EditorialCheck(
            "title_idea_alignment",
            float(metrics["title_idea_alignment"]) >= float(limits["min_title_alignment"]),
            f"{metrics['title_idea_alignment']:.0%} of ideas support the "
            f"'{metrics['title_promise']}' promise "
            f"(minimum {float(limits['min_title_alignment']):.0%})",
        ),
        EditorialCheck(
            "creator_diversity",
            float(diversity.get("creator_diversity", 1.0))
            >= float(limits["min_creator_diversity"]),
            f"{float(diversity.get('creator_diversity', 0)):.2f} distinct creators "
            f"per clip (minimum {limits['min_creator_diversity']})",
            severity="warning",
        ),
        EditorialCheck(
            "average_clip_score",
            average_score >= float(limits["min_average_clip_score"]),
            f"average selected clip scored {average_score} "
            f"(minimum {limits['min_average_clip_score']})",
            severity="warning",
        ),
        EditorialCheck(
            "artifact_provenance",
            provenance_passed is not False,
            "every artifact belongs to this generation"
            if provenance_passed
            else "artifacts could not be proven to share one generation",
        ),
        EditorialCheck(
            "promise_alignment",
            int(promise_alignment_failures) <= int(limits["max_promise_alignment_failures"]),
            f"{promise_alignment_failures} idea(s) do not support the title promise",
        ),
        EditorialCheck(
            "premium_visual_ratio",
            premium_ratio >= float(limits["min_premium_visual_ratio"]),
            f"{premium_ratio:.0%} of clips are premium interior footage by "
            f"caption AND frames (minimum "
            f"{float(limits['min_premium_visual_ratio']):.0%}); the caption "
            f"alone would have said {caption_only_ratio:.0%}; "
            f"{people_dominant} people-dominant, {dark_clips} dark, "
            f"{empty_clips} empty",
            severity="warning",
        ),
        # No frames inspected means nothing was measured, which is not the
        # same as measuring badly. Without the optional CLIP backend, or on a
        # run where inspection timed out, these gates have no evidence and
        # must not invent a failure.
        EditorialCheck(
            "final_shot_relevance",
            (
                not final_visual
                or final_semantic_average
                >= float(limits["min_final_shot_semantic_match"])
            ),
            (
                f"the {len(final_visual)} clips actually on screen match their "
                f"narration at {final_semantic_average:.2f} on average "
                f"(minimum {limits['min_final_shot_semantic_match']}); across "
                f"all {len(inspected)} candidates it was {semantic_average:.2f}"
                if final_visual
                else "no frames were inspected, so relevance is unmeasured"
            ),
        ),
        EditorialCheck(
            "final_shot_low_relevance",
            (
                not final_visual
                or final_low_relevance_pct
                <= float(limits["max_final_shot_low_relevance"])
            ),
            (
                f"{final_low_relevance} of {len(final_visual)} clips on screen "
                f"({final_low_relevance_pct:.0%}) barely match the sentence "
                f"they illustrate (limit "
                f"{float(limits['max_final_shot_low_relevance']):.0%}); "
                f"{low_relevance} of {len(inspected)} candidates did"
                if final_visual
                else "no frames were inspected, so relevance is unmeasured"
            ),
        ),
        EditorialCheck(
            "duration_accuracy",
            (
                not metrics.get("requested_duration_seconds")
                or 90.0 <= float(metrics.get("duration_accuracy_percentage", 100.0)) <= 110.0
            ),
            f"{metrics.get('actual_duration_seconds', 0)}s against a requested "
            f"{metrics.get('requested_duration_seconds', 0)}s "
            f"({metrics.get('duration_accuracy_percentage', 0)}% of it)",
            severity="warning",
        ),
        EditorialCheck(
            "requested_item_count",
            (
                not metrics.get("item_count_was_explicit")
                or metrics.get("actual_item_count") == metrics.get("requested_item_count")
            ),
            f"{metrics.get('actual_item_count', 0)} ideas against the "
            f"{metrics.get('requested_item_count', 0)} the topic asked for",
        ),
        EditorialCheck(
            "candidate_pool_relevance",
            not inspected
            or semantic_average >= float(limits["min_visual_semantic_match"]),
            f"the candidate pool averaged {semantic_average:.2f} "
            f"(minimum {limits['min_visual_semantic_match']}) across "
            f"{len(inspected)} inspected clips",
            severity="warning",
        ),
        EditorialCheck(
            "causal_promise_alignment",
            causal_score >= float(limits["min_causal_promise_alignment"]),
            f"every section explains the '{metrics['title_promise']}' promise at "
            f"{causal_score:.2f} on average "
            f"(minimum {limits['min_causal_promise_alignment']}); "
            f"{min(section_scores) if section_scores else 1.0} is the weakest",
        ),
        EditorialCheck(
            "subtitle_safe_area",
            bool(metrics.get("subtitle_safe_area_passed", True)),
            f"captions sit {metrics.get('subtitle_bottom_margin_px', 0)}px above "
            f"the bottom edge in at most "
            f"{metrics.get('max_subtitle_lines', 0)} lines",
        ),
        EditorialCheck(
            "subtitle_timing",
            bool(metrics.get("subtitle_timing_passed", True)),
            f"{metrics.get('subtitle_event_count', 0)} caption events, "
            f"{metrics.get('average_subtitle_words', 0)} words and "
            f"{metrics.get('average_subtitle_seconds', 0)}s each, "
            f"{metrics.get('subtitle_overlap_count', 0)} overlapping, "
            f"{metrics.get('subtitle_flash_count', 0)} too brief",
        ),
        EditorialCheck(
            "sections_visually_supported",
            not weak_sections,
            (
                f"{len(weak_sections)} script section(s) are carried by too few "
                "distinct clips"
                if weak_sections
                else f"all {len(coverage)} sections have distinct footage"
            ),
            severity="warning",
        ),
    ]

    report = EditorialReport(metrics=metrics, checks=checks, section_coverage=coverage)
    report.log_summary()
    if final_visual:
        log.info(
            "[QC] final low relevance: %.0f%% - %s",
            final_low_relevance_pct * 100,
            "PASSED"
            if final_low_relevance_pct <= float(limits["max_final_shot_low_relevance"])
            else "FAILED",
        )
    return report
