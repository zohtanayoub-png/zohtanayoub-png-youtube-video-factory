#!/usr/bin/env python3
"""Is the food right, in the right state, and is it the subject?

``reel_entity_check.py`` answered the first question and the reel stopped
narrating apples over oranges. What three renders then shipped is the second
and third:

    "la manzana con piel conserva la fibra"   over an apple **cake**
    "la manzana con piel conserva la fibra"   over a **peeled** apple
    "las fresas suelen aportar menos ..."     over a **dog**
    "el kiwi ..."                             over a **coconut**

Every one of those scores ``manzana = 1.00``. They are apples, and the
identification probe is answering its own question correctly.

So this measures the layer that is supposed to catch them, on real footage,
**before** another forty second render is spent finding out. Nine piles, each
a provider search chosen so that a human already knows the answer: five that
must be accepted and four that must be rejected. Every clip is scored twice -
by the entity probe alone, which is what shipped, and by the four-probe
conjunction, which is what is proposed - and the two numbers that matter are
reported for both:

* **false negatives** - good footage the probe throws away. Every one is a
  clip the repair pass has to replace, so this is a real cost and the reason
  a stricter gate is not automatically a better one.
* **false positives** - the cake, the dog and the coconut getting through.
  This is the whole point.

A change is worth having when the second falls and the first does not rise
to meet it. The pile labels are the *search intent*: a "peeled apple" search
returns the odd unpeeled apple, so each clip's provider id and score are
printed and a frame of it is saved beside the report, and the numbers should
be read with that in mind rather than as ground truth.

``raspberry`` is the second command and a separate question: the raspberry
probe measured 0.0 against 0.0 on the shipped prompts, and before that
number is tuned away it is worth knowing whether it is the wording, the
number of frames or the resolution that is wrong. It scores the same two
piles under every combination and prints the table.

Run either with the ``reel-grounding-check`` task on the video workflow.
"""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Sequence

from vidfactory.config import load_config
from vidfactory.downloader import ClipDownloader
from vidfactory.logging_utils import get_logger, setup_logging
from vidfactory.reels.foods import (
    BY_NAME,
    FOOD_IDENTIFY_PASS,
    identify_food,
    requirement_for_food,
    requirement_prompts,
    score_requirement,
)
from vidfactory.stock import build_providers
from vidfactory.visual_analysis import VisualAnalyzer, crop_center, sample_frames
from vidfactory.visual_model import load_model

log = get_logger("REELCHECK")


@dataclass(frozen=True)
class Pile:
    """One search whose answer is already known."""

    name: str
    food: str
    query: str
    accept: bool


#: The focused validation set the brief asks for, in its order.
PILES: tuple[Pile, ...] = (
    Pile("raw apple with skin", "manzana",
         "whole raw red apple with skin on a wooden table", True),
    Pile("peeled apple", "manzana",
         "peeled apple without skin on a plate", False),
    Pile("apple cake or pie", "manzana",
         "apple pie slice dessert on a plate", False),
    Pile("strawberries", "fresas",
         "fresh strawberries in a white bowl", True),
    Pile("strawberries with an animal", "fresas",
         "dog with strawberries", False),
    Pile("raspberries", "frambuesas",
         "fresh raspberries close up bowl", True),
    Pile("kiwi", "kiwi",
         "sliced kiwi fruit on a plate", True),
    Pile("kiwi in a tropical mix", "kiwi",
         "tropical fruit platter coconut pineapple", False),
    Pile("avocado", "aguacate",
         "halved avocado on a wooden board", True),
)

#: Cuts to sweep for the three new probes, together. With three frames the
#: only reachable shares are 0, 1/3, 2/3 and 1, so a finer sweep would be
#: measuring nothing.
SWEEP = (0.34, 0.5, 0.67, 1.0)

#: Raspberry wordings. The shipped one, one written around what a raspberry
#: has and a strawberry does not, and one written around the whole punnet
#: rather than the berry.
RASPBERRY_WORDINGS: dict[str, tuple[str, ...]] = {
    "shipped": (
        "fresh raspberries", "a bowl of raspberries", "raspberries close up",
    ),
    "texture": (
        "raspberries with a hollow centre",
        "bumpy red raspberry drupelets close up",
        "small soft matte red raspberries",
    ),
    "arrangement": (
        "a punnet of raspberries stacked in rows",
        "many small raspberries filling a bowl",
        "raspberries piled on a wooden table",
    ),
}


def search_clips(providers: Sequence[Any], query: str, limit: int) -> list[Any]:
    found: list[Any] = []
    for provider in providers:
        try:
            found.extend(provider.search(query, per_page=limit * 2, page=1))
        except Exception as exc:                           # pragma: no cover
            log.warning("search failed for %r: %s", query, exc)
    return found


def fetch(downloader: Any, clip: Any) -> Any | None:
    got = downloader.fetch_many([clip], needed=1)
    return got[0] if got else None


def frames_of(result: Any, count: int, edge: int, timeout: float = 30.0) -> list[Any]:
    """Decode ``count`` frames of a fetched clip at ``edge`` pixels square."""

    clip = result.clip
    stills = list(getattr(clip, "preview_images", None) or [])
    single = getattr(clip, "preview_image", "")
    if single and single not in stills:
        stills.append(single)
    return sample_frames(
        video=clip.local_path or result.path,
        stills=stills,
        duration=float(getattr(clip, "duration", 0.0) or 0.0),
        count=count,
        size=(edge, edge),
        timeout=timeout,
    )


def save_frame(result: Any, target: Path) -> None:
    """One JPEG of the clip, so the pile labels can be checked by eye."""

    source = result.clip.local_path or result.path
    target.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", "-y", "-ss", "1",
         "-i", str(source), "-frames:v", "1", "-vf", "scale=360:-2", str(target)],
        capture_output=True, check=False, timeout=60,
    )


def rates(rows: Sequence[dict[str, Any]], key: str) -> dict[str, Any]:
    """False positives and false negatives for one verdict column."""

    good = [r for r in rows if r["should_accept"]]
    bad = [r for r in rows if not r["should_accept"]]
    kept = sum(1 for r in good if r[key])
    leaked = sum(1 for r in bad if r[key])
    return {
        "accepted_of_good": f"{kept}/{len(good)}",
        "false_negative_rate": round(100.0 * (len(good) - kept) / len(good), 1)
        if good else 0.0,
        "accepted_of_bad": f"{leaked}/{len(bad)}",
        "false_positive_rate": round(100.0 * leaked / len(bad), 1) if bad else 0.0,
    }


def run_validation(args: argparse.Namespace, analyzer: Any, providers: Any,
                   downloader: Any) -> dict[str, Any]:
    edge = analyzer.decode_size[0]
    rows: list[dict[str, Any]] = []
    frame_dir = Path(args.out).parent / "frames"

    for pile in PILES:
        entity = BY_NAME[pile.food]
        requirement = requirement_for_food(entity)
        prompts, _ = requirement_prompts(requirement)
        taken = 0
        for clip in search_clips(providers, pile.query, args.clips):
            if taken >= args.clips:
                break
            result = fetch(downloader, clip)
            if result is None:
                continue
            frames = frames_of(result, args.frames, edge)
            if not frames:
                continue
            per_frame = analyzer.probe_frames(frames, prompts, use_claim_model=True)
            if not per_frame:
                continue
            full = score_requirement(requirement, per_frame)
            # "Before" is the entity probe on its own, exactly as it shipped.
            before = identify_food(entity, [row[:len(entity.positives)
                                                + len(entity.competitors)]
                                            for row in per_frame])
            taken += 1
            save_frame(result, frame_dir / f"{pile.food}-{taken:02d}-"
                                           f"{pile.name.replace(' ', '_')}.jpg")
            rows.append({
                "pile": pile.name,
                "food": pile.food,
                "source": result.clip.key,
                "should_accept": pile.accept,
                "entity_score": round(before.score, 3),
                "accepted_before": bool(before.passed),
                "state_score": round(full.state_match_score, 3)
                if full.state_checked else None,
                "context_score": round(full.context_match_score, 3)
                if full.context_checked else None,
                "dominant_subject_score": round(full.dominant_subject_score, 3),
                "distractor_dominance_score": round(full.distractor_dominance_score, 3),
                "final_score": round(full.score, 3),
                "accepted_after": bool(full.passed),
                "failed_on": list(full.failed_on),
                "looked_like": full.top_distractor,
            })
            log.info(
                "%s %s: entity %.2f -> %s | state %s context %s subject %.2f -> %s",
                pile.name, result.clip.key, before.score,
                "accept" if before.passed else "reject",
                f"{full.state_match_score:.2f}" if full.state_checked else "-",
                f"{full.context_match_score:.2f}" if full.context_checked else "-",
                full.dominant_subject_score,
                "accept" if full.passed else f"reject ({','.join(full.failed_on)})",
            )

    per_pile = []
    for pile in PILES:
        mine = [r for r in rows if r["pile"] == pile.name]
        if not mine:
            continue
        per_pile.append({
            "pile": pile.name,
            "query": pile.query,
            "should_accept": pile.accept,
            "clips": len(mine),
            "accepted_before": sum(1 for r in mine if r["accepted_before"]),
            "accepted_after": sum(1 for r in mine if r["accepted_after"]),
            "entity_median": round(
                statistics.median(r["entity_score"] for r in mine), 3),
            "state_median": _median(r["state_score"] for r in mine),
            "context_median": _median(r["context_score"] for r in mine),
            "subject_median": round(
                statistics.median(r["dominant_subject_score"] for r in mine), 3),
            "failed_on": _tally(r["failed_on"] for r in mine),
        })

    return {
        "command": "validation",
        "model": args.model,
        "frames_per_clip": args.frames,
        "entity_cut": FOOD_IDENTIFY_PASS,
        "clips": len(rows),
        "before": rates(rows, "accepted_before"),
        "after": rates(rows, "accepted_after"),
        "per_pile": per_pile,
        "per_clip": rows,
    }


def _median(values: Any) -> float | None:
    present = [v for v in values if v is not None]
    return round(statistics.median(present), 3) if present else None


def _tally(lists: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    for entry in lists:
        for reason in entry:
            counts[reason] = counts.get(reason, 0) + 1
    return counts


def run_raspberry(args: argparse.Namespace, analyzer: Any, providers: Any,
                  downloader: Any) -> dict[str, Any]:
    """Why does the raspberry probe measure 0.0 against 0.0?

    Four things could be wrong and only one of them is the threshold: the
    words, the number of frames, the resolution the frames were decoded at,
    or the model. This changes the first three, one at a time, on the same
    two piles - a raspberry search and the strawberry search that beats it -
    and reports what each is worth. Nothing here changes a cut.
    """

    base = BY_NAME["frambuesas"]
    edge = analyzer.decode_size[0]
    piles = {
        "raspberries": ("fresh raspberries close up bowl", True),
        "strawberries": ("fresh strawberries in a white bowl", False),
    }

    # Decode once at the largest size any variant needs, then derive the rest:
    # a download and a decode is the expensive part, and the crop variant is
    # only meaningful against frames that were never squashed to 224 first.
    cached: dict[str, list[tuple[str, list[Any], list[Any]]]] = {}
    for pile, (query, _accept) in piles.items():
        got: list[tuple[str, list[Any], list[Any]]] = []
        for clip in search_clips(providers, query, args.clips):
            if len(got) >= args.clips:
                break
            result = fetch(downloader, clip)
            if result is None:
                continue
            wide = frames_of(result, args.frames, edge * 2)
            many = frames_of(result, max(args.frames, 7), edge)
            if not wide:
                continue
            got.append((result.clip.key, wide, many))
        cached[pile] = got
        log.info("%s: %d clips", pile, len(got))

    variants: list[dict[str, Any]] = []
    for wording, positives in RASPBERRY_WORDINGS.items():
        entity = replace(base, positives=tuple(positives))
        prompts = [*entity.positives, *entity.competitors]
        for shape in ("frames-3", "frames-7", "crop-0.5"):
            scores: dict[str, list[float]] = {}
            for pile, clips in cached.items():
                pile_scores: list[float] = []
                for _key, wide, many in clips:
                    if shape == "frames-7":
                        frames = many
                    elif shape == "crop-0.5":
                        frames = [crop_center(f, 0.5, (edge, edge)) for f in wide]
                    else:
                        # Exactly what the pipeline decodes today.
                        frames = many[:args.frames]
                    per_frame = analyzer.probe_frames(
                        frames, prompts, use_claim_model=True
                    )
                    if per_frame:
                        pile_scores.append(identify_food(entity, per_frame).score)
                scores[pile] = pile_scores
            own = scores.get("raspberries", [])
            wrong = scores.get("strawberries", [])
            variants.append({
                "wording": wording,
                "shape": shape,
                "own_scores": [round(s, 3) for s in own],
                "wrong_scores": [round(s, 3) for s in wrong],
                "own_median": round(statistics.median(own), 3) if own else None,
                "wrong_median": round(statistics.median(wrong), 3) if wrong else None,
                "kept_of_own": f"{sum(1 for s in own if s >= FOOD_IDENTIFY_PASS)}"
                               f"/{len(own)}",
                "rejected_of_wrong":
                    f"{sum(1 for s in wrong if s < FOOD_IDENTIFY_PASS)}/{len(wrong)}",
            })
            log.info(
                "%s / %s: own median %s, wrong median %s",
                wording, shape, variants[-1]["own_median"],
                variants[-1]["wrong_median"],
            )

    return {
        "command": "raspberry",
        "model": args.model,
        "cut": FOOD_IDENTIFY_PASS,
        "competitors": list(base.competitors),
        "variants": variants,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["validation", "raspberry"],
                        default="validation", nargs="?")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--clips", type=int, default=6,
                        help="clips per pile (each is a download and a decode)")
    parser.add_argument("--frames", type=int, default=3)
    parser.add_argument("--out", default="output/reel-grounding-check.json")
    parser.add_argument("--model", default="claim", choices=["rank", "claim"],
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
        print("no visual model; nothing to measure")
        return 2
    # The same model in both slots: the frames are decoded at its input size
    # and the probes are asked of it by name.
    analyzer = VisualAnalyzer(
        model=model, claim_model=model,
        frames_per_clip=args.frames, allow_remote_video=False,
    )
    downloader = ClipDownloader(
        workdir=Path("work/reelcheck"), min_width=1280, min_height=720,
        min_seconds=2.0, max_mb=90, timeout=120, retries=2,
    )

    if args.command == "raspberry":
        report = run_raspberry(args, analyzer, providers, downloader)
    else:
        report = run_validation(args, analyzer, providers, downloader)

    target = Path(args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":                                 # pragma: no cover
    raise SystemExit(main())
