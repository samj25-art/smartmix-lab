# AI-Based Software Interface for Concrete Mix Design

Streamlit prototype for the minor project (GCOE Amravati, Civil Engineering).
Three **separate** engines (v2 adds the LECA lightweight module):

| Engine | What it does | Files |
|---|---|---|
| **Engineering calculator** (deterministic) | IS 10262:2019 procedure, Sections 2-3 (M10-M100): target strength, w/c, water, binder, SCM, aggregates, admixture, moisture correction, checks, step-by-step trace | `src/engineering.py`, `src/constants.py` |
| **LECA lightweight concrete** (deterministic) | Absolute-volume balance on oven-dry particle SG, net vs absorption water split, fine/coarse by density closure, batch quantities, checks, trace. Method: `docs/LECA_METHOD.md` | `src/lwac.py`, `src/lwac_ui.py`, `src/mix_types.py` |
| **ML strength predictor** | Linear / Random Forest / Hist-GB trained on the public UCI dataset (8 inputs → compressive strength, MPa) | `src/data_loading.py`, `src/model_training.py`, `src/prediction.py` |

The AI model does **not** design mixes and is **not** IS-compliant by itself. This is a research prototype - not a substitute for trial mixes and laboratory testing.

**LECA app:** `run_leca.bat` / `streamlit run leca_app.py` (stand-alone) or the "LECA Lightweight Concrete" page of the main app. Python use: `from src.lwac import design_leca_mix_simple`. LECA defaults marked ASSUMPTION are not code values - no LWAC code was supplied; the Streamlit page was exercised only against a stub (Streamlit not installable offline). Unit tests: `tests/test_lwac.py`.

## 1. Windows setup (beginner)

1. Install Python 3.10-3.12 from https://www.python.org/downloads/ - **tick "Add Python to PATH"**.
2. Unzip the project, open the folder, then either double-click `setup_windows.bat` (once) and `run_app.bat`, **or** in Command Prompt:

```bat
cd C:\path\to\concrete_mix_ai
py -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```
The browser opens at http://localhost:8501.

## 2. The model is PRE-TRAINED (nothing to do before first use)

`models/` already contains a model trained on the real UCI file (`data/concrete_data.csv`, 1030 lab mixes):

| Item | Value |
|---|---|
| Selected model | Hist Gradient Boosting (chosen by 5-fold grouped CV on the training part only) |
| Split | 824 train / 206 test (80/20, seed 42, duplicates kept on one side) |
| Held-out test R² / RMSE / MAE | **0.939 / 4.37 MPa / 2.62 MPa** |
| Other candidates (test R²) | Random Forest 0.915, Linear Regression 0.581 |

These numbers appear on the **Home** page and the **AI Model** page and are read from `models/metrics.json` - never typed in.
If you re-train (AI Model page or `python train_model.py`) the numbers change slightly with scikit-learn version and data.

**If the saved model cannot be loaded on your PC** (usually a different scikit-learn version) the app re-trains once at start-up
from `data/concrete_data.csv` (about 1 minute) and continues - you do not need to do anything.

`HPC_DATA.csv` is **not** used: about 60 % of its rows are identical to UCI rows and ~30 % more are near-duplicates, so it
cannot serve as independent test data and would inflate accuracy if merged.

## 3. Typical demo flow

1. **Mix Input** - grade, exposure, slump, aggregate data, SCM, admixture (water reduction from trials), the 8 ML features, optional prices.
2. **Engineering Calculator** - confirm key inputs → run → quantities, checks (PASS / FAIL / REVIEW / PENDING), formula trace.
3. **AI Strength Prediction** - "use calculated mix" or type values → predicted MPa at the entered age, ~90 % band, out-of-range warnings, target comparison.
4. **Candidate Comparison** (experimental) - editable table, no automatic "best".
5. **Results & Reports** - dashboard, **CSV** and **PDF** download.
6. **Workbook Audit** - what is wrong/different in the original Excel logic, side-by-side numbers.

## 4. What was actually verified (and how)

Run `run_tests.bat` or `python -m unittest discover -s tests -t .` (32 tests; no pytest needed).

* Engineering calculator vs the worked examples **printed in IS 10262:2019 Annex A (PPC M40), B (fly-ash M40, wet aggregates), D (M70, silica fume + fly ash)** - all agree within 1 % (IS rounds intermediate values; exact re-computation cannot match digit-for-digit). Invariants: volume = 1 m³, mass balance, no SCM double counting, admixture dose never changes water, slump applied once.
* Pipeline tests use **synthetic** data (`tests/synthetic.py`) because the sandbox where this was built had no internet - they prove the code works, **not** that the model is accurate on real concrete.
* PDF and CSV generation tested (with and without a model).

## 5. NOT verified / known limitations - read before presenting

* **The Streamlit UI was never launched in the build environment** (no internet, Streamlit not installable). All eight pages were executed against a stand-in for the Streamlit API to catch Python errors, but layout and widget behaviour on real Streamlit are untested. Expect to fix small UI issues on first run - tell me the traceback.
* The pre-trained metrics above are real (UCI file, full-mode training took ~45 s on the build machine). They describe accuracy on **this public lab dataset**, not on your own materials.
* **IS 456:2000 was not supplied.** Durability limits (max w/c, minimum binder, 450 kg/m³ max cement) are shown as "verify". Only 0.45/320 (severe, RC) and 0.60/240 (moderate, plain) are confirmed indirectly by the IS 10262 examples. Check `IS456_*` in `src/constants.py` against the code.
* **Fig. 1 (w/c vs strength)** cannot be read exactly from the PDF. For OPC 43/PPC the app interpolates between three points printed in the standard's examples (48.25→0.36, 38.25→0.43, 20.77→0.61) and flags it as an estimate; OPC 33/53 require you to enter the w/c read from the printed chart. Table 8 (high strength) is interpolated linearly.
* Not implemented: self-compacting concrete (Section 4), mass concrete (Section 5), air-entrained, early-strength adjustments.
* ML model limits: lab data (1030 mixes), no silica fume/metakaolin column, no aggregate shape, cement grade or admixture type; UCI `superplasticizer` is assumed to be kg/m³ of admixture. Predictions outside the training range are flagged, but even inside the range the ~90 % band is only an empirical guide.
* VBA: `vbaProject.bin` exists but no custom macro source could be extracted offline - the workbook's macros were not reviewed.
* Trial mixes and lab verification are always reported as **NOT DONE**.

## 6. Workbook findings (summary - see `docs/WORKBOOK_AUDIT.md`)

Standard-deviation/X tables differ from IS Tables 1-2; target strength does not take the higher of the two formulas; w/c is a hard-coded step function; **slump is applied twice**; plasticiser dose is used as water reduction; absolute volume ignores fly ash and admixture; fine:coarse split is manual instead of Tables 5/10; air-content table differs from IS and the air input cell is unused; the OUTPUT status test applies `MID()` to a numeric cell (threshold becomes 82). The report's comparison table also labels water as "W/C". Your original `.xlsm` is untouched.

## 7. Project layout

```
app.py                 Streamlit UI (8 pages)
train_model.py         optional command-line training
src/constants.py       IS tables with source tags
src/engineering.py     IS 10262 calculator (+ trace and checks)
src/validation.py      input validation
src/data_loading.py    UCI loading / cleaning / quality report
src/model_training.py  training, CV, evaluation, saving
src/prediction.py      schema + range checks, prediction
src/report.py          CSV and PDF
src/workbook_replica.py  Python copy of the old Excel logic + audit findings
tests/                 32 unit tests
docs/WORKBOOK_AUDIT.md
```
