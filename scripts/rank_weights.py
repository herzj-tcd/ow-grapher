#!/usr/bin/env python3
"""
Estimates relative match-count weights per competitive rank by solving the
weighted-average constraint:

    P_all[hero] ≈ Σ_rank( P_rank[hero] × w_rank )   where Σ w = 1

The system is overdetermined (~40 heroes, 7 unknowns) and solved via NNLS.

Output: data/rank_weights.json

Usage:
    python3 rank_weights.py
    python3 rank_weights.py --data data/comp_mnk.json --out data/rank_weights.json
"""

import argparse
import json
import warnings
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from scipy.optimize import nnls

_ROOT = Path(__file__).parent.parent

RANK_ORDER = ["bronze", "silver", "gold", "platinum", "diamond", "master", "grandmaster"]
REGIONS    = ["americas", "asia", "europe"]
DATASETS   = ["comp_mnk", "comp_controller"]


def solve_weights(rows: list[dict], region: str) -> dict[str, float] | None:
    """
    Returns normalised rank weights for one region, or None if data is missing.
    Rows must include both 'all' and per-rank tiers.
    """
    heroes = sorted({r["hero"] for r in rows if r["tier"] == "all" and r["region"] == region})
    if not heroes:
        return None

    def pick(hero: str, tier: str) -> float | None:
        for r in rows:
            if r["hero"] == hero and r["tier"] == tier and r["region"] == region:
                return r["pick_rate"]
        return None

    P_all  = np.array([pick(h, "all") for h in heroes], dtype=float)
    P_rank = np.column_stack([
        [pick(h, rank) for h in heroes]
        for rank in RANK_ORDER
    ]).astype(float)

    # Drop heroes missing any value
    mask = ~(np.isnan(P_all) | np.isnan(P_rank).any(axis=1))
    if mask.sum() < len(RANK_ORDER):
        warnings.warn(f"Too few complete heroes for region={region!r} ({mask.sum()} usable)")
        return None

    A, b = P_rank[mask], P_all[mask]

    # Normalise columns so NNLS isn't biased by scale differences
    col_norms = np.linalg.norm(A, axis=0)
    col_norms[col_norms == 0] = 1.0
    w, _ = nnls(A / col_norms, b)
    w = w / col_norms            # undo column normalisation
    total = w.sum()
    if total == 0:
        return None
    w /= total

    return {rank: round(float(w[i]), 6) for i, rank in enumerate(RANK_ORDER)}


def combined_weights(per_region: dict[str, dict[str, float]]) -> dict[str, float]:
    """Simple average across regions (equal region weighting)."""
    totals: dict[str, float] = {r: 0.0 for r in RANK_ORDER}
    n = 0
    for region_w in per_region.values():
        for rank, w in region_w.items():
            totals[rank] += w
        n += 1
    if n == 0:
        return {}
    return {rank: round(totals[rank] / n, 6) for rank in RANK_ORDER}


def process_dataset(data_path: Path) -> dict:
    rows = json.loads(data_path.read_text())["rows"]
    result: dict[str, dict] = {}
    for region in REGIONS:
        w = solve_weights(rows, region)
        if w is not None:
            result[region] = w
    if result:
        result["combined"] = combined_weights(result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Estimate competitive rank match-count weights")
    parser.add_argument("--out", default=str(_ROOT / "data" / "rank_weights.json"),
                        help="Output path (default: data/rank_weights.json)")
    args = parser.parse_args()

    output: dict = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "method": "nnls_weighted_average",
        "note": (
            "Relative match-count weights per rank derived from the constraint that "
            "the 'all' tier pick rates equal a weighted average of per-rank pick rates. "
            "Solved via non-negative least squares across all heroes. "
            "Values within each region sum to 1.0."
        ),
        "rank_order": RANK_ORDER,
        "weights": {},
    }

    for dataset in DATASETS:
        data_path = _ROOT / "data" / f"{dataset}.json"
        if not data_path.exists():
            print(f"Skipping {dataset}: {data_path} not found")
            continue
        print(f"Processing {dataset}...")
        result = process_dataset(data_path)
        output["weights"][dataset] = result
        for region, w in result.items():
            vals = "  ".join(f"{r}: {v:.3f}" for r, v in w.items())
            print(f"  {region:<10} {vals}")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
