#!/usr/bin/env python3
"""
Map-specific hero performance report.

Generates an overview showing which heroes lead on each map and by how much.
Also calculates per-hero metrics on each map (optional with --per-map).

Metrics:
  - pick_rate_delta: map_rate - overall_rate
  - pick_rate_ratio: delta / overall_rate (percent change)
  - win_rate_delta: map_rate - overall_rate
  - win_rate_multiplier: delta / |overall_rate - 50%| (change relative to skew from neutral)

Usage:
    python3 map_hero_report.py                           # generate overview (CSV)
    python3 map_hero_report.py --per-map                 # also write per-map files
    python3 map_hero_report.py --region americas         # filter to one region
    python3 map_hero_report.py --format json             # output JSON instead of CSV
    python3 map_hero_report.py --format both             # output both CSV and JSON
    python3 map_hero_report.py --data comp_mnk           # different dataset
"""

import argparse
import json
import csv
from pathlib import Path
from collections import defaultdict

_ROOT = Path(__file__).parent.parent


def load_overall_stats(data_path: str) -> dict:
    """Load overall stats, aggregate across all regions and tiers.

    Returns dict: {hero_name: {"pick_rate": float, "win_rate": float}}
    """
    with open(data_path, encoding="utf-8") as f:
        data = json.load(f)

    hero_stats = defaultdict(lambda: {"pick_sum": 0, "win_sum": 0, "count": 0})

    for row in data["rows"]:
        hero = row["hero"]
        hero_stats[hero]["pick_sum"] += row["pick_rate"]
        hero_stats[hero]["win_sum"] += row["win_rate"]
        hero_stats[hero]["count"] += 1

    # Average across regions/tiers
    result = {}
    for hero, stats in hero_stats.items():
        result[hero] = {
            "pick_rate": stats["pick_sum"] / stats["count"],
            "win_rate": stats["win_sum"] / stats["count"],
        }
    return result


def load_map_stats(map_path: str) -> dict:
    """Load map-specific stats.

    Returns dict: {region: {hero_name: {"pick_rate": float, "win_rate": float}}}
    """
    with open(map_path, encoding="utf-8") as f:
        data = json.load(f)

    result = defaultdict(dict)
    for row in data["rows"]:
        hero = row["hero"]
        region = row["region"]
        result[region][hero] = {
            "pick_rate": row["pick_rate"],
            "win_rate": row["win_rate"],
        }
    return dict(result)


def calculate_metrics(map_stats: dict, overall_stats: dict, region: str) -> list:
    """Calculate deltas and relative metrics for a map/region.

    Returns list of dicts with hero metrics.
    """
    results = []

    for hero, map_hero_stats in map_stats.items():
        if hero not in overall_stats:
            continue

        overall = overall_stats[hero]
        map_val = map_hero_stats

        pick_delta = map_val["pick_rate"] - overall["pick_rate"]
        win_delta = map_val["win_rate"] - overall["win_rate"]

        # Pick rate ratio: how much did it change relative to baseline?
        pick_ratio = pick_delta / overall["pick_rate"] if overall["pick_rate"] > 0 else 0

        # Win rate divergence multiplier: how much did the skew from 50% change?
        overall_skew = overall["win_rate"] - 50.0
        win_multiplier = (
            win_delta / abs(overall_skew)
            if abs(overall_skew) > 0.1  # avoid divide-by-zero for near-50% heroes
            else 0
        )

        results.append({
            "hero": hero,
            "region": region,
            "pick_rate_map": round(map_val["pick_rate"], 2),
            "pick_rate_overall": round(overall["pick_rate"], 2),
            "pick_rate_delta": round(pick_delta, 2),
            "pick_rate_ratio": round(pick_ratio, 3),
            "win_rate_map": round(map_val["win_rate"], 2),
            "win_rate_overall": round(overall["win_rate"], 2),
            "win_rate_delta": round(win_delta, 2),
            "win_rate_multiplier": round(win_multiplier, 3),
        })

    return results


def generate_overview(overall_stats: str, maps_dir: str, region: str = None) -> list:
    """Generate overview of which heroes lead on each map.

    Returns list of dicts with map-level summary stats.
    """
    overall = load_overall_stats(overall_stats)
    maps_path = Path(maps_dir)
    map_files = sorted(maps_path.glob("*.json"))

    overview = []

    for map_file in map_files:
        map_name = map_file.stem
        map_stats = load_map_stats(map_file)

        # If region filter specified, only use that region
        if region:
            if region not in map_stats:
                continue
            regions_to_process = [region]
        else:
            regions_to_process = list(map_stats.keys())

        for r in regions_to_process:
            # Calculate metrics for all heroes on this map
            metrics = calculate_metrics(map_stats[r], overall, r)

            # Find top/bottom by different metrics
            by_wr_delta = sorted(metrics, key=lambda x: x["win_rate_delta"], reverse=True)
            by_wr_multiplier = sorted(metrics, key=lambda x: x["win_rate_multiplier"], reverse=True)
            by_pick_delta = sorted(metrics, key=lambda x: x["pick_rate_delta"], reverse=True)
            by_pick_ratio = sorted(metrics, key=lambda x: x["pick_rate_ratio"], reverse=True)

            overview.append({
                "map": map_name,
                "region": r,
                "best_wr_hero": by_wr_delta[0]["hero"],
                "best_wr_delta": by_wr_delta[0]["win_rate_delta"],
                "best_wr_map": by_wr_delta[0]["win_rate_map"],
                "best_wr_overall": by_wr_delta[0]["win_rate_overall"],
                "worst_wr_hero": by_wr_delta[-1]["hero"],
                "worst_wr_delta": by_wr_delta[-1]["win_rate_delta"],
                "worst_wr_map": by_wr_delta[-1]["win_rate_map"],
                "worst_wr_overall": by_wr_delta[-1]["win_rate_overall"],
                "best_wr_skew_hero": by_wr_multiplier[0]["hero"],
                "best_wr_skew_multiplier": by_wr_multiplier[0]["win_rate_multiplier"],
                "most_picked_hero": by_pick_delta[0]["hero"],
                "most_picked_delta": by_pick_delta[0]["pick_rate_delta"],
                "most_picked_map": by_pick_delta[0]["pick_rate_map"],
                "most_picked_overall": by_pick_delta[0]["pick_rate_overall"],
                "least_picked_hero": by_pick_delta[-1]["hero"],
                "least_picked_delta": by_pick_delta[-1]["pick_rate_delta"],
                "least_picked_map": by_pick_delta[-1]["pick_rate_map"],
                "least_picked_overall": by_pick_delta[-1]["pick_rate_overall"],
                "most_contested_hero": by_pick_ratio[0]["hero"],
                "most_contested_ratio": by_pick_ratio[0]["pick_rate_ratio"],
            })

    return overview


def generate_per_map_reports(overall_stats: str, maps_dir: str, out_dir: Path, region: str = None):
    """Generate and save per-map detailed reports."""
    overall = load_overall_stats(overall_stats)
    maps_path = Path(maps_dir)
    map_files = sorted(maps_path.glob("*.json"))

    count = 0
    for map_file in map_files:
        map_name = map_file.stem
        map_stats = load_map_stats(map_file)

        if region:
            if region not in map_stats:
                continue
            regions_to_process = [region]
        else:
            regions_to_process = list(map_stats.keys())

        map_report = []
        for r in regions_to_process:
            metrics = calculate_metrics(map_stats[r], overall, r)
            map_report.extend(metrics)

        if not map_report:
            continue

        count += 1
        # Saves are handled by caller based on format preference
        yield map_name, map_report


def save_overview(overview: list, out_dir: Path, format: str = "csv"):
    """Save overview report in specified format(s)."""
    out_dir.mkdir(parents=True, exist_ok=True)

    if format in ("csv", "both"):
        out_csv = out_dir / "overview.csv"
        with open(out_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=overview[0].keys())
            writer.writeheader()
            writer.writerows(overview)
        print(f"Wrote overview to {out_csv.name}")

    if format in ("json", "both"):
        out_json = out_dir / "overview.json"
        with open(out_json, "w", encoding="utf-8") as f:
            json.dump(overview, f, indent=2)
        print(f"Wrote overview to {out_json.name}")


def save_per_map_reports(gen, out_dir: Path, format: str = "csv"):
    """Save per-map reports from generator in specified format(s)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    for map_name, map_report in gen:
        if format in ("csv", "both"):
            out_csv = out_dir / f"{map_name}.csv"
            with open(out_csv, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=map_report[0].keys())
                writer.writeheader()
                writer.writerows(map_report)
            count += 1

        if format in ("json", "both"):
            out_json = out_dir / f"{map_name}.json"
            with open(out_json, "w", encoding="utf-8") as f:
                json.dump(map_report, f, indent=2)
            count += 1

    print(f"Wrote {count} per-map report(s)")


def generate_report(overall_stats: str, maps_dir: str, region: str = None, out_dir: str = None, per_map: bool = False, format: str = "csv"):
    """Load data and generate reports."""

    if out_dir is None:
        out_root = _ROOT / "outputs"
        per_map_dir = out_root / "map_hero_reports"
    else:
        out_root = Path(out_dir)
        per_map_dir = out_root / "map_hero_reports"

    # Load overall stats
    print(f"Loading overall stats from {overall_stats}...")
    overall = load_overall_stats(overall_stats)
    print(f"  Found {len(overall)} heroes")

    # Find all map files
    maps_path = Path(maps_dir)
    map_files = sorted(maps_path.glob("*.json"))
    print(f"Found {len(map_files)} map files in {maps_dir}")
    print()

    # Generate and save overview to main outputs dir
    print("Generating overview...")
    overview = generate_overview(overall_stats, maps_dir, region)
    save_overview(overview, out_root, format=format)
    print()

    # Optionally generate per-map reports to subdirectory
    if per_map:
        print("Generating per-map reports...")
        gen = generate_per_map_reports(overall_stats, maps_dir, per_map_dir, region)
        save_per_map_reports(gen, per_map_dir, format=format)
        print()


def main():
    parser = argparse.ArgumentParser(
        description="Generate per-map hero performance reports"
    )
    parser.add_argument(
        "--data",
        default="comp_mnk",
        help="Data file prefix (default: comp_mnk)",
    )
    parser.add_argument(
        "--region",
        help="Filter to specific region (americas/asia/europe, default: all)",
    )
    parser.add_argument(
        "--out",
        help="Output directory (default: outputs/map_hero_reports/)",
    )
    parser.add_argument(
        "--per-map",
        action="store_true",
        help="Also generate detailed per-map reports",
    )
    parser.add_argument(
        "--format",
        choices=["csv", "json", "both"],
        default="csv",
        help="Output format (default: csv)",
    )

    args = parser.parse_args()

    overall_file = _ROOT / "data" / f"{args.data}.json"
    maps_dir = _ROOT / "data" / "maps" / args.data

    if not overall_file.exists():
        print(f"ERROR: {overall_file} not found")
        return 1
    if not maps_dir.exists():
        print(f"ERROR: {maps_dir} not found")
        return 1

    generate_report(
        str(overall_file),
        str(maps_dir),
        region=args.region,
        out_dir=args.out,
        per_map=args.per_map,
        format=args.format,
    )


if __name__ == "__main__":
    main()
