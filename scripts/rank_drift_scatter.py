#!/usr/bin/env python3
"""
Scatter plot showing hero movement from Bronze → Grandmaster.
Each hero gets a start point (Bronze), an end point (GM), and an arrow between them.
Axes: pick rate (x) vs win rate (y).

Usage:
    python3 rank_drift_scatter.py                          # all regions averaged
    python3 rank_drift_scatter.py --region americas        # one region
    python3 rank_drift_scatter.py --role support           # filter by role
    python3 rank_drift_scatter.py --data other.json --out results/
"""

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent

import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
from matplotlib.lines import Line2D

ROLE_COLORS = {
    "tank":    "#5B9BD5",
    "damage":  "#E87722",
    "support": "#70AD47",
}

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


def _mean(vals: list) -> float | None:
    valid = [v for v in vals if v is not None]
    return sum(valid) / len(valid) if valid else None


def compute_endpoints(
    rows: list[dict],
    region: str | None,
    hero_roles: dict,
) -> list[dict]:
    ranked = [r for r in rows if r["tier"] in ("bronze", "grandmaster")]
    if region:
        ranked = [r for r in ranked if r["region"] == region]

    heroes = list(dict.fromkeys(r["hero"] for r in ranked))
    results = []
    for hero in heroes:
        bronze_rows = [r for r in ranked if r["hero"] == hero and r["tier"] == "bronze"]
        gm_rows     = [r for r in ranked if r["hero"] == hero and r["tier"] == "grandmaster"]

        b_pick = _mean([r["pick_rate"] for r in bronze_rows])
        b_win  = _mean([r["win_rate"]  for r in bronze_rows])
        g_pick = _mean([r["pick_rate"] for r in gm_rows])
        g_win  = _mean([r["win_rate"]  for r in gm_rows])

        if any(v is None for v in (b_pick, b_win, g_pick, g_win)):
            continue

        results.append({
            "hero":         hero,
            "role":         hero_roles.get(hero, "damage"),
            "bronze_pick":  b_pick,
            "bronze_win":   b_win,
            "gm_pick":      g_pick,
            "gm_win":       g_win,
        })
    return results


def make_chart(
    heroes: list[dict],
    region_key: str,
    out_dir: Path,
    patch: str | None,
    fetched_date: str | None,
    role_filter: str | None,
) -> Path:
    if role_filter:
        heroes = [h for h in heroes if h["role"] == role_filter]
    if not heroes:
        print("No data after filtering.", file=sys.stderr)
        sys.exit(1)

    region_label = REGION_DISPLAY.get(region_key, region_key.title())
    patch_str    = f"  •  Patch {patch}" if patch else ""
    date_str     = f"  •  {fetched_date}" if fetched_date else ""
    subtitle     = f"{region_label}  •  {INPUT_MODE}  •  Bronze → Grandmaster{patch_str}{date_str}"

    fig, ax = plt.subplots(figsize=(14, 9))
    fig.patch.set_facecolor("#1A1A2E")
    ax.set_facecolor("#16213E")

    # Reference lines at averages of the GM positions
    avg_pick = sum(h["gm_pick"] for h in heroes) / len(heroes)
    ax.axhline(50,       color="white",   linewidth=0.8, alpha=0.35, zorder=1)
    ax.axvline(avg_pick, color="#AAAAAA", linewidth=0.8, alpha=0.35, zorder=1, linestyle="--")

    for h in heroes:
        color = ROLE_COLORS.get(h["role"], "#AAAAAA")
        dx = h["gm_pick"]  - h["bronze_pick"]
        dy = h["gm_win"]   - h["bronze_win"]

        # Arrow from bronze → GM
        ax.annotate(
            "",
            xy=(h["gm_pick"],     h["gm_win"]),
            xytext=(h["bronze_pick"], h["bronze_win"]),
            arrowprops=dict(
                arrowstyle="-|>",
                color=color,
                lw=1.2,
                alpha=0.75,
                mutation_scale=10,
            ),
            zorder=3,
        )

        # Bronze dot (hollow)
        ax.scatter(
            h["bronze_pick"], h["bronze_win"],
            color="#1A1A2E", edgecolors=color, linewidths=1.4,
            s=38, zorder=4,
        )
        # GM dot (filled)
        ax.scatter(
            h["gm_pick"], h["gm_win"],
            color=color, s=50, zorder=5,
            edgecolors="#1A1A2E", linewidths=0.6,
        )

        # Label near GM end, offset away from arrow direction
        norm = (dx**2 + dy**2) ** 0.5 or 1
        ox = (dx / norm) * 8 + 3
        oy = (dy / norm) * 8 + 3
        ax.annotate(
            h["hero"],
            xy=(h["gm_pick"], h["gm_win"]),
            xytext=(ox, oy),
            textcoords="offset points",
            fontsize=6.5,
            color="#DDDDDD",
            zorder=6,
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
    kw = dict(fontsize=8, alpha=0.3, color="white", va="center", ha="center", zorder=2)
    ax.text((avg_pick + x_max) / 2, (50 + y_max) / 2, "Popular & Strong",  **kw)
    ax.text((x_min + avg_pick) / 2, (50 + y_max) / 2, "Niche & Strong",    **kw)
    ax.text((avg_pick + x_max) / 2, (y_min + 50) / 2, "Popular & Weak",    **kw)
    ax.text((x_min + avg_pick) / 2, (y_min + 50) / 2, "Niche & Weak",      **kw)

    # Legend: roles + bronze/gm dot explanation
    role_handles = [
        Line2D([0], [0], marker="o", color="w", markerfacecolor=ROLE_COLORS[r],
               markersize=7, label=r.title(), linewidth=0)
        for r in ("tank", "damage", "support")
    ]
    tier_handles = [
        Line2D([0], [0], marker="o", color="w", markerfacecolor="#1A1A2E",
               markeredgecolor="#AAAAAA", markeredgewidth=1.3,
               markersize=7, label="Bronze", linewidth=0),
        Line2D([0], [0], marker="o", color="w", markerfacecolor="#AAAAAA",
               markersize=7, label="Grandmaster", linewidth=0),
    ]
    ax.legend(
        handles=role_handles + tier_handles,
        facecolor="#1A1A2E", edgecolor="#2A2A4A", labelcolor="#CCCCCC",
        fontsize=9, loc="lower right",
    )

    ax.set_title(
        f"Pick Rate vs Win Rate — Bronze → Grandmaster Drift\n{subtitle}",
        color="white", fontsize=13, pad=12,
    )
    fig.tight_layout()

    out_dir.mkdir(parents=True, exist_ok=True)
    role_slug = f"_{role_filter}" if role_filter else ""
    region_slug = region_key.replace(" ", "_")
    out_path = out_dir / f"rank_drift_{region_slug}{role_slug}.png"
    fig.savefig(out_path, dpi=150, facecolor=fig.get_facecolor())
    plt.close(fig)
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Bronze→GM drift scatter")
    parser.add_argument("--region", choices=["americas", "asia", "europe"],
                        metavar="REGION", help="Region to show (default: average all). Choices: americas, asia, europe")
    parser.add_argument("--role", metavar="ROLE", choices=["tank", "damage", "support"])
    parser.add_argument("--data", default=str(_ROOT / "data" / "comp_mnk.json"), metavar="FILE")
    parser.add_argument("--out",  default=str(_ROOT / "outputs"),             metavar="DIR")
    args = parser.parse_args()

    payload      = load_data(args.data)
    rows         = payload["rows"]
    patch        = payload.get("patch_note")
    fetched_date = (payload.get("fetched_at") or "")[:10] or None
    hero_roles   = payload.get("hero_roles", {})

    region_key = args.region or "all"

    heroes = compute_endpoints(rows, args.region, hero_roles)
    print(f"Heroes with complete data: {len(heroes)}  region={region_key}")

    out_path = make_chart(heroes, region_key, Path(args.out), patch, fetched_date, args.role)
    print(f"  {out_path}")


if __name__ == "__main__":
    main()
