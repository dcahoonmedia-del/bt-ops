# 07 — Call tracking

**Vendor:** CallTrackingMetrics (CTM), Coalmarch tenant  
**App:** https://app.calltrackingmetrics.com  
**Access this pass:** **No.** Email OTP (e.g. 23 Aug 2026). Per instructions, **2FA was not completed.**

Gmail also shows `noreply@calltrackingmetrics.com` “Authorization Code” and “you’re subscribed to call notifications for Coalmarch.”

---

## How numbers are used (from site + mail, not CTM admin)

| Number | Role |
| --- | --- |
| **(910) 329-1337** | Canonical / GBP / schema |
| **(910) 356-9966** | Website DNI (`ctm-target-number-link`) |
| **(910) 218-9465** | Proposed LSA **message** number (Sep 2025 recap — confirm if still true) |

Pools: GBP vs web vs paid vs LSA vs organic — **not listed**. DNI is on the site. Routing, hours, qualified-call length — **unknown**.

**Do not listen to recordings. Do not export caller PII.**

---

## Metrics requested vs available

All of: total/unique/first/repeat, answered/missed/abandoned, duration, source/campaign/landing/keyword, LSA vs GBP vs organic vs ads vs direct vs social, day/hour, geo, service, first/last touch, spam, existing vs new — **Unavailable** without CTM.

Coalmarch **call leads** are the only surrogate:

| Period | Call leads |
| --- | ---: |
| Last 30d | 50 (−22%) |
| Jul 2026 month | 76 |
| YTD months sum (Jan–Jul + partial Aug) | see 06 |

GBP **764 calls / 6 months** is **not** CTM unique new.

---

## Missed-call analysis

**Cannot quantify.** Hours 8–5 vs aggregator 9–6 plus LSA evenings (Sep 2025: discussed extending ads hours to 5:30) means **paid could generate unanswered rings**. That is a hypothesis until CTM hour-of-day × missed is exported.

August tech-out: even **answered** calls may not become jobs.

---

## Attribution vs other tools

| Source | Calls-ish |
| --- | --- |
| CTM | Locked |
| GBP | 764 / Mar–Aug 2026 |
| Coalmarch | 50 / last 30d |
| Ads | Unknown |
| LSA emails | ~201 threads / 365d |
| GA4 | Not used |

Discrepancies expected: existing customers, direct 1337, multi-call, GBP vs DNI, LSA’s own number.

**Next:** Daniel or Coalmarch export **aggregated** CTM (source, hour, duration buckets, first-time, missed) with phones stripped.
