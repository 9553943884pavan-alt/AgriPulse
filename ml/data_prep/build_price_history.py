"""Build REAL monthly mandi price history for Maharashtra from the full Agmarknet daily data.

Source: India Data Portal "Agriculture Marketing" package (Agmarknet daily price and arrival data, published as
bulk CSV): https://ckandev.indiadataportal.com/dataset/agriculture-marketing
  * "APMC Arrivals And Prices (Old Source)": daily rows from 2021-01-01 (about 4.2 GB)
  * "APMC Arrivals And Prices (New Source)": daily rows from 2025-10 onward (about 0.8 GB)
Both files are streamed and filtered on the fly (never stored whole): only Maharashtra rows for our crops are kept.

Why: the earlier price_history_monthly.csv was modelled (every district moved in exact lockstep), not observed.

Outputs (Teammate-B/data/processed/):
  price_history_monthly.csv        commodity, district, year, month, modal_price_rs_per_quintal (median of daily modal
                                   prices), n_observations
  price_history_state_monthly.csv  commodity, year, month, median/mean/std of daily modal price across all
                                   Maharashtra markets, n_observations, n_districts  (used for price risk)
Raw filtered rows are written to a gzip file outside git (see --raw-out); copy of both outputs goes to the B2 folder.

Run from the repo root:  python -I ml/data_prep/build_price_history.py [--raw-out <file.csv.gz>]
"""

import csv
import gzip
import io
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
B_PROC = REPO_ROOT / "Teammate-B" / "data" / "processed"
B_B2 = REPO_ROOT / "Teammate-B" / "teammate_b" / "B2_price_history_monthly"
SOURCES = {
    "old": "https://ckandev.indiadataportal.com/dataset/1749d812-35b4-4635-ac29-dd3116ed31b0/resource/21ecb9f0-7bf9-42d0-af24-df2e230e4a0a/download/apmc-arrivals-and-prices-old-source.csv",
    "new": "https://ckandev.indiadataportal.com/dataset/1749d812-35b4-4635-ac29-dd3116ed31b0/resource/078fd1ea-dab6-4aca-aed9-3a4b8b2c761d/download/apmc-arrivals-and-prices-new-source.csv",
}
HEADERS = {"User-Agent": "Mozilla/5.0 (AgriPulse data prep)"}
KEEP_STATE = "Maharashtra"


def norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


# Agmarknet renamed several commodities between the old file (2021-2025) and the new one (2025-10 onward).
# Every alias maps to the canonical name in crops_master.csv, so one crop stays one series.
COMMODITY_ALIASES = {
    # Confirmed 2026-10-31 by scanning the old (2021-2025) bulk file's real Maharashtra rows
    # (ml/data_prep/scan_commodity_names.py -> old_source_commodities.txt):
    #   "Rice" 14,466 rows, "Paddy(Dhan)(Common)" 12,725 rows, "Arhar (Tur/Red Gram)(Whole)" 70,836 rows,
    #   "Arhar Dal(Tur Dal)" 1,214 rows.
    "Paddy(Common)": ["Paddy", "Rice", "Paddy(Dhan)(Common)", "Paddy(Dhan)", "Rice(Common)"],
    "Red gram/Arhar/Tur(whole)": ["Arhar (Tur/Red Gram)(Whole)", "Arhar Dal(Tur Dal)", "Arhar(Tur/Red Gram)",
                                  "Tur", "Red Gram", "Arhar"],
    "Moth": ["Moth Bean", "Moath Dal", "Matki"],
    "Bengal Gram(Gram)(Whole)": ["Bengal Gram Dal (Chana Dal)", "Gram Raw(Chholia)"],
    "Green Gram(Moong)(Whole)": ["Green Gram Dal (Moong Dal)"],
    "Black Gram(Urd Beans)(Whole)": ["Black Gram Dal (Urd Dal)"],
    "Lentil(Masur)(Whole)": ["Masur Dal"],
}


def wanted_commodities() -> dict[str, str]:
    """normalised source name -> canonical crops_master name."""
    master = pd.read_csv(B_PROC / "crops_master.csv")
    master = master[master["is_maharashtra_crop"].astype(str).str.lower() == "true"]
    wanted = {}
    for name in master["agmarknet_commodity"].dropna():
        wanted[norm(name)] = name
        for alias in COMMODITY_ALIASES.get(name, []):
            wanted[norm(alias)] = name
    return wanted


def district_lookup() -> dict[str, str]:
    """Any Agmarknet spelling -> the canonical district name in districts.csv."""
    districts = pd.read_csv(REPO_ROOT / "Teammate-A" / "data" / "processed" / "districts.csv")
    return {norm(n): row.district for row in districts.itertuples()
            for n in [row.district, *str(row.name_variants).split("|")]}


def stream_lines(url: str, start: int = 0):
    """Yield (decoded line, byte offset after the line); reconnects with a Range header if the connection drops."""
    offset = start
    while True:
        request = urllib.request.Request(url, headers={**HEADERS, **({"Range": f"bytes={offset}-"} if offset else {})})
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                pending = b""
                while True:
                    chunk = response.read(1 << 20)
                    if not chunk:
                        if pending:
                            yield pending.decode("utf-8", errors="replace"), offset + len(pending)
                        return
                    pending += chunk
                    *lines, pending = pending.split(b"\n")
                    for line in lines:
                        offset += len(line) + 1
                        yield line.decode("utf-8", errors="replace"), offset
        except (OSError, ConnectionError) as exc:
            print(f"[retry] connection dropped at {offset / 1e6:.0f} MB: {type(exc).__name__}", flush=True)
            time.sleep(10)


def filter_source(name: str, url: str, wanted: dict[str, str], writer) -> int:
    kept = rows = 0
    header = None
    started = time.time()
    for line, offset in stream_lines(url):
        if header is None:
            header = next(csv.reader([line]))
            idx = {col: header.index(col) for col in header}
            date_col = "report_date" if "report_date" in idx else "date"
            commodity_col = "commodity_name"
            continue
        rows += 1
        if rows % 2_000_000 == 0:
            print(f"[{name}] {rows / 1e6:.0f}M rows, {offset / 1e9:.2f} GB, kept {kept:,}, {time.time() - started:.0f}s", flush=True)
        if KEEP_STATE not in line:  # cheap pre-filter before parsing the line
            continue
        parts = next(csv.reader([line]))
        if len(parts) != len(header) or parts[idx["state_name"]] != KEEP_STATE:
            continue
        official = wanted.get(norm(parts[idx[commodity_col]]))
        if official is None:
            continue
        writer.writerow([name, parts[idx[date_col]], parts[idx["district_name"]], parts[idx["market_center" if "market_center" in idx else "market_center_name"]],
                         official, parts[idx["variety"]], parts[idx["min_price"]], parts[idx["max_price"]], parts[idx["modal_price"]],
                         parts[idx["price_unit"]]])
        kept += 1
    print(f"[{name}] finished: {rows:,} rows read, {kept:,} Maharashtra rows for our crops kept", flush=True)
    return kept


def main() -> int:
    raw_out = Path(sys.argv[sys.argv.index("--raw-out") + 1]) if "--raw-out" in sys.argv else Path("maharashtra_prices_raw.csv.gz")
    wanted = wanted_commodities()
    print(f"[info] {len(wanted)} source names, raw output {raw_out}", flush=True)
    if "--reaggregate" in sys.argv:          # rebuild the tables from an existing raw file, no download
        print("[info] re-aggregating from the saved raw file", flush=True)
    else:
        with gzip.open(raw_out, "wt", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["source", "date", "district", "market", "commodity", "variety", "min_price", "max_price", "modal_price", "price_unit"])
            for name, url in SOURCES.items():
                filter_source(name, url, wanted, writer)

    data = pd.read_csv(raw_out, parse_dates=["date"])
    lookup = district_lookup()
    unmatched = sorted({d for d in data["district"].unique() if norm(d) not in lookup})
    if unmatched:
        print("[WARN] district spellings not in districts.csv (rows dropped):", unmatched)
    data["district"] = data["district"].map(lambda v: lookup.get(norm(v)))
    data = data.dropna(subset=["district"])
    data["modal_price"] = pd.to_numeric(data["modal_price"], errors="coerce")
    data = data.dropna(subset=["modal_price"])
    data = data[data["modal_price"] > 0]
    # the old and new files may overlap on some days: keep one row per market-day-variety
    data = data.drop_duplicates(subset=["date", "district", "market", "commodity", "variety", "modal_price"])
    per_quintal = data["price_unit"].str.contains("quintal", case=False, na=False)
    print("[info] rows in other units (not per quintal):", data.loc[~per_quintal, ["commodity", "price_unit"]].drop_duplicates().to_dict("records"))
    other_units = data.loc[~per_quintal, ["commodity", "price_unit"]].drop_duplicates()
    data = data[per_quintal].copy()
    data["year"], data["month"] = data["date"].dt.year, data["date"].dt.month

    district = (data.groupby(["commodity", "district", "year", "month"])["modal_price"]
                .agg(modal_price_rs_per_quintal="median", n_observations="size").round(2).reset_index())
    state = (data.groupby(["commodity", "year", "month"])["modal_price"]
             .agg(median_modal_rs_per_quintal="median", mean_modal_rs_per_quintal="mean", std_modal_rs_per_quintal="std", n_observations="size")
             .round(2).reset_index())
    state["n_districts"] = data.groupby(["commodity", "year", "month"])["district"].nunique().values
    for folder in (B_PROC, B_B2):
        district.to_csv(folder / "price_history_monthly.csv", index=False, encoding="utf-8")
        state.to_csv(folder / "price_history_state_monthly.csv", index=False, encoding="utf-8")
    summary = {
        "district_rows": len(district), "state_rows": len(state), "date_range": [str(data["date"].min().date()), str(data["date"].max().date())],
        "commodities_with_history": sorted(state["commodity"].unique()),
        "commodities_without_history": sorted(set(wanted.values()) - set(state["commodity"].unique())),
        "commodities_not_priced_per_quintal": other_units.to_dict("records"),
        "months_per_commodity": state.groupby("commodity").size().to_dict(),
    }
    print(json.dumps(summary, indent=1, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
