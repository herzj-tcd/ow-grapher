#!/usr/bin/env python3
"""
Scatter plot: pick rate (x) vs win rate (y), one point per hero.

Usage:
    python3 scatter.py                         # all regions, all ranks
    python3 scatter.py --rank bronze           # bronze tier only
    python3 scatter.py --americas              # Americas region only
    python3 scatter.py --europe --rank master  # Europe, master tier
    python3 scatter.py --role support          # only support heroes
    python3 scatter.py --data other.json       # different data file
    python3 scatter.py --out results/          # different output folder
"""

import argparse
import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

RANK_ORDER = ["bronze", "silver", "gold", "platinum", "diamond", "master", "grandmaster"]

ROLE_COLORS = {
    "tank":    "#5B9BD5",
    "damage":  "#E87722",
    "support": "#70AD47",
}
ROLE_LABELS = {
    "tank":    "Tank",
    "damage":  "Damage",
    "support": "Support",
}

REGION_DISPLAY = {
    "americas": "Americas",
    "asia":     "Asia",
    "europe":   "Europe",
    "all":      "All Regions",
}

RANK_DISPLAY = {
    "bronze":       "Bronze",
    "silver":       "Silver",
    "gold":         "Gold",
    "platinum":     "Platinum",
    "diamond":      "Diamond",
    "master":       "Master",
    "grandmaster":  "Grandmaster+",
    "all":          "All Ranks",
}


def load_data(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _mean(vals: list) -> float | None:
    valid = [v for v in vals if v is not None]
    return sum(valid) / len(valid) if valid else None


def build_points(
    rows: list[dict],
    region: str | None,
    tier: str,
    hero_roles: dict,
) -> list[dict]:
    """
    Return one averaged point per hero.
    region=None  → average all three regions.
    tier="all"   → use the pre-aggregated 'all' rows from the API.
    """
    subset = rows
    if region:
        subset = [r for r in subset if r["region"] == region]
    subset = [r for r in subset if r["tier"] == tier]

    heroes = list(dict.fromkeys(r["hero"] for r in subset))
    points = []
    for hero in heroes:
        hero_rows = [r for r in subset if r["hero"] == hero]
        pick = _mean([r["pick_rate"] for r in hero_rows])
        win  = _mean([r["win_rate"]  for r in hero_rows])
        if pick is None or win is None:
            continue
        points.append({
            "hero": hero,
            "pick_rate": pick,
            "win_rate": win,
            "role": hero_roles.get(hero, "damage"),
        })
    return points


def make_scatter(
    points: list[dict],
    region_key: str,
    tier_key: str,
    out_dir: Path,
    patch: str | None,
    fetched_date: str | None,
    role_filter: str | None,
) -> Path:
    if role_filter:
        points = [p for p in points if p["role"] == role_filter]

    if not points:
        print("No data points after filtering.", file=sys.stderr)
        sys.exit(1)

    region_label = REGION_DISPLAY.get(region_key, region_key.title())
    tier_label   = RANK_DISPLAY.get(tier_key, tier_key.title())
    patch_str    = f"  •  Patch {patch}" if patch else ""
    date_str     = f"  •  {fetched_date}" if fetched_date else ""
    subtitle     = f"{region_label}  •  {tier_label}{patch_str}{date_str}"

    fig, ax = plt.subplots(figsize=(13, 8))
    fig.patch.set_facecolor("#1A1A2E")
    ax.set_facecolor("#16213E")

    # Reference lines
    all_picks = [p["pick_rate"] for p in points]
    avg_pick  = sum(all_picks) / len(all_picks)
    ax.axhline(50,       color="white",   linewidth=0.9, alpha=0.4, zorder=1)
    ax.axvline(avg_pick, color="#AAAAAA", linewidth=0.9, alpha=0.4, zorder=1, linestyle="--")

    # Scatter by role
    roles_present = sorted({p["role"] for p in points})
    for role in roles_present:
        rpts = [p for p in points if p["role"] == role]
        ax.scatter(
            [p["pick_rate"] for p in rpts],
            [p["win_rate"]  for p in rpts],
            color=ROLE_COLORS.get(role, "#AAAAAA"),
            s=70, zorder=3, label=ROLE_LABELS.get(role, role.title()),
            edgecolors="#1A1A2E", linewidths=0.6,
        )

    # Hero labels — simple offset, no external lib needed
    for p in points:
        ax.annotate(
            p["hero"],
            xy=(p["pick_rate"], p["win_rate"]),
            xytext=(4, 4),
            textcoords="offset points",
            fontsize=6.5,
            color="#DDDDDD",
            zorder=5,
        )

    ax.xaxis.set_major_formatter(ticker.FormatStrFormatter("%.1f%%"))
    ax.yaxis.set_major_formatter(ticker.FormatStrFormatter("%.1f%%"))
    ax.tick_params(colors="#CCCCCC", labelsize=9)
    ax.grid(color="#2A2A4A", linewidth=0.6, zorder=0)
    ax.set_axisbelow(True)
    for spine in ax.spines.values():
        spine.set_edgecolor("#2A2A4A")

    ax.set_xlabel("Pick Rate", color="#AAAAAA", fontsize=11)
    ax.set_ylabel("Win Rate",  color="#AAAAAA", fontsize=11)

    # Quadrant labels
    x_min, x_max = ax.get_xlim()
    y_min, y_max = ax.get_ylim()
    kw = dict(fontsize=8, alpha=0.35, color="white", va="center", ha="center", zorder=2)
    ax.text((avg_pick + x_max) / 2, (50 + y_max) / 2, "Popular & Strong",   **kw)
    ax.text((x_min + avg_pick) / 2, (50 + y_max) / 2, "Niche & Strong",     **kw)
    ax.text((avg_pick + x_max) / 2, (y_min + 50) / 2, "Popular & Weak",     **kw)
    ax.text((x_min + avg_pick) / 2, (y_min + 50) / 2, "Niche & Weak",       **kw)

    ax.legend(
        facecolor="#1A1A2E", edgecolor="#2A2A4A", labelcolor="#CCCCCC",
        fontsize=9, loc="lower right",
    )
    ax.set_title(
        f"Pick Rate vs Win Rate\n{subtitle}",
        color="white", fontsize=13, pad=12,
    )
    fig.tight_layout()

    out_dir.mkdir(parents=True, exist_ok=True)
    role_slug = f"_{role_filter}" if role_filter else ""
    filename  = f"scatter_{region_key}_{tier_key}{role_slug}.png"
    out_path  = out_dir / filename
    fig.savefig(out_path, dpi=150, facecolor=fig.get_facecolor())
    plt.close(fig)
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Scatter: pick rate vs win rate for all heroes")

    region_group = parser.add_mutually_exclusive_group()
    region_group.add_argument("--americas", action="store_true")
    region_group.add_argument("--asia",     action="store_true")
    region_group.add_argument("--europe",   action="store_true")

    parser.add_argument(
        "--rank", "--tier",
        metavar="RANK",
        choices=RANK_ORDER + ["all"],
        default="all",
        help="Rank tier to show (default: all). Choices: " + ", ".join(RANK_ORDER + ["all"]),
    )
    parser.add_argument("--role", metavar="ROLE", choices=["tank", "damage", "support"])
    parser.add_argument("--data", default="rates.json", metavar="FILE")
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
        region_key = None  # average all

    tier_key = args.rank

    points = build_points(rows, region_key, tier_key, hero_roles)

    region_display = region_key or "all"
    print(f"Plotting {len(points)} heroes  region={region_display}  tier={tier_key}")

    out_path = make_scatter(
        points, region_display, tier_key,
        Path(args.out), patch, fetched_date, args.role,
    )
    print(f"  {out_path}")


if __name__ == "__main__":
    main()
