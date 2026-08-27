# Meta / paid-ads research — Eastern NC pest control

**Date observed:** 2026-08-23  
**Constraint:** Public sources only. No quote forms. No calls.  
**Library URL used:** https://www.facebook.com/ads/library

Companion: `pricing-research.md`, `pricing-draft.csv`.

---

## Method and limits

Attempted on 2026-08-23:

1. **Meta Ad Library web UI**  
   `https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country=US&q=<brand>&search_type=keyword_unordered`  
   Fetch returned a login/JS shell only. The library is not readable as static HTML from this environment. No Ads Archive API token was available.

2. **Public Ad Library mirrors**  
   - [AdMakeAI Terminix advertiser page](https://admakeai.com/advertisers/terminix) — scrapes Meta Ad Library daily.  
   - [PipelineOn “Pest Control Companies Running Most Facebook Ads 2026”](https://pipelineon.com/blog/pest-control-companies-running-most-facebook-ads-2026/) — June 2026 census of **139 US pest advertisers / 623 live ads**.

3. **On-site offers that typically match paid search/social CTAs**  
   Homepage banners, coupon codes, and franchise specials pages (documented in `pricing-draft.csv`). These are the creatives most likely running in paid social even when the library UI is gated.

4. **X (Twitter)**  
   Connected X account is **not enrolled** for search. No X ad or organic scan was run.

**Cannot confirm from here:** exact geo targeting (Onslow vs national), spend, A/B variants, or whether a given Meta ad is currently eligible in 28405 / 28540. Treat library-mirror counts as national unless noted.

---

## Library URLs to reopen in a browser

Search these in Ad Library (country = United States, category = All ads):

| Query | Suggested Ad Library search |
| --- | --- |
| Orkin | Orkin |
| Terminix | Terminix |
| Aptive | Aptive Environmental OR Aptive Pest Control |
| Hawx | Hawx Pest Control |
| Massey | Massey Services |
| Mosquito Joe | Mosquito Joe of Southeastern NC |
| Mosquito Authority | Mosquito Authority of Jacksonville |
| Diamond Pest Pro | Diamond Pest Pro |
| Cape Fear Termite | Cape Fear Termite & Pest Control |
| B&T | B&T Pest Control |
| Clegg’s | Clegg's Pest Control |
| Port City Pest | Port City Pest |
| Jones Pest Control | Jones Pest Control Jacksonville |
| Economy Exterminators | Economy Exterminators |
| Pest & Termite Consultants | Pest and Termite Consultants |

Direct library entry: https://www.facebook.com/ads/library

---

## What public mirrors showed on 2026-08-23

### Terminix (national)

Source: https://admakeai.com/advertisers/terminix

| Metric | Value |
| --- | --- |
| Active Meta ads | **264** |
| Video | 86 (33%) |
| Image | 12 (5%) |
| Carousel | 6 |
| Dynamic | 160 (61%) |
| Platforms (counts on that snapshot) | Facebook 404, Instagram 404, Messenger 364 |
| Longest-running visible | ~56 days |

**Visible ad themes (headlines/snippets on the mirror, no dollar prices in the unlocked tiles):**

- “Before termites show up”
- “Before mosquitoes show up”
- “Before rodents show up”
- “Before pests show up”
- “Free termite inspection”
- “Call the pest pros”

Price is **not** in the unlocked creative snippets. That matches Terminix.com, which hides plan dollars behind an address widget and uses **codes** instead:

| Code / offer (site, 2026-08-23) | Where |
| --- | --- |
| **SAVE75** | terminix.com homepage |
| **SAVE50** | /pest-control/ “SAVE $50 ON PEST CONTROL” |
| **BITE50** | $50 off mosquito & tick |
| Bundle termite + pest save avg **$175** | My Offers module |
| **$100** off rodent/wildlife | My Offers module |

Expect Meta traffic to land on address-capture pages with those codes, not on a public rate card. **Wilmington branch exists** (2111 Capital Drive) so national ads can convert locally even if creative is not NC-specific.

### Industry census (June 2026)

Source: PipelineOn audit of **every active US pest control Facebook advertiser** in June 2026.

- 139 companies, 623 live ads.
- Highest volume in that census were **regional** brands (Plunkett’s 70, Atticare 37, Dynasty 26, HomeTeam 23, Brooks 21…) — **not** Orkin/Terminix/Aptive.
- Implication: national chains may run fewer, higher-production ads (Terminix’s 264 in August via AdMakeAI suggests Terminix volume is real but may sit outside PipelineOn’s “US pest advertiser” filter or may have ramped after June). Local Eastern NC independents were **not** in the published top 10.

No PipelineOn row for B&T, Cape Fear, Diamond, Port City, Jones, or Mosquito Joe of Southeastern NC.

### Other brands

No AdMakeAI-style public scrape was found for Orkin, Aptive, Hawx, Massey, Mosquito Joe SE NC, Mosquito Authority Jacksonville, Diamond, Cape Fear, or B&T on 2026-08-23. Those brands still have **on-site offer units** that are the usual paid-social payload:

| Brand | Live offer language most likely in ads | Geo relevance |
| --- | --- | --- |
| **Orkin** | “Save $75… code APPLY75” | National; Wilmington location page exists |
| **Hawx** | Homepage “GET $150 OFF”; NC city pages historically “$150 off… code NC150”; some WP copy “up to $350 off” | Wilmington branch serves this DMA |
| **Aptive** | Lead-gen: “$200 off initial” / “From $49/mo*” — **not** on Aptive’s own Wilmington URL | Wilmington branch 10 Cardinal Dr S |
| **Massey** | “Save $50 on pest services” | Wilmington page |
| **Mosquito Joe SE NC** | 57% off Home Pest Defense with Mosquito; $25 first treatment; 5% hero — expire 12/31/2026 | Franchise explicitly Wilmington |
| **Mosquito Authority JAX** | $89/mo pest+mosquito; $149/mo total home; $39 add-on | Jacksonville franchise |
| **Clegg’s** | $39 off initial pest; $100 off termite; 15% military / first responder | Wilmington office |
| **B&T** | $75 / $100 / $25 heroes / refer-a-friend — expire 08/31/2026 | Eastern NC; Meta Pixel `1126336218230620` on btpestcontrol.com |
| **PTC** | $175/qtr + free Trelona | Wilmington/Jacksonville landing pages |
| **Cape Fear** | $85/quarter | Homepage |

B&T is **running a Meta Pixel**, so they are at least measuring (and likely buying) Meta traffic. Pixel ID from saved site HTML: `1126336218230620`.

---

## Offer patterns in paid creative (inferred)

What competitors put in ads vs what they put on rate cards:

1. **Dollar-off initial**, not monthly price — Orkin $75, Terminix $50–$75, Hawx $150, Massey $50, Clegg’s $39, Mosquito Joe $25. Exception: Mosquito Authority and Cape Fear/PTC/B&T will actually print a recurring number.

2. **Fear + inspection CTA** — Terminix library themes are “before termites/mosquitoes/rodents show up” + free termite inspection. No price.

3. **Percent-off bundles** — Mosquito Joe 57% off “Home Pest Defense with Mosquito” is a classic franchise Meta/Google coupon. Base price hidden.

4. **Hero / military** — High relevance next to Camp Lejeune. B&T $25 stackable; Joe 5% not combinable; Clegg’s 15%.

5. **Code-based checkout** — APPLY75, SAVE75, SAVE50, BITE50, NC150. Codes are more common for nationals than for local independents (B&T uses offer IDs in URLs: `offer=138`, `145`, `142`…).

6. **Geo mismatch risk** — Arrow’s $50 coupons and Terminix Triad’s $42/mo are **real advertised prices** that do **not** apply to Jacksonville/Wilmington branches. Ads for those brands can still impression in NC.

---

## Google Business Profile / Facebook organic

Not fully scrapeable here. What was confirmed from websites and directories:

- Hawx Wilmington/Jacksonville pages embed Google ratings (Wilmington page 4.8 / 3223 reviews; Jacksonville page 4.6 / 1987 — likely national/brand rollups, not branch-only).
- Massey Wilmington cites 15,000+ reviews (brand-level).
- Aptive Wilmington page: 4.7 from a large Google pool.
- Jones, Port City, Canady: review text about “great price” / “fair” **without dollars**.
- No Google Business post archive with prices was captured.

Facebook Page posts for these companies were login-walled in fetch.

---

## Practical takeaway for B&T

- Nationals **will not** fight B&T on a public $29/$45/$59 grid in ads. They will fight on **$50–$150 off first service** and “free inspection.”
- The only local paid-social prices a shopper can screenshot today: **Cape Fear $85/qtr**, **PTC $175/qtr**, **Mosquito Authority $89 / $149**, **Diamond $269 start / $299 termite year**, **B&T $29/$45/$59 + $75/$100**.
- Hawx’s **$150 off** is the loudest first-service discount in-market; B&T’s $75 setup-off is half that headline.
- Mosquito Joe’s **57% off** pest+mosquito bundle is the loudest **percent** claim; B&T’s counter is “mosquito included at $45/mo.”
- Re-open Ad Library in a logged-in browser on the URLs above to attach creative screenshots. This file records everything that was publicly recoverable without the JS UI.
