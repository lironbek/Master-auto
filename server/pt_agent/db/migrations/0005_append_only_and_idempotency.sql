-- Append-only trails also refuse TRUNCATE (row triggers do not fire for it),
-- and the evidence access log gets the same protection as the audit log.
drop trigger if exists audit_events_no_truncate on audit_events;
create trigger audit_events_no_truncate
  before truncate on audit_events
  for each statement execute function prevent_audit_mutation();

drop trigger if exists evidence_access_log_no_update on evidence_access_log;
create trigger evidence_access_log_no_update
  before update or delete on evidence_access_log
  for each row execute function prevent_audit_mutation();

drop trigger if exists evidence_access_log_no_truncate on evidence_access_log;
create trigger evidence_access_log_no_truncate
  before truncate on evidence_access_log
  for each statement execute function prevent_audit_mutation();

-- Agent-run idempotency is enforced by the database, not only by a
-- read-then-insert in the API (two serverless instances can race).
create unique index if not exists idx_agent_runs_idempotency
  on agent_runs (agent_id, (data ->> 'idempotency_key'))
  where data ->> 'idempotency_key' is not null;
