# B9 — Crop Name Master Table (`crops_master.csv`)

## Status: ☑ DONE & VERIFIED

### Methodology & Schema
- **Dataset ID:** B9
- **Rows:** 29 total crops (26 valid Maharashtra crops + 3 non-Maharashtra Kaggle crops explicitly flagged `is_maharashtra_crop=false` per Section 3 of `DATA_COLLECTION.md`).
- **Columns:** `crop_id, display_name_en, display_name_mr, display_name_hi, kaggle_label, agmarknet_commodity, des_crop_name, season, is_maharashtra_crop`.
- **Purpose:** Acts as the central relational join table linking Stage 1 (Kaggle Classifier), Stage 2 (DES Historical Yields `B3`), Stage 3 (Agmarknet Mandi Prices `B1`/`B2`, Cost of Cultivation `B4`, Fertilizer `B5`, MSP `B6`, Crop Calendar `B7`, Seed `B8`), and Stage 4 (Marathi & Hindi names for Sarvam AI / Gemini).
