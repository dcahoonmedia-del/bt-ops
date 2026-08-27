# 02 — Google Search Console

**Property:** `https://www.btpestcontrol.com/`  
**Accessed:** 23 August 2026  
**UI export zip** was produced in-browser (`https___www.btpestcontrol.com_-Performance-on-Search-2026-08-23.zip`, ~23 KB). File was **not** successfully copied into `account-data/exports/` in this workspace (path mismatch). Treat numbers below as **UI + July email**. Re-export to lock CSVs.

**Do not request indexing.**

---

## Totals

| Range | Clicks | Impressions | CTR | Avg position |
| --- | ---: | ---: | ---: | ---: |
| 22 May 2026 – 21 Aug 2026 | 1,174 | 164,000 | 0.7% | 12.2 |
| 22 Apr 2025 – 21 Aug 2026 | 4,670 | 951,000 | 0.5% | 23.9 |
| July 2026 (GSC email) | 385 | 52,600 | — | — |

July email devices (clicks): mobile **300**, desktop **77**, tablet **8**. Country: US 368, UK 11, PH 1.

**Trend:** impressions huge vs clicks. Position 23.9 on the long window is **blog/query-tail**, not “the brand is #24.” Brand queries sit in the top of the query list.

---

## Query groups (long window — UI top)

| Group | Evidence |
| --- | --- |
| Brand | `b&t pest control` 614 c / 2,514 i; `b and t pest control` 138; `bt pest control` 83; `b & t pest control` 71 |
| General pest | `pest control near me` 45 c / 22,201 i (CTR terrible) |
| Wildlife/DIY | possum/opossum cluster: 133+52+48+38+36 clicks — **largest non-brand** |
| PestGuard | **Not in top 10** |
| Mosquito | **Not in top 10** |
| Fire ant | **Not in top 10** |
| Termite | Not in top 10 |
| WDIR/WDI | Not in top 10 (demand shows in **forms**, not GSC head) |
| German roach | Page-level: `/services/german-cockroach-control` 66 clicks |
| Bed bug | Not in top 10 |
| Rodent/flea/tick | Flea **page** 49 clicks; flea **signs** post 120 clicks |
| Crawl | Not in top 10 |
| Commercial / vacation rental | Not in top 10 |
| City modifiers | Jacksonville / Sneads Ferry / Holly Ridge **pages** in top pages |

---

## Geography in queries/pages

| Place | Signal |
| --- | --- |
| Jacksonville | `/pest-control-jacksonville` 89 clicks / 75,805 impr (long window) |
| Sneads Ferry | `/pest-control-sneads-ferry` 81 / 27,538 |
| Holly Ridge | `/pest-control-holly-ridge` 51 / 20,888 |
| Surf City / Topsail / Camp Lejeune / Wilmington / beaches | **Not in this top-10 page list** |

Phase 1 “Jacksonville organic weak” is **nuanced**: the city URL gets **impressions** (75k) and **modest clicks** (89). CTR/position problem, not zero demand.

---

## Pages

| Page | Clicks (long) | Role |
| --- | ---: | --- |
| `/blog/posts/possum-in-yard` | 1,798 | DIY magnet |
| `/?utm_source=GBP&utm_medium=organic&utm_campaign=gbp-holly-ridge` | 1,120 | **GBP as a search landing** |
| `/` | 638 | Brand/home |
| `/blog/posts/common-signs-fleas` | 120 | Info |
| Jacksonville / Sneads Ferry city | 89 / 81 | Local |
| German roach service | 66 | Commercial |
| Stinging insects blog | 66 | Info |
| Holly Ridge city | 51 | Local |
| Flea service | 49 | Commercial |

**Cannibalization:** homepage vs UTM’d homepage vs city pages all compete for brand. Possum post cannibalizes wildlife intent that is **not** a booked-service strategy.

High impression / low CTR: `pest control near me`, Jacksonville city (75k impr / 89 clicks), possum (266k impr).

---

## Indexing (UI)

- Indexed ~**83**; not indexed ~**52**  
- Sitemaps present  
- No manual actions / security issues noted  
- Core Web Vitals: not pulled this pass  

Phase 1 `/node/` and off-sitemap issues: **not re-crawled in GSC UI this pass**. Still open.

---

## vs Phase 1 SEO claims

| Claim | GSC verdict |
| --- | --- |
| Jacksonville weakness | **Impressions yes, clicks weak** — pack + CTR, not “no query” |
| Wilmington weakness | **No ILM page in top 10** — still weak / deprioritized |
| HQ/Topsail strength | Holly Ridge + Sneads Ferry URLs **do** click |
| Fire-ant page opportunity | **Not query-head**; still a **content** bet |
| Mosquito weakness | **Not query-head** |
| Lejeune/PCS/WDIR | **Not query-head**; **forms say otherwise** |
| Vacation rental | Unseen in head queries |
| Thin/overbuilt cities | Only a few city URLs earn clicks; rest unproven |
| Sitemap / node URLs | Unverified this pass |

---

## Business read

Organic search is **brand + GBP + a possum article**. It is **not** (yet) a mosquito/fire-ant/WDIR capture engine in GSC. Do not celebrate 951k impressions.
