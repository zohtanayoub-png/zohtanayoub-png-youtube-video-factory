"""Can MobileCLIP tell an apple from an orange?

The long-form side answered the equivalent question three times before it
trusted a threshold, and twice the answer was "no". So this asks it for food
rather than assuming: search the provider for each food, search it for the
food that actually turned up instead, score both piles with the same probe,
and print where the two separate - if they separate at all.

Two numbers matter and they are not the same number:

* **kept** - of clips found by searching for the food itself, how many the
  probe accepts. Every one it rejects is a good clip the repair pass has to
  replace, so this is a real cost.
* **rejected** - of clips found by searching for the confusable food, how many
  the probe catches. This is the whole point.

A cut is only worth having where the second is high and the first is ~100%.
Run it with the `reel-entity-check` task on the video workflow.
"""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Any

from vidfactory.config import load_config
from vidfactory.downloader import ClipDownloader
from vidfactory.logging_utils import get_logger, setup_logging
from vidfactory.reels.foods import BY_NAME, identify_food, score_food
from vidfactory.stock import build_providers
from vidfactory.visual_analysis import VisualAnalyzer
from vidfactory.visual_model import load_model

log = get_logger("FOODCHECK")

#: The confusions worth measuring: the food, and what a search returns instead.
#: The apple/orange pair is first because it is the one that shipped.
CONFUSIONS: tuple[tuple[str, str], ...] = (
    ("manzana", "fresh oranges on a wooden table"),
    ("fresas", "fresh raspberries close up bowl"),
    ("frambuesas", "fresh strawberries in a white bowl"),
    ("kiwi", "fresh limes on a table"),
    ("aguacate", "sliced kiwi fruit on a plate"),
)

SWEEP = (0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80)


def score_pile(analyzer: Any, downloader: Any, providers: Any, entity: Any,
               query: str, limit: int, scorer: Any) -> list[float]:
    """Grounding scores for `limit` clips found by `query`."""

    candidates: list[Any] = []
    for provider in providers:
        try:
            candidates.extend(provider.search(query, per_page=limit * 2, page=1))
        except Exception as exc:                           # pragma: no cover
            log.warning("search failed for %r: %s", query, exc)
    scores: list[float] = []
    for clip in candidates:
        if len(scores) >= limit:
            break
        fetched = downloader.fetch_many([clip], needed=1)
        if not fetched:
            continue
        result = fetched[0]
        frames = analyzer.sample(
            result.clip, video=result.clip.local_path or result.path
        )
        grounding = analyzer.ground_entity(frames, entity, scorer)
        if grounding.checked:
            scores.append(grounding.score)
    return scores


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--clips", type=int, default=6,
                        help="clips per pile (each is a download and a decode)")
    parser.add_argument("--out", default="output/reel-entity-check.json")
    parser.add_argument("--scorer", default="identify",
                        choices=["identify", "dominance"])
    parser.add_argument("--model", default="rank", choices=["rank", "claim"],
                        help="rank = MobileCLIP-S0, claim = the validated ViT-L/14")
    args = parser.parse_args(argv)
    setup_logging(verbose=False)

    config = load_config(args.config)
    providers = build_providers(dict(config.get("sources", {}) or {}))
    if not providers:
        print("no stock provider is available")
        return 2
    key = "visual.model" if args.model == "rank" else "visual.claim_model"
    settings = dict(config.get(key, {}) or {})
    settings.setdefault("enabled", True)
    model = load_model(settings) if settings.get("enabled", True) else None
    if model is None:
        print("no visual model; nothing to calibrate")
        return 2
    analyzer = VisualAnalyzer(
        model=model,
        frames_per_clip=int(config.get("visual.frames_per_clip", 3)),
        allow_remote_video=False,
    )

    work = Path("work/foodcheck")
    downloader = ClipDownloader(
        workdir=work, min_width=1280, min_height=720, min_seconds=2.0,
        max_mb=90, timeout=120, retries=2,
    )

    rows: list[dict[str, Any]] = []
    for name, wrong_query in CONFUSIONS:
        entity = BY_NAME[name]
        scorer = identify_food if args.scorer == "identify" else score_food
        right = score_pile(
            analyzer, downloader, providers, entity, entity.queries[0],
            args.clips, scorer,
        )
        wrong = score_pile(
            analyzer, downloader, providers, entity, wrong_query,
            args.clips, scorer,
        )
        rows.append({
            "food": name,
            "own_query": entity.queries[0],
            "wrong_query": wrong_query,
            "own_scores": [round(s, 3) for s in right],
            "wrong_scores": [round(s, 3) for s in wrong],
            "own_median": round(statistics.median(right), 3) if right else None,
            "wrong_median": round(statistics.median(wrong), 3) if wrong else None,
        })
        log.info(
            "%s: own median %s (n=%d), wrong median %s (n=%d)",
            name,
            rows[-1]["own_median"], len(right),
            rows[-1]["wrong_median"], len(wrong),
        )

    own = [s for r in rows for s in r["own_scores"]]
    wrong = [s for r in rows for s in r["wrong_scores"]]
    sweep = []
    for cut in SWEEP:
        # identify: the score IS the share of frames naming the right food, so
        # it passes at score >= cut. dominance: the score is "the food owns the
        # frame" and passes at score >= 1 - cut.
        bar = cut if args.scorer == "identify" else 1.0 - cut
        keep = sum(1 for s in own if s >= bar)
        catch = sum(1 for s in wrong if s < bar)
        sweep.append({
            "cut": cut,
            "passes_at_score": round(bar, 2),
            "kept_of_own": f"{keep}/{len(own)}",
            "kept_pct": round(100.0 * keep / len(own), 1) if own else 0.0,
            "rejected_of_wrong": f"{catch}/{len(wrong)}",
            "rejected_pct": round(100.0 * catch / len(wrong), 1) if wrong else 0.0,
        })

    report = {"scorer": args.scorer, "model": args.model,
              "per_food": rows, "sweep": sweep,
              "own_clips": len(own), "wrong_clips": len(wrong)}
    target = Path(args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":                                 # pragma: no cover
    raise SystemExit(main())
