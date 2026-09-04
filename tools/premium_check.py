"""Why the footage is not premium, and whether a ranking change would help.

`final_shot_premium_visual_ratio` sat at 0.39 in run 38 against a 0.60 target,
and a single ratio cannot be worked on: 39% could be thirty renovations or
thirty dim rooms and those have opposite fixes. Worse, the only way to find
out used to be a thirty minute render.

So this searches the provider exactly as the pipeline does, inspects the
candidates with the real analyzer, and reports:

  * how many candidates were inspected
  * the premium ratio of the pool and of the clips a ranker would actually
    pick, which are different numbers and the second is the one that ships
  * why every non-premium clip failed, by name and count
  * the same figures for a *proposed* pool and ranking, so a change can be
    argued from a predicted number rather than from a hope
  * whether entity grounding and semantic relevance survive the change,
    because a ranking that buys premium footage by dropping relevance has
    made the video worse

Preview stills only. A full pass over a hundred candidates costs a few
hundred kilobytes and about a minute, against half an hour for a render.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vidfactory.config import load_config                       # noqa: E402
from vidfactory.entities import required_entity                 # noqa: E402
from vidfactory.queries import PREMIUM_QUERIES                  # noqa: E402
from vidfactory.ranking import (                                # noqa: E402
    ClipRanker,
    RankingContext,
    VisualRankingSettings,
    premium_visual_report,
    rank_with_vision,
    visual_score,
)
from vidfactory.stock.registry import build_providers           # noqa: E402
from vidfactory.visual_analysis import (                        # noqa: E402
    VisualAnalyzer,
    premium_breakdown,
    premium_failure_reason,
)
from vidfactory.visual_model import load_model                  # noqa: E402


#: What a decorating video about making a room look bigger actually searches
#: for. Taken from the knowledge base's own query vocabulary rather than
#: invented, so the pool resembles a real render's.
BASELINE_QUERIES: tuple[str, ...] = (
    "small living room",
    "living room rug under sofa",
    "curtains living room window",
    "painted wall trim interior",
    "living room wall art above sofa",
    "floor lamp living room corner",
    "mirror living room wall",
    "living room shelving storage",
)


def gather(provider: Any, queries: Sequence[str], per_query: int, pages: int) -> dict[str, Any]:
    """Every distinct candidate those queries return, remembering its query."""

    pool: dict[str, Any] = {}
    for query in queries:
        for page in range(1, pages + 1):
            try:
                results = provider.search(query, per_page=per_query, page=page)
            except Exception as exc:
                print(f"  search failed for {query!r} page {page}: {exc}")
                continue
            for clip in results:
                if clip.key not in pool:
                    clip.query = query
                    pool[clip.key] = clip
    return pool


def inspect(analyzer: VisualAnalyzer, pool: dict[str, Any]) -> None:
    """Decode and measure every candidate once; both arms reuse the result."""

    for index, clip in enumerate(pool.values(), start=1):
        if getattr(clip, "visual", None):
            continue
        analysis = analyzer.analyze_clip(clip, query=clip.query, narration=clip.query)
        clip.visual = analysis.to_dict()
        clip.visual_semantic_match = analysis.semantic_match
        if index % 25 == 0:
            print(f"  inspected {index}/{len(pool)}")


def select(
    clips: Sequence[Any],
    context: RankingContext,
    ranker: ClipRanker,
    settings: VisualRankingSettings,
    wanted: int,
) -> list[Any]:
    """What this ranking would actually put on screen."""

    ranked = ranker.rank(list(clips), context)
    with_vision = rank_with_vision(ranked, settings)
    with_vision.sort(key=lambda c: visual_score(c, settings)[0], reverse=True)
    return with_vision[:wanted]


def measure(name: str, clips: Sequence[Any]) -> dict[str, Any]:
    pairs = [
        (premium_visual_report(c, getattr(c, "query", "")), dict(c.visual or {}))
        for c in clips
    ]
    breakdown = premium_breakdown(pairs)

    semantics = [
        float(dict(c.visual or {}).get("semantic_match", 0.0))
        for c in clips
        if dict(c.visual or {}).get("analyzed")
    ]
    grounded = [
        dict(c.visual or {}) for c in clips
        if dict(c.visual or {}).get("entity") and
        dict(c.visual or {}).get("entity_grounding_checked")
    ]
    failed = [g for g in grounded if not g.get("entity_grounding_passed")]
    return {
        "name": name,
        "clips": len(clips),
        "premium_ratio": breakdown["ratio"],
        "reasons": breakdown["reasons"],
        "percentages": breakdown["percentages"],
        "semantic_average": round(sum(semantics) / len(semantics), 3) if semantics else 0.0,
        "low_relevance": sum(1 for s in semantics if s < 0.50),
        "grounding_checked": len(grounded),
        "grounding_failed": len(failed),
    }


def show(row: dict[str, Any]) -> None:
    print(f"\n--- {row['name']} ---")
    print(f"  clips                {row['clips']}")
    print(f"  premium ratio        {row['premium_ratio']:.3f}")
    print(f"  semantic average     {row['semantic_average']:.3f}")
    print(f"  below 0.50 relevance {row['low_relevance']}")
    print(f"  grounding            {row['grounding_failed']} failed "
          f"of {row['grounding_checked']} checked")
    print("  why not premium:")
    for reason, count in row["reasons"].items():
        print(f"    {reason:32} {count:>4}  {row['percentages'][reason]:>5.1f}%")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--per-query", type=int, default=15)
    parser.add_argument("--pages", type=int, default=1)
    parser.add_argument("--select", type=int, default=40,
                        help="how many clips a render of this size would use")
    parser.add_argument("--baseline-flag-penalty", type=float, default=60.0)
    parser.add_argument("--proposed-flag-penalty", type=float, default=110.0)
    parser.add_argument("--json-out", default="")
    parser.add_argument("--config", default="config.yaml")
    args = parser.parse_args(argv)

    config = load_config(args.config)
    providers = [p for p in build_providers(dict(config.get("sources", {}) or {}))
                 if p.name != "local"]
    if not providers:
        print("[FAIL] no stock provider - set PEXELS_API_KEY")
        return 1
    provider = providers[0]

    model = load_model(dict(config.get("visual.model", {}) or {}))
    print(f"visual model: {getattr(model, 'name', None) or 'pixel statistics only'}")
    analyzer = VisualAnalyzer(
        model=model,
        frames_per_clip=int(config.get("visual.frames_per_clip", 3)),
        allow_remote_video=False,
    )

    print(f"\nsearching {len(BASELINE_QUERIES)} baseline queries...")
    baseline_pool = gather(provider, BASELINE_QUERIES, args.per_query, args.pages)
    print(f"  {len(baseline_pool)} distinct candidates")

    print(f"searching {len(PREMIUM_QUERIES)} premium queries...")
    premium_pool = gather(provider, PREMIUM_QUERIES, args.per_query, args.pages)
    print(f"  {len(premium_pool)} distinct candidates")

    combined = dict(baseline_pool)
    combined.update(premium_pool)
    print(f"\ninspecting {len(combined)} candidates (preview stills)...")
    inspect(analyzer, combined)

    ranker = ClipRanker(
        weights=dict(config.get("ranking.weights", {}) or {}),
        min_score=float(config.get("ranking.min_score", 28)),
        max_uses_per_clip=int(config.get("ranking.max_uses_per_clip", 3)),
    )
    context = RankingContext(
        query="small living room ideas that make a space look bigger",
        keywords=("living", "room", "small", "space"),
        min_shot_seconds=3.0,
        max_shot_seconds=6.0,
        prefer_width=1920,
        min_width=1280,
        min_height=720,
        min_source_seconds=5.0,
        cooldown_days=45.0,
        history={},
        enforce_aspirational=bool(config.get("ranking.enforce_aspirational", True)),
        enforce_premium=False,
        min_interior_relevance=float(config.get("ranking.min_interior_relevance", 0.35)),
    )

    def settings(penalty: float) -> VisualRankingSettings:
        weights = dict(config.get("visual.weights", {}) or {})
        return VisualRankingSettings(
            semantic=float(weights.get("semantic", 45)),
            subject=float(weights.get("subject", 30)),
            quality=float(weights.get("quality", 18)),
            novelty=float(weights.get("novelty", 12)),
            technical=float(weights.get("technical", 8)),
            min_semantic=float(config.get("visual.min_semantic_match", 0.28)),
            flag_penalty=penalty,
        )

    rows = [
        measure("pool: baseline queries only", list(baseline_pool.values())),
        measure("pool: baseline + premium queries", list(combined.values())),
        measure(
            f"SELECTED before (baseline queries, flag penalty "
            f"{args.baseline_flag_penalty:.0f})",
            select(list(baseline_pool.values()), context, ranker,
                   settings(args.baseline_flag_penalty), args.select),
        ),
        measure(
            f"SELECTED after (+premium queries, flag penalty "
            f"{args.proposed_flag_penalty:.0f})",
            select(list(combined.values()), context, ranker,
                   settings(args.proposed_flag_penalty), args.select),
        ),
    ]
    for row in rows:
        show(row)

    before, after = rows[2], rows[3]
    print("\n" + "=" * 62)
    print(f"premium ratio   {before['premium_ratio']:.3f} -> "
          f"{after['premium_ratio']:.3f}  (target 0.600)")
    print(f"semantic avg    {before['semantic_average']:.3f} -> "
          f"{after['semantic_average']:.3f}  (must not fall)")
    print(f"grounding fails {before['grounding_failed']} -> {after['grounding_failed']}")
    print(f"candidates inspected: {len(combined)}")

    if args.json_out:
        Path(args.json_out).write_text(json.dumps(rows, indent=2), encoding="utf-8")
        print(f"rows written to {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
