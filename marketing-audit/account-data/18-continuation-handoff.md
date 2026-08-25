# 18 — Continuation handoff (25 Aug 2026, updated)

This loop **finished** the CTM header-aggregate pass, the Estimates-module correction, period-matched Fieldwork Date Added **52**, and 24 Jul–22 Aug **completed** inspection/setup WO type counts. Do not redo Google/Coalmarch/GBP/Ads/LSA/GA4/GSC.

---

## Work completed

1. **Estimates module:** empty Sales → Estimates ≠ no estimating. Onsite estimates are inspection-estimate **work orders**.
2. **CTM (authenticated; 2FA setup not clicked):** Calls header, not Reports (those URLs 404).
   - 24 Jul–22 Aug 00:00–22 Aug 23:59: **149** calls; first-time **75**; Answered **123**; Missed filter **0**; unique/voicemail/after-hours **not shown**.
   - 24 May–22 Aug: **349** calls.
   - 1 Jan–22 Aug: **809** calls.
   - Source filters counted: Website **65**, Google Ads **1**, Google Call Asset **1**. Remainder **82** **not** assigned (other labels seen: Local Services Ads, Holly Ridge GLS, Emergency Tech).
   - Timezone **not displayed**.
3. **Fieldwork Customer List Date Added custom 24 Jul–22 Aug = 52** (preset Last 30 days remains **53** on 26 Jul–25 Aug).
4. **Completed Work Orders** 24 Jul–22 Aug unfiltered **1,064**. Type footers: Inspection/Estimate **2**, Pest Inspection / Estimate **4**, Termite Inspection / Estimate **7**, WDIR-100 **2**, PestGuard Set-up **26**, Termite renewal **12** (SV qty was **20**).
5. Person-level CTM↔Fieldwork match **not attempted**.

---

## Exact filters used

| System | Report | Dates | Filter |
| --- | --- | --- | --- |
| CTM | `/calls` header | 2026-07-24 00:00–2026-08-22 23:59 (and 90d/YTD) | Calls activity; status/source name filters |
| Fieldwork | Customer List | 24 Jul–22 Aug 2026 | Date Added custom |
| Fieldwork | Completed Work Orders | 24 Jul–22 Aug 2026 | One service type at a time; View Report not Save |
| Fieldwork | Service Volume By Location Type | three windows | already saved prior loop |

---

## Metric rules still in force

- **52/99 = 52.5%** is new accounts per platform lead, **not** a close rate.
- **$5,390/52 = $103.65** and **$41,940/311 = $134.86** are **not CAC**.
- **149/50 = 2.98×** CTM calls vs Coalmarch call leads — different objects.
- **75** first-time ≠ **52** Date Added.
- Completed inspection ≠ sale.

---

## Files updated this loop

`07`, `09`, `10`, `12`–`17`, `00`, `18`, exec summary, `ACCOUNT-DATA-AUDIT.md`, `exports/ctm-aggregates.csv`, `exports/fieldwork-completed-inspection-wos.csv`, reconciliation/scorecard CSVs.

---

## Outstanding (optional follow-up; not required to interpret the 30d picture)

1. CTM Reports UI if Coalmarch enables it without clicking Set up 2FA: unique, after-hours, voicemail, remaining source **counts**.
2. Fieldwork completed WO types for **24 May–22 Aug** and **1 Jan–22 Aug**.
3. PestguardPLUS Set up / Quarterly New Set-Up / PestGuard Plus Annual Inspection completed counts (30d UI not finished).
4. Source-frequency on Fieldwork new accounts (PII stripped).
5. Still **do not** export CDRs or save call-list screenshots.

---

## Privacy

- No call-list screenshots, CDRs, recordings, names, phones, or customer identifiers committed.
- Login-only CTM shot from the earlier blocker may still exist as `ctm-access-blocker.webp` (login card).
- Do not commit Gmail CTM authorization codes.

## Next prompt (only if finishing optional gaps)

Fieldwork Grok is signed in; CTM is authenticated. Do not click Set up 2FA. Pull Completed Work Orders type footers for 24 May–22 Aug and 1 Jan–22 Aug (same type list as `exports/fieldwork-completed-inspection-wos.csv`). If a CTM source filter can count Local Services Ads / Holly Ridge GLS / Emergency Tech on 24 Jul–22 Aug without showing numbers, record those header counts. Update `07` and `17`. No CDRs, no call-row screenshots.
