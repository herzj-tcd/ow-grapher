#!/usr/bin/env python3
"""
Regenerate all current graphs and publish them to releases/current/.

To add a new graph type:
  1. Write a job function: (data_path: str, tmp_dir: Path) -> list[(src: Path, dest_name: str)]
  2. Append it to JOBS as ("subfolder_name", your_function).
"""

import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

DATA_FILE = "data/rates.json"
RELEASES_DIR = Path("releases/current")


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------

def job_rank_curves(data_path: str, tmp_dir: Path) -> list[tuple[Path, str]]:
    import hero_rank_curves as hrc

    with open(data_path, encoding="utf-8") as f:
        payload = json.load(f)

    rows = payload["rows"]
    patch = payload.get("patch_note")
    fetched_date = (payload.get("fetched_at") or "")[:10] or None

    filtered_rows, region_key = hrc.filter_region(rows, None)  # average all regions
    heroes = list(dict.fromkeys(r["hero"] for r in rows if r["tier"] != "all"))

    all_series = [hrc.compute_series(filtered_rows, h) for h in heroes]
    all_picks  = [v for s in all_series for v in s["pick"] if v is not None]
    all_wins   = [v for s in all_series for v in s["win"]  if v is not None]
    y_limits   = (hrc._axis_limits(all_picks), hrc._axis_limits(all_wins))

    results = []
    for hero, series in zip(heroes, all_series):
        src = hrc.make_graph(
            hero, series, region_key, tmp_dir, patch, fetched_date,
            stacked=True, y_limits=y_limits,
        )
        slug = hero.lower().replace(" ", "_").replace(":", "")
        results.append((src, f"{slug}.png"))
    return results


# Add new jobs here: ("subfolder", function)
JOBS: list[tuple[str, object]] = [
    ("rank_curves", job_rank_curves),
]


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_job(subfolder: str, fn, data_path: str) -> int:
    out_dir = RELEASES_DIR / subfolder
    tmp_dir = out_dir / "_tmp"
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        pairs = fn(data_path, tmp_dir)
        for src, dest_name in pairs:
            shutil.move(str(src), out_dir / dest_name)
    finally:
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir)

    print(f"  [{subfolder}] {len(pairs)} file(s) → {out_dir}/")
    return len(pairs)


def main() -> None:
    data_path = DATA_FILE
    if not Path(data_path).exists():
        print(f"Error: data file {data_path!r} not found.", file=sys.stderr)
        sys.exit(1)

    print(f"Updating graphs from {data_path} → {RELEASES_DIR}/\n")
    total = sum(run_job(sub, fn, data_path) for sub, fn in JOBS)
    print(f"\nDone. {total} file(s) total.")


if __name__ == "__main__":
    main()
