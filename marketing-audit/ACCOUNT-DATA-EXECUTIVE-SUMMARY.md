# B&T Pest Control — Account-data executive summary

**Prepared:** 23–25 August 2026  
**Company:** B&T Pest Control (family-owned). **Owner:** Toby Cahoon. **Marketing/ops contact on these accounts:** Daniel Cahoon (`daniel@btpestcontrol.com`).  
**Scope:** Read-only inspection of authenticated Google, Coalmarch, Gmail, Fieldwork, and related sessions. No ads, GBP, GA4, GSC, GTM, LSA, Coalmarch, Fieldwork, or call-tracking settings were changed. No call recordings were played. No customer names, full phones, emails, street addresses, account numbers, or card data are stored in this file.

This is the management layer on top of the public-web audit in `FINAL-MARKETING-AUDIT.md`. It does **not** redo that audit. It tests those hypotheses against first-party data.

---

## 1. Account access

| Platform | Access | Notes |
| --- | --- | --- |
| Google account | **Yes** | `daniel@btpestcontrol.com` |
| Google Business Profile (owner) | **Yes** | B&T Pest Control, Inc · 1276 NC-172, Holly Ridge · (910) 329-1337 |
| Search Console | **Yes** | `https://www.btpestcontrol.com/` |
| GA4 | **Partial** | Coalmarch-owned property; overview metrics only in this pass |
| Google Ads (Search/PPC) | **Yes (paused)** | CID **367-996-4323**: **173 campaigns, all paused** (JAX/Wilmington/Rocky Point pest & bed bug). Not the live spend engine |
| Local Services Ads | **Inferred + Gmail** | CID **589-278-3347** is **active** (hundreds of “new call” emails). Direct LSA UI not fully exported |
| Tag Manager | **Not completed** | |
| Looker Studio | **Not completed** | |
| YouTube Studio | **Not completed** | Public/site evidence: videos previously pulled after a former employee issue |
| Coalmarch Performance Insights | **Yes** | `performanceinsights.coalmarch.com` (TapClicks). Primary lead/spend rollup |
| CallTrackingMetrics | **Blocked 25 Aug 2026** | Session expired to login. 2FA setup **not** clicked. No call aggregates. |
| Meta / Facebook Ads Manager | **Not in this Google session** | October 2025 recap: in-house Meta video (~20 clicks/day) existed |
| Fieldwork CRM | **Yes (25 Aug 2026)** | User `Grok`. Date Added, Executive Summary, service volume, estimates/agreements reports. **No** 2026 source tags |

---

## 2. Data actually analyzed

- **Google:** GBP owner performance (Mar–Aug 2026), GSC 3-month and ~16-month query/page stats, July GSC email, GA4 28-day snapshot, Ads account IDs and billing/LSA mail.
- **Coalmarch:** YTD and last-30-day spend/leads/CPL, monthly 2026 table, paid vs SEO retainer split, inbound-ad lead types.
- **Call tracking:** Only what Coalmarch rolls up (call vs form vs message). Raw CTM dispositions, duration, spam, and unique callers are **unavailable**.
- **Gmail (aggregated):** Paid-budget history, LSA lead-notification volume, website form **types** (estimate vs WDIR vs contact), GBP hygiene thread with Toby, WDIR form-outage thread, contract/budget decisions.
- **Fieldwork (25 Aug 2026):** new accounts by Date Added (53 / 156 / 311 — see date caveats), Executive Summary production/invoicing for 30d / 90d / YTD, August service-volume mix, empty August estimates/agreements. Customer-level rows were **not** stored.
- **Not used as customer evidence:** individual form bodies, LSA caller identity, CTM recordings, Fieldwork customer lists, route-email bodies.

---

## 3. Five most important discoveries

1. **Leads are real and paid is mostly Local Services Ads, not a big branded Search account.** Coalmarch YTD (1 Jan–22 Aug 2026): **$41,940 spend, 741 leads, $56.60 CPL**. Agency mail (Jan 2026) said **100% of paid budget was on LSA**. Search CID **367-996-4323** has **173 paused geo campaigns** (including Wilmington). LSA mail and payment notices prove LSA is the live paid engine. Do not flip Search back on without term-level history.

2. **Spend doubled; lead volume did not.** YTD spend **+120%** vs prior year; leads **+8%**; CPL **+104%**. That is the opposite of “more budget = proportionally more work.” Efficiency is the problem, not awareness in the abstract.

3. **Jacksonville is already the #1 discovery query on the Holly Ridge GBP** (“pest control jacksonville nc” **147** searches in the GBP insights window). Phase 1 Maps weakness is still the right *competitive* story. First-party data adds: Google is already showing this listing to Jacksonville searchers. The gap is winning the **local pack / close**, not whether Jacksonville demand exists.

4. **WDIR/real-estate forms are a live channel, not a theory.** In a 50-thread sample of `noreply@coalmarchleads.com`, **17/54 subject lines were Wood Destroying Insect Report** vs **35 Free Estimate** and **2 Contact**. The WDIR form **did break in May 2026**; mail resumed afterward. Coalmarch **paid** webforms show **zero for 13 months** because paid is **LSA calls/messages**, not because the site form has been dead since 2025.

5. **GBP is operationally dirty in ways Phase 1 could only guess.** Owner-side description still includes **lawn care**. Toby (owner) independently flagged fake/keyword services (home construction, honeybee removal, snake, Jacksonville-only fleas, etc.) and asked Coalmarch for a professional read **before editing**. That hygiene work is higher leverage than a site redesign.

6. **Fieldwork is a $700k YTD route business, not a 741-lead sales funnel.** Date Added **311** new accounts YTD vs Coalmarch **741** leads. Completed work is **7,901** WOs at **~$88** average — PestGuard Regular is the volume engine. The **Estimates module** is empty for 2026; that is **not** “no estimating.” B&T records onsite estimates as **inspection-estimate work orders**. Marketing still is **not** tagged on those WOs. **311/741 = 42%** is new accounts per platform lead, **not** a close rate. **$41,940 / 311 = $134.86** is marketing dollars per new account, **not CAC**.

---

## 4. Where leads actually come from

**Best current picture (Coalmarch definitions, not booked jobs):**

Last 30 days (24 Jul–22 Aug 2026): **99 leads** at **$54.49** blended CPL.

| Source (Coalmarch) | Last 30d | How to read it |
| --- | ---: | --- |
| Paid (LSA-heavy “inbound advertising”) | 55 leads / $3,350 / $61 CPL | Calls 30, messages 25; July paid **webforms 0** |
| Organic/SEO retainer attribution | 44 leads / $2,040 retainer / $46.40 CPL | Cheaper on paper; retainer is a fee, not media |
| Calls (all channels) | 50 | Down 22% vs prior 30d |
| Webforms | 24 | Up 37% — **not** the same as paid webforms |
| Messages (GBP/LSA-style) | 25 | Up 92% |

GBP Mar–Aug 2026: **764 calls**, **456 website clicks**, **370 direction requests** from the listing. GSC is **branded + possum-blog** more than service-intent SEO.

**Cannot yet say:** which of those 741 YTD “leads” became which of the **311** Fieldwork accounts, or which accounts are LSA vs GBP vs site vs realtor vs existing. Fieldwork Lead Source exists on Estimates and was **empty for August 2026**.

---

## 5. Best-performing services (demand evidence, not revenue)

| Signal | What it says |
| --- | --- |
| Form mix (email sample) | General **Free Estimate** is the majority; **WDIR** is a large minority (~30% of sampled form mail). |
| Agency May 2026 recap | **Bed bug** lead volume down; they called it high-profit and a priority. |
| GSC | Informational **possum/wildlife DIY** dominates non-brand clicks. German-roach **service URL** appears in top pages. Mosquito and fire-ant **queries are not in the GSC top 10**. |
| GBP searches | Generic pest/exterminator + Jacksonville + fleas Surf City — not mosquito-franchise terms. |

**Revised view vs Phase 1:** WDIR is **confirmed demand**. Mosquito/fire-ant as *search* opportunities remain **strategically plausible** but **not proven by first-party query volume**. Bed bugs are an agency-flagged **decline**, not a growth proof.

---

## 6. Best-performing markets

| Market | First-party evidence | Phase 1 public audit |
| --- | --- | --- |
| Holly Ridge / HQ | GBP pin, hours, phone, brand queries | Strongest Maps |
| Jacksonville | **#1 GBP search term**; city URL in GSC top pages; planned office suite (Sep 2025 recap) | Weakest Maps vs Modern |
| Sneads Ferry / Surf City | GBP service-area chips; fleas Surf City query; city URLs | Strong home-field |
| Wilmington / Ogden | Agency (May 2026): **do not** build city pages there | Phase 1 called it expansion; **near-term paid/SEO push should wait** |
| Growth towns named by agency | Richlands, Beulaville, Hubert, Swansboro, Maysville | Not the Phase 1 “40 city pages” mill |

---

## 7. Spend that looks inefficient or wasteful

- **YTD CPL +104% with only +8% leads** — the headline waste is **buying more expensive leads**, not a tiny vanity campaign.
- **LSA card declines** (multiple 2026 notices on CID 589-278-3347) — paid can go dark without a strategy change.
- **Link-building add-on cancelled Jul 2026** — family judged it did not produce business. Treat remaining SEO retainer as **rankings/leads**, not backlink theater.
- **August paid cut $4,600 → $2,000** because **a tech is out** — correct ops decision; do not read August lead drop as a channel failure.
- **Cannot prove Search-term waste** without Ads search-terms export (UI not fully pulled).

---

## 8. Lost-lead / missed-call problems

- **WDIR form outage (May 2026)** — documented lost real-estate work until fixed.
- **Homepage/city conversion-rate drop** (May 2026 agency recap) — CRO, not more towns.
- **LSA message leads** were discussed and not blindly enabled (May 2026). Message volume is now up 92% in the last 30 days — need CTM to see if those are answered.
- **CTM** session expired 25 Aug 2026 before Reports totals; 2FA setup was **not** clicked. Missed/unique/after-hours still unknown.
- **YouTube** previously stripped (former employee) — not a current lead engine.
- Capacity: owner/GM side is **labor-constrained** (crawl advertised but understaffed; August tech out; seasonal vs annual contract confusion). Marketing that books work you cannot run is waste.

---

## 9. Tracking problems that block confident decisions

No system in the stack currently answers the full path:

`search/ad → page/GBP → call/form → qualified → booked → recurring revenue`

Missing: **person-level** CRM feedback, unique new vs existing callers, spam filters, source on 2026 Fieldwork accounts, CAC by channel, LTV. Coalmarch “lead” ≠ Fieldwork “Date Added” (**741 ≠ 311**). Fieldwork production (**$700.07k** YTD) is mostly **existing PestGuard routes**, not new-customer revenue. GA4 “key events” fell **−28.6%** in 28 days while sessions rose — event tracking is not a business P&L.

---

## 10. Original audit conclusions — status

See `account-data/11-original-audit-validation.md` for the full table. Short version:

| Status | Items |
| --- | --- |
| **Confirmed / strongly supported** | NAP/hours still messy in the ecosystem; GBP needs cleanup; CRO > city mill; social is not the lead engine; WDIR/Lejeune-adjacent demand is real; reviews/Maps matter more than a redesign; HQ-area strength |
| **Changed** | Paid is **already LSA-first**, not “start Search on HQ+mosquito+WDIR.” Wilmington is **deprioritized by agency/client**. Jacksonville demand is **already hitting GBP**. |
| **Contradicted / overstated** | “LSA dormant” (browser pass 1) — **false**. “WDIR form still broken in July” as a paid-webform zero — **too strong**; WDIR mail continued. Mosquito/fire-ant as *proven unpaid search winners* — **not in GSC top queries**. |
| **Still unverified** | $45 PestGuard is the best *growth offer* in **booked revenue**; vacation-rental $; referral $ too low; close rates; whether GBP Jacksonville impressions convert vs Modern |

---

## 11. Ten highest-priority actions

1. **Clean GBP** (description, junk services, secondary categories) with a written change list — do not shotgun-edit. Owner already listed the junk.  
2. **Stabilize LSA billing** so the card does not kill the main paid channel.  
3. **Keep WDIR form uptime monitored**; it is a realtor/lender pipe.  
4. **CRO on homepage + city pages** (short form, SMS, PestGuard $45 inclusion) — agency already flagged CVR drop.  
5. **Do not raise paid until capacity is back** (Daniel already cut August to $2k).  
6. **Jacksonville:** treat as **review + pack + office-suite** problem, not “they never search us.”  
7. **Export Ads + LSA + CTM** (Daniel or Coalmarch) so search-term waste and missed calls are measurable.  
8. **Ignore Wilmington city-page build** until JAX/Onslow is saturated (agency instruction, now first-party aligned).  
9. **Stop paying for link-building theater** (already cancelled) — hold SEO to leads/rankings.  
10. **Require Fieldwork source** on every new account (LSA, GBP, website/organic, Google Ads, realtor/WDIR, referral, existing, other). Until then, **$134.86** per new account is the only spend/account math, and it is **not** channel CAC.  

---

## 12. Highest-value tests (46–90 days)

1. **PestGuard $45 inclusion vs Basic coupon** on homepage + GBP post — success = estimate forms + calls, not traffic.  
2. **WDIR/PCS landing page** fed by organic + LSA (not a 40-city mill).  
3. **LSA message handling SLA** now that messages +92%.  
4. **Fire-ant / mosquito pages** as *tests* (GSC does not yet show those queries in the head).  
5. **Jacksonville review velocity** vs any new city URL.

---

## 13. Urgent problems

| Type | Issue |
| --- | --- |
| Wasted spend | CPL doubled YoY; LSA declines; cancelled link package |
| Lost leads | May WDIR outage; possible unanswered messages; no missed-call data |
| Incorrect business info | GBP lawn care + junk services; aggregator 9–6 vs site/GBP 8–5 |
| Broken tracking | CTM locked; Ads UI incomplete; Fieldwork Estimates *module* unused (onsite estimates are WOs); GA4 key events unexplained drop |
| Bad optimization | Unknown whether LSA is charging for existing customers/spam |
| Attribution | Coalmarch lead ≠ Fieldwork Date Added (**741 vs 311** YTD) |

---

## 14. What Fieldwork changed (25 Aug 2026)

Fieldwork did **not** change Coalmarch spend/leads/CPL, LSA-first paid, GBP Jacksonville demand, or the August $2k cap. It **did** replace “no CRM” with:

- **311** new accounts YTD vs **741** platform leads  
- **$700.07k** production / **7,901** WOs at **~$88** — a route shop  
- PestGuard Regular as the volume service type (Aug service-volume)  
- The **Estimates module** is unused for 2026; onsite estimates are **inspection-estimate work orders**. Channel source tags still missing, so channel CAC is still impossible.  

### Reconciliation

| Period | Marketing leads | Fieldwork new accounts | Fieldwork production | Booking rate |
| --- | ---: | ---: | ---: | --- |
| ~30d | 99 (24 Jul–22 Aug) | 53 on **26 Jul–25 Aug** preset | $93.73k / 1,064 WOs (24 Jul–22 Aug) | **None comparable** |
| 90d | No native PI total | 156 (24 May–22 Aug) | $271.78k / 3,131 WOs | **None** (no 90d leads) |
| YTD | 741 / $41,940 | 311 | $700.07k / 7,901 WOs | **Not a close rate.** 311/741 = 42% accounts per lead |

### CAC / LTV

`$41,940 / 311 = $134.86` marketing dollars per new Fieldwork account YTD. **Not CAC** (unattributed mix). LTV **not computed**.

### Budget actions (priority)

1. Do not raise paid.  
2. Fix LSA billing.  
3. Require Fieldwork source list (LSA, GBP, website/organic, Google Ads, realtor/WDIR, referral, existing, other).  
4. Sell PestGuard accounts, not raw CPL.  
5. Find where WDIR lives in Fieldwork; count inspection-estimate **work orders** (not the Estimates module).  
6. Do not turn on 173 paused Search campaigns.  
7. Keep August-style capacity cap.  
8. Complete CTM aggregates (missed / unique / after-hours).

### Data-quality plan

Required source values above; 0 blanks on new Date Added; monthly count next to Coalmarch 30d/YTD; never map `Google` to a channel.

### Unresolved gaps

Exact 24 Jul–22 Aug Date Added count; CTM aggregates; Completed Work Orders by inspection type; source frequency; LTV.

### Inventory

Canonical paper: `account-data/17-fieldwork-crm.md`. Updated: this file, `ACCOUNT-DATA-AUDIT.md`, `00`, `09`, `10`, `12`–`16`, `exports/fieldwork-*.csv`, screenshots README. **No Fieldwork records or settings were changed.**

Full papers: `ACCOUNT-DATA-AUDIT.md` and `account-data/00`–`17`.
