#!/usr/bin/env python3
"""
Scatter plot: pick rate (x) vs win rate (y), one point per hero.

Usage:
    python3 scatter.py                                    # all regions, all ranks
    python3 scatter.py --rank gold                        # gold tier only
    python3 scatter.py --region americas                  # Americas region only
    python3 scatter.py --region europe --rank master      # Europe, master tier
    python3 scatter.py --role support                     # only support heroes
    python3 scatter.py --mobile                           # portrait layout, larger text for phones
    python3 scatter.py --split role                       # one chart per role + combined
    python3 scatter.py --split region --rank gold         # one chart per region, gold rank
    python3 scatter.py --split rank --region americas     # one chart per rank, Americas
    python3 scatter.py --split role --normalise           # split by role with shared axes
    python3 scatter.py --data other.json                  # different data file
    python3 scatter.py --out results/                     # different output folder
"""

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent

import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
from adjustText import adjust_text

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

INPUT_MODE = "Mouse & Keyboard"

MOBILE_POINT_SIZE      = 200
MOBILE_LABEL_FONTSIZE  = 16
MOBILE_TICK_FONTSIZE   = 18
MOBILE_AXIS_FONTSIZE   = 18
MOBILE_TITLE_FONTSIZE  = 20
MOBILE_QUAD_FONTSIZE   = 14
MOBILE_LEGEND_FONTSIZE = 16

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


def _scatter_limits(vals: list, pad: float = 0.5) -> tuple[float, float]:
    return min(vals) - pad, max(vals) + pad


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
    mobile: bool = False,
    axis_limits: tuple | None = None,
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
    if mobile:
        subtitle = f"{region_label}  •  {INPUT_MODE}\n{tier_label}{patch_str}{date_str}"
    else:
        subtitle = f"{region_label}  •  {INPUT_MODE}  •  {tier_label}{patch_str}{date_str}"

    if mobile:
        figsize         = (9, 14)
        label_fontsize  = MOBILE_LABEL_FONTSIZE
        tick_fontsize   = MOBILE_TICK_FONTSIZE
        axis_fontsize   = MOBILE_AXIS_FONTSIZE
        title_fontsize  = MOBILE_TITLE_FONTSIZE
        quad_fontsize   = MOBILE_QUAD_FONTSIZE
        legend_fontsize = MOBILE_LEGEND_FONTSIZE
        point_size      = MOBILE_POINT_SIZE
    else:
        figsize         = (13, 8)
        label_fontsize  = 6.5
        tick_fontsize   = 9
        axis_fontsize   = 11
        title_fontsize  = 13
        quad_fontsize   = 8
        legend_fontsize = 9
        point_size      = 70

    fig, ax = plt.subplots(figsize=figsize)
    fig.patch.set_facecolor("#1A1A2E")
    ax.set_facecolor("#16213E")

    # Reference lines
    all_picks = [p["pick_rate"] for p in points]
    avg_pick  = sum(all_picks) / len(all_picks)
    ax.axhline(50,       color="white",   linewidth=0.9, alpha=0.4, zorder=1)
    ax.axvline(avg_pick, color="#AAAAAA", linewidth=0.9, alpha=0.4, zorder=1, linestyle="--")

    # Scatter by role
    roles_present = sorted({p["role"] for p in points})
    scatter_artists = []
    for role in roles_present:
        rpts = [p for p in points if p["role"] == role]
        sc = ax.scatter(
            [p["pick_rate"] for p in rpts],
            [p["win_rate"]  for p in rpts],
            color=ROLE_COLORS.get(role, "#AAAAAA"),
            s=point_size, zorder=3, label=ROLE_LABELS.get(role, role.title()),
            edgecolors="#1A1A2E", linewidths=0.6,
        )
        scatter_artists.append(sc)

    if axis_limits:
        ax.set_xlim(*axis_limits[0])
        ax.set_ylim(*axis_limits[1])

    # Hero labels — adjust_text repels from both other labels and the scatter points
    texts = [
        ax.text(p["pick_rate"], p["win_rate"], p["hero"],
                fontsize=label_fontsize, color="#DDDDDD", zorder=5)
        for p in points
    ]
    adjust_text(
        texts, ax=ax,
        add_objects=scatter_artists,
        arrowprops=dict(arrowstyle="-", color="#666666", lw=0.5, shrinkA=5),
    )

    ax.xaxis.set_major_formatter(ticker.FormatStrFormatter("%.1f%%"))
    ax.yaxis.set_major_formatter(ticker.FormatStrFormatter("%.1f%%"))
    ax.tick_params(colors="#CCCCCC", labelsize=tick_fontsize)
    ax.grid(color="#2A2A4A", linewidth=0.6, zorder=0)
    ax.set_axisbelow(True)
    for spine in ax.spines.values():
        spine.set_edgecolor("#2A2A4A")

    ax.set_xlabel("Pick Rate", color="#AAAAAA", fontsize=axis_fontsize)
    ax.set_ylabel("Win Rate",  color="#AAAAAA", fontsize=axis_fontsize)

    # Quadrant labels
    x_min, x_max = ax.get_xlim()
    y_min, y_max = ax.get_ylim()
    kw = dict(fontsize=quad_fontsize, alpha=0.35, color="white", va="center", ha="center", zorder=2)
    ax.text((avg_pick + x_max) / 2, (50 + y_max) / 2, "Popular & Strong",   **kw)
    ax.text((x_min + avg_pick) / 2, (50 + y_max) / 2, "Niche & Strong",     **kw)
    ax.text((avg_pick + x_max) / 2, (y_min + 50) / 2, "Popular & Weak",     **kw)
    ax.text((x_min + avg_pick) / 2, (y_min + 50) / 2, "Niche & Weak",       **kw)

    ax.legend(
        facecolor="#1A1A2E", edgecolor="#2A2A4A", labelcolor="#CCCCCC",
        fontsize=legend_fontsize, loc="lower right",
    )
    ax.set_title(
        f"Pick Rate vs Win Rate\n{subtitle}",
        color="white", fontsize=title_fontsize, pad=12,
    )
    fig.tight_layout()

    out_dir.mkdir(parents=True, exist_ok=True)
    role_slug   = f"_{role_filter}" if role_filter else ""
    mobile_slug = "_mobile" if mobile else ""
    filename    = f"scatter_{region_key}_{tier_key}{role_slug}{mobile_slug}.png"
    out_path    = out_dir / filename
    fig.savefig(out_path, dpi=150, facecolor=fig.get_facecolor())
    plt.close(fig)
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Scatter: pick rate vs win rate for all heroes")
    parser.add_argument("--region", choices=["americas", "asia", "europe"],
                        metavar="REGION", help="Region to show (default: average all). Choices: americas, asia, europe")
    parser.add_argument(
        "--rank",
        metavar="RANK",
        choices=RANK_ORDER + ["all"],
        default="all",
        help="Rank tier to show (default: all). Choices: " + ", ".join(RANK_ORDER + ["all"]),
    )
    parser.add_argument("--role", metavar="ROLE", choices=["tank", "damage", "support"])
    parser.add_argument("--mobile", action="store_true",
                        help="Portrait layout with larger text, optimised for phone screens")
    parser.add_argument("--split", metavar="BY", choices=["role", "region", "rank"],
                        help="Generate one chart per value of BY (role/region/rank) plus a combined chart")
    parser.add_argument("--normalise", "--normalize", action="store_true",
                        help="Pin all charts to the same axis limits (useful with --split)")
    parser.add_argument("--data", default=str(_ROOT / "data" / "rates.json"), metavar="FILE")
    parser.add_argument("--out",  default=str(_ROOT / "outputs"),             metavar="DIR")
    args = parser.parse_args()

    payload      = load_data(args.data)
    rows         = payload["rows"]
    patch        = payload.get("patch_note")
    fetched_date = (payload.get("fetched_at") or "")[:10] or None
    hero_roles   = payload.get("hero_roles", {})

    tier_key       = args.rank
    region_display = args.region or "all"

    if args.split:
        split_by = args.split

        if split_by == "role" and args.role:
            parser.error("--split role and --role cannot be used together")
        if split_by == "region" and args.region:
            parser.error("--split region and --region cannot be used together")
        if split_by == "rank" and args.rank != "all":
            parser.error("--split rank and --rank cannot be used together")

        # Build (points, region_key, tier_key, role_filter) for each chart
        charts = []
        if split_by == "role":
            base = build_points(rows, args.region, tier_key, hero_roles)
            for role in ["tank", "damage", "support"]:
                charts.append((base, region_display, tier_key, role))
            charts.append((base, region_display, tier_key, None))
        elif split_by == "region":
            for region in ["americas", "asia", "europe"]:
                pts = build_points(rows, region, tier_key, hero_roles)
                charts.append((pts, region, tier_key, args.role))
            pts = build_points(rows, None, tier_key, hero_roles)
            charts.append((pts, "all", tier_key, args.role))
        elif split_by == "rank":
            for rank in RANK_ORDER:
                pts = build_points(rows, args.region, rank, hero_roles)
                charts.append((pts, region_display, rank, args.role))
            pts = build_points(rows, args.region, "all", hero_roles)
            charts.append((pts, region_display, "all", args.role))

        axis_limits = None
        if args.normalise:
            all_picks, all_wins = [], []
            for pts, _rk, _tk, rf in charts:
                visible = [p for p in pts if p["role"] == rf] if rf else pts
                all_picks.extend(p["pick_rate"] for p in visible)
                all_wins.extend(p["win_rate"]   for p in visible)
            axis_limits = (_scatter_limits(all_picks), _scatter_limits(all_wins))

        print(f"Generating {len(charts)} charts  split={split_by}  region={region_display}"
              f"  tier={tier_key}  normalise={args.normalise}")
        for pts, rk, tk, rf in charts:
            out_path = make_scatter(
                pts, rk, tk, Path(args.out), patch, fetched_date, rf,
                mobile=args.mobile, axis_limits=axis_limits,
            )
            print(f"  {out_path}")
    else:
        points = build_points(rows, args.region, tier_key, hero_roles)

        axis_limits = None
        if args.normalise:
            all_picks = [p["pick_rate"] for p in points]
            all_wins  = [p["win_rate"]  for p in points]
            axis_limits = (_scatter_limits(all_picks), _scatter_limits(all_wins))

        print(f"Plotting {len(points)} heroes  region={region_display}  tier={tier_key}")
        out_path = make_scatter(
            points, region_display, tier_key,
            Path(args.out), patch, fetched_date, args.role,
            mobile=args.mobile, axis_limits=axis_limits,
        )
        print(f"  {out_path}")


if __name__ == "__main__":
    main()
