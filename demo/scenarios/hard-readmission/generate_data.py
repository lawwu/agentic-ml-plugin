"""
Scenario: Hospital 30-Day Readmission Prediction
-------------------------------------------------
Business request: "We want to reduce readmissions."

Intentional pitfalls:
  1. days_until_readmission — only non-null for readmitted patients → perfect target echo
  2. discharge_to — determined at discharge (same time as label window opens); ambiguous
     availability depending on whether prediction is at admission or discharge
  3. insurance_type — proxy for race/SES under ECOA-adjacent healthcare equity frameworks
  4. attending_physician_id — encodes physician-level variability, not patient risk
  5. race and age — protected attributes with real performance gaps
  6. Patients who died before 30 days: label=False but they COULDN'T be readmitted →
     censoring problem; their "non-readmission" is not exchangeable with healthy survivors
  7. Label ambiguity: no distinction between planned readmissions (chemo cycle 2) vs.
     unplanned (complication). Standard 30-day metric conflates these.
  8. discharge_notes_readmission_risk — derived from clinician notes at discharge that
     encode the physician's own readmission risk assessment → target leakage via proxy
"""
import numpy as np
import pandas as pd

rng = np.random.default_rng(42)
n = 4000

age = rng.integers(18, 90, n)
gender = rng.choice(["M", "F", "Other"], n, p=[0.48, 0.50, 0.02])
race = rng.choice(
    ["White", "Black", "Hispanic", "Asian", "Other"],
    n, p=[0.62, 0.17, 0.13, 0.05, 0.03]
)
insurance_type = np.where(
    race == "White",
    rng.choice(["Private", "Medicare", "Medicaid", "Uninsured"], n, p=[0.50, 0.30, 0.15, 0.05]),
    np.where(
        race == "Black",
        rng.choice(["Private", "Medicare", "Medicaid", "Uninsured"], n, p=[0.30, 0.28, 0.32, 0.10]),
        rng.choice(["Private", "Medicare", "Medicaid", "Uninsured"], n, p=[0.35, 0.25, 0.30, 0.10]),
    )
)

num_comorbidities = rng.poisson(2.5, n).clip(0, 8)
length_of_stay_days = rng.integers(1, 21, n)
num_prior_admissions_1yr = rng.poisson(0.8, n).clip(0, 5)
attending_physician_id = rng.choice([f"MD{i:03d}" for i in range(60)], n)

# Label: 30-day readmission
log_odds = (
    -2.5
    + 0.03 * num_comorbidities
    + 0.08 * num_prior_admissions_1yr
    + 0.015 * (age - 50).clip(0)
    + 0.4 * (insurance_type == "Medicaid")
    + 0.3 * (insurance_type == "Uninsured")
    + 0.25 * (race == "Black")
    + rng.normal(0, 0.3, n)
)
prob = 1 / (1 + np.exp(-log_odds))
readmitted_30d = rng.binomial(1, prob).astype(bool)

# Died before 30 days (censored) — 3% of patients; can't be readmitted
died_before_30d = rng.binomial(1, 0.03, n).astype(bool)
readmitted_30d = readmitted_30d & ~died_before_30d  # censored patients always False

discharge_to = rng.choice(
    ["Home", "SNF", "Rehab", "Hospice"],
    n, p=[0.65, 0.18, 0.13, 0.04]
)
# Hospice → patient is dying; nearly never readmitted (they die in hospice)
# SNF patients have higher readmission rates
discharge_multiplier = np.where(
    discharge_to == "Hospice", 0.05,
    np.where(discharge_to == "SNF", 1.4, 1.0)
)
readmitted_30d = (rng.uniform(0, 1, n) < prob * discharge_multiplier).astype(bool)
readmitted_30d = readmitted_30d & ~died_before_30d

# PITFALL 1: days_until_readmission — post-outcome, only for readmitted
days_until_readmission = np.where(
    readmitted_30d,
    rng.integers(1, 30, n),
    np.nan
)

# PITFALL 8: clinician's readmission risk note at discharge (encodes clinical judgment
# which is partially a prediction of the outcome itself)
# High-risk patients get higher scores from physicians at discharge
note_risk_score = (
    0.3 * num_comorbidities / 8
    + 0.3 * (prob > 0.25).astype(float)
    + rng.normal(0, 0.1, n)
).clip(0, 1).round(2)

primary_diagnosis_icd = rng.choice(
    [f"I{rng.integers(10,99)}.{rng.integers(0,9)}" for _ in range(120)], n
)

df = pd.DataFrame({
    "patient_id": [f"PAT{i:06d}" for i in range(n)],
    "age": age,
    "gender": gender,
    "race": race,
    "insurance_type": insurance_type,
    "primary_diagnosis_icd": primary_diagnosis_icd,
    "num_comorbidities": num_comorbidities,
    "length_of_stay_days": length_of_stay_days,
    "num_prior_admissions_1yr": num_prior_admissions_1yr,
    "attending_physician_id": attending_physician_id,
    "discharge_to": discharge_to,
    "died_before_30d": died_before_30d,       # should be excluded, often isn't
    "days_until_readmission": days_until_readmission,  # PITFALL 1: post-outcome
    "discharge_notes_readmission_risk": note_risk_score,  # PITFALL 8: proxy leakage
    "readmitted_30d": readmitted_30d,
})

df.to_csv("data.csv", index=False)
print(f"Rows: {len(df)} | Readmission rate: {df.readmitted_30d.mean():.1%}")
print(f"Censored (died before 30d): {df.died_before_30d.sum()} ({df.died_before_30d.mean():.1%})")
print(f"days_until_readmission null rate: {df.days_until_readmission.isna().mean():.1%}")
print(f"Insurance by race:\n{df.groupby('race')['insurance_type'].value_counts(normalize=True).unstack().round(2)}")
