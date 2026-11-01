# A7: Groundwater Level & Block Category — Data Collection & Methodology Report

**Checklist Item:** `A7` — Groundwater category + levels (`processed/groundwater_by_block.csv`)  
**Status:** ✅ **SATISFIED**  
**Data File in this Folder:** [`groundwater_by_block.csv`](file:///c:/Users/hp/Downloads/AgriPulse/Teammate_A_Checklist/A7_Groundwater_Level_Status/groundwater_by_block.csv)  
**Canonical Copy:** [`data/processed/groundwater_by_block.csv`](file:///c:/Users/hp/Downloads/AgriPulse/data/processed/groundwater_by_block.csv)

---

## 1. Official Government Sources
1. **Central Ground Water Board (CGWB), Ministry of Jal Shakti, Govt. of India:** *National Compilation on Dynamic Ground Water Resources of India (2023–24 Assessment)* (`cgwb.gov.in` / IN-GRES Portal `ingres.iith.ac.in`).
2. **Groundwater Surveys and Development Agency (GSDA), Govt. of Maharashtra:** Joint CGWB-GSDA Taluka/Watershed Ground Water Assessment & Observation Well Monitoring (`gsda.maharashtra.gov.in`).

## 2. Coverage & Categorization Rules (`71` Assessment Units)
Covers all **36 Maharashtra districts** (district-level average rows) plus **35 critical/high-stress agricultural talukas/blocks** across Western Maharashtra, Marathwada, Khandesh, and Vidarbha (such as `Rahata`, `Kopargaon`, `Sangamner`, `Morshi`, `Warud`, `Chandur Bazar`, `Raver`, `Yawal`, `Baramati`, `Indapur`, `Purandar`, `Malshiras`, `Sangola`, `Sinnar`, `Malegaon`, `Katol`, `Narkhed`, `Jath`, `Maan`).

Per CGWB statutory norms, the **Stage of Ground Water Extraction (`extraction_pct`)** is:
$$\text{Stage of Extraction (\%)} = \frac{\text{Annual Ground Water Extraction (All Uses)}}{\text{Annual Extractable Ground Water Resource}} \times 100$$
* **`Safe`:** $\le 70\%$
* **`Semi-critical`:** $> 70\%$ and $\le 90\%$
* **`Critical`:** $> 90\%$ and $\le 100\%$
* **`Over-exploited`:** $> 100\%$

## 3. How the Optimizer Uses This Table
In the AgriPulse Quadratic Programming (QP) water constraint:
* **`Safe` blocks:** Up to `100%` of the farmer's sustainable borewell/open-well yield can be allocated.
* **`Semi-critical` blocks:** Borewell extraction is capped at `75%`, and drip/sprinkler adoption is prioritized.
* **`Critical` (`>90%`) & `Over-exploited` (`>100%`) blocks:** High-water-demand perennial crops (`sugarcane`, `banana`) are penalized/restricted, shifting land allocation toward high-value low-water pulses (`chickpea`, `pigeonpeas`, `mungbean`), millets (`jowar`, `bajra`), or drip-irrigated orchards.
