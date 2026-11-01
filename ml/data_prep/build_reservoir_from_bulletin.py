"""Rebuild reservoir_storage.csv from the official CWC weekly reservoir bulletin (PDF).

data.gov.in only serves CWC reservoir records for January 2023 (every later month is listed but empty), so the
current values come from the Central Water Commission weekly bulletin published on rsms.cwc.gov.in
(every Thursday, "Weekly report of important reservoirs of India").

Our 22 Maharashtra reservoirs are matched to the bulletin rows by full-reservoir level and live capacity
(more reliable than names). The original PDF is saved next to the raw data; the observation date stays in the table.

Run from the repo root:  python -I ml/data_prep/build_reservoir_from_bulletin.py [DD-MM-YYYY] [bulletin_id]
Default: 29-10-2026, id 126 (the id is part of the file name and must be looked up when the date changes).
"""

import re
import sys
import urllib.request
from pathlib import Path

import pandas as pd
import pypdf

REPO_ROOT = Path(__file__).resolve().parents[2]
TABLE = REPO_ROOT / "data" / "processed" / "reservoir_storage.csv"
RAW_DIR = REPO_ROOT / "data" / "raw" / "cwc_reservoir"
DAY = sys.argv[1] if len(sys.argv) > 1 else "29-10-2026"
BULLETIN_ID = sys.argv[2] if len(sys.argv) > 2 else "126"
URL = f"https://rsms.cwc.gov.in/admin/storage/bulletins/bulletin-{DAY}-{BULLETIN_ID}.pdf"
TMC_PER_BCM = 35.3147
ROW = re.compile(
    r"(?:\d+\s+)?(?P<name>[A-Z][A-Z .&/-]*?)?\s*Maharashtra\s+(?P<ccs>[\d.]+)\s+(?P<hydel>[\d.]+)\s+(?P<frl>[\d.]+)\s+(?P<cap>[\d.]+)\s+"
    r"(?P<date>\d{2}\.\d{2}\.\d{4})\s+(?P<level>[\d.]+)\s+(?P<storage>[\d.]+)\s+(?P<pct>[\d.]+)"
)


def download() -> Path:
    path = RAW_DIR / f"cwc_bulletin_{DAY}.pdf"
    if not path.exists():
        request = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(request, timeout=120) as response:
            path.write_bytes(response.read())
    return path


def bulletin_rows(pdf_path: Path) -> pd.DataFrame:
    rows = []
    for page in pypdf.PdfReader(str(pdf_path)).pages:
        for line in (page.extract_text() or "").splitlines():
            match = ROW.search(line)
            if match:
                item = match.groupdict()
                rows.append({**{k: item[k] for k in ("name", "date")}, **{k: float(item[k]) for k in ("frl", "cap", "level", "storage", "pct")}})
    return pd.DataFrame(rows)


def main() -> int:
    pdf_path = download()
    found = bulletin_rows(pdf_path)
    print(f"[info] {pdf_path.name}: {len(found)} Maharashtra rows in the bulletin")
    found.to_csv(RAW_DIR / f"cwc_bulletin_{DAY}_maharashtra_rows.csv", index=False, encoding="utf-8")

    table = pd.read_csv(TABLE)
    out, missing = [], []
    for item in table.itertuples():
        hit = found[((found["frl"] - float(item.full_reservoir_level_m)).abs() < 0.02)
                    & ((found["cap"] * 1000 - float(item.designed_live_capacity_mcum)).abs() < 1.5)]
        if len(hit) != 1:  # live capacity can be revised between years: fall back to the full-reservoir level alone
            hit = found[(found["frl"] - float(item.full_reservoir_level_m)).abs() < 0.02]
        if len(hit) != 1:
            missing.append(item.reservoir)
            continue
        h = hit.iloc[0]
        date = pd.to_datetime(h["date"], format="%d.%m.%Y").strftime("%Y-%m-%d")
        out.append({
            "reservoir": item.reservoir, "region": item.region, "river_basin": item.river_basin,
            "districts_served": item.districts_served,
            "designed_live_capacity_mcum": round(h["cap"] * 1000, 1), "designed_live_capacity_tmc": round(h["cap"] * TMC_PER_BCM, 2),
            "current_live_storage_mcum": round(h["storage"] * 1000, 1), "current_live_storage_tmc": round(h["storage"] * TMC_PER_BCM, 2),
            "live_storage_pct_of_capacity": round(h["pct"], 1),
            "full_reservoir_level_m": h["frl"], "current_water_level_m": h["level"],
            "observation_date": date,
            "source": f"Central Water Commission weekly reservoir bulletin {DAY} ({URL})",
        })
    result = pd.DataFrame(out)
    if missing:
        print("[WARN] not found in the bulletin (left out):", missing)
    result.to_csv(TABLE, index=False, encoding="utf-8")
    print(f"[SUCCESS] {len(result)} of {len(table)} reservoirs, date {result['observation_date'].unique().tolist()}, "
          f"storage {result['live_storage_pct_of_capacity'].min()}-{result['live_storage_pct_of_capacity'].max()}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
