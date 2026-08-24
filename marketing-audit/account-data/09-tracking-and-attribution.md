# 09 — Tracking and attribution map

Ideal:  
`Search/ad/social → website/GBP → call/form/message → marketing lead → qualified → booked → recurring → revenue`

## What B&T can answer today

| Question | Can they? | How |
| --- | --- | --- |
| Which channel created the lead? | **Partially** | Coalmarch last-touch-ish paid vs organic; LSA vs SEO not split cleanly |
| Which search? | **Rarely** | GSC for organic queries (not leads); Ads terms **missing**; LSA has no keyword |
| Which campaign? | **No** (this pass) | Ads UI not exported |
| Which service? | **Only forms** | Estimate vs WDIR vs contact. Calls untagged |
| Which city? | **Weak** | GBP queries; GSC pages; no lead geo report |
| Qualified? | **No** | No score in PI |
| Answered? | **No** | CTM locked |
| Appointment scheduled? | **No** | Not in Google/Coalmarch |
| Job completed? | **No** | |
| Recurring? | **No** | Mentioned in meetings (20 new recurring Jul 2025) — not a dashboard |
| Revenue / margin / CAC / LTV | **No** | |

## Breaks

| Issue | Evidence |
| --- | --- |
| Phone-click as conversion | GA4 key events unexplained; not mapped |
| Form success | WDIR **broke May 2026**; coalmarchleads.com still mails; thank-you not verified |
| Duplicate conversions | Possible: GBP call + CTM + LSA + GA4 |
| Calls regardless of quality | Coalmarch call = lead |
| Forms counted before success | Unknown |
| Portal contamination | ServiceWork portal exists |
| Tracking numbers vs NAP | 356 vs 1337 — **explained**, still confuses humans |
| Missing UTMs | GBP UTM homepage is actually present (good) |
| Cross-domain | Unaudited |
| CRM feedback to Ads/LSA | None seen |
| One-time vs recurring | Not in ads |
| Repeat/existing as new | Unknown |
| Spam as leads | Unknown |
| Ads optimizing to junk | Search likely off; LSA optimizes to Google’s lead definition |
| Conflicting conversion defs | GA4 52 vs Coalmarch 99 vs GBP calls 100+/mo |

**Do not fix in-product.** Export CTM, lock form analytics, join monthly booked jobs in a sheet.
