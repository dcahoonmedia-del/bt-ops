# 17 — Fieldwork / CRM findings

**Prepared:** 25 August 2026 (authenticated pass; earlier 24–25 Aug login-wall notes superseded)  
**Company:** B&T Pest Control · Holly Ridge, NC  
**Fieldwork user this session:** `Grok` at `https://app.fieldworkhq.com`  
**Mode:** Read-only. Temporary date filters only. No Save / Create / Edit / Delete. No test records. No sign-out. No customer names, phones, emails, street addresses, account numbers, or card data are stored here.

This paper is the CRM system-of-record for the account-data audit. It does **not** redo Google, Coalmarch, GBP, Ads, LSA, GA4, Search Console, or call-tracking research.

---

## Access

| Check | Result |
| --- | --- |
| Authenticated | **Yes** (25 Aug 2026, after Daniel signed the session in) |
| Company | B&T Pest Control |
| Nav | Customers · Calendar · Sales · Marketing · Reports |
| Reports catalog | **79** reports (Commissions 9, Customers 10, Financial 16, Operations 29, Pest Control 6, Sales 1, Summary 5, Tax 3). Saved/Favorites: 0 |

A prior pass hit a login wall (`fw-chrome-history.webp`, `fw-session-check-2026-08-25.webp`). Those shots only prove the earlier blocker. They are not current access evidence.

---

## Directly observed facts

### New customers (Date Added = account created)

| Period shown in UI | Filter | Count | Report |
| --- | --- | ---: | --- |
| 26 Jul 2026 – 25 Aug 2026 | Customer List · Date Added · **Last 30 days** preset | **53** | `/newer_reports/customer_list` |
| 24 May 2026 – 22 Aug 2026 | Date Added · custom | **156** | same |
| 1 Jan 2026 – 22 Aug 2026 | Date Added · custom | **311** | same |

The **Last 30 days** preset is **not** Coalmarch’s 24 Jul–22 Aug window (it is 26 Jul–25 Aug). YTD and 90-day custom ranges **do** end on 22 Aug 2026.

Sidebar (Customers module, not the dated report): **2,818** Active. Inactive counts **differed by view** (2,697 vs 2,897) — do not treat inactive as a stable KPI. Leads sidebar: **0**. Commercial: low single digits. Financial hold: **62**.

### Production / invoicing (Executive Summary)

Date definition: work-order **completion** for production/completion; **invoice date** for invoiced/paid (UI does not print a data dictionary; this is the usual Fieldwork pairing and matches the totals).

| Period | Invoiced | Paid | Unpaid | Completed WOs | Scheduled WOs | Completion | Production | Avg / WO | Cancellations | On-time |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 24 Jul–22 Aug 2026 | $87.49k | $84.12k | $3.37k | 1,064 | 1,116 | 95.34% | $93.73k | $88.10 | 6 (0.54%) | 81.77% |
| 24 May–22 Aug 2026 | $281.40k | $275.23k | $6.17k | 3,131 | 3,247 | 96.43% | $271.78k | $86.80 | 13 (0.4%) | 82.18% |
| 1 Jan–22 Aug 2026 | $699.71k | $692.46k | $7.32k | 7,901 | 8,121 | 97.29% | $700.07k | $88.60 | 28 (0.34%) | 82.67% |

Executive Summary also showed **0%** “Callbacks” and **0%** “Missed” in all three windows. That is Fieldwork’s **callback/missed KPI**, not the absence of service types named “Call Back” (those exist; see service mix).

Screenshots: `fw-exec-30d.webp`, `fw-exec-90d.webp`, `fw-executive-summary-ytd.webp`.

### Recurring vs one-time

**Sales → Sales By Agreement Type** for **1–31 Aug 2026:** **0** agreements, $0 (screenshot `fw-sales-by-agreement-type.webp`).

That does **not** mean B&T has no recurring work. Recurring is stored as **service types** (PestGuard Regular, PestGuardPLUS, quarterly, commercial routes). The Agreements module looks unused for August 2026.

### Service mix (Service Volume By Location Type)

**Report date filter:** 1 Aug 2026 – 31 Aug 2026 (calendar August, **not** 24 Jul–22 Aug).  
**Footer:** **1,167** rows, **annual value $463,201**, **period total value $68,455**.  
**Location Type** column was **blank** on visible rows. The report is grouped by **Service Type**.

First page (A–G alphabetically) included commercial monthly/weekly, bed-bug heat, German-roach initial, flea/fire-ant/bee treatments, extra service / follow-up at **$0**, and call-back types at **$0**. Screenshot: `fw-service-volume-by-location-type.webp`.

**Top types by quantity** (same report, recorded while scrolling; not all on the first-page screenshot):

| Service type | Qty | Annual value | Period total |
| --- | ---: | ---: | ---: |
| PestGuard - Regular Pest Service | 551 | $261,516 | $21,937 |
| PestGuardPLUS Regular Service | 104 | $67,302 | $5,638 |
| Pest Control - Quarterly | 87 | $25,441 | $6,360 |
| Commercial Pest Service - Monthly | 41 | $33,348 | $2,779 |
| Extra Service / Follow-up | 33 | $0 | $0 |

No service type named **WDIR** / Wood Destroying Insect Report was seen on the visible list. **Termite – Bait Monitoring** and inspection/estimate types **were** present. **Pest Inspection / Estimate** and **Inspection/Estimate** exist as types.

### Estimates module vs onsite inspection-estimate work orders

**Correction:** An empty Fieldwork **Estimates** module is **not** evidence that B&T does no estimating. The office records **onsite estimates as inspection-estimate work orders** (service types such as **Pest Inspection / Estimate** and **Inspection/Estimate**), not as Sales → Estimates rows.

**Estimates *module* (unused product feature):**

- **Reports → Estimates**, Estimate Date **1–31 Aug 2026:** **0** rows. Column **Lead Source** exists (empty because the table is empty). Screenshot: `fw-estimates.webp`.
- **Sales → Estimates** list: historical estimates (years **2018–2025** visible), many **Expired**, some **Accepted**, sidebar **Archived 112**.
- Customers sidebar **Leads: 0**.

Do **not** treat those zeros as “no quotes in August.” Period-matched inspection-estimate **work-order** counts are the right metric and were not pulled in the first authenticated pass. A completed inspection is **not** automatically a sale.

### Marketing / source fields

- The unused Estimates module has a **Lead Source** column. **No 2026 August *module* values to count.** That does **not** mean 2026 jobs have no estimating activity.
- Distinct picklist values were **not** observed (empty Estimates table; Customize not used, to avoid Save).
- Customer List default columns did **not** show Marketing Campaign / Source.
- **Marketing → Campaigns** showed **historical email/ad campaigns** (examples: 2018–2019 hurricane/phone emails; **Google Adwords – Mosquito** May 2017, $250 cost, 0 customers). Those are **old blast campaigns**, not 2026 intake sources. They must not be read as LSA/GBP/Ads attribution.

### Geography

No city/ZIP **count** report was opened without customer-level rows. New-customer lists (Date Added) showed **Onslow-centered cities** on the first page (Jacksonville, Holly Ridge, Sneads Ferry, Surf City, North Topsail Beach, Richlands, plus other NC towns). The city field also contains **out-of-area** values (including other states). Those are **data-quality flags**, not markets. First-page cities are **not** a census.

Customer-list screenshots were **deleted** from the repo because they included account numbers and masked card numbers.

### What was not changed

No Fieldwork records, reports, filters (persisted), campaigns, users, or settings were saved. Customize was not saved.

---

## Calculated findings

Formulas use only the facts above. Populations are **not** the same people.

| Metric | Formula | Result | Use? |
| --- | --- | --- | --- |
| YTD new accounts / Coalmarch leads | 311 / 741 | **42.0%** | **Yield proxy only.** Not a close rate. Leads are calls+forms+messages; accounts include every Date Added (any source). Dates both end 22 Aug 2026. |
| ~30d new accounts / Coalmarch 30d leads | 53 / 99 | **53.5%** | **Do not use.** Numerator is 26 Jul–25 Aug; denominator is 24 Jul–22 Aug. |
| 90d share of YTD new accounts | 156 / 311 | **50.2%** | Half of 2026 new accounts were added 24 May–22 Aug. |
| Marketing $ per new Fieldwork account (YTD) | $41,940 / 311 | **$134.86** | **Not CAC.** Spend is all Coalmarch marketing; 311 are all new accounts, not “from ads.” |
| Marketing $ per new account (~30d, misaligned) | $5,390 / 53 | **$101.70** | **Do not use as CAC.** Date mismatch + same mix problem. |
| PestGuard Regular share of Aug service-volume qty | 551 / 1,167 | **47.2%** | Share of **this report’s rows**, Aug calendar month, not completed-WO mix. |
| PestGuard Regular + PLUS share of qty | (551+104) / 1,167 | **56.1%** | Same limitation. |
| PestGuard Regular + PLUS share of annual $ | ($261,516+$67,302) / $463,201 | **71.0%** | Annualized value on the Aug service-volume report, not YTD invoiced $699.71k. |
| Avg ticket vs new-account value | $88.60 YTD production / WO | Recurring-visit economics | **Not** the price of a new PestGuard setup. |

**Booking/conversion rate with a comparable numerator and denominator:** **none.** Fieldwork does not show which of the 741 Coalmarch leads became which of the 311 accounts. The empty **Estimates module** is the wrong denominator; inspection-estimate **work-order** counts were not yet period-matched. A completed inspection is not automatically a sale.

**LTV:** **not computed.** Need average agreement price × tenure. Agreements report was empty for August; PestGuard annual values exist on the service-volume report but are not tenure.

**Revenue from new customers vs existing:** **unavailable.** YTD $700.07k production is almost entirely **existing-route work** at ~$88/visit. It cannot be credited to 2026 marketing.

---

## Reasonable inferences

1. Fieldwork is the **live ops/billing system** (2,818 active customers; thousands of 2026 work orders; daily Route #3 mail).
2. **The Estimates *module* is unused for 2026; estimating still happens as inspection-estimate work orders.** Empty August Estimates rows do **not** mean no quotes. Lead Source on that module still cannot attribute 2026 marketing. Source would need to live on the customer or on the inspection-estimate WO.
3. **Recurring general pest is the production engine.** ~$88 average WO and PestGuard Regular as the largest service-volume type match a bi-monthly/quarterly route shop, not a one-time-treatment shop.
4. **Coalmarch “lead” is much larger than Fieldwork “new account.”** YTD 741 vs 311. The gap is some mix of existing customers, spam, no-shows, WDIR/one-time that may not create a lasting account, duplicates, and timing — **not measured**.
5. **A blank or generic “Google” source, if it appears later, still would not prove LSA vs GBP vs organic vs Google Ads.** No 2026 source values were seen to test this.

---

## Unknowns / unavailable

| Question | Why unavailable | Exact report/field to resolve |
| --- | --- | --- |
| New accounts in **24 Jul–22 Aug** (exact Coalmarch 30d) | UI used Last-30-days preset (26 Jul–25 Aug) = **53** | Customer List · Date Added · custom **24 Jul–22 Aug 2026** |
| Which new accounts came from LSA / GBP / site / Ads / realtor / referral / existing | Lead Source empty for Aug estimates; customer source column not in default view | Customer List with **Marketing Campaign or Lead Source** column; value frequency including **blank**; **do not Save** a Customize unless the owner wants a saved view |
| Inspection-estimate WO volume (period-matched) | Not counted in first pass (module emptiness was misread) | Work orders / Service Volume filtered to **Pest Inspection / Estimate**, **Inspection/Estimate**, plus any WDIR/termite-letter types; 24 Jul–22 Aug, 24 May–22 Aug, 1 Jan–22 Aug |
| New vs existing mix **on jobs** | Exec Summary is all WOs | Jobs/WOs with customer Date Added vs WO date (export, PII stripped) |
| Recurring vs one-time **$** | Agreements module 0 in Aug; service-volume is not completed-WO revenue | Completed production by service type for 24 Jul–22 Aug and YTD |
| WDIR volume in Fieldwork | No type named WDIR on the visible service list | Service-volume / WO search for WDIR, WDI, wood-destroying, termite letter |
| City/ZIP **counts** | No aggregate geo report without customer rows | Customer Value by Location or grouped city/ZIP export, counts only |
| True CAC / LTV | New accounts are unattributed; no tenure | Source-tagged new accounts × spend; agreement price × years |
| Whether Fieldwork “Google” exists as a value | Picklist not opened | Lead Source / Marketing Campaign dropdown (read-only) |

---

## Reconciliation with marketing leads

Coalmarch **lead** = tracked call + form + message. Fieldwork **new customer** = Date Added. Fieldwork **production** = completed work orders (mostly recurring).

| Period | Marketing spend | Marketing leads | Fieldwork new customers (Date Added) | Fieldwork completed WOs | Fieldwork production | Fieldwork invoiced | Comparable booking rate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| ~30d | $5,390 · **24 Jul–22 Aug** | **99** · same | **53** · **26 Jul–25 Aug** (preset; **not the same days**) | **1,064** · 24 Jul–22 Aug | **$93.73k** · 24 Jul–22 Aug | **$87.49k** | **None.** Dates and populations differ. |
| 90d | No native Coalmarch 90d total | **Unavailable** (do not use May–Aug monthly sum 479) | **156** · 24 May–22 Aug | **3,131** · 24 May–22 Aug | **$271.78k** | **$281.40k** | **None.** No 90d lead denominator. |
| YTD | $41,940 · 1 Jan–22 Aug | **741** · same | **311** · 1 Jan–22 Aug | **7,901** · 1 Jan–22 Aug | **$700.07k** | **$699.71k** | **None** that is a close rate. **311/741 = 42%** is only “new accounts per platform lead.” |

GBP **764 listing calls** (Mar–Aug) and GSC **1,174 clicks** (22 May–21 Aug) are still **not** Fieldwork denominators.

**What prevents a person-level match:** no shared ID between Coalmarch/CTM/LSA and Fieldwork in the repo; unused Estimates-*module* source field (onsite estimates are WOs, not that module); Date Added ≠ lead timestamp; production is recurring routes, not “this month’s leads.”

---

## Required source list (still recommended)

Lock as **required** on new customers (and on estimates if the office starts using them):

`LSA` · `GBP` · `website/organic` · `Google Ads` · `realtor/WDIR` · `referral` · `existing customer` · `other` (note required)

Never store blank or `Google`. Fieldwork **can** store a source (Lead Source on the unused Estimates module; Marketing Campaign exists in the product). Put the required list on **new customers and inspection-estimate work orders**, not on a module the office does not use. It **cannot** distinguish those channels until values are used on 2026 records.

---

## Marketing-budget implications (from Fieldwork + existing PI)

1. **Do not raise paid** to chase Coalmarch lead volume. YTD **741 leads → 311 new accounts**, and most dollars ($700k production) are **route work**, not new-account sales. Capacity (August tech-out, $2k cap) still binds.
2. **Optimize for PestGuard accounts**, not raw CPL. Service-volume is PestGuard-heavy; ~$88 tickets are maintenance visits.
3. **LSA billing** still must not fail (card declines). LSA vs other Google sources is **still untagged** in Fieldwork.
4. **Do not reactivate** the 173 paused Search campaigns as a “test.”
5. **WDIR** is a marketing form channel (~30% of sampled site-form subjects) but **not** a named Fieldwork service type in the Aug service-volume first pass — office must show where those jobs live before spending more on realtor ads.
6. **Instrument source this week** (I8 in the action plan). Until then, $134.86 per new account is a ceiling on “marketing dollars per account,” not a channel CAC.
7. **Keep CTM 2FA** on the list: Fieldwork will not show missed/after-hours unique callers.

---

## Screenshots kept (no customer rows)

| File | What it shows |
| --- | --- |
| `fw-reports-menu.webp` | 79-report catalog |
| `fw-executive-summary-ytd.webp` | Exec Summary 1 Jan–22 Aug 2026 |
| `fw-exec-30d.webp` | Exec Summary 24 Jul–22 Aug 2026 |
| `fw-exec-90d.webp` | Exec Summary 24 May–22 Aug 2026 |
| `fw-sales-by-agreement-type.webp` | 0 agreements, Aug 2026 |
| `fw-estimates.webp` | Empty **Estimates module** for Aug 2026 (not proof of no onsite estimates) |
| `fw-service-volume-by-location-type.webp` | Aug 2026 service types; footer 1,167 / $463,201 / $68,455 |
| `fw-chrome-history.webp` | Pre-login: history only Sign In |
| `fw-session-check-2026-08-25.webp` | Pre-login wall (superseded) |

Customer-list captures that showed account/card columns were **removed** and not committed.

---

## File note

Working notes `_fieldwork-pass2-metrics.md` and `_fieldwork-pass3-metrics.md` are raw collection logs. **This file is canonical** if they disagree (prefer Executive Summary screenshots over notes; prefer 311/156/53 as counted in the Customer List footer).
