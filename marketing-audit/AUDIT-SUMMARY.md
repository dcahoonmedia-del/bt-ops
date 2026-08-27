# B&T Pest Control — browser-session notes (partial)

**This is not the full audit.** Decision document: [`FINAL-MARKETING-AUDIT.md`](FINAL-MARKETING-AUDIT.md).

The “two phone numbers” item below is almost certainly **CallTrackingMetrics dynamic number insertion**: source HTML stores `910-329-1337`; some browser sessions swap in `910-356-9966`. Standardize reporting, don’t assume the site “forgot” the office number.

---

# Browser-based audit notes
**Date:** August 23, 2026  
**Research Method:** Browser-based audit (research-only, no customer interaction)  
**Evidence Location:** `/workspace/marketing-audit/evidence/browser/`

---

## EXECUTIVE SUMMARY

B&T Pest Control demonstrates strong online marketing fundamentals with an excellent 4.9-star rating (286 reviews), professional website design, and comprehensive service area coverage across 25 Eastern NC cities. The business has significant conversion optimization opportunities, particularly around phone number consistency, live engagement tools, and mobile CTA optimization.

---

## KEY METRICS

### Google Business Profile
- **Rating:** 4.9/5 stars ⭐⭐⭐⭐⭐
- **Review Count:** 286 reviews
- **Business Name:** B&T Pest Control, Inc
- **Primary Phone (GBP):** (910) 329-1337
- **Website Phone:** 910-356-9966 ⚠️ *Discrepancy noted*
- **Address:** 1276 NC-172, Holly Ridge, NC 28445
- **Hours:** M-F: 8AM-5PM, Sat-Sun: Closed
- **Owner Response Rate:** Active (responds within days)
- **Most Mentioned Attribute:** "Polite staff" (20 mentions)

### Website Performance
- **Domain:** btpestcontrol.com
- **Design Quality:** Professional, clean, mobile-responsive
- **Trust Signals:** ✅ 40+ years in business, NPMA certified, NC PMA member
- **Active Offers:** $75 off initial service, Refer-a-friend program
- **Review Display:** 4.9 stars prominently shown (website shows "285 reviews")

### Service Coverage
**25 Cities Served:**
Burgaw, Cape Carteret, Carolina Beach, Cedar Point, Half Moon, Hampstead, Holly Ridge, Hubert, Jacksonville, Kure Beach, Maple Hill, Maysville, Newport, North Topsail Beach, Piney Green, Porters Neck, Richlands, Rocky Point, Sneads Ferry, Surf City, Swansboro, Topsail Beach, Verona, Wilmington, Wrightsville Beach

---

## STRENGTHS

### Website
✅ **Clear Value Proposition:** "Protecting Eastern NC Homes from Pests Since 1982"  
✅ **Strong CTAs:** Multiple conversion points (phone, form, buttons)  
✅ **Professional Photography:** Branded truck, family imagery, professional headshots  
✅ **Trust Signals:** 40-year badge, satisfaction guarantee, certifications  
✅ **Social Proof:** Reviews integrated, Google rating badge in header  
✅ **Service Differentiation:** PestGuard plans, emergency callback service  
✅ **Content Marketing:** Blog with pest education articles  

### Google Business Profile
✅ **Excellent Rating:** 4.9/5 puts them in top tier  
✅ **High Review Volume:** 286 reviews shows consistent customer satisfaction  
✅ **Active Management:** Owner responds to reviews professionally  
✅ **Complete Information:** All fields filled out correctly  
✅ **Active Posts:** "$100 Off PestGuardPLUS" offer visible  
✅ **Customer Service Focus:** "Polite staff" most-mentioned attribute  

---

## CRITICAL ISSUES

### 🚨 Phone Number Inconsistency
- **Website displays:** 910-356-9966
- **GBP lists:** (910) 329-1337
- **Official contact (per user):** 910-329-1337
- **Impact:** Confusion, potential lost calls, tracking issues
- **Recommendation:** Standardize to ONE number OR implement call tracking with clear source attribution

### ⚠️ Missing Conversion Tools
1. **No Live Chat Widget** - Missing real-time engagement opportunity
2. **No Click-to-Text Button** - Despite SMS opt-in checkbox in form
3. **No Instant Quote Calculator** - Could reduce form friction
4. **Long Lead Form** - Many fields may reduce completion rate

### ⚠️ Navigation/UX Issues
- "MY ACCOUNT" button prominent but irrelevant to first-time visitors
- Could create confusion about whether account required for estimates

---

## OPPORTUNITIES

### Immediate (Quick Wins)
1. **Resolve phone number discrepancy** - Standardize across all platforms
2. **Add live chat widget** - Capture visitors outside business hours
3. **Add click-to-text CTA** - Mobile users prefer SMS
4. **A/B test shorter form** - Reduce fields to increase conversions
5. **Add mobile sticky phone bar** - Always-visible call button on mobile

### Medium-Term
6. **Pricing transparency** - Consider showing starting prices or ranges
7. **Video testimonials** - Add to review section for higher trust
8. **Before/after photos** - Visual proof of service quality
9. **FAQ schema markup** - Improve SERP features
10. **Service area pages** - Individual landing pages for each city

### Long-Term
11. **Competitor analysis** - Benchmark against local pest control companies
12. **PPC audit** - Optimize Google Ads spend and positioning
13. **Social media strategy** - Build consistent presence on identified channels
14. **Review generation system** - Systematize review requests post-service

---

## RESEARCH COMPLETED

### ✅ Captured & Documented:
- Homepage (full scroll, 16 screenshots)
- Areas We Service page (city list documented)
- Google Business Profile (overview + reviews)
- Rating, review count, owner responses
- Business hours, address, contact info
- Special offers, trust signals, certifications
- Website conversion elements and forms

### ⏸️ Not Completed (Time Constraints):
- Additional website pages (/services, /about, /packages, /contact)
- Competitor Maps local pack analysis
- Google Search SERP analysis
- Social media profiles (Facebook, Instagram, TikTok, YouTube)
- Review sites (Yelp, BBB, Angi)
- Mobile viewport testing
- Page speed analysis

---

## SCREENSHOT INVENTORY

**Total:** 19 screenshots saved to `/workspace/marketing-audit/evidence/browser/`

### Website (17 files):
1. `01-homepage-hero.webp` - Hero with family photo, headline, rating
2. `02-homepage-pest-selector.webp` - Interactive pest problem selector
3. `03-homepage-about-form.webp` - Company info + estimate request form
4. `04-homepage-trust-signals.webp` - 3 trust badges (price, guarantee, experience)
5. `05-homepage-truck-photo.webp` - Branded Nissan truck image
6. `06-homepage-service-cards-start.webp` - Service section header
7. `07-homepage-service-cards-full.webp` - 4 service cards (pest, termite, bed bug, WDIR)
8. `08-homepage-offers.webp` - $75 off + referral offer banners
9. `09-homepage-reviews-start.webp` - Reviews section header
10. `10-homepage-reviews.webp` - Customer review carousel
11. `11-homepage-blog-posts.webp` - Blog section start
12. `12-homepage-blog-full.webp` - 3 blog article cards
13. `13-homepage-service-area-start.webp` - Service area map section
14. `14-homepage-cities-list.webp` - All 25 cities listed
15. `15-homepage-certifications-footer.webp` - NPMA & NCPMA logos
16. `16-homepage-footer-full.webp` - Footer with nav, address, hours, social icons
17. `17-areas-we-service.webp` - Dedicated areas page with city list

### Google Business Profile (2 files):
18. `18-google-business-profile-overview.webp` - GBP main info tab
19. `19-google-business-profile-reviews.webp` - Reviews tab with ratings breakdown

---

## RECOMMENDATIONS PRIORITY

### 🔴 HIGH PRIORITY (Do Immediately):
1. Fix phone number inconsistency across website and GBP
2. Add live chat widget for after-hours engagement
3. Add mobile click-to-call sticky button
4. Test shorter lead form version (A/B test)

### 🟡 MEDIUM PRIORITY (Next 30 Days):
5. Add click-to-text SMS button
6. Implement video testimonials
7. Create city-specific landing pages
8. Add before/after service photos
9. Optimize "MY ACCOUNT" button visibility for first-time visitors

### 🟢 LOW PRIORITY (Next 90 Days):
10. Complete competitor Maps analysis
11. Audit social media presence and consistency
12. Review site presence (Yelp, BBB, Angi)
13. Implement review generation automation
14. Consider pricing transparency options

---

## DETAILED NOTES

Full audit notes with screenshots, observations, and technical details available at:
**`/workspace/marketing-audit/evidence/browser/browser-notes.md`**

---

**Audit Status:** Partial (core website and GBP completed; competitor analysis, social media, and review sites pending)  
**Next Steps:** Address high-priority issues, then complete competitor and social media analysis for full market positioning assessment.
