# Data Architecture Plan (Firestore Emulator -> Firestore)

This plan documents the data model and flow for the Financial Transaction Categorization & Insights Tool.
It is written with juniors in mind: clear naming, simple relationships, and practical reasoning.

## Goals
- Support multi-file uploads (up to 10 files per run).
- Store custom categories, keywords, and business/personal tags.
- Produce summaries, charts, and narrative reports.
- Keep the Firestore model so migration from emulator to production is minimal.

## Collections (Firestore)

### 1) users/{userId}
**Purpose**: Root document for a user account.
**Fields**:
- `profile`: name, email, created_at
- `settings`: default_currency, timezone, default_entity

**Why**: Firestore is user-centric. Putting everything under a user document keeps data scoped and secure.

### 2) users/{userId}/categories/{categoryId}
**Purpose**: User-defined categories and matching hints.
**Fields**:
- `name`
- `type`: `income` | `expense`
- `entity`: `business` | `personal` | `mixed`
- `keywords`: array of strings
- `aliases`: array of strings
- `is_active`
- `created_at`, `updated_at`

**Why**: Categories are personalized. Keeping them per-user avoids conflicts and makes queries fast.

### 3) users/{userId}/uploads/{uploadId}
**Purpose**: Track the status and metadata of a multi-file ingestion job.
**Fields**:
- `status`: `pending` | `processing` | `done` | `error`
- `source_files`: array of `{filename, size, rows}`
- `row_count`, `error_count`
- `schema_mapping`: normalized columns used for parsing
- `created_at`, `completed_at`

**Why**: Uploads are the main unit of work. We need to reference them from transactions and reports.

### 4) users/{userId}/transactions/{transactionId}
**Purpose**: Cleaned, normalized, categorized transactions.
**Fields**:
- `upload_id`
- `date` (ISO date string)
- `description`
- `amount` (positive for income, negative for expense)
- `category_id`, `category_name`
- `entity`: `business` | `personal`
- `tags`: array of strings
- `merchant` (optional)
- `raw`: optional original fields
- `created_at`

**Why**: This is the primary dataset for analytics. Store it in a flat, query-friendly shape.

### 5) users/{userId}/daily_aggregates/{dateId}
**Purpose**: Precomputed totals by day for charts.
**Fields**:
- `date`
- `income_total`
- `expense_total`
- `net`
- `business_expense_total`
- `personal_expense_total`
- `updated_at`

**Why**: Aggregations in Firestore are expensive. Precompute daily totals for dashboard speed.

### 6) users/{userId}/reports/{reportId}
**Purpose**: Store narrative output and chart-ready summaries.
**Fields**:
- `upload_id`
- `summary` (totals, top categories)
- `narrative` (string)
- `charts` (arrays for UI)
- `export_links` (excel/pdf)
- `created_at`

**Why**: Reports are derived artifacts. Persist them so the UI can load instantly.

## Optional: Learning & Corrections
### users/{userId}/merchant_rules/{merchantId}
**Purpose**: Remember user corrections for faster future categorization.
**Fields**:
- `merchant`
- `category_id`
- `entity`
- `confidence`
- `last_seen`

**Why**: Lets the system "learn" without an ML model initially.

## Ingestion Flow (Upload -> Results)
1. Create `uploads/{uploadId}` with `status = processing`.
2. Parse files and normalize columns.
3. Write `transactions` and update `daily_aggregates`.
4. Create `reports/{reportId}` with summaries + narrative.
5. Update `uploads/{uploadId}` to `done`.

## Index Strategy (Firestore)
- `transactions`: index `(date, category_id)`
- `transactions`: index `(date, entity)`
- `transactions`: index `(upload_id, date)`
- `reports`: index `(upload_id, created_at)`
- `daily_aggregates`: index `(date)`

**Why**: These are common query patterns for charts and report views.

## Storage Notes
- Raw uploads live on disk for emulator testing.
- In production, move raw files to GCS with a short retention policy.
- Keep denormalized fields like `category_name` for faster UI queries.

## Migration Notes
- Firestore Emulator uses the same API as production.
- Stick to Firestore-style documents and subcollections to avoid refactors.
