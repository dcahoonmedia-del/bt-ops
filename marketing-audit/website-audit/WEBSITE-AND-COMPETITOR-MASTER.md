# Website, ownership, and competitor master report

**Company:** B&T Pest Control · Holly Ridge, NC  
**Site:** https://www.btpestcontrol.com/  
**Prepared:** 27 August 2026  
**Mode:** Read-only. No site, DNS, tag, form, or GBP changes. No test leads, calls, or texts.

**Facts vs recommendations** are labeled. **Verified / Inferred / Unknown / Must ask Coalmarch** are labeled in the ownership section.

This is the **only** website/competitor master for this phase. Phase 1 papers (`08-website-cro-seo.md`, `04-competitor-profiles.md`, `15-recommendations.md`) remain in the archive; where they disagree with a 27 Aug live observation, **this file wins**.

---

## Executive conclusion

**Is the website helping or hurting conversion?**  
**Both, depending on the shopper.** It **helps** people who already want a local monthly plan: published **$29 / $45 / $59**, $45 includes mosquitoes and fire ants, sticky Call + Estimate on mobile, 4.9★ widget, real WDIR realtor form. It **hurts** a panicked mobile first-timer: the homepage hero is “since 1982,” not the $45 inclusion offer; the estimate form is **nine fields**; Jacksonville’s **title** is still stuffed with a $100 termite/bed-bug coupon; Drupal leftover **“Benefit Body”** legends remain in city-page HTML; click-to-text is missing. Phone conversion can still work because sticky **CALL US** is present. Digital conversion is slower than the offer deserves.

**What should be fixed first?**  
(1) Homepage and city-page **hero = $45 PestGuard + what’s included/excluded**. (2) Offers still dated **08/31/2026**. (3) Template leftovers and “free estimate” vs **$75 inspection** (Daniel, 17 Jun 2026). (4) Short mobile form + click-to-text. (5) WDIR: add fee/SLA only if ops agrees; do not shorten the realtor form blindly.

**What is Coalmarch likely providing?**  
A **Sprowt** (Drupal 10) site they host and edit, **SEO retainer** (Coalmarch PI organic line **$2,040 / 44 leads** in 24 Jul–22 Aug), form mail via **coalmarchleads.com**, **CTM** DNI, **GTM-MH3JJKS**, GA4 under **Coalmarch Productions**, GBP/SEO support, LSA/paid (separate budget), and Performance Insights. B&T does **not** appear to self-serve the CMS: Daniel emails Coalmarch for copy fixes; they completed a punch list in **six days** (17–23 Jun 2026).

**What must B&T learn or obtain before taking control?**  
GoDaddy/DNS login, Drupal (or rebuild) skills, file/DB export, replacement for coalmarchleads + CTM + GTM, 301 map of ~92 URLs, privacy/form legal, and a content owner. **Do not migrate in this 90-day plan.**

**Which improvements can B&T make without changing vendors?**  
Almost all high-impact CRO is a **Coalmarch ticket**, not a DIY CMS edit. Internally B&T can: decide inspection pricing copy, send the punch list, keep NAP/hours consistent in directories they control, tag Fieldwork sources, and stop asking for more city pages.

---

## 1. Ownership and dependency inventory

Observation date **27 Aug 2026** unless noted.

| Item | Finding | Confidence |
| --- | --- | --- |
| Domain | `btpestcontrol.com` live; www and apex both resolve to **35.202.252.85** | **Verified** (DNS A) |
| Registrar | **Unknown** (WHOIS/RDAP blocked in this environment) | **Unknown** |
| DNS | NS **ns47.domaincontrol.com** / **ns48.domaincontrol.com** (GoDaddy DNS) | **Verified** |
| Who controls DNS login | B&T vs Coalmarch | **Must ask Coalmarch** (and Daniel) |
| Hosting origin | **nginx/1.24.0** + Drupal; IP is **Google Cloud** range | **Verified** headers; **Inferred** Coalmarch GCP |
| Static files | `/public_files/btpestcontrol-s3-live/` | **Verified** HTML; **Inferred** S3 bucket named for the client |
| CMS | **Drupal 10** (`x-generator`, meta Generator) | **Verified** |
| Theme / product | Theme `btpestcontrol_s3`; `/themes/sprowt3/`; Sprowt classes and address widget | **Verified** HTML. **Inferred:** Coalmarch **Sprowt** platform (proprietary) |
| Admin access for B&T | `robots.txt` Disallow `/admin/`, `/user/login`. Daniel emailed Coalmarch 17 Jun 2026 for copy/review/offer fixes; Coalmarch said complete 23 Jun 2026 | **Inferred strongly:** no day-to-day admin. **Must ask** for a login vs ticket-only |
| Page builder | Drupal blocks, paragraphs, Webform, Solution Finder | **Verified** |
| Notable modules | Drupal Webform (`free-quote`); `pestpac_webforms` UTM script; CTM header blocks | **Verified** paths. PestPac name is **legacy/generic Sprowt**, not proof B&T still runs PestPac (CRM is **Fieldwork**) |
| Forms | Homepage Webform `free-quote` (first/last, phone, email, source, address, current-customer, help, SMS opt-in). Notifications historically **noreply@coalmarchleads.com** | **Verified** HTML + prior Gmail. **Must ask** exact routing/backup |
| WDIR form | `/services/wood-destroying-insect-report` — long realtor form (agency, buyer/seller, access/lockbox prompt, payment, delivery). `/wdir` is **404**. | **Verified** 27 Aug 2026 |
| Call tracking | `ctm-target-number-link` on `tel:` links. Raw HTML shows **(910) 329-1337**. CTM script is **not** in first-party HTML (likely GTM). Browser DNI **(910) 356-9966** observed 23 Aug and in CTM (account 462929). | **Verified** classes + GTM. Displayed 356 is **inferred DNI after JS**. |
| GTM | **GTM-MH3JJKS** | **Verified** live HTML 27 Aug |
| GA4 | Property “B&T Pest Control - GA4” under **Coalmarch Productions** (23 Aug) | **Verified** access inventory |
| Search Console | URL-prefix property on daniel@ (23 Aug) | **Verified** |
| GBP | Owner access daniel@; listing phone 1337 | **Verified** |
| Ads | Search CID paused; LSA active | **Verified** account-data (not a website finding except landing pages) |
| Cookie/consent | **No banner** on mobile homepage load 27 Aug. Privacy policy dated **01/22/2026**; browser-cookie instructions only; Flash-cookie language is dated | **Verified** |
| Privacy contacts | Opt-out emails listed: daniel@, contactus@, allison@; children contact toby@ | **Verified** policy page |
| Backups / export | Not visible from the public site | **Must ask Coalmarch** |
| Migratable? | Content and URLs can be copied; **theme, Webform+leads mail, CTM blocks, Sprowt widgets, and hosting are coupled** | **Inferred**. Full Drupal export **Must ask** |
| Email | MX → Google (`aspmx.l.google.com`) | **Verified**. B&T Workspace is independent of Sprowt |
| Customer portal | `btpestcontrol.serviceworkportal.com` (Fieldwork/ServiceWork) | **Verified** Phase 1. Independent of Coalmarch CMS |
| Contractual / proprietary | Sprowt is Coalmarch’s product. Contract renewed **April 2026, one year**; no seasonal retainer (mail 1 Jul 2026) | **Verified** mail. License terms **Must ask** |
| Facebook pixel | Referenced in live scripts 27 Aug | **Verified** by browser pass (do not treat as a second ad account) |

### What would stop functioning if Coalmarch access were removed

**Likely (inferred until they confirm):** public site if they own GCP/nginx; `/public_files/` assets; Drupal admin; form notification pipeline; CTM number swap; GTM container they own; organic reporting in Performance Insights; ticketed content edits.

**Likely to keep (verified independent):** Google Workspace email, Fieldwork, GBP (if B&T remains owner), GSC on daniel@, office number 1337, ServiceWork portal.

**Unknown:** domain auto-renew, DNS login, SSL, whether GTM is transferable.

**Do not migrate until those unknowns are answered in writing.**

---

## 2. Conversion and content audit (live site)

**Mobile viewport** ~375px, 27 Aug 2026, plus page fetches the same day. Prior HTML dump 23 Aug 2026 still matches stack.

### What works (observed)

- Sticky mobile bar: **CALL US** + **REQUEST AN ESTIMATE**.  
- PestGuard prices still public on `/compare-our-packages`: Basic **starting at 29/month**, PestGuard **45/month** (fire ants, fleas, ticks, stinging insects, mosquitoes), Plus **59/month** (adds termites / Advance bait). Initial fee still “applies,” dollar amount unpublished. HTML does not prefix `$`.  
- 4.9★ / **288** reviews widget (27 Aug).  
- Family/pet-safe and callback guarantee copy.  
- Truck photo and NPMA / NCPMA logos.  
- Hours on footer **M–F 8–5** (matches site/GBP, not 9–6 aggregators).  
- WDIR is a **working product form** (VA/FHA in title).  
- German roach **from $225** (Phase 1; still the clearest priced specialty).  
- Click-to-call **links** are present (`tel:` + CTM classes). Not test-called in this pass.

### What hurts conversion (observed)

| Finding | Customer impact | Conversion impact | SEO risk | Effort | B&T can DIY? |
| --- | --- | --- | --- | --- | --- |
| Homepage hero is tenure (“Since 1982”), not **$45 + included mosquitoes/fire ants** | High (wrong promise vs panic shopper) | High | Low | Low (copy) | No — Coalmarch ticket |
| $45 only after `/compare-our-packages` | High | High | Low | Low | No |
| Estimate form **9 fields** + SMS legal | High on mobile | High | None | Medium | No |
| No click-to-text CTA | Medium (hours 8–5) | Medium | None | Low–med | No |
| Offers expire **08/31/2026** still live on 27 Aug | High if they rot after 31 Aug | Medium | Low | Low | No |
| Jacksonville **title** stuffed (“Save $100 on Termite and Bed Bug… Pest Control Near Me”); H1 is “Pest Exterminators in Jacksonville, NC” | Medium | Medium | **High** (keyword stuffing) | Low | No |
| Drupal **fieldset-legend “Benefit Body”** still in Jacksonville HTML (2×, 27 Aug) — leftover CMS chrome; screen readers may announce it | Medium (unfinished) | Low–med | Low–med | Low | No |
| City pages historically coupon-first (Daniel 17 Jun); Jacksonville H1 is cleaner than the title — do not spawn more coupon cities | Medium | Medium | Medium | Medium | No |
| “Free estimate” vs **$75 inspection** (Daniel 17 Jun) | High (bait-and-switch risk) | High | Low | Low | No |
| WDIR: no public fee or turnaround; 15+ fields including lockbox | Realtors need SLA; homeowners bounce | Medium (right form, wrong marketing) | Medium | Medium | Copy via Coalmarch; ops must set SLA |
| Dual phone after CTM DNI (356 vs 1337) | Medium if both paint | Low if staff know DNI | None | Low (label) | Partial — **ask Coalmarch** before changing `tel:` |
| No cookie banner; policy still mentions Flash cookies | Low for conversion | None | Compliance | Medium | Coalmarch legal |
| Same-day language on areas page vs Aug tech-out | High if they cannot fulfill | Medium | Low | Low | Ops + Coalmarch |
| Blog Jacksonville mill + possum traffic | Low for panic shoppers | Low | Medium (wrong intent) | Medium | Ticket; don’t add more mill posts |
| Commercial promised, not built | Low unless they want commercial | Low | Low | High | Only if ops wants it |
| MY ACCOUNT in header | Low (existing customers) | Low clutter | None | Low | Optional demote |

### Consistency with Fieldwork and GBP

- Service types on the site (PestGuard, termite, WDIR, bed bug heat, wildlife, crawl, German roach) **match** live Fieldwork types. **Verified** against `17-fieldwork-crm.md`.  
- Recurring work is **PestGuard Regular** in Fieldwork, not the unused Agreements module. Site PestGuard naming is the right customer language.  
- GBP still has **lawn care** and junk services (owner mail 16 Aug) that the **website does not** push. Site is cleaner than GBP.  
- Capacity: Fieldwork is a route shop (~$88/WO). Site should sell **PestGuard accounts**, not “any pest, any city, same day.”  
- Direct-to-service **PestGuard Set-up** completed WOs **26** in 24 Jul–22 Aug — some customers skip a named inspection. The site should not imply every job starts with a free inspection.

### Tracking appears to function (without submitting)

- CTM classes on `tel:` links.  
- Webform + UTM capture script present.  
- coalmarchleads mail still arrived in 2026 (account-data sample).  
- May 2026 WDIR outage was real and later restored.  
- GA4 key events are **not** trustworthy as a conversion count (−28.6% vs sessions up). Use Coalmarch forms + CTM + Fieldwork Date Added.

---

## 3. Competitor benchmark (7 locals)

**Selection rule:** actual overlap on B&T’s priority markets/services from Phase 1 (`04`, `05`, Maps notes). Not chosen for national fame. **Aptive / Orkin / Terminix omitted** from this table (paid/door-to-door, not the website set).

Live re-check **27 Aug 2026** plus Phase 1 profiles **23 Aug 2026**.

| Competitor | Why they matter | Offer / price (public) | CTA / friction | Trust | WDIR/termite | What to adopt | What not to copy |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **Modern Exterminating** (`modernexterminating.com`) | JAX pack gravity; 1952 | No public monthly | Call + free estimate; sticky phone | Heritage + volume | Strong WDIR/termite tiles | Heritage/story photos | Hide all prices |
| **Eastline** (`eastlinepest.com`) | Military/VA/WDIR language; Onslow | No public price; $99 bundle bar | Schedule + call | 4.9 / 400+; QualityPro | **VA WDIR-100**, Termidor, seasonal calendar | Seasonal pest calendar; Camp Lejeune words | Vague “bundle & save” |
| **Diamond Pest Pro** (`diamondpestpro.com`) | Topsail/Hampstead driveway; review velocity | **$269 then $45/mo**; mosquito add-on **+$25** | Calculator; call | 4.9 / 780+ | Moderate on homepage | Size-based **initial + monthly** transparency | “Since 2020” as the story |
| **Cape Fear Termite & Pest** (`capefearpestcontrol.com`) | Pender/ILM; cheap quarterly | **$85/quarter** in hero | Sign up + call + chat | Weak review display | Strong wood-destroying | Bold simple quarterly number | Weak review proof |
| **Mosquito Authority JAX** | Owns mosquito queries | No price on page (Phase 1 site **$89 / $149**) | Quote + **AI chat** | Franchise, few reviews on page | N/A (outdoor only) | Explain *why* interval exists | AI chat as primary; mosquito-only positioning |
| **May Exterminating** (`mayexterminating.com`) | JAX institution; move-out | No public price; **$60 move-out** (Phase 1) | Call + Book/Text/Call/Email widget | Since 1963 | Termite + moisture co-equal | Text channel; move-out SKU **if ops can run it** | Widget spam; no prices |
| **Pest & Termite Consultants** (`pestandtermiteconsultants.com`) | City pages on Surf City/Sneads/JAX | **$175/quarter** pest+termite (Phase 1 + 27 Aug) | Form/call | 4.9 / 840+ claimed 27 Aug | Trelona bundle | Bundle pest+termite as a named plan (B&T already has Plus) | Template city mill |

**B&T differentiator that is still available:** published **all-in $45** with mosquitoes/fire ants **included**, 44-year family, Holly Ridge–Topsail HQ, 3-way termite *story* (proof still thin). Nobody in this set combines those four on the homepage.

**B&T should not imitate:** 40 doorway cities, fake Jacksonville pin, matching $150 national coupons, hiding PestGuard prices, AI-first contact.

---

## 4. Prioritized 30 / 60 / 90-day website plan

All items assume **Coalmarch still hosts**. Impact = customer + conversion. B&T implements by **ticket + ops decision**, not Drupal.

### Days 0–30 (do now)

1. **Hero rewrite** (home + pest page): $45/mo PestGuard; mosquitoes, fire ants, fleas, ticks, stingers included; German roaches / bed bugs / termites excluded; call + short form.  
2. **Offer dates:** extend or replace everything still showing **08/31/2026**. Align $75-off **Basic** vs pushing Plus (Phase 1 already flagged this).  
3. **Strip “Benefit Body”** fieldset legends and stuffed city **titles**; scan other city pages. Do not 404 old URLs.  
4. **Kill “free estimate”** where inspections are **$75** (Daniel 17 Jun).  
5. **Label the phone:** “Call tracking number” vs office, or show 1337 and keep 356 as DNI only in `tel:` — **ask Coalmarch** so tracking does not break.  
6. Send Coalmarch the question list in §6 (ownership). No migration.

### Days 31–60

7. **Short mobile form** (name, phone, zip or address, optional note) + click-to-text. Keep long form on `/get-your-estimate`.  
8. **WDIR page:** fee, turnaround, VA/FHA, “realtors: use this form”; do not drop lockbox fields.  
9. **Fire-ant page** + mosquito **vs $89 franchise** table (link to PestGuard).  
10. Demote Expertise.com; keep Google + NPMA. Real tech photos if Daniel has them.  
11. City-page standard: Wilmington-style substance, not coupon H1 (Daniel 17 Jun). Limit new cities.

### Days 61–90

12. Camp Lejeune / PCS / WDIR landing **only if** ops can take the volume.  
13. Vacation-rental / beach-house page (reviews already prove the ICP).  
14. Termite proof: 3-way diagram + two written jobs (no customer PII in recaps).  
15. Optional: initial-fee range vs Diamond’s $269.  
16. Still **no** site migration. Revisit ownership answers; if they refuse export/DNS transparency, that is a **2027 contract** issue, not a 90-day rebuild.

**Not in 90 days:** commercial site build, 40 city mill, Search Ads reboot, chatbot, matching Mosquito Authority’s outdoor-only brand.

---

## 5. Ownership and migration-readiness checklist

Complete **before** any “take the site in-house” decision. Status today:

| Check | Status 27 Aug 2026 |
| --- | --- |
| Domain registrar account in B&T’s name, 2FA, auto-renew | Unknown — ask |
| DNS (GoDaddy domaincontrol) login in B&T’s name | Unknown — ask |
| List of all records (A/AAAA/CNAME/MX/TXT/SPF/DKIM) exported | Not done |
| SSL issuer and auto-renew owner | Unknown |
| Drupal version + contrib/custom module list | Drupal 10 verified; full list unknown |
| Admin user for B&T (or documented ticket SLA) | Ticket-only, inferred |
| Database + `public_files` backup restore-tested | Unknown |
| Form destinations documented (to, CC, coalmarchleads) | Partial |
| CTM numbers, pools, DNI script owner | CTM exists; pools unknown |
| GTM-MH3JJKS container ownership + export | Unknown (Coalmarch likely) |
| GA4 property move vs copy | Coalmarch Productions — ask |
| URL inventory (~92 sitemap URLs) + 301 plan | Sitemap 200 on 27 Aug; map not built |
| Legal: privacy, SMS, AI disclaimer stay accurate | Policy exists; cookie banner absent |
| Replacement vendor or employee Drupal/Sprowt skill | Not in place |
| Parallel run (new host) before DNS cut | Not started |
| Written termination clause (notice, data, fees) | **Must ask** — contract Apr 2026–Apr 2027 |

**Migration is not ready.** Email and Fieldwork independence is the only bright spot.

---

## 6. Questions for Coalmarch

Send as one list (Tarsha / Matt). Do not imply cancellation.

1. Who is the **registrar of record** and who has the login?  
2. Who has **GoDaddy DNS** (ns47/ns48)? Can B&T be added without removing you?  
3. Confirm hosting: GCP project, nginx, S3 `btpestcontrol-s3-live` — B&T-owned or Coalmarch-owned?  
4. Is the CMS **Sprowt**? What Drupal version and who may have `/user/login`?  
5. What is the monthly **website/Sprowt/hosting** fee vs the **SEO retainer** vs paid ads?  
6. SLA for content tickets (Jun 2026 punch list took ~6 days — is that standard)?  
7. Export: Drupal DB, files, Webform submissions (PII — send to B&T inbox, not a repo), GTM, GA4.  
8. If the contract ends, what URLs, numbers, and tags **stop** on day 1 vs day 30?  
9. Can DNI stay on **356** if B&T later changes hosts?  
10. Form pipeline: Drupal Webform → ? → coalmarchleads.com → which mailboxes? Backup if that domain fails (May 2026 WDIR).  
11. Who owns **GTM-MH3JJKS**?  
12. Cookie consent: why no banner; will you update Flash-cookie language?  
13. Please implement the 0–30 day punch list in §4 (hero, expiries, Benefit Body legends, stuffed Jacksonville title, free-estimate copy).  
14. Do not add city pages or blog posts until the punch list is done.  
15. Written confirmation that B&T owns **content and the domain**, even if Sprowt is licensed.

---

## 7. Monthly Grokbot lead-conversion scorecard

Use `website-audit/monthly-scorecard-schema.csv` and the table in `MARKETING-CONTROL-CENTER.md`.

**Minimum monthly narrative (five lines):**  
(1) Spend and PI leads. (2) CTM calls vs PI call leads. (3) Date Added on the **same dates**. (4) PestGuard Set-up + pest inspection-estimate + WDIR-100 completed WOs. (5) Whether the $45 hero and offer dates are still correct on the live homepage.

Do not report CAC. Do not average GA4 with Coalmarch.

---

## 8. Stopping point

Stop new research. The next work is a **Coalmarch ticket** plus filling next month’s scorecard. Do not open another competitor inventory. Do not reconcile paid ads again unless a landing-page test needs a channel label.
