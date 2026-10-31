# B10 — AI API Keys & Multilingual Language Benchmark (`B10_REPORT.md`)

## Status: ☑ DONE & VERIFIED (`HTTP 200 OK` on All 3 Keys)

### 1. Deliverable Summary
- **Dataset / Task ID:** `B10`
- **Files in Subfolder:**
  - `llm_language_test.md` — Full benchmark table, latencies, rate limits, and verbatim Marathi/Hindi/English outputs.
  - `raw_results.json` — Raw JSON responses captured from the live API runs.
  - `B10_AI_KEYS_AND_LANGUAGE_TEST_REPORT.md` — Methodology & production configuration guide.
- **Root Security Files Created:**
  - `.env` — Contains active `SARVAM_API_KEY`, `GEMINI_API_KEY`, and `DATA_GOV_IN_API_KEY`.
  - `.env.example` — Contains key names without secret values for safe GitHub commit.
  - `.gitignore` — Excludes `.env` from version control.

### 2. Important Model IDs Discovered During Live Testing
- **Sarvam AI Chat:** `sarvam-m` is deprecated → use **`sarvam-105b-conversations`** (fast chat) or **`sarvam-105b`** (reasoning, requires `max_tokens >= 1000` because ~350 tokens are used in `reasoning_tokens`).
- **Sarvam AI Translation:** Use **`mayura:v1`** (`< 1s` response time for `en-IN` → `mr-IN` and `hi-IN`).
- **Sarvam AI Text-to-Speech (TTS):** `bulbul:v2` is deprecated → use **`bulbul:v3`** (`~3.2s` response time for 600 KB WAV audio).
- **Google Gemini:** `gemini-2.5-flash` is retired for new keys → use **`gemini-3.8-flash`**.


