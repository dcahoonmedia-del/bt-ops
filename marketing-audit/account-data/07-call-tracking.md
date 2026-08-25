# 07 — Call tracking (CallTrackingMetrics)

**Vendor:** CallTrackingMetrics (CTM), Coalmarch tenant  
**App:** https://app.calltrackingmetrics.com  
**Account:** B & T Pest Control (CTM account id **462929** — internal id, not a customer identifier)  
**Timezone:** **Not displayed** on the calls UI. User profile showed default country **US +1** only. B&T operates in North Carolina; Coalmarch/Fieldwork calendar dates were treated as the same civil dates. URL filters used `start_date=YYYY-MM-DD 00:00` and `end_date=YYYY-MM-DD 23:59` with **no TZ offset**. Midnight-boundary mismatch vs Coalmarch/Fieldwork is possible.

**Access this pass (25 Aug 2026):** Authenticated. A banner said multi-factor authentication is required (“Set up 2FA now”). That control was **not** clicked. Direct `/reports`, `/analytics`, and `/dashboard` URLs returned **page not found**. Aggregates below come from the **calls list header + filter-panel counts**, not a Reports dashboard. **No** call-list screenshot, CDR export, recording, name, or phone was saved.

---

## How numbers are used (from site + mail, not CTM admin)

| Number | Role |
| --- | --- |
| **(910) 329-1337** | Canonical / GBP / schema |
| **(910) 356-9966** | Website DNI (`ctm-target-number-link`) |
| **(910) 218-9465** | Proposed LSA **message** number (Sep 2025 recap — confirm if still true) |

Routing, hours, and qualified-call length in CTM admin were **not** opened (2FA banner; settings not changed).

**Did not:** listen to recordings; export caller PII; complete Set up 2FA; change classifications, tags, notes, assignments, tracking numbers, routing, users, or integrations.

---

## Period-matched CTM header counts

Target windows match Coalmarch/Fieldwork civil dates.

| Window | Start | End | Total calls (header “filtered calls”) | Source |
| --- | --- | --- | ---: | --- |
| Coalmarch 30d | 2026-07-24 00:00 | 2026-08-22 23:59 | **149** | CTM calls filter URL |
| ~90d | 2026-05-24 00:00 | 2026-08-22 23:59 | **349** | same |
| YTD | 2026-01-01 00:00 | 2026-08-22 23:59 | **809** | same |

**Inclusion:** whatever the CTM calls index includes when those dates are set (all activity types in that list, not a duration-qualified subset — duration threshold **not shown**).  
**Exclusion:** texts/forms/chats were not counted (Activity Logs has separate sections; only **Calls** was used).  
**Limitation:** this is a list-header count, not a Reports KPI tile. Cached “all time” totals (five-digit) were seen when a date URL failed to apply and were **discarded**.

---

## 24 Jul–22 Aug 2026 — dispositions and first-time

**Denominator for shares below:** **149** CTM calls, 24 Jul 2026 00:00–22 Aug 2026 23:59, Calls activity, header filter.

| Metric | Numerator | Denominator | Result | How obtained | Limitation |
| --- | ---: | ---: | --- | --- | --- |
| Total calls | 149 | — | **149** | Header | Not unique humans |
| First-time contact | 75 | 149 | **50.3%** | Filter “First-time contact” | CTM first-seen number, **not** a Fieldwork new customer |
| Not first-time (repeat inflation remainder) | 149 − 75 = **74** | 149 | **49.7%** | Arithmetic | Not a named “repeat” filter |
| Repeat inflation (calls per first-time contact) | 149 | 75 | **1.99×** | Arithmetic | Inflates volume vs first-time; still not unique callers |
| Unique callers | — | — | **Unavailable** | No Unique filter | Do not use 75 as unique callers |
| Answered | 123 | 149 | **82.6%** | Status = Answered | Other statuses exist; voicemail is **not** a status |
| Missed (CTM “Show missed calls”) | 0 | 149 | **0** | Missed filter returned 0 rows | Does **not** prove voicemail/after-hours were answered by a person |
| Abandoned | — | — | **Not shown** | No Abandoned status | |
| Voicemail | — | — | **Not shown** | No Voicemail status | |
| After-hours | — | — | **Not shown** | No after-hours filter | |
| Answered gap | 149 − 123 = **26** | 149 | **17.4%** | Arithmetic | Status mix among Busy / Hangup / Canceled / Failed / Completed / other **not counted** |

Status dropdown options observed (not all counted): Answered, Busy, Canceled, Completed, Failed, Hangup, In progress, Received, Sending, Delivered, Unsent, Undelivered, Unreachable, Flagged, Blocked, Queued, Receiving, Sent, Hold.

---

## Source / channel labels (24 Jul–22 Aug 2026)

Filter-panel **counts confirmed** by applying one **name** at a time (no tracking numbers recorded):

| Source label (exact UI name) | Count | Share of 149 |
| --- | ---: | ---: |
| Website | **65** | 43.6% |
| Google Ads | **1** | 0.7% |
| Google Call Asset | **1** | 0.7% |
| **Confirmed subtotal** | **67** | 45.0% |
| **Uncounted remainder** | **82** | 55.0% |

**Do not** assign the remainder to one label. Other **names** were visible on the list (not counted, because a single-source filter count was not completed): **Local Services Ads**, **Holly Ridge GLS**, **Emergency Tech**, and possibly more.

**Google Ads / Google Call Asset = 1 each** is **not** evidence that Search CID 367-996-4323 is spending. Search campaigns were paused in the Ads UI. These labels can be call-asset / residual / misnamed LSA inventory.

**Probable new vs existing (only what is supportable):**

- **First-time contact 75 / 149** shows about half of CTM calls are **not** a first-seen number. That is **repeat-call inflation**, not a new-customer count.
- Labels such as **Emergency Tech** and **Holly Ridge GLS** (seen, not counted) are **consistent with** existing-customer / office routing mixed into the same 149, but **counts were not taken**, so do not quote a new-customer percentage from CTM.
- **Website 65** is a CTM source label, not “organic Google” and not Coalmarch’s 50 call leads.

---

## Comparability with Coalmarch lead totals

Coalmarch **24 Jul–22 Aug 2026:** **99** leads = **50** calls + **24** forms + **25** messages. Spend **$5,390**.

| Comparison | Numerator | Denominator | Result | Use? |
| --- | ---: | ---: | --- | --- |
| CTM calls / Coalmarch call leads | 149 | 50 | **2.98×** | **Not interchangeable.** Coalmarch “call lead” is a **subset** (or a different clock) vs CTM Calls index |
| CTM first-time / Coalmarch call leads | 75 | 50 | **1.50×** | Still not a match |
| CTM Website-source / Coalmarch call leads | 65 | 50 | **1.30×** | Labels differ; do not equate |
| CTM calls / Coalmarch all leads | 149 | 99 | **1.51×** | Mixes calls with forms/messages in the denominator |
| CTM YTD calls / Coalmarch YTD leads | 809 | 741 | **1.09×** | Different objects (calls vs call+form+message). **Not** a quality ratio |

**Why they disagree (checked before any person match):**

1. Coalmarch counts **leads** (calls + forms + messages). CTM header is **calls only**.  
2. Coalmarch **50** call leads ≠ CTM **149** calls in the same civil dates — likely duration qualification, marketing-number pools vs all CTM numbers, spam/existing filters, or double-counting rules. **Admin definition not opened.**  
3. Timezone not printed in CTM; URL is naive local midnight.  
4. Repeat callers: **74 / 149** are not first-time contacts.  
5. Existing-customer traffic is **plausible** (non-Website labels) and **unquantified**.

**Do not** treat CTM 149 as Coalmarch 50, and **do not** treat 75 first-time contacts as 52 new Fieldwork accounts.

---

## Matching CTM to Fieldwork

**Not attempted at record level.** Identifiers were not copied out of the UIs.

Pre-match checks:

| Check | Result |
| --- | --- |
| Phone normalization (10-digit vs +1 vs formatting) | **Unknown** (customer phones not inspected for export) |
| Multiple callers per Fieldwork account | **Unknown** |
| Existing customers generate repeat calls | **Supported in aggregate:** 74/149 not first-time; office-style source names present |
| Coalmarch “call lead” vs CTM total vs unique vs duration | **They do not match 50 vs 149 vs 75** |
| Periods | Civil dates aligned **24 Jul–22 Aug / 24 May–22 Aug / 1 Jan–22 Aug 2026** |
| Time zones | **Not confirmed equal** |

**Stop:** no person-level attribution. No crosswalk file.

---

## Missed-call analysis

CTM “Show missed calls” = **0** for 24 Jul–22 Aug. That is **not** a proof that every ring was handled by staff. Voicemail and after-hours are **not** CTM statuses here. Fieldwork Executive Summary “Missed 0%” is a **work-order** KPI, not rings.

**26 / 149** calls were not Status=Answered. Those 26 were **not** broken out.

---

## Files

Working log: `_ctm-pass.md`. Sanitized counts: `exports/ctm-aggregates.csv`.
