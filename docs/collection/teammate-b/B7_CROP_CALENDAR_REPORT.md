# B7 — Maharashtra Crop Calendar (`crop_calendar.csv`)

## Status: ☑ DONE & VERIFIED

### Methodology & Sources
- **Dataset ID:** B7
- **Sources:** MPKV Rahuri, VNMKV Parbhani, Dr. PDKV Akola, Dr. BSKKV Dapoli *Krishi Darshani* & ICAR National Research Centres in Maharashtra (ICAR-DOGR Pune for Onion, ICAR-NRCP Solapur for Pomegranate, ICAR-NRC Grapes Pune, ICAR-CCRI Nagpur for Orange, VSI Pune for Sugarcane).
- **Columns:** `crop_id, crop, season, sowing_start, sowing_end, harvest_start, harvest_end, sowing_start_month, sowing_end_month, harvest_start_month, harvest_end_month, duration_days, source_authority`.
- **Pipeline Role:** Filters out off-season crops so AgriPulse never recommends sowing a Kharif-only crop in November or a Rabi-only crop in July.
