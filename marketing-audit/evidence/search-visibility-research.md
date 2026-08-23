# B&T Pest Control — local search visibility research

**Subject:** B&T Pest Control (`btpestcontrol.com`), HQ 1276 NC-172, Holly Ridge, NC 28445  
**Date of collection:** 2026-08-23  
**Territory sampled:** Jacksonville, Wilmington, Surf City, Holly Ridge, Hampstead, Sneads Ferry, Swansboro, Richlands, Hubert, Wrightsville Beach, Carolina Beach, Burgaw, Ogden, Porters Neck, Cape Carteret, Newport, Piney Green, Rocky Point, Verona, Topsail Beach.

## Method and limits (read this first)

This is a **representative sample of 48 query observations**, not a paid rank-tracker panel. Collection constraints:

- **No paid ads were clicked. No forms were submitted.**
- Live Google web SERPs (`google.com/search`) returned a JS/consent wall from this environment, so **organic order is from web-search results** (Google-indexed titles/URLs). That order is a strong proxy for organic competition but is **not a screenshot of a Holly Ridge–located Google SERP with a 3-pack overlay**. Treat organic positions as “appears in the first cluster of indexed results,” not as guaranteed #1–#10 Google ranks.
- **Maps / local pack** was collected from Google Maps search URLs geo-centered on each market (`/maps/search/…/@lat,lng`). Many listings rendered as **address + phone + blurb without a visible rating**. Names for unlabeled addresses were reverse-looked-up from public business records (not by clicking ads). Some Maps pages mixed in out-of-state chains (Utah) because the datacenter IP is not coastal NC; those are ignored in the synthesis.
- **Sponsored / LSA ads** were not visible in Maps fetches or the JS-walled Google SERP. Ads column in the CSV is therefore `not observed (no click)`.
- **Ratings** on Maps were generally **not rendered** in the fetch. B&T’s own site schema (and Google-review aggregators) cite **4.9 / 285 reviews**; a third-party aggregator (`pestcontrolreviews.com`) cites **4.94 / 134** web reviews and **#1 of 2** in the Holly Ridge ZIP. Do not treat those as live Maps-pack stars.
- Reddit/forum: `site:reddit.com` pest-control queries for Jacksonville / Wilmington / Holly Ridge returned **no usable threads** in this pass.

Raw query log: [`search-observations.csv`](./search-observations.csv).

---

## Who actually owns search visibility

### One-sentence answer

**B&T owns Maps in the Holly Ridge–Surf City–Sneads Ferry core and often ranks in the organic top 3 on its own city pages in Onslow/Pender beach towns; Jacksonville Maps and Wilmington Maps/organic are owned by in-town incumbents (Modern, May, Dodson, Terminix; Clegg’s, Jay Taylor, Allied, Canady & Son, Healthy Home). Programmatic city-page factories (Aptive, Rid-A-Pest, Bug-N-A-Rug, Pest & Termite Consultants, Pro-Con, Ward) flood organic for every small town and steal clicks B&T should own.**

### Maps vs organic, by geography

| Zone | Maps owner(s) | Organic owner(s) | B&T |
|---|---|---|---|
| **Holly Ridge (HQ)** | **B&T #1** on Maps for “pest control” near 34.49,-77.54. Nearby: G’s Pest Control (Sneads Ferry), Freedom Lawns, Bug-N-A-Rug (Hampstead 19618 US-17), Tri-County, Mosquito Authority, Jones Pest (Maple Hill). | B&T city page **#2** behind Riggs Moisture, Termite & Pest; Aptive, Pestco, Bug-N-A-Rug also in the cluster. | Strongest market. Maps leader. Organic not uncontested. |
| **Surf City / Topsail corridor** | **Bug-N-A-Rug (Hampstead office) #1**, **B&T #2**, then Atlantic Mosquito & Wildlife, Riggs, Cape Fear Termite & Pest, Freedom Lawns, G’s, Tri-County. | Pest & Termite Consultants, Terminix, **B&T city page ~#3**, Pro-Con, Bug-N-A-Rug. | Maps presence is real. Organic is a dogfight with SEO factories. |
| **Sneads Ferry** | **G’s Pest Control #1**, **B&T #2**, Mosquito Authority, then Jacksonville spillover (Modern / Terminix / May / Dodson) plus Bug-N-A-Rug. | Massey, Pest & Termite Consultants, Aptive, **B&T ~#4**, Rid-A-Pest. | Maps top-3. Organic mid-pack. |
| **Hampstead** | **Bug-N-A-Rug #1**, Riggs, Tri-County, Cape Fear Termite & Pest, Canady & Son. **B&T not in the local Maps list.** | **B&T city page #1** in the web cluster, then Beach Pest Service, Rid-A-Pest, Pest & Termite Consultants, Bug-N-A-Rug. | Inverse of Holly Ridge: organic yes, Maps no (GBP gravity is Holly Ridge, not Hampstead). |
| **Jacksonville / Camp Lejeune** | **Modern Exterminating (627 College St) #1**, **Terminix (420 SR 1702) #2**, **May Exterminating (2701 Commerce Rd) #3**, Dodson (129 Old Bridge), Massey, Bug Off, Jones, All American. **B&T absent from this Maps set.** Termite Maps pack is the same in-town set. | Eastline, May, Modern, **B&T city page ~#4**, Dodson. Autocomplete brands: Jones, Dodson, Hawx, Aptive, May, Modern, Jarman — **not B&T**. | Organic present via city page. Maps is the hole. Brand-name demand accrues to Jacksonville incumbents. |
| **Wilmington / Wrightsville / Carolina Beach / Ogden / Porters Neck** | Wilmington Maps: local addresses matching **Aptive/Terminix-class chains (2111 Capital Dr)**, **Economy Exterminators (3135 Kitty Hawk / 910-790-2000)**, **Clegg’s**, **Canady & Son**, **Jay Taylor**, Allied-class listings. **B&T not in Wilmington Maps results.** | Clegg’s, Allied, Pest Authority, Healthy Home, Jay Taylor for “pest control Wilmington.” **B&T’s Wilmington city page did not appear in the first organic cluster.** Wrightsville: PTC, Clegg’s, Rid-A-Pest, **B&T ~#4**. Carolina Beach: Allied, PTC, Bug-N-A-Rug, Economy — **B&T absent**. Ogden: **B&T city page #1** (thin/programmatic SERP). Porters Neck: Beach Pest, Rid-A-Pest, **B&T ~#3**. | Wilmington is the weakest major market. Ogden/Porters Neck organic is a city-page play, not Maps. |
| **Swansboro / Cape Carteret / Newport / Hubert** | Swansboro Maps resolved to **Canady’s Termite & Pest Control, 105 Seth Thomas Ln #4, Swansboro**. Hubert/Cape Carteret not fully packed in this pass. | Swansboro organic: Eastline, PTC, Aptive, Rid-A-Pest, Terminix — **B&T not in first 5**. Cape Carteret: Eastline, Pro-Con, Rid-A-Pest, **B&T ~#4**, Bug-N-A-Rug. Newport: Eastline, Clegg’s, Rid-A-Pest, **B&T ~#4**. Hubert: **B&T city page #1**, then Aptive, Terminix, Jacksonville Pest Pros, Bug-N-A-Rug. | Eastline is the Crystal Coast organic specialist. B&T wins Hubert (closer to Onslow) and is mid-pack on Cape Carteret/Newport. |
| **Richlands / Piney Green / Verona** | Not fully packed (rural). Jacksonville incumbents and Jones Pest (Richlands PO Box / Maple Hill) are the likely Maps set. | Richlands: Jones Pest, Alphin, Jarman’s — **B&T not in first cluster**. Piney Green: Pro-Con / Ward / Bedingfield spam + **B&T Jacksonville page, not `/pest-control-piney-green`**. Verona: **B&T city page #1** (almost no local competitors in the index). | Small-town organic is binary: unique local (Jones/Alphin) or B&T template page. Piney Green dedicated URL is underperforming vs Jacksonville page. |
| **Burgaw / Rocky Point** | Not packed in this pass; Pender locals (Manning’s, Cape Fear, Bug-N-A-Rug) expected. | Burgaw: PTC, Manning’s, Bug-N-A-Rug, Pro-Con, Jay Taylor — **B&T absent from first 5** despite having `/pest-control-burgaw`. Rocky Point: Aptive, Pestco, **B&T ~#3**, Mosquito Joe, Pro-Con. | Burgaw page is indexed but not winning. Rocky Point is competitive-but-present. |
| **Topsail Beach** | Same Topsail/Hampstead Maps set as Surf City. | **B&T `/pest-control-topsail-nc` #1**, Riggs, Pestco, Bug-N-A-Rug, Cape Fear. | Strong organic on a dedicated Topsail URL. |

### Maps vs organic, by service

| Intent | Who ranks | B&T |
|---|---|---|
| **General pest control + city** | Mix of true locals + **city-page mills** (Aptive, Rid-A-Pest, Bug-N-A-Rug, PTC, Pro-Con, Ward, Massey, Terminix). | City landing pages (`/pest-control-{city}`) — **not the homepage** — when B&T ranks at all. |
| **Exterminator Jacksonville** | May homepage, Modern homepage, **B&T Jacksonville page ~#3**, Eastline. | City page, not a dedicated “exterminator” URL. |
| **Termite control / treatment / company / inspection** | Jacksonville: **May termite page, Jones termite page, Eastline, PTC**; B&T Jacksonville **city page** (termite is a section, not `/services/termite-control`). Wilmington autocomplete points at Clegg’s, Canady, Diamond, Aptive, Dodson. | Site **has** `/services/termite-control` and even `/services/termite-control/ogden-nc`. Those URLs **did not surface** on Jacksonville/Wilmington termite queries in this sample. |
| **WDIR / wood-destroying insect report** | **May WDI page, Modern WDIR page, Eastline WDIR page, NCDA memo, Riggs WDI page** (Jax). Wilmington: **PTC WDI-100, Canady & Son WDIR, NCDA, realtor explainers**. | `/services/wood-destroying-insect-report` exists (H1: “WDIR in Jacksonville, North Carolina”) and **did not appear** in WDIR SERPs. This is a high-intent VA/real-estate query B&T is built to serve and is currently **losing to Jacksonville specialists**. |
| **Bed bug** | May, Modern, Terminix, Rid-A-Pest; B&T Jacksonville city page (heat-treatment section). | `/services/bed-bug-treatment` did not take the slot; city page did. |
| **Mosquito (Surf City)** | **Town of Surf City / Pender County Vector Control #1**, Riggs mosquito page, Kiefer/Rent-to-Kill, Schultz, Bug-N-A-Rug. | **Absent.** Municipal spray is the SERP feature. Private demand is owned by mosquito specialists, not B&T’s city page. |
| **Fire ant Jacksonville** | Terminix, D&D, Eastline, Freedom Lawns, May ant page. | **Absent.** |
| **Rodent Wilmington** | Clegg’s rodent page, Massey, PTC, Port City Pest, Jay Taylor. | **Absent.** `/services/rodent-control` did not rank. |
| **German roach Wilmington** | Healthy Home (strong specialty content), Emergency Pest Team, NCSU Extension, Bug-N-A-Rug blog, Jay Taylor. | **Absent** despite `/services/german-cockroach-control`. |
| **Wildlife Jacksonville** | **Wildlife specialists, not PMPs:** Jacksonville Pest Pros, Critter Control, Ecocentric, NC Wildlife agent finder. Autocomplete goes to **animal control**, not B&T. | `/services/wildlife-control` did not rank. This query class is a different SERP (licensed WCO vs pest control). |
| **Commercial Wilmington** | Wilkey, Healthy Home commercial, Jay Taylor commercial, PTC commercial, Clegg’s. | **Absent.** No commercial-specific URL observed ranking. |
| **Crawl space moisture Wilmington** | **Crawl-space contractors, not PMPs:** Crawl Space Ninja, Elite Moisture, Carolina Duct & Crawl, cost-guide sites. | `/services/crawl-space-moisture-control` did not rank in Wilmington. Different competitive set (encapsulation vs pest). |
| **Near me / Holly Ridge** | Autocomplete for “pest control holly ridge nc” suggests **“buggin out pest control holly ridge nc”** (competitor brand) before generic “in my area.” | Brand is not the default suggest. |

---

## Autocomplete / PAA-style demand (discovered)

Google Suggest (`suggestqueries.google.com`, 2026-08-23) — valuable extra phrases beyond the brief:

**Jacksonville**
- pest control jacksonville nc **prices**
- **jones** pest control jacksonville nc
- **dodson** pest control jacksonville nc
- **hawx** pest control jacksonville nc
- **aptive** pest control jacksonville nc
- **may** pest control jacksonville nc
- **modern** pest control jacksonville nc
- **best** pest control jacksonville nc
- **jarman** pest control jacksonville nc
- termite **inspection** jacksonville nc (not just “control”)
- wdir jacksonville nc (also hurricane PAA noise)

**Wilmington**
- pest control wilmington nc **reviews**
- **rodent** control wilmington nc
- **termite** control wilmington nc
- aptive / dodson / **canady** / **diamond** / **clegg’s** / allied / **ridd** pest control wilmington nc
- termite **companies** wilmington nc
- termite treatment **what to expect** / **how is it done** / **how much**

**Holly Ridge / Surf City / Hampstead**
- **buggin out** pest control holly ridge nc (brand competitor in suggest)
- **tri county** pest control hampstead nc
- mosquito control surf city → **how much does mosquito control cost**, mosquito control near me / ideas
- “are there sharks in surf city nc” (noise; low pest suggest volume)

**Wildlife / WDIR**
- wildlife control jacksonville → **animal control**, **wildlife removal**, **critter control**, **onslow animal control**
- wood destroying insect report nc → **nc wood destroying insect report** (state-form language)

**Implication:** Jacksonville brand demand is already allocated to Jones / Dodson / May / Modern / Hawx / Aptive. B&T is not a suggest entity there. Wilmington suggest is Clegg’s / Canady / Diamond / Aptive. Holly Ridge suggest includes a competing local brand (“Buggin Out”).

PAA was not extractable from the JS-walled Google SERP. Suggest is the substitute.

---

## Organic pattern: service pages vs homepages vs city pages

| Who | What ranks |
|---|---|
| **B&T** | Almost always a **city landing page** (`/pest-control-jacksonville`, `/pest-control-holly-ridge`, …). Homepage did not take local-intent queries. **Service URLs** (`/services/termite-control`, `/services/wood-destroying-insect-report`, `/services/wildlife-control`, `/services/rodent-control`, `/services/german-cockroach-control`, `/services/crawl-space-moisture-control`) **rarely if ever** appeared in this sample. Ogden is the exception: a more differentiated city page (`/pest-control-ogden`) plus nested `/services/.../ogden-nc` URLs exist; the Ogden city page **did** rank #1 for “pest control Ogden NC.” |
| **May, Modern, Clegg’s, Jay Taylor, Allied, Healthy Home, Eastline, Jones** | **Homepages and real service pages** (termite, WDIR, bed bug, rodent, commercial). |
| **Aptive, Rid-A-Pest, Bug-N-A-Rug, Pest & Termite Consultants, Pro-Con, Ward, Massey, Terminix, Mosquito Joe** | **Programmatic location URLs** for every town in the brief. They occupy SERP slots even when they have no office in that town. |

Directories that appeared: `pestcontrolreviews.com` (B&T Holly Ridge profile), BBB (Modern), Porch/Birdeye (Jones/Alphin Richlands). Yelp HTML was bot-blocked. Reddit/forums: none found.

---

## Technical SEO notes on B&T (from page source, 2026-08-23)

Inspected saved HTML plus live fetches of city/service URLs.

### Stack and tracking
- Drupal 10 / Sprowt theme; CallTrackingMetrics (`462929.tctm.co`); Meta Pixel `1126336218230620`; duplicate Google Search Console meta (`BCk4C1mm7Vp-x_5F61Uw3EZNS8KkViAbHpxNauxc8jw` appears twice).

### Titles — keyword stuffing + near-duplicates
Most city titles follow one template, often **well past 70 characters**, stuffing every money term:

> `Pest Control in {City}, NC | Save $100 on Bed Bug and Termite Exterminations | B&T Pest Control | Termite Control, Termite Inspection, Bed Bug Treatment, Bed Bug Exterminator, Mosquito Control Near Me, Rodent Control, Exterminator Near Me`

Observed on Holly Ridge, Surf City, Hampstead, Sneads Ferry, Swansboro, Hubert, Cape Carteret, Newport, Porters Neck, Rocky Point, Verona, Burgaw, Carolina Beach, Wrightsville Beach, Topsail, Richlands, etc.

**Ogden is the only clearly rewritten city title:**  
`Guaranteed Pest Control in Ogden, NC | B&T Pest Control | …` plus FAQPage schema.

Piney Green title has a typo/spacing issue: `Pest Control in Piney Green , NC | …` (space before comma).

Service titles are offer-led, not query-led, e.g. `Better Than Liquid Alone | 3-Way Termite Protection…`, `Kill Bed Bugs in 1 Day…`, `Save $250 on Crawl Space Encapsulation | Eastern NC | B&T`.

### H1s
City H1s rotate “Pest Exterminators in {City}, NC” vs “Pest Control in {City}, NC” — inconsistent. Service H1s are generic (“Our Termite Control Services”) except WDIR (`WDIR in Jacksonville, North Carolina`) which **geo-locks a territory-wide service page to Jacksonville**.

Ogden nested termite H1 is truncated/broken in source: `Termite Control in Ogden,`.

### Schema
On sampled pages:

- `Product` + `AggregateRating` (4.9 / 285) — **Product-for-a-company is a known rich-result footgun**.
- `LocalBusiness` + `PostalAddress` (Holly Ridge HQ) **copied onto every city page** — does not create unique GBP entities for Wilmington/Jacksonville.
- BreadcrumbList (itemprop).
- Some service/Ogden pages add `FAQPage`.
- **No `PestControlService` / `Service` + `areaServed` per city** observed in the snippets reviewed.

### Thin / templated city pages
Word counts on city URLs are not “empty” (~1,900–3,100 words) but **highly templated**: same PestGuard $45/mo offer, same $100/$250 coupons, same service list, city name swapped. Burgaw exists in the index and **still lost** the Burgaw SERP — template + no local proof (office, reviews-by-city, unique photos, realtor WDIR proof) is not enough against Manning’s / PTC / Bug-N-A-Rug.

**Sitemap vs live:** live city URLs exist for Wrightsville Beach and Burgaw even if emphasis in the crawl list was Onslow/Pender/New Hanover cores. Piney Green has a dedicated URL that **lost to the Jacksonville page** on “pest control Piney Green NC.”

### Nested Ogden service URLs
`/services/{service}/ogden-nc` exists for bed bug, termite, mosquito, rodent, wildlife, crawl space. That pattern was **not replicated** for Jacksonville, Wilmington, Surf City, or Holly Ridge — so the only “service + city” landing pages in the sitemap cluster around Ogden, a small Wilmington suburb, while the money markets use one fat city page.

---

## Competitive set (who to treat as the real SERP)

**Onslow / Jacksonville**
- Modern Exterminating (1952, 627 College St) — Maps #1
- May Exterminating (2701 Commerce Rd) — Maps #3, owns termite/WDIR/bed-bug **service URLs**
- Dodson Bros. (129 Old Bridge St) — Maps + brand suggest
- Terminix Jacksonville (420 SR 1702) — Maps #2
- Eastline Pest Management — organic/WDIR/military-family messaging
- Jones Pest Control (Richlands / Maple Hill) — brand suggest + Richlands organic
- Massey, All American, Bug Off, Jarman, Hawx, Aptive

**Topsail / Holly Ridge / Hampstead / Sneads Ferry**
- **Bug-N-A-Rug** (19618 US-17, Hampstead) — Maps #1 Surf City & Hampstead
- **G’s Pest Control** — Maps #1 Sneads Ferry
- Riggs Moisture, Termite & Pest — Holly Ridge organic #1, mosquito Surf City
- Tri-County / Cape Fear Termite & Pest / Pestco
- Mosquito Authority, Atlantic Mosquito & Wildlife, Freedom Lawns (lawn+pest adjacency)

**Wilmington / beaches**
- Clegg’s, Jay Taylor (since 1941), Allied (Carolina Beach office), Canady & Son, Healthy Home, Economy Exterminators, Pest Authority, Port City Pest, Wilkey (commercial)

**Crystal Coast**
- Eastline, Canady’s (Swansboro GBP), Clegg’s Newport pages

**SERP clutter (every town)**
- Aptive, Rid-A-Pest, Pest & Termite Consultants, Pro-Con, Ward, Massey, Terminix location microsites

---

## Implications for B&T (visibility only; not a full strategy doc)

1. **GBP / Maps is the Jacksonville and Wilmington problem, not “more city pages.”** B&T already has city URLs. Jacksonville Maps is Modern/Terminix/May. Wilmington Maps is Clegg’s/Jay Taylor/Canady/Economy/chains. Hampstead Maps is Bug-N-A-Rug despite B&T ranking organically.
2. **Service-intent organic is being left on the table.** Termite, WDIR, German roach, rodent, wildlife, crawl space, commercial, fire ant, and Surf City mosquito queries are won by **dedicated service URLs or specialists**. B&T’s service pages exist and are not the ranking URL.
3. **WDIR is a military/real-estate money query in Jacksonville and B&T is invisible** against May, Modern, and Eastline.
4. **City-title stuffing and Product schema** are technical debt; Ogden’s differentiated page is the internal proof that unique copy ranks (Ogden #1 vs Burgaw miss).
5. **Do not confuse programmatic competitors with local operators.** Aptive/Rid-A-Pest/PTC will keep occupying organic slots; Maps is where true locals (including B&T in Holly Ridge) still win.

See CSV for the observation log.
