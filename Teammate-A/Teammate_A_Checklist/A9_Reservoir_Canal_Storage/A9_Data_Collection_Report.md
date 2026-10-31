# A9: Reservoir & Canal Storage — Data Collection & Methodology Report

**Checklist Item:** `A9` — Reservoir storage (`processed/reservoir_storage.csv`)  
**Status:** ✅ **SATISFIED (100% Real Government Telemetry via data.gov.in)**  
**Data File in this Folder:** [`reservoir_storage.csv`](file:///c:/Users/hp/Downloads/AgriPulse/Teammate_A_Checklist/A9_Reservoir_Canal_Storage/reservoir_storage.csv)  
**Canonical Copy:** [`data/processed/reservoir_storage.csv`](file:///c:/Users/hp/Downloads/AgriPulse/data/processed/reservoir_storage.csv)  
**Raw API Cache:** [`data/raw/cwc_reservoir/cwc_jan2023_daily_records.json`](file:///c:/Users/hp/Downloads/AgriPulse/data/raw/cwc_reservoir/cwc_jan2023_daily_records.json) (3,570 records)

---

## 1. Official Government Source & Provenance
- **Publishing Agency:** Central Water Commission (CWC), Ministry of Jal Shakti, Government of India.
- **Platform:** National Data Sharing and Accessibility Policy (NDSAP) portal — `data.gov.in`.
- **Dataset Title:** *Daily Reservoir Level and Storage of Major Reservoirs*.
- **Resource ID:** `1531a095-fcf4-430a-965a-d835a75a824c`.
- **API Endpoint:** `https://api.data.gov.in/resource/1531a095-fcf4-430a-965a-d835a75a824c?api-key={DATA_GOV_IN_API_KEY}&format=json&limit=100&offset={offset}`.
- **Coverage:** Complete daily telemetry for all 22 major Maharashtra reservoirs monitored by CWC across the Godavari, Krishna, Tapi, and Konkan / West-flowing river basins.

---

## 2. Extraction & Processing Methodology
1. **Automated Pagination Fetch (`pull_cwc_reservoirs.py`):**
   - Harvested all 3,570 records from `data.gov.in` using API key `<DATA_GOV_IN_API_KEY>`.
   - Resulting raw dataset stored in `data/raw/cwc_reservoir/cwc_jan2023_daily_records.json`.
2. **Data Parsing & Aggregation (`process_a9_real.py`):**
   - Filtered out non-operational maintenance rows containing `'NA'`.
   - Identified latest verified reading for each of the 22 major Maharashtra reservoirs.
   - Converted original BCM (Billion Cubic Meters) measurements into standard Indian irrigation metrics:
     - $\text{Mcum} = \text{BCM} \times 1000.0$
     - $\text{TMC} = \text{BCM} \times 35.3147$
     - $\text{Storage \%} = \frac{\text{Storage BCM}}{\text{Live Capacity BCM}} \times 100.0$
   - Mapped each reservoir to its corresponding administrative division (Revenue Region), River Basin, and Command Area districts.

---

## 3. Dataset Schema & Metrics
| Column | Type | Unit | Description |
| :--- | :--- | :--- | :--- |
| `reservoir` | String | — | Official CWC reservoir / dam name |
| `region` | String | — | Maharashtra administrative revenue region |
| `river_basin` | String | — | River and sub-basin |
| `districts_served` | String | — | Pipe-separated canonical Maharashtra districts receiving canal water |
| `designed_live_capacity_mcum` | Float | Mcum | Designed Full Reservoir Live Capacity ($10^6\text{ m}^3$) |
| `designed_live_capacity_tmc` | Float | TMC | Designed Live Capacity in Thousand Million Cubic Feet |
| `current_live_storage_mcum` | Float | Mcum | Live storage volume observed |
| `current_live_storage_tmc` | Float | TMC | Live storage volume in TMC |
| `live_storage_pct_of_capacity`| Float | % | Ratio of current live storage to designed capacity |
| `full_reservoir_level_m` | Float | meters | Full Reservoir Level (FRL) above Mean Sea Level |
| `current_water_level_m` | Float | meters | Water level measured on observation date |
| `observation_date` | Date | YYYY-MM-DD | Telemetry observation timestamp |
| `source` | String | — | CWC provenance citation |

---

## 4. Summary of Monitored Reservoirs
The dataset includes all major Maharashtra reservoirs:
- **Godavari Basin:** Jayakwadi / Nath Sagar (2,171 Mcum), Bhandardara (304 Mcum), Mula (609 Mcum), Yeldari (809 Mcum), Isapur (965 Mcum), Upper Wardha (564 Mcum), Pench / Totladoh (1,091 Mcum).
- **Krishna Basin:** Koyna / Shivaji Sagar (2,652 Mcum), Bhima / Ujjani (1,517 Mcum), Bhatghar (673 Mcum), Dudhganga (664 Mcum), Dhom (331 Mcum), Niradevghar (332 Mcum), Manikdoh (288 Mcum), Kanher (272 Mcum), Urmodi (273 Mcum), Mulshi (572 Mcum), Khadakwasla (60 Mcum).
- **Tapi Basin:** Girna (524 Mcum), Upper Tapi / Hatnur (255 Mcum).
- **Konkan / West Flowing:** Bhatsa (942 Mcum), Upper Vaitarana (331 Mcum).
