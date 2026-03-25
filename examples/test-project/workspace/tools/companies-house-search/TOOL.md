---
name: companies-house-search
description: >
  Search and filter the Companies House directory of UK registered companies via the
  Lenkie Working Capital API. Use this tool to find prospect companies by industry
  (SIC code), company status, incorporation date range, postcode, or company name.
  All filters are combined with AND logic; multi-value parameters (sic_codes, statuses,
  company_types) use OR logic internally. Returns a paginated list of companies.
  Page size is capped at 100.
parameters:
  sic_codes:
    type: string
    description: >
      Comma-separated SIC (Standard Industrial Classification) codes to filter by (OR logic).
      Example: "86230,86210" for dental and GP practices.
    required: false
  name_search:
    type: string
    description: >
      Full-text search on company name. Supports multi-word queries.
      Ignored when company_number is set.
    required: false
  company_number:
    type: string
    description: >
      Exact Companies House registration number (e.g. "12345678").
      When provided, all other filters are ignored.
    required: false
  statuses:
    type: string
    description: >
      Comma-separated company status values to filter by (OR logic).
      Common values: Active, Dissolved, Liquidation, Administration.
      Defaults to Active only when not specified. Example: "Active"
    required: false
  company_types:
    type: string
    description: >
      Comma-separated company type values to filter by (OR logic).
      Example: "Private Limited Company"
    required: false
  postcode:
    type: string
    description: Registered office postcode, exact match (e.g. "EC1A 1BB").
    required: false
  incorporation_date_from:
    type: string
    description: >
      Earliest incorporation date, inclusive (YYYY-MM-DD).
      Use to filter for established businesses, e.g. incorporated before 2021-01-01
      to find companies trading for 5+ years.
    required: false
  incorporation_date_to:
    type: string
    description: Latest incorporation date, inclusive (YYYY-MM-DD).
    required: false
  next_accounts_due_from:
    type: string
    description: Earliest next-accounts-due date, inclusive (YYYY-MM-DD).
    required: false
  next_accounts_due_to:
    type: string
    description: Latest next-accounts-due date, inclusive (YYYY-MM-DD).
    required: false
  page_number:
    type: integer
    description: Page number (1-based). Defaults to 1.
    required: false
  page_size:
    type: integer
    description: Results per page. Defaults to 15. Maximum is 100.
    required: false
---

# Companies House Search Tool

Searches the Lenkie Working Capital API's copy of the Companies House directory.

## When to use

- Build a prospect list filtered by SIC code (industry sector)
- Find active UK limited companies incorporated within a date range
- Look up a specific company by registration number or name
- Filter by postcode for geographic targeting

## Key limitations

- **No turnover data** — Companies House does not hold revenue figures. Turnover must be
  verified through a separate enrichment step before outreach.
- **Sector proxy only** — SIC codes indicate the declared industry, not confirmed revenue
  model or ICP fit. Use SIC codes as a first-pass filter; always note this limitation.
- **UK-registered companies only** — all results are UK entities.

## Typical ICP lead-finding workflow

1. Call with the ICP-relevant SIC codes for the target tier (e.g. dental: 86230)
2. Filter `statuses=Active` and set `incorporation_date_to` to 5+ years ago
3. Optionally filter by `company_types=Private Limited Company`
4. Return results as candidate leads, flagging that turnover is unverified
