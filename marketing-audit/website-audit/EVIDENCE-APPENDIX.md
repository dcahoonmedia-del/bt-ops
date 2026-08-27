# Evidence appendix — website / competitors / ownership

**Observation date unless noted:** 27 August 2026  
**Purpose:** Cite sources used in `WEBSITE-AND-COMPETITOR-MASTER.md`. No customer PII, form bodies, credentials, or tokens.

This is the **only** new evidence appendix for the website phase. Phase 1 HTML dumps remain in `../evidence/`.

---

## 1. B&T live pages fetched (read-only)

| URL | Method | Used for |
| --- | --- | --- |
| https://www.btpestcontrol.com/ | curl 27 Aug + Phase 1 mobile browser 23 Aug | Drupal 10, nginx, GTM-MH3JJKS, Sprowt theme, hero “Since 1982”, sticky Call/Estimate, form fields, offer expiry **08/31/2026**, `ctm-target-number-link`. Raw HTML phones **1337** (DNI 356 is after JS). |
| https://www.btpestcontrol.com/compare-our-packages | curl 27 Aug | Starting at **29 / 45 / 59** per month; $45 copy includes fire ants, fleas, ticks, stinging insects, mosquitoes; Plus adds termites / Advance bait; “Initial Fee Applies” |
| https://www.btpestcontrol.com/pest-control-jacksonville | curl 27 Aug | Title stuffed with Save $100 termite/bed bug; H1 “Pest Exterminators in Jacksonville, NC”; **Benefit Body** fieldset-legend ×2. `/jacksonville-nc-pest-control` is **404**. |
| https://www.btpestcontrol.com/services/wood-destroying-insect-report | curl 27 Aug | VA & FHA in title; long realtor Webform; no public fee. `/wdir` is **404**. |
| https://www.btpestcontrol.com/privacy-policy | curl (this phase / Phase 1) | Last modified **01/22/2026**; Coalmarch/CTM/GA disclosure |
| https://www.btpestcontrol.com/robots.txt | curl 27 Aug | Disallow `/admin/`, `/user/login` |
| https://www.btpestcontrol.com/sitemap.xml | curl 27 Aug | **92** `<loc>` URLs (not 27) |
| https://www.btpestcontrol.com/themes/sprowt3/ | HTTP 200 | Sprowt theme tree |
| https://www.btpestcontrol.com/themes/custom/btpestcontrol_s3/ | HTTP 200 | Custom theme tree |
| DNS `btpestcontrol.com` | `dig NS` / `A` / `MX` | NS ns47/ns48.domaincontrol.com; A **35.202.252.85**; MX Google Workspace |
| WHOIS / RDAP | failed in this environment | Registrar **unknown** |

**Not done:** form POST, click-to-call, click-to-text, Drupal login, DNS/hosting login, plugin admin.

---

## 2. Stack crumbs (homepage HTML, 27 Aug 2026)

- `Drupal 10 (https://www.drupal.org)`
- `nginx/1.24.0`
- `gtm.js?id=GTM-MH3JJKS` — **use this ID**. A prior mobile-browser OCR of `GTM-M833JKS` was a misread.
- `ctm-target-number-link` on `tel:` — CTM tracker JS **not** in first-party HTML on 27 Aug (likely GTM). Phase 1 homepage dump still shows the CTM script.
- `modules/custom/pestpac_webforms/js/utm-capture.js` — **legacy module name**; CRM is Fieldwork
- Webform `free-quote` / `form_id=webform_submission_free_quote_add_form`
- Files under `/public_files/btpestcontrol-s3-live/`
- Theme CSS: `btpestcontrol_s3`

---

## 3. Repository Gmail / Coalmarch evidence (no PII copied)

| Source | Date | Finding |
| --- | --- | --- |
| `daniel@` sent “Website fixes” | 17 Jun 2026 | Stale reviews/former techs on homepage; expired referral **2/25**; flea blog used bite photos + “bed bugs” copy; Surf City “36 years” vs homepage 44; coupon-first city pages; Holly Ridge “free estimate” vs **$75** inspections |
| Coalmarch (Rachael) | 23 Jun 2026 | Edits completed; asked for more if needed |
| `noreply@coalmarchleads.com` | sampled 23–24 Aug 2026 | Estimate vs WDIR vs Contact subjects; May 2026 WDIR outage then resume |
| Coalmarch email | 13 Jul 2026 | Link-building cancelled |
| Coalmarch email | 22 Apr 2026 | Contract renewed one year |
| CTM login mail | 24–25 Aug 2026 | Tracking **(910) 356-9966**; account **462929** |
| Phase 1 `evidence/bt-homepage.html` | 22–23 Aug 2026 | Drupal/Sprowt/GTM/CTM already present |

---

## 4. Competitor pages (limited live pass, 27 Aug 2026)

Full notes: `competitor-audit-27aug2026.md`. Canonical table: `WEBSITE-AND-COMPETITOR-MASTER.md` §3.

DNS that **did not resolve** on 27 Aug (do not use): `modernpestnc.com`, `eastlineexterminators.com`, `capefeartermiteandpest.com`.

| Company | URLs that resolved |
| --- | --- |
| Modern Exterminating | https://modernexterminating.com/ |
| Eastline Pest Management | https://eastlinepest.com/ and `/pest-control-jacksonville-nc` |
| Diamond Pest Pro | https://www.diamondpestpro.com/ |
| Cape Fear Termite & Pest | https://www.capefearpestcontrol.com/ |
| Mosquito Authority JAX | https://www.mosquitoauthority.com/jacksonville-nc/ |
| May Exterminating | https://www.mayexterminating.com/ |
| Pest & Termite Consultants | https://www.pestandtermiteconsultants.com/areas-we-serve/jacksonville |

National brands (Aptive, Orkin, Terminix) were **not** re-audited as conversion peers.

---

## 5. Screenshots

Committed mobile-emulation captures (27 Aug 2026; DevTools visible; no form values):

- `screenshots/bt-home-mobile-hero.webp` — hero “Since 1982”, sticky CALL US / REQUEST AN ESTIMATE, 288 reviews
- `screenshots/bt-home-mobile-coupon.webp` — offers still dated **08/31/2026**
- `screenshots/bt-packages-mobile-45.webp` — PestGuard 45/month inclusion copy

Also use Phase 1 `../evidence/` HTML captures.

---

## 6. What this appendix does **not** contain

- Form field values, caller names, CTM recordings, Fieldwork customers
- Passwords, API keys, GTM container JSON, Drupal user lists
- Another full competitor encyclopedia
- Paid-ad reconciliation (see `../ACCOUNT-DATA-EXECUTIVE-SUMMARY.md`)
