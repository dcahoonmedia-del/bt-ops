# 16 — Sources and export log

**Audit window:** 23–24 August 2026  
**Identity:** daniel@btpestcontrol.com  
**Rule:** no customer PII, passwords, recordings, or live edits.

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
| CTM | — | Coalmarch | — | — | — | — | 2026-08-23 | **2FA not completed** |
| GTM / Looker / YT Studio | — | — | — | — | — | — | — | **Not completed** |
| Drive | search | daniel@ | — | pest/Coalmarch | Empty | — | 2026-08-23 | |

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

## Reproducibility gaps

1. Copy GSC zip + PI screenshots into `account-data/exports/` and `screenshots/` on a machine where Downloads is this repo.  
2. Coalmarch: ranking PDF, Ads, LSA invoice.  
3. CTM aggregate CSV with PII stripped.
