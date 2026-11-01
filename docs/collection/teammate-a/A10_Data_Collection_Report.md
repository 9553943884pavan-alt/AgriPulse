# A10: Irrigation Source & Efficiency by District — Data Collection & Methodology Report

**Checklist Item:** `A10` — Irrigation source + efficiency (`processed/irrigation_by_district.csv`)  
**Status:** ✅ **SATISFIED (100% Real Government Telemetry & Census)**  
**Data File in this Folder:** [`irrigation_by_district.csv`](file:///c:/Users/hp/Downloads/AgriPulse/Teammate_A_Checklist/A10_Irrigation_Source_Efficiency/irrigation_by_district.csv)  
**Canonical Copy:** [`data/processed/irrigation_by_district.csv`](file:///c:/Users/hp/Downloads/AgriPulse/data/processed/irrigation_by_district.csv)  
**Raw API Cache:** [`data/raw/des_lus_irrigation/maharashtra_source_wise_irrigated_area.json`](file:///c:/Users/hp/Downloads/AgriPulse/data/raw/des_lus_irrigation/maharashtra_source_wise_irrigated_area.json) (653 records)

---

## 1. Official Government Sources & Provenance
1. **Directorate of Economics & Statistics (DES) / DACNET, Ministry of Agriculture & Farmers Welfare:**
   - Platform: National Data Sharing and Accessibility Policy (NDSAP) portal — `data.gov.in`.
   - Dataset: *District-wise, Source-wise Net and Gross Irrigated Area in Maharashtra*.
   - Resource ID: `512a034f-6924-42d8-9a76-d40bfb56424a`.
   - Harvested: All 653 historical records across all Maharashtra districts via `pull_a10_des.py`.
2. **Ministry of Jal Shakti, Government of India — 6th Minor Irrigation Census:**
   - Publication: *Report on 6th Census of Minor Irrigation Schemes (State-wise Volume 2: Maharashtra)*.
   - Scheme Disaggregation: Ground water schemes (`open dug wells` = 76.9% state share; `shallow/medium/deep tubewells & borewells` = 13.6%) vs. surface water schemes (`surface flow / canals` and `surface lift / tanks` = 9.5%).
3. **Food and Agriculture Organization (FAO) / ICAR Irrigation Application Efficiency Standards:**
   - **Surface Flood / Furrow Irrigation (`efficiency_flood_pct`):** `60.0%`
   - **Sprinkler Irrigation (`efficiency_sprinkler_pct`):** `75.0%`
   - **Drip / Trickle Micro-irrigation (`efficiency_drip_pct`):** `90.0%`

---

## 2. Dataset Schema & Metrics
| Column | Type | Unit | Description |
| :--- | :--- | :--- | :--- |
| `district` | String | — | Canonical Maharashtra district name |
| `region` | String | — | Revenue / agro-climatic region |
| `net_irrigated_area_pct` | Float | % | Net Irrigated Area as % of Net Sown Area |
| `open_well_share_pct` | Float | % | % of irrigated area powered by open dug wells |
| `borewell_tubewell_share_pct`| Float | % | % of irrigated area powered by deep/shallow tubewells & borewells |
| `canal_surface_flow_share_pct`| Float | % | % of irrigated area powered by government canal network |
| `tank_surface_lift_share_pct` | Float | % | % of irrigated area powered by irrigation tanks / lift schemes |
| `micro_irrigation_adoption_pct`| Float | % | Adoption rate of micro-irrigation (drip + sprinkler) |
| `efficiency_flood_pct` | Float | % | Water conveyance & application efficiency under surface flooding (60%) |
| `efficiency_sprinkler_pct` | Float | % | Water conveyance & application efficiency under sprinkler systems (75%) |
| `efficiency_drip_pct` | Float | % | Water conveyance & application efficiency under precision drip (90%) |
| `source_reference` | String | — | Official citation |

---

## 3. How AgriPulse Uses This Table
1. **Default Irrigation Baselines:** If a farmer doesn't specify their irrigation infrastructure, the system infers their water source profile from the district baseline.
2. **Crop Yield Prediction (`irrigated_pct`):** Supplies the district-level irrigation access parameter to the machine learning yield model.
3. **"Water Saved With Drip" Impact Engine:**
   - Under conventional flood irrigation, gross water extraction is $\text{Gross Water} = \frac{\text{Net Crop Water Need}}{0.60}$.
   - Under precision drip irrigation, gross water extraction is $\text{Gross Water} = \frac{\text{Net Crop Water Need}}{0.90}$.
   - Drip irrigation achieves a **33.3% net reduction** in total water withdrawal ($1 - 0.60 / 0.90 = 0.333$), demonstrating tangible climate resilience and water savings on the user dashboard.
