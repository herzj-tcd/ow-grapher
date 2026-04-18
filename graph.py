#!/usr/bin/env python3
"""
Draw win rate / pick rate line graphs per hero across ranks.

Usage:
    python3 graph.py                        # all heroes, average of all regions
    python3 graph.py --hero Ana             # one hero only
    python3 graph.py --americas             # Americas region only
    python3 graph.py --asia --hero Tracer   # Asia, one hero
    python3 graph.py --data other.json      # use a different data file
    python3 graph.py --out results/         # different output folder
"""

import argparse
import json
import sys
from datetime import date
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np

RANK_ORDER = ["bronze", "silver", "gold", "platinum", "diamond", "master", "grandmaster"]
RANK_LABELS = ["Bronze", "Silver", "Gold", "Platinum", "Diamond", "Master", "GM"]

PICK_COLOR = "#E87722"   # orange
WIN_COLOR  = "#3A8FD4"   # blue

REGION_DISPLAY = {
    "americas": "Americas",
    "asia":     "Asia",
    "europe":   "Europe",
    "all":      "All Regions",
}


def load_data(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def filter_region(rows: list[dict], region: str | None) -> tuple[list[dict], str]:
    """Return (filtered_rows, region_label). region=None means average all three."""
    ranked = [r for r in rows if r["tier"] != "all"]
    if region:
        filtered = [r for r in ranked if r["region"] == region]
        return filtered, region
    return ranked, "all"


def compute_series(rows: list[dict], hero: str, region_key: str) -> dict:
    """
    Returns {"pick": [float|None x7], "win": [float|None x7]}
    averaged over regions when region_key == "all".
    """
    hero_rows = [r for r in rows if r["hero"].lower() == hero.lower()]

    pick_vals = []
    win_vals  = []
    for rank in RANK_ORDER:
        rank_rows = [r for r in hero_rows if r["tier"] == rank]
        if not rank_rows:
            pick_vals.append(None)
            win_vals.append(None)
            continue
        picks = [r["pick_rate"] for r in rank_rows if r["pick_rate"] is not None]
        wins  = [r["win_rate"]  for r in rank_rows if r["win_rate"]  is not None]
        pick_vals.append(sum(picks) / len(picks) if picks else None)
        win_vals.append(sum(wins)   / len(wins)  if wins  else None)

    return {"pick": pick_vals, "win": win_vals}


def mean_ignoring_none(vals: list) -> float | None:
    valid = [v for v in vals if v is not None]
    return sum(valid) / len(valid) if valid else None


def make_graph(
    hero: str,
    series: dict,
    region_key: str,
    out_dir: Path,
    data_date: str,
    patch: str | None,
) -> Path:
    pick_vals = series["pick"]
    win_vals  = series["win"]

    x = np.arange(len(RANK_ORDER))

    fig, ax = plt.subplots(figsize=(10, 5.5))
    fig.patch.set_facecolor("#1A1A2E")
    ax.set_facecolor("#16213E")

    def plot_line(vals, color, label):
        # Split into segments at None gaps so lines don't bridge missing data
        xs, ys = [], []
        for i, v in enumerate(vals):
            if v is not None:
                xs.append(x[i])
                ys.append(v)
            elif xs:
                ax.plot(xs, ys, color=color, linewidth=2, zorder=3)
                ax.scatter(xs, ys, color=color, s=55, zorder=4)
                xs, ys = [], []
        if xs:
            ax.plot(xs, ys, color=color, linewidth=2, label=label, zorder=3)
            ax.scatter(xs, ys, color=color, s=55, zorder=4)

        avg = mean_ignoring_none(vals)
        if avg is not None:
            ax.axhline(avg, color=color, linestyle="--", linewidth=1.2,
                       alpha=0.7, zorder=2)

    plot_line(pick_vals, PICK_COLOR, "Pick Rate")
    plot_line(win_vals,  WIN_COLOR,  "Win Rate")

    # X axis
    ax.set_xticks(x)
    ax.set_xticklabels(RANK_LABELS, color="#CCCCCC", fontsize=10)

    # Y axis
    all_vals = [v for v in pick_vals + win_vals if v is not None]
    if all_vals:
        lo = max(0, min(all_vals) - 5)
        hi = max(all_vals) + 5
        ax.set_ylim(lo, hi)
    ax.yaxis.set_major_formatter(ticker.FormatStrFormatter("%.1f%%"))
    ax.tick_params(axis="y", colors="#CCCCCC", labelsize=9)

    # Grid
    ax.grid(axis="y", color="#2A2A4A", linewidth=0.7, zorder=1)
    ax.set_axisbelow(True)
    for spine in ax.spines.values():
        spine.set_edgecolor("#2A2A4A")

    # Legend — manual patches so dotted lines show correctly
    from matplotlib.lines import Line2D
    legend_elements = [
        Line2D([0], [0], color=PICK_COLOR, linewidth=2, marker="o",
               markersize=6, label="Pick Rate"),
        Line2D([0], [0], color=WIN_COLOR,  linewidth=2, marker="o",
               markersize=6, label="Win Rate"),
        Line2D([0], [0], color=PICK_COLOR, linewidth=1.2, linestyle="--",
               alpha=0.7, label="Pick Rate avg"),
        Line2D([0], [0], color=WIN_COLOR,  linewidth=1.2, linestyle="--",
               alpha=0.7, label="Win Rate avg"),
    ]
    ax.legend(handles=legend_elements, facecolor="#1A1A2E", edgecolor="#2A2A4A",
              labelcolor="#CCCCCC", fontsize=9, loc="best")

    # Title
    region_label = REGION_DISPLAY.get(region_key, region_key.title())
    patch_str = f"  •  Patch {patch}" if patch else ""
    ax.set_title(
        f"{hero}  —  Pick & Win Rate by Rank\n"
        f"{region_label}{patch_str}",
        color="white", fontsize=13, pad=12,
    )
    ax.set_xlabel("Rank", color="#AAAAAA", fontsize=10)

    fig.tight_layout()

    out_dir.mkdir(parents=True, exist_ok=True)
    slug = hero.lower().replace(" ", "_").replace(":", "")
    filename = f"{slug}-{region_key.replace(' ', '_')}-{data_date}.png"
    out_path = out_dir / filename
    fig.savefig(out_path, dpi=150, facecolor=fig.get_facecolor())
    plt.close(fig)
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Graph OW hero pick/win rates by rank")
    region_group = parser.add_mutually_exclusive_group()
    region_group.add_argument("--americas", action="store_true")
    region_group.add_argument("--asia",     action="store_true")
    region_group.add_argument("--europe",   action="store_true")
    parser.add_argument("--hero",  metavar="NAME", help="Only graph this hero")
    parser.add_argument("--data",  default="rates.json", metavar="FILE")
    parser.add_argument("--out",   default="outputs", metavar="DIR")
    args = parser.parse_args()

    payload = load_data(args.data)
    rows    = payload["rows"]
    patch   = payload.get("patch_note")

    if args.americas:
        region_key = "americas"
    elif args.asia:
        region_key = "asia"
    elif args.europe:
        region_key = "europe"
    else:
        region_key = "all"

    filtered_rows, region_key = filter_region(rows, region_key if region_key != "all" else None)

    data_date = date.today().isoformat()
    out_dir   = Path(args.out)

    # Collect hero list
    all_heroes = list(dict.fromkeys(r["hero"] for r in rows if r["tier"] != "all"))
    if args.hero:
        match = next((h for h in all_heroes if h.lower() == args.hero.lower()), None)
        if match is None:
            names = ", ".join(all_heroes)
            print(f"Hero {args.hero!r} not found. Available: {names}", file=sys.stderr)
            sys.exit(1)
        heroes = [match]
    else:
        heroes = all_heroes

    print(f"Generating {len(heroes)} graph(s)  region={region_key}  patch={patch}")
    for hero in heroes:
        series   = compute_series(filtered_rows, hero, region_key)
        out_path = make_graph(hero, series, region_key, out_dir, data_date, patch)
        print(f"  {out_path}")

    print(f"\nDone. {len(heroes)} file(s) written to {out_dir}/")


if __name__ == "__main__":
    main()
