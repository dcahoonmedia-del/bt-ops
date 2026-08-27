# Website: conversion, branding, technical SEO

**Superseded for decisions:** 27 Aug 2026 live pass in [`website-audit/WEBSITE-AND-COMPETITOR-MASTER.md`](website-audit/WEBSITE-AND-COMPETITOR-MASTER.md). Keep this file as the 23 Aug 2026 public-web notes.

**URL:** https://www.btpestcontrol.com/  
**Date:** 2026-08-23  
**Stack (inferred):** Drupal + Sprowt/local-services theme (robots Disallow `/admin/`, `/core/`; Simple XML Sitemap).

---

## 1. First impression (branding)

**Works**

- Immediately local: “Eastern NC,” 1982, 44+ years.  
- PestGuard as a named product (brandable).  
- Prices on the pest page — rare and good.  
- Sticky call + Google 4.9 widget.  
- Family/pet-safe, callback guarantee, no extra charge for “premium” pests.

**Hurts**

- Visual system is **template-local-SEO**: repeating stock-ish “ImageImage” blocks, duplicated nav, duplicated forms. Feels like a franchise mill, which undercuts the 44-year family story.  
- Homepage H1/body is generic comfort copy; the $45 inclusion is the actual differentiator and is **below** the pest selector.  
- Expertise.com “Best in Jacksonville” badge is low-trust among sophisticated shoppers.  
- Photography of **real B&T people** is not the hero (media gallery exists but is buried).  
- “36 years / 40 years / 44 years” still mixed in templates.

**Ants-in-the-kitchen test:** A panicked user can **call 910-329-1337** immediately. They cannot see “we’ll be there today in your zip,” cannot book a slot, and must complete a long form. **Pass on phone, fail on digital urgency.**

---

## 2. Conversion paths

| Path | Friction | Notes |
| --- | --- | --- |
| Call | Low | Sticky + header |
| Homepage pest checkboxes | Medium | Nice qualifier; still dumps into same long form |
| `/get-a-quote` | Medium-high | Duplicate of on-page forms |
| Specials “Redeem” | Medium | Expiry 08/31/2026 creates urgency |
| Compare packages | Low-medium | Best commercial page; initial fee still opaque |
| Chat / SMS click-to-text | Missing | Competitors (Aptive) chat |
| Online scheduler | Missing | Portal is for **existing** customers (`btpestcontrol.serviceworkportal.com`) |
| Click-to-call on mobile | Present | Keep |

**Form fields:** first, last, phone, email, source, current customer, address, message, SMS legal. For emergency ants that is **too many**. Split: (A) emergency 3-field + (B) full quote.

**No pricing on termite/bed bug/WDIR/wildlife** except German roaches $225 and monthly PestGuard. Bed bug heat shoppers bounce to companies that say “from $X/room.”

**Trust row missing on many templates:** license number, insurance, NPMA logo as image not just footer link, background checks, military discount badge.

---

## 3. Technical SEO (crawled)

| Item | Status | Evidence |
| --- | --- | --- |
| HTTPS | Yes | Live site |
| robots.txt | Allows site; Disallow admin, `/search/`, user | `/robots.txt` |
| XML sitemap | 92 URLs; **500 via some fetchers, 200 via curl** | Fragile |
| Indexable | Yes | — |
| Canonicals | Present on sampled pages | Need a crawl to find cross-duplicates |
| Title tags | Often **stuffed** (“Save $100 on Termite and Bed Bug… Pest Control Near Me” repeated) | Jacksonville, Burgaw, Wrightsville, etc. |
| Meta descriptions | Offer-led, sometimes mismatched to $75 vs $100 | — |
| H1 | One primary H1 on service pages | OK |
| H2/H3 | Service pages decent; city pages sectioned | OK |
| Internal links | Service ↔ city inconsistent; Ogden over-linked | `/services/.../ogden-nc` cluster |
| URL structure | Clean `/services/{sku}`, `/pest-control-{city}` | Good |
| City pages in sitemap | 21 of 25 directory cities; Burgaw, Maple Hill, Wrightsville Beach **missing from sitemap** | HTML vs sitemap |
| Thin/templated cities | High risk on smaller towns | Same PestGuard block |
| Blog | Split URL patterns (`/blog/`, `/blog/posts/`, `/about/our-blog/`) | Duplicate-system smell |
| Schema | Not fully extracted (homepage HTML dump oversized in this environment) | **Re-run in Search Console / Rich Results** — LocalBusiness + Service + FAQ + Review is expected on Sprowt but unverified here |
| Alt text | Many empty/generic “Image” in text extract | Weak |
| Page speed / CWV | Not measured (no PSI API in this pass) | Drupal + slick + third-party reviews often mediocre on mobile |
| 404 / redirects | `/sitemap` 404; some `/node/{id}` cities | Cedar Point, Kure Beach, Maysville, N. Topsail |
| www vs naked | Both resolve | Confirm canonical host |

**Google’s “what / where / why trust”:**  
WHAT = yes on service URLs. WHERE = partial (city pages, but missing N. Topsail/Kure/Cedar Point). WHY TRUST = 4.9 + years, but license #, photos of techs, and review schema are under-exploited.

---

## 4. Information architecture issues

1. PestGuard vs PestGuard vs PestGuard Plus naming vs PestGuardBASIC in coupons.  
2. Commercial promised, not built.  
3. Mosquitoes sold as included but mosquito page still needs a **calculator vs Mosquito Authority**.  
4. WDIR is a form-first page — good for closings, bad for SEO education.  
5. Blog Jacksonville-heavy; Wilmington/Topsail under-posted relative to service area.

---

## 5. Priority UX/CRO fixes (no build in this phase)

1. Hero: “Mosquitoes, fire ants, and fleas included — $45/mo” + call.  
2. Show **initial fee** or a range.  
3. Short mobile form.  
4. Click-to-text.  
5. Real photos of Toby’s team / trucks / crawl spaces.  
6. De-stuff titles.  
7. Add Camp Lejeune / WDIR / vacation-rental landing pages.  
8. Fix sitemap + orphan cities.  
9. Align hours/NAP.  
10. Stop Expertise badge as a primary trust signal; use Google + NPMA + NC license.
