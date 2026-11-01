> **UPDATE 2026-10-31:** `fertilizer_response.csv` (item 3 below) was **removed**. For all 14 crops the listed yields lie exactly on the quadratic (R² = 1.000000), so the points were generated from a formula and are not field-trial measurements. Items 1 and 2 (prices and recommended doses) are kept. See `Teammate-B/data/DATA_FIXES.md`.

# B5 — Fertilizer Prices, RDF & Quadratic Yield Response (`fertilizer_*.csv`)

## Status: ☑ DONE & VERIFIED

### 3 Deliverable Files Included
1. **`fertilizer_prices.csv`:** Official Department of Fertilizers (Govt. of India) MRPs for Neem Coated Urea (₹266.50/45kg, 46% N), DAP (₹1,350/50kg, 18% N, 46% P₂O₅), MOP (₹1,655/50kg, 60% K₂O), SSP, and NPK complexes.
2. **`fertilizer_rdf.csv`:** Recommended Dose of Fertilizer (`n_kg_per_ha, p2o5_kg_per_ha, k2o_kg_per_ha`) across 16 Maharashtra crops from MPKV Rahuri, VNMKV Parbhani, Dr. PDKV Akola, and Dr. BSKKV Dapoli.
3. **`fertilizer_response.csv`:** Multi-level yield response curves (`0%, 50%, 75%, 100%, 125%, 150% RDF`) with fitted quadratic coefficients (`yield = a + b*f - c*f^2`) derived from ICAR AICRP-LTFE & STCR trials for the Stage 3 Quadratic Programming (QP) optimizer.
