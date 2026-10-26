# AI-Based Software Interface for Concrete Mix Design

Streamlit prototype for the minor project (GCOE Amravati, Civil Engineering).
Two **separate** engines:

| Engine | What it does | Files |
|---|---|---|
| **Engineering calculator** (deterministic) | IS 10262:2019 procedure, Sections 2-3 (M10-M100): target strength, w/c, water, binder, SCM, aggregates, admixture, moisture correction, checks, step-by-step trace | `src/engineering.py`, `src/constants.py` |
| **ML strength predictor** | Linear / Random Forest / Hist-GB trained on the public UCI dataset (8 inputs → compressive strength, MPa) | `src/data_loading.py`, `src/model_training.py`, `src/prediction.py` |

The AI model does **not** design mixes and is **not** IS-compliant by itself. This is a research prototype - not a substitute for trial mixes and laboratory testing.

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
The browser opens at https://smartmix-lab.streamlit.app/.

## 2. Get the dataset and train the model

* Download **Concrete_Data.xls** (or the zip) from https://archive.ics.uci.edu/dataset/165/concrete+compressive+strength
* In the app: **AI Model → upload the file → Train and evaluate**. (Or put it at `data/concrete_data.csv`, or run `python train_model.py path\to\Concrete_Data.xls`.)
* The app also *tries* an automatic download when internet is available; if it fails you get a clear message and the upload box.
* Until training succeeds the app says **"Model not trained"** and shows no accuracy numbers. All metrics shown later are computed from the held-out test set - quote them from the app, not from anywhere else.

Training protocol: duplicate-safe 80/20 split (seed 42) → 5-fold grouped CV + small grid search on the training part only → best CV-RMSE model chosen → test set used once for MAE / RMSE / R² → actual-vs-predicted, residual and permutation-importance plots → saved to `models/` with joblib.

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
* **The UCI dataset was not downloaded or trained on here.** No real metrics exist yet. Full-mode training time on a laptop is unmeasured (use *Fast mode* for demos).
* The automatic download URL is untested; upload fallback is provided.
* **IS 456:2000 was not supplied.** Durability limits (max w/c, minimum binder, 450 kg/m³ max cement) are shown as "verify". Only 0.45/320 (severe, RC) and 0.60/240 (moderate, plain) are confirmed indirectly by the IS 10262 examples. Check `IS456_*` in `src/constants.py` against the code.
* **Fig. 1 (w/c vs strength)** cannot be read exactly from the PDF. For OPC 43/PPC the app interpolates between three points printed in the standard's examples (48.25→0.36, 38.25→0.43, 20.77→0.61) and flags it as an estimate; OPC 33/53 require you to enter the w/c read from the printed chart. Table 8 (high strength) is interpolated linearly.
* Not implemented: self-compacting concrete (Section 4), mass concrete (Section 5), air-entrained, lightweight aggregate, early-strength adjustments.
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
