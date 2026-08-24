# 00 — Access and measurement inventory

**Accessed:** 23 August 2026  
**Google identity:** `daniel@btpestcontrol.com` (Daniel Cahoon)  
**Owner of the company (confirmed by Daniel):** Toby Cahoon · `toby@btpestcontrol.com`  
**Website connected:** `https://www.btpestcontrol.com/`  
**Read-only:** yes. No settings saved.

---

## Platform inventory

| Platform | Account / property | Website / location | History visible | Completeness | Active? | Multiple? | Correct B&T? | Overlaps |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Google account | daniel@btpestcontrol.com | — | Mail from 2021+ Coalmarch | High for mail | Yes | Facebook Accounts Center also has `btpest` + personal | Yes | — |
| GBP | B&T Pest Control, Inc · 1276 NC-172, Holly Ridge, NC 28445 · (910) 329-1337 | btpestcontrol.com | Insights ~6 months in UI | Medium (no CSV) | Yes | Not observed in this pass | Yes | Coalmarch GBP module |
| GSC | URL prefix `https://www.btpestcontrol.com/` | Same | ~16 months in UI | High if exports kept | Yes | Unknown if domain property also exists | Yes | GA4, Coalmarch SEO |
| GA4 | “B&T Pest Control - GA4” under Coalmarch Productions | btpestcontrol.com stream | 28-day snapshot this pass | Medium | Yes | Possible extra properties not listed | Yes | Ads link unknown |
| Google Ads Search | CID **367-996-4323** | — | Call-recording policy mail Apr 2026 | **Low in UI this session** | Unclear | Yes (separate LSA CID) | Yes | Coalmarch “paid” |
| LSA | CID **589-278-3347** · B&T Pest Control (Local Services) | — | Gmail lead notices through 21 Aug 2026; payment declines 2026 | High via mail; UI weak | **Yes** | — | Yes | Coalmarch paid, CTM |
| GTM | Not inventoried | — | — | Unknown | Unknown | — | — | GA4/Ads tags |
| Looker Studio | Not inventoried | — | — | Unknown | Unknown | — | — | — |
| YouTube | Public `@BTPest` / site gallery | — | Studio not pulled | Low | Dormant/stripped (former employee, Jul 2025 mail) | — | Yes | Social |
| Coalmarch PI | performanceinsights.coalmarch.com · daniel@ | B&T client | YTD 2026 + monthly | High for their KPIs | Yes | Welcome mail also said performanceinsights.coalmarch.com | Yes | All Google + CTM |
| Coalmarch leads mail | noreply@coalmarchleads.com | Forms on site | ~56 threads / 365d estimate | High for form *type* | Yes | — | Yes | GA4 forms |
| CTM | app.calltrackingmetrics.com (Coalmarch tenant) | DNI 910-356-9966 vs office 910-329-1337 | 2FA wall | **None this pass** | Yes (codes firing) | — | Yes | Coalmarch calls, GBP, Ads |
| Meta Ads | Not in Google profile | — | Oct 2025 recap only | Low | Was active 2025 | — | Yes | Branded search |
| Birdeye / directories | Public only | — | — | Phase 1 | — | — | NAP conflicts | GBP |

---

## Tracking limitations (inventory level)

1. Coalmarch **lead** = call + form + message as they define it. No booked-job join.  
2. Organic CPL uses **retainer dollars / attributed organic leads** — accounting CPL, not media CPL.  
3. Paid webform **zero in July inbound module** vs **39 webforms in the monthly company total** — different filters.  
4. LSA “new call” email ≠ charged lead ≠ unique prospect.  
5. GSC clicks ≠ leads. Possum blog inflates clicks.  
6. GBP calls ≠ CTM unique new callers.  
7. GA4 US-vs-Singapore split on a 28-day view is a **bot/quality flag**, not a market.  
8. Credentials: a Coalmarch welcome mail contained a default password. **Not stored in-repo. Rotate it.**

---

## Historical ranges used in later papers

| Label | Dates | Notes |
| --- | --- | --- |
| Last 30d (Coalmarch) | 24 Jul 2026 – 22 Aug 2026 | Inclusive dashboard range |
| YTD (Coalmarch) | 1 Jan 2026 – 22 Aug 2026 | Partial August |
| GBP performance | Mar 2026 – Aug 2026 | UI 6-month block |
| GSC 3 months | 22 May 2026 – 21 Aug 2026 | |
| GSC long | 22 Apr 2025 – 21 Aug 2026 | ~16 months |
| GA4 snapshot | ~26 Jul – 23 Aug 2026 | 28 days |
| Last 12 complete months | 1 Aug 2025 – 31 Jul 2026 | **Not fully exported** from Ads/GA4 |
| July GSC email | July 2026 calendar month | 385 clicks / 52.6K impr |

Exact filters: see `16-sources-and-export-log.md`.
