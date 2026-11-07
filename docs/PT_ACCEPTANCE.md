# Acceptance-criteria coverage (PRD section 21)

Each criterion maps to tests in `tests/`.

| # | Criterion (summary) | Test(s) |
|---|---|---|
| 1 | Unapproved target blocked via redirect, DNS change, browser resource | `test_scope_validator.py::test_out_of_scope_blocked`, `test_redirect_revalidated`, `test_metadata_blocked`, `test_internal_ip_blocked`, `test_subdomain_not_implied`, `test_resolved_internal_address_refused`; `test_runner.py::test_make_fetch_blocks_offsite_redirect_and_follows_onsite` |
| 2 | No cross-organization read/approve of run, evidence or report | `test_vault.py::test_cross_org_access_denied`, `test_untrusted_and_api.py::test_api_cross_org_isolation` |
| 3 | Target content posing as a system instruction cannot change scope/policy | `test_untrusted_and_api.py::test_injection_detected_and_not_followed`, `test_runner.py::test_execute_run_persists_everything` (injection in a real response is logged, not followed); deleted evidence not viewable via old id: `test_vault.py::test_deleted_evidence_not_viewable_via_old_id` |
| 4 | Expired approval or changed material parameter prevents execution | `test_policy_engine.py::test_expired_approval_rejected`, `test_changed_parameters_void_approval`, `test_approval_bound_to_target_and_module` |
| 5 | A verified finding includes matching evidence | `test_findings_and_report.py::test_verified_requires_evidence` |
| 6 | Synthetic secret never appears raw in logs, prompts, reports, screenshots | `test_redaction.py` (all), `test_vault.py::test_stored_evidence_has_no_raw_secret` |
| 7 | Stop button cuts egress within the time target | `test_orchestrator_and_loop.py::test_stop_cuts_egress` |
| 8 | Module failure/timeout shown as "not completed", not "passed" | report never marks a failed module as passed: `reports/generator.py` + `test_empty_report_is_not_a_clean_bill` |
| 9 | Retest does not use an expired authorization | `test_policy_engine.py::test_expired_approval_rejected`, `test_orchestrator_and_loop.py::test_expired_authorization_stops_run` |
| 10 | No extra data-gathering once sufficient proof obtained | budget/stop gate in `agent/loop.py::step`; `test_budget_stops_run` |
| 11 | Policy-component failure blocks active tests | fail-closed: `test_policy_engine.py::test_fail_closed_when_no_rule_matches` |
| 12 | Report distinguishes proven impact, hypothesis, coverage limits | `test_findings_and_report.py::test_report_distinguishes_proven_and_inferred` |

Run them all:

```bash
python -m pytest -q
```
