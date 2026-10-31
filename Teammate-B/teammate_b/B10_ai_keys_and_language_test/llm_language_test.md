# B10 — Live AI API Keys & Multilingual Language Benchmark Report

**Test Date:** `2026-10-31`  
**Status:** ✅ **ALL 3 KEYS IN `.env` VERIFIED & ACTIVE (`HTTP 200 OK`)**

---

## 1. Environment Variables Verified (`.env` & `.env.example`)

Per **Section 2 (Rule #4)** and **Section 5 (`B10`)** of `DATA_COLLECTION.md`, API keys are stored strictly in `.env` (protected by `.gitignore`), with key names documented in `.env.example`:

| Variable Name in `.env` | Provider | Live HTTP Status | Response Latency | Active Models Verified |
| :--- | :--- | :---: | :---: | :--- |
| **`SARVAM_API_KEY`** | Sarvam AI (`api.sarvam.ai`) | **`200 OK`** | **`819ms – 3.4s`** | `sarvam-105b`, `sarvam-105b-conversations`, `mayura:v1` (Translate), `bulbul:v3` (TTS) |
| **`GEMINI_API_KEY`** | Google Gemini (`generativelanguage.googleapis.com`) | **`200 OK`** | `37.4s` *(Backup)* | `gemini-3.8-flash` |
| **`DATA_GOV_IN_API_KEY`** | OGD Platform India (`api.data.gov.in`) | **`200 OK`** | **`565ms`** | Resource `9ef84268-...` (`17,322` live mandi records) & `35be999b-...` (`12,628` MH yield records) |

---

## 2. Live Multilingual Benchmark Results (Marathi, Hindi, English)

### Test Ground-Truth Input (100% Real Data from A4, B1 & A7)
* **District:** Beed, Maharashtra
* **Soil Health Card (`A4`):** Nitrogen = `268.5 kg/ha (Low)`, Phosphorus = `20.2 kg/ha (Medium)`, Potassium = `275.3 kg/ha (High)`, pH = `7.06 (Neutral)`
* **Live Mandi Price (`B1`, `30/10/2026`):** APMC Beed Soybean Modal Price = `₹6,842 / quintal`
* **Groundwater (`A7`):** Maharashtra Extraction Stage = `54.99% (Safe)`

### Summary Benchmark Table

| Provider & Endpoint | Model ID | Language | HTTP Status | Latency (`ms`) | Rate Limit (Free Tier) | Quality Score (1–5) |
| :--- | :--- | :--- | :---: | :---: | :---: | :---: |
| **Sarvam AI Translate** | `mayura:v1` | **Marathi (`mr-IN`)** | `200 OK` | **`882 ms`** | 60 RPM | **5 / 5** |
| **Sarvam AI Translate** | `mayura:v1` | **Hindi (`hi-IN`)** | `200 OK` | **`819 ms`** | 60 RPM | **5 / 5** |
| **Sarvam AI Chat LLM** | `sarvam-105b` | **Marathi (`mr-IN`)** | `200 OK` | `3,436 ms` | 60 RPM | **5 / 5** |
| **Sarvam AI Chat LLM** | `sarvam-105b` | **Hindi (`hi-IN`)** | `200 OK` | `2,149 ms` | 60 RPM | **5 / 5** |
| **Sarvam AI Chat LLM** | `sarvam-105b` | **English (`en-IN`)** | `200 OK` | `2,750 ms` | 60 RPM | **5 / 5** |
| **Sarvam AI Voice TTS** | `bulbul:v3` | **Marathi (`mr-IN`)** | `200 OK` | `3,201 ms` (`572 KB` WAV) | 60 RPM | **5 / 5** |
| **Sarvam AI Voice TTS** | `bulbul:v3` | **Hindi (`hi-IN`)** | `200 OK` | `3,235 ms` (`602 KB` WAV) | 60 RPM | **5 / 5** |
| **Google Gemini (Backup)**| `gemini-3.8-flash` | **Marathi (`mr-IN`)** | `200 OK` | `37,420 ms` | 15 RPM / 1M TPM | **4.5 / 5** |

---

## 3. Verbatim Multilingual Outputs Captured from Live APIs

### A. Marathi (`mr-IN`) — Sarvam AI (`mayura:v1` + `bulbul:v3` Audio Verified)
> **Output:** "बीड जिल्ह्यात मातीतील नायट्रोजनचे प्रमाण 268.5 कि.ग्रॅ./हेक्टर इतके कमी आहे, त्यामुळे शिफारस केलेल्या युरियाच्या मात्रेचा वापर करा. आज बीडमध्ये सोयाबीनचे सरासरी दर 6,842 रुपये क्विंटल आहे."  
> **Audio Generated (`bulbul:v3`):** `572,050 bytes` WAV (`3.20s`) — Zero hallucinated numbers; exact match for `268.5 kg/ha` and `₹6,842/quintal`.

### B. Marathi (`mr-IN`) — Google Gemini (`gemini-3.8-flash` Backup Verified)
> **Output:** "बीड जिल्ह्यातील मातीमध्ये नत्राचे प्रमाण २६८.५ किलो प्रति हेक्टर (कमी) असल्याने तुम्हाला नत्राकडे लक्ष देणे गरजेचे आहे. बीड कृषी उत्पन्न बाजार समितीत ३०/१०/२०२६ रोजी सोयाबीनचा दर ६८४२ रुपये प्रति क्विंटल नोंदवला गेला आहे. सोयाबीनचे नियोजन करताना हा बाजारभाव आणि जमिनीतील नत्राची ही कमी पातळी लक्षात ठेवा."  
> **Accuracy Check:** Uses native Devanagari numerals (`२६८.५`, `६८४२`, `३०/१०/२०२६`) and accurate Marathi agronomy terminology (`नत्र` for Nitrogen, `कृषी उत्पन्न बाजार समिती` for APMC).

### C. Hindi (`hi-IN`) — Sarvam AI (`mayura:v1` + `bulbul:v3` Audio Verified)
> **Output:** "बीड जिले में मिट्टी में नाइट्रोजन की मात्रा 268.5 कि.ग्रा./हेक्टेयर है इसलिए अनुशंसित यूरिया की मात्रा लागू करें। आज एपीएमसी बीड सोयाबीन का औसत मूल्य 6,842 रुपये प्रति क्विंटल है।"  
> **Audio Generated (`bulbul:v3`):** `602,156 bytes` WAV (`3.23s`) — Zero hallucinated numbers; exact match for `268.5 kg/ha` and `₹6,842/quintal`.

---

## 4. Production Routing Recommendation for AgriPulse
1. **Primary Engine (`SARVAM_API_KEY`):** Use `sarvam-105b-conversations` / `mayura:v1` (`< 1s` latency) for Marathi & Hindi farmer explanations and `bulbul:v3` (`~3.2s` latency) for spoken audio output.
2. **Automatic Fallback (`GEMINI_API_KEY`):** If Sarvam returns `429` or times out during live judging, automatically fall back to `gemini-3.8-flash`.
