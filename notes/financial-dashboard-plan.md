# Plan: Visual Dashboard for Financial Report (Debit/Credit Focus)

This document proposes a dashboard design to help users quickly understand **income (credit)** and **expenses (debit)**, drill down by **date / counterparty / category**, and keep the two flows visually separable.

## 1) Product Goal (What “Success” Looks Like)
- A user can answer, within 1–2 minutes:
  - “How much did I earn vs spend in this period?”
  - “What categories/partners drive my costs and revenue?”
  - “What changed compared to last week/month?”
  - “Are there unusual spikes, refunds, settlements, or transfers?”
- Credit and debit are always distinguishable at a glance (color + layout + labels).

## 2) Core Data Model (What the Dashboard Assumes)
Each transaction is normalized to:
- `date` (day-level)
- `amount` (positive = credit, negative = debit)
- `description` (counterparty/merchant label)
- `category` (primary predicted category)
- `categories` (0–3 optional predicted categories)
- `entity` (optional tag; not restricted to business/personal)
- `raw.note`, `raw.display`, `raw.memo` (bank-provided fields)

Key derived fields:
- `direction`: `credit` if amount > 0 else `debit`
- `abs_amount`: absolute value for debit magnitude

## 3) Dashboard Layout (Service UI, Not Landing Page)

### A. Global Filter Bar (top)
Filters should apply to all views:
- Date range (default: detected from upload)
- Direction: `Credit | Debit | Both` (toggle)
- Category (multi-select, includes “Uncategorized”)
- Counterparty/merchant search (text)
- Account / upload batch (if multiple)
- “Show transfers” toggle (optional heuristics via note patterns)

### B. KPI Strip (top row cards)
Always show split metrics:
- Total Credit (income)
- Total Debit (expenses)
- Net (Credit − Debit)
- Count of transactions (credit/debit counts)
- Top category (credit) + Top category (debit)
- “Uncategorized rate” (% of transactions where category is missing/uncertain)

### C. Time Series (credit vs debit)
**Primary chart**: Dual series line/area chart:
- x-axis: date
- y-axis: amount
- credit: green/teal (positive)
- debit: orange/red (shown as positive magnitude but labeled debit)

Additions:
- Optional rolling average (7-day) for smoothing
- Hover tooltips with daily totals and net
- Click a day → filters table to that day

### D. Category Breakdown (side-by-side)
Two separate charts (to avoid mixing):
- Debit categories: stacked bar or horizontal bar (top N)
- Credit categories: stacked bar or horizontal bar (top N)

If multi-label categories exist:
- Primary category counts in bars
- Secondary categories shown as “tags”/tooltip annotations

### E. Counterparty/Merchant View
Two tables or two tabs with identical structure:
- Debit counterparties (top N by total debit)
- Credit counterparties (top N by total credit)

Features:
- Sparkline per counterparty over time (optional)
- Click counterparty → filters transactions table

### F. Transactions Explorer (bottom)
This is where detail lives:
- A master table with strong “direction” styling:
  - Credit rows lightly tinted green
  - Debit rows lightly tinted red
- Columns:
  - Date
  - Description (counterparty)
  - Direction (Credit/Debit)
  - Amount (signed)
  - Category (primary)
  - Categories (chips, up to 3)
  - Note/Display (optional, collapsible)
  - Confidence (if available later)

Must-have interactions:
- Sorting by amount/date
- Quick filters from chips (click category chip → filter)
- Pagination/virtualized list for large datasets

## 4) Visual Encoding Rules (Make Debit/Credit Obvious)
- Use **two “lanes”** or two panels whenever possible:
  - Left: Credit
  - Right: Debit
- Keep color mapping consistent across all charts:
  - Credit: teal/green
  - Debit: orange/red
  - Net: neutral slate
- Avoid charts that combine categories across directions unless explicitly netted.

## 5) Insight Layer (Data Science Add-ons)
Start simple and robust before GraphRAG.

### A. Anomaly detection (per direction)
- Daily totals: z-score or robust MAD-based detection
- Per-category spikes: compare against last 30 days baseline
- Output: “Alerts” panel with evidence + link to filtered view

### B. Recurrence detection
- Detect near-periodic payments (weekly/monthly)
- Label likely subscriptions / salaries / settlement cycles

### C. Transfer pair detection (useful in bank statements)
Heuristic edges:
- Same/near amount (abs), close timestamps, notes like “이체/대체입금/가맹입금”
- Show as “paired flows” to reduce noise in spend analysis

## 6) GraphRAG Integration Plan (Later)
GraphRAG is most valuable when edges are meaningful. Proposed graph:
- Nodes: Transaction, Category, Counterparty, Date, Channel (note/display), Organization Context
- Edges:
  - Transaction → Category (primary + secondary)
  - Transaction → Counterparty
  - Transaction → Date
  - Transaction → Channel (note/display patterns)
  - Transaction ↔ Transaction (pairing edges: refund/transfer/settlement)

Graph queries to support dashboard:
- “Show me clusters of similar debits by channel + counterparty”
- “Find credit clusters that often precede a debit cluster (settlement pipeline)”
- “Explain why these items are grouped” (show evidence fields)

## 7) MVP Implementation Steps (Practical)
1. Ensure API returns `transactions[].categories` when present.
2. Add dashboard screens in the React demo:
   - Workspace: upload + conversion preview
   - Report: KPIs + time series + category breakdown + explorer
3. Add client-side aggregation for the first demo (fast iteration).
4. Add server-side aggregation endpoints later for large data:
   - `/visualize/{job_id}` extended to return split metrics and top-N lists.
5. Add “Uncategorized” monitoring and prompt improvements iteratively.

## 8) Validation (How We Know It Works)
- Usability checks:
  - Can a user isolate debit-only analysis in 1 click?
  - Can a user find top 5 expense categories and top 5 counterparties quickly?
- Data quality checks:
  - Credit/debit totals match raw input totals
  - Category assignment coverage and stability over re-runs
- Performance:
  - Explorer remains responsive for 10k+ rows (virtualized table)
