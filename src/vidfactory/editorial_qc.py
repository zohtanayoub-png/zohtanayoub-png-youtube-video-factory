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
        "min_causal_promise_alignment": 0.85,
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
    low_relevance = sum(1 for s in semantic_scores if s < 0.45)

    # A clip is premium only if its caption *and* its pixels agree. Run 6
    # reported 91% premium footage from captions alone while the video
    # contained a floor plan, two empty rooms and a plastic-wrapped sofa.
    premium_clips = 0
    for report, visual in zip(premium_reports, visual_reports):
        by_caption = bool(report.get("is_premium", False))
        if visual.get("analyzed"):
            premium_clips += int(by_caption and bool(visual.get("is_premium_visual")))
        else:
            premium_clips += int(by_caption)
    premium_ratio = round(premium_clips / len(selected), 3) if selected else 0.0

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
    visual_meta = dict(visual_stats or {})
    causal_score = float(getattr(causal, "overall", 1.0)) if causal is not None else 1.0
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
        "mean_interior_relevance": mean_relevance,
        "promise_alignment_failures": int(promise_alignment_failures),
        # ---- real frame inspection --------------------------------------
        "visual_semantic_match_average": semantic_average,
        "low_relevance_clip_count": low_relevance,
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
        "search": stats,
        **diversity,
    }

    checks = [
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
            f"{premium_ratio:.0%} of clips are premium interior footage "
            f"(minimum {float(limits['min_premium_visual_ratio']):.0%}); "
            f"{people_dominant} people-dominant, {dark_clips} dark, "
            f"{empty_clips} empty",
            severity="warning",
        ),
        EditorialCheck(
            "visual_semantic_match",
            semantic_average >= float(limits["min_visual_semantic_match"]),
            f"frames match the narration at {semantic_average:.2f} on average "
            f"(minimum {limits['min_visual_semantic_match']}), measured on "
            f"{len(inspected)} clip(s) by {visual_meta.get('model', 'no model')}",
            severity="warning",
        ),
        EditorialCheck(
            "low_relevance_clips",
            (low_relevance / len(inspected) if inspected else 0.0)
            <= float(limits["max_low_relevance_clips"]),
            f"{low_relevance} of {len(inspected)} inspected clips barely match "
            f"the sentence they illustrate "
            f"(limit {float(limits['max_low_relevance_clips']):.0%})",
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
    return report
