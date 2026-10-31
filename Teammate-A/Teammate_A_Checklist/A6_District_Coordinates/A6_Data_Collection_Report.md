# A6: Canonical Maharashtra Districts, Coordinates & Name Variants — Data Collection Report

**Checklist Item:** `A6` — 36 districts + coordinates + name variants (`processed/districts.csv`)  
**Status:** ✅ **SATISFIED**  
**Data File in this Folder:** [`districts.csv`](file:///c:/Users/hp/Downloads/AgriPulse/Teammate_A_Checklist/A6_District_Coordinates/districts.csv)  
**Canonical Copy:** [`data/processed/districts.csv`](file:///c:/Users/hp/Downloads/AgriPulse/data/processed/districts.csv)

---

## 1. Purpose & Rule 6 Compliance
Per **Rule 6** of [`DATA_COLLECTION.md`](file:///c:/Users/hp/Downloads/AgriPulse/DATA_COLLECTION.md#L85):
> *"District names: sources spell them differently (`Ahmednagar` / `Ahmadnagar` / `Ahilyanagar`, `Beed` / `Bid`, `Raigad` / `Raigarh`). Keep one canonical list of 36 Maharashtra districts in `data/processed/districts.csv` with a `name_variants` column. Every other file must join to it."*

## 2. Data Sources Used
* **District List & Official Renamings:** Local Government Directory (LGD, Government of India) & Maharashtra Revenue Department (`36` districts, including recent official renamings: `Chhatrapati Sambhajinagar` for `Aurangabad`, `Dharashiv` for `Osmanabad`, and `Ahilyanagar` for `Ahmednagar`).
* **District HQ Coordinates (`latitude`, `longitude`):** Open-Meteo Geocoding API (`https://geocoding-api.open-meteo.com/v1/search`) cross-checked with OpenStreetMap Nominatim district headquarters.

## 3. Schema of `districts.csv`
| Column | Type | Example | Description |
| :--- | :--- | :--- | :--- |
| `district` | String | `Chhatrapati Sambhajinagar` | Canonical district key used across all AgriPulse CSV tables |
| `state` | String | `Maharashtra` | State name |
| `hq_name` | String | `Chhatrapati Sambhajinagar (Aurangabad)` | District headquarters town/city |
| `latitude` | Float | `19.8762` | HQ Latitude (`°N`) |
| `longitude` | Float | `75.3433` | HQ Longitude (`°E`) |
| `name_variants` | Pipe-delimited String | `Chhatrapati Sambhajinagar\|Aurangabad\|Sambhajinagar\|AURANGABAD` | All spelling variants across IMD, Agmarknet, DES, CGWB, and SHC portals |
