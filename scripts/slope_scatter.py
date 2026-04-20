#!/usr/bin/env python3
"""
Scatter plot: pick rate slope (x) vs win rate slope (y), one point per hero.
Slopes are linear regression across all ranks (% pts per rank step).

Usage:
    python3 slope_scatter.py                              # all regions
    python3 slope_scatter.py --region americas            # Americas region only
    python3 slope_scatter.py --region europe --mobile     # Europe, mobile layout
    python3 slope_scatter.py --role support               # only support heroes
    python3 slope_scatter.py --split role                 # one chart per role + combined
    python3 slope_scatter.py --split region               # one chart per region + combined
    python3 slope_scatter.py --data other.json --out results/
"""

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent

import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np
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


def load_data(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _mean(vals: list) -> float | None:
    valid = [v for v in vals if v is not None]
    return sum(valid) / len(valid) if valid else None


def _scatter_limits(vals: list, pad: float = 0.01) -> tuple[float, float]:
    if not vals:
        return -0.1, 0.1
    return min(vals) - pad, max(vals) + pad


def compute_slopes(
    rows: list[dict],
    region: str | None,
    hero_roles: dict,
) -> list[dict]:
    """
    Compute linear regression slopes for pick and win rate across all ranks.
    Returns one entry per hero.
    """
    all_rows = [r for r in rows if r["tier"] in RANK_ORDER]
    if region:
        all_rows = [r for r in all_rows if r["region"] == region]

    heroes = list(dict.fromkeys(r["hero"] for r in all_rows))
    results = []

    for hero in heroes:
        points = []
        for i, rank in enumerate(RANK_ORDER):
            rank_rows = [r for r in all_rows if r["hero"] == hero and r["tier"] == rank]
            pick = _mean([r["pick_rate"] for r in rank_rows])
            win  = _mean([r["win_rate"]  for r in rank_rows])
            if pick is not None and win is not None:
                points.append((i, pick, win))

        if len(points) < 2:
            continue

        xs = [p[0] for p in points]
        pick_slope = float(np.polyfit(xs, [p[1] for p in points], 1)[0])
        win_slope  = float(np.polyfit(xs, [p[2] for p in points], 1)[0])

        results.append({
            "hero": hero,
            "pick_slope": pick_slope,
            "win_slope": win_slope,
            "role": hero_roles.get(hero, "damage"),
        })

    return results


def make_scatter(
    points: list[dict],
    region_key: str,
    out_dir: Path,
    patch: str | None,
    fetched_date: str | None,
    role_filter: str | None,
    mobile: bool = False,
    axis_limits: tuple | None = None,
    explain: bool = False,
) -> Path:
    if role_filter:
        points = [p for p in points if p["role"] == role_filter]

    if not points:
        print("No data points after filtering.", file=sys.stderr)
        sys.exit(1)

    region_label = REGION_DISPLAY.get(region_key, region_key.title())
    patch_str    = f"  •  Patch {patch}" if patch else ""
    date_str     = f"  •  {fetched_date}" if fetched_date else ""

    if explain:
        if mobile:
            subtitle = f"{region_label}  •  {INPUT_MODE}\n{patch_str.lstrip('  •  ')}{date_str}".strip("\n •")
            subtitle += "\n\nMeasures how hero popularity & strength change across rank tiers"
        else:
            subtitle = f"{region_label}  •  {INPUT_MODE}  •  Measured across all rank tiers{patch_str}{date_str}"
    else:
        if mobile:
            subtitle = f"{region_label}  •  {INPUT_MODE}\n{patch_str.lstrip('  •  ')}{date_str}".strip("\n •")
        else:
            subtitle = f"{region_label}  •  {INPUT_MODE}{patch_str}{date_str}"

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

    # Reference lines at 0
    ax.axhline(0, color="white",   linewidth=0.9, alpha=0.4, zorder=1)
    ax.axvline(0, color="#AAAAAA", linewidth=0.9, alpha=0.4, zorder=1, linestyle="--")

    # Scatter by role
    roles_present = sorted({p["role"] for p in points})
    scatter_artists = []
    for role in roles_present:
        rpts = [p for p in points if p["role"] == role]
        sc = ax.scatter(
            [p["pick_slope"] for p in rpts],
            [p["win_slope"]  for p in rpts],
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
        ax.text(p["pick_slope"], p["win_slope"], p["hero"],
                fontsize=label_fontsize, color="#DDDDDD", zorder=5)
        for p in points
    ]
    adjust_text(
        texts, ax=ax,
        add_objects=scatter_artists,
        arrowprops=dict(arrowstyle="-", color="#666666", lw=0.5, shrinkA=5),
    )

    ax.xaxis.set_major_formatter(ticker.FormatStrFormatter("%+.2f%%"))
    ax.yaxis.set_major_formatter(ticker.FormatStrFormatter("%+.2f%%"))
    ax.tick_params(colors="#CCCCCC", labelsize=tick_fontsize)
    ax.grid(color="#2A2A4A", linewidth=0.6, zorder=0)
    ax.set_axisbelow(True)
    for spine in ax.spines.values():
        spine.set_edgecolor("#2A2A4A")

    ax.set_xlabel("Pick Rate Slope (% pts per rank)", color="#AAAAAA", fontsize=axis_fontsize)
    ax.set_ylabel("Win Rate Slope (% pts per rank)",  color="#AAAAAA", fontsize=axis_fontsize)

    if explain:
        # Axis direction labels positioned on either side of the midlines, closer to edges
        x_min, x_max = ax.get_xlim()
        y_min, y_max = ax.get_ylim()
        x_range = x_max - x_min
        y_range = y_max - y_min

        axis_label_kw = dict(color="#999999", fontsize=8, weight="bold", zorder=3)

        # X-axis: labels on either side of x=0 at y=0
        ax.text(x_min + x_range * 0.1, 0, "← more popular at low ranks", ha="center", va="bottom", **axis_label_kw)
        ax.text(x_max - x_range * 0.1, 0, "more popular at high ranks →", ha="center", va="bottom", **axis_label_kw)

        # Y-axis: labels on either side of y=0 at x=0
        ax.text(0, y_min + y_range * 0.1, "stronger at\nlow ranks\n↓", ha="center", va="center", **axis_label_kw)
        ax.text(0, y_max - y_range * 0.1, "↑\nstronger at\nhigh ranks", ha="center", va="center", **axis_label_kw)

    # Quadrant labels
    x_min, x_max = ax.get_xlim()
    y_min, y_max = ax.get_ylim()
    kw = dict(fontsize=quad_fontsize, alpha=0.35, color="white", va="center", ha="center", zorder=2)

    if explain:
        # Catchy labels for explained mode
        ax.text((0 + x_max) / 2, (0 + y_max) / 2, "Skill Scaling",      **kw)
        ax.text((x_min + 0) / 2, (0 + y_max) / 2, "OTP Bait",           **kw)
        ax.text((0 + x_max) / 2, (y_min + 0) / 2, "Noob Stompers",      **kw)
        ax.text((x_min + 0) / 2, (y_min + 0) / 2, "Training Wheels",    **kw)
    else:
        # Verbose labels for default mode
        ax.text((0 + x_max) / 2, (0 + y_max) / 2, "Popular at high ranks\nStronger at high ranks",   **kw)
        ax.text((x_min + 0) / 2, (0 + y_max) / 2, "Popular at low ranks\nStronger at high ranks",     **kw)
        ax.text((0 + x_max) / 2, (y_min + 0) / 2, "Popular at high ranks\nStronger at low ranks",     **kw)
        ax.text((x_min + 0) / 2, (y_min + 0) / 2, "Popular at low ranks\nStronger at low ranks",       **kw)

    if len(roles_present) > 1:
        ax.legend(
            facecolor="#1A1A2E", edgecolor="#2A2A4A", labelcolor="#CCCCCC",
            fontsize=legend_fontsize, loc="lower right",
        )
    ax.set_title(
        f"Pick Rate Slope vs Win Rate Slope\n{subtitle}",
        color="white", fontsize=title_fontsize, pad=12,
    )
    fig.tight_layout()

    out_dir.mkdir(parents=True, exist_ok=True)
    role_slug   = f"_{role_filter}" if role_filter else ""
    mobile_slug = "_mobile" if mobile else ""
    filename    = f"slope_scatter_{region_key}{role_slug}{mobile_slug}.png"
    out_path    = out_dir / filename
    fig.savefig(out_path, dpi=150, facecolor=fig.get_facecolor())
    plt.close(fig)
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Slope scatter: pick rate slope vs win rate slope for all heroes")
    parser.add_argument("--region", choices=["americas", "asia", "europe"],
                        metavar="REGION", help="Region to show (default: average all). Choices: americas, asia, europe")
    parser.add_argument("--role", metavar="ROLE", choices=["tank", "damage", "support"])
    parser.add_argument("--mobile", action="store_true",
                        help="Portrait layout with larger text, optimised for phone screens")
    parser.add_argument("--split", metavar="BY", choices=["role", "region"],
                        help="Generate one chart per value of BY (role/region) plus a combined chart")
    parser.add_argument("--normalise", "--normalize", action="store_true",
                        help="Pin all charts to the same axis limits (useful with --split)")
    parser.add_argument("--explain", action="store_true",
                        help="Add explanatory labels and subtitle to make the data more accessible")
    parser.add_argument("--data", default=str(_ROOT / "data" / "comp_mnk.json"), metavar="FILE")
    parser.add_argument("--out",  default=str(_ROOT / "outputs"),             metavar="DIR")
    args = parser.parse_args()

    payload      = load_data(args.data)
    rows         = payload["rows"]
    patch        = payload.get("patch_note")
    fetched_date = (payload.get("fetched_at") or "")[:10] or None
    hero_roles   = payload.get("hero_roles", {})

    region_display = args.region or "all"

    if args.split:
        split_by = args.split

        if split_by == "role" and args.role:
            parser.error("--split role and --role cannot be used together")
        if split_by == "region" and args.region:
            parser.error("--split region and --region cannot be used together")

        # Build (points, region_key, role_filter) for each chart
        charts = []
        if split_by == "role":
            base = compute_slopes(rows, args.region, hero_roles)
            for role in ["tank", "damage", "support"]:
                charts.append((base, region_display, role))
            charts.append((base, region_display, None))
        elif split_by == "region":
            for region in ["americas", "asia", "europe"]:
                pts = compute_slopes(rows, region, hero_roles)
                charts.append((pts, region, args.role))
            pts = compute_slopes(rows, None, hero_roles)
            charts.append((pts, "all", args.role))

        axis_limits = None
        if args.normalise:
            all_picks, all_wins = [], []
            for pts, _rk, rf in charts:
                visible = [p for p in pts if p["role"] == rf] if rf else pts
                all_picks.extend(p["pick_slope"] for p in visible)
                all_wins.extend(p["win_slope"]   for p in visible)
            axis_limits = (_scatter_limits(all_picks), _scatter_limits(all_wins))

        print(f"Generating {len(charts)} charts  split={split_by}  region={region_display}")
        for pts, rk, rf in charts:
            out_path = make_scatter(
                pts, rk, Path(args.out), patch, fetched_date, rf,
                mobile=args.mobile, axis_limits=axis_limits, explain=args.explain,
            )
            print(f"  {out_path}")
    else:
        points = compute_slopes(rows, args.region, hero_roles)

        axis_limits = None
        if args.normalise:
            all_picks = [p["pick_slope"] for p in points]
            all_wins  = [p["win_slope"]  for p in points]
            axis_limits = (_scatter_limits(all_picks), _scatter_limits(all_wins))

        print(f"Plotting {len(points)} heroes  region={region_display}")
        out_path = make_scatter(
            points, region_display, Path(args.out), patch, fetched_date, args.role,
            mobile=args.mobile, axis_limits=axis_limits, explain=args.explain,
        )
        print(f"  {out_path}")


if __name__ == "__main__":
    main()
