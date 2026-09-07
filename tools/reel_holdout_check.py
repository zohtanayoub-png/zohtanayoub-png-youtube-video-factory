#!/usr/bin/env python3
"""Held-out measurement. Nothing here scores a change on the clips that shaped it.

The four-probe conjunction cut false positives from 66.7% to 20.8% and pushed
false negatives from 26.7% to 50.0%, and both halves of that came off the same
fifty-four clips. Those clips have now done their job: they are what the
prompts were written against, so a prompt rewritten in the light of them
cannot be graded on them without the grade meaning nothing.

``data/calibration/reel_grounding_dev_clips.json`` freezes the fifty-four
provider ids and the nine queries that produced them. Every pile this tool
builds excludes both - a different query, and an explicit id filter under it -
so a number printed here is a number about footage the prompts have never
seen.

Four questions, four commands, and they are deliberately separate runs:

``berries``    does the raspberry wording+crop candidate survive fresh
               footage, against strawberry, blackberry and blueberry? A
               confusion matrix, because "kept 5 of 8" hides which berry the
               other three turned into.
``avocado``    which avocado states a generic ``aguacate`` beat should accept,
               decided on its own calibration piles - whole, halved, sliced,
               toast, guacamole, smoothie, unrelated green - and never on the
               clips that exposed the smoothie problem.
``apple``      can any backend answer "is this apple raw, and is its skin
               visible" at all? Backends and prompt formulations together,
               with load time, per-frame runtime and peak memory beside the
               accuracy, because a verifier that cannot run on a free runner
               is not a candidate.
``holdout``    the whole gate on fresh piles: precision and recall, overall
               and per food and per state.

Run them with the ``reel-holdout-check`` task on the video workflow.
"""

from __future__ import annotations

import argparse
import json
import resource
import time
from dataclasses import dataclass
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

log = get_logger("HOLDOUT")

FROZEN = Path("data/calibration/reel_grounding_dev_clips.json")


def frozen() -> tuple[set[str], set[str]]:
    """(clip ids, queries) that development already spent."""

    if not FROZEN.exists():                                # pragma: no cover
        log.warning("no frozen development set at %s", FROZEN)
        return set(), set()
    data = json.loads(FROZEN.read_text(encoding="utf-8"))
    return set(data.get("clips") or []), {
        q.strip().lower() for q in data.get("burned_queries") or []
    }


@dataclass(frozen=True)
class Pile:
    """One search whose answer a human already knows, on unseen footage."""

    name: str
    query: str
    #: What the pile is *of*, for a confusion matrix.
    truth: str = ""
    #: Whether a beat requiring ``food`` should accept it.
    accept: bool = True
    food: str = ""
    page: int = 1


# ---------------------------------------------------------------------------
# The piles. Every query differs from the nine the development set spent.
# ---------------------------------------------------------------------------

BERRY_PILES: tuple[Pile, ...] = (
    Pile("raspberries", "ripe raspberries harvest closeup macro", "frambuesas"),
    Pile("strawberries", "strawberries on a rustic wooden board", "fresas"),
    Pile("blackberries", "fresh blackberries in a ceramic bowl", "moras"),
    Pile("blueberries", "fresh blueberries in a wooden spoon", "arandanos"),
)

#: Label groups for the berry confusion matrix. Local to the measurement -
#: blackberries and blueberries are not foods a reel narrates, they are what a
#: raspberry gets confused with, and the registry is not the place for that.
BERRY_LABELS: dict[str, tuple[str, ...]] = {
    "frambuesas": ("fresh raspberries", "a bowl of raspberries", "raspberries close up"),
    "fresas": ("fresh strawberries", "a bowl of red strawberries",
               "whole strawberries close up"),
    "moras": ("fresh blackberries", "a bowl of blackberries", "blackberries close up"),
    "arandanos": ("fresh blueberries", "a bowl of blueberries", "blueberries close up"),
}

#: The candidate wording the development run pointed at, stated once.
BERRY_CANDIDATE: dict[str, tuple[str, ...]] = {
    "frambuesas": ("a punnet of raspberries stacked in rows",
                   "many small raspberries filling a bowl",
                   "raspberries piled on a wooden table"),
    "fresas": ("a punnet of strawberries stacked in rows",
               "many red strawberries filling a bowl",
               "strawberries piled on a wooden table"),
    "moras": ("a punnet of blackberries stacked in rows",
              "many dark blackberries filling a bowl",
              "blackberries piled on a wooden table"),
    "arandanos": ("a punnet of blueberries stacked in rows",
                  "many small blueberries filling a bowl",
                  "blueberries piled on a wooden table"),
}

AVOCADO_PILES: tuple[Pile, ...] = (
    Pile("whole avocado", "whole avocados in a basket", "whole", True, "aguacate"),
    Pile("halved avocado", "avocado cut open showing the pit", "halved", True, "aguacate"),
    Pile("sliced avocado", "avocado slices fanned on a plate", "sliced", True, "aguacate"),
    Pile("avocado toast", "avocado toast breakfast plate", "toast", True, "aguacate"),
    Pile("guacamole", "bowl of guacamole with tortilla chips", "guacamole", False, "aguacate"),
    Pile("avocado smoothie", "green avocado smoothie in a tall glass", "smoothie", False, "aguacate"),
    Pile("unrelated green", "fresh green peas and broccoli on a table", "other", False, "aguacate"),
)

APPLE_PILES: tuple[Pile, ...] = (
    Pile("raw apple with skin", "red apples on a branch in an orchard", "raw", True, "manzana"),
    Pile("peeled apple", "peeling an apple with a knife", "peeled", False, "manzana"),
    Pile("apple dessert", "homemade apple crumble in a baking dish", "dessert", False, "manzana"),
    Pile("apple juice", "pouring apple juice into a glass", "juice", False, "manzana"),
)

#: The held-out set. Every query here is new again: the calibration run
#: above spent its own, and a pile that decided a rule cannot also grade it.
HOLDOUT_PILES: tuple[Pile, ...] = (
    Pile("raw apple with skin", "shiny apples in a wooden crate at a market", "raw", True, "manzana"),
    Pile("peeled apple", "hand peeling apple skin into a spiral", "peeled", False, "manzana"),
    Pile("apple dessert", "apple tart with cream on a plate", "dessert", False, "manzana"),
    Pile("strawberries", "strawberries in a punnet at a farm stall", "raw", True, "fresas"),
    Pile("strawberry dessert", "strawberry ice cream in a cone", "processed", False, "fresas"),
    Pile("raspberries", "raspberries on a branch in a garden", "raw", True, "frambuesas"),
    Pile("kiwi", "kiwi fruit sliced on a wooden chopping board", "raw", True, "kiwi"),
    Pile("kiwi in a mixed platter", "fruit salad bowl with pineapple and melon", "mixed", False, "kiwi"),
    # The avocado states the calibration decided, on footage it never saw.
    Pile("whole avocado", "avocados piled at a grocery market", "whole", True, "aguacate"),
    Pile("halved avocado", "avocado halves with lime on a board", "halved", True, "aguacate"),
    Pile("sliced avocado", "avocado slices arranged on a salad", "sliced", True, "aguacate"),
    Pile("avocado toast", "toast with sliced avocado on top", "toast", True, "aguacate"),
    Pile("guacamole", "guacamole dip in a molcajete bowl", "guacamole", False, "aguacate"),
    Pile("avocado smoothie", "green avocado milkshake in a glass", "smoothie", False, "aguacate"),
    Pile("food with an animal", "dog begging next to a plate of food", "animal", False, "fresas"),
)


#: Which piles each command searches. Named once so the freeze check and the
#: runner cannot disagree about what a command is about to spend.
PILES_FOR: dict[str, tuple[Pile, ...]] = {
    "berries": BERRY_PILES,
    "avocado": AVOCADO_PILES,
    "apple": APPLE_PILES,
    "holdout": HOLDOUT_PILES,
}


def spent_piles(command: str, burned: set[str]) -> list[Pile]:
    """The piles this command would search that are already used up.

    A pile is spent the moment its numbers decide something or grade
    something: re-running it measures the pile rather than the probe, which
    is the whole failure this file exists to prevent. Checked for the command
    about to run and not for every command there is, because a calibration
    pile is *supposed* to be in the burned list once it has been spent.
    """

    return [p for p in PILES_FOR.get(command, ())
            if p.query.strip().lower() in burned]



# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------

def collect(providers: Sequence[Any], downloader: Any, pile: Pile, limit: int,
            excluded: set[str], edge: int, frames: int,
            wide: bool = False) -> list[tuple[Any, list[Any], list[Any]]]:
    """Download and decode ``limit`` unseen clips for one pile.

    Returns (clip, frames at the model's input, frames at twice it). The
    second set is what a centre crop is worth measuring on: cropping a frame
    that was already squashed to 224 recovers nothing.
    """

    found: list[Any] = []
    for provider in providers:
        try:
            found.extend(provider.search(pile.query, per_page=limit * 3, page=pile.page))
        except Exception as exc:                           # pragma: no cover
            log.warning("search failed for %r: %s", pile.query, exc)
    taken: list[tuple[Any, list[Any], list[Any]]] = []
    skipped = 0
    for clip in found:
        if len(taken) >= limit:
            break
        if clip.key in excluded:
            skipped += 1
            continue
        got = downloader.fetch_many([clip], needed=1)
        if not got:
            continue
        result = got[0]
        stills = list(getattr(result.clip, "preview_images", None) or [])
        single = getattr(result.clip, "preview_image", "")
        if single and single not in stills:
            stills.append(single)
        source = result.clip.local_path or result.path
        duration = float(getattr(result.clip, "duration", 0.0) or 0.0)
        normal = sample_frames(video=source, stills=stills, duration=duration,
                               count=frames, size=(edge, edge))
        if not normal:
            continue
        big = sample_frames(video=source, stills=stills, duration=duration,
                            count=frames, size=(edge * 2, edge * 2)) if wide else []
        taken.append((result.clip, normal, big))
    if skipped:
        log.info("%s: skipped %d development clip(s)", pile.name, skipped)
    log.info("%s: %d fresh clips for %r", pile.name, len(taken), pile.query)
    return taken


def argmax_label(analyzer: Any, frames: Sequence[Any],
                 labels: dict[str, tuple[str, ...]]) -> tuple[str, dict[str, float]]:
    """Which label group wins the most frames? A confusion matrix needs no cut."""

    names = list(labels)
    prompts = [p for name in names for p in labels[name]]
    spans: list[tuple[int, int]] = []
    at = 0
    for name in names:
        spans.append((at, at + len(labels[name])))
        at += len(labels[name])
    rows = analyzer.probe_frames(frames, prompts, use_claim_model=True)
    if not rows:
        return "", {}
    votes = {name: 0 for name in names}
    for row in rows:
        best = max(range(len(names)), key=lambda i: max(row[spans[i][0]:spans[i][1]]))
        votes[names[best]] += 1
    total = sum(votes.values()) or 1
    return max(votes, key=lambda n: votes[n]), {n: v / total for n, v in votes.items()}


def matrix(rows: Sequence[dict[str, Any]], labels: Sequence[str]) -> dict[str, Any]:
    """truth -> predicted counts, plus precision and recall per label."""

    table = {t: {p: 0 for p in labels} for t in labels}
    for row in rows:
        if row["truth"] in table and row["predicted"] in table[row["truth"]]:
            table[row["truth"]][row["predicted"]] += 1
    scores = {}
    for label in labels:
        tp = table[label][label]
        predicted = sum(table[t][label] for t in labels)
        actual = sum(table[label].values())
        scores[label] = {
            "precision": round(tp / predicted, 3) if predicted else None,
            "recall": round(tp / actual, 3) if actual else None,
            "support": actual,
        }
    return {"matrix": table, "per_label": scores}


# ---------------------------------------------------------------------------
# berries
# ---------------------------------------------------------------------------

def run_berries(args, analyzer, providers, downloader, excluded) -> dict[str, Any]:
    edge = analyzer.decode_size[0]
    piles = {p.name: collect(providers, downloader, p, args.clips, excluded,
                             edge, 3, wide=True) for p in BERRY_PILES}

    variants = {
        "shipped (3 frames, no crop)": (BERRY_LABELS, False),
        "shipped + centre crop": (BERRY_LABELS, True),
        "arrangement (3 frames, no crop)": (BERRY_CANDIDATE, False),
        "arrangement + centre crop": (BERRY_CANDIDATE, True),
    }
    report: dict[str, Any] = {"command": "berries", "clips_per_pile": args.clips,
                              "variants": {}}
    for title, (labels, crop) in variants.items():
        rows: list[dict[str, Any]] = []
        for pile in BERRY_PILES:
            for clip, normal, big in piles[pile.name]:
                frames = ([crop_center(f, 0.5, (edge, edge)) for f in big]
                          if crop and big else normal)
                predicted, share = argmax_label(analyzer, frames, labels)
                if not predicted:
                    continue
                rows.append({"pile": pile.name, "source": clip.key,
                             "truth": pile.truth, "predicted": predicted,
                             "share": {k: round(v, 2) for k, v in share.items()}})
        confusion = matrix(rows, list(labels))
        correct = sum(1 for r in rows if r["truth"] == r["predicted"])
        report["variants"][title] = {
            **confusion,
            "accuracy": round(correct / len(rows), 3) if rows else None,
            "clips": len(rows),
            "per_clip": rows,
        }
        log.info("%s: accuracy %s over %d clips", title,
                 report["variants"][title]["accuracy"], len(rows))

    # And the production question, which is not the same as the matrix: does
    # a frambuesas beat accept raspberry footage and reject the rest?
    entity = BY_NAME["frambuesas"]
    prompts = [*entity.positives, *entity.competitors]
    gate: dict[str, Any] = {}
    for pile in BERRY_PILES:
        kept = 0
        counted = 0
        for _clip, normal, _big in piles[pile.name]:
            per_frame = analyzer.probe_frames(normal, prompts, use_claim_model=True)
            if not per_frame:
                continue
            counted += 1
            kept += bool(identify_food(entity, per_frame).passed)
        gate[pile.name] = f"{kept}/{counted}"
    report["frambuesas_gate_shipped"] = gate
    log.info("frambuesas gate, shipped prompts: %s", gate)
    return report


# ---------------------------------------------------------------------------
# avocado
# ---------------------------------------------------------------------------

#: The candidate rules. The shipped one is first so the table reads as a
#: before/after, and every candidate is written from the *question* rather
#: than from the clips that embarrassed the last one: a beat that says
#: "aguacate" wants the fruit visible, in any cut, and does not want a drink.
AVOCADO_RULES: dict[str, dict[str, tuple[str, ...]]] = {
    "shipped": {
        "required": ("a fresh raw avocado",
                     "an avocado cut in half showing the stone",
                     "sliced green avocado flesh"),
        "forbidden": ("a tub of packaged guacamole dip", "an avocado smoothie"),
    },
    "fruit-is-visible": {
        "required": ("a whole avocado with dark green skin",
                     "an avocado cut in half showing the stone",
                     "slices of green avocado flesh",
                     "avocado on toast with visible slices"),
        "forbidden": ("a green drink in a glass",
                      "a smooth green dip with no visible fruit",
                      "a bowl of mashed green paste"),
    },
    "fruit-is-visible-strict": {
        "required": ("a whole avocado with dark green skin",
                     "an avocado cut in half showing the stone",
                     "slices of green avocado flesh"),
        "forbidden": ("a green drink in a glass",
                      "a smooth green dip with no visible fruit",
                      "a bowl of mashed green paste",
                      "green vegetables that are not avocado"),
    },
}


def run_avocado(args, analyzer, providers, downloader, excluded) -> dict[str, Any]:
    edge = analyzer.decode_size[0]
    piles = {p.name: collect(providers, downloader, p, args.clips, excluded, edge, 3)
             for p in AVOCADO_PILES}
    report: dict[str, Any] = {"command": "avocado", "rules": {}}

    for name, rule in AVOCADO_RULES.items():
        prompts = [*rule["required"], *rule["forbidden"]]
        positives = len(rule["required"])
        per_pile: dict[str, Any] = {}
        for pile in AVOCADO_PILES:
            accepted = counted = 0
            losers: dict[str, int] = {}
            for _clip, frames, _big in piles[pile.name]:
                rows = analyzer.probe_frames(frames, prompts, use_claim_model=True)
                if not rows:
                    continue
                counted += 1
                wins = 0
                for row in rows:
                    best = max(range(len(prompts)), key=lambda i: row[i])
                    if best < positives:
                        wins += 1
                    else:
                        loser = prompts[best]
                        losers[loser] = losers.get(loser, 0) + 1
                if wins / len(rows) >= 0.5:
                    accepted += 1
            per_pile[pile.name] = {
                "state": pile.truth,
                "should_accept": pile.accept,
                "accepted": f"{accepted}/{counted}",
                "accepted_pct": round(100.0 * accepted / counted, 1) if counted else None,
                "top_forbidden": max(losers, key=lambda k: losers[k]) if losers else "",
            }
        good = [p for p in AVOCADO_PILES if p.accept]
        bad = [p for p in AVOCADO_PILES if not p.accept]

        def total(piles_: Sequence[Pile], key: int) -> int:
            return sum(int(per_pile[p.name]["accepted"].split("/")[key]) for p in piles_)

        report["rules"][name] = {
            "required": list(rule["required"]),
            "forbidden": list(rule["forbidden"]),
            "per_pile": per_pile,
            "accepted_of_valid": f"{total(good, 0)}/{total(good, 1)}",
            "accepted_of_invalid": f"{total(bad, 0)}/{total(bad, 1)}",
        }
        log.info("avocado %s: valid %s, invalid %s", name,
                 report["rules"][name]["accepted_of_valid"],
                 report["rules"][name]["accepted_of_invalid"])
    return report


# ---------------------------------------------------------------------------
# apple - backends and formulations together
# ---------------------------------------------------------------------------

#: Every backend worth trying on a free runner, with why it is a candidate.
#: ``licence`` is the model's, and it is a selection criterion rather than a
#: footnote: this is a commercial channel.
BACKENDS: tuple[dict[str, Any], ...] = (
    {
        "name": "clip-vit-large-patch14 (quantized, in production)",
        "repo": "Xenova/clip-vit-large-patch14",
        "vision_file": "onnx/vision_model_quantized.onnx",
        "text_file": "onnx/text_model_quantized.onnx",
        "image_size": 224,
        "licence": "MIT (OpenAI CLIP weights, MIT)",
    },
    {
        "name": "clip-vit-large-patch14 (full precision)",
        "repo": "Xenova/clip-vit-large-patch14",
        "vision_file": "onnx/vision_model.onnx",
        "text_file": "onnx/text_model.onnx",
        "image_size": 224,
        "licence": "MIT (OpenAI CLIP weights, MIT)",
    },
    {
        "name": "siglip-base-patch16-224",
        "repo": "Xenova/siglip-base-patch16-224",
        "vision_file": "onnx/vision_model_quantized.onnx",
        "text_file": "onnx/text_model_quantized.onnx",
        "image_size": 224,
        "licence": "Apache-2.0",
    },
)

#: Three ways of asking the same question, because the formulation may be the
#: whole problem. The shipped one asks about *absence*, which is what a
#: contrastive model is worst at; the others put a positive on both sides.
APPLE_FORMULATIONS: dict[str, dict[str, tuple[str, ...]]] = {
    "absence (shipped)": {
        "required": ("a fresh raw apple with its skin on", "a whole unpeeled apple",
                     "raw apple slices with the red skin still on"),
        "forbidden": ("a peeled apple with no skin", "a slice of apple cake",
                      "apple pie", "a glass of apple juice",
                      "cooked apple or apple sauce",
                      "a processed apple dessert with cream"),
    },
    "positive-vs-positive": {
        "required": ("a red apple with shiny red skin",
                     "a green apple with smooth green skin",
                     "an apple whose red skin covers it"),
        "forbidden": ("a pale yellow apple with the skin cut away",
                      "white apple flesh with no colour on the outside",
                      "a brown baked apple dessert",
                      "a glass of cloudy apple juice"),
    },
    "colour-and-surface": {
        "required": ("apples with glossy red and green surfaces",
                     "apples on a tree with their skin on"),
        "forbidden": ("pale wet apple flesh being cut",
                      "apple pieces in pastry and syrup",
                      "an apple drink in a glass"),
    },
}


def peak_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def run_apple(args, _analyzer, providers, downloader, excluded, config) -> dict[str, Any]:
    """Which backend, if any, can see an apple's skin - and what does it cost?

    The frames are decoded once at the largest input any candidate wants and
    re-used, so what is timed is the model rather than FFmpeg.
    """

    biggest = max(int(b["image_size"]) for b in BACKENDS)
    piles = {p.name: collect(providers, downloader, p, args.clips, excluded,
                             biggest, 3) for p in APPLE_PILES}

    report: dict[str, Any] = {"command": "apple", "backends": []}
    for spec in BACKENDS:
        entry = {k: v for k, v in spec.items() if k != "name"}
        entry["name"] = spec["name"]
        before = peak_mb()
        started = time.time()
        try:
            settings = {"enabled": True, "repo": spec["repo"],
                        "vision_file": spec["vision_file"],
                        "text_file": spec["text_file"],
                        "tokenizer_file": "tokenizer.json",
                        "image_size": spec["image_size"], "fallback": False,
                        "threads": int(config.get("visual.claim_model.threads", 2))}
            model = load_model(settings)
        except Exception as exc:                           # pragma: no cover
            model = None
            entry["error"] = str(exc)[:300]
        entry["load_seconds"] = round(time.time() - started, 1)
        if model is None:
            entry["loaded"] = False
            entry.setdefault("error", "load_model returned None")
            report["backends"].append(entry)
            log.warning("%s did not load: %s", spec["name"], entry["error"])
            continue

        entry["loaded"] = True
        probe = VisualAnalyzer(model=model, claim_model=model, frames_per_clip=3,
                               allow_remote_video=False)
        edge = probe.decode_size[0]
        entry["image_size"] = edge
        formulations: dict[str, Any] = {}
        frame_count = 0
        spent = 0.0
        for title, rule in APPLE_FORMULATIONS.items():
            prompts = [*rule["required"], *rule["forbidden"]]
            positives = len(rule["required"])
            per_pile: dict[str, str] = {}
            correct = total = 0
            for pile in APPLE_PILES:
                accepted = counted = 0
                for _clip, frames, _big in piles[pile.name]:
                    usable = [crop_center(f, 1.0, (edge, edge)) for f in frames]
                    started = time.time()
                    rows = probe.probe_frames(usable, prompts, use_claim_model=True)
                    spent += time.time() - started
                    frame_count += len(usable)
                    if not rows:
                        continue
                    counted += 1
                    wins = sum(
                        1 for row in rows
                        if max(range(len(prompts)), key=lambda i: row[i]) < positives
                    )
                    accepted += (wins / len(rows)) >= 0.5
                per_pile[pile.name] = f"{accepted}/{counted}"
                correct += accepted if pile.accept else counted - accepted
                total += counted
            formulations[title] = {
                "per_pile": per_pile,
                "accuracy": round(correct / total, 3) if total else None,
            }
            log.info("%s / %s: accuracy %s", spec["name"], title,
                     formulations[title]["accuracy"])
        entry["formulations"] = formulations
        entry["seconds_per_frame"] = round(spent / frame_count, 3) if frame_count else None
        entry["peak_rss_mb"] = round(peak_mb(), 1)
        entry["rss_added_mb"] = round(peak_mb() - before, 1)
        report["backends"].append(entry)
        del probe, model
    return report


# ---------------------------------------------------------------------------
# holdout - the whole gate, on unseen footage
# ---------------------------------------------------------------------------

def run_holdout(args, analyzer, providers, downloader, excluded) -> dict[str, Any]:
    edge = analyzer.decode_size[0]
    rows: list[dict[str, Any]] = []
    for pile in HOLDOUT_PILES:
        entity = BY_NAME[pile.food]
        requirement = requirement_for_food(entity)
        prompts, _ = requirement_prompts(requirement)
        for clip, frames, _big in collect(providers, downloader, pile, args.clips,
                                          excluded, edge, 3):
            per_frame = analyzer.probe_frames(frames, prompts, use_claim_model=True)
            if not per_frame:
                continue
            full = score_requirement(requirement, per_frame)
            entity_only = identify_food(
                entity,
                [row[:len(entity.positives) + len(entity.competitors)]
                 for row in per_frame],
            )
            rows.append({
                "pile": pile.name, "food": pile.food, "state": pile.truth,
                "source": clip.key, "should_accept": pile.accept,
                "accepted_before": bool(entity_only.passed),
                "accepted_after": bool(full.passed),
                "entity_score": round(full.entity_presence_score, 3),
                "state_score": round(full.state_match_score, 3) if full.state_checked else None,
                "context_score": round(full.context_match_score, 3) if full.context_checked else None,
                "dominant_subject_score": round(full.dominant_subject_score, 3),
                "failed_on": list(full.failed_on),
                "looked_like": full.top_distractor,
            })
            log.info("%s %s: before %s after %s%s", pile.name, clip.key,
                     "accept" if entity_only.passed else "reject",
                     "accept" if full.passed else "reject",
                     "" if full.passed else f" ({','.join(full.failed_on)})")

    def rates(key: str, subset: Sequence[dict[str, Any]]) -> dict[str, Any]:
        good = [r for r in subset if r["should_accept"]]
        bad = [r for r in subset if not r["should_accept"]]
        tp = sum(1 for r in good if r[key])
        fp = sum(1 for r in bad if r[key])
        fn = len(good) - tp
        return {
            "accepted_of_valid": f"{tp}/{len(good)}",
            "accepted_of_invalid": f"{fp}/{len(bad)}",
            "precision": round(tp / (tp + fp), 3) if (tp + fp) else None,
            "recall": round(tp / len(good), 3) if good else None,
            "false_negative_rate": round(100.0 * fn / len(good), 1) if good else None,
            "false_positive_rate": round(100.0 * fp / len(bad), 1) if bad else None,
        }

    by_food: dict[str, Any] = {}
    for food in sorted({r["food"] for r in rows}):
        subset = [r for r in rows if r["food"] == food]
        by_food[food] = {"before": rates("accepted_before", subset),
                         "after": rates("accepted_after", subset)}
    by_state: dict[str, Any] = {}
    for state in sorted({r["state"] for r in rows}):
        subset = [r for r in rows if r["state"] == state]
        by_state[state] = {
            "clips": len(subset),
            "should_accept": subset[0]["should_accept"],
            "accepted_before": sum(1 for r in subset if r["accepted_before"]),
            "accepted_after": sum(1 for r in subset if r["accepted_after"]),
        }
    return {
        "command": "holdout",
        "clips": len(rows),
        "before": rates("accepted_before", rows),
        "after": rates("accepted_after", rows),
        "per_food": by_food,
        "per_state": by_state,
        "per_clip": rows,
    }


# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command",
                        choices=["berries", "avocado", "apple", "holdout"])
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--clips", type=int, default=6)
    parser.add_argument("--out", default="")
    args = parser.parse_args(argv)
    setup_logging(verbose=False)

    config = load_config(args.config)
    providers = build_providers(dict(config.get("sources", {}) or {}))
    if not providers:
        print("no stock provider is available")
        return 2
    excluded, burned = frozen()
    log.info("excluding %d development clips and %d spent queries",
             len(excluded), len(burned))
    already = spent_piles(args.command, burned)
    if already:
        print("these piles have already been spent, on deciding a rule or on "
              "grading one, and cannot do either again:")
        for pile in already:
            print(f"  {pile.name}: {pile.query!r}")
        print("write new queries for this command before running it.")
        return 2

    downloader = ClipDownloader(
        workdir=Path("work/holdout"), min_width=1280, min_height=720,
        min_seconds=2.0, max_mb=90, timeout=120, retries=2,
    )

    if args.command == "apple":
        report = run_apple(args, None, providers, downloader, excluded, config)
    else:
        settings = dict(config.get("visual.claim_model", {}) or {})
        settings.setdefault("enabled", True)
        model = load_model(settings)
        if model is None:
            print("no claim model; nothing to measure")
            return 2
        analyzer = VisualAnalyzer(model=model, claim_model=model,
                                  frames_per_clip=3, allow_remote_video=False)
        runner = {"berries": run_berries, "avocado": run_avocado,
                  "holdout": run_holdout}[args.command]
        report = runner(args, analyzer, providers, downloader, excluded)

    report["held_out_from"] = {"clips": len(excluded), "queries": sorted(burned)}
    target = Path(args.out or f"output/holdout/{args.command}.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":                                 # pragma: no cover
    raise SystemExit(main())
