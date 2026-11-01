"""Live E2E scenario harness for POST /api/plan.

Run (from repo root):
    backend/.venv/Scripts/python.exe backend/tests/e2e_scenarios/run_scenarios.py [--base URL] [--only name,name]

Checks invariants only (no expected outputs). Writes raw JSON to results/<name>.json
and a table to results/SUMMARY.md. Exit code 1 if any scenario is FAIL.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

import httpx

HERE = Path(__file__).parent
RESULTS = HERE / "results"
BASE = "http://127.0.0.1:8000"
SCEN = ("drought", "normal", "excess")


# ----------------------------------------------------------------- helpers
def close(a, b, rel=0.01, abs_=1.0):
    return abs(a - b) <= max(abs_, rel * max(abs(a), abs(b)))


def post_plan(base, profile, timeout=120, retry_s=60):
    """POST with retry on connection errors (server may be restarting)."""
    t0 = time.time()
    last = None
    while True:
        try:
            r = httpx.post(f"{base}/api/plan", json=profile, timeout=timeout)
            return r, None
        except (httpx.ConnectError, httpx.ReadError, httpx.RemoteProtocolError, httpx.ConnectTimeout) as e:
            last = e
            if time.time() - t0 > retry_s:
                return None, f"connection error after {retry_s}s: {e!r}"
            time.sleep(3)
        except httpx.TimeoutException as e:
            return None, f"timeout after {timeout}s: {e!r}"


def server_up(base=BASE):
    try:
        return httpx.get(f"{base}/api/health", timeout=3).status_code == 200
    except Exception:
        return False


def all_numbers(obj, out):
    """Collect every numeric value in the plan (excluding explanation text)."""
    if isinstance(obj, bool):
        return
    if isinstance(obj, (int, float)):
        out.append(float(obj))
    elif isinstance(obj, dict):
        for k, v in obj.items():
            if k == "explanation":
                continue
            all_numbers(v, out)
    elif isinstance(obj, list):
        for v in obj:
            all_numbers(v, out)


NUM = r"(\d[\d,]*(?:\.\d+)?)"
RS_RE = re.compile(r"(?:₹|Rs\.?|INR)\s*" + NUM + r"\s*(lakh|lakhs|crore|crores|k)?", re.I)
RS_POST_RE = re.compile(NUM + r"\s*(lakh|lakhs|crore|crores)?\s*(?:rupees|₹)", re.I)
ACRE_RE = re.compile(NUM + r"\s*(?:-|\s)?(?:acres?|एकर)", re.I)


def _f(s):
    return float(s.replace(",", ""))


def extract_claims(text):
    claims = []  # (kind, value, raw)
    for m in RS_RE.finditer(text):
        v = _f(m.group(1))
        mult = (m.group(2) or "").lower()
        if mult.startswith("lakh"):
            v *= 1e5
        elif mult.startswith("crore"):
            v *= 1e7
        elif mult == "k":
            v *= 1e3
        claims.append(("rs", v, m.group(0).strip()))
    for m in RS_POST_RE.finditer(text):
        v = _f(m.group(1))
        mult = (m.group(2) or "").lower()
        if mult.startswith("lakh"):
            v *= 1e5
        elif mult.startswith("crore"):
            v *= 1e7
        claims.append(("rs", v, m.group(0).strip()))
    for m in ACRE_RE.finditer(text):
        claims.append(("acre", _f(m.group(1)), m.group(0).strip()))
    return claims


def number_pool(plan):
    pool = []
    all_numbers(plan, pool)
    extra = []
    for s in plan.get("strategies", []):
        a = s["totals"]["budget_used_rs"]
        if a:
            extra.append(s["expected_profit_rs"] / a * 100)
        extra.append(abs(s["expected_profit_rs"]))
        for al in s["allocations"]:
            for sc in SCEN:
                extra.append(abs(al["profit_rs"][sc]))
    for c in plan.get("crops", []):
        for sc in SCEN:
            extra.append(abs(c["profit_rs_per_acre"][sc]))
    pool += extra
    pool += [abs(x) for x in pool]
    # also allow sums of per-acre values x acres is overkill; keep to direct matches
    return pool


def claim_matches(kind, v, pool):
    for p in pool:
        if close(v, p, rel=0.01, abs_=1.0 if kind == "rs" else 0.06):
            return True
        # rounded to nearest 100 / 1000 / lakh-decimals
        if kind == "rs":
            for step in (10, 100, 500, 1000, 10000):
                if abs(v - round(p / step) * step) < 1e-6:
                    return True
            if v >= 1e5 and close(v, p, rel=0.011):
                return True
    return False


# ----------------------------------------------------------------- checks
def check_strategy(plan, s, land, budget, fails, notes):
    sid = s["id"]
    pre = f"[{sid}] "
    allocs = s["allocations"]
    solver = (s.get("solver") or {}).get("status")
    if solver is not None and str(solver).lower() in ("error", "failed", "exception"):
        fails.append(pre + f"solver status = {solver}")
    crops = {c["crop_id"]: c for c in plan["crops"]}
    water_by_sc = {w["scenario"]: w for w in plan["water"]}
    exceeds = set(s.get("traditional_exceeds") or [])
    is_trad = s.get("kind") == "traditional"
    if not allocs:
        return
    acres = [a["acres"] for a in allocs]
    if any(x < -1e-9 for x in acres):
        fails.append(pre + f"negative acres: {acres}")
    sa = sum(acres)
    tot = s["totals"]
    if is_trad and "land" in exceeds:
        notes.append(pre + f"traditional exceeds land (declared): {sa} > {land}")
    elif sa > land * 1.005 + 1e-6:
        fails.append(pre + f"sum(acres)={sa} > land_acres={land}")
    elif sa > land + 1e-6:
        notes.append(pre + f"sum(acres)={sa} exceeds land_acres={land} by rounding only (acres rounded to 3 dp)")
    if not close(sa, tot["land_used_acres"], rel=0.001, abs_=0.01):
        fails.append(pre + f"sum(acres)={sa} != totals.land_used_acres={tot['land_used_acres']}")
    sc_cost = sum(a["cost_rs"] for a in allocs)
    if is_trad and "budget" in exceeds:
        notes.append(pre + f"traditional exceeds budget (declared): {sc_cost:.0f} > {budget}")
    elif sc_cost > budget + 1:
        fails.append(pre + f"sum(cost_rs)={sc_cost:.0f} > budget_rs={budget}")
    if not close(sc_cost, tot["budget_used_rs"], rel=0.001, abs_=2):
        fails.append(pre + f"sum(cost_rs)={sc_cost:.1f} != totals.budget_used_rs={tot['budget_used_rs']}")
    sw = sum(a["water_m3"] for a in allocs)
    sc = s["safety_scenario"]
    avail = water_by_sc[sc]["available_m3"]["total"]["value"]
    if is_trad and "water" in exceeds:
        notes.append(pre + f"traditional exceeds water (declared): {sw:.0f} > {avail}")
    elif sw > avail + 1:
        fails.append(pre + f"sum(water_m3)={sw:.0f} > available[{sc}]={avail}")
    elif is_trad and sw > avail + 1:
        fails.append(pre + "traditional exceeds water but not declared in traditional_exceeds")
    if not close(sw, tot["water_m3"], rel=0.001, abs_=2):
        fails.append(pre + f"sum(water_m3)={sw:.1f} != totals.water_m3={tot['water_m3']}")
    # per-allocation
    for a in allocs:
        c = crops.get(a["crop_id"])
        if c is None:
            fails.append(pre + f"allocation crop {a['crop_id']} not in crops[]")
            continue
        ac = a["acres"]
        if not close(a["cost_rs"], c["cost_per_acre"]["total_rs"] * ac, rel=0.01, abs_=1):
            fails.append(pre + f"{a['crop_id']}: cost_rs={a['cost_rs']} vs cost_per_acre*acres={c['cost_per_acre']['total_rs'] * ac:.1f}")
        for scn in SCEN:
            exp = c["profit_rs_per_acre"][scn] * ac
            if not close(a["profit_rs"][scn], exp, rel=0.01, abs_=1):
                fails.append(pre + f"{a['crop_id']}: profit_rs[{scn}]={a['profit_rs'][scn]:.1f} vs per_acre*acres={exp:.1f}")
        if a.get("revenue_rs"):
            for scn in SCEN:
                if not close(a["revenue_rs"][scn], a["cost_rs"] + a["profit_rs"][scn], rel=0.01, abs_=2):
                    fails.append(pre + f"{a['crop_id']}: revenue[{scn}]={a['revenue_rs'][scn]:.1f} != cost+profit={a['cost_rs'] + a['profit_rs'][scn]:.1f}")
        wn = c["water_need_m3_per_acre"].get(sc, {}).get("value") if isinstance(c.get("water_need_m3_per_acre"), dict) else None
        if wn is not None and not close(a["water_m3"], wn * ac, rel=0.02, abs_=2):
            fails.append(pre + f"{a['crop_id']}: water_m3={a['water_m3']} vs need[{sc}]*acres={wn * ac:.1f}")
        if ac > 0 and abs(a["share_pct"] - ac / max(sa, 1e-9) * 100) > 1.0 and abs(a["share_pct"] - ac / land * 100) > 1.0:
            notes.append(pre + f"{a['crop_id']}: share_pct={a['share_pct']} vs acres/total={ac / max(sa, 1e-9) * 100:.1f}")
    # (f) profit by scenario
    for scn in SCEN:
        tot_p = sum(a["profit_rs"][scn] for a in allocs)
        if not close(s["profit_by_scenario_rs"][scn], tot_p, rel=0.005, abs_=2):
            fails.append(pre + f"profit_by_scenario[{scn}]={s['profit_by_scenario_rs'][scn]:.1f} != sum(alloc)={tot_p:.1f}")
    # expected profit vs scenario weights
    probs = {x["id"]: x["probability"] for x in plan["scenarios"]}
    ep = sum(probs[scn] * s["profit_by_scenario_rs"][scn] for scn in SCEN)
    if not close(s["expected_profit_rs"], ep, rel=0.01, abs_=2):
        fails.append(pre + f"expected_profit_rs={s['expected_profit_rs']} != sum(p*profit)={ep:.1f}")
    wc = min(s["profit_by_scenario_rs"][scn] for scn in SCEN)
    if not close(s["worst_case_profit_rs"], wc, rel=0.01, abs_=2):
        fails.append(pre + f"worst_case_profit_rs={s['worst_case_profit_rs']} != min scenario={wc:.1f}")
    if not s.get("feasible", True) and allocs:
        notes.append(pre + "feasible=false but has allocations")


def run_one(base, sc):
    name = sc["name"]
    prof = sc["profile"]
    rec = dict(name=name, district=prof["location_text"], land=prof["land_acres"], budget=prof["budget_rs"],
               water=prof["water_source"], season="", rec_strategy="", rec_crops="", profit=None, roi=None,
               status="", reason="", fails=[], notes=[], provenance={}, http=None, secs=None)
    t0 = time.time()
    r, err = post_plan(base, prof)
    rec["secs"] = round(time.time() - t0, 1)
    if r is None:
        rec["status"], rec["reason"] = "BLOCKED", err
        return rec
    rec["http"] = r.status_code
    try:
        body = r.json()
    except Exception:
        body = None
    (RESULTS / f"{name}.json").write_text(
        json.dumps(body, indent=2, ensure_ascii=False) if body is not None else r.text, encoding="utf-8")
    if r.status_code in (502, 503, 504):
        rec["status"], rec["reason"] = "BLOCKED", f"HTTP {r.status_code}: {r.text[:200]}"
        return rec
    if r.status_code >= 500:
        rec["status"], rec["reason"] = "FAIL", f"HTTP {r.status_code}: {r.text[:300]}"
        return rec
    if r.status_code != 200:
        if r.status_code in sc.get("expect_http", [200]):
            rec["status"] = "PASS-NOPLAN"
            rec["reason"] = f"HTTP {r.status_code} (graceful rejection): {r.text[:200]}"
        else:
            rec["status"], rec["reason"] = "FAIL", f"unexpected HTTP {r.status_code}: {r.text[:300]}"
        return rec
    plan = body
    fails, notes = rec["fails"], rec["notes"]
    land, budget = prof["land_acres"], prof["budget_rs"]
    rec["season"] = plan["season"]["name"]
    # provenance
    rec["provenance"] = dict(
        price_status={c["crop_id"]: c["price"]["status"] for c in plan["crops"]},
        warnings=[w["code"] for w in plan["warnings"]],
        data_status=plan["data_status"],
        explanation_provider=plan["explanation"]["provider"],
        grounded=plan["explanation"]["grounded"],
        resolved=plan["location"]["resolved_name"],
        n_crops=len(plan["crops"]), excluded=[e["crop_id"] for e in plan["excluded_crops"]],
    )
    # strategies
    for s in plan["strategies"]:
        check_strategy(plan, s, land, budget, fails, notes)
    strat = {s["id"]: s for s in plan["strategies"]}
    rid = plan.get("recommended_strategy")
    if rid is not None and rid not in strat:
        fails.append(f"recommended_strategy={rid} not in strategies {list(strat)}")
    rs = strat.get(rid) if rid else None
    rec["rec_strategy"] = rid or "-"
    text = plan["explanation"]["text"]
    if rs and rs["allocations"]:
        used = [a for a in rs["allocations"] if a["acres"] > 1e-9]
        rec["rec_crops"] = ", ".join(f"{a['crop_id']} {a['acres']:.2f}" for a in used)
        rec["profit"] = rs["expected_profit_rs"]
        bu = rs["totals"]["budget_used_rs"]
        rec["roi"] = (rs["expected_profit_rs"] / bu * 100) if bu else None
        fin = rs.get("finance")
        if fin and fin.get("roi_pct") and rec["roi"] is not None:
            if not close(fin["roi_pct"]["value"], rec["roi"], rel=0.02, abs_=0.6):
                fails.append(f"[{rid}] finance.roi_pct={fin['roi_pct']['value']} vs computed {rec['roi']:.2f}")
        if re.search(r"no profitable", text, re.I):
            fails.append("explanation says 'no profitable plan' but a recommended strategy with allocations exists")
        if not used:
            notes.append("recommended strategy has zero-acre allocations only")
    # (i) hallucination check on explanation
    pool = number_pool(plan)
    pool += [land, budget, 100.0]
    unmatched = []
    for kind, v, raw in extract_claims(text):
        if not claim_matches(kind, v, pool):
            unmatched.append(f"{raw} ({kind} {v:g})")
    rec["unmatched_explanation_numbers"] = unmatched
    if unmatched:
        fails.append("explanation numbers not found in plan (possible hallucination): " + "; ".join(unmatched))
    # classification
    has_plan = bool(rs and rs["allocations"] and any(a["acres"] > 1e-9 for a in rs["allocations"]))
    if fails:
        rec["status"] = "FAIL"
        rec["reason"] = " | ".join(fails[:6]) + (f" (+{len(fails) - 6} more)" if len(fails) > 6 else "")
    elif has_plan:
        rec["status"] = "PASS"
    else:
        coherent = bool(text.strip()) and (plan.get("infeasibility") is not None or rid is None or
                                           any(s.get("infeasibility") for s in plan["strategies"]))
        if coherent:
            rec["status"] = "PASS-NOPLAN"
            inf = plan.get("infeasibility") or {}
            rec["reason"] = f"no plan: suggestion_code={inf.get('suggestion_code')} params={inf.get('suggestion_params')}"
        else:
            rec["status"] = "FAIL"
            rec["reason"] = "no allocations and no coherent infeasibility/explanation"
    return rec


def fmt_money(x):
    return "-" if x is None else f"{x:,.0f}"


def write_summary(recs, path=None):
    path = path or (RESULTS / "SUMMARY.md")
    L = ["# E2E scenario summary", "", f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}  ",
         "Season is derived by the backend from today's date (no override field in FarmProfile).", "",
         "| scenario | district | season | land (ac) | budget (Rs) | water | recommended strategy | recommended crops (acres) | expected profit (Rs) | ROI % | status | failure reason |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in recs:
        roi = "-" if r["roi"] is None else f"{r['roi']:.1f}"
        reason = (r["reason"] or "").replace("|", "/").replace("\n", " ")
        L.append(f"| {r['name']} | {r['district']} | {r['season'] or '-'} | {r['land']} | {fmt_money(r['budget'])} | {r['water']} | "
                 f"{r['rec_strategy'] or '-'} | {r['rec_crops'] or '-'} | {fmt_money(r['profit'])} | {roi} | {r['status']} | {reason} |")
    L += ["", "## Provenance and notes", ""]
    for r in recs:
        p = r["provenance"]
        L.append(f"### {r['name']} ({r['status']}, HTTP {r['http']}, {r['secs']}s)")
        if p:
            L.append(f"- price.status: {p['price_status']}")
            L.append(f"- warnings: {p['warnings']}")
            L.append(f"- data_status: {p['data_status']}; explanation provider: {p['explanation_provider']}, grounded={p['grounded']}")
            L.append(f"- excluded crops: {p['excluded']}")
        for n in r["notes"]:
            L.append(f"- note: {n}")
        for f in r["fails"]:
            L.append(f"- FAIL: {f}")
        L.append("")
    path.write_text("\n".join(L), encoding="utf-8")


def load_scenarios():
    return json.loads((HERE / "scenarios.json").read_text(encoding="utf-8"))["scenarios"]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=BASE)
    ap.add_argument("--only", default="")
    a = ap.parse_args(argv)
    RESULTS.mkdir(exist_ok=True)
    scs = load_scenarios()
    if a.only:
        want = set(a.only.split(","))
        scs = [s for s in scs if s["name"] in want]
    recs = []
    for sc in scs:
        rec = run_one(a.base, sc)
        recs.append(rec)
        roi = "-" if rec["roi"] is None else f"{rec['roi']:.1f}%"
        print(f"{rec['status']:12s} {rec['name']:42s} profit={fmt_money(rec['profit'])} ROI={roi} ({rec['secs']}s)")
        if rec["reason"]:
            print("    ", rec["reason"][:400].encode("ascii", "replace").decode())
    write_summary(recs)
    (RESULTS / "records.json").write_text(json.dumps(recs, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"\nSummary: {RESULTS / 'SUMMARY.md'}")
    return 1 if any(r["status"] == "FAIL" for r in recs) else 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
