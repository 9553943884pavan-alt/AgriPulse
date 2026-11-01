# E2E scenario summary

Generated: 2026-11-01 22:56:17  
Season is derived by the backend from today's date (no override field in FarmProfile).

| scenario | district | season | land (ac) | budget (Rs) | water | recommended strategy | recommended crops (acres) | expected profit (Rs) | ROI % | status | failure reason |
|---|---|---|---|---|---|---|---|---|---|---|---|
| nashik_borewell_drip_balanced | Nashik | Rabi | 5.0 | 155,000 | borewell | lp_max_profit | onion 1.72 | 16,516 | 22.5 | PASS |  |
| pune_canal_flood_safe | Pune | Rabi | 4.0 | 115,000 | canal | lp_max_profit | - | - | - | PASS-NOPLAN | no plan: suggestion_code=RESOURCE_LIMIT_BLOCKS_ALLOCATION params={'limiting': ['water'], 'safety_scenario': 'normal', 'profitable_crop_ids': ['onion'], 'min_plan_acres': 0.01} |
| pune_borewell_drip_safe | Pune | Rabi | 4.0 | 115,000 | borewell | lp_max_profit | onion 1.82 | 35,500 | 45.7 | PASS |  |
| solapur_rainfed_balanced | Solapur | Rabi | 6.0 | 65,000 | rainfed | lp_max_profit | - | - | - | PASS-NOPLAN | no plan: suggestion_code=NO_POSITIVE_ALLOCATION params={'reason': 'no_crop_has_positive_expected_margin'} |
| ahilyanagar_tiny_borewell_safe | Ahilyanagar | Rabi | 3.0 | 90,000 | borewell | lp_max_profit | - | - | - | PASS-NOPLAN | no plan: suggestion_code=NO_POSITIVE_ALLOCATION params={'reason': 'no_crop_has_positive_expected_margin'} |
| latur_lowbudget_balanced | Latur | Rabi | 2.0 | 8,000 | rainfed | lp_max_profit | - | - | - | PASS-NOPLAN | no plan: suggestion_code=NO_POSITIVE_ALLOCATION params={'reason': 'no_crop_has_positive_expected_margin'} |
| nagpur_large_maxprofit | Nagpur | Rabi | 40.0 | 1,400,000 | both | lp_max_profit | onion 11.57 | 397,841 | 80.5 | PASS |  |
| kolhapur_borewell_sprinkler_maxprofit | Kolhapur | Rabi | 8.0 | 280,000 | borewell | lp_max_profit | chickpea 5.20, onion 1.90, wheat 0.90 | 30,716 | 15.4 | PASS |  |
| jalgaon_edge_tiny_plot | Jalgaon | Rabi | 0.25 | 1,000 | rainfed | lp_max_profit | - | - | - | PASS-NOPLAN | no plan: suggestion_code=NO_POSITIVE_ALLOCATION params={'reason': 'no_crop_has_positive_expected_margin'} |
| edge_unsupported_district | Bengaluru | - | 3.0 | 50,000 | rainfed | - | - | - | - | PASS-NOPLAN | HTTP 422 (graceful rejection): {"error":{"code":"LOCATION_NOT_FOUND","message":"We could not find this place in India.","user_message":{"mr":"हे ठिकाण भारतात सापडले नाही.","hi":"यह स्थान भारत में नहीं मिला।","en":"We could not find |

## Provenance and notes

### nashik_borewell_drip_balanced (PASS, HTTP 200, 6.0s)
- price.status: {'chickpea': 'cached', 'maize': 'cached', 'onion': 'cached', 'wheat': 'cached'}
- warnings: ['OLD_COST_YEAR', 'CACHED_PRICES']
- data_status: {'live': 1, 'cached': 4, 'official_dataset': 34}; explanation provider: template, grounded=False
- excluded crops: ['grapes', 'jowar', 'lentil', 'mango', 'orange', 'pomegranate', 'sugarcane']
- note: [traditional] traditional exceeds water (declared): 8620 > 5040.0
- note: [traditional] feasible=false but has allocations

### pune_canal_flood_safe (PASS-NOPLAN, HTTP 200, 3.8s)
- price.status: {'chickpea': 'cached', 'maize': 'cached', 'onion': 'cached', 'wheat': 'cached'}
- warnings: ['OLD_COST_YEAR', 'CACHED_PRICES', 'CANAL_NOT_CREDITED']
- data_status: {'live': 1, 'cached': 4, 'official_dataset': 34}; explanation provider: template, grounded=False
- excluded crops: ['jowar', 'lentil', 'mango', 'orange', 'pomegranate', 'sugarcane', 'grapes']
- note: [traditional] traditional exceeds water (declared): 11200 > 0.0
- note: [traditional] feasible=false but has allocations

### pune_borewell_drip_safe (PASS, HTTP 200, 3.7s)
- price.status: {'chickpea': 'cached', 'maize': 'cached', 'onion': 'cached', 'wheat': 'cached'}
- warnings: ['OLD_COST_YEAR', 'CACHED_PRICES']
- data_status: {'live': 1, 'cached': 4, 'official_dataset': 34}; explanation provider: template, grounded=False
- excluded crops: ['jowar', 'lentil', 'mango', 'orange', 'pomegranate', 'sugarcane', 'grapes']
- note: [traditional] traditional exceeds water (declared): 7467 > 5760.0
- note: [traditional] feasible=false but has allocations

### solapur_rainfed_balanced (PASS-NOPLAN, HTTP 200, 3.9s)
- price.status: {'chickpea': 'cached', 'maize': 'cached', 'onion': 'cached', 'wheat': 'cached'}
- warnings: ['OLD_COST_YEAR', 'CACHED_PRICES']
- data_status: {'live': 1, 'cached': 4, 'official_dataset': 34}; explanation provider: template, grounded=False
- excluded crops: ['banana', 'jowar', 'lentil', 'mango', 'orange', 'pomegranate', 'sugarcane', 'grapes']
- note: [traditional] traditional exceeds budget (declared): 158579 > 65000
- note: [traditional] traditional exceeds water (declared): 15170 > 0.0
- note: [traditional] feasible=false but has allocations

### ahilyanagar_tiny_borewell_safe (PASS-NOPLAN, HTTP 200, 3.6s)
- price.status: {'chickpea': 'cached', 'maize': 'cached', 'onion': 'cached', 'wheat': 'cached'}
- warnings: ['OLD_COST_YEAR', 'CACHED_PRICES']
- data_status: {'live': 1, 'cached': 4, 'official_dataset': 34}; explanation provider: template, grounded=False
- excluded crops: ['jowar', 'lentil', 'mango', 'orange', 'pomegranate', 'sugarcane', 'grapes']
- note: [traditional] traditional exceeds water (declared): 4828 > 134.4
- note: [traditional] feasible=false but has allocations

### latur_lowbudget_balanced (PASS-NOPLAN, HTTP 200, 3.6s)
- price.status: {'chickpea': 'cached', 'maize': 'cached', 'wheat': 'cached'}
- warnings: ['OLD_COST_YEAR', 'CACHED_PRICES']
- data_status: {'live': 1, 'cached': 3, 'official_dataset': 33}; explanation provider: template, grounded=False
- excluded crops: ['banana', 'jowar', 'lentil', 'mango', 'onion', 'orange', 'pomegranate', 'sugarcane', 'grapes']
- note: [traditional] traditional exceeds budget (declared): 41991 > 8000
- note: [traditional] traditional exceeds water (declared): 3373 > 0.0
- note: [traditional] feasible=false but has allocations

### nagpur_large_maxprofit (PASS, HTTP 200, 3.1s)
- price.status: {'chickpea': 'cached', 'onion': 'cached', 'wheat': 'cached'}
- warnings: ['OLD_COST_YEAR', 'CACHED_PRICES', 'CANAL_NOT_CREDITED']
- data_status: {'live': 1, 'cached': 3, 'official_dataset': 33}; explanation provider: template, grounded=False
- excluded crops: ['grapes', 'jowar', 'lentil', 'maize', 'mango', 'orange', 'pomegranate', 'sugarcane']
- note: [traditional] traditional exceeds water (declared): 74294 > 38880.0
- note: [traditional] feasible=false but has allocations

### kolhapur_borewell_sprinkler_maxprofit (PASS, HTTP 200, 3.4s)
- price.status: {'chickpea': 'cached', 'maize': 'cached', 'onion': 'cached', 'wheat': 'cached'}
- warnings: ['OLD_COST_YEAR', 'CACHED_PRICES']
- data_status: {'live': 1, 'cached': 4, 'official_dataset': 34}; explanation provider: template, grounded=False
- excluded crops: ['banana', 'grapes', 'jowar', 'lentil', 'mango', 'orange', 'pomegranate', 'sugarcane']
- note: [traditional] traditional exceeds water (declared): 17000 > 9000.0
- note: [traditional] feasible=false but has allocations

### jalgaon_edge_tiny_plot (PASS-NOPLAN, HTTP 200, 3.5s)
- price.status: {'chickpea': 'cached', 'maize': 'cached', 'onion': 'cached', 'wheat': 'cached'}
- warnings: ['OLD_COST_YEAR', 'CACHED_PRICES']
- data_status: {'live': 1, 'cached': 4, 'official_dataset': 34}; explanation provider: template, grounded=False
- excluded crops: ['banana', 'grapes', 'jowar', 'lentil', 'mango', 'orange', 'pomegranate', 'sugarcane']
- note: [traditional] traditional exceeds budget (declared): 6600 > 1000
- note: [traditional] traditional exceeds water (declared): 668 > 0.0
- note: [traditional] feasible=false but has allocations

### edge_unsupported_district (PASS-NOPLAN, HTTP 422, 0.9s)
