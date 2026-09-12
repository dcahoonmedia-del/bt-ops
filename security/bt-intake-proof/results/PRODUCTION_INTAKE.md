# Production intake architecture (not live)

**Architecture/tests: PASS.**  
**Live broadening: not authorized.** Isolated marker harness remains on.

| Gate | Result |
| --- | --- |
| Production capture ignores subject/sender/thread age | PASS (unit) |
| New reply on old thread is a new event | PASS (unit) |
| Existing customer and office-owned stay visible | PASS (unit) |
| Classification failure pending, not dropped | PASS (unit) |
| Case decision is not a silent global rule | PASS (unit) |
| Explicit promote keeps version/provenance | PASS (unit) |
| Daniel override anytime | PASS (unit) |
| Live receiver still uses marker harness | PASS |
| Env cannot enable shadow_all | PASS |
| Real customer bodies still omitted on live store path | PASS |
| Shadow/real-customer processing activated | no |

See `knowledge/PRODUCTION_INTAKE.md`.
