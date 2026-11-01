# AgriPulse Browser and Agent-Memory Test Report

Date: 2026-11-01

## Environment

- Frontend: `http://127.0.0.1:5173` (Vite)
- Backend: `http://127.0.0.1:8000` (FastAPI/Uvicorn)
- Browser test tool: Microsoft Edge via Playwright
- Backend health: `ok`, 19 data files loaded, models loaded

## Testing Samples

### Sample 1: Beed basic crop plan

Farmer message:

> I am from Beed, Maharashtra. I have 5 acres and want to plan a crop with a budget of 50,000 rupees.

Agent response:

> With the current real data, no profitable crop plan was found for this season. See the reasons and next options below.

Trace result:

- Crop recommendations: 4 candidates, 8 excluded
- Yield forecasts: 4 crops
- Plan optimization: 4 strategies compared
- Plan feasibility check: completed successfully; no profitable allocation

The result is explained in the UI rather than presented as a broken plan: all evaluated Rabi crops had negative margins at the available cached price and cost data.

### Sample 2: Pune irrigated crop plan

Farmer message:

> Create a crop plan for 3 acres in Pune, Maharashtra. My budget is 250,000 rupees. I have one borewell supplying 10,000 litres per hour for 6 hours daily and use drip irrigation.

Agent response:

> With the current real data, no profitable crop plan was found for this season. See the reasons and next options below.

Trace result:

- Crop recommendations: 5 candidates, 6 excluded
- Yield forecasts: 5 crops
- Plan optimization: 4 strategies compared
- Plan feasibility check: completed successfully

The UI listed the economics transparently, including chickpea at -₹1,640/acre, maize at -₹764/acre, onion at -₹14,924/acre, and wheat at -₹6,456/acre. This is a data-driven no-plan outcome, not an API or UI failure.

### Sample 3: Nashik plan, memory, and update

Initial farmer message:

> Create a crop plan for 2 acres in Nashik, Maharashtra with a budget of 200,000 rupees, one borewell supplying 8,000 litres per hour for 6 hours daily, and drip irrigation.

Initial response:

> With the current real data, no profitable crop plan was found for this season. See the reasons and next options below.

Memory follow-up after restarting the backend:

> What district and farm size did I give you?

Agent response:

> From your saved farm profile: the location is Nashik, Maharashtra, the farm size is 2 acres, and the budget is ₹200,000.

Fact-update follow-up:

> Please change my budget to 300,000 rupees.

Outcome: the agent re-ran the data, recommendation, yield, optimization, and feasibility steps.

Memory verification:

> What is my saved budget now?

Agent response:

> From your saved farm profile: the location is Nashik, Maharashtra, the farm size is 2 acres, and the budget is ₹300,000.

### Sample 4: Satara guided data collection

Initial farmer message:

> Create a crop plan for 1 acre in Satara, Maharashtra. My budget is 150,000 rupees, and I use drip irrigation with a borewell.

Agent follow-up:

> How many litres per hour does your borewell give, and how many hours a day does the pump run? If you don't know, just say 'I don't know'.

Farmer reply:

> The borewell supplies 8,000 litres per hour, and the pump runs for 6 hours daily.

Result: the full trace completed successfully (recommendations, yield forecasts, optimization, and feasibility). No plan was allocated because the evaluated crops had negative margins, which the UI listed explicitly: chickpea -₹2,955/acre, maize -₹4,084/acre, onion -₹23,341/acre, and wheat -₹3,723/acre. The UI also disclosed that prices were cached and cultivation costs were from 2022-23.

## Bugs Found and Fixed

1. Informational follow-up questions re-ran optimization and repeated the plan response.
   - Fixed by answering questions directly from the saved farm profile.

2. Farm memory disappeared after a backend restart.
   - Fixed by restoring durable profile and plan data from the application cache before a new graph invocation.

3. Placeholder profiles created while requesting missing information could overwrite a valid saved profile.
   - Fixed by persisting only complete, valid farm profiles.

4. Numeric fact updates were treated as informational memory questions.
   - Fixed by routing `follow_up` updates through profile extraction and re-planning.

5. Empty optimizer results looked like a ₹0 crop plan.
   - Fixed by showing the no-plan explanation, evaluated margins, exclusions, and warnings instead.

6. Trace labels exposed internal IDs.
   - Replaced with readable labels: Crop recommendations, Yield forecasts, Plan optimization, and Plan feasibility check.

## Validation

- Browser console: no application errors during final flows.
- Network: health, sources, and agent chat requests returned HTTP 200.
- Backend test suite: 216 passed.
- Frontend test suite: 16 passed.
- Frontend production build: passed.

## Current Limitation

Current Rabi inputs in the tested districts produced negative margins for all price-and-cost-complete candidate crops. The app correctly declines to invent a recommendation and instead shows the evaluated economics. Cached price data and 2022-23 cultivation costs are disclosed in the UI.
