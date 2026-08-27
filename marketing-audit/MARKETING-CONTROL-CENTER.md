# B&T Pest Control — Marketing control center

**Owner (company):** Toby Cahoon  
**Working the accounts:** Daniel Cahoon (`daniel@btpestcontrol.com`)  
**This file updated:** 27 August 2026  
**Rule:** This is the index. Do not treat older papers as current if this file marks them superseded.

---

## Current overall conclusion

B&T is a **route business** (Fieldwork: **$700k** YTD production, **7,901** completed WOs, PestGuard Regular as the volume type) with a **real website offer** ($29 / $45 / $59 PestGuard; **$45 includes mosquitoes and fire ants**) that is **under-shown on the mobile homepage**.

Paid is **LSA-first**. Coalmarch YTD (1 Jan–22 Aug 2026): **$41,940 / 741 leads / $56.60 CPL**. Fieldwork Date Added in the same window: **311**. That **42%** is new accounts per platform lead, **not** a close rate. **$41,940 / 311 is not CAC.**

The website **helps** callers and price-comparison shoppers who reach PestGuard pages. It **hurts** mobile first-timers (hero is tenure, not $45; long form; coupon-first city pages; leftover template text). **Do not migrate off Coalmarch yet.** Fix copy and CRO **through** Coalmarch. Learn ownership, export, and DNS before any vendor change.

**Website/competitor master (this phase):** `website-audit/WEBSITE-AND-COMPETITOR-MASTER.md`

---

## Decisions already made

| Decision | Evidence | Status |
| --- | --- | --- |
| Do not raise paid above ops capacity | Aug 2026 tech-out; Daniel cut paid to **$2,000** | In force |
| Do not flip the **173 paused** Search campaigns | Ads CID 367-996-4323; no search-term history | In force |
| Link-building add-on cancelled | Mail Jul 2026 | Done |
| Coalmarch contract is **annual** (renewed Apr 2026); paid ads can be seasonal | Tarsha Holland 1 Jul 2026 | In force |
| Empty Fieldwork Estimates *module* ≠ no estimating | Inspection-estimate **work orders** | Corrected 25 Aug 2026 |
| Do not treat blank/`Google` as LSA vs GBP vs organic vs Ads | No 2026 Fieldwork source tags | In force |
| Do not terminate/migrate the website in this phase | This control center | In force |

---

## Active experiments / live offers

| Item | Window | Note |
| --- | --- | --- |
| $75 off PestGuard **Basic** setup | Site still shows expiry **08/31/2026** as of 27 Aug 2026 | **Ops risk in 4 days** — ask Coalmarch to extend or swap copy |
| $100 off PestGuard Plus | Same expiry | Same |
| $250 off crawl package | Same expiry | Same |
| August paid cap $2,000 | Jul 30 2026 mail | Dashboard previously still showed a higher budget |
| GBP hygiene | Daniel/Toby 16–24 Aug 2026 | Coalmarch SEO replied 24 Aug; **edits not made by this audit** |

No homepage $45-hero test is live. That is the recommended next CRO test (Coalmarch implements).

---

## Authoritative reports (read these)

| Topic | Canonical file | Date |
| --- | --- | --- |
| **This index** | `MARKETING-CONTROL-CENTER.md` | 27 Aug 2026 |
| Website, ownership, competitors, 30/60/90, Coalmarch questions | `website-audit/WEBSITE-AND-COMPETITOR-MASTER.md` | 27 Aug 2026 |
| Website evidence (sources, stack crumbs, screenshot inventory) | `website-audit/EVIDENCE-APPENDIX.md` | 27 Aug 2026 |
| Account-data executive summary | `ACCOUNT-DATA-EXECUTIVE-SUMMARY.md` | 23–25 Aug 2026 |
| Account-data full | `ACCOUNT-DATA-AUDIT.md` | 23–25 Aug 2026 |
| Public-web decision doc (Phase 1) | `FINAL-MARKETING-AUDIT.md` | 23 Aug 2026 |
| Fieldwork CRM | `account-data/17-fieldwork-crm.md` | 25 Aug 2026 |
| Call tracking | `account-data/07-call-tracking.md` | 25 Aug 2026 |
| Action plan (paid/GBP/ops) | `account-data/13-revised-action-plan.md` | 25 Aug 2026 |

---

## Open questions

1. Who holds the **GoDaddy** (domaincontrol.com NS) login — B&T or Coalmarch?  
2. What is the **Sprowt / hosting** line item vs the **SEO retainer** (~$2,040 / 30d in Coalmarch PI)?  
3. Can B&T get a Drupal admin, or only ticketed edits?  
4. Export: full Drupal DB + files, or HTML only?  
5. What dies if Coalmarch access is removed (GTM-MH3JJKS, CTM DNI, coalmarchleads.com, GCP origin)?  
6. Exact **inspection fee** on the street vs “free estimate” leftover copy (Daniel 17 Jun 2026: **$75** for inspections).  
7. Fieldwork source tags still unused — channel CAC still impossible.

---

## Next actions (website phase)

Prioritized in the master report. First five:

1. Tell Coalmarch: hero **$45 + included mosquitoes/fire ants**; stop coupon-first city H1s.  
2. Extend or replace offers expiring **31 Aug 2026**.  
3. Remove leftover **“Benefit Body”** fieldset legends; unstuff the Jacksonville title.  
4. Short mobile form + click-to-text (do not submit tests).  
5. WDIR page: price and turnaround **only if ops agrees**; keep the long realtor form.

Do **not** rebuild the site. Do **not** turn Search Ads back on to “fix” the website.

---

## Monthly lead-conversion scorecard (Grokbot schema)

Fill one row per calendar month. Exact dates, not “last 30 days.” Timezone: America/New_York unless a system prints another.

| Field | Numerator | Denominator | Source | Inclusion / exclusion | Do not call it |
| --- | --- | --- | --- | --- | --- |
| Marketing spend | $ | — | Coalmarch PI | Paid + retainer as PI reports | — |
| Platform leads | count | — | Coalmarch PI | Calls + forms + messages | Jobs |
| Call leads | count | leads | Coalmarch PI | Call type only | CTM calls |
| Form leads | count | leads | Coalmarch PI | Webforms | Submitted-but-spam unknown |
| Message leads | count | leads | Coalmarch PI | GBP/LSA-style | Answered messages |
| CTM calls | count | — | CTM Calls header | Same civil dates; TZ if shown | Coalmarch call leads |
| CTM first-time | count | CTM calls | CTM filter | First-seen number | New Fieldwork account |
| CTM answered | count | CTM calls | Status=Answered | Voicemail may be absent | Live-answer proof |
| New Fieldwork accounts | count | — | Date Added **custom** | Same start/end as PI | Close rate |
| Accounts per platform lead | new accounts | PI leads | Calculated | Populations differ | Close rate / booking rate |
| Marketing $ per new account | spend | new accounts | Calculated | Unattributed mix | **CAC** |
| PestGuard Set-up completed WOs | count | — | Fieldwork Completed Work Orders | Service type exact name | New customers from ads |
| Pest onsite-estimate completed WOs | Inspection/Estimate + Pest Inspection / Estimate | — | Fieldwork | Not a sale | Close rate |
| WDIR-100 completed WOs | count | — | Fieldwork | Not realtor-attributed unless tagged | — |
| Production $ | $ | — | Exec Summary | Mostly existing routes | New-customer revenue |
| Site sessions | count | — | Coalmarch or GA4 — pick one and label | Do not average the two | Leads |

Template CSV: `website-audit/monthly-scorecard-schema.csv`.

---

## Research archive (do not delete)

### Phase 1 — public web (23 Aug 2026)

Still useful for facts; **recommendations** prefer the 27 Aug master report and `account-data/13`.

| File | Role |
| --- | --- |
| `01-bt-current-state.md` | Site IA, prices, NAP |
| `02-service-area-map.md` | Cities vs sitemap |
| `03-competitor-inventory.csv` | Broad inventory (30+) |
| `04-competitor-profiles.md` | Who matters; **benchmark set chosen from here** |
| `05-search-visibility.md` | Directional SERP/Maps |
| `06`–`07` GBP/reviews (public) | Superseded for owner metrics by `account-data/01` |
| `08-website-cro-seo.md` | CRO/SEO; **updated by 27 Aug live pass** |
| `09`–`16` pricing, content gap, social, citations, journeys, scorecard, recs, sources | Historical |
| `evidence/` | HTML captures, sitemap, research notes |
| `FINAL-MARKETING-AUDIT.md` | Phase 1 decision doc |
| `AUDIT-SUMMARY.md` | Short Phase 1 wrap |

### Phase 2 — authenticated accounts (23–25 Aug 2026)

| File | Role |
| --- | --- |
| `ACCOUNT-DATA-EXECUTIVE-SUMMARY.md` | Management layer |
| `account-data/00`–`18` | Working papers. **17** = Fieldwork. **07** = CTM. **18** = CTM/Fieldwork handoff |
| `account-data/_browser-pass*.md`, `_ctm-pass.md`, `_fieldwork-*.md` | Collection logs, not canonical |
| `account-data/AUDIT_SUMMARY_REPORT.md` | Early snapshot; platforms-not-accessed list is **stale** |
| `account-data/README.md` | Folder index; **control center** is the master index |
| `AUDIT_COMPLETION_SUMMARY.md` | Leftover; not canonical |

### Phase 3 — website/competitors (27 Aug 2026)

| File | Role |
| --- | --- |
| `website-audit/WEBSITE-AND-COMPETITOR-MASTER.md` | **Canonical** |
| `website-audit/EVIDENCE-APPENDIX.md` | Sources and stack |
| `website-audit/competitor-audit-27aug2026.md` | Working capture of 7 sites |
| `website-audit/monthly-scorecard-schema.csv` | Monthly Grokbot columns |
| `website-audit/bt-competitor-audit-27aug2026.md` | **Removed** (incomplete first pass). Replacement: master report + `competitor-audit-27aug2026.md` |

---

## Duplicate / conflicting figures (how to resolve)

| Conflict | Use |
| --- | --- |
| Coalmarch 50 call leads vs CTM 149 calls (24 Jul–22 Aug) | Both; they are **different objects** (`07`) |
| Date Added 53 vs 52 | **52** = 24 Jul–22 Aug custom; **53** = Last 30 days preset 26 Jul–25 Aug |
| Site phone 356 vs GBP 1337 | **1337** office/GBP; **356** CTM DNI on the site |
| Review count 285 / 286 / 288 | Widget drift; GBP owner **286** on 23 Aug; site **288** on 27 Aug |
| Service-volume qty vs completed WOs | Completed WOs for jobs; SV overcounts some renewals |
| GA4 ~52 key events vs 99 PI leads | Ignore GA4 as lead count |
| “No estimating” vs empty Estimates module | **Wrong.** Use inspection-estimate WOs |

---

## Stopping point

This phase ends when the master report, appendix, control center, and executive-summary pointer are committed. Further work is **implementation with Coalmarch** (punch list) and **monthly scorecard filling** — not more competitor lists or another CRM reconciliation.
