# A3: SoilGrids REST API — Data Collection & Unit Conversion Report

**Checklist Item:** `A3` — SoilGrids tested + unit conversions noted  
**Status:** ✅ **SATISFIED**  
**Data File in this Folder:** [`soilgrids.json`](file:///c:/Users/hp/Downloads/AgriPulse/Teammate_A_Checklist/A3_SoilGrids_Properties/soilgrids.json)  
**Canonical Copy:** [`data/samples/soilgrids.json`](file:///c:/Users/hp/Downloads/AgriPulse/data/samples/soilgrids.json)

---

## 1. Source & Endpoint Details
* **Provider:** ISRIC — World Soil Information (`SoilGrids v2.0`, 250m spatial resolution)
* **Base URL:** `https://rest.isric.org/soilgrids/v2.0/properties/query`
* **Authentication:** Public REST API (`No API Key required`)
* **Rate Limit:** ~5 requests/minute on public tier (recommended to cache responses per coordinate)

## 2. Exact Query Tested (Rural Agricultural Pixel — Chhatrapati Sambhajinagar, Maharashtra)
```http
GET https://rest.isric.org/soilgrids/v2.0/properties/query?lon=75.3000&lat=19.8500&property=phh2o&property=nitrogen&property=soc&property=clay&property=sand&property=silt&depth=0-5cm&depth=5-15cm&depth=15-30cm&value=mean
```

## 3. Mandatory Unit Conversions Applied
SoilGrids returns integer-scaled units (`mapped units`) to save storage bandwidth. Every response is converted as follows before entering the AgriPulse pipeline:

| Property | SoilGrids Raw Unit | Conversion Formula | Target Agronomic Unit |
| :--- | :--- | :--- | :--- |
| **`phh2o`** | $\text{pH} \times 10$ | $\text{Value} \div 10$ | **pH** (`H2O`) |
| **`nitrogen`** | $\text{cg/kg}$ (`centigrams/kg`) | $\text{Value} \div 100$ | **g/kg** (`Total Nitrogen`) |
| **`soc`** | $\text{dg/kg}$ (`decigrams/kg`) | $\text{Value} \div 10$ | **g/kg** (`Soil Organic Carbon`) |
| **`clay`** | $\text{g/kg}$ (`grams/kg`) | $\text{Value} \div 10$ | **%** (`Clay Percentage`) |
| **`sand`** | $\text{g/kg}$ (`grams/kg`) | $\text{Value} \div 10$ | **%** (`Sand Percentage`) |
| **`silt`** | $\text{g/kg}$ (`grams/kg`) | $\text{Value} \div 10$ | **%** (`Silt Percentage`) |

## 4. Critical Edge-Case Discovered & Mitigated
1. **Urban Built-Up Mask (`mean: null`):** If a farmer or geocoder passes the exact city-center coordinates of a district HQ (e.g., `lat=30.9010, lon=75.8573` in Ludhiana or `lat=19.8762, lon=75.3433` in central Sambhajinagar), SoilGrids returns `mean: null` because urban concrete/asphalt pixels are masked out at 250m resolution.
   * **Fix:** If `mean == null`, shift coordinates by `±0.05°` (~5 km into surrounding rural farmland) or fall back automatically to **A4 (`soil_npk_by_district.csv`)**.
2. **Missing P and K in SoilGrids:** SoilGrids v2.0 does not provide plant-available Phosphorus (`P`) or Potassium (`K`). These are supplied by **A4 (Soil Health Card Portal)**.
