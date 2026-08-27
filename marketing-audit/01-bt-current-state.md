# B&T Pest Control — current-state profile

**Date observed:** 2026-08-23  
**Official site:** [https://www.btpestcontrol.com/](https://www.btpestcontrol.com/)  
**Legal/operating name in public listings:** B&T Pest Control / B&T Pest Control, Inc.

This file is a factual inventory of how B&T presents itself. Recommendations live in `15-recommendations.md` and `FINAL-MARKETING-AUDIT.md`.

---

## 1. Identity and positioning

| Attribute | Public claim | Source | Confidence |
| --- | --- | --- | --- |
| Founded | 1982 (44+ years) | Homepage title, About Us | High |
| Ownership | Family-owned | About Us, Tracxn, LinkedIn | High |
| Named leader (public) | Toby Cahoon, Operating Partner / GM; LinkedIn also lists NC Wildlife Damage Control Agent and NC Structural Pest Control Licensee | [LinkedIn](https://www.linkedin.com/in/toby-cahoon-76b86416) | Medium (profile, not the site) |
| HQ | 1276 NC 172, Holly Ridge, NC 28445 | Site footer, Maps | High |
| Phone | **910-329-1337** canonical (schema, footer, GBP). Some visitors see **910-356-9966** via CallTrackingMetrics DNI on `tel:` links. | Homepage HTML + browser session | High |
| Hours (site) | Mon–Fri 8:00 a.m.–5:00 p.m.; Sat/Sun closed | Footer | High |
| Hours (third-party) | Birdeye/Google scrape showed 9:00 a.m.–6:00 p.m. in one aggregator | [Birdeye](https://reviews.birdeye.com/b-t-pest-control-144800454509466) | Medium — **NAP conflict** |
| Mission language | “Exceed our clients’ expectations and surpass our competitors’ efforts.” Client-driven; customer service as foundation | About Us | High |
| Brand promise | Guaranteed protective barrier; “we don’t just spray and pray”; come back free | Homepage | High |
| Award | “Best Pest Control Companies in Jacksonville Award” via Expertise.com-style “manual review” | About Us | High that they display it; **low** that shoppers treat Expertise badges as decisive |
| Associations | Footer links to NPMA (`npmapestworld.org`) and NC Pest Management Association | Site footer | High they claim membership; membership status not independently verified |

**Implicit position today:** long-tenure local family company with an all-inclusive monthly plan (PestGuard) that bundles “premium” pests other companies upsell. Not positioned as cheapest, not as a national brand, not as a mosquito-only specialist, not as a Camp Lejeune military specialist (even though the market is).

---

## 2. Contact and conversion system

| Channel | Detail | Source |
| --- | --- | --- |
| Phone | 910-329-1337; sticky “Call Us Now” | Header |
| Quote form | First/last name, phone, email, source, current customer, address, message + SMS consent | Homepage, service pages, `/get-your-estimate` |
| Estimate page | [Get Your Quote](https://www.btpestcontrol.com/get-your-estimate) | Sitemap |
| Contact page | [Contact](https://www.btpestcontrol.com/contact) | Sitemap |
| Customer portal | `https://btpestcontrol.serviceworkportal.com/sessions/new` | Areas-page HTML |
| Chat | Not observed in crawled HTML | Medium — no Intercom/Drift/Tawk signatures found |
| Text-to-book | SMS consent on forms; no public “text this number” CTA | Site forms |
| Online booking of a specific slot | Not observed; forms are lead-gen, not a scheduler | High |
| Review funnel | `/leave-review` | Sitemap |

**Friction:** forms are long (name, phone, email, source, current-customer, address, open text, legal SMS). A homeowner with ants in the kitchen can call; they cannot book a time without a callback. No visible live chat.

---

## 3. Service inventory (what the site actually sells)

### Recurring residential pest — PestGuard family

Source: [Compare packages](https://www.btpestcontrol.com/compare-our-packages) and [Pest Control](https://www.btpestcontrol.com/services/pest-control). All labeled **“Starting at” + “Initial Fee Applies.”** Setup dollar amount is **not published**.

| Plan | Advertised monthly | Cadence | Stated coverage | Explicit exclusions |
| --- | --- | --- | --- | --- |
| PestGuard Basic | $29/mo | 4 quarterly exterior inspections/treatments | House ants, house spiders, American / Oriental / Smokey Brown roaches | Not a full premium-pest plan |
| PestGuard | $45/mo | 6 bi-monthly exterior inspections/treatments | Current infestations + fire ants, fleas, ticks, stinging insects, mosquitoes, “and more”; YardGuard up to ½ acre | German cockroaches, bed bugs, wood-destroying insects |
| PestGuard Plus | $59/mo (auto-pay mentioned on termite page) | 6 bi-monthly visits + termite bait monitoring | PestGuard + termites via Advance Termite Bait System; copy also claims liquid + borate as part of a “3-way” program | German roaches and bed bugs still outside general pest |

**Guarantee (PestGuard):** free extra service if unsatisfied, if pests appear between visits, or if pests appear inside. “FREE Emergency Call-Back Service.”

**Exterior-first method:** “90% of pest problems originate outside”; EPA-approved products; interior treatment at initial visit; interiors not routinely treated unless needed.

### Termites

Source: [Termite Control](https://www.btpestcontrol.com/services/termite-control)

- Claims to be the only Eastern NC company combining **liquid + Advance bait + borate**
- PestGuard Plus is the packaged offer ($59/mo starting, $100 off promo)
- One-time termite treatments also offered; promo: free one-time exterior pest service (**$225 value**) with termite treatment
- “No booster treatments required”
- Monitoring of bait stations every two months
- Copy claims no other eastern NC company offers this combination — **competitive claim, not independently verified**

### Wood-destroying insect reports

Source: [WDIR](https://www.btpestcontrol.com/services/wood-destroying-insect-report)

- NC WDIR-100 / WDIR language mixed with “WDIR” on some pages
- VA & FHA approved in title
- Real-estate closing form (buyer/seller, lockbox, payment, transfer of existing termite agreement)
- **No public inspection fee**

### Bed bugs

Source: [Bed Bug Treatment](https://www.btpestcontrol.com/services/bed-bug-treatment)

- High-intensity **heat**, one-day / single-visit claim
- 30-day warranty; **90 days if mattress/box-spring encasements purchased**
- Cost-effectiveness pitch (keep furniture; not “cheap”)
- Jacksonville city page also says 30-day warranty
- **No public dollar price**

### German cockroaches

Source: service page (extracted 2026-08-23)

- **Starting at $225** (verified advertised, size/infestation dependent)
- Intensive initial treatment + **two complimentary follow-ups within 60 days**
- Family/pet-friendly language
- Not included in PestGuard

### Mosquitoes

- Included in PestGuard at $45/mo (core differentiator vs mosquito franchises)
- One-time / event treatments mentioned
- YardGuard as the yard component

### Fleas

- Covered under PestGuard
- “Flea Magic” one-year written guarantee language on flea page
- Indoor + lawn treatments; move-out flea treatments **without warranty**

### Rodents

- Inspection, bait/traps, **exclusion**
- Included as a PestGuard selling point on city pages (“rats… at no extra charge” on some Holly Ridge/Topsail copy — confirm whether rats are truly in the $45 plan; pest-control page exclusions list German roaches, bed bugs, WDIs only)

### Wildlife

- Birds, squirrels, raccoons, opossums
- Claims a **Certified NC Wildlife Damage Control Agent** on staff
- Exclusion + decontamination
- Promo: **10% off wildlife exclusion**

### Crawl space moisture

- Evaluation of wood moisture / RH
- 8-mil overlapped/anchored/taped vapor barrier (vs 6-mil knock)
- Seal vents/cracks
- Industrial dehumidifier with pump (vs portable indoor units)
- Repair of moisture damage
- Promo: **$250 off** complete sealing + dehumidifier (specials page); crawl-space page also says **$250 off** in body copy

### One-time general pest

- Offered (About Us: “one-time pest control services”)
- List value implied at **$225** via free-with-termite offer
- Refer-a-friend table includes “One Time Pest Service” at $10 / $10 credit

### Commercial / property management / HOA

- Homepage says “homeowners and businesses”
- **No dedicated commercial, restaurant, HOA, or property-management page in the XML sitemap**
- Beach-house / rental language appears on city pages (Surf City, Wrightsville, Jacksonville reviews)

### Not found as dedicated pages

Ants (beyond a section on the pest-control page), fire ants, spiders, ticks, stinging insects, carpenter ants (blog only), Formosan termites, commercial IPM, attic insulation, mosquito-only seasonal package page (mosquitoes are a service page but sold as included).

---

## 4. Offers (specials page, expire 08/31/2026)

Source: [Special Offers](https://www.btpestcontrol.com/special-offers)

| Offer | Copy | Stack notes |
| --- | --- | --- |
| $75 off PestGuard **Basic** initial setup | Headline on some modules says “PestGuard”; body specifies Basic | Ambiguous whether it applies to $45 PestGuard |
| $100 off PestGuard Plus | Pest + termite program | Repeated on city pages |
| $250 off crawl space package | Sealing + dehumidifier | |
| Free exterior pest ($225 value) | With termite treatment | |
| $25 off recurring for Community Heroes | Military, LE, educators, medical, clergy, fire, EMS; **can combine** | Strong Camp Lejeune fit |
| 10% off wildlife exclusion | | |
| Refer a friend | Dual credit | See table |

Refer-a-friend (verified on `/refer-friend`):

| New service | Current customer | New customer |
| --- | --- | --- |
| One-time pest | $10 | $10 |
| PestGuard | $20 | $20 |
| PestGuard Plus | $25 | $25 |
| Termite | $25 | $25 |
| Bed bug | $25 | $25 |
| Crawl space encapsulation | $50 | $50 |

These credits are small versus Mosquito Joe ($50/$50) and Economy Exterminators ($50 + drawing) as documented in `evidence/pricing-research.md`.

---

## 5. Website structure (sitemap, 92 URLs)

Full list: `evidence/bt-sitemap.xml` / `evidence/bt-sitemap-urls.txt`.

**Core conversion:** `/`, `/get-your-estimate`, `/contact`, `/compare-our-packages`, `/special-offers`, `/refer-friend`, `/leave-review`

**Service URLs:** pest-control, termite-control, bed-bug-treatment, wood-destroying-insect-report, rodent-control, mosquito-control, flea-control, wildlife-control, crawl-space-moisture-control, german-cockroach-control

**Oddity:** several `/services/.../ogden-nc` child pages (termite, bed bug, mosquito, rodent, wildlife, crawl space). Ogden is over-built relative to Jacksonville/Wilmington.

**Blog:** mix of `/blog/...`, `/blog/posts/...`, and old `/about/our-blog/...`. Many Jacksonville-centric posts (fire ants, bed bugs, termites, mice, raccoons, pigeons, possums, crawl space). Newer 2026 posts exist (carpenter ants vs termites, fall pests, German roaches, stinging insects, ticks).

**Platform:** Drupal (robots.txt Disallow `/core/`, `/admin/`; Simple XML Sitemap module). Theme/Sprowt-class local-service CMS.

**Sitemap 500 via some fetchers; curl returned 200** — treat as intermittently fragile.

**Index holes:** `/pest-control-burgaw`, `/pest-control-maple-hill`, `/pest-control-wrightsville-beach` exist but are **not** in sitemap. Cedar Point, Kure Beach, Maysville, North Topsail Beach are listed as cities **without** public URLs.

---

## 6. Trust, reviews, and social (public)

| Asset | Observation | Source | Confidence |
| --- | --- | --- | --- |
| Google rating on site | **4.9 stars, 285 reviews** | Site header widget 2026-08-23 | High for what the widget shows |
| Google (Birdeye scrape) | **4.9 / 271** | Birdeye 2026-08-23 | High that aggregator lagged or Google count moved |
| Google Maps CID | `15308633390670589428` | Site link | High |
| Yelp | [b-and-t-pest-control-holly-ridge](https://www.yelp.com/biz/b-and-t-pest-control-holly-ridge); MapQuest Yelp feed **4.0 / 6 reviews** including a 2022 burglary allegation | MapQuest/Yelp | Medium for count; **do not treat allegation as fact** — it is a public review B&T must manage |
| BBB | Profile URL in third-party indexes: `bbb.org/us/nc/holly-ridge/profile/pest-control/b-t-pest-control-0593-90054048` | Search | Medium — live BBB fetch timed out |
| Facebook | [facebook.com/btpestcontrolinc](https://www.facebook.com/btpestcontrolinc) | Footer | High URL; follower count not captured (login wall) |
| Instagram | [instagram.com/btpest](https://www.instagram.com/btpest/) | Footer | High URL |
| YouTube | [youtube.com/@BTPest](https://www.youtube.com/@BTPest); media gallery embeds flea/mouse and “Christmas Mouse Miracle” | Media gallery | High |
| TikTok | [tiktok.com/@btpest](https://www.tiktok.com/@btpest) | Footer | High URL; content volume not independently counted |
| Photos | Media gallery exists | `/media-gallery` | High |

**Review themes from on-site Google snippets and Birdeye excerpts:** on-time, professional, friendly, long tenure (17–20 years), beach-house contracts, fire ants gone, spiders gone, value/price, named techs **Michael / Michel Arnold, Josh / Josh McLamb**. Negative depth is **not** visible in the on-site widget (it only shows 5-stars).

---

## 7. Technical / brand inconsistencies (inventory only)

1. **Hours:** site 8–5 vs aggregator 9–6.  
2. **City on Google/Birdeye:** Surf City vs Holly Ridge office.  
3. **Address strings:** 1276 NC 172 vs 1276 NC Highway 172 vs 1276 NC-172.  
4. **WDIR vs WDIR vs WDI vs NC WDIR-100** naming.  
5. **PestGuard vs PestGuard vs PestGuardBASIC vs PestGuardPLUS** casing.  
6. **$75 off** headline vs Basic-only body.  
7. **Years in business:** “36 years,” “40 years,” “44 years” all appear on live templates.  
8. **Expertise Jacksonville award** on a Holly Ridge company — fine, but it frames JAX as home base while GBP is Holly Ridge/Surf City.  
9. City-page titles stuffed with “Save $100 on Termite and Bed Bug” even when the live offer is $100 off **Plus**, not a generic $100 off those jobs.  
10. No commercial page despite “businesses” claims.

---

## 8. What B&T is actually good at (from public evidence)

- **Price transparency** on monthly plans ($29 / $45 / $59) — rare in this DMA.  
- **Bundling mosquitoes, fire ants, fleas, ticks, stinging insects** into the $45 plan.  
- **Termite + pest bundle** at $59/mo with a 3-method story.  
- **Heat bed bugs** with a written 30/90-day warranty.  
- **Public German-roach starting price ($225)** plus two follow-ups.  
- **44-year local tenure** and high Google star rating.  
- **Hero discount that stacks.**  
- **Wildlife license claim** and crawl-space offering (full-home envelope, not spray-only).

## 9. What B&T is not (yet)

- The Google-review volume leader in Jacksonville (Modern Exterminating is in another league).  
- A military/PCS specialist on the website (Eastline and May are louder).  
- A mosquito-season TV/radio brand (Mosquito Authority / Mosquito Joe own that SKU).  
- A commercial/food-safety brand.  
- A company that publishes the **initial setup fee**.  
- A company with a defined same-day radius, online scheduler, or always-on chat.
