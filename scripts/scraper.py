#!/usr/bin/env python3
"""
Scrapes hero pick/win rates from overwatch.blizzard.com/en-us/rates/
across all tier × region combinations via the background JSON API.

Usage:
    python3 scraper.py                            # comp + mnk, all tiers/regions
    python3 scraper.py --mode qp                  # quickplay (no tier breakdown)
    python3 scraper.py --input controller         # controller input method
    python3 scraper.py --maps all                 # one file per map → data/maps/comp_mnk/
    python3 scraper.py --maps kings-row           # one specific map
    python3 scraper.py --no-cache                 # ignore cached responses
    python3 scraper.py --out myfile.json          # custom output path (single-file modes)
"""

import argparse
import json
import re
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).parent.parent

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://overwatch.blizzard.com/en-us/rates/"
API_URL  = "https://overwatch.blizzard.com/en-us/rates/data/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "X-Requested-With": "XMLHttpRequest",
    "Accept-Language": "en-US,en;q=0.9",
}

TIERS   = ["All", "Bronze", "Silver", "Gold", "Platinum", "Diamond", "Master", "Grandmaster"]
REGIONS = ["Americas", "Asia", "Europe"]

GAME_MODES    = {"comp": "2", "qp": "0"}
INPUT_METHODS = {"mnk": "PC", "controller": "Console"}

MAPS = {
    "antarctic-peninsula":  "Antarctic Peninsula",
    "busan":                "Busan",
    "ilios":                "Ilios",
    "lijiang-tower":        "Lijiang Tower",
    "nepal":                "Nepal",
    "oasis":                "Oasis",
    "samoa":                "Samoa",
    "circuit-royal":        "Circuit Royal",
    "dorado":               "Dorado",
    "havana":               "Havana",
    "junkertown":           "Junkertown",
    "rialto":               "Rialto",
    "route-66":             "Route 66",
    "shambali-monastery":   "Shambali Monastery",
    "watchpoint-gibraltar": "Watchpoint: Gibraltar",
    "aatlis":               "Aatlis",
    "new-junk-city":        "New Junk City",
    "suravasa":             "Suravasa",
    "blizzard-world":       "Blizzard World",
    "eichenwalde":          "Eichenwalde",
    "hollywood":            "Hollywood",
    "kings-row":            "King's Row",
    "midtown":              "Midtown",
    "numbani":              "Numbani",
    "paraiso":              "Paraíso",
    "colosseo":             "Colosseo",
    "esperanca":            "Esperança",
    "new-queen-street":     "New Queen Street",
    "runasapi":             "Runasapi",
}

SLEEP_SEC   = 1.2
MAX_RETRIES = 4

# ── Patch tracking ────────────────────────────────────────────────────────────

def _get_previous_patch() -> str | None:
    """Read the previously recorded patch version."""
    patch_file = _ROOT / ".patch_version"
    if patch_file.exists():
        return patch_file.read_text(encoding="utf-8").strip()
    return None


def _save_patch_version(patch: str | None) -> None:
    """Save the current patch version."""
    if patch:
        patch_file = _ROOT / ".patch_version"
        patch_file.write_text(patch, encoding="utf-8")


def _archive_data_for_patch(old_patch: str) -> None:
    """Move data folder contents to releases/patch_OLDPATCH."""
    data_dir = _ROOT / "data"
    if not data_dir.exists():
        return

    releases_dir = _ROOT / "releases" / f"patch_{old_patch}"
    releases_dir.mkdir(parents=True, exist_ok=True)

    for item in data_dir.iterdir():
        if item.name != "maps":
            dest = releases_dir / item.name
            if dest.exists():
                shutil.rmtree(dest) if item.is_dir() else dest.unlink()
            shutil.move(str(item), str(dest))

    maps_dir = data_dir / "maps"
    if maps_dir.exists():
        maps_dest = releases_dir / "maps"
        if maps_dest.exists():
            shutil.rmtree(maps_dest)
        shutil.move(str(maps_dir), str(maps_dest))


# ── Cache paths ───────────────────────────────────────────────────────────────

def _cache_subdir(mode: str, input_method: str, map_slug: str | None) -> Path:
    folder = f"{mode}_{input_method}"
    if map_slug:
        return _ROOT / "cache" / "maps" / folder
    return _ROOT / "cache" / folder


def _cache_path(mode: str, input_method: str, map_slug: str | None, tier: str, region: str) -> Path:
    base = _cache_subdir(mode, input_method, map_slug)
    if map_slug:
        key = f"{map_slug}_{region}".lower().replace(" ", "_")
    else:
        key = f"{region}_{tier}".lower().replace(" ", "_")
    return base / f"api_{key}.json"


# ── Fetching ──────────────────────────────────────────────────────────────────

def fetch_rates(
    tier: str,
    region: str,
    mode: str,
    input_method: str,
    map_slug: str | None,
    use_cache: bool = True,
) -> tuple[dict, bool]:
    """Returns (data, fetched_from_network)."""
    path = _cache_path(mode, input_method, map_slug, tier, region)
    if use_cache and path.exists():
        return json.loads(path.read_text()), False

    params: dict = {
        "rq":     GAME_MODES[mode],
        "tier":   tier,
        "region": region,
        "input":  INPUT_METHODS[input_method],
    }
    if map_slug:
        params["map"] = map_slug

    delay = 2.0
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(API_URL, headers=HEADERS, params=params, timeout=15)
            if resp.status_code == 429 or resp.status_code >= 500:
                print(f"    HTTP {resp.status_code}, retry {attempt}/{MAX_RETRIES} in {delay:.0f}s")
                time.sleep(delay)
                delay *= 2
                continue
            resp.raise_for_status()
            data = resp.json()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data, indent=2))
            return data, True
        except requests.RequestException as exc:
            if attempt == MAX_RETRIES:
                raise
            print(f"    Error: {exc}, retry {attempt}/{MAX_RETRIES} in {delay:.0f}s")
            time.sleep(delay)
            delay *= 2

    raise RuntimeError(f"Failed to fetch tier={tier!r} region={region!r} after {MAX_RETRIES} retries")


def fetch_page_html(use_cache: bool = True) -> str:
    path = _ROOT / "cache" / "default.html"
    if use_cache and path.exists():
        return path.read_text(encoding="utf-8")
    resp = requests.get(
        BASE_URL,
        headers={**HEADERS, "X-Requested-With": None},
        timeout=15,
    )
    resp.raise_for_status()
    path.write_bytes(resp.content)
    time.sleep(SLEEP_SEC)
    return resp.text


# ── Parsing ───────────────────────────────────────────────────────────────────

def parse_patch_note(html: str) -> str | None:
    m = re.search(r'\d+\.\d+\.\d+', html)
    return m.group(0) if m else None


def parse_rows(
    data: dict,
    tier: str,
    region: str,
    map_slug: str | None = None,
) -> tuple[list[dict], dict[str, str]]:
    """Returns (rows, {hero_name: role})."""
    rows, roles = [], {}
    for entry in data.get("rates", []):
        cells    = entry.get("cells", {})
        hero_obj = entry.get("hero") or {}
        pick = cells.get("pickrate")
        win  = cells.get("winrate")
        name = cells.get("name") or entry.get("id", "")

        row: dict = {
            "region":    region.lower(),
            "hero":      name,
            "pick_rate": None if (pick is None or pick < 0) else pick,
            "win_rate":  None if (win  is None or win  < 0) else win,
        }
        if not map_slug:
            row["tier"] = tier.lower()

        rows.append(row)
        if name and hero_obj.get("role"):
            roles[name] = hero_obj["role"].lower()

    return rows, roles


def validate(data: dict, expected_tier: str, expected_region: str) -> None:
    sel = data.get("selected", {})
    if sel.get("tier") != expected_tier:
        print(f"  WARNING: expected tier={expected_tier!r}, got {sel.get('tier')!r}")
    if sel.get("region") != expected_region:
        print(f"  WARNING: expected region={expected_region!r}, got {sel.get('region')!r}")


# ── Output ────────────────────────────────────────────────────────────────────

def _write_output(
    all_rows: list[dict],
    hero_roles: dict[str, str],
    patch: str | None,
    out_path: str,
    extra_meta: dict | None = None,
) -> None:
    output: dict = {
        "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "patch_note": patch,
        "hero_roles": dict(sorted(hero_roles.items())),
    }
    if extra_meta:
        output.update(extra_meta)
    output["rows"] = all_rows
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(json.dumps(output, indent=2), encoding="utf-8")


def _derive_out_path(mode: str, input_method: str, map_slug: str | None) -> str:
    if map_slug:
        return str(_ROOT / "data" / "maps" / f"{mode}_{input_method}" / f"{map_slug}.json")
    return str(_ROOT / "data" / f"{mode}_{input_method}.json")


# ── Scrape routines ───────────────────────────────────────────────────────────

def scrape_standard(mode: str, input_method: str, use_cache: bool, patch: str | None, out_path: str) -> None:
    """Scrape all tiers × regions for a standard (non-map) dataset."""
    tiers = TIERS if mode == "comp" else ["All"]
    total = len(tiers) * len(REGIONS)
    all_rows: list[dict] = []
    hero_roles: dict[str, str] = {}
    done = 0

    for region in REGIONS:
        for tier in tiers:
            done += 1
            print(f"[{done:2d}/{total}] tier={tier:<12s} region={region}")
            data, from_network = fetch_rates(tier, region, mode, input_method, None, use_cache)
            validate(data, tier, region)
            rows, roles = parse_rows(data, tier, region)
            all_rows.extend(rows)
            hero_roles.update(roles)
            if from_network:
                time.sleep(SLEEP_SEC)

    _write_output(all_rows, hero_roles, patch, out_path)
    print(f"\nWrote {len(all_rows)} rows to {out_path}")
    print(f"  ({len(tiers)} tiers × {len(REGIONS)} regions × ~{len(all_rows) // total} heroes)")


def scrape_map(
    map_slug: str,
    mode: str,
    input_method: str,
    use_cache: bool,
    patch: str | None,
    out_path: str,
) -> None:
    """Scrape all regions for a single map (no tier breakdown)."""
    all_rows: list[dict] = []
    hero_roles: dict[str, str] = {}

    for i, region in enumerate(REGIONS, 1):
        print(f"[{i}/{len(REGIONS)}] map={map_slug:<25s} region={region}")
        data, from_network = fetch_rates("All", region, mode, input_method, map_slug, use_cache)
        rows, roles = parse_rows(data, "All", region, map_slug)
        all_rows.extend(rows)
        hero_roles.update(roles)
        if from_network:
            time.sleep(SLEEP_SEC)

    map_name = MAPS.get(map_slug, map_slug)
    _write_output(all_rows, hero_roles, patch, out_path, {"map": map_name})
    print(f"  Wrote {len(all_rows)} rows to {out_path}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape Overwatch hero rates")
    parser.add_argument(
        "--mode", choices=["comp", "qp"], default="comp",
        help="Game mode: comp (default) or qp (quickplay)",
    )
    parser.add_argument(
        "--input", choices=["mnk", "controller"], default="mnk", dest="input_method",
        help="Input method: mnk (default) or controller",
    )
    parser.add_argument(
        "--maps", metavar="MAP",
        help=(
            "Map to scrape, or 'all' to generate one file per map. "
            f"Available: {', '.join(MAPS)}"
        ),
    )
    parser.add_argument("--no-cache", action="store_true", help="Ignore cached responses")
    parser.add_argument(
        "--out", metavar="FILE",
        help="Output file path (auto-derived if omitted; ignored when --maps all)",
    )
    args = parser.parse_args()

    use_cache    = not args.no_cache
    mode         = args.mode
    input_method = args.input_method

    print("Fetching page for patch version...")
    html  = fetch_page_html(use_cache=use_cache)
    patch = parse_patch_note(html)
    print(f"  Patch: {patch}\n")

    previous_patch = _get_previous_patch()
    if previous_patch and patch and previous_patch != patch:
        print(f"Patch incremented from {previous_patch} to {patch}")
        print(f"Archiving previous data to releases/patch_{previous_patch}/...")
        _archive_data_for_patch(previous_patch)
        print()

    _save_patch_version(patch)

    if args.maps:
        if args.maps == "all":
            if args.out:
                parser.error("--out cannot be used with --maps all (one file is written per map)")
            for slug in MAPS:
                scrape_map(slug, mode, input_method, use_cache, patch,
                           _derive_out_path(mode, input_method, slug))
        else:
            slug = args.maps
            if slug not in MAPS:
                print(
                    f"Unknown map {slug!r}. Use 'all' or one of:\n  {', '.join(MAPS)}",
                    file=sys.stderr,
                )
                sys.exit(1)
            scrape_map(slug, mode, input_method, use_cache, patch,
                       args.out or _derive_out_path(mode, input_method, slug))
    else:
        scrape_standard(mode, input_method, use_cache, patch,
                        args.out or _derive_out_path(mode, input_method, None))


if __name__ == "__main__":
    main()
