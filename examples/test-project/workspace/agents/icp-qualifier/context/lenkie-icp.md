# Lenkie ICP — Ideal Customer Profile
> March 2026 · Final

---

## What Lenkie does

Lenkie pays named B2B suppliers directly on behalf of SMEs (subcontractor payroll, HMRC, materials, locum staff, lab fees, professional services). The customer repays Lenkie. It is NOT invoice finance, MCA, or a business loan. The customer must have identifiable B2B payables.

---

## Core ICP — Primary Target (all conditions required)

| Criterion | Rule |
|---|---|
| Geography | UK-registered limited company |
| Turnover | £1m–£30m annual (sweet spot) |
| Trading | 5–20 years (incorporated 5+ years ago) |
| Ownership | Owner-operator led |
| Revenue | B2B only |
| Payment cycles | Episodic / project-based / seasonal / contract |
| Sector | Tier 1 (see below) |

---

## Turnover Bands

| Band | Treatment |
|---|---|
| Below £1m | **Decline** |
| £1m–£2m | Accept with +15–25% premium, £150k facility cap, manual review |
| £2m–£30m | Standard terms |
| Above £30m | Out of scope |

> **Companies House note:** Turnover is NOT available in CH data. Always flag as "unverified — requires enrichment before outreach."

---

## Sector Tier Map

### Tier 1 — Growth Priorities (lead all outbound)

| SIC Code(s) | Sector |
|---|---|
| 86230 | Private dental groups / DSOs |
| 86210, 86220 | Private GP & specialist medical practices |
| 87100, 87200, 87300 | Residential care (elderly, disability, mental health) |
| 69101, 69102, 69103, 69109 | Legal services (solicitors, barristers, patent agents) |
| 35110–35300 | Renewables (solar, heat pump, EV charging) |
| 43210, 43220 | MCS-certified heat pump / EV charging installers |
| 49410, 49420 | Road freight, haulage & B2B logistics |

### Tier 2 — Managed Growth (serve, no dedicated outbound)

#### Construction — Hard Cap: ≤15% of monthly origination (SIC 41/42/43 combined)

| SIC Code(s) | Sub-sector | Extra rules |
|---|---|---|
| 42110–42990 | Civil engineering & infrastructure | Best treatment within construction |
| 43110–43999 | Specialist trades (electrical, plumbing, roofing) | £2m+ t/o required (hard minimum, not just premium); named end-client contract required |
| 41100–41202 | Building project development | £2m+ t/o; conservative facility sizing |

Construction auto-decline: SIC 43xxx sub-£2m = **hard decline**.

Cap alert thresholds: 12% = underwriting alert; 14% = CFO sign-off required; 15% = pause.

#### Other Tier 2

| SIC Code(s) | Sector |
|---|---|
| 69201–69203 | Accounting, bookkeeping & tax |
| 71111–71129 | Architecture & engineering consulting |
| 46720–46770 | Wholesale — metals & commodities |
| 46110–46690 | Wholesale — industrial & building materials |
| 81100–81299 | Facilities management & building maintenance |
| 78200 | B2B staffing (construction/healthcare/logistics) — named corporate clients required |
| 86900 | Allied health (physiotherapy, occupational health) |
| 25110–25999 | Fabricated metal products manufacturing |
| 52101–52290 | Warehousing & distribution |
| 80100–80300 | Security services (B2B) |
| 53201–53202 | Courier & last-mile delivery (B2B) |

### Tier 3 — Reactive Only

| SIC Code(s) | Sector |
|---|---|
| 70221–70229 | Management consultancy |
| 73110–73200 | Advertising & market research |
| 59111–59200 | Film, TV & content production |
| 28110–28990 | Industrial machinery manufacturing |

### Negative — Auto-Decline

| SIC Code(s) | Sector |
|---|---|
| 47710–47789 | Fashion & lifestyle retail |
| 56101–56302 | Restaurants, bars, pubs, hospitality |
| 55100–55900 | Hotels & accommodation |
| 68100–68320 | Real estate (buy/sell/manage) |
| 01110–03220 | Agriculture, forestry, fishing |
| 90010–93290 | Arts, entertainment, recreation |
| 47910 | eCommerce / online retail |
| 62011–62090 | Software / IT (early-stage) |

---

## What Companies House can and cannot tell us

| Criterion | Available? | How |
|---|---|---|
| UK-registered | ✓ | All CH records |
| Sector (proxy) | ✓ | SIC codes — declared sector only |
| Trading duration | ✓ | `incorporation_date` |
| Active status | ✓ | `company_status = Active` |
| Company type | ✓ | e.g. Private Limited Company |
| Geography (regional) | ✓ | Postcode |
| Turnover | ✗ | Not in CH |
| Owner-operator | ✗ | Not derivable |
| B2B revenue model | ✗ | Not derivable |

**Always state in output:** "Turnover unverified — requires enrichment before outreach. Results are sector-qualified candidates only."
