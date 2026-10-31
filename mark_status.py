"""Mark completed/in-progress tasks in backend/SPECS.md and ml/SPECS.md."""
import re
import sys

NOT_STARTED = "\u2b1c"   # ⬜
IN_PROGRESS = "\U0001f7e8"  # 🟨
DONE = "\u2705"          # ✅
BLOCKED = "\u26d4"       # ⛔
DROPPED = "\u2796"       # ➖

# ── Backend SPECS ─────────────────────────────────────────────────────────────
# Verified by scanning the actual codebase 2026-10-31
BACKEND_DONE = {
    # Phase 0 setup
    "P0.5",         # skeleton, pytest, ruff, requirements.txt — confirmed
    "P0.6",         # .github/workflows/backend-ci.yml — confirmed exists
    # Contracts
    "C.1",          # 50 Pydantic types in schemas.py — confirmed
    "C.3",          # stubs.py with correct signatures — confirmed
    "C.4",          # GET /api/schemas/sse-events — confirmed
    # Data
    "DATA.1",       # 18 loaders in loaders.py — confirmed
    "DATA.2",       # resolver.py canonical names — confirmed
    "DATA.3",       # backend/tests/test_data.py — confirmed exists (15687 bytes)
    # Services
    "SVC.1",        # core/: cache, errors, http_client, timing, units — confirmed
    "SVC.2",        # services/location.py — confirmed
    "SVC.3",        # services/weather.py — confirmed
    "SVC.4",        # services/soil.py — confirmed
    "SVC.5",        # services/prices.py — confirmed
    "SVC.6",        # services/costs.py — confirmed
    "SVC.7",        # services/water.py — confirmed
    "SVC.8",        # services/district_context.py — confirmed
    "SVC.9",        # services/speech.py — confirmed
    "SVC.10",       # pipeline.py run_plan() — confirmed
    "SVC.11",       # plan store via cache.py — confirmed
    # API
    "API.1",        # E1 SSE /api/agent/chat — confirmed
    "API.2",        # E2 /api/plan — confirmed
    "API.3",        # E3 /api/plans/{id}/reoptimize — confirmed
    "API.4",        # E4 /api/threads/{id} — confirmed
    "API.5",        # E5 /api/transcribe + E6 /api/speak — confirmed
    "API.6",        # E7 /api/prefetch — confirmed
    "API.7",        # E8 /api/locations/search + E9 /api/districts + E10 context — confirmed
    "API.8",        # E11 /api/sources + E12 /api/sources/health — confirmed
    "API.9",        # E13 /api/health — confirmed
    "API.10",       # errors, CORS, size limits — confirmed
}
# P0.1,P0.2,P0.3,P0.4 = admin/data-intake tasks, not code — genuinely not started
# C.2 = docs/API_CONTRACT.md + api_examples/ — not created yet
# SVC.8b = CWC bulletin refresh script — ml/data_prep/build_reservoir_from_bulletin.py exists (93 lines, implemented)
BACKEND_DONE.add("SVC.8b")   # build_reservoir_from_bulletin.py confirmed implemented

# ── ML SPECS ──────────────────────────────────────────────────────────────────
# Verified by scanning app/ml/ and stubs.py
ML_DONE = {
    # Agent — all 10 nodes fully implemented
    "AG.1",         # agent/client.py (Sarvam chat) — confirmed
    "AG.2",         # agent/tools.py — confirmed
    "AG.3",         # agent/nodes.py extract_profile — confirmed
    "AG.4",         # agent/nodes.py ask_missing — confirmed
    "AG.5",         # agent/graph.py full graph — confirmed
    "AG.6",         # agent/nodes.py relax_constraint — confirmed
    "AG.7",         # agent/memory.py AsyncSqliteSaver — confirmed
    "AG.8",         # agent/nodes.py explain — confirmed
    "AG.9",         # agent/grounding.py — confirmed
    "AG.10",        # agent/templates.py fallback — confirmed
    # ML functions — real implementations confirmed in app/ml/
    "ML.1",         # app/ml/suitability.py (10866 bytes, 11 functions) — confirmed real
    "ML.7",         # app/ml/water_need.py (8203 bytes, 8 functions) — confirmed real
    "ML.8",         # app/ml/fertilizer.py (7630 bytes, 10 functions) — confirmed real
    # Optimizer — all 5 confirmed real in app/ml/optimizer.py (31297 bytes, 18 functions)
    "OPT.1",        # LP HiGHS — confirmed
    "OPT.2",        # QP CVXPY — confirmed
    "OPT.3",        # 4 strategies — confirmed
    "OPT.4",        # infeasibility report — confirmed
    "OPT.5",        # impact metrics — confirmed
}
ML_IN_PROGRESS = {
    # Scenario yields stub exists but NotImplementedError (needs ML.4 + ML.5)
    "ML.6",
}
ML_NOT_STARTED = {
    # All need yield_training.csv cleaned (ML.2) + weather archive (ML.5)
    "ML.2",         # data cleaning script (yield_training.csv) — not run yet
    "ML.3",         # hierarchical median yield baseline — not yet
    "ML.4",         # gradient boosting yield model — not yet
    "ML.4b",        # SHAP suitability — not yet
    "ML.5",         # climate scenarios P10/P50/P90 — no full weather archive yet
    "ML.9",         # experiment reports — not yet
    "QA.3",         # demo script 3 farmer stories — not yet
    "DD.5",         # README final setup — not yet
    "DD.6",         # slide deck — not yet
}


def patch_row(line: str, task_id: str, done_set, ip_set, ns_set) -> str:
    """Replace the trailing status emoji for a matching task row."""
    # Match "| ID |" at start of line (with possible leading whitespace)
    stripped = line.strip()
    if not re.match(rf"^\| {re.escape(task_id)}\b", stripped):
        return line

    # Determine new status
    if task_id in done_set:
        new_status = DONE
    elif task_id in ip_set:
        new_status = IN_PROGRESS
    elif task_id in ns_set:
        new_status = NOT_STARTED
    else:
        return line

    # Replace any existing status emoji at end of line (inside last | cell)
    new_line = re.sub(
        r"[\u2b1c\u2705\u26d4\u2796\U0001f7e8]",
        new_status,
        line,
    )
    return new_line


def process_file(path: str, done_set, ip_set=None, ns_set=None):
    ip_set = ip_set or set()
    ns_set = ns_set or set()
    all_ids = done_set | ip_set | ns_set

    with open(path, encoding="utf-8") as f:
        lines = f.readlines()

    new_lines = []
    changed = 0
    for line in lines:
        original = line.rstrip("\n")
        patched = original
        for task_id in all_ids:
            result = patch_row(original, task_id, done_set, ip_set, ns_set)
            if result != original:
                patched = result
                changed += 1
                break
        new_lines.append(patched + "\n")

    with open(path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

    print(f"{path}: {changed} rows updated")


# Run
process_file(
    r"C:\Users\hp\Downloads\AgriPulse-main\backend\SPECS.md",
    done_set=BACKEND_DONE,
    ip_set=set(),
    ns_set=set(),
)

process_file(
    r"C:\Users\hp\Downloads\AgriPulse-main\ml\SPECS.md",
    done_set=ML_DONE,
    ip_set=ML_IN_PROGRESS,
    ns_set=ML_NOT_STARTED,
)

# Verify
print("\n=== Backend SPECS status ===")
with open(r"C:\Users\hp\Downloads\AgriPulse-main\backend\SPECS.md", encoding="utf-8") as f:
    for line in f:
        if re.match(r"^\| (P0|C\.|DATA|SVC|API|QA|DD)\.", line):
            task = re.match(r"^\| (\S+) \|", line)
            tid = task.group(1) if task else "?"
            status = DONE if DONE in line else IN_PROGRESS if IN_PROGRESS in line else NOT_STARTED if NOT_STARTED in line else "?"
            print(f"  {tid:10} {status}")

print("\n=== ML SPECS status ===")
with open(r"C:\Users\hp\Downloads\AgriPulse-main\ml\SPECS.md", encoding="utf-8") as f:
    for line in f:
        if re.match(r"^\| (ML\.|OPT\.|AG\.)", line):
            task = re.match(r"^\| (\S+) \|", line)
            tid = task.group(1) if task else "?"
            status = DONE if DONE in line else IN_PROGRESS if IN_PROGRESS in line else NOT_STARTED if NOT_STARTED in line else "?"
            print(f"  {tid:10} {status}")
