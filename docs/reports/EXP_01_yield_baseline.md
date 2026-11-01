# EXP_01: Hierarchical Median Yield Baseline (ML.3)

## 1. Overview
Evaluates the non-parametric hierarchical median lookup on an out-of-time test split.
Lookup hierarchy: `(district, crop_id, season) -> (district, crop_id) -> (crop_id, season) -> (crop_id) -> statewide median`.

## 2. Dataset & Split
- **Dataset**: `yield_training.csv` (11576 total rows across 34 agricultural districts).
- **Training period**: 1997–2011 (9889 rows).
- **Test period**: 2012–2014 (1687 rows, out-of-time).

## 3. Overall Out-of-Time Metrics
- **MAE**: 0.9245 tonnes/ha (3.74 quintals/acre)
- **RMSE**: 3.2784 tonnes/ha
- **WAPE**: 20.81%
- **R²**: 0.9585

## 4. Per-Crop Error Summary
| Crop ID | Test Samples | Baseline MAE (t/ha) | WAPE (%) | R² |
|---|---|---|---|---|
| bajra | 56 | 0.2203 | 32.65% | 0.3314 |
| blackgram | 62 | 0.1847 | 32.27% | -0.0108 |
| chickpea | 91 | 0.2109 | 27.42% | -0.0031 |
| cotton | 75 | 0.6869 | 41.53% | -0.3681 |
| groundnut | 149 | 0.3091 | 25.73% | 0.4546 |
| jowar | 149 | 0.2929 | 31.29% | 0.3784 |
| maize | 199 | 0.5953 | 33.29% | 0.3062 |
| mungbean | 86 | 0.2274 | 46.25% | -0.1043 |
| pigeonpeas | 97 | 0.2703 | 47.37% | 0.1549 |
| rice | 100 | 0.34 | 20.17% | 0.7917 |
| soybean | 84 | 0.4698 | 38.46% | 0.2472 |
| sugarcane | 79 | 12.2473 | 16.44% | 0.3931 |
| wheat | 87 | 0.3052 | 22.2% | 0.4287 |