# A4: District Soil N, P, K & pH (Soil Health Card) — Data Collection & Methodology Report

**Checklist Item:** `A4` — District N, P, K, pH (`processed/soil_npk_by_district.csv`)  
**Status:** ✅ **SATISFIED**  
**Data Files in this Folder:**
1. [`soil_npk_by_district.csv`](file:///c:/Users/hp/Downloads/AgriPulse/Teammate_A_Checklist/A4_Soil_NPK_SoilHealthCard/soil_npk_by_district.csv) — Clean district-level Soil N, P, K, pH, OC, and Micronutrient table (`757` districts including all Maharashtra districts)
2. [`India_District_Soil_NPK_Climate.csv`](file:///c:/Users/hp/Downloads/AgriPulse/Teammate_A_Checklist/A4_Soil_NPK_SoilHealthCard/India_District_Soil_NPK_Climate.csv) — Combined Soil + Live Open-Meteo Weather & Top-3 Crop Recommendations (`757` districts × `35` columns)
**Canonical Copy:** [`data/processed/soil_npk_by_district.csv`](file:///c:/Users/hp/Downloads/AgriPulse/data/processed/soil_npk_by_district.csv)

---

## 1. Official Government Source & Live API
* **Portal:** Soil Health Card (SHC) Central Portal, Department of Agriculture & Farmers Welfare, Government of India
* **Live GraphQL Endpoint:** `POST https://soilhealth4.dac.gov.in`
* **Queries Executed:**
  1. `query Query { getState }` — Retrieved all 34 active State/UT IDs.
  2. `query GetNutrientDashboardForPortal($state: ID, $count: Boolean) { getNutrientDashboardForPortal(state: $state, count: $count) }` with `{"state": "<STATE_ID>", "count": false}` — Retrieved real laboratory soil-test aggregations for **757 Indian districts** across cycles `2023-24`, `2024-25`, `2025-26`, and `2026-27`.

## 2. Agronomic Conversion Methodology (SHC Sample Counts $\rightarrow$ `kg/ha` & `pH`)
The Soil Health Card GraphQL API returns exact laboratory sample counts categorized into `Low`, `Medium`, and `High` fertility brackets for `N`, `P`, `K`, and `OC`, `Acidic / Neutral / Alkaline` for `pH`, `Saline / NonSaline` for `EC`, and `Sufficient / Deficient` for micronutrients (`Zn`, `Fe`, `S`, `Cu`, `B`, `Mn`).

Using the **ICAR / Ramamoorthy & Bajaj (1969) Weighted Nutrient Index** and official Government of India SHC bracket midpoints, we compute continuous district values:

1. **Available Nitrogen (`n_kg_per_ha`):**
   $$\text{n\_kg\_per\_ha} = \frac{190 \cdot N_{\text{Low}} + 420 \cdot N_{\text{Medium}} + 650 \cdot N_{\text{High}}}{N_{\text{Low}} + N_{\text{Medium}} + N_{\text{High}}}$$
   *(Official SHC cutoffs: Low $< 280\text{ kg/ha}$, Medium $280\text{–}560\text{ kg/ha}$, High $> 560\text{ kg/ha}$)*
2. **Available Phosphorus (`p_kg_per_ha`):**
   $$\text{p\_kg\_per\_ha} = \frac{7 \cdot P_{\text{Low}} + 18 \cdot P_{\text{Medium}} + 38 \cdot P_{\text{High}}}{P_{\text{Low}} + P_{\text{Medium}} + P_{\text{High}}}$$
   *(Official SHC cutoffs: Low $< 10\text{ kg/ha}$, Medium $10\text{–}25\text{ kg/ha}$, High $> 25\text{ kg/ha}$)*
3. **Available Potassium (`k_kg_per_ha`):**
   $$\text{k\_kg\_per\_ha} = \frac{80 \cdot K_{\text{Low}} + 194 \cdot K_{\text{Medium}} + 360 \cdot K_{\text{High}}}{K_{\text{Low}} + K_{\text{Medium}} + K_{\text{High}}}$$
   *(Official SHC cutoffs: Low $< 108\text{ kg/ha}$, Medium $108\text{–}280\text{ kg/ha}$, High $> 280\text{ kg/ha}$)*
4. **Soil Reaction (`ph`):**
   $$\text{ph} = \frac{5.6 \cdot \text{pH}_{\text{Acidic}} + 7.0 \cdot \text{pH}_{\text{Neutral}} + 8.1 \cdot \text{pH}_{\text{Alkaline}}}{\text{pH}_{\text{Acidic}} + \text{pH}_{\text{Neutral}} + \text{pH}_{\text{Alkaline}}}$$
5. **Classifier-Ready Scale (`n_crop_rec_scale`, `p_crop_rec_scale`, `k_crop_rec_scale`):**
   Normalized via the district's Nutrient Index ($NI \in [1, 3]$) to match the exact feature distribution (`N: 20–140`, `P: 10–125`, `K: 15–200`) of [`Crop_recommendation.csv`](file:///c:/Users/hp/Downloads/AgriPulse/Crop_recommendation.csv).
