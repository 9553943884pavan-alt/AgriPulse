# Phase 2 optimizer mathematics and data contract

This document defines the units and admissible transformations for the
optimizer. It is deliberately conservative: an unavailable input is an
exclusion, an unknown uncertainty, or a disclosed assumption. It is never
silently filled with a synthetic value.

## Units and provenance

Every external or computed farmer-visible value is represented as a
`SourcedValue` with source, `as_of`, unit, and status. An optimizer input has
these canonical units:

| Quantity | Canonical unit | Rule |
| --- | --- | --- |
| Land and allocation | acre | Decision variable `x_i` is acres of crop `i`. |
| Yield | quintal/acre | Convert model output using 1 t/ha = 4.04686 q/acre. |
| Price | Rs/quintal | A current mandi quote may be seasonally adjusted only from observed monthly history. |
| Cost, revenue, profit | Rs/acre or Rs | Costs are per acre; strategy totals multiply by acres. |
| Crop water need and water availability | m3/acre and m3 | 1 mm over 1 acre = 4.04686 m3. |
| Fertilizer | kg nutrient/acre | N, P2O5, and K2O are not interchangeable. |

Expected harvest price is `current_quote * seasonal_ratio`, optionally floored
at an applicable MSP. The ratio is used only when the price-history service
reports its actual supporting history; otherwise the unadjusted ratio and its
limitation must be returned. 2022-23 cost data remain dated state baselines,
not current farm quotations.

## Water balance

The optimizer must use exactly one of the following equivalent formulations;
the current target contract is the first.

1. **Net-irrigation form (required):**

   `ETc_is = Kc_i * ET0_s`

   `Pe_s = min(effective_rain_factor * rainfall_s, ETc_is)`

   `I_is = max(0, (ETc_is - Pe_s) / irrigation_efficiency)`

   `w_is = I_is * 4.04686` m3/acre

   The water constraint is `sum_i(w_is * x_i) <= groundwater_s + canal_s`.
   Rainfall is already deducted from demand and **must not** be added to this
   irrigation supply again.

2. **Gross-demand form:** compare `ETc * 4.04686 / efficiency` with a supply
   containing effective rainfall plus delivered irrigation. This form must not
   be mixed with the net-irrigation form.

Groundwater is credited only from a supplied borewell discharge and pump-hours
input, subject to a declared CGWB-category cap. Canal volume is zero unless a
source-backed command-area entitlement/duty is available. Category caps,
effective-rain factor, and default irrigation efficiency are assumptions until
their cited source is supplied.

## Deterministic LP

For eligible crop options `i`, choose acreage `x_i >= 0`:

`maximize sum_i(expected_margin_i * x_i)`

subject to:

- `sum_i x_i <= land_acres`
- `sum_i cost_i * x_i <= budget_rs`
- `sum_i water_i,safety * x_i <= irrigation_supply_safety`
- `x_i <= diversification_cap(n) * land_acres`
- explicit eligibility exclusions for missing source inputs, non-positive
  expected margin, or product-defined minimum suitability.

`expected_margin_i` is the probability-weighted scenario margin only when
scenario weights are supplied as a complete, non-negative vector summing to
one. Schema validation rejects a partial or unnormalised scenario contract.

Solver status, used land/budget/water, binding constraints, and a zero-plan
reason are result fields, not inferred by the UI.

## Discrete and risk models

MILP crop-activation variables and minimum acreage may be added only when a
documented operational minimum (plot, seed package, labour, buyer contract) is
available. Without that evidence the LP must remain continuous; arbitrary tiny
or mandatory allocations are not substituted with invented constants.

QP/MIQP risk allocation is permitted only with enough aligned, historical or
auditable simulated joint **profit** samples (yield and harvest price) to
estimate a covariance matrix and calibrate a rupee-scale risk aversion. Three
constructed weather scenarios are not a covariance sample. Until that evidence
exists, risk-labelled recommendations must be disabled or clearly marked as
deterministic scenario comparisons.

Robust planning can instead report a scenario-feasible allocation and its
worst-case profit, provided each scenario retains its analogue-year provenance.

## Uncertainty and explanations

`UncertaintyBand` has ordered lower, expected, and upper values plus a unit,
basis, and status. It is optional because current datasets do not justify an
interval for every crop; absence means unknown uncertainty, not zero risk.

SHAP is restricted to the supported yield-prediction model. It explains that
model's prediction relative to its model baseline; it does not explain the
derived suitability ratio, causal agronomy, or optimizer allocation. Allocation
explanations must instead cite margins, active constraints, scenario outcomes,
and counterfactual constraint changes.
