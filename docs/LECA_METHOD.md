# LECA lightweight-aggregate concrete: method (src/lwac.py)

IS 10262 fails for LECA because its tables assume SG ~2.7, ~0.5 % absorption and 2300-2500 kg/m³.
This module replaces the aggregate tables with a **density-closure volume method**.

## Inputs
| Group | Inputs |
|---|---|
| Strength | fck, site control (S per IS 10262 Table 2), optional LECA strength ceiling |
| Density | target **fresh** density + tolerance (or a fine fraction of aggregate volume instead) |
| LECA | **oven-dry particle SG** (pores included, 1.0-1.5), loose dry bulk density, 24 h absorption %, moisture state (oven-dry / SSD pre-soaked / moisture content), share of absorption taken up before set |
| Fine | same five items (natural sand ~2.62 / 1 %; or LECA fines for all-lightweight) |
| Paste | cement SG, SCM % of binder (GGBS, fly ash), w/cm (manual or estimated), slump, base net water, air %, minimum binder |
| Admixture | dose % of binder, SG, water reduction % **from trials** (never derived from dose) |

## Formulas
1. f'ck = max(fck + 1.65 S, fck + X)
2. w/cm: manual, or normal-weight curve at f'ck / efficiency (ASSUMPTION, efficiency 0.85)
3. W_net = W50 · (1 + 0.03 (slump−50)/25) · (1 − red/100)
4. B = max(W_net / wcm, B_min); SCM are part of B; cement = B − ΣSCM; wcm = W_net / B
5. V_agg = 1 − air − Σ(mass / (SG·1000)) over cement, SCM, **net** water, admixture.
   Absorbed water is **not** in this sum: it sits inside the LECA particle volume V = M_dry/(SG_dry·1000).
6. ρ_i = SG_dry,i · 1000 · (1 + A_i);  V_f = (ρ_t − M_paste − ρ_c V_agg)/(ρ_f − ρ_c);  V_c = V_agg − V_f;  M_dry = V · SG_dry · 1000
7. Water: absorption water = A·M_dry; to add = W_net + Σ M_dry (A − m) − surface credit  (m = current moisture)
   Batch mass of aggregate = M_dry (1 + m)
8. Fresh density = binder + W_net + admixture + Σ M_dry (1 + A); oven-dry ≈ dry aggregates + 1.2 B; equilibrium ≈ oven-dry + 50

## Why this protects the paste
The strength-governing free w/cm uses **net** water only. The absorption water is supplied separately
(pre-soak, or added at the mixer), so dry LECA cannot pull water out of the paste. A dry LECA with 12 %
absorption and 520 kg/m³ dry mass needs ~62 kg/m³ extra water.

## Not code values (ASSUMPTION)
strength efficiency 0.85, base water 170 kg/m³, air 2 %, binder window 300-550, oven-dry/equilibrium
rules of thumb, structural window (≥17 MPa, 1120-1920 kg/m³), loose-bulk-volume limit 1.2.
Calibrate with trial mixes; LECA particle strength caps achievable concrete strength.
