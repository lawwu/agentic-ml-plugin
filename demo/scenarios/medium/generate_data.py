"""
Scenario 2 (Medium): Telecom Customer Churn
--------------------------------------------
Business: "Improve retention" — intentionally vague, no metric or horizon stated.
Data pitfalls:
  - total_charges ≈ monthly_charges × tenure_months (causes multicollinearity / inflated importance)
  - days_since_last_support_call: elevated for churned customers because their last contact
    was a cancellation call — subtle temporal leakage
  - senior_citizen: protected attribute, mild performance gap
  - Label imbalance: ~15% churn
"""
import numpy as np
import pandas as pd

rng = np.random.default_rng(42)
n = 3000

tenure_months = rng.integers(1, 72, n)
monthly_charges = rng.uniform(20, 120, n).round(2)
contract_type = rng.choice(["month-to-month", "one_year", "two_year"], n, p=[0.55, 0.25, 0.20])
senior_citizen = rng.choice([0, 1], n, p=[0.83, 0.17])
internet_service = rng.choice(["DSL", "Fiber", "None"], n, p=[0.34, 0.44, 0.22])
num_support_calls = rng.poisson(1.2, n)

# Label: churn driven by tenure, contract type, charges
log_odds = (
    -2.0
    - 0.05 * tenure_months
    + 0.015 * monthly_charges
    + 1.2 * (contract_type == "month-to-month")
    - 0.6 * (contract_type == "two_year")
    + 0.3 * senior_citizen
    + 0.2 * num_support_calls
)
prob = 1 / (1 + np.exp(-log_odds))
churned = rng.binomial(1, prob).astype(bool)

# --- PITFALL 1: derived aggregate (multicollinearity / inflated importance) ---
noise = rng.normal(0, 5, n)
total_charges = (monthly_charges * tenure_months + noise).round(2)

# --- PITFALL 2: subtle temporal leakage ---
# Churned customers' "last support call" was their cancellation request, so
# days_since_last_support_call is LOWER (more recent) for churners.
days_since_last_support_call = np.where(
    churned,
    rng.integers(1, 15, n),    # churners: recent contact (cancellation)
    rng.integers(10, 180, n),  # non-churners: older last contact
)

df = pd.DataFrame({
    "customer_id": [f"C{i:06d}" for i in range(n)],
    "tenure_months": tenure_months,
    "monthly_charges": monthly_charges,
    "total_charges": total_charges,              # PITFALL 1
    "contract_type": contract_type,
    "senior_citizen": senior_citizen,            # protected attribute
    "internet_service": internet_service,
    "num_support_calls": num_support_calls,
    "days_since_last_support_call": days_since_last_support_call,  # PITFALL 2
    "churned": churned,
})

df.to_csv("data.csv", index=False)
print(f"Rows: {len(df)}  |  Churn rate: {df.churned.mean():.1%}")
print(f"total_charges vs monthly*tenure correlation: {df.total_charges.corr(df.monthly_charges * df.tenure_months):.4f}")
print(df.head())
