"""
Scenario: E-commerce Fraud Detection
--------------------------------------
Business request: "Flag fraudulent transactions so we can block them."

Intentional pitfalls:
  1. chargeback_initiated_days_ago — only present for fraud cases → perfect target echo
  2. transaction_reviewed — only 8% of transactions were manually reviewed;
     labels are confirmed only for reviewed transactions (selection bias);
     unreviewed transactions assumed non-fraud but many are mislabeled
  3. previous_model_risk_score — output of the PREVIOUS fraud model used as a feature;
     creates a feedback loop (model learns to agree with its predecessor, not reality)
  4. Extreme imbalance: 0.3% fraud rate → AUROC meaningless; need AUPRC or precision@k
  5. ip_country — geographic proxy; also highly correlated with fraud in ways that
     reflect data collection bias (fraud teams focused on certain regions)
  6. No time-based split: fraud patterns change monthly (concept drift);
     random split leaks future fraud signatures into training data
  7. amount — extreme outliers: legitimate large B2B transactions mixed with
     consumer fraud dataset; separate populations
  8. device_fingerprint_age_hours — only very recent device fingerprints exist for
     fraud (fraudsters create new fingerprints per transaction); value range reveals
     the label (< 2 hours → almost always fraud)
"""
import numpy as np
import pandas as pd

rng = np.random.default_rng(42)
n = 20000

# 0.3% fraud rate — severe imbalance
n_fraud = int(n * 0.003)
n_legit = n - n_fraud
is_fraud = np.array([True] * n_fraud + [False] * n_legit)
rng.shuffle(is_fraud)

amount = np.where(
    is_fraud,
    rng.choice(
        [rng.uniform(10, 500, n), rng.uniform(500, 5000, n)],
        n
    ).diagonal(),
    np.where(
        rng.random(n) < 0.02,
        rng.uniform(2000, 50000, n),   # legitimate large transactions (B2B)
        rng.lognormal(4.5, 1.2, n)     # typical consumer transactions
    )
)
amount = amount.clip(1).round(2)

hour_of_day = np.where(is_fraud, rng.integers(0, 24, n), rng.integers(7, 23, n))
day_of_week = rng.integers(0, 7, n)
user_account_age_days = np.where(
    is_fraud, rng.integers(0, 30, n), rng.integers(1, 3000, n)
)
num_transactions_last_24h = np.where(
    is_fraud, rng.integers(3, 30, n), rng.poisson(1.5, n)
)
device_type = rng.choice(["mobile", "desktop", "tablet"], n, p=[0.55, 0.38, 0.07])
is_new_device = np.where(is_fraud, rng.binomial(1, 0.85, n), rng.binomial(1, 0.12, n))
merchant_category = rng.choice(
    [f"CAT{i:03d}" for i in range(50)], n
)
ip_country = np.where(
    is_fraud,
    rng.choice(["NG", "RO", "US", "BR", "VN"], n, p=[0.25, 0.20, 0.35, 0.10, 0.10]),
    rng.choice(["US", "CA", "GB", "DE", "AU"], n, p=[0.55, 0.12, 0.10, 0.10, 0.13])
)

# PITFALL 7: extreme amount outliers from B2B transactions
# (B2B > $10K: 0.1% of rows, legitimate; distorts amount importance)

# PITFALL 8: device_fingerprint_age_hours
# Fraudsters create new fingerprints; legit users have old devices
device_fingerprint_age_hours = np.where(
    is_fraud,
    rng.uniform(0, 2, n),     # fraud: brand new fingerprint (< 2 hrs)
    rng.uniform(24, 8760, n)  # legit: device used for days/months
)

# PITFALL 3: previous_model_risk_score — prior model output as feature
# It's correlated with fraud (AUC ~0.76) but creates feedback loop
prior_model_score = (
    0.4 * is_fraud.astype(float)
    + 0.3 * (device_fingerprint_age_hours < 2).astype(float)
    + 0.1 * (num_transactions_last_24h > 5).astype(float)
    + rng.beta(1, 4, n) * 0.2
).clip(0, 1).round(3)

# PITFALL 2: transaction_reviewed — only 8% reviewed; selection bias
# Fraud team reviews suspicious transactions, so reviewed=True overrepresents fraud
reviewed_prob = np.where(is_fraud, 0.90, 0.06)
transaction_reviewed = rng.binomial(1, reviewed_prob, n).astype(bool)
# In reality, labels are ONLY confirmed for reviewed transactions
# Unreviewed non-fraud may contain undetected fraud (5% estimated)
label_confirmed = transaction_reviewed  # label noise for unreviewed

# PITFALL 1: chargeback_initiated_days_ago — post-outcome, only for fraud
chargeback_initiated_days_ago = np.where(
    is_fraud,
    rng.integers(1, 45, n),
    np.nan
)

# Fake transaction timestamp (for concept drift demo — no actual drift in data,
# but the absence of time-based split is the pitfall)
days_ago = rng.integers(0, 365, n)
transaction_timestamp = pd.Timestamp("2025-02-26") - pd.to_timedelta(days_ago, unit="D")

df = pd.DataFrame({
    "transaction_id": [f"TXN{i:08d}" for i in range(n)],
    "transaction_timestamp": transaction_timestamp,
    "amount": amount,
    "hour_of_day": hour_of_day,
    "day_of_week": day_of_week,
    "merchant_category": merchant_category,
    "ip_country": ip_country,
    "user_account_age_days": user_account_age_days,
    "num_transactions_last_24h": num_transactions_last_24h,
    "device_type": device_type,
    "is_new_device": is_new_device,
    "device_fingerprint_age_hours": device_fingerprint_age_hours,  # PITFALL 8
    "previous_model_risk_score": prior_model_score,                # PITFALL 3
    "transaction_reviewed": transaction_reviewed,                   # PITFALL 2
    "chargeback_initiated_days_ago": chargeback_initiated_days_ago,# PITFALL 1
    "is_fraud": is_fraud,
})

df.to_csv("data.csv", index=False)
print(f"Rows: {len(df)} | Fraud rate: {df.is_fraud.mean():.3%}")
print(f"Reviewed transactions: {df.transaction_reviewed.mean():.1%}")
print(f"chargeback null rate (should be ~99.7%): {df.chargeback_initiated_days_ago.isna().mean():.1%}")
print(f"device_fingerprint_age_hours — fraud median: {df[df.is_fraud].device_fingerprint_age_hours.median():.2f}h  legit median: {df[~df.is_fraud].device_fingerprint_age_hours.median():.0f}h")
