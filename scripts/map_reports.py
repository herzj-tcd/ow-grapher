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

    If no region filter, averages metrics across all regions.
    Returns list of dicts with map-level summary stats.
    """
    overall = load_overall_stats(overall_stats)
    maps_path = Path(maps_dir)
    map_files = sorted(maps_path.glob("*.json"))

    overview = []

    for map_file in map_files:
        map_name = map_file.stem
        map_stats = load_map_stats(map_file)

        # If region filter specified, process only that region
        if region:
            if region not in map_stats:
                continue
            regions_to_process = [region]
        else:
            regions_to_process = list(map_stats.keys())

        # Aggregate metrics across regions (or single region if filtered)
        aggregated_metrics = defaultdict(
            lambda: {
                "wr_map_sum": 0,
                "wr_delta_sum": 0,
                "wr_ratio_sum": 0,
                "pick_map_sum": 0,
                "pick_delta_sum": 0,
                "pick_ratio_sum": 0,
                "count": 0,
            }
        )

        for r in regions_to_process:
            metrics = calculate_metrics(map_stats[r], overall, r)
            for m in metrics:
                hero = m["hero"]
                aggregated_metrics[hero]["wr_map_sum"] += m["win_rate_map"]
                aggregated_metrics[hero]["wr_delta_sum"] += m["win_rate_delta"]
                aggregated_metrics[hero]["wr_ratio_sum"] += m["win_rate_multiplier"]
                aggregated_metrics[hero]["pick_map_sum"] += m["pick_rate_map"]
                aggregated_metrics[hero]["pick_delta_sum"] += m["pick_rate_delta"]
                aggregated_metrics[hero]["pick_ratio_sum"] += m["pick_rate_ratio"]
                aggregated_metrics[hero]["count"] += 1

        # Calculate averages
        averaged = {}
        for hero, stats in aggregated_metrics.items():
            n = stats["count"]
            averaged[hero] = {
                "wr_map": stats["wr_map_sum"] / n,
                "wr_delta": stats["wr_delta_sum"] / n,
                "wr_ratio": stats["wr_ratio_sum"] / n,
                "pick_map": stats["pick_map_sum"] / n,
                "pick_delta": stats["pick_delta_sum"] / n,
                "pick_ratio": stats["pick_ratio_sum"] / n,
            }

        # Sort by different metrics
        by_wr_absolute = sorted(averaged.items(), key=lambda x: x[1]["wr_map"], reverse=True)
        by_wr_delta = sorted(averaged.items(), key=lambda x: x[1]["wr_delta"], reverse=True)
        by_wr_ratio = sorted(averaged.items(), key=lambda x: x[1]["wr_ratio"], reverse=True)
        by_pick_absolute = sorted(averaged.items(), key=lambda x: x[1]["pick_map"], reverse=True)
        by_pick_delta = sorted(averaged.items(), key=lambda x: x[1]["pick_delta"], reverse=True)
        by_pick_ratio = sorted(averaged.items(), key=lambda x: x[1]["pick_ratio"], reverse=True)

        entry = {
            "map": map_name,
            # Win rate: absolute, delta, ratio (highest then lowest for each)
            "highest_wr": by_wr_absolute[0][0],
            "most_improved_wr": by_wr_delta[0][0],
            "most_improved_wr_relative": by_wr_ratio[0][0],
            "lowest_wr": by_wr_absolute[-1][0],
            "most_decreased_wr": by_wr_delta[-1][0],
            "most_decreased_wr_relative": by_wr_ratio[-1][0],
            # Pick rate: absolute, delta, ratio (highest then lowest for each)
            "highest_pick": by_pick_absolute[0][0],
            "most_picked_increase": by_pick_delta[0][0],
            "most_picked_increase_relative": by_pick_ratio[0][0],
            "lowest_pick": by_pick_absolute[-1][0],
            "most_picked_decrease": by_pick_delta[-1][0],
            "most_picked_decrease_relative": by_pick_ratio[-1][0],
        }
        overview.append(entry)

    return overview


def generate_per_map_reports(overall_stats: str, maps_dir: str, out_dir: Path, region: str = None):
    """Generate and save per-map detailed reports.

    Yields tuples of (map_name, map_report, target_region) where target_region
    is the region to use in the output folder structure.
    """
    overall = load_overall_stats(overall_stats)
    maps_path = Path(maps_dir)
    map_files = sorted(maps_path.glob("*.json"))

    for map_file in map_files:
        map_name = map_file.stem
        map_stats = load_map_stats(map_file)

        if region:
            if region not in map_stats:
                continue
            regions_to_process = [region]
        else:
            regions_to_process = list(map_stats.keys())

        for r in regions_to_process:
            metrics = calculate_metrics(map_stats[r], overall, r)

            # Remove region column from metrics for individual region reports
            for metric in metrics:
                metric.pop("region", None)

            if not metrics:
                continue

            # Yield with target region for folder organization
            yield map_name, metrics, r


def save_overview(overview: list, out_dir: Path, format: str = "csv"):
    """Save overview report in specified format(s)."""
    out_dir.mkdir(parents=True, exist_ok=True)

    if format in ("csv", "both"):
        out_csv = out_dir / "map_reports_overview.csv"
        with open(out_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=overview[0].keys())
            writer.writeheader()
            writer.writerows(overview)
        print(f"Wrote overview to {out_csv.name}")

    if format in ("json", "both"):
        out_json = out_dir / "map_reports_overview.json"
        with open(out_json, "w", encoding="utf-8") as f:
            json.dump(overview, f, indent=2)
        print(f"Wrote overview to {out_json.name}")


def save_per_map_reports(gen, out_dir: Path, region: str = None, format: str = "csv"):
    """Save per-map reports from generator in specified format(s).

    Organizes files by region folder structure if multiple regions.
    """
    count = 0
    for map_name, map_report, region_name in gen:
        # Create region-specific subdirectory
        if region:
            # Single region specified, save directly to out_dir
            region_dir = out_dir
        else:
            # Multiple regions, organize by region
            region_dir = out_dir / region_name

        region_dir.mkdir(parents=True, exist_ok=True)

        if format in ("csv", "both"):
            out_csv = region_dir / f"{map_name}.csv"
            with open(out_csv, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=map_report[0].keys())
                writer.writeheader()
                writer.writerows(map_report)
            count += 1

        if format in ("json", "both"):
            out_json = region_dir / f"{map_name}.json"
            with open(out_json, "w", encoding="utf-8") as f:
                json.dump(map_report, f, indent=2)
            count += 1

    print(f"Wrote {count} per-map report(s)")


def generate_report(overall_stats: str, maps_dir: str, region: str = None, out_dir: str = None, per_map: bool = False, format: str = "csv"):
    """Load data and generate reports."""

    if out_dir is None:
        out_root = _ROOT / "outputs"
        per_map_dir = out_root / "map_reports"
    else:
        out_root = Path(out_dir)
        per_map_dir = out_root / "map_reports"

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
        save_per_map_reports(gen, per_map_dir, region=region, format=format)
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
        help="Output directory (default: outputs/map_reports/)",
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
