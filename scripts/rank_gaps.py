#!/usr/bin/env python3
"""
Bar charts: Bronze → Grandmaster gap in pick rate and win rate per hero.

Produces two separate charts — one for pick rate, one for win rate — each
ordered by its own stat value ascending.

Methods:
  linreg    (default) — OLS slope across all ranks (% pts per rank step)
  endpoint            — simple GM minus Bronze gap
  spearman            — Spearman rank correlation across all ranks

Usage:
    python3 rank_gaps.py                              # all regions, linreg
    python3 rank_gaps.py --method endpoint            # endpoint comparison
    python3 rank_gaps.py --method spearman            # rank correlation
    python3 rank_gaps.py --mobile                     # portrait, horizontal bars, larger text
    python3 rank_gaps.py --split role                 # one chart per role + combined
    python3 rank_gaps.py --split region               # one chart per region + combined
    python3 rank_gaps.py --region americas --role support
    python3 rank_gaps.py --data other.json --out results/
"""

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent

import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np

RANK_ORDER = ["bronze", "silver", "gold", "platinum", "diamond", "master", "grandmaster"]

ROLE_COLORS = {
    "tank":    "#5B9BD5",
    "damage":  "#E87722",
    "support": "#70AD47",
}

INPUT_MODE = "Mouse & Keyboard"

MOBILE_TICK_FONTSIZE  = 16
MOBILE_AXIS_FONTSIZE  = 18
MOBILE_TITLE_FONTSIZE = 18
MOBILE_ANNOT_FONTSIZE = 18

REGION_DISPLAY = {
    "americas": "Americas",
    "asia":     "Asia",
    "europe":   "Europe",
    "all":      "All Regions",
}

_STAT_META = {
    ("linreg", "pick"): {
        "y_label":    "Pick Rate Slope (% pts per rank)",
        "low_label":  "More popular at\nlow ranks",
        "high_label": "More popular at\nhigh ranks",
        "y_fmt":      "%+.3f%%",
        "chart_title": "Pick Rate Slope Across Ranks",
    },
    ("linreg", "win"): {
        "y_label":    "Win Rate Slope (% pts per rank)",
        "low_label":  "Stronger at\nlow ranks",
        "high_label": "Stronger at\nhigh ranks",
        "y_fmt":      "%+.3f%%",
        "chart_title": "Win Rate Slope Across Ranks",
    },
    ("endpoint", "pick"): {
        "y_label":    "Pick Rate Gap (GM − Bronze)",
        "low_label":  "More picked in Bronze",
        "high_label": "More picked in GM",
        "y_fmt":      "%+.1f%%",
        "chart_title": "Bronze → Grandmaster Pick Rate Gap",
    },
    ("endpoint", "win"): {
        "y_label":    "Win Rate Gap (GM − Bronze)",
        "low_label":  "Higher win rate in Bronze",
        "high_label": "Higher win rate in GM",
        "y_fmt":      "%+.1f%%",
        "chart_title": "Bronze → Grandmaster Win Rate Gap",
    },
    ("spearman", "pick"): {
        "y_label":    "Pick Rate Rank Correlation (Spearman ρ)",
        "low_label":  "Negatively correlated",
        "high_label": "Positively correlated",
        "y_fmt":      "%+.2f",
        "chart_title": "Pick Rate Rank Correlation",
    },
    ("spearman", "win"): {
        "y_label":    "Win Rate Rank Correlation (Spearman ρ)",
        "low_label":  "Negatively correlated",
        "high_label": "Positively correlated",
        "y_fmt":      "%+.2f",
        "chart_title": "Win Rate Rank Correlation",
    },
}


def load_data(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _mean(vals: list) -> float | None:
    valid = [v for v in vals if v is not None]
    return sum(valid) / len(valid) if valid else None


def _spearman(xs: list[float], ys: list[float]) -> float:
    rx = np.argsort(np.argsort(xs)).astype(float)
    ry = np.argsort(np.argsort(ys)).astype(float)
    n  = len(xs)
    d2 = np.sum((rx - ry) ** 2)
    return float(1 - 6 * d2 / (n * (n**2 - 1)))


def compute_gaps(
    rows: list[dict],
    region: str | None,
    hero_roles: dict,
    method: str,
) -> list[dict]:
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

        if method == "endpoint":
            bronze = next((p for p in points if p[0] == 0), None)
            gm     = next((p for p in points if p[0] == 6), None)
            if bronze is None or gm is None:
                continue
            pick_val = gm[1] - bronze[1]
            win_val  = gm[2] - bronze[2]

        elif method == "linreg":
            if len(points) < 2:
                continue
            xs = [p[0] for p in points]
            pick_val = float(np.polyfit(xs, [p[1] for p in points], 1)[0])
            win_val  = float(np.polyfit(xs, [p[2] for p in points], 1)[0])

        elif method == "spearman":
            if len(points) < 3:
                continue
            xs = [p[0] for p in points]
            pick_val = _spearman(xs, [p[1] for p in points])
            win_val  = _spearman(xs, [p[2] for p in points])

        else:
            raise ValueError(f"Unknown method: {method!r}")

        results.append({
            "hero":     hero,
            "role":     hero_roles.get(hero, "damage"),
            "pick_gap": pick_val,
            "win_gap":  win_val,
        })

    return results


def _make_single_chart(
    gaps: list[dict],
    stat: str,
    method: str,
    region_key: str,
    out_dir: Path,
    patch: str | None,
    fetched_date: str | None,
    role_filter: str | None,
    mobile: bool = False,
) -> Path:
    from matplotlib.patches import Patch

    meta        = _STAT_META[(method, stat)]
    gap_key     = f"{stat}_gap"
    sorted_gaps = sorted(gaps, key=lambda g: g[gap_key])

    heroes = [g["hero"]  for g in sorted_gaps]
    vals   = [g[gap_key] for g in sorted_gaps]
    roles  = [g["role"]  for g in sorted_gaps]

    n = len(heroes)

    region_label = REGION_DISPLAY.get(region_key, region_key.title())
    patch_str    = f"  •  Patch {patch}" if patch else ""
    date_str     = f"  •  {fetched_date}" if fetched_date else ""

    if mobile:
        subtitle       = f"{region_label}  •  {INPUT_MODE}\n{patch_str.lstrip('  •  ')}{date_str}".strip("\n •")
        tick_fontsize  = MOBILE_TICK_FONTSIZE
        axis_fontsize  = MOBILE_AXIS_FONTSIZE
        title_fontsize = MOBILE_TITLE_FONTSIZE
        annot_fontsize = MOBILE_ANNOT_FONTSIZE
        figsize        = (9, max(16, n * 0.45))
    else:
        subtitle       = f"{region_label}  •  {INPUT_MODE}{patch_str}{date_str}"
        tick_fontsize  = 9
        axis_fontsize  = 10
        title_fontsize = 13
        annot_fontsize = 7.5
        figsize        = (max(14, n * 0.38), 6)

    fig, ax = plt.subplots(figsize=figsize, layout="constrained")
    fig.patch.set_facecolor("#1A1A2E")
    ax.set_facecolor("#16213E")

    bar_colors = [ROLE_COLORS.get(r, "#AAAAAA") for r in roles]

    if mobile:
        y = np.arange(n)
        ax.barh(y, vals, color=bar_colors, height=0.7, zorder=3, edgecolor="#1A1A2E", linewidth=0.4)
        ax.axvline(0, color="#AAAAAA", linewidth=0.9, zorder=4)
        ax.xaxis.set_major_formatter(ticker.FormatStrFormatter(meta["y_fmt"]))
        ax.tick_params(axis="x", colors="#CCCCCC", labelsize=tick_fontsize, labelrotation=45)
        ax.tick_params(axis="y", left=False, labelleft=False)
        ax.grid(axis="x", color="#2A2A4A", linewidth=0.6, zorder=0)
        ax.set_axisbelow(True)
        for spine in ax.spines.values():
            spine.set_edgecolor("#2A2A4A")
        ax.set_xlabel(meta["y_label"], color="#AAAAAA", fontsize=axis_fontsize)

        pad = (max(vals) - min(vals)) * 0.01
        for i, (hero, val) in enumerate(zip(heroes, vals)):
            if val >= 0:
                ax.text(-pad, i, hero, va="center", ha="right", color="#CCCCCC",
                        fontsize=tick_fontsize, zorder=5, clip_on=False)
            else:
                ax.text(pad, i, hero, va="center", ha="left", color="#CCCCCC",
                        fontsize=tick_fontsize, zorder=5, clip_on=False)

        x_min, x_max = ax.get_xlim()
        kw = dict(fontsize=annot_fontsize, alpha=0.45, color="white", ha="center", zorder=2)
        ax.text(x_max * 0.75, n * 0.25, meta["low_label"],  rotation=0, va="center", **kw)
        ax.text(x_min * 0.75, n * 0.75, meta["high_label"], rotation=0, va="center", **kw)

        legend_loc = "lower right"
    else:
        x = np.arange(n)
        ax.bar(x, vals, color=bar_colors, width=0.7, zorder=3, edgecolor="#1A1A2E", linewidth=0.4)
        ax.axhline(0, color="#AAAAAA", linewidth=0.9, zorder=4)
        ax.yaxis.set_major_formatter(ticker.FormatStrFormatter(meta["y_fmt"]))
        ax.tick_params(axis="y", colors="#CCCCCC", labelsize=tick_fontsize)
        ax.grid(axis="y", color="#2A2A4A", linewidth=0.6, zorder=0)
        ax.set_axisbelow(True)
        for spine in ax.spines.values():
            spine.set_edgecolor("#2A2A4A")
        ax.set_ylabel(meta["y_label"], color="#AAAAAA", fontsize=axis_fontsize)

        y_min, y_max = ax.get_ylim()
        kw = dict(fontsize=annot_fontsize, alpha=0.45, color="white", va="center", zorder=2)
        ax.text(n * 0.15, y_min * 0.85, meta["low_label"],  **kw)
        ax.text(n * 0.85, y_max * 0.85, meta["high_label"], **kw)

        ax.set_xticks(x)
        ax.set_xticklabels(heroes, rotation=45, ha="right", color="#CCCCCC", fontsize=8)
        legend_loc = "upper right"

    roles_present = sorted(set(roles))
    if len(roles_present) > 1:
        legend_handles = [
            Patch(facecolor=ROLE_COLORS["tank"],    label="Tank"),
            Patch(facecolor=ROLE_COLORS["damage"],  label="Damage"),
            Patch(facecolor=ROLE_COLORS["support"], label="Support"),
        ]
        ax.legend(
            handles=legend_handles,
            facecolor="#1A1A2E", edgecolor="#2A2A4A", labelcolor="#CCCCCC",
            fontsize=9 if not mobile else 13, loc=legend_loc,
        )

    role_str = f"  •  {role_filter.title()}" if role_filter else ""
    fig.suptitle(
        f"{meta['chart_title']}{role_str}\n{subtitle}",
        color="white", fontsize=title_fontsize,
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    role_slug   = f"_{role_filter}" if role_filter else ""
    mobile_slug = "_mobile" if mobile else ""
    region_slug = region_key.replace(" ", "_")
    out_path    = out_dir / f"rank_gaps_{stat}_{method}_{region_slug}{role_slug}{mobile_slug}.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    return out_path


def make_charts(
    gaps: list[dict],
    method: str,
    region_key: str,
    out_dir: Path,
    patch: str | None,
    fetched_date: str | None,
    role_filter: str | None,
    mobile: bool = False,
) -> list[Path]:
    if role_filter:
        gaps = [g for g in gaps if g["role"] == role_filter]
    if not gaps:
        print("No data after filtering.", file=sys.stderr)
        sys.exit(1)

    return [
        _make_single_chart(gaps, stat, method, region_key, out_dir, patch, fetched_date, role_filter, mobile)
        for stat in ("pick", "win")
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="Rank gap bar charts")
    parser.add_argument("--method", default="linreg",
                        choices=["linreg", "endpoint", "spearman"],
                        help="Analysis method (default: linreg)")
    parser.add_argument("--region", choices=["americas", "asia", "europe"],
                        metavar="REGION", help="Region to show (default: average all). Choices: americas, asia, europe")
    parser.add_argument("--role", metavar="ROLE", choices=["tank", "damage", "support"])
    parser.add_argument("--mobile", action="store_true",
                        help="Portrait layout with horizontal bars and larger text, optimised for phone screens")
    parser.add_argument("--split", metavar="BY", choices=["role", "region"],
                        help="Generate one chart per value of BY (role/region) plus a combined chart")
    parser.add_argument("--data", default=str(_ROOT / "data" / "comp_mnk.json"), metavar="FILE")
    parser.add_argument("--out",  default=str(_ROOT / "outputs"),                metavar="DIR")
    args = parser.parse_args()

    if args.split == "role" and args.role:
        parser.error("--split role and --role cannot be used together")
    if args.split == "region" and args.region:
        parser.error("--split region and --region cannot be used together")

    payload      = load_data(args.data)
    rows         = payload["rows"]
    patch        = payload.get("patch_note")
    fetched_date = (payload.get("fetched_at") or "")[:10] or None
    hero_roles   = payload.get("hero_roles", {})

    out_dir = Path(args.out)

    if args.split:
        # Build list of (gaps, region_key, role_filter) for each chart
        charts = []
        if args.split == "role":
            base = compute_gaps(rows, args.region, hero_roles, args.method)
            region_key = args.region or "all"
            for role in ["tank", "damage", "support"]:
                charts.append((base, region_key, role))
            charts.append((base, region_key, None))
        elif args.split == "region":
            for region in ["americas", "asia", "europe"]:
                gaps = compute_gaps(rows, region, hero_roles, args.method)
                charts.append((gaps, region, args.role))
            gaps = compute_gaps(rows, None, hero_roles, args.method)
            charts.append((gaps, "all", args.role))

        print(f"Generating {len(charts) * 2} charts  split={args.split}  method={args.method}")
        for gaps, region_key, role_filter in charts:
            for out_path in make_charts(gaps, args.method, region_key, out_dir, patch, fetched_date, role_filter, args.mobile):
                print(f"  {out_path}")
    else:
        region_key = args.region or "all"
        gaps = compute_gaps(rows, args.region, hero_roles, args.method)
        print(f"Heroes with complete data: {len(gaps)}  region={region_key}  method={args.method}")

        for out_path in make_charts(gaps, args.method, region_key, out_dir, patch, fetched_date, args.role, args.mobile):
            print(f"  {out_path}")


if __name__ == "__main__":
    main()
