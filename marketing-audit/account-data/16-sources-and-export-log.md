# 16 — Sources and export log

**Audit window:** 23–25 August 2026  
**Identity:** daniel@btpestcontrol.com  
**Rule:** no customer PII, passwords, recordings, or live edits. Fieldwork was opened **read-only** on 25 Aug 2026 (user `Grok`). No Fieldwork records or settings were saved.

| Platform | Report | Property | Date range | Filters | Export file | Screenshot | Accessed | Limitations |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| GBP | Owner insights | B&T Pest Control, Inc, 1276 NC-172 | Mar–Aug 2026 | Default | None (UI) | Referenced `08_gbp_*` / pass-1 notes; **not all files in repo** | 2026-08-23 | No CSV; search-count labels inconsistent |
| GBP | Listing fields | Same | Point in time | — | — | Pass-1 inventory | 2026-08-23 | Services list not fully scraped |
| GSC | Performance | https://www.btpestcontrol.com/ | 22 May–21 Aug 2026; 22 Apr 2025–21 Aug 2026 | Web, all queries | Zip created in browser **not copied to repo** | Pass-1 notes | 2026-08-23 | Re-export needed |
| GSC | Index coverage | Same | Point in time | — | — | — | 2026-08-23 | 83 vs 52 only |
| GSC email | July performance | Same | Jul 2026 | — | — | — | 2026-08-04 email | Email rounded |
| GA4 | Home | B&T Pest Control - GA4 | ~28d to 23 Aug 2026 | Default | None | Pass-1 | 2026-08-23 | Spam geo; key events |
| Ads | Campaigns | CID 367-996-4323 | UI showed Jun 2023 | — | None | Stale UI | 2026-08-23 | **Incomplete** |
| LSA | Gmail notices | CID 589-278-3347 | ~365d | from:localservices-noreply | None (counts only) | — | 2026-08-23 | Not charged-lead CSV |
| Coalmarch PI | Overview, monthly, paid vs SEO | B&T | 24 Jul–22 Aug 2026; YTD to 22 Aug; months 2026 | Default | None in repo | `01`–`07` coalmarch webp **filenames logged; files may live only on agent VM** | 2026-08-23 | Lead definition opaque |
| Gmail | Agency recaps / budgets | daniel@ | 2025-07 – 2026-08 | coalmarch.com | None | — | 2026-08-23 | Recaps are secondary |
| Gmail | Form subjects | coalmarchleads.com | ~365d; 50-thread sample coded | subject only | — | — | 2026-08-23 | **No bodies stored** |
| CTM | Calls header + status/source filters | Coalmarch tenant / B&T acct 462929 | 24 Jul–22 Aug; 24 May–22 Aug; 1 Jan–22 Aug 2026 00:00–23:59 | Calls activity; TZ not shown | `exports/ctm-aggregates.csv` | none (no call-list shots) | 2026-08-25 | Reports URLs 404. 2FA **not** clicked. Unique/voicemail/after-hours not shown. Remainder sources uncounted |
| GTM / Looker / YT Studio | — | — | — | — | — | — | — | **Not completed** |
| Drive | search | daniel@ | — | pest/Coalmarch | Empty | — | 2026-08-23 | |
| Fieldwork web | Login wall (pre-auth) | app.fieldworkhq.com | Point in time | None | None | `fw-session-check-2026-08-25.webp`; `fw-chrome-history.webp` | 2026-08-24 / early 2026-08-25 | **Superseded.** Empty email/password at that time |
| Fieldwork | Executive Summary | B&T Pest Control | 24 Jul–22 Aug; 24 May–22 Aug; 1 Jan–22 Aug 2026 | All branches | `exports/fieldwork-reconciliation.csv` | `fw-exec-30d.webp`, `fw-exec-90d.webp`, `fw-executive-summary-ytd.webp` | 2026-08-25 | Production vs invoice clocks differ; ~$88 avg WO is route work |
| Fieldwork | Customer List · Date Added | same | **24 Jul–22 Aug custom = 52**; 26 Jul–25 Aug preset = 53; 24 May–22 Aug; 1 Jan–22 Aug | Date Added | counts in reconciliation CSV | Customer-list shots **deleted** | 2026-08-25 | Footer counts only |
| Fieldwork | Sales By Agreement Type | same | 1–31 Aug 2026 | Default | — | `fw-sales-by-agreement-type.webp` | 2026-08-25 | **0** agreements. Recurring is service types, not this module |
| Fieldwork | Estimates (module) | same | 1–31 Aug 2026 | Estimate Date | — | `fw-estimates.webp` | 2026-08-25 | **0** module rows. **Not** “no estimating.” Onsite estimates are inspection-estimate WOs |
| Fieldwork | Service Volume By Location Type | same | 1–31 Aug 2026 | Default | `exports/fieldwork-service-volume-aug2026.csv` | `fw-service-volume-by-location-type.webp` | 2026-08-25 | Location Type blank; grouped by service type; Aug calendar ≠ 30d marketing |
| Fieldwork | Completed Work Orders | same | 24 Jul–22 Aug 2026 | Status completed (report default); Services one-type filter; View Report not Save | `exports/fieldwork-completed-inspection-wos.csv` | none (no WO rows) | 2026-08-25 | Unfiltered 1,064. Type counts for inspection/setup/renewal as listed. 90d/YTD types not finished |
| Gmail | Fieldwork operational mail | from:fieldworkhq.com | ~365d; last 30d | Subjects only | None (counts only) | — | 2026-08-25 | Route #3 daily sheets; bodies **not** opened |
| Public | Customer portal | btpestcontrol.serviceworkportal.com | Point in time | — | — | Phase 1 | Phase 1 | Existing-customer portal |

## Gmail threads used as **management** evidence (not customer leads)

- Google Business Profile (Daniel → Coalmarch, 16 Aug 2026) + Toby reply  
- August paid budget $4,600 → Daniel **$2,000** (29–30 Jul 2026)  
- July / June / May / April / March / Jan budget mails  
- 1 May 2026 business review recap (pack #1 claim, 247 LSA / 6mo / $55, CVR, bed bugs, geo)  
- 16 Sep 2025 bi-annual recap (revenue −5% YTD, JAX suite, LSA hours, German roach content)  
- WDIR form broken 18 May 2026  
- Link-building cancel Jul 2026  
- LSA COI / payment declines / new admin  
- Contract seasonal vs annual 1 Jul 2026  
- YouTube employee takedown Jul 2025  
- Dashboard walkthrough 10 Aug 2026 (rankings PDF **not saved here**)

## Form-mail sample (subjects only)

First results page of `from:noreply@coalmarchleads.com`: **17 WDIR / 35 Free Estimate / 2 Contact** (54 subject hits). **Do not reopen to mine names.**

## Sanitized exports added 25 Aug 2026

- `exports/fieldwork-reconciliation.csv` — marketing vs Fieldwork by window  
- `exports/fieldwork-required-sources.csv` — recommended required source list (not observed as 2026 values)  
- `exports/fieldwork-service-volume-aug2026.csv` — Aug 2026 service-volume footer + top types  
- `exports/fieldwork-inspection-estimate-types.csv` — service-volume qty for inspection/setup types, three windows  
- `exports/fieldwork-completed-inspection-wos.csv` — completed WO type counts 24 Jul–22 Aug  
- `exports/ctm-aggregates.csv` — CTM header counts (no caller PII)  

## Reproducibility gaps

1. Copy GSC zip + PI screenshots into `account-data/exports/` and `screenshots/` on a machine where Downloads is this repo.  
2. Coalmarch: ranking PDF, Ads, LSA invoice.  
3. CTM Reports dashboard (unique / after-hours / voicemail / remaining source labels) without CDRs — header path is documented in `07`.  
4. Fieldwork Completed Work Orders by type for **24 May–22 Aug** and **1 Jan–22 Aug**.  
5. Fieldwork source-frequency on new accounts (PII stripped).
