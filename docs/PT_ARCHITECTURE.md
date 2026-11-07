# Architecture

Implements PRD section 15. Data flows one way through the governance gates; no
component may skip a gate.

```
                         proposes (untrusted)
   AI Planner  ───────────────────────────────►  Action (contract, section 7)
   (hypotheses)                                         │
                                                        ▼
                                              ┌───────────────────┐
                                              │   Policy Engine    │  binding decision
                                              │  (sections 7-8)    │  BLOCK / HALT /
                                              └─────────┬──────────┘  REQUIRE_APPROVAL / ALLOW
                                                        │ ALLOW only
                                                        ▼
                                              ┌───────────────────┐
                                              │   Tool Gateway     │  approved modules only
                                              │   (section 15)     │
                                              └─────────┬──────────┘
                                                        │
                                                        ▼
                                              ┌───────────────────┐
                                              │  Egress Validator  │  per-request scope +
                                              │  (section 9)       │  SSRF guard, redirects
                                              └─────────┬──────────┘
                                                        │ in-scope only
                                                        ▼
                                                    Target (test env)
                                                        │ response
                                                        ▼
                                              ┌───────────────────┐
                                              │  Redaction (mem)   │  before any store/log/model
                                              │  (section 10)      │
                                              └─────────┬──────────┘
                                                        ▼
                               Evidence Vault ──► Findings ──► Report Service
                               (section 10.1)    (section 12)  (section 13, frozen versions)
```

## Trust boundaries

- **Untrusted:** target content, files, tool results, and anything the model
  emits. An instruction found there is recorded as an observation and never
  executed (`pt_agent/agent/untrusted.py`, section 7).
- **Trusted facts:** derived server-side by the orchestrator and handed to the
  policy engine as `ActionFacts`. The engine never reads model output directly.
- **Secrets:** test-account credentials live in the Secrets Vault and are
  injected into tools, never passed to the model (section 7). Discovered
  secrets are redacted and fingerprinted; using them is blocked (section 8).

## Fail-closed defaults

| Failure | Behavior |
|---|---|
| No policy rule matches | `REQUIRE_APPROVAL` (never auto-allow) |
| Redaction cannot guarantee a clean artifact | store refused + alert (AC 6) |
| Target unparseable / not in scope | egress blocked (AC 1) |
| Authorization expired mid-run | run stopped, no new actions (section 18) |
| Budget limit reached | run stopped (section 5) |

## What is intentionally not here

Active exploitation modules. The Tool Gateway defines the interface
(`TestModule`); only passive/structural reference modules ship. Active modules
are added by an operator running under a verified test contract, so they are
out of scope for this governance-layer repository.
