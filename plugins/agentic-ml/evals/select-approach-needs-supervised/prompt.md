---
description: The clean twin of rule-is-enough. Labeled history exists and no rule is known, so supervised learning fits.
tags: [select-approach, clean, dev]
max_turns: 20
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill]
---

Our finance team wants to know which supplier invoices are likely to be disputed, so a clerk can check them before payment.

We have three years of invoices, about 400,000 rows, each marked with whether it was later disputed (about 2 percent were). For each invoice we know the amount, the supplier, the supplier's age and dispute history, the purchase category, and who raised it. Nobody has a rule that works: the clerks say disputes "depend on a mix of things". A clerk can check about 50 invoices a day, and results are needed the morning after an invoice arrives.

What kind of approach should we use? Write your outputs to ./out.
