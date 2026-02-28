"""
Scenario: B2B SaaS Customer Churn (xhard difficulty)
------------------------------------------------------
Business request: "Predict which companies will not renew next quarter."

Intentional pitfalls (composite — no single-column leakage):
  1. Composite leak: support_tickets_open + days_since_last_login together
     predict churn near-perfectly, but neither alone does
  2. Entity-level temporal leakage: same company_id appears across train/test
     unless group-aware split is used (GroupKFold or group-time split)
  3. Survivorship bias: companies that churned early are absent from later
     snapshots — naive random splits mix temporal cohorts
  4. Label definition drift: churned definition changes at snapshot_quarter=4
     (from "no renewal" to "no renewal OR downgrade >50%"), inflating churn rate
  5. Future-peeking feature: next_quarter_pipeline_value is only known after
     the prediction window closes (post-outcome feature)
  6. Simpson's paradox: discount_pct correlates positively with churn overall
     but negatively within each company_size segment (large companies get
     discounts AND churn less)
  7. Protected proxy: region is a proxy for company_size which correlates with
     churn; bias audit should catch regional disparate impact
  8. Feature staleness: nps_score is updated only annually; stale for 3 of 4
     quarters per year
"""
import numpy as np
import pandas as pd

rng = np.random.default_rng(42)

N_COMPANIES = 2000
N_QUARTERS = 6

company_ids = [f"CO{i:05d}" for i in range(N_COMPANIES)]
industries = rng.choice(
    ["SaaS", "Fintech", "Healthcare", "Retail", "Manufacturing", "Education"],
    N_COMPANIES,
    p=[0.30, 0.20, 0.15, 0.15, 0.12, 0.08],
)
company_sizes = rng.choice(
    ["small", "mid", "large"],
    N_COMPANIES,
    p=[0.55, 0.30, 0.15],
)
# PITFALL 7: region is a proxy for company_size (large companies cluster in US/EU)
region_probs = {
    "small": ["APAC", "LATAM", "MEA", "US", "EU"],
    "mid":   ["US", "EU", "APAC", "LATAM", "MEA"],
    "large": ["US", "EU", "US", "EU", "APAC"],
}
regions = np.array([
    rng.choice(["APAC", "LATAM", "MEA", "US", "EU"],
               p={"small": [0.25, 0.25, 0.20, 0.20, 0.10],
                  "mid":   [0.15, 0.10, 0.10, 0.35, 0.30],
                  "large": [0.10, 0.05, 0.05, 0.45, 0.35]}[company_sizes[i]])
    for i in range(N_COMPANIES)
])

# Base ARR by company size
arr_base = {
    "small": rng.lognormal(9.2, 0.5, N_COMPANIES),   # ~$10K median
    "mid":   rng.lognormal(11.5, 0.6, N_COMPANIES),  # ~$100K median
    "large": rng.lognormal(13.8, 0.7, N_COMPANIES),  # ~$1M median
}
arr_usd_base = np.array([
    arr_base[company_sizes[i]][i] for i in range(N_COMPANIES)
]).clip(5000, 5_000_000).round(-2)

seat_count_base = np.where(
    company_sizes == "small",
    rng.integers(2, 30, N_COMPANIES),
    np.where(
        company_sizes == "mid",
        rng.integers(30, 200, N_COMPANIES),
        rng.integers(200, 2000, N_COMPANIES),
    )
)

# PITFALL 8: NPS score updated annually (one draw per company, reused for 3/4 quarters)
nps_annual = rng.integers(20, 90, N_COMPANIES)

rows = []
quarter_dates = pd.date_range("2023-01-01", periods=N_QUARTERS, freq="QS")

for q_idx in range(N_QUARTERS):
    snapshot_date = quarter_dates[q_idx]
    snapshot_quarter = q_idx + 1  # 1-based

    for c_idx in range(N_COMPANIES):
        cid = company_ids[c_idx]
        size = company_sizes[c_idx]
        region = regions[c_idx]
        industry = industries[c_idx]

        # Usage metrics with quarterly noise
        mau_base = seat_count_base[c_idx] * rng.uniform(0.4, 1.0)
        monthly_active_users = max(1, int(mau_base + rng.normal(0, mau_base * 0.1)))

        # PITFALL 1 (part A): support_tickets_open — moderate signal alone
        support_tickets_open = int(rng.poisson(
            3 + (seat_count_base[c_idx] / 50) * rng.uniform(0.5, 2.0)
        ))

        # PITFALL 1 (part B): days_since_last_login — moderate signal alone
        days_since_last_login = int(rng.gamma(2, 10))

        # PITFALL 8: NPS only refreshed in Q1 each year; stale in Q2-Q4
        if snapshot_quarter % 4 == 1:  # annual refresh
            nps_annual[c_idx] = max(0, min(100, nps_annual[c_idx] + rng.integers(-5, 6)))
        nps_score = nps_annual[c_idx]

        arr_usd = arr_usd_base[c_idx] * (1 + rng.normal(0, 0.03))
        arr_usd = round(max(5000, arr_usd), -2)

        # PITFALL 6 (Simpson's paradox): discount_pct
        # Small companies get aggressive acquisition discounts AND churn more
        # Large companies get minimal/no discounts (flat enterprise rates) AND churn less
        # → Overall: discount positively correlates with churn (confounded by size)
        # → Within each size segment: higher discount slightly REDUCES churn
        discount_pct = round(
            {"small": rng.uniform(20, 45),
             "mid":   rng.uniform(8, 22),
             "large": rng.uniform(0, 8)}[size], 1
        )

        contract_months_remaining = rng.integers(0, 13)

        # ---------- label computation ----------

        # Base churn probability by size (large churn much less)
        # Wide gap needed for Simpson's paradox to show in aggregate
        base_churn_p = {"small": 0.32, "mid": 0.14, "large": 0.04}[size]

        # PITFALL 6: discount reduces churn within segment
        # Within-segment: higher discount slightly reduces churn (true negative signal)
        # But because small companies have both high discounts AND high base churn,
        # the overall (unconditional) correlation is positive — Simpson's paradox
        discount_effect = -0.0006 * discount_pct

        # PITFALL 1: composite signal (interaction term, not additive)
        composite_risk = (
            (support_tickets_open > 8) and (days_since_last_login > 25)
        )
        composite_effect = 0.40 if composite_risk else 0.0

        # Mild individual effects (neither alone is enough)
        ticket_effect = 0.005 * max(0, support_tickets_open - 5)
        login_effect  = 0.003 * max(0, days_since_last_login - 20)

        nps_effect = -0.002 * (nps_score - 50)  # positive NPS → lower churn
        mau_effect = -0.0003 * (monthly_active_users / max(1, seat_count_base[c_idx]) * 100 - 70)

        churn_p = (
            base_churn_p
            + discount_effect
            + composite_effect
            + ticket_effect
            + login_effect
            + nps_effect
            + mau_effect
        ).clip(0.02, 0.92)

        # PITFALL 4: label definition drift at snapshot_quarter >= 4
        # Before Q4: churned = no renewal
        # Q4+: churned = no renewal OR downgrade > 50%
        if snapshot_quarter >= 4:
            downgrade_extra = rng.binomial(1, 0.06)  # 6% downgrade >50%
            churned = bool(rng.binomial(1, churn_p)) or bool(downgrade_extra)
        else:
            churned = bool(rng.binomial(1, churn_p))

        # PITFALL 3: survivorship bias — churned companies don't appear in later quarters
        # (handled below: we remove rows for companies that churned in earlier quarters)

        # PITFALL 5: next_quarter_pipeline_value — future feature (post-outcome)
        # High pipeline value → lower churn; but this is ONLY known next quarter
        next_quarter_pipeline_value = round(
            arr_usd * rng.uniform(0.5, 1.5) * (0.3 if churned else 1.1), -2
        )

        rows.append({
            "company_id": cid,
            "snapshot_date": snapshot_date.date(),
            "snapshot_quarter": snapshot_quarter,
            "industry": industry,
            "company_size": size,
            "region": region,
            "arr_usd": arr_usd,
            "seat_count": seat_count_base[c_idx],
            "monthly_active_users": monthly_active_users,
            "support_tickets_open": support_tickets_open,
            "days_since_last_login": days_since_last_login,
            "nps_score": nps_score,
            "discount_pct": discount_pct,
            "contract_months_remaining": contract_months_remaining,
            "next_quarter_pipeline_value": next_quarter_pipeline_value,
            "churned": churned,
        })

df = pd.DataFrame(rows)

# PITFALL 3: Apply survivorship bias — remove post-churn snapshots
# Once a company churns in quarter Q, it's absent from Q+1 onward
churned_quarter = (
    df[df["churned"]]
    .groupby("company_id")["snapshot_quarter"]
    .min()
    .rename("churn_quarter")
)
df = df.merge(churned_quarter, on="company_id", how="left")
df["churn_quarter"] = df["churn_quarter"].fillna(999)
df = df[df["snapshot_quarter"] <= df["churn_quarter"]].drop(columns=["churn_quarter"])

# Drop snapshot_quarter (internal bookkeeping; kept in data as a subtle pitfall hint)
# Actually keep it — agents should notice label drift correlates with this column

df = df.reset_index(drop=True)
df.to_csv("data.csv", index=False)

# Summary stats
print(f"Rows: {len(df)} | Companies: {df.company_id.nunique()}")
print(f"Churn rate overall:  {df.churned.mean():.3%}")
print(f"Churn rate Q1-Q3:    {df[df.snapshot_quarter < 4].churned.mean():.3%}")
print(f"Churn rate Q4-Q6:    {df[df.snapshot_quarter >= 4].churned.mean():.3%}  (label drift)")
print(f"Snapshots per company (median): {df.groupby('company_id').size().median():.1f}")
print(
    f"Composite leak (tickets>8 AND login>25) prevalence: "
    f"{((df.support_tickets_open > 8) & (df.days_since_last_login > 25)).mean():.3%}"
)
print(
    f"Discount vs churn (overall corr): "
    f"{df['discount_pct'].corr(df['churned'].astype(float)):.3f}  "
    f"(positive = naive Simpson direction)"
)
for sz in ["small", "mid", "large"]:
    sub = df[df.company_size == sz]
    corr = sub["discount_pct"].corr(sub["churned"].astype(float))
    print(f"  discount vs churn within {sz}: {corr:.3f}  (should be negative)")
