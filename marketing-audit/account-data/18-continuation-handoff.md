# 18 — Continuation handoff (25 Aug 2026)

Stop condition: CTM session expired before period-matched aggregates. Fieldwork inspection-type **service-volume** counts for three windows are saved. Do not redo Google/Coalmarch/GBP/Ads/LSA/GA4/GSC.

---

## Work completed

1. **Estimates-module correction** committed: empty Sales → Estimates ≠ no estimating. Onsite estimates are inspection-estimate **work orders**.
2. **CTM:** Brief authenticated call-list view (PII seen, **not** saved). 2FA setup banner observed, **not** clicked. Then login wall. No totals.
3. **Fieldwork Service Volume By Location Type** for:
   - 24 Jul 2026 – 22 Aug 2026
   - 24 May 2026 – 22 Aug 2026
   - 1 Jan 2026 – 22 Aug 2026  
   Timezone **not displayed**. Qty is **not** completed-WO count.

---

## Exact filters used

| System | Report | Dates | Filter |
| --- | --- | --- | --- |
| Fieldwork | `/newer_reports/service_volume_by_location_type` | three windows above | Date picker; scan service type names |
| Fieldwork | Estimates module | 1–31 Aug 2026 | Empty (unused module) |
| CTM | — | intended same three windows | **Not reached** |

---

## Verified figures (Service Volume qty — not completed WOs)

**24 Jul–22 Aug 2026** (Coalmarch 30d dates): Inspection/Estimate **2** + Pest Inspection / Estimate **4** = **6**. Termite Inspection / Estimate **7**. WDIR-100 **2**. PestGuard Set-up **26**. PestguardPLUS Set up **3**. Quarterly New Set-Up **4**. Termite renewal+inspection **20**. PestGuard Plus annual inspection **18**. Footer: **1,134** qty / **$68,198** period total / **$454,876** annual.

**24 May–22 Aug 2026:** Inspection/Estimate **13** + Pest Inspection / Estimate **10** = **23**. Termite Inspection / Estimate **35**. WDIR-100 **20**. PestGuard Set-up **69**. Footer: **3,319** qty / **$208,008.55** / **$1,284,283.20** annual.

**1 Jan–22 Aug 2026:** Inspection/Estimate **39** + Pest Inspection / Estimate **29** = **68**. Termite Inspection / Estimate **82**. WDIR-100 **49**. PestGuard Set-up **120**. PestguardPLUS Set up **12**. Quarterly New Set-Up **12**. Termite renewal+inspection **221**. Footer: **8,293** qty / **$520,542.80** / **$3,410,319.20** annual.

Do **not** treat 6 pest inspection-estimate lines as “6 new customers.” Do **not** treat a completed inspection as a sale. Do **not** divide marketing spend by 311 and call it CAC.

Coalmarch **24 Jul–22 Aug:** **99** leads, **50** calls, **$5,390**. YTD: **741** leads, **$41,940**.

---

## Files updated this loop

- `07-call-tracking.md`, `17-fieldwork-crm.md`, `10`, `12`, `13`, `14`, `15`, `16`, `00`, `09`, exec summary, `ACCOUNT-DATA-AUDIT.md`
- `exports/fieldwork-inspection-estimate-types.csv`
- `_ctm-pass.md`, `_fieldwork-inspection-wos.md` (working notes)
- `screenshots/ctm-access-blocker.webp` (login only)

---

## Outstanding

1. **CTM Reports/Analytics** for the three date windows: total calls, unique, dispositions, after-hours, first vs repeat, source **labels** (no numbers). Do not Set up 2FA. No CDR export. No call-list screenshots.
2. Fieldwork **Completed Work Orders** (or equivalent) by service type for the same dates — to replace service-volume qty if it is active lines.
3. Canceled/incomplete inspection WOs.
4. New vs existing on inspection WOs **only** if an aggregate flag exists (no customer-level conversion %).
5. Customer Date Added **24 Jul–22 Aug** custom (not Last 30 days preset).
6. CTM↔Fieldwork match rules (phones stay in-session).

---

## Open browser locations (when last seen)

- CTM: `app.calltrackingmetrics.com/login?redir=.../calls`
- Fieldwork: still signed in as Grok; last report Service Volume By Location Type
- Do not sign out of Fieldwork

---

## Privacy cleanup

- No call-list screenshots committed.
- Customer-list shots with cards/accounts already deleted earlier.
- Working notes must not contain names/phones. `_ctm-pass.md` describes that PII was on screen but does not copy it.
- Re-scan exports before commit: service type names and counts only.

---

## Next prompt (paste to finish CTM)

You are already on the B&T marketing-audit branch. CTM session died at the login wall; Fieldwork Grok is signed in. **Do not click Set up 2FA.** After Daniel restores CTM, open Reports/Analytics only. Pull totals for 24 Jul–22 Aug 2026, 24 May–22 Aug 2026, and 1 Jan–22 Aug 2026 (record timezone). Capture answered/missed/abandoned/voicemail/after-hours, unique vs total, first vs repeat if shown, source **labels** not phone numbers. No call-row screenshots, no CDR export, no recordings. Then compare to Coalmarch 50 call leads / 99 leads (24 Jul–22 Aug) using the formulas in `07-call-tracking.md` and `18-continuation-handoff.md`. If a Completed Work Orders report exists in Fieldwork, replace Service Volume qty for inspection/estimate types with completed counts for those same dates. Update `07`, `10`, `17`, `16`, exec summary. Do not call CAC the $41,940/311 figure.
