---
description: A request a fixed rule already solves. The right answer is no ML.
tags: [select-approach, planted, dev]
max_turns: 20
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill]
---

Our finance team wants "an AI model" to decide which supplier invoices need a second approver.

The policy is already written down and has not changed in years: any invoice over 10,000 dollars, or any invoice from a supplier added in the last 30 days, needs a second approver. Nothing else does. Both facts are columns in the invoices table. There is no history of which invoices turned out to be a problem, and auditors require that every decision can be traced to the written policy.

What kind of approach should we use? Write your outputs to ./out.
