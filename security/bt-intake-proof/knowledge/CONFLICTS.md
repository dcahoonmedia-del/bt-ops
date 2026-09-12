# Conflicts called out (not silently chosen)

Newest explicit Daniel-approved rule wins. Phase C assignment limits are dated 2026-09-12. The Sept 11 architecture is newer than the Sept 10 files for design; it is not newer than the Phase C prompt for what this test may do.

| Topic | Older / conflicting text | Winner | Why |
| --- | --- | --- | --- |
| Recurring vs one-time first | Sept 6 Grok files said one-time first | Recurring first, then one-time | Owner rule in Operating Brief, Handoff (Sept 10), and Architecture new-lead flow (Sept 11) |
| WDIR price | Old $150 reference | **$225** for new quotes | Daniel explicit Sept 10; Architecture §10 repeats it. Refer already-approved older quotes to Daniel |
| Beulaville | Older bot list omitted it | Beulaville is served | Daniel explicit. Do not challenge that town |
| Website-only PestGuard copy | Public site “starting at $45/mo” without stating the common $150 initial | Researched standard offer **$150 initial, $45/month**; verify eligibility | Operating Brief / Handoff observed baseline; Architecture: PestGuard billing versus visit frequency explicit. Do not lead with cheaper Basic by default |
| “Bi-monthly” | Website/internal shorthand | Say **every other month** in customer copy | Owner clarification. Monthly billing is not monthly service |
| Diagnostic vs WDIR | Easy to conflate $75 and $225 | Diagnostic inspection $75 (credited to treatment) is **not** a WDIR. WDIR is $225 | Sept 10 documents; keep them separate |
| Flea re-entry | A Sept 10 draft said people/pets could stay inside | Do not invent chemical/re-entry instructions | Daniel corrected that draft. Architecture: never invent flea preparation. Not SENT, but the error must not repeat |
| Fieldwork matching on every case | Phase C (earlier 2026-09-12): no Fieldwork | **Read-only Fieldwork match/context in Phase D** | Later 2026-09-12 Phase D prompt. Still no Fieldwork writes. Phase C no-write/no-send rules remain |
| Live Fieldwork MCP OAuth | Phase D wanted live HQ reads | **Historical fixture PHASE-D-MATT-001 only tonight** | Daniel 2026-09-12: stop OAuth; use the Sept 10 audit Matt evidence. Live connectivity stays BLOCKED |
| FIELDWORK VERIFIED vs fixture | Earlier Phase D draft used FIELDWORK VERIFIED | **FIELDWORK_FIXTURE_VERIFIED** | Daniel 2026-09-12. Do not use LIVE_FIELDWORK_VERIFIED |
| One identifier match | Easy to treat email-or-phone-only as the customer | **ambiguous_match_needs_daniel** | Daniel 2026-09-12. Do not guess |
| Email sent vs booking | Sept 10 CoS sent mail at 1:07:33 before WO 172708 at 1:20:24 | **Pending/proposed write is not a verified booking** | Same audit sequence. Do not infer customer confirmation |
| Approval sends mail | Phase C: approval is recorded state only | **Phase E only: one version-bound contactus→daniel send after exact approval** | Later 2026-09-12 Phase E prompt. Phase C cases still do not send |
| After approval, send and verify | Architecture §7/§10: pilot approvals authorize the immediate reviewed send, then destination verify | **Phase C: recorded state only. Phase E: one bounded send of the exact approved internal packet, then independent verify** | Phase E prompt is newer for that one internal test. Sender API return is still not delivery proof |
| Independent Auditor | Architecture: hourly/daily independent audit task | **No Auditor in Phase C** | 2026-09-12 Phase C prompt. Do not add a second worker |
| Scheduling / Astra / LSA / CTM native | Architecture flows for scheduling, Astra exceptions, and later native channels | Out of this test | Phase C is contactus Gmail Case Manager draft + iPhone review only |
| Architecture vs implementation | Architecture §14: “No implementation authorized by this document” | Phase C prompt authorizes this slice only | Architecture remains the design reference; do not productize or cut over |
| Fourth baseline file | Two identical handoff uploads looked like four sources | Fourth file is **Proposed Architecture** (Sept 11) | Daniel: one handoff was sent twice by mistake |
| Historical named holds | Brief lists specific past customers and office holds | Not a live dispatch list | Owner note plus 2026-09-12 instruction: examples/evidence only |
| Grok worker/send delegation | Audit describes CoS → Written Leads send handoff | Do not recreate delegated send | Audit says REMOVE that handoff; Architecture agrees; Phase C does not send |

Unresolved (not silently filled): current size limits, Basic/Plus setup fees, exact access-notice policy, agreement cancellation language, live route roster.
