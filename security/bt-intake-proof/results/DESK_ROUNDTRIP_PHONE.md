# ChatGPT iPhone acceptance script (Mac off)

This is **not** a PASS until Daniel actually does it. Gmail packets existing is not a phone PASS.

Prereq: live host must be running the round-trip revision (blocked on this agent until SSH deploy). Isolation stays on. Do not send customer mail.

1. Turn the Mac off. Use only the iPhone.
2. Open the B&T Lead Desk ChatGPT project. Ask: "What's the latest lead?"
3. ChatGPT should answer from the newest `BT-INTAKE-PROOF-DESK-CASE-E9A8` / queue mail, in plain language. It should not read case IDs, hashes, or nonces unless you ask.
4. Say: "Hold this one."
5. Wait for a new `BT-INTAKE-PROOF-DESK-RESULT-E9A8` mail, or a fresh case packet. ChatGPT should say it put the lead on hold.
6. Ask for a new draft: "Make it shorter." Confirm a new draft version in the next case packet (ChatGPT may not say the number).
7. If a Brenda/Ally case is showing, say it stays with Brenda or Ally. Confirm the next packet does not offer an AI send.
8. Do **not** approve a send until you have approved the exact `BT-DESK-ROUNDTRIP-SEND-E9A8` packet in `results/DESK_ROUNDTRIP.md`.
9. If ChatGPT shows a Gmail sent confirmation, that is the app. It does not mean the backend verified delivery.
