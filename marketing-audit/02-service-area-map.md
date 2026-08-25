# B&T Pest Control — Service area map

**Date observed:** 2026-08-23  
**Primary sources:** [Areas We Service](https://www.btpestcontrol.com/areas-we-service), site header/footer county nav, sitemap (`https://www.btpestcontrol.com/sitemap.xml`), city-page HTML, service-page “areas we service” lists.

Confidence: **High** for cities listed in the official areas directory and header. **Medium** for extra towns named only on individual service pages.

---

## Headquarters and operating footprint

| Item | Value | Source |
| --- | --- | --- |
| Office | 1276 NC 172, Holly Ridge, NC 28445 | Footer / contact / Google Maps CID `15308633390670589428` |
| Counties named in site nav | **Onslow, Pender, New Hanover, Carteret** | Header “Areas We Service” |
| Positioning | Family-owned Eastern / coastal NC company since 1982 | About Us, homepage |
| Same-day claim | “same-day services to residents in our same-day service area” | Areas We Service page — **the same-day radius is not defined** |

Holly Ridge sits between Jacksonville / Camp Lejeune and the Topsail–Wilmington beach corridor. That is a real geographic advantage: one plant can cover Onslow military housing **and** Pender/New Hanover beach rentals. Marketing currently underuses that “between the base and the beach” story.

---

## Official city list (Areas We Service directory)

Extracted from live HTML of `/areas-we-service` on 2026-08-23. Twenty-five places are listed.

| City / community | County | Dedicated URL | In XML sitemap? | Notes |
| --- | --- | --- | --- | --- |
| Burgaw | Pender | `/pest-control-burgaw` | **No** | Live page exists; orphaned from sitemap |
| Cape Carteret | Carteret | `/pest-control-cape-carteret` | Yes | |
| Carolina Beach | New Hanover | `/pest-control-carolina-beach` | Yes | |
| Cedar Point | Carteret | **No URL** (`/node/60` unlinked) | No | Listed, **no public city page** |
| Half Moon | Onslow | `/pest-control-half-moon` | Yes | Census-designated place next to Jacksonville |
| Hampstead | Pender | `/pest-control-hampstead` | Yes | Fast-growth corridor |
| Holly Ridge | Onslow | `/pest-control-holly-ridge` | Yes | HQ market |
| Hubert | Onslow | `/pest-control-hubert` | Yes | |
| Jacksonville | Onslow | `/pest-control-jacksonville` | Yes | Largest demand city |
| Kure Beach | New Hanover | **No URL** (`/node/59`) | No | Listed, **no public city page** |
| Maple Hill | Pender | `/pest-control-maple-hill` | **No** | Live page; not in sitemap |
| Maysville | Jones | **No URL** (`/node/49`) | No | Listed; Jones County is **not** in the header county list |
| Newport | Carteret | `/pest-control-newport` | Yes | |
| North Topsail Beach | Onslow | **No URL** (`/node/46`) | No | High-value beach; **no city page** |
| Piney Green | Onslow | `/pest-control-piney-green` | Yes | |
| Porters Neck | New Hanover | `/pest-control-porters-neck` | Yes | Affluent Wilmington suburb |
| Richlands | Onslow | `/pest-control-richlands` | Yes | |
| Rocky Point | Pender | `/pest-control-rocky-point` | Yes | |
| Sneads Ferry | Onslow | `/pest-control-sneads-ferry` | Yes | MARSOC / growth |
| Surf City | Pender | `/pest-control-surf-city` | Yes | Core beach market |
| Swansboro | Onslow | `/pest-control-swansboro` | Yes | |
| Topsail Beach | Pender | `/pest-control-topsail-nc` | Yes | |
| Verona | Onslow | `/pest-control-verona` | Yes | |
| Wilmington | New Hanover | `/pest-control-wilmington` | Yes | Largest metro in footprint |
| Wrightsville Beach | New Hanover | `/pest-control-wrightsville-beach` | **No** | Live page; not in sitemap |

**Count:** 25 named markets, 21 with public city URLs, 4 directory listings with **no indexable city page**, 3 live city pages **missing from sitemap**.

Ogden is in the header under New Hanover and has `/pest-control-ogden` (in sitemap) but is **not** in the 25-name areas directory. Treat Ogden as a 26th marketed city.

---

## Markets named on service pages but not in the official directory

These appear on crawl-space / wildlife / German-roach style “areas” lists. Treat as **claimed or aspirational**, not as confirmed routed cities, until operations confirms.

| Place | Where it appeared | Dedicated page? |
| --- | --- | --- |
| Camp Lejeune / military housing | Competitor pages + B&T Jacksonville copy alludes to military; not a named city card | No |
| Cape Carteret vs Cape Carteret spelling | Directory uses Cape Carteret | Yes |
| Burgaw spelled “Burgaw” on some service-area blurbs | Crawl-space page | Burgaw page exists |
| Carolina Beach | Crawl-space list as “Carolina Beach” | Yes as Carolina Beach |
| Cedar Point | Directory only | No |
| Half Moon spelled “Half Moon” | Crawl-space list | Half Moon page exists |
| Hampstead spelled “Hampstead” | Crawl-space list | Hampstead page exists |
| Kure Beach spelled “Kure Beach” | Crawl-space list | No |
| Maple Hill | Crawl-space list | Maple Hill page exists |
| Maysville spelled “Maysville” | Crawl-space list | No |
| North Topsail Beach spelled “North Topsail Beach” | Crawl-space list | No |
| Richlands spelled “Richlands” | Crawl-space list | Richlands page exists |
| Rocky Point spelled “Rocky Point” | Crawl-space list | Rocky Point page exists |
| Sneads Ferry spelled “Sneads Ferry” | Crawl-space list | Sneads Ferry page exists |
| Surf City spelled “Surf City” | Crawl-space list | Surf City page exists |
| Swansboro spelled “Swansboro” | Crawl-space list | Swansboro page exists |
| Topsail Beach spelled “Topsail Beach” | Crawl-space list | Yes |
| Wrightsville Beach spelled “Wrightsville Beach” | Crawl-space list | Wrightsville Beach page exists |

Inconsistent spelling (Burgaw/Burgaw, Sneads/Sneads, Surf/Surf, Kure/Kure, Maysville/Maysville, Half Moon/Half Moon, Hampstead/Hampstead, North Topsail/North Topsail) is a **NAP/content quality issue**. Google does not need every variant, but internally this looks like templated copy that was never copy-edited.

---

## Counties vs cities — gaps

Header counties: Onslow, Pender, New Hanover, Carteret.

| County | Cities with pages | Obvious gaps |
| --- | --- | --- |
| Onslow | Jacksonville, Holly Ridge, Hubert, Half Moon, Piney Green, Richlands, Sneads Ferry, Swansboro, Verona, North Topsail Beach (listed only) | **Camp Lejeune, Midway Park, Pumpkin Center, Dixon, Stella** — high military/PCS demand, no pages |
| Pender | Surf City, Topsail Beach, Hampstead, Burgaw, Rocky Point, Maple Hill | **Scotts Hill** (growth), **Atkinson** |
| New Hanover | Wilmington, Wrightsville Beach, Carolina Beach, Porters Neck, Ogden; Kure Beach listed only | **Castle Hayne, Myrtle Grove, Masonboro, Figure Eight** (affluent) |
| Carteret | Cape Carteret, Newport; Cedar Point listed only | **Swansboro is Onslow**; **Morehead City, Emerald Isle, Cedar Point page missing, Peletier, Bogue** — May Exterminating and Orkin New Bern already sell these |
| Jones (not in header) | Maysville listed only | Either add Jones County to the claim or stop listing Maysville |

---

## Demand vs content strength (qualitative)

| Priority | Market | Why it matters | B&T content today |
| --- | --- | --- | --- |
| 1 | Jacksonville | Largest population + Camp Lejeune PCS / WDIR | City page exists; thinner than Eastline / May / Modern local-authority pages |
| 2 | Wilmington | Largest metro; heavy competitor density | Stronger city page (home+yard $45 story) |
| 3 | Surf City / Topsail / N. Topsail | Vacation rentals, beach houses, fire ants, mosquitoes | Surf City + Topsail pages; **North Topsail Beach has no page** |
| 4 | Hampstead / Scotts Hill | Fast residential growth between JAX and ILM | Hampstead page only |
| 5 | Sneads Ferry | MARSOC growth | Page exists |
| 6 | Wrightsville / Carolina / Kure | Premium coastal | Wrightsville + Carolina pages; **Kure Beach no page** |
| 7 | Swansboro / Cape Carteret / Newport | Carteret overlap with May, Orkin, Mosquito Authority | Pages exist; likely weak in Maps vs Jacksonville-based brands |
| 8 | Burgaw / Rocky Point / Maple Hill | Lower search volume | Pages exist; Burgaw/Maple Hill not in sitemap |

---

## Competitive implication

B&T’s **claimed** territory is a four-county coastal strip. B&T’s **indexed** territory is 21 city URLs plus Ogden.

Competitors attacking the same strip:

- **Onslow-first:** Modern Exterminating, May Exterminating, Eastline Pest Management, Jones Pest Control, Rid-A-Pest, Mosquito Authority Jacksonville, Orkin New Bern
- **Wilmington-first expanding north:** Healthy Home, Port City Pest, Cape Fear Termite & Pest, Diamond Pest Pro, Pest & Termite Consultants, Aptive, Hawx, Massey, Orkin Wilmington, Terminix
- **Specialists:** Mosquito Joe / Mosquito Authority (mosquito SKU), Bug Out (moisture + insulation), Riggs (Hampstead moisture/termite)

B&T is one of the few locals that honestly straddles **both** Jacksonville and Wilmington. Most competitors are headquartered in one metro and “also serve” the other. That is a positioning asset if city pages, GBP, and ads stop sounding like a generic Eastern NC template.

---

## Recommended location-page build order

1. **North Topsail Beach** — already in the directory; no URL  
2. **Kure Beach** — already in the directory; no URL  
3. **Cedar Point** — already in the directory; no URL  
4. **Camp Lejeune / military / PCS / WDIR** — not a city, but a high-intent landing page  
5. **Maysville** — only if Jones County is truly serviced  
6. Add Burgaw, Maple Hill, Wrightsville Beach to **sitemap**  
7. Decide whether Morehead City / Emerald Isle are in-radius (May already owns that story)

Do **not** mass-produce 40 thin city pages. The four missing directory cities plus a Camp Lejeune/WDIR page will close the most obvious holes.
