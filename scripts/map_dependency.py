#!/usr/bin/env python3
"""
Measure hero map dependency using coefficient of variation.

Metrics:
  - pick_rate_cv: std_dev(pick_rates across maps) / mean(pick_rates)
  - win_rate_cv: std_dev(win_rates across maps) / mean(|win_rates - 50%|)

The win rate CV is normalized by distance from 50% (the relevant magnitude for skew).

Usage:
    python3 map_dependency.py                    # generate scatter plot (default)
    python3 map_dependency.py --csv              # output CSV instead
    python3 map_dependency.py --data comp_mnk    # different dataset
    python3 map_dependency.py --region americas  # filter to one region
"""

import argparse
import json
import csv
from pathlib import Path
from collections import defaultdict
import statistics
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
from adjustText import adjust_text

_ROOT = Path(__file__).parent.parent

INPUT_MODE = "Mouse & Keyboard"

REGION_DISPLAY = {
    "americas": "Americas",
    "asia":     "Asia",
    "europe":   "Europe",
    "all":      "All Regions",
}


def load_data(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_overall_stats(data_path: str) -> dict:
    """Load overall stats, aggregate across all regions and tiers.

    Returns dict: {hero_name: {"pick_rate": float, "win_rate": float}}
    """
    data = load_data(data_path)

    hero_stats = defaultdict(lambda: {"pick_sum": 0, "win_sum": 0, "count": 0})

    for row in data["rows"]:
        hero = row["hero"]
        hero_stats[hero]["pick_sum"] += row["pick_rate"]
        hero_stats[hero]["win_sum"] += row["win_rate"]
        hero_stats[hero]["count"] += 1

    result = {}
    for hero, stats in hero_stats.items():
        result[hero] = {
            "pick_rate": stats["pick_sum"] / stats["count"],
            "win_rate": stats["win_sum"] / stats["count"],
        }
    return result


def load_all_map_stats(maps_dir: str, region: str = None) -> dict:
    """Load all map-specific stats and aggregate by hero.

    Returns dict: {hero_name: {"pick_rates": [float], "win_rates": [float]}}
    """
    maps_path = Path(maps_dir)
    map_files = sorted(maps_path.glob("*.json"))

    hero_map_data = defaultdict(lambda: {"pick_rates": [], "win_rates": []})

    for map_file in map_files:
        data = load_data(str(map_file))

        for row in data["rows"]:
            hero = row["hero"]
            if region and row["region"] != region:
                continue

            hero_map_data[hero]["pick_rates"].append(row["pick_rate"])
            hero_map_data[hero]["win_rates"].append(row["win_rate"])

    return dict(hero_map_data)


def calculate_pick_rate_cv(pick_rates: list) -> float:
    """Calculate coefficient of variation for pick rates."""
    if not pick_rates or len(pick_rates) < 2:
        return 0.0

    mean = statistics.mean(pick_rates)
    if mean == 0:
        return 0.0

    std_dev = statistics.stdev(pick_rates)
    return std_dev / mean


def calculate_win_rate_cv(win_rates: list) -> float:
    """Calculate coefficient of variation for win rates.

    Normalized by distance from 50% (the relevant magnitude for skew).
    """
    if not win_rates or len(win_rates) < 2:
        return 0.0

    distances = [abs(wr - 50.0) for wr in win_rates]
    mean_distance = statistics.mean(distances)

    if mean_distance == 0:
        return 0.0

    std_dev = statistics.stdev(win_rates)
    return std_dev / mean_distance


def calculate_metrics(hero_map_data: dict, overall_stats: dict) -> dict:
    """Calculate CVs for each hero.

    Returns dict: {hero_name: {"pick_cv": float, "win_cv": float, "overall_wr": float}}
    """
    results = {}

    for hero, map_data in hero_map_data.items():
        if hero not in overall_stats:
            continue

        pick_cv = calculate_pick_rate_cv(map_data["pick_rates"])
        win_cv = calculate_win_rate_cv(map_data["win_rates"])
        overall_wr = overall_stats[hero]["win_rate"]

        results[hero] = {
            "pick_cv": pick_cv,
            "win_cv": win_cv,
            "overall_wr": overall_wr,
        }

    return results


def make_scatter(
    metrics: dict,
    region_key: str,
    out_dir: Path,
    patch: str | None,
    fetched_date: str | None,
) -> Path:
    """Generate and save scatter plot with hero map dependency metrics."""
    if not metrics:
        print("No metrics to plot.")
        return None

    heroes = list(metrics.keys())
    pick_cvs = [metrics[h]["pick_cv"] for h in heroes]
    win_cvs = [metrics[h]["win_cv"] for h in heroes]
    colors = [metrics[h]["overall_wr"] for h in heroes]

    region_label = REGION_DISPLAY.get(region_key, region_key.title())
    patch_str = f"  •  Patch {patch}" if patch else ""
    date_str = f"  •  {fetched_date}" if fetched_date else ""
    subtitle = f"{region_label}  •  {INPUT_MODE}{patch_str}{date_str}"

    figsize = (13, 8)
    label_fontsize = 6.5
    tick_fontsize = 9
    axis_fontsize = 11
    title_fontsize = 13

    fig, ax = plt.subplots(figsize=figsize)
    fig.patch.set_facecolor("#1A1A2E")
    ax.set_facecolor("#16213E")

    # Reference lines: average pick and win rate CVs
    avg_pick_cv = sum(pick_cvs) / len(pick_cvs)
    ax.axhline(
        statistics.mean(win_cvs),
        color="#AAAAAA",
        linewidth=0.9,
        alpha=0.4,
        zorder=1,
        linestyle="--",
    )
    ax.axvline(
        avg_pick_cv,
        color="#AAAAAA",
        linewidth=0.9,
        alpha=0.4,
        zorder=1,
        linestyle="--",
    )

    scatter = ax.scatter(
        pick_cvs,
        win_cvs,
        c=colors,
        cmap="RdYlGn",
        s=70,
        alpha=0.7,
        vmin=45,
        vmax=55,
        edgecolors="#1A1A2E",
        linewidths=0.6,
        zorder=3,
    )

    # Hero labels with adjust_text
    texts = [
        ax.text(
            pick_cvs[i],
            win_cvs[i],
            hero,
            fontsize=label_fontsize,
            color="#DDDDDD",
            zorder=5,
        )
        for i, hero in enumerate(heroes)
    ]
    adjust_text(
        texts,
        ax=ax,
        add_objects=[scatter],
        arrowprops=dict(arrowstyle="-", color="#666666", lw=0.5, shrinkA=5),
    )

    ax.tick_params(colors="#CCCCCC", labelsize=tick_fontsize)
    ax.grid(color="#2A2A4A", linewidth=0.6, zorder=0)
    ax.set_axisbelow(True)
    for spine in ax.spines.values():
        spine.set_edgecolor("#2A2A4A")

    ax.set_xlabel("Pick Rate Variability (CV)", color="#AAAAAA", fontsize=axis_fontsize)
    ax.set_ylabel("Win Rate Variability (CV)", color="#AAAAAA", fontsize=axis_fontsize)

    cbar = plt.colorbar(scatter, ax=ax)
    cbar.set_label("Overall Win Rate (%)", fontsize=axis_fontsize, color="#AAAAAA")
    cbar.ax.tick_params(colors="#CCCCCC", labelsize=tick_fontsize)

    ax.set_title(
        f"Hero Map Dependency\n{subtitle}",
        color="white",
        fontsize=title_fontsize,
        pad=12,
    )

    fig.tight_layout()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "map_dependency.png"
    fig.savefig(out_path, dpi=150, facecolor=fig.get_facecolor())
    plt.close(fig)
    return out_path


def save_csv(metrics: dict, out_path: Path):
    """Save metrics to CSV."""
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=["hero", "pick_cv", "win_cv", "overall_wr"]
        )
        writer.writeheader()
        for hero, data in sorted(metrics.items()):
            writer.writerow(
                {
                    "hero": hero,
                    "pick_cv": round(data["pick_cv"], 3),
                    "win_cv": round(data["win_cv"], 3),
                    "overall_wr": round(data["overall_wr"], 2),
                }
            )

    print(f"Wrote metrics to {out_path}")


def main():
    parser = argparse.ArgumentParser(description="Analyze hero map dependency")
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
        help="Output directory (default: outputs/)",
    )
    parser.add_argument(
        "--csv",
        action="store_true",
        help="Output CSV instead of scatter plot",
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

    if args.out:
        out_dir = Path(args.out)
    else:
        out_dir = _ROOT / "outputs"

    # Load data
    print(f"Loading overall stats from {overall_file}...")
    overall_stats = load_overall_stats(str(overall_file))
    print(f"  Found {len(overall_stats)} heroes")

    # Get patch and date info
    payload = load_data(str(overall_file))
    patch = payload.get("patch_note")
    fetched_date = (payload.get("fetched_at") or "")[:10] or None

    print(f"Loading map stats from {maps_dir}...")
    hero_map_data = load_all_map_stats(str(maps_dir), region=args.region)
    print(f"  Loaded map data for {len(hero_map_data)} heroes")
    print()

    # Calculate metrics
    print("Calculating map dependency metrics...")
    metrics = calculate_metrics(hero_map_data, overall_stats)
    print(f"  Calculated metrics for {len(metrics)} heroes")
    print()

    # Output
    region_key = args.region or "all"
    if args.csv:
        out_path = out_dir / "map_dependency.csv"
        save_csv(metrics, out_path)
    else:
        out_path = make_scatter(metrics, region_key, out_dir, patch, fetched_date)
        if out_path:
            print(f"Wrote scatter plot to {out_path}")


if __name__ == "__main__":
    main()
