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
) -> EditorialReport:
    """Measure the editorial quality of a finished edit."""

    limits = {
        "max_source_reuse": 0,
        "min_unique_source_ratio": 0.95,
        "max_generic_query_percentage": 0.35,
        "min_title_alignment": 0.8,
        "min_creator_diversity": 0.5,
        "min_average_clip_score": 40.0,
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
