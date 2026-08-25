# 10 — Cross-system lead reconciliation

Windows differ. **Do not average them into one fake number.**

## Last ~30 days (marketing)

**Coalmarch:** 24 Jul–22 Aug 2026 · 99 leads · $5,390 · $54.49 CPL  
**GSC 3 months** is not 30 days (1,174 clicks).  
**GA4 ~28d:** 896 sessions, ~52 key events.  
**GBP:** August calls ~105 on a 6-month chart (partial month).  
**LSA mail:** several notices per week in Aug (not summed here).  
**CTM:** n/a → **149** CTM calls vs **50** Coalmarch call leads (24 Jul–22 Aug). First-time **75**. Unique callers unavailable. See `07-call-tracking.md`.

### Channel skeleton (30d)

| Metric | Google (mixed) | GA4 | Coalmarch | CTM | Best estimate | Confidence |
| --- | --- | --- | --- | --- | --- | --- |
| Visibility | GSC 3mo 164k impr; GBP 901 “searched in area” last month | 761 users / 28d | 690 sessions Aug MTD | — | Use GSC+GBP for search; PI for sessions | Medium |
| Calls | GBP Aug ~105 (partial) | — | 50 call leads | **149** | **50 Coalmarch call leads ≠ 149 CTM calls ≠ ~105 GBP** | Medium |
| Forms/messages | — | — | 24 forms + 25 messages | — | 49 digital non-call leads | Medium |
| Platform conversions | Ads unknown; LSA emails ≠ charges | 52 key events | 99 leads | — | **99 Coalmarch leads** | Medium as KPI / Low as jobs |
| Unique leads | — | — | ≤99 | First-time **75** (≠ unique) | **Unknown unique humans** | Low |
| Qualified | — | — | — | — | **Unavailable** | — |
| Booked | — | — | — | Fieldwork Date Added | **52 new accounts** 24 Jul–22 Aug (custom). Preset Last 30 days = **53** on 26 Jul–25 Aug | Medium as count / Low as “from these 99 leads” |

## YTD 2026 (1 Jan–22 Aug)

| Metric | Google | GA4 | Coalmarch | CTM | Best estimate | Confidence |
| --- | --- | --- | --- | --- | --- | --- |
| Spend | LSA declines; no Ads export | — | **$41,940** | — | **$41,940 marketing (PI)** | High |
| Leads | LSA ~201 emails/365d (not YTD-cut) | — | **741** | — | **741 platform leads** | High as PI / Low as customers |
| New Fieldwork accounts | — | — | — | Fieldwork Date Added | **311** (1 Jan–22 Aug) | High as CRM count |
| CPL | — | — | **$56.60** | — | Platform CPL | High |
| GSC clicks | 4,670 / ~16mo | — | — | — | Not leads | High |
| GBP calls | 764 / Mar–Aug | — | — | — | Listing calls | High |

## Why they disagree

- Clicks ≠ calls ≠ charged LSA ≠ CTM unique ≠ jobs.  
- Organic PI leads include **retainer allocation**.  
- July **paid webforms 0** vs July **39 webforms** total: organic/direct forms still counted.  
- GA4 key events collapsed (−28.6%) — ignore for volume.  
- LSA email count **overcounts** unique jobs.  
- GBP includes **repeat and customer** calls to 1337.

**Most trustworthy for money in:** Coalmarch spend.  
**Most trustworthy for “did marketing make the phone/form move”:** Coalmarch leads + GBP actions, **qualified by office**.  
**Most trustworthy for SEO queries:** GSC.  
**Least:** GA4 conversions; Ads UI this session.  
**Jobs / new customers / revenue:** Fieldwork Date Added and Executive Summary (see `17-fieldwork-crm.md`). Production (~$88/WO) is mostly **recurring routes**, not new-account sales.

---

## Fieldwork vs marketing leads (25 Aug 2026)

Windows and **date definitions** differ. Coalmarch = lead created (call/form/message). Fieldwork new customers = **Date Added**. Fieldwork production = **completed work orders** (mostly existing PestGuard routes).

| Period | Marketing leads (Coalmarch) | Fieldwork new customers | Fieldwork completed WOs / production | Comparable booking rate |
| --- | ---: | ---: | ---: | --- |
| Last 30d marketing · 24 Jul–22 Aug 2026 | **99** ($5,390) | **52** Date Added (custom; same civil dates). Preset was **53** on 26 Jul–25 Aug | **1,064** WOs / **$93.73k** prod / **$87.49k** invoiced | **Not a close rate.** **52/99 = 52.5%** is only new accounts per platform lead. CTM **149** calls / Coalmarch **50** call leads = **2.98×**. |
| 90d · 24 May–22 Aug 2026 | **No native PI export** (do not use May–Aug monthly sum 479) | **156** Date Added | **3,131** WOs / **$271.78k** prod / **$281.40k** invoiced | **None** (no 90d lead total). |
| YTD · 1 Jan–22 Aug 2026 | **741** ($41,940) | **311** Date Added | **7,901** WOs / **$700.07k** prod / **$699.71k** invoiced | **Not a close rate.** **311/741 = 42%** is only new accounts per platform lead. |

GBP **764 listing calls** (Mar–Aug) and GSC **1,174 clicks** (22 May–21 Aug) are **not** Fieldwork denominators.

**What still prevents a person-level match:** no shared ID in the repo; Estimates *module* unused (onsite estimates are inspection WOs); CTM 149 ≠ Coalmarch 50 ≠ Fieldwork 52 in the same dates; production is recurring ~$88 tickets. Phone matching was **not** done. Do **not** treat blank or generic “Google” as LSA/GBP/organic/Ads if that value appears later.

Pest onsite-estimate **completed WOs = 6** (24 Jul–22 Aug; matches service-volume qty). WDIR-100 completed **2**. PestGuard Set-up completed **26**. None of these is a close rate vs 99 leads. See `17-fieldwork-crm.md`.

---

## By channel (judgment)

| Channel | Visibility | Calls | Forms/msg | Unique leads | Qualified | Booked |
| --- | --- | --- | --- | --- | --- | --- |
| GBP | High (3,966 views / 6mo) | 764 / 6mo | Messages mixed into PI | Unknown | Unknown | Unknown (no source tags in FW) |
| Organic | GSC 1,174 clicks / 3mo, mostly brand+possum | In the 44 organic leads / 30d | Yes (estimate+WDIR) | Unknown | Unknown | Unknown (no source tags in FW) |
| Search Ads | Not evidenced live | Unknown | Unknown | Unknown | — | — |
| LSA | Active | Majority of paid calls | Messages possible | Unknown | Unknown | Unknown (no source tags in FW) |
| Direct | 188 GA4 sessions / 28d | DNI/brand | Yes | Unknown | — | — |
| Referral | Unmeasured | — | — | — | — | — |
| Social | Meta assist 2025 | Not in PI | — | Low | — | — |
