# AgriPulse data

Every dataset the project uses lives under this one folder. Nothing data-related sits outside it.

```
data/
├── processed/   21 analysis-ready tables — the only folder the backend reads
├── raw/         untouched source downloads, one subfolder per source
├── samples/     small API-response samples kept for reference
├── evidence/    per-checklist deliverable copies (hackathon audit trail)
├── cache.db     runtime SQLite cache (created by the backend, not source data)
├── SOURCES_teammate_a.md, SOURCES_teammate_b.md   provenance notes
└── DATA_FIXES.md                                  corrections log
```

| Folder | Size | Files |
|---|---|---|
| `processed/` | 4.3 MB | 21 |
| `raw/` | 31 MB | 117 |
| `samples/` | 45 KB | 4 |
| `evidence/` | 7.1 MB | 34 |

## Before you move anything

**File paths in `processed/` and `raw/` are hard-coded in source.** Renaming or moving a file here
will break the app. The paths are referenced from exactly these places:

| Where | What it points at |
|---|---|
| `backend/app/data/loaders.py` | `_PROC` → `data/processed/` (every backend table) |
| `backend/tests/test_data.py` | `data/processed/` + a repo-wide scan of `data/` |
| `ml/data_prep/*.py` | `data/processed/`, `data/raw/`, `data/evidence/teammate-b/` |
| `ml/experiments/train_yield_model.py` | `yield_training.csv`, `district_rainfall_history.csv` |

If you do move something, update those and run `python -I ml/data_prep/check_data.py` plus
`pytest backend/tests/test_data.py`.

## `processed/` — the tables the app reads

19 of these are eagerly loaded at backend startup by `load_all()`; `/api/health` reports
`models_loaded` and the loaded count. Row counts are data rows, excluding the header.

| File | Rows | What it holds |
|---|---|---|
| `districts.csv` | 36 | Maharashtra districts: canonical name, LGD code, coordinates, name variants |
| `district_crop_yields.csv` | 12,367 | DES district × crop × year area/production/yield |
| `crop_calendar.csv` | 25 | sowing windows and crop duration per crop and season |
| `crops_master.csv` | 28 | canonical crop names with `crop_id` and mr/hi/en display names |
| `soil_npk_by_district.csv` | 757 | Soil Health Card N/P/K and climate, all-India districts |
| `groundwater_by_block.csv` | 71 | block-level groundwater level and extraction category |
| `irrigation_by_district.csv` | 36 | irrigated area by source, with source efficiency |
| `recent_rainfall.csv` | 36 | recent observed rainfall per district |
| `reservoir_storage.csv` | 22 | CWC weekly reservoir and canal storage percentages |
| `crop_water_coefficients.csv` | 29 | FAO-56 Kc values and stage lengths (ini/dev/mid/late) |
| `cost_of_cultivation.csv` | 15 | DES cost-of-cultivation cost lines per crop |
| `seed.csv` | 13 | Mahabeej seed rate and price per crop |
| `fertilizer_rdf.csv` | 15 | recommended fertilizer dose per crop |
| `fertilizer_prices.csv` | 6 | fertilizer product prices |
| `fertilizer_use_by_district.csv` | 34 | district fertilizer consumption kg/ha |
| `msp.csv` | 45 | minimum support prices (and sugarcane FRP) |
| `price_history_monthly.csv` | 21,707 | observed Agmarknet monthly modal price per crop × district |
| `price_history_state_monthly.csv` | 1,490 | state-level monthly price spread, used for price risk |
| `district_rainfall_history.csv` | 4,032 | seasonal weather per district × year, 1997–2024 |
| `yield_training.csv` | 11,576 | ML training table (28 features); not warmed at startup |
| `district_weather_seasonal.csv` | 4,032 | ML intermediate from the weather build; no backend loader |

## `raw/` — source downloads

| Folder | Files | Source |
|---|---|---|
| `nominatim/` | 36 | OSM Nominatim district-headquarters lookups |
| `open_meteo_archive/` | 36 | Open-Meteo archive, earlier 2010–2025 pull |
| `open_meteo_archive_1997_2025/` | 36 | Open-Meteo archive 1997–2025, the one in use |
| `cwc_reservoir/` | 3 | CWC weekly reservoir bulletin (PDF + extracted rows) |
| `fao56/` | 3 | FAO-56 reference chapters for Kc values |
| `des_lus_irrigation/` | 1 | DES land-use / source-wise irrigated area |
| `mi_census_village/` | 1 | Minor Irrigation census village schedule |
| `agmarknet/` | 1 | raw Agmarknet price export |

Raw files are inputs only — never edit them by hand. Regenerate `processed/` from them instead.

## Regenerating `processed/`

Run from the repo root. Scripts marked ⚠ hit the network and overwrite tables in place.

```bash
python -I ml/data_prep/fetch_weather.py              # ⚠ → raw/open_meteo_archive_1997_2025/
python -I ml/data_prep/build_yield_training.py       #    → yield_training, district_rainfall_history,
                                                     #      district_weather_seasonal
python -I ml/data_prep/build_price_history.py        # ⚠ → price_history_monthly, price_history_state_monthly
python -I ml/data_prep/build_reservoir_from_bulletin.py  # → reservoir_storage
python -I ml/data_prep/normalize_district_names.py   #    normalise district spellings across data/
python -I ml/data_prep/check_data.py                 #    read-only validator, 18 checks
```

Train the yield model with `python -I ml/experiments/train_yield_model.py`
(writes `ml/models/yield_model_a.joblib`).

## `evidence/` — audit trail

`evidence/teammate-a/A1…A10` and `evidence/teammate-b/A4…A7, B1…B12` keep each checklist item's
delivered output next to the dataset it produced. Most files here are byte-identical copies of a
table in `processed/`; they exist so each checklist item can be verified on its own. Two build
scripts still write into `evidence/teammate-b/B2_price_history_monthly/` and
`B12_yield_training_dataset/`, so don't delete those folders.

## Two deliberate de-duplication calls

When the four scattered data folders were merged, two filenames collided:

- **`districts.csv`** existed in four places, all byte-identical (`ec88da28`). One copy now lives in
  `processed/`; the `evidence/` copies were left in place.
- **`district_rainfall_history.csv`** existed in two genuinely different versions. The 272 KB
  Teammate-B build is the one the code reads and is in `processed/`. The older 237 KB Teammate-A
  variant is preserved at `evidence/teammate-a/A2_Historical_Weather_10Yrs/`.
- **`soil_npk_by_district.csv`** likewise: the all-India 757-row version is in `processed/`; a
  smaller 34-row variant remains at `evidence/teammate-b/A4_soil_health_card/`.

## Secrets

No API keys belong in any file under `data/`. Keys live only in `.env`, which is gitignored;
`.env.example` carries the key *names* with empty values. Two checks enforce this:
`ml/data_prep/check_data.py` matches known key prefixes, and
`backend/tests/test_data.py::test_no_api_keys_in_folder` scans `data/`, `backend/data/` and `docs/`.
