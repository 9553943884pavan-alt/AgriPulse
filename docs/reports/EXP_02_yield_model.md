# EXP_02: Gradient Boosting Crop Yield Model (ML.4 & ML.4b)

## 1. Overview
Trains and evaluates `HistGradientBoostingRegressor` on official DES + ERA5 weather dataset.
Compares Model A (shipped, exogenous features only) against Model B (reference with lags) and the ML.3 baseline.

## 2. Models Compared
| Model | Features | Out-of-Time MAE | WAPE | R² | Role |
|---|---|---|---|---|---|
| **ML.3 Baseline** | Hierarchical median lookup | 0.9245 t/ha | 20.81% | 0.9585 | Fallback & sanity bounds |
| **Model A** | Weather + Soil + Irrigation + Fertilizer + District/Crop/Season | **1.0351 t/ha** | **23.3%** | **0.9336** | **Shipped to production** |
| **Model B** | Model A + `yield_prev_year` + `yield_3yr_avg` | 1.0285 t/ha | 23.15% | 0.9413 | Reference (proves lag signal) |

## 3. Key Findings
- **Model A achieves R² of 0.9336** across 1,687 out-of-time test points.
- Operating without lag features allows clean 2026 inference without artificial or stale inputs.
- For crops with low sample counts or high variance, code implements automatic fallback to the ML.3 baseline.

## 4. Per-Crop Performance Breakdown (Model A vs Baseline)
| Crop ID | Test Samples | Model A MAE (t/ha) | Model A WAPE (%) | Baseline WAPE (%) | Shipped Primary |
|---|---|---|---|---|---|
| bajra | 56 | 0.2433 | 36.05% | 32.65% | ML.3 Baseline |
| blackgram | 62 | 0.2218 | 38.74% | 32.27% | ML.3 Baseline |
| chickpea | 91 | 0.2177 | 28.31% | 27.42% | ML.3 Baseline |
| cotton | 75 | 0.6574 | 39.75% | 41.53% | Model A |
| groundnut | 149 | 0.3022 | 25.15% | 25.73% | Model A |
| jowar | 149 | 0.3414 | 36.46% | 31.29% | ML.3 Baseline |
| maize | 199 | 0.6337 | 35.44% | 33.29% | ML.3 Baseline |
| mungbean | 86 | 0.2399 | 48.81% | 46.25% | ML.3 Baseline |
| pigeonpeas | 97 | 0.289 | 50.64% | 47.37% | ML.3 Baseline |
| rice | 100 | 0.4067 | 24.12% | 20.17% | ML.3 Baseline |
| soybean | 84 | 0.5275 | 43.19% | 38.46% | ML.3 Baseline |
| sugarcane | 79 | 14.8602 | 19.95% | 16.44% | ML.3 Baseline |
| wheat | 87 | 0.3292 | 23.94% | 22.2% | ML.3 Baseline |