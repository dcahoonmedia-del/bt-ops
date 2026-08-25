# CallTrackingMetrics (CTM) Access Report - B&T Pest Control
**Date:** 2026-08-25  
**Auditor:** Autonomous Agent  
**Status:** ❌ BLOCKED - Login Required

## Access Status
**NO ACCESS** - Session expired, login wall encountered at `app.calltrackingmetrics.com`

## Blocker Details
- **URL Attempted:** `https://app.calltrackingmetrics.com/calls`
- **Redirect:** `https://app.calltrackingmetrics.com/login?redir=...`
- **Issue:** CTM session has expired. Login page displays with:
  - "Sign in with Google" option
  - Email/Password fields
  - Verified indicator (green checkmark)
- **Screenshot:** `screenshots/ctm-access-blocker.webp`
- **Time of Block:** 2026-08-25 11:22 AM UTC

## What Was Observed
1. Initial browser tabs showed CTM was previously open with a calls list visible
2. The calls list page displayed:
   - 2FA setup banner: "Multi-Factor Authentication is required for this account. Set up 2FA now."
   - Call records with caller names, phone numbers (PII visible)
   - Coalmarch tenant branding
   - B & T Pest Control account indicator
3. Session expired when attempting to navigate to Reports/Analytics section

## Data Collection Attempted
Per instructions, the goal was to collect READ-ONLY aggregate metrics for these periods:
- **A)** 2026-07-24 through 2026-08-22 (30d)
- **B)** 2026-05-24 through 2026-08-22 (90d)
- **C)** 2026-01-01 through 2026-08-22 (YTD)

### Metrics Target (Not Retrieved):
1. Total calls
2. Unique callers
3. Answered/missed/abandoned/voicemail/after-hours breakdown
4. Repeat vs first-time caller ratio
5. Source/channel/tracking number breakdown (by label, not phone numbers)
6. New vs existing customer distinction (if available)
7. Account timezone
8. Call definition (minimum duration threshold)
9. Alignment check with Coalmarch's reported 50 call-leads in 30d

## Compliance with Instructions
✅ **DID NOT** attempt to enter login credentials  
✅ **DID NOT** click "Set up 2FA"  
✅ **DID NOT** change any settings, classifications, tags, notes, assignments  
✅ **DID NOT** call, text, or email anyone  
✅ **DID NOT** play call recordings  
✅ **DID NOT** export call details with PII  
✅ **DID NOT** screenshot pages with caller names or phone numbers  
✅ **DID NOT** sign out  
✅ **DID** screenshot the login blocker (no PII present)  
✅ **DID** document the blocker in this file  
✅ **DID** stop when encountering the login wall as instructed  

## Next Steps Required
**Manual intervention needed:**  
Daniel or authorized user must log in to CTM to restore session access. Once authenticated, the data collection can proceed by navigating to:
- Reports or Analytics section (aggregate totals only)
- Dashboard with KPI tiles showing period-specific metrics
- Any report showing call volume, disposition, and source breakdowns without individual call details

## No Data Retrieved
- **Total calls:** Not available
- **Unique callers:** Not available
- **Call dispositions:** Not available
- **Source breakdown:** Not available
- **Timezone:** Not confirmed
- **Call definition:** Not confirmed
- **Repeat caller ratio:** Not available
- **Coalmarch alignment:** Cannot verify

## Files Created
- `screenshots/ctm-access-blocker.webp` - Login page screenshot (no PII)
- `_ctm-pass.md` - This report

---
**Agent stopped as instructed when login wall was encountered.**
