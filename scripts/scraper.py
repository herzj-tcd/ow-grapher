#!/usr/bin/env python3
"""
Scrapes hero pick/win rates from overwatch.blizzard.com/en-us/rates/
across all tier × region combinations via the background JSON API.

Usage:
    python3 scraper.py                  # scrape everything, write rates.json
    python3 scraper.py --no-cache       # ignore cached responses
    python3 scraper.py --out myfile.json
"""

import argparse
import json
import re
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

TIERS = ["All", "Bronze", "Silver", "Gold", "Platinum", "Diamond", "Master", "Grandmaster"]
REGIONS = ["Americas", "Asia", "Europe"]

SLEEP_SEC = 1.2
MAX_RETRIES = 4


# ── Fetching ──────────────────────────────────────────────────────────────────

def _cache_path(tier: str, region: str) -> Path:
    key = f"{region}_{tier}".lower().replace(" ", "_")
    return _ROOT / "cache" / f"api_{key}.json"


def fetch_rates(tier: str, region: str, use_cache: bool = True) -> dict:
    path = _cache_path(tier, region)
    if use_cache and path.exists():
        return json.loads(path.read_text())

    params = {"rq": "2", "tier": tier, "region": region}
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
            path.write_text(json.dumps(data, indent=2))
            return data
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
        headers={**HEADERS, "X-Requested-With": None},  # normal page request
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


def parse_rows(data: dict, tier: str, region: str) -> tuple[list[dict], dict[str, str]]:
    """Returns (rows, {hero_name: role}) — roles collected once, not repeated per row."""
    rows, roles = [], {}
    for entry in data.get("rates", []):
        cells    = entry.get("cells", {})
        hero_obj = entry.get("hero") or {}
        pick = cells.get("pickrate")
        win  = cells.get("winrate")
        name = cells.get("name") or entry.get("id", "")
        rows.append({
            "region":    region.lower(),
            "tier":      tier.lower(),
            "hero":      name,
            "pick_rate": None if (pick is None or pick < 0) else pick,
            "win_rate":  None if (win  is None or win  < 0) else win,
        })
        if name and hero_obj.get("role"):
            roles[name] = hero_obj["role"].lower()
    return rows, roles


def validate(data: dict, expected_tier: str, expected_region: str) -> None:
    sel = data.get("selected", {})
    if sel.get("tier") != expected_tier:
        print(f"  WARNING: expected tier={expected_tier!r}, got {sel.get('tier')!r}")
    if sel.get("region") != expected_region:
        print(f"  WARNING: expected region={expected_region!r}, got {sel.get('region')!r}")


# ── Main ──────────────────────────────────────────────────────────────────────

def scrape(use_cache: bool = True, out_path: str | None = None) -> None:
    if out_path is None:
        out_path = str(_ROOT / "data" / "rates.json")
    (_ROOT / "cache").mkdir(exist_ok=True)

    print("Fetching page for patch version...")
    html = fetch_page_html(use_cache=use_cache)
    patch = parse_patch_note(html)
    print(f"  Patch: {patch}")

    total = len(TIERS) * len(REGIONS)
    all_rows: list[dict] = []
    hero_roles: dict[str, str] = {}
    done = 0

    for region in REGIONS:
        for tier in TIERS:
            done += 1
            print(f"[{done:2d}/{total}] tier={tier:<12s} region={region}")
            data = fetch_rates(tier, region, use_cache=use_cache)
            validate(data, tier, region)
            rows, roles = parse_rows(data, tier, region)
            all_rows.extend(rows)
            hero_roles.update(roles)
            if not _cache_path(tier, region).exists():
                time.sleep(SLEEP_SEC)

    output = {
        "fetched_at":  datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "patch_note":  patch,
        "hero_roles":  dict(sorted(hero_roles.items())),
        "rows":        all_rows,
    }

    Path(out_path).write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(f"\nWrote {len(all_rows)} rows to {out_path}")
    print(f"  ({len(TIERS)} tiers × {len(REGIONS)} regions × ~{len(all_rows)//total} heroes)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape Overwatch hero rates")
    parser.add_argument("--no-cache", action="store_true", help="Ignore cached responses")
    parser.add_argument("--out", default=str(_ROOT / "data" / "rates.json"), help="Output file (default: data/rates.json)")
    args = parser.parse_args()

    scrape(use_cache=not args.no_cache, out_path=args.out)


if __name__ == "__main__":
    main()
