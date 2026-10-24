"""
Reference tables.

Every table carries a SOURCE tag so the app can show what is verified.

  IS10262_VERIFIED : value was read from the supplied IS 10262:2019 PDF
                     (IS10262_2019.pdf) - clause/table number is given.
  IS456_UNVERIFIED : value comes from IS 456:2000 Table 5 / cl. 8.2.4.2.
                     IS 456 was NOT among the supplied attachments, only quoted
                     indirectly in IS 10262 examples (0.45 / 320 for 'severe' RC,
                     0.60 / 240 for 'moderate' plain concrete). The remaining
                     IS 456 entries are typed from general knowledge and MUST be
                     checked against the actual code before use.
"""

SOURCE_IS10262 = "IS 10262:2019 (verified from supplied PDF)"
SOURCE_IS456 = "IS 456:2000 (NOT in supplied attachments - verify)"
SOURCE_ASSUMPTION = "Assumption / user input"
SOURCE_WORKBOOK = "Existing Excel workbook"


# ---- IS 10262:2019 Table 1 : value of X (cl. 4.2) -------------------------------
def table1_X(fck: float) -> float:
    if fck <= 15:
        return 5.0
    if fck <= 25:
        return 5.5
    if fck <= 60:
        return 6.5
    return 8.0  # M65 and above


# ---- IS 10262:2019 Table 2 : assumed standard deviation, good site control ------
def table2_S(fck: float) -> float:
    if fck <= 15:
        return 3.5
    if fck <= 25:
        return 4.0
    if fck <= 60:
        return 5.0
    return 6.0  # M65 - M80 (Table 2 lists up to M80; same value assumed above)


STANDARD_GRADES = [10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60]
HIGH_STRENGTH_GRADES = [65, 70, 75, 80, 85, 90, 95, 100]
ALL_GRADES = STANDARD_GRADES + HIGH_STRENGTH_GRADES

# ---- Table 3 : entrapped air (%) ordinary / standard grades --------------------
TABLE3_AIR = {10.0: 1.5, 20.0: 1.0, 40.0: 0.8}
# ---- Table 6 : entrapped air (%) high strength ----------------------------------
TABLE6_AIR = {10.0: 1.0, 12.5: 0.8, 20.0: 0.5}

# ---- Table 4 : water content kg/m3 at 50 mm slump, angular aggregate, SSD ------
TABLE4_WATER = {10.0: 208.0, 20.0: 186.0, 40.0: 165.0}
# ---- Table 7 : water content kg/m3 (high strength, no chemical admixture) ------
TABLE7_WATER = {10.0: 200.0, 12.5: 195.0, 20.0: 186.0}

# Cl. 5.3 : reduction of water for aggregate shape (ordinary grades), kg/m3
SHAPE_WATER_REDUCTION = {
    "Crushed angular": 0.0,
    "Sub-angular": 10.0,
    "Gravel with some crushed particles": 15.0,
    "Rounded gravel": 20.0,
}
SLUMP_STEP_PERCENT = 3.0  # +/- 3 % per 25 mm slump change (cl. 5.3)

# ---- Table 5 : coarse aggregate volume fraction at w/c 0.50 (ordinary) ---------
TABLE5_CA = {
    10.0: {"IV": 0.54, "III": 0.52, "II": 0.50, "I": 0.48},
    20.0: {"IV": 0.66, "III": 0.64, "II": 0.62, "I": 0.60},
    40.0: {"IV": 0.73, "III": 0.72, "II": 0.71, "I": 0.69},
}
# ---- Table 10 : coarse aggregate volume fraction at w/cm 0.30 (high strength) --
TABLE10_CA = {
    10.0: {"III": 0.56, "II": 0.54, "I": 0.52},
    12.5: {"III": 0.58, "II": 0.56, "I": 0.54},
    20.0: {"III": 0.68, "II": 0.66, "I": 0.64},
}

# ---- Table 8 : recommended w/cm for high strength with HRWRA + silica fume -----
# target strength -> {msa: w/cm}
TABLE8_WCM = {
    70: {10.0: 0.36, 12.5: 0.35, 20.0: 0.33},
    75: {10.0: 0.34, 12.5: 0.33, 20.0: 0.31},
    80: {10.0: 0.32, 12.5: 0.31, 20.0: 0.29},
    85: {10.0: 0.30, 12.5: 0.29, 20.0: 0.27},
    90: {10.0: 0.28, 12.5: 0.27, 20.0: 0.26},
    100: {10.0: 0.26, 12.5: 0.25, 20.0: 0.24},
}

# ---- Table 9 : recommended SCM dosage in high strength mixes (% of total cementitious)
TABLE9_SCM_RANGE = {
    "Fly ash": (15, 30),
    "GGBS": (25, 50),
    "Metakaolin": (5, 15),
    "Silica fume": (5, 10),
}

# Annex G typical admixture ranges (informative): dose % by mass of cementitious,
# water reduction % (to be CONFIRMED BY TRIAL - never derived from dose alone)
ADMIXTURE_TYPES = {
    "None": {"dose": (0.0, 0.0), "reduction": (0.0, 0.0)},
    "Plasticiser / water reducer (IS 9103)": {"dose": (0.3, 0.5), "reduction": (5.0, 12.0)},
    "Superplasticiser, normal (SMF/SNF)": {"dose": (0.5, 1.5), "reduction": (15.0, 30.0)},
    "Superplasticiser, PCE": {"dose": (0.5, 1.5), "reduction": (20.0, 40.0)},
}

# ---- IS 456:2000 Table 5 durability limits (UNVERIFIED - see header) ------------
# exposure -> (max w/c, min cementitious kg/m3)
IS456_REINFORCED = {
    "Mild": (0.55, 300),
    "Moderate": (0.50, 300),
    "Severe": (0.45, 320),          # 0.45 / 320 confirmed by IS 10262 Annex A-5, A-7
    "Very severe": (0.45, 340),
    "Extreme": (0.40, 360),
}
IS456_PLAIN = {
    "Mild": (0.60, 220),
    "Moderate": (0.60, 240),        # 0.60 / 240 confirmed by IS 10262 Annex F
    "Severe": (0.50, 250),
    "Very severe": (0.50, 260),
    "Extreme": (0.45, 280),
}
IS456_MAX_CEMENT_KG = 450.0         # IS 456 cl. 8.2.4.2 (max cement content, excl. SCM)

# Fresh density sanity window - an indicative rule of thumb, NOT a code limit
DENSITY_SANITY_RANGE = (2200.0, 2600.0)

# ---- Default specific gravities (taken from the Annex A..F examples) ------------
DEFAULT_SG = {
    "OPC": 3.15, "PPC": 2.88, "Fly ash": 2.20, "GGBS": 3.00,
    "Silica fume": 2.20, "Metakaolin": 2.50,
    "Coarse aggregate": 2.74, "Fine aggregate": 2.65,
    "Admixture": 1.145,
}

# Fig. 1 anchor points for the OPC 43 / curve-2 strength vs w/c relationship.
# These three points are the ONLY readings of Fig. 1 printed in the standard text
# (Annex A-5/B-5/C-5 : 48.25 -> 0.36 ; Annex E-5 : 38.25 -> 0.43 ; Annex F-5 : 20.77 -> 0.61).
FIG1_CURVE2_ANCHORS = [(20.77, 0.61), (38.25, 0.43), (48.25, 0.36)]

# UCI Concrete Compressive Strength dataset -----------------------------------------
UCI_URL = "https://archive.ics.uci.edu/static/public/165/concrete+compressive+strength.zip"
UCI_PAGE = "https://archive.ics.uci.edu/dataset/165/concrete+compressive+strength"
FEATURES = ["cement", "slag", "fly_ash", "water", "superplasticizer",
            "coarse_agg", "fine_agg", "age"]
TARGET = "strength"
FEATURE_LABELS = {
    "cement": "Cement (kg/m³)",
    "slag": "Blast furnace slag (kg/m³)",
    "fly_ash": "Fly ash (kg/m³)",
    "water": "Water (kg/m³)",
    "superplasticizer": "Superplasticizer (kg/m³)",
    "coarse_agg": "Coarse aggregate (kg/m³)",
    "fine_agg": "Fine aggregate (kg/m³)",
    "age": "Curing age (days)",
}
