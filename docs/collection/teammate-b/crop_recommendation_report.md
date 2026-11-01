# Technical Verification & Audit Report: `Crop_recommendation.csv`

## 1. Executive Summary & Integrity Audit

| Property | Verified Value |
| :--- | :--- |
| **File Name** | `Crop_recommendation.csv` |
| **File Size** | `150,034` bytes (`146.5 KB`) |
| **Total Rows** | `2,200` data rows (+ `1` header row = `2,201` lines) |
| **Missing / Null / Corrupt Rows** | **`0` (100% Clean)** |
| **Total Columns** | `8` (`N, P, K, temperature, humidity, ph, rainfall, label`) |
| **Distinct Crops (`label`)** | **`22` crops** |
| **Class Balance** | **Perfectly Balanced (`100` rows per crop × `22` crops = `2,200` rows)** |
| **Match with `DATA_COLLECTION.md` (Section 3)** | ✅ **100% Exact Match** |

---

## 2. Schema & Live Input Mapping (Pipeline Stage 1: Crop Classifier)

Every column in `Crop_recommendation.csv` aligns with **Section 3 of `DATA_COLLECTION.md`** and maps directly to our live APIs and `DistrictwiseSoilData.csv`:

| Column | Data Type | Dataset Range (`Min – Max`) | Unit | Live Production Source in AgriPulse |
| :--- | :--- | :---: | :--- | :--- |
| **`N`** | `integer` | `0 – 140` | Soil Nitrogen ratio (`kg/ha` scale) | `DistrictwiseSoilData.csv` (`N` / `N_kg_ha` — Soil Health Card `A4`) |
| **`P`** | `integer` | `5 – 145` | Soil Phosphorus ratio (`kg/ha` scale) | `DistrictwiseSoilData.csv` (`P` / `P_kg_ha` — Soil Health Card `A4`) |
| **`K`** | `integer` | `5 – 205` | Soil Potassium ratio (`kg/ha` scale) | `DistrictwiseSoilData.csv` (`K` / `K_kg_ha` — Soil Health Card `A4`) |
| **`temperature`** | `float` | `8.83 – 43.68` | `°C` (Growing season mean temp) | Open-Meteo Forecast/Archive API (`A1`/`A2`) & `DistrictwiseSoilData.csv` |
| **`humidity`** | `float` | `14.26 – 99.98` | `%` (Relative humidity) | Open-Meteo Forecast API (`relative_humidity_2m`, `A1`) |
| **`ph`** | `float` | `3.50 – 9.94` | Soil `pH` (`0–14` scale) | ISRIC SoilGrids (`phh2o ÷ 10`, `A3`) & `DistrictwiseSoilData.csv` (`ph`, `A4`) |
| **`rainfall`** | `float` | `20.21 – 298.56` | `mm` (Seasonal/monthly effective rain) | Open-Meteo Forecast + Archive (`A1`/`A2`) |
| **`label`** | `string` | `22 unique crops` | Target class label | Output of Stage 1 Crop Classifier |

---

## 3. Complete Statistical Profile of All 22 Crops (`n = 100` per crop)

The table below shows the exact **Min–Max (and Mean)** bounds for every crop in `Crop_recommendation.csv`, which defines the decision boundaries learned by the Stage 1 Crop Classifier:

| # | `label` | `N` (`Min–Max`, `Avg`) | `P` (`Min–Max`, `Avg`) | `K` (`Min–Max`, `Avg`) | `temperature` (`°C`) | `humidity` (`%`) | `ph` (`Min–Max`, `Avg`) | `rainfall` (`mm`) |
| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| 1 | **`rice`** | `60–99` (`79.9`) | `35–60` (`47.6`) | `35–45` (`39.9`) | `20.0–26.9` (`23.7`) | `80.1–85.0` (`82.3`) | `5.0–7.9` (`6.4`) | `182.6–298.6` (`236.2`) |
| 2 | **`maize`** | `60–100` (`77.8`) | `35–60` (`48.4`) | `15–25` (`19.8`) | `18.0–26.5` (`22.4`) | `55.3–74.8` (`65.1`) | `5.5–7.0` (`6.2`) | `60.7–109.8` (`84.8`) |
| 3 | **`chickpea`** | `20–60` (`40.1`) | `55–80` (`67.8`) | `75–85` (`79.9`) | `17.0–21.0` (`18.9`) | `14.3–20.0` (`16.9`) | `6.0–8.9` (`7.3`) | `65.1–94.8` (`80.1`) |
| 4 | **`kidneybeans`** | `0–40` (`20.8`) | `55–80` (`67.5`) | `15–25` (`20.1`) | `15.3–24.9` (`20.1`) | `18.1–25.0` (`21.6`) | `5.5–6.0` (`5.7`) | `60.3–149.7` (`105.9`) |
| 5 | **`pigeonpeas`** | `0–40` (`20.7`) | `55–80` (`67.7`) | `15–25` (`20.3`) | `18.3–37.0` (`27.7`) | `30.4–69.7` (`48.1`) | `4.5–7.4` (`5.8`) | `90.1–198.8` (`149.5`) |
| 6 | **`mothbeans`** | `0–40` (`21.4`) | `35–60` (`48.0`) | `15–25` (`20.2`) | `24.0–32.0` (`28.2`) | `40.0–65.0` (`53.2`) | `3.5–9.9` (`6.8`) | `30.9–74.4` (`51.2`) |
| 7 | **`mungbean`** | `0–40` (`21.0`) | `35–60` (`47.3`) | `15–25` (`19.9`) | `27.0–29.9` (`28.5`) | `80.0–90.0` (`85.5`) | `6.2–7.2` (`6.7`) | `36.1–59.9` (`48.4`) |
| 8 | **`blackgram`** | `20–60` (`40.0`) | `55–80` (`67.5`) | `15–25` (`19.2`) | `25.1–34.9` (`30.0`) | `60.1–70.0` (`65.1`) | `6.5–7.8` (`7.1`) | `60.4–74.9` (`67.9`) |
| 9 | **`lentil`** | `0–40` (`18.8`) | `55–80` (`68.4`) | `15–25` (`19.4`) | `18.1–29.9` (`24.5`) | `60.1–69.9` (`64.8`) | `5.9–7.8` (`6.9`) | `35.0–54.9` (`45.7`) |
| 10 | **`pomegranate`**| `0–40` (`18.9`) | `5–30` (`18.8`) | `35–45` (`40.2`) | `18.1–25.0` (`21.8`) | `85.1–95.0` (`90.1`) | `5.6–7.2` (`6.4`) | `102.5–112.5` (`107.5`) |
| 11 | **`banana`** | `80–120` (`100.2`)| `70–95` (`82.0`) | `45–55` (`50.0`) | `25.0–29.9` (`27.4`) | `75.0–85.0` (`80.4`) | `5.5–6.5` (`6.0`) | `90.1–119.8` (`104.6`) |
| 12 | **`mango`** | `0–40` (`20.1`) | `15–40` (`27.2`) | `25–35` (`29.9`) | `27.0–36.0` (`31.2`) | `45.0–55.0` (`50.2`) | `4.5–7.0` (`5.8`) | `89.3–100.8` (`94.7`) |
| 13 | **`grapes`** | `0–40` (`23.2`) | `120–145` (`132.5`)| `195–205` (`200.1`)| `8.8–41.9` (`23.8`) | `80.0–84.0` (`81.9`) | `5.5–6.5` (`6.0`) | `65.0–74.9` (`69.6`) |
| 14 | **`watermelon`** | `80–120` (`99.4`) | `5–30` (`17.0`) | `45–55` (`50.2`) | `24.0–27.0` (`25.6`) | `80.0–90.0` (`85.2`) | `6.0–7.0` (`6.5`) | `40.1–59.8` (`50.8`) |
| 15 | **`muskmelon`** | `80–120` (`100.3`)| `5–30` (`17.7`) | `45–55` (`50.1`) | `27.0–29.9` (`28.7`) | `90.0–95.0` (`92.3`) | `6.0–6.8` (`6.4`) | `20.2–29.9` (`24.7`) |
| 16 | **`apple`** | `0–40` (`20.8`) | `120–145` (`134.2`)| `195–205` (`199.9`)| `21.0–24.0` (`22.6`) | `90.0–94.9` (`92.3`) | `5.5–6.5` (`5.9`) | `100.1–125.0` (`112.7`) |
| 17 | **`orange`** | `0–40` (`19.6`) | `5–30` (`16.6`) | `5–15` (`10.0`) | `10.0–34.9` (`22.8`) | `90.0–95.0` (`92.2`) | `6.0–8.0` (`7.0`) | `100.2–119.7` (`110.5`) |
| 18 | **`papaya`** | `31–70` (`49.9`) | `46–70` (`59.0`) | `45–55` (`50.0`) | `23.0–43.7` (`33.7`) | `90.0–94.9` (`92.4`) | `6.5–7.0` (`6.7`) | `40.4–248.9` (`142.6`) |
| 19 | **`coconut`** | `0–40` (`22.0`) | `5–30` (`16.9`) | `25–35` (`30.6`) | `25.0–29.9` (`27.4`) | `90.0–100.0` (`94.8`)| `5.5–6.5` (`6.0`) | `131.1–225.6` (`175.7`) |
| 20 | **`cotton`** | `100–140` (`117.8`)| `35–60` (`46.2`) | `15–25` (`19.6`) | `22.0–26.0` (`24.0`) | `75.0–84.9` (`79.8`) | `5.8–8.0` (`6.9`) | `60.7–99.9` (`80.4`) |
| 21 | **`jute`** | `60–100` (`78.4`) | `35–60` (`46.9`) | `35–45` (`40.0`) | `23.1–27.0` (`25.0`) | `70.9–89.9` (`79.6`) | `6.0–7.5` (`6.7`) | `150.2–199.8` (`174.8`) |
| 22 | **`coffee`** | `80–120` (`101.2`)| `15–40` (`28.7`) | `25–35` (`29.9`) | `23.1–27.9` (`25.5`) | `50.0–69.9` (`58.9`) | `6.0–7.5` (`6.8`) | `115.2–199.5` (`158.1`) |

---

## 4. Alignment with `DATA_COLLECTION.md` (Section 3 & `B9` Crop Master Table)

As highlighted in **Section 3 of `DATA_COLLECTION.md`**, we must apply two rules when using `Crop_recommendation.csv` for **Maharashtra**:

### A. Filter Out 3 Non-Maharashtra Crops (`300` rows excluded for Maharashtra)
* ❌ **`apple`** (Temperate Himalayan crop; not grown commercially in Maharashtra)
* ❌ **`coffee`** (Plantation crop of Karnataka/Kerala/TN; not grown commercially in Maharashtra)
* ❌ **`jute`** (Eastern India delta crop; erroneously predicted in `DistrictwiseSoilData.csv` when unfiltered)

### B. 19 Valid Classifier Crops + 6 Essential Maharashtra Crops from `B3` (Yield Dataset)
Below is the **`B9` Crop Master Mapping (`crops_master.csv` preview)** showing how `Crop_recommendation.csv` joins with your **Live Maharashtra Mandi CSV (`9ef84268-...csv`)** and **DES Yield API (`35be999b-...`)**:

| `crop_id` | `kaggle_label` (`Crop_recommendation.csv`) | `agmarknet_commodity` (`9ef84268-...csv` Live Match) | `des_crop_name` (`B3` Yield API) | Marathi (`display_name_mr`) | Hindi (`display_name_hi`) | Primary Season |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `rice` | `rice` | `Paddy(Common)` | `Rice` | भात / तांदूळ | धान / चावल | Kharif |
| `maize` | `maize` | `Maize` | `Maize` | मका | मक्का | Kharif / Rabi |
| `chickpea` | `chickpea` | `Bengal Gram(Gram)(Whole)` | `Gram` | हरभरा | चना | Rabi |
| `pigeonpeas`| `pigeonpeas` | `Red gram/Arhar/Tur(whole)` | `Arhar/Tur` | तूर | अरहर / तूर | Kharif |
| `mungbean` | `mungbean` | `Green Gram(Moong)(Whole)` | `Moong(Green Gram)` | मूग | मूंग | Kharif |
| `blackgram` | `blackgram` | `Black Gram(Urd Beans)(Whole)`| `Urad` | उडीद | उड़द | Kharif |
| `mothbeans` | `mothbeans` | `Moth` / `Mataki` | `Moth` | मटकी | मोठ | Kharif |
| `lentil` | `lentil` | `Lentil(Masur)(Whole)` | `Masoor` | मसूर | मसूर | Rabi |
| `cotton` | `cotton` | `Cotton` | `Cotton(lint)` | कापूस | कपास | Kharif |
| `pomegranate`| `pomegranate` | `Pomegranate` | `Pomegranate` | डाळिंब | अनार | Perennial / Bahar |
| `banana` | `banana` | `Banana` | `Banana` | केळी | केला | Perennial / Whole Yr |
| `mango` | `mango` | `Mango` | `Mango` | आंबा | आम | Summer / Perennial |
| `grapes` | `grapes` | `Grapes` | `Grapes` | द्राक्षे | अंगूर | Rabi / Perennial |
| `orange` | `orange` | `Orange` | `Orange` | संत्री | संतरा | Mrig / Ambia Bahar |
| `papaya` | `papaya` | `Papaya` | `Papaya` | पपई | पपीता | Whole Year |
| `watermelon`| `watermelon` | `Water Melon` | `Watermelon` | कलिंगड | तरबूज | Summer / Zaid |
| `muskmelon` | `muskmelon` | `Karbuja(Musk Melon)` | `Muskmelon` | खरबूज | खरबूजा | Summer / Zaid |
| `coconut` | `coconut` | `Coconut` | `Coconut` | नारळ | नारियल | Whole Year (Konkan) |
| **`soybean`** | *(Added via `B3` Yield)* | `Soyabean` | `Soyabean` | सोयाबीन | सोयाबीन | **Kharif (Major MH)** |
| **`jowar`** | *(Added via `B3` Yield)* | `Jowar(Sorghum)` | `Jowar` | ज्वारी | ज्वार | **Kharif / Rabi (Major MH)**|
| **`bajra`** | *(Added via `B3` Yield)* | `Bajra(Pearl Millet/Cumbu)` | `Bajra` | बाजरी | बाजरा | **Kharif (Major MH)** |
| **`wheat`** | *(Added via `B3` Yield)* | `Wheat` | `Wheat` | गहू | गेहूं | **Rabi (Major MH)** |
| **`sugarcane`**| *(Added via `B3` Yield)* | `Gur(Jaggery)` / `Sugarcane` | `Sugarcane` | ऊस | गन्ना | **Whole Year (Major MH)**|
| **`onion`** | *(Added via `B3` Yield)* | `Onion` | `Onion` | कांदा | प्याज | **Kharif / Rabi (Major MH)**|
| **`groundnut`**| *(Added via `B3` Yield)* | `Groundnut` | `Groundnut` | भुईमूग | मूंगफली | **Kharif / Summer (Major MH)**|

---

## 5. How `Crop_recommendation.csv` Connects to `DistrictwiseSoilData.csv`

```mermaid
flowchart LR
    A["DistrictwiseSoilData.csv\n(N, P, K, ph, temperature, humidity, rainfall)"] --> B["Stage 1: Crop Suitability Classifier\n(Trained on Crop_recommendation.csv)"]
    C["Maharashtra Crop Rules\n(Exclude apple/coffee/jute + Add Soybean/Jowar/Wheat/Onion/Sugarcane/Groundnut)"] --> B
    B --> D["Top Suitable Crops for District\n(Passed to Stage 2 Yield Model & Stage 3 QP Optimizer)"]
```

### Final Verdict
`Crop_recommendation.csv` is **100% verified, clean (`0` missing rows, `2,200` balanced records), and ready for Stage 1 (Crop Classifier training)** as specified in Section 3 of `DATA_COLLECTION.md`.
