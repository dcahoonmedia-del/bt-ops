# 09 — Tracking and attribution map

Ideal:  
`Search/ad/social → website/GBP → call/form/message → marketing lead → qualified → booked → recurring → revenue`

## What B&T can answer today

| Question | Can they? | How |
| --- | --- | --- |
| Which channel created the lead? | **Partially in PI; no in Fieldwork 2026** | Coalmarch paid vs organic. Estimates-*module* Lead Source unused; onsite estimates are inspection WOs |
| Which search? | **Rarely** | GSC for organic queries (not leads); Ads terms **missing**; LSA has no keyword |
| Which campaign? | **No** (this pass) | Ads UI not exported |
| Which service? | **Forms + Fieldwork types** | Site: estimate vs WDIR vs contact. Fieldwork: PestGuard/termite/etc. on WOs — **not joined** to the lead |
| Which city? | **Weak** | GBP queries; GSC pages; no city-count report without customer rows |
| Qualified? | **No** | No score in PI |
| Answered? | **No** | CTM locked |
| Appointment scheduled? | **Partially** | Calendar/WOs exist; not joined to marketing leads |
| Job completed? | **Yes as totals** | Exec Summary completed WOs by date; not by channel |
| Recurring? | **Yes as service types** | PestGuard Regular 551 qty on Aug service-volume; Agreements report 0 in Aug 2026 |
| Revenue / margin / CAC / LTV | **Partial** | $700.07k YTD production; **$134.86** marketing $ / new account is **not CAC**; LTV unknown |

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
| CRM feedback to Ads/LSA | Fieldwork open; **no** source tags on 2026 estimates; no offline conversion import seen |
| One-time vs recurring | Not in ads |
| Repeat/existing as new | Unknown |
| Spam as leads | Unknown |
| Ads optimizing to junk | Search likely off; LSA optimizes to Google’s lead definition |
| Conflicting conversion defs | GA4 52 vs Coalmarch 99 vs GBP calls 100+/mo |

**Do not fix in-product.** Export CTM, lock form analytics, tag Fieldwork source on new accounts, join monthly Date Added counts to PI.
