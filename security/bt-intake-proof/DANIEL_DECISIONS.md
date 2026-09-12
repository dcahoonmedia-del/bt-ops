# Phase C review surface (no public site)

I am using Gmail you already have. A case review lands in `daniel@btpestcontrol.com` so you can open it on iPhone Mail.

Reply to `contactus@` and keep the CASE=/DRAFT= marker:

- `BT-INTAKE-PROOF-CASE-APPROVE-E9A8`
- `BT-INTAKE-PROOF-CASE-CHANGES-E9A8`
- `BT-INTAKE-PROOF-CASE-NONE-E9A8`

Approval is recorded only. It will not send a customer message.

Phase E (internal B&T test only): approving the exact `BT-PHASE-E-SEND-E9A8-C4F1` packet authorizes one bounded contactus@ → daniel@ send of that version. A generic or stale approval will not send. Phase C cases still do not send.

I am **not** opening a public URL, adding a domain, or adding a paid auth product. Say if you want IAP on the VM later.

Phase F1 iPhone Lead Desk uses Gmail packets in `daniel@`, not a ChatGPT custom MCP. OpenAI's custom MCP apps are web-only. Ask ChatGPT to read the latest `BT-INTAKE-PROOF-DESK-*` emails. Those packets do not approve or send.

Production intake will capture every contactus@ inbound, then classify. The `BT-INTAKE-PROOF-*` filters stay on for isolated testing until you separately authorize shadow intake of all real contactus@ mail. Real-customer processing is off.

You can run the desk in ordinary speech. You do not need to remember case IDs or say a magic phrase. If you say "yeah, looks good" after I asked whether to send, that can mean send this version. If you change your mind in the same breath, the later instruction wins. I still will not send a stale or office-owned packet.
