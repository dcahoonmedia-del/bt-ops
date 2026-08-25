# 07 — Call tracking (CallTrackingMetrics)

**Vendor:** CallTrackingMetrics (CTM), Coalmarch tenant  
**App:** https://app.calltrackingmetrics.com  
**Timezone:** **Not confirmed** (login wall before account settings). B&T operates in North Carolina; treat Coalmarch/Fieldwork calendar dates as local business dates until CTM TZ is read.

**Access this pass (25 Aug 2026):** **No aggregates.** A CTM tab was briefly open (Coalmarch / B&T Pest Control). A banner said multi-factor authentication is required (“Set up 2FA now”). That control was **not** clicked. Navigating toward Reports/Analytics hit a **login wall**. Credentials were **not** entered. No call-detail screenshot, export, recording, name, or phone was saved.

Screenshot: `screenshots/ctm-access-blocker.webp` (login card only).

---

## How numbers are used (from site + mail, not CTM admin)

| Number | Role |
| --- | --- |
| **(910) 329-1337** | Canonical / GBP / schema |
| **(910) 356-9966** | Website DNI (`ctm-target-number-link`) |
| **(910) 218-9465** | Proposed LSA **message** number (Sep 2025 recap — confirm if still true) |

Pools: GBP vs web vs paid vs LSA vs organic — **not listed**. DNI is on the site. Routing, hours, qualified-call length — **unknown**.

**Do not listen to recordings. Do not export caller PII. Do not complete Set up 2FA.**

---

## Requested CTM metrics vs available

Target windows (match Coalmarch/Fieldwork): **24 Jul–22 Aug 2026**, **24 May–22 Aug 2026**, **1 Jan–22 Aug 2026**.

| Question | Result | Source | Limitation |
| --- | --- | --- | --- |
| Total calls | **Unavailable** | CTM Reports not opened | Session expired |
| Unique callers | **Unavailable** | | |
| Answered / missed / abandoned / voicemail / after-hours | **Unavailable** | | |
| Repeat-call inflation | **Unavailable** | | |
| Source/channel attribution | **Unavailable** | | Do not treat tracking numbers as source names in the repo |
| New vs existing callers | **Unavailable** | | Not supportable without a CTM report |
| Comparability with Coalmarch **50** call leads (24 Jul–22 Aug) | **Cannot test** | Coalmarch PI | CTM total/unique unknown |

**Surrogate only (not CTM):** Coalmarch call leads **50** (24 Jul–22 Aug 2026, −22% vs prior 30d). GBP **764 listing calls** Mar–Aug 2026 is a different clock and includes existing/repeat.

---

## Matching CTM to Fieldwork

**Not attempted.** CTM was not in a reports session. Even after login, do not claim attribution until these are checked inside the UIs (identifiers stay in the session; **no crosswalk in the repo**):

- Phone normalization (10-digit vs +1 vs formatting)
- Multiple callers per Fieldwork account
- Repeat calls from existing PestGuard routes
- Whether Coalmarch “call lead” = CTM total calls, unique callers, or duration-qualified calls
- Timezone and inclusive calendar dates

---

## Missed-call analysis

**Cannot quantify.** Hours 8–5 vs aggregator 9–6 plus possible LSA evenings remains a **hypothesis**. August tech-out: even answered calls may not become jobs. Fieldwork Exec Summary “Missed 0%” is a **work-order** KPI, not CTM missed rings.

---

## Next (when a live CTM session exists)

Open **Reports / Analytics** only. Date pickers **24 Jul–22 Aug**, **24 May–22 Aug**, **1 Jan–22 Aug**. Capture KPI tiles (no call-list screenshots). Do not click Set up 2FA. Do not export CDRs.

Handoff: `18-continuation-handoff.md`.
