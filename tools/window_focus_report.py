#!/usr/bin/env python3
"""Which focus measure separates readable food footage from blurred food footage.

Reads two files and decides nothing on its own:

``data/calibration/window_focus_metrics.json``   the numbers, from run 34342326028
``data/calibration/window_readability_labels.json``  the labels, made by looking

The rule this exists to enforce is the brief's: ``pexels:37239365`` is the clip
that motivated the gate, so it may be *validated* against but must never help
choose the threshold. Every threshold below is the geometric midpoint of the
gap between the watchable windows and the unwatchable ones **with that clip
excluded**, and the held-out column then reports whether it happens to reject
it anyway. A metric that only rejects it because it was fitted to it has
proved nothing.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Sequence

METRICS = Path("data/calibration/window_focus_metrics.json")
LABELS = Path("data/calibration/window_readability_labels.json")

#: Every candidate, at both decode sizes. 224 is what production sees today.
CANDIDATES: tuple[str, ...] = (
    "edge_density", "strong_edge_fraction", "p999_gradient",
    "laplacian_variance", "normalised_laplacian", "normalised_p99",
)
SIZES: tuple[str, ...] = ("224", "480x270")


def load() -> tuple[list[dict[str, Any]], dict[str, str]]:
    rows = json.loads(METRICS.read_text(encoding="utf-8"))["per_window"]
    labels = {
        row["window_id"]: row["label"]
        for row in json.loads(LABELS.read_text(encoding="utf-8"))["labels"]
    }
    return rows, labels


def separation(rows: Sequence[dict[str, Any]], metric: str) -> dict[str, Any]:
    """Whether one metric puts every watchable window above every blurred one."""

    watchable = [r for r in rows if r.get("label") == "WATCHABLE"]
    unwatchable = [r for r in rows if r.get("label") == "UNWATCHABLE"]
    free = [r for r in unwatchable if not r.get("held_out")]
    held = [r for r in unwatchable if r.get("held_out")]
    borderline = [r for r in rows if r.get("label") == "BORDERLINE"]
    if not watchable or not free or metric not in watchable[0]:
        return {"metric": metric, "separates": False, "why": "not enough labels"}

    low, high = max(r[metric] for r in free), min(r[metric] for r in watchable)
    result: dict[str, Any] = {
        "metric": metric,
        "watchable_min": high,
        "watchable_max": max(r[metric] for r in watchable),
        "unwatchable_free_max": low,
        "held_out": sorted(r[metric] for r in held),
        "borderline": sorted(r[metric] for r in borderline),
        "separates": low < high,
    }
    if not result["separates"]:
        return result
    # Geometric rather than arithmetic: these are ratio-scaled quantities
    # spanning four orders of magnitude, and the midpoint of 4.8 and 39.5 is
    # not 22.
    threshold = math.sqrt(max(low, 1e-6) * high)
    result.update({
        "gap_ratio": round(high / max(low, 1e-9), 2),
        "threshold": round(threshold, 4),
        "held_out_rejected": f"{sum(1 for v in result['held_out'] if v < threshold)}"
                             f"/{len(held)}",
        "watchable_rejected": sum(1 for r in watchable if r[metric] < threshold),
        "of_all_rejected": f"{sum(1 for r in rows if r[metric] < threshold)}/{len(rows)}",
    })
    grounded = [r for r in rows if r.get("segment_grounding_passed")]
    lost = [r for r in grounded if r[metric] < threshold]
    result["grounded_rejected"] = f"{len(lost)}/{len(grounded)}"
    result["grounded_rejected_ids"] = [r["window_id"] for r in lost]
    return result


def main() -> int:
    rows, labels = load()
    for row in rows:
        row["label"] = labels.get(row["window_id"], "")

    report = {
        "windows": len(rows),
        "labelled": sum(1 for r in rows if r["label"]),
        "note": (
            "Thresholds are chosen from the labelled windows with "
            "pexels:37239365 excluded; the held_out column is validation, not "
            "evidence for the choice."
        ),
        "candidates": [
            separation(rows, f"{name}@{size}")
            for name in CANDIDATES for size in SIZES
        ],
    }
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":                                 # pragma: no cover
    raise SystemExit(main())
