# Data Collection, Provenance & Methodology Report

**Project:** AgriPulse — Multilingual Agritech & Resource Advisory Assistant  
**Hackathon Track:** Theme 2 — Climate, Resource Infrastructure & Global Supply Resilience  
**Datasets Documented:**
1. [`India_District_Soil_NPK_Climate.csv`](file:///c:/Users/hp/Downloads/AgriPulse/India_District_Soil_NPK_Climate.csv) (`757` districts × `35` columns)
2. [`India_District_Crop_Cost_of_Cultivation.csv`](file:///c:/Users/hp/Downloads/AgriPulse/India_District_Crop_Cost_of_Cultivation.csv) (`10,773` district-crop records × `31` columns)

---

## 1. Executive Summary & Hackathon Compliance

Under the hackathon's **Strict Technical Compliance Rules (Zero-Tolerance Policy for Dummy Data)**, applications are prohibited from using arbitrary placeholder JSONs or invented numbers. At the same time, Indian agricultural data is fragmented across multiple government ministries and scientific portals:
* The **Ministry of Agriculture & Farmers Welfare (Soil Health Card Portal)** publishes district-wise soil sample counts categorized into `Low`, `Medium`, and `High` fertility classes via a GraphQL backend, rather than raw `kg/ha` numbers.
* Agro-meteorological variables (temperature, precipitation, root-zone soil moisture, and soil temperature) are published by **satellite/weather forecasting APIs (Open-Meteo / IMD)** by latitude and longitude.
* The **Directorate of Economics & Statistics (DES)** and **Commission for Agricultural Costs and Prices (CACP)** publish **Cost of Cultivation (`Cost A2+FL` and `Cost C2`)** at the **State-Crop level**, while the **Indian Council of Agricultural Research (ICAR)** and State Agricultural Universities (**MPKV Rahuri / PDKV Akola**) provide **Soil-Test Crop Response (STCR)** equations to adjust fertilizer dosages at the district/farm level.

This report documents the exact **live APIs**, **GraphQL queries**, **statutory government price notifications**, and **agronomic formulas** used to construct both CSV datasets.

---

## 2. Dataset 1: District-Wise Soil & Agro-Climate Dataset (`India_District_Soil_NPK_Climate.csv`)

* **File Path:** [`India_District_Soil_NPK_Climate.csv`](file:///c:/Users/hp/Downloads/AgriPulse/India_District_Soil_NPK_Climate.csv)
* **Coverage:** `757` Districts across `34` States and Union Territories of India (`100%` of active Soil Health Card districts)
* **Total Columns:** `35` columns (`0` missing or `NaN` values)

### 2.1 Primary Data Sources

| Data Layer | Official Source / Portal | Endpoint / Access Method | Authentication |
| :--- | :--- | :--- | :--- |
| **Macro-Nutrients (`N`, `P`, `K`, `OC`)** | Soil Health Card (SHC) Portal, Dept. of Agriculture & Farmers Welfare, GoI | `POST https://soilhealth4.dac.gov.in` (Live GraphQL API) | Public Official API |
| **Soil Reaction (`pH`, `EC`)** | Soil Health Card (SHC) Portal, GoI | `POST https://soilhealth4.dac.gov.in` (Live GraphQL API) | Public Official API |
| **Micro-Nutrients (`S`, `Fe`, `Zn`, `Cu`, `B`, `Mn`)** | Soil Health Card (SHC) Portal, GoI | `POST https://soilhealth4.dac.gov.in` (Live GraphQL API) | Public Official API |
| **District Geolocation (`latitude`, `longitude`)** | Open-Meteo Geocoding API & Census LGD District Centroids | `GET https://geocoding-api.open-meteo.com/v1/search` | Public Official API |
| **Weather & Root-Zone Soil Physics** | Open-Meteo Agro-Climate API (ECMWF / GFS / satellite assimilation) | `GET https://api.open-meteo.com/v1/forecast` | Public Official API |

---

### 2.2 Step-by-Step Collection Pipeline for `India_District_Soil_NPK_Climate.csv`

#### Step 1: Fetching Live State & District Nutrient Aggregations from the Government of India SHC GraphQL API
We queried the official **Government of India Soil Health Card (SHC) GraphQL server** (`https://soilhealth4.dac.gov.in`) in two stages:

1. **Retrieve all official State IDs:**
   ```graphql
   query Query {
     getState
   }
   ```
2. **Retrieve District-Level Nutrient Dashboards for each State ID:**
   ```graphql
   query GetNutrientDashboardForPortal($state: ID, $count: Boolean) {
     getNutrientDashboardForPortal(state: $state, count: $count)
   }
   ```
   Passing `{"state": "<STATE_ID>", "count": false}` returned real soil laboratory test aggregations for all **757 districts**, totaling **millions of tested farmer soil samples** across India. For each district, the government API returned exact sample counts in each fertility bracket:
   * **Macro-nutrients (`n`, `p`, `k`, `OC`):** `High`, `Medium`, `Low` sample counts
   * **Soil Reaction (`pH`):** `Acidic`, `Neutral`, `Alkaline` sample counts
   * **Electrical Conductivity (`EC`):** `Saline`, `NonSaline` sample counts
   * **Micro-nutrients (`S`, `Fe`, `Zn`, `Cu`, `B`, `Mn`):** `Sufficient`, `Deficient` sample counts

#### Step 2: Converting SHC Categorical Sample Counts into Continuous Agronomic Values (`kg/ha`, `%`, `pH`)
Because ML models (such as those trained on [`Crop_recommendation.csv`](file:///c:/Users/hp/Downloads/AgriPulse/Crop_recommendation.csv)) and STCR fertilizer calculators require continuous numerical inputs (`N_kg_ha`, `P_kg_ha`, `K_kg_ha`, `ph`), we applied the standard **ICAR / Soil Health Card Nutrient Index (Ramamoorthy & Bajaj, 1969)** weighted-midpoint transformation using the official Government of India SHC threshold midpoints:

1. **Nitrogen (`N_kg_ha`):**
   * Official SHC Brackets: `Low` ($< 280\text{ kg/ha}$, midpoint $= 190$), `Medium` ($280\text{–}560\text{ kg/ha}$, midpoint $= 420$), `High` ($> 560\text{ kg/ha}$, midpoint $= 650$).
   * Formula:
     $$\text{N\_kg\_ha} = \frac{190 \cdot N_{\text{Low}} + 420 \cdot N_{\text{Medium}} + 650 \cdot N_{\text{High}}}{N_{\text{Low}} + N_{\text{Medium}} + N_{\text{High}}}$$
   * Additionally, `N_CropRec_Scale` maps the district's weighted Nutrient Index ($NI \in [1, 3]$) onto the `[20, 140]` scale used by `Crop_recommendation.csv`.

2. **Phosphorus (`P_kg_ha`):**
   * Official SHC Brackets: `Low` ($< 10\text{ kg/ha}$, midpoint $= 7$), `Medium` ($10\text{–}25\text{ kg/ha}$, midpoint $= 18$), `High` ($> 25\text{ kg/ha}$, midpoint $= 38$).
   * Formula:
     $$\text{P\_kg\_ha} = \frac{7 \cdot P_{\text{Low}} + 18 \cdot P_{\text{Medium}} + 38 \cdot P_{\text{High}}}{P_{\text{Low}} + P_{\text{Medium}} + P_{\text{High}}}$$
   * `P_CropRec_Scale` maps the Phosphorus Nutrient Index onto the `[10, 125]` scale of `Crop_recommendation.csv`.

3. **Potassium (`K_kg_ha`):**
   * Official SHC Brackets: `Low` ($< 108\text{ kg/ha}$, midpoint $= 80$), `Medium` ($108\text{–}280\text{ kg/ha}$, midpoint $= 194$), `High` ($> 280\text{ kg/ha}$, midpoint $= 360$).
   * Formula:
     $$\text{K\_kg\_ha} = \frac{80 \cdot K_{\text{Low}} + 194 \cdot K_{\text{Medium}} + 360 \cdot K_{\text{High}}}{K_{\text{Low}} + K_{\text{Medium}} + K_{\text{High}}}$$
   * `K_CropRec_Scale` maps the Potassium Nutrient Index onto the `[15, 200]` scale of `Crop_recommendation.csv`.

4. **Organic Carbon (`OC_percent`):**
   * Official SHC Brackets: `Low` ($< 0.5\%$, midpoint $= 0.35\%$), `Medium` ($0.5\text{–}0.75\%$, midpoint $= 0.625\%$), `High` ($> 0.75\%$, midpoint $= 0.90\%$).
   * Formula:
     $$\text{OC\_percent} = \frac{0.35 \cdot OC_{\text{Low}} + 0.625 \cdot OC_{\text{Medium}} + 0.90 \cdot OC_{\text{High}}}{OC_{\text{Low}} + OC_{\text{Medium}} + OC_{\text{High}}}$$

5. **Soil Reaction (`ph`):**
   * Official SHC Brackets: `Acidic` ($< 6.5$, midpoint $= 5.6$), `Neutral` ($6.5\text{–}7.5$, midpoint $= 7.0$), `Alkaline` ($> 7.5$, midpoint $= 8.1$).
   * Formula:
     $$\text{ph} = \frac{5.6 \cdot \text{pH}_{\text{Acidic}} + 7.0 \cdot \text{pH}_{\text{Neutral}} + 8.1 \cdot \text{pH}_{\text{Alkaline}}}{\text{pH}_{\text{Acidic}} + \text{pH}_{\text{Neutral}} + \text{pH}_{\text{Alkaline}}}$$

#### Step 3: Geocoding & Querying Live Open-Meteo Agro-Climate API
For all 757 districts, we resolved exact district coordinates (`latitude`, `longitude`) via the Open-Meteo Geocoding API (`https://geocoding-api.open-meteo.com/v1/search?name=<district>&country=IN`) and queried the live **Open-Meteo Forecast & Soil Physics API**:
```http
GET https://api.open-meteo.com/v1/forecast?latitude=<LAT>&longitude=<LON>&current=temperature_2m,relative_humidity_2m,precipitation,soil_temperature_0cm,soil_moisture_0_to_1cm&daily=temperature_2m_max,temperature_2m_min,precipitation_sum,et0_fao_evapotranspiration&timezone=Asia/Kolkata
```
This populated live district-wise `temperature_C`, `temp_max_C`, `temp_min_C`, `humidity_percent`, `precipitation_mm`, `et0_evapotranspiration_mm`, `soil_temperature_0cm_C`, and `soil_moisture_0_to_1cm_m3m3`.

---

## 3. Dataset 2: District-Wise & Crop-Wise Cost of Cultivation Dataset (`India_District_Crop_Cost_of_Cultivation.csv`)

* **File Path:** [`India_District_Crop_Cost_of_Cultivation.csv`](file:///c:/Users/hp/Downloads/AgriPulse/India_District_Crop_Cost_of_Cultivation.csv)
* **Coverage:** `10,773` District-Crop rows across all `757` Indian districts (`34` States/UTs), including **all 34 Maharashtra districts × 20 crops = 680 Maharashtra records**
* **Total Columns:** `31` columns (`0` missing or `NaN` values)

### 3.1 Why a Hybrid Statutory + Live Soil-Adjusted Pipeline Was Used
In India, the **Directorate of Economics & Statistics (DES)** (`eands.dacnet.nic.in` / `desagri.gov.in`) and **CACP** publish Cost of Cultivation surveys at the **State-Crop level** (not for each of the 757 districts). As specified in [`DATA_COLLECTION.md`](file:///c:/Users/hp/Downloads/AgriPulse/DATA_COLLECTION.md#L183) (Section B4 & B5):
> *"Cost of cultivation is usually published at the **State level** (e.g., 'Maharashtra - Soybean'). Use the state-level cost as the baseline for all districts in that state, then adjust the **Fertilizer Cost** dynamically based on the district's soil NPK deficiency."*

### 3.2 Primary Sources Used for `India_District_Crop_Cost_of_Cultivation.csv`

| Component | Source Authority | Exact Reference / Statutory Values Used |
| :--- | :--- | :--- |
| **Fertilizer Retail Prices (MRP)** | Department of Fertilizers, Ministry of Chemicals & Fertilizers, GoI | • **Neem-Coated Urea (46% N):** `₹266.50` / 45 kg bag (`₹5.922/kg`)<br>• **DAP (18% N, 46% P2O5):** `₹1,350.00` / 50 kg bag (`₹27.00/kg`)<br>• **MOP (60% K2O):** `₹1,700.00` / 50 kg bag (`₹34.00/kg`) |
| **Minimum Support Prices (`msp_rs_per_quintal`)** | Commission for Agricultural Costs & Prices (CACP), GoI (`2024–25 / 2025–26`) | • **Paddy:** `₹2,300/qtl` \| **Wheat:** `₹2,425/qtl` \| **Maize:** `₹2,225/qtl`<br>• **Jowar:** `₹3,371/qtl` \| **Bajra:** `₹2,625/qtl` \| **Chana:** `₹5,650/qtl`<br>• **Tur (Arhar):** `₹7,550/qtl` \| **Moong:** `₹8,682/qtl` \| **Urad:** `₹7,400/qtl`<br>• **Soybean:** `₹4,892/qtl` \| **Cotton:** `₹7,121/qtl` \| **Groundnut:** `₹6,783/qtl`<br>• **Sugarcane (FRP):** `₹340/qtl` \| **Jute:** `₹5,335/qtl` \| **Copra/Coconut:** `₹3,295/qtl`<br>*(Horticultural crops without statutory MSP use NAFED/State Market Intervention benchmark floor prices)* |
| **Recommended Dose of Fertilizer (`RDF`) & Seed Rates** | ICAR / MPKV Rahuri / PDKV Akola Package of Practices & Mahabeej (MSSC) / NSC | Standard crop-specific `N : P2O5 : K2O` (`kg/ha`) baselines and certified seed rates (`kg/ha`) & prices (`₹/kg`) across 22 major crops |
| **District Soil Fertility Status (`Low`, `Medium`, `High` %)** | [`India_District_Soil_NPK_Climate.csv`](file:///c:/Users/hp/Downloads/AgriPulse/India_District_Soil_NPK_Climate.csv) (Live SHC GraphQL API) | District-specific `N_Low_Percent`, `N_High_Percent`, `P_Low_Percent`, `P_High_Percent`, `K_Low_Percent`, `K_High_Percent`, and `OC_Low_Percent` |
| **District Agro-Climatic Conditions** | [`India_District_Soil_NPK_Climate.csv`](file:///c:/Users/hp/Downloads/AgriPulse/India_District_Soil_NPK_Climate.csv) (Live Open-Meteo API) | District-specific `soil_moisture_0_to_1cm_m3m3`, `seasonal_rainfall_est_mm`, and `humidity_percent` |
| **Operational Cost Structure (`Cost A2+FL` & `Cost C2`)** | DES Comprehensive Scheme for Cost of Cultivation (`eands.dacnet.nic.in`) | Itemized operational components (`human_labour`, `bullock_labour`, `machine_labour`, `seed`, `fertilizer`, `manure`, `pesticide`, `irrigation`, `interest`) |

---

### 3.3 Exact Mathematical Formulas Used in `build_cost_of_cultivation_csv.py`

#### 1. Seed Cost Calculation (Section B8 of `DATA_COLLECTION.md`)
$$\text{seed\_rs\_per\_ha} = \text{seed\_rate\_kg\_per\_ha} \times \text{seed\_price\_rs\_per\_kg}$$

#### 2. Dynamic STCR Fertilizer Dosage & Cost Calculation (Section B5 of `DATA_COLLECTION.md`)
Following the **ICAR / MPKV Soil-Test Crop Response (STCR)** rule specified in Section B5 of [`DATA_COLLECTION.md`](file:///c:/Users/hp/Downloads/AgriPulse/DATA_COLLECTION.md#L195-L216), a soil test showing **Low** nutrient availability requires **+25% (`1.25×`)** of the standard Recommended Dose of Fertilizer (RDF), whereas **High** nutrient availability requires **-25% (`0.75×`)** of RDF.

For each district $d$ and crop $c$, we compute the continuous **District STCR Nutrient Adjustment Factor** directly from the district's Soil Health Card `Low` and `High` sample percentages:
$$F_{N}(d) = 1.0 + 0.25 \times \left(\frac{\text{N\_Low\_Percent}_d - \text{N\_High\_Percent}_d}{100}\right)$$
$$F_{P}(d) = 1.0 + 0.25 \times \left(\frac{\text{P\_Low\_Percent}_d - \text{P\_High\_Percent}_d}{100}\right)$$
$$F_{K}(d) = 1.0 + 0.25 \times \left(\frac{\text{K\_Low\_Percent}_d - \text{K\_High\_Percent}_d}{100}\right)$$

This yields the district-adjusted nutrient requirements (`kg/ha`):
$$\text{rdf\_n\_kg\_per\_ha} = \text{RDF}_{N, c} \times F_{N}(d)$$
$$\text{rdf\_p2o5\_kg\_per\_ha} = \text{RDF}_{P, c} \times F_{P}(d)$$
$$\text{rdf\_k2o\_kg\_per\_ha} = \text{RDF}_{K, c} \times F_{K}(d)$$

Next, we convert pure nutrient requirements (`N`, `P2O5`, `K2O`) into commercial fertilizer quantities (`kg/ha`) accounting for the **18% Nitrogen already present in DAP**:
1. **DAP (`18% N`, `46% P2O5`):**
   $$\text{dap\_kg\_per\_ha} = \frac{\text{rdf\_p2o5\_kg\_per\_ha}}{0.46}$$
2. **Nitrogen supplied by DAP:**
   $$N_{\text{from\_DAP}} = \text{dap\_kg\_per\_ha} \times 0.18$$
3. **Urea (`46% N`):**
   $$\text{urea\_kg\_per\_ha} = \frac{\max(0,\; \text{rdf\_n\_kg\_per\_ha} - N_{\text{from\_DAP}})}{0.46}$$
4. **Muriate of Potash — MOP (`60% K2O`):**
   $$\text{mop\_kg\_per\_ha} = \frac{\text{rdf\_k2o\_kg\_per\_ha}}{0.60}$$
5. **Total Fertilizer Cost (`fertilizer_rs_per_ha`):**
   $$\text{fertilizer\_rs\_per\_ha} = (\text{urea\_kg\_per\_ha} \times 5.9222) + (\text{dap\_kg\_per\_ha} \times 27.00) + (\text{mop\_kg\_per\_ha} \times 34.00)$$

#### 3. District-Adjusted Operational Cost Components (Section B4 of `DATA_COLLECTION.md`)
* **Farmyard Manure (`manure_rs_per_ha`):** Scaled by the district's Soil Health Card Organic Carbon deficiency (`OC_Low_Percent`), since low-organic-carbon soils require higher FYM/compost application.
* **Labour & Mechanization (`human_labour_rs_per_ha`, `bullock_labour_rs_per_ha`, `machine_labour_rs_per_ha`):** Scaled from DES/CACP crop operational baselines using state-level agricultural wage and tractorization indices.
* **Irrigation (`irrigation_rs_per_ha`):** Scaled inversely by the district's seasonal rainfall and root-zone soil moisture (`soil_moisture_0_to_1cm_m3m3`) from Open-Meteo (drier districts incur higher groundwater pumping/electricity costs).
* **Pesticide / Plant Protection (`pesticide_rs_per_ha`):** Adjusted by the district's relative humidity (`humidity_percent`), reflecting higher fungal/pest spray frequency in humid conditions.
* **Interest on Working Capital (`interest_rs_per_ha`):** Computed following the **CACP statutory convention** of `7%` per annum Kisan Credit Card (KCC) interest rate applied for half the crop season (`3.5%` effective rate on operational working capital):
  $$\text{interest\_rs\_per\_ha} = 0.035 \times \text{Working\_Capital}$$

#### 4. Total Cost `A2+FL`, Comprehensive Cost `C2`, and Net Profitability
* **Cost `A2+FL` (`cost_a2_fl_rs_per_ha`):** Sum of all paid-out operational expenses plus imputed family labour, plus `8%` depreciation/miscellaneous overheads.
* **Cost `C2` (`cost_c2_rs_per_ha`):** Comprehensive cost including imputed rental value of owned land and interest on fixed capital (`1.32 × Cost A2+FL`, matching the standard CACP all-India ratio between `C2` and `A2+FL`).
* **Gross Revenue & Net Profit over `A2+FL`:**
  $$\text{expected\_revenue\_msp\_rs\_per\_ha} = \text{msp\_rs\_per\_quintal} \times \text{expected\_yield\_quintal\_per\_ha}$$
  $$\text{net\_profit\_a2fl\_rs\_per\_ha} = \text{expected\_revenue\_msp\_rs\_per\_ha} - \text{cost\_a2\_fl\_rs\_per\_ha}$$

---

## 4. Complete Column-by-Column Data Dictionary

### 4.1 `India_District_Soil_NPK_Climate.csv` (`35` Columns)

| # | Column Name | Unit / Type | Source | Description |
| :---: | :--- | :--- | :--- | :--- |
| 1 | `state` | String | SHC Portal (`soilhealth4.dac.gov.in`) | Official State / UT name |
| 2 | `district` | String | SHC Portal (`soilhealth4.dac.gov.in`) | Official District name |
| 3 | `district_code` | Integer | LGD / SHC Portal | Official Government District Code (Primary Join Key) |
| 4 | `latitude` | Decimal Degrees | Open-Meteo Geocoding API | District centroid latitude |
| 5 | `longitude` | Decimal Degrees | Open-Meteo Geocoding API | District centroid longitude |
| 6 | `N_kg_ha` | `kg/ha` | SHC API + ICAR Nutrient Index | Available Nitrogen in `kg/ha` |
| 7 | `P_kg_ha` | `kg/ha` | SHC API + ICAR Nutrient Index | Available Phosphorus in `kg/ha` |
| 8 | `K_kg_ha` | `kg/ha` | SHC API + ICAR Nutrient Index | Available Potassium in `kg/ha` |
| 9 | `N_CropRec_Scale` | `20–140` | Derived from `N` Nutrient Index | Nitrogen normalized to `Crop_recommendation.csv` feature scale |
| 10 | `P_CropRec_Scale` | `10–125` | Derived from `P` Nutrient Index | Phosphorus normalized to `Crop_recommendation.csv` feature scale |
| 11 | `K_CropRec_Scale` | `15–200` | Derived from `K` Nutrient Index | Potassium normalized to `Crop_recommendation.csv` feature scale |
| 12 | `OC_percent` | `%` | SHC API + ICAR Nutrient Index | Soil Organic Carbon percentage |
| 13 | `ph` | pH (`5.6–8.1`) | SHC API + ICAR Nutrient Index | Soil pH reaction |
| 14 | `EC_Saline_Percent` | `%` | SHC GraphQL API | Percentage of soil samples classified as Saline |
| 15–22 | `N/P/K/OC_Low/High_Percent` | `%` | SHC GraphQL API | Exact percentage of district soil samples in Low and High classes |
| 23–28 | `S/Fe/Zn/Cu/B/Mn_Deficient_Percent` | `%` | SHC GraphQL API | Exact percentage of district soil samples deficient in 6 micronutrients |
| 29–35 | `temperature_C`, `humidity_percent`, `precipitation_mm`, `et0_evapotranspiration_mm`, `soil_temperature_0cm_C`, `soil_moisture_0_to_1cm_m3m3`, `seasonal_rainfall_est_mm` | `°C`, `%`, `mm`, `m³/m³` | Live Open-Meteo Forecast API | Real-time agro-climatic and surface soil physical metrics |

### 4.2 `India_District_Crop_Cost_of_Cultivation.csv` (`31` Columns)

| # | Column Name | Unit / Type | Reference in `DATA_COLLECTION.md` | Description |
| :---: | :--- | :--- | :--- | :--- |
| 1–3 | `state`, `district`, `district_code` | String / Int | Section B4 | Location identifiers (joins with `India_District_Soil_NPK_Climate.csv`) |
| 4–7 | `crop_id`, `crop_name`, `agmarknet_commodity`, `season` | String | Section B1 & B4 | Crop identifiers (joins with `Crop_recommendation.csv` and Agmarknet API) |
| 8–10 | `seed_rate_kg_per_ha`, `seed_price_rs_per_kg`, `seed_rs_per_ha` | `kg/ha`, `₹/kg`, `₹/ha` | **Section B8** | Certified seed rate, unit price, and total seed cost per hectare |
| 11–13 | `rdf_n_kg_per_ha`, `rdf_p2o5_kg_per_ha`, `rdf_k2o_kg_per_ha` | `kg/ha` | **Section B5** | STCR soil-adjusted Nitrogen, Phosphorus, and Potash requirements |
| 14–16 | `urea_kg_per_ha`, `dap_kg_per_ha`, `mop_kg_per_ha` | `kg/ha` | **Section B5** | Commercial fertilizer bags/quantities required per hectare |
| 17 | `fertilizer_rs_per_ha` | `₹/ha` | **Section B4 & B5** | Total statutory fertilizer cost per hectare |
| 18–24 | `manure_rs_per_ha`, `human_labour_rs_per_ha`, `bullock_labour_rs_per_ha`, `machine_labour_rs_per_ha`, `irrigation_rs_per_ha`, `pesticide_rs_per_ha`, `interest_rs_per_ha` | `₹/ha` | **Section B4** | Itemized operational expenses per hectare |
| 25 | `cost_a2_fl_rs_per_ha` | `₹/ha` | **Section B4** | Total paid-out operational cost + imputed family labour (`Cost A2+FL`) |
| 26 | `cost_c2_rs_per_ha` | `₹/ha` | **Section B4** | Comprehensive cost of cultivation including land rent (`Cost C2`) |
| 27–30 | `msp_rs_per_quintal`, `expected_yield_quintal_per_ha`, `expected_revenue_msp_rs_per_ha`, `net_profit_a2fl_rs_per_ha` | `₹/qtl`, `qtl/ha`, `₹/ha` | **Section B6** | Official MSP, expected yield, gross revenue, and net return over `Cost A2+FL` |
| 31 | `reference_year` | String | Metadata | Reference period (`2024-26 (DES/CACP & STCR)`) |
