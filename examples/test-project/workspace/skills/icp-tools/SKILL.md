---
name: icp-tools
description: Tools for finding and qualifying ICP (Ideal Customer Profile) leads from external data sources
tools:
  - companies-house-search
---

# ICP Tools

Tools for discovering prospect companies from known data sources and filtering them
against Lenkie's Ideal Customer Profile criteria.

## Available tools

- **companies-house-search** — searches the Companies House directory of UK registered
  companies, filtered by SIC code, incorporation date, status, postcode, and more.
  Use this as the primary first-pass filter for sector-based lead discovery.

## Data source coverage

| Source | Sector filter | Turnover | Trading duration | Geography |
|---|---|---|---|---|
| Companies House | ✓ (SIC codes) | ✗ | ✓ (incorporation date) | ✓ (UK only) |

Turnover is not available from Companies House. Results from this skill should be
treated as **candidate leads** — sector-qualified but not turnover-verified.
