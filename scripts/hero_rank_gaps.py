#!/usr/bin/env python3
"""
Bar chart: Bronze → Grandmaster gap in pick rate and win rate per hero.

Positive gap = higher at GM than Bronze; negative = lower.
Heroes sorted by pick-rate gap descending.

Usage:
    python3 hero_rank_gaps.py                  # all regions averaged
    python3 hero_rank_gaps.py --americas       # one region only
    python3 hero_rank_gaps.py --role support   # filter by role
    python3 hero_rank_gaps.py --data other.json --out results/
"""

import argparse
import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np

RANK_ORDER  = ["bronze", "silver", "gold", "platinum", "diamond", "master", "grandmaster"]

PICK_COLOR  = "#E87722"
WIN_COLOR   = "#3A8FD4"

ROLE_COLORS = {
    "tank":    "#5B9BD5",
    "damage":  "#E87722",
    "support": "#70AD47",
}

REGION_DISPLAY = {
    "americas": "Americas",
    "asia":     "Asia",
    "europe":   "Europe",
    "all":      "All Regions",
}


def load_data(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _mean(vals: list) -> float | None:
    valid = [v for v in vals if v is not None]
    return sum(valid) / len(valid) if valid else None


def compute_gaps(
    rows: list[dict],
    region: str | None,
    hero_roles: dict,
) -> list[dict]:
    """
    For each hero return the GM minus Bronze gap for pick and win rate,
    averaged across regions (or one region if specified).
    Heroes with null data at either endpoint are dropped.
    """
    ranked = [r for r in rows if r["tier"] in ("bronze", "grandmaster")]
    if region:
        ranked = [r for r in ranked if r["region"] == region]

    heroes = list(dict.fromkeys(r["hero"] for r in ranked))
    results = []
    for hero in heroes:
        bronze_rows = [r for r in ranked if r["hero"] == hero and r["tier"] == "bronze"]
        gm_rows     = [r for r in ranked if r["hero"] == hero and r["tier"] == "grandmaster"]

        bronze_pick = _mean([r["pick_rate"] for r in bronze_rows])
        bronze_win  = _mean([r["win_rate"]  for r in bronze_rows])
        gm_pick     = _mean([r["pick_rate"] for r in gm_rows])
        gm_win      = _mean([r["win_rate"]  for r in gm_rows])

        if any(v is None for v in (bronze_pick, bronze_win, gm_pick, gm_win)):
            continue

        results.append({
            "hero":       hero,
            "role":       hero_roles.get(hero, "damage"),
            "pick_gap":   gm_pick  - bronze_pick,
            "win_gap":    gm_win   - bronze_win,
            "bronze_pick": bronze_pick,
            "gm_pick":     gm_pick,
            "bronze_win":  bronze_win,
            "gm_win":      gm_win,
        })

    results.sort(key=lambda h: h["pick_gap"])
    return results


def make_chart(
    gaps: list[dict],
    region_key: str,
    out_dir: Path,
    patch: str | None,
    fetched_date: str | None,
    role_filter: str | None,
) -> Path:
    if role_filter:
        gaps = [g for g in gaps if g["role"] == role_filter]
    if not gaps:
        print("No data after filtering.", file=sys.stderr)
        sys.exit(1)

    heroes    = [g["hero"]    for g in gaps]
    pick_gaps = [g["pick_gap"] for g in gaps]
    win_gaps  = [g["win_gap"]  for g in gaps]
    roles     = [g["role"]     for g in gaps]

    n  = len(heroes)
    x  = np.arange(n)

    region_label = REGION_DISPLAY.get(region_key, region_key.title())
    patch_str    = f"  •  Patch {patch}" if patch else ""
    date_str     = f"  •  {fetched_date}" if fetched_date else ""
    subtitle     = f"{region_label}{patch_str}{date_str}"

    fig, (ax_pick, ax_win) = plt.subplots(
        2, 1, figsize=(max(14, n * 0.38), 10),
        sharex=True, gridspec_kw={"hspace": 0.06},
        layout="constrained",
    )
    fig.patch.set_facecolor("#1A1A2E")

    bar_colors = [ROLE_COLORS.get(r, "#AAAAAA") for r in roles]

    for ax, vals, label, low_label, high_label in (
        (ax_pick, pick_gaps, "Pick Rate Gap (GM − Bronze)", "More picked in Bronze", "More picked in GM"),
        (ax_win,  win_gaps,  "Win Rate Gap (GM − Bronze)",  "Higher win rate in Bronze", "Higher win rate in GM"),
    ):
        ax.set_facecolor("#16213E")
        ax.bar(x, vals, color=bar_colors, width=0.7, zorder=3, edgecolor="#1A1A2E", linewidth=0.4)
        ax.axhline(0, color="#AAAAAA", linewidth=0.9, zorder=4)
        ax.yaxis.set_major_formatter(ticker.FormatStrFormatter("%+.1f%%"))
        ax.tick_params(axis="y", colors="#CCCCCC", labelsize=9)
        ax.grid(axis="y", color="#2A2A4A", linewidth=0.6, zorder=0)
        ax.set_axisbelow(True)
        for spine in ax.spines.values():
            spine.set_edgecolor("#2A2A4A")
        ax.set_ylabel(label, color="#AAAAAA", fontsize=10)
        y_min, y_max = ax.get_ylim()
        mid = len(x) // 2
        kw = dict(fontsize=7.5, alpha=0.45, color="white", va="center", zorder=2)
        ax.text(mid, y_min * 0.85, low_label, **kw)
        ax.text(mid, y_max * 0.85, high_label,  **kw)

    ax_pick.spines["bottom"].set_visible(False)
    ax_win.spines["top"].set_visible(False)
    ax_pick.tick_params(axis="x", bottom=False)

    ax_win.set_xticks(x)
    ax_win.set_xticklabels(heroes, rotation=45, ha="right", color="#CCCCCC", fontsize=8)

    # Role colour legend
    from matplotlib.patches import Patch
    legend_handles = [
        Patch(facecolor=ROLE_COLORS["tank"],    label="Tank"),
        Patch(facecolor=ROLE_COLORS["damage"],  label="Damage"),
        Patch(facecolor=ROLE_COLORS["support"], label="Support"),
    ]
    ax_pick.legend(
        handles=legend_handles,
        facecolor="#1A1A2E", edgecolor="#2A2A4A", labelcolor="#CCCCCC",
        fontsize=9, loc="upper right",
    )

    role_str = f"  •  {role_filter.title()}" if role_filter else ""
    fig.suptitle(
        f"Bronze → Grandmaster Gap{role_str}\n{subtitle}",
        color="white", fontsize=13,
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    role_slug   = f"_{role_filter}" if role_filter else ""
    region_slug = region_key.replace(" ", "_")
    out_path    = out_dir / f"rank_gaps_{region_slug}{role_slug}.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Bronze→GM gap bar chart")

    region_group = parser.add_mutually_exclusive_group()
    region_group.add_argument("--americas", action="store_true")
    region_group.add_argument("--asia",     action="store_true")
    region_group.add_argument("--europe",   action="store_true")

    parser.add_argument("--role", metavar="ROLE", choices=["tank", "damage", "support"])
    parser.add_argument("--data", default="data/rates.json", metavar="FILE")
    parser.add_argument("--out",  default="outputs",    metavar="DIR")
    args = parser.parse_args()

    payload      = load_data(args.data)
    rows         = payload["rows"]
    patch        = payload.get("patch_note")
    fetched_date = (payload.get("fetched_at") or "")[:10] or None
    hero_roles   = payload.get("hero_roles", {})

    if args.americas:
        region_key = "americas"
    elif args.asia:
        region_key = "asia"
    elif args.europe:
        region_key = "europe"
    else:
        region_key = "all"

    region_filter = None if region_key == "all" else region_key

    gaps = compute_gaps(rows, region_filter, hero_roles)
    print(f"Heroes with complete data: {len(gaps)}  region={region_key}")

    out_path = make_chart(gaps, region_key, Path(args.out), patch, fetched_date, args.role)
    print(f"  {out_path}")


if __name__ == "__main__":
    main()
