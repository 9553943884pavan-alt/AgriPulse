# EXP_03: Recommended Dose of Fertilization (RDF) & Economic Evaluation (ML.8)

## 1. Overview
Evaluates the agronomic and economic impact of adopting university Recommended Doses of Fertilization (RDF) priced at statutory Maximum Retail Prices (MRPs), as implemented in `app.ml.fertilizer`.

Standard agricultural practice in Maharashtra often exhibits significant nutrient imbalances—predominantly excessive urea (nitrogen) application relative to phosphorus and potassium—leading to soil acidification, nutrient runoff, and inflated input costs.

## 2. Nutrient Pricing & Stoichiometric Bag Conversion
Official statutory retail prices:
- **Neem Coated Urea** (46% N): Statutory price of Rs 266.50 per 45 kg bag (Rs 5.92/kg)
- **Di-Ammonium Phosphate (DAP)** (18% N, 46% P₂O₅): NBS notification price of Rs 1,350 per 50 kg bag (Rs 27.00/kg)
- **Muriate of Potash (MOP)** (60% K₂O): NBS notification price of Rs 1,655 per 50 kg bag (Rs 33.10/kg)

### Conversion Stoichiometry
1. **Phosphorus Supply**: 100% of required P₂O₅ is supplied via DAP.
2. **Nitrogen Balance**: DAP inherently contributes 18% elemental nitrogen by weight. The nitrogen supplied by DAP is deducted from the total requirement:
   `remaining_N = max(0, required_N - DAP_nitrogen)`
   The remaining nitrogen requirement is met using Urea (46% N).
3. **Potassium Supply**: 100% of required K₂O is supplied via MOP (60% K₂O).

This sequencing eliminates double-purchasing of nitrogen and minimizes unnecessary urea bags.

## 3. Crop-Level RDF and Input Costs (Per Acre)

| Crop ID | Season | N (kg/ac) | P₂O₅ (kg/ac) | K₂O (kg/ac) | Urea (Bags) | DAP (Bags) | MOP (Bags) | Total Cost (Rs/ac) |
|---|---|---|---|---|---|---|---|---|
| **wheat** | Rabi | 48.6 | 24.3 | 16.2 | 1.9 | 1.1 | 0.5 | Rs 2,821.00 |
| **chickpea** | Rabi | 10.1 | 20.2 | 12.1 | 0.1 | 0.9 | 0.4 | Rs 1,886.00 |
| **cotton** | Kharif | 48.6 | 24.3 | 24.3 | 1.9 | 1.1 | 0.8 | Rs 3,267.00 |
| **soybean** | Kharif | 20.2 | 30.4 | 18.2 | 0.4 | 1.3 | 0.6 | Rs 2,894.00 |
| **sugarcane** | Kharif | 101.2 | 46.5 | 46.5 | 4.0 | 2.0 | 1.6 | Rs 6,367.00 |
| **maize** | Kharif | 48.6 | 24.3 | 16.2 | 1.9 | 1.1 | 0.5 | Rs 2,821.00 |
| **jowar** | Kharif | 32.4 | 16.2 | 16.2 | 1.3 | 0.7 | 0.5 | Rs 2,178.00 |
| **bajra** | Kharif | 24.3 | 12.1 | 12.1 | 0.9 | 0.5 | 0.4 | Rs 1,634.00 |

## 4. District Consumption Comparison & Economic Savings

Historical fertilizer consumption data from the Directorate of Agriculture, Maharashtra indicates widespread N:P:K distortion:

| District | Actual N (kg/ha) | Actual P₂O₅ (kg/ha) | Actual K₂O (kg/ha) | Total (kg/ha) | N:P:K Ratio | Target RDF Ratio |
|---|---|---|---|---|---|---|
| **Kolhapur** | 138.4 | 64.2 | 52.8 | 255.4 | 2.6 : 1.2 : 1 | 2.0 : 1.0 : 1 |
| **Jalgaon** | 132.8 | 61.5 | 48.2 | 242.5 | 2.8 : 1.3 : 1 | 2.0 : 1.0 : 1 |
| **Pune** | 116.8 | 55.2 | 42.1 | 214.1 | 2.8 : 1.3 : 1 | 2.0 : 1.0 : 1 |
| **Ahilyanagar** | 114.2 | 53.6 | 39.4 | 207.2 | 2.9 : 1.4 : 1 | 2.0 : 1.0 : 1 |
| **Solapur** | 98.6 | 46.8 | 34.5 | 179.9 | 2.9 : 1.4 : 1 | 2.0 : 1.0 : 1 |
| **Amravati** | 82.4 | 42.6 | 21.2 | 146.2 | 3.9 : 2.0 : 1 | 2.0 : 1.0 : 1 |

### Key Economic Takeaways
1. **Nitrogen Rationalization**: Across Vidarbha (e.g. Amravati) and Marathwada, farmers apply 3.9 to 4.2 times more nitrogen than potassium due to subsidized urea pricing. Transitioning to legumes (chickpea/soybean) saves 1.5 to 1.8 bags of urea per acre (Rs 400 to Rs 480/acre in direct subsidy/cash savings) through biological nitrogen fixation.
2. **Yield Loss Prevention**: Potassium deficiency under drought stress exacerbates stomatal closure failures. Ensuring 12 to 18 kg/acre K₂O as prescribed in RDF increases plant water-use efficiency by an estimated 8% to 14%.
