"""Fetch daily weather for every Maharashtra district from the Open-Meteo archive (ERA5).

One consistent source for 1997-2025, replacing the two disagreeing rainfall files
(Teammate B 1997-2014 and Teammate A 2010-2025). Coordinates come from
data/processed/districts.csv (OSM Nominatim district headquarters).

Output: data/raw/open_meteo_archive_1997_2025/<District>.json (one file per district,
unchanged API response). Re-running skips files that already exist.
"""

import csv
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DISTRICTS_CSV = REPO_ROOT / "data" / "processed" / "districts.csv"
OUT_DIR = REPO_ROOT / "data" / "raw" / "open_meteo_archive_1997_2025"
API = "https://archive-api.open-meteo.com/v1/archive"
START, END = "1997-01-01", "2025-12-31"
DAILY = [
    "precipitation_sum",
    "et0_fao_evapotranspiration",
    "temperature_2m_max",
    "temperature_2m_min",
    "relative_humidity_2m_mean",
]


def fetch(latitude: str, longitude: str) -> dict:
    query = urllib.parse.urlencode({
        "latitude": latitude,
        "longitude": longitude,
        "start_date": START,
        "end_date": END,
        "daily": ",".join(DAILY),
        "timezone": "Asia/Kolkata",
    })
    request = urllib.request.Request(f"{API}?{query}", headers={"User-Agent": "AgriPulse-data-prep/1.0"})
    with urllib.request.urlopen(request, timeout=90) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with DISTRICTS_CSV.open(encoding="utf-8", newline="") as csv_file:
        districts = list(csv.DictReader(csv_file))
    failed = []
    for row in districts:
        name = row["district"]
        target = OUT_DIR / f"{name.replace(' ', '_')}.json"
        if target.exists() and target.stat().st_size > 1000:
            continue
        for attempt in range(1, 5):
            try:
                data = fetch(row["latitude"], row["longitude"])
                days = len(data["daily"]["time"])
                if days < 10_000:
                    raise ValueError(f"only {days} days returned")
                target.write_text(json.dumps(data), encoding="utf-8")
                print(f"[OK] {name}: {days} days")
                break
            except (urllib.error.URLError, TimeoutError, ValueError, KeyError) as exc:
                print(f"[RETRY {attempt}] {name}: {exc}")
                time.sleep(5 * attempt)
        else:
            failed.append(name)
        time.sleep(1.5)
    if failed:
        print("[FAILED]", ", ".join(failed))
        return 1
    print(f"[SUCCESS] {len(districts)} districts in {OUT_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
