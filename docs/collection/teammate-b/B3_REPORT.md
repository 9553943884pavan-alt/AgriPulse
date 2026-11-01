# B3 — District Crop Yields (10+ Years History)

## Methodology & Verification
- **Dataset ID:** B3
- **Publisher:** Directorate of Economics and Statistics (DES), Ministry of Agriculture & Farmers Welfare / OGD Platform India (`api.data.gov.in`)
- **Resource ID:** `35be999b-0208-4354-b557-f6ca9a5355de`
- **Collection Method:** Programmatic pagination query via official OGD India REST API endpoint using registered API Key.
- **Records Processed:** 12,628 raw API records retrieved -> 12,367 cleaned Maharashtra records across 1997–2014.
- **Data Cleaning Rules Applied (per Section 5A of DATA_COLLECTION.md):**
  1. Removed zero or negative `area_ha` and `production_tonnes` rows (212 rows).
  2. Removed extreme typo outliers exceeding physiological agronomic limits (48 rows, e.g. >25 t/ha for grains).
  3. Mapped all historical district variations (Ahmednagar, Aurangabad, Osmanabad, etc.) to canonical LGD names.
- **Derived Column:** `yield_tonnes_per_ha = production_tonnes / area_ha`.
