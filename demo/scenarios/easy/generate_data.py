"""
Scenario 1 (Easy): Premium Subscription Upgrade Prediction
-----------------------------------------------------------
Business: Predict whether a free-tier user will upgrade to premium in the next 30 days.
Data: Clean, no leakage, ~28% positive rate, no protected attribute concerns.
"""
import numpy as np
import pandas as pd

rng = np.random.default_rng(42)
n = 1200

age = rng.integers(22, 65, n)
days_since_signup = rng.integers(1, 730, n)
num_logins_30d = rng.poisson(8, n)
avg_session_minutes = rng.gamma(3, 8, n).round(1)
num_purchases_30d = rng.poisson(2, n)
plan_type = rng.choice(["free", "trial"], n, p=[0.7, 0.3])

# Label: upgrade probability driven by logins, session length, purchases
log_odds = (
    -2.5
    + 0.04 * num_logins_30d
    + 0.02 * avg_session_minutes
    + 0.3 * num_purchases_30d
    + 0.5 * (plan_type == "trial")
)
prob = 1 / (1 + np.exp(-log_odds))
will_upgrade = rng.binomial(1, prob).astype(bool)

df = pd.DataFrame({
    "user_id": [f"U{i:05d}" for i in range(n)],
    "age": age,
    "days_since_signup": days_since_signup,
    "num_logins_30d": num_logins_30d,
    "avg_session_minutes": avg_session_minutes,
    "num_purchases_30d": num_purchases_30d,
    "plan_type": plan_type,
    "will_upgrade": will_upgrade,
})

df.to_csv("data.csv", index=False)
print(f"Rows: {len(df)}  |  Positive rate: {df.will_upgrade.mean():.1%}")
print(df.head())
