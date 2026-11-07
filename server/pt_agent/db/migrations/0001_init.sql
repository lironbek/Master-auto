-- PT Agent — initial schema (PRD section 16).
-- Every business table carries organization_id so tenant isolation is enforced
-- in storage, not only in the UI (PRD section 3). Typed columns hold the keys
-- used for queries; the full record is kept in `data` (jsonb).
--
-- RLS is enabled on every table with NO policies. The owning backend role
-- (Neon owner / Supabase service role) bypasses RLS and enforces organization
-- ownership server-side on every request (acceptance criterion 2). Any other
-- role sees nothing until per-organization policies are added.

create table if not exists organizations (
  id          text primary key,
  name        text not null,
  created_at  timestamptz not null default now(),
  data        jsonb not null default '{}'::jsonb
);

create table if not exists users (
  id               text primary key,
  organization_id  text not null references organizations(id) on delete cascade,
  email            text not null,
  display_name     text not null default '',
  created_at       timestamptz not null default now(),
  data             jsonb not null default '{}'::jsonb
);

create table if not exists memberships (
  id               text primary key,
  organization_id  text not null references organizations(id) on delete cascade,
  user_id          text not null,
  role             text not null,
  created_at       timestamptz not null default now(),
  data             jsonb not null default '{}'::jsonb
);

create table if not exists projects (
  id               text primary key,
  organization_id  text not null,
  name             text not null,
  description      text not null default '',
  created_at       timestamptz not null default now(),
  data             jsonb not null default '{}'::jsonb
);

create table if not exists assets (
  id               text primary key,
  organization_id  text not null,
  project_id       text not null references projects(id) on delete cascade,
  label            text not null,
  created_at       timestamptz not null default now(),
  data             jsonb not null default '{}'::jsonb
);

create table if not exists authorizations (
  id               text primary key,
  organization_id  text not null,
  project_id       text not null references projects(id) on delete cascade,
  valid_from       timestamptz not null,
  valid_until      timestamptz not null,
  control_verified boolean not null default false,
  created_at       timestamptz not null default now(),
  data             jsonb not null default '{}'::jsonb
);

create table if not exists scope_versions (
  id               text primary key,
  organization_id  text not null,
  project_id       text not null references projects(id) on delete cascade,
  version          integer not null,
  status           text not null default 'draft',
  authorization_id text not null,
  environment      text not null default 'test',
  policy_version   text not null default 'policy-v1',
  approved_by      text,
  approved_at      timestamptz,
  created_at       timestamptz not null default now(),
  data             jsonb not null default '{}'::jsonb,
  unique (project_id, version)
);

create table if not exists test_account_refs (
  id               text primary key,
  organization_id  text not null,
  project_id       text not null references projects(id) on delete cascade,
  label            text not null,
  role_label       text not null,
  vault_ref        text not null default '',   -- opaque handle; never the credential
  created_at       timestamptz not null default now(),
  data             jsonb not null default '{}'::jsonb
);

create table if not exists scan_runs (
  id               text primary key,
  organization_id  text not null,
  project_id       text not null references projects(id) on delete cascade,
  scope_version_id text not null references scope_versions(id),
  mode             text not null,
  status           text not null default 'created',
  started_at       timestamptz,
  stopped_at       timestamptz,
  stop_reason      text not null default '',
  created_at       timestamptz not null default now(),
  data             jsonb not null default '{}'::jsonb
);

create table if not exists hypotheses (
  id               text primary key,
  organization_id  text not null,
  run_id           text not null references scan_runs(id) on delete cascade,
  resolved         boolean not null default false,
  created_at       timestamptz not null default now(),
  data             jsonb not null default '{}'::jsonb
);

create table if not exists actions (
  id               text primary key,
  organization_id  text not null,
  run_id           text not null references scan_runs(id) on delete cascade,
  scope_version_id text not null,
  policy_version   text not null,
  target_host      text not null,
  module           text not null,
  risk             text not null default 'read_only',
  approval_id      text,
  created_at       timestamptz not null default now(),
  data             jsonb not null default '{}'::jsonb
);

create table if not exists approvals (
  id                    text primary key,
  organization_id       text not null,
  run_id                text not null references scan_runs(id) on delete cascade,
  action_id             text not null,
  approver_user_id      text not null,
  target_host           text not null,
  module                text not null,
  valid_until           timestamptz not null,
  parameter_fingerprint text not null,
  revoked               boolean not null default false,
  created_at            timestamptz not null default now(),
  data                  jsonb not null default '{}'::jsonb
);

-- Evidence vault (PRD 10.1-10.4): only redacted content is ever stored.
create table if not exists evidence (
  id                        text primary key,
  organization_id           text not null,
  project_id                text not null references projects(id) on delete cascade,
  finding_id                text,
  kind                      text not null,
  sensitivity               text not null default 'high',
  redacted_source           text not null,
  redacted_fingerprint      text not null default '',   -- HMAC, never raw value
  checksum                  text not null default '',
  redaction_policy_version  text not null default 'redaction-v1',
  captured_at               timestamptz not null default now(),
  delete_at                 timestamptz,
  created_at                timestamptz not null default now(),
  data                      jsonb not null default '{}'::jsonb
);

create table if not exists evidence_access_log (
  id               bigserial primary key,
  organization_id  text not null,
  evidence_id      text not null,
  actor            text not null,
  action           text not null,      -- store | view | download | delete
  at               timestamptz not null default now()
);

create table if not exists findings (
  id               text primary key,
  organization_id  text not null,
  project_id       text not null references projects(id) on delete cascade,
  run_id           text not null references scan_runs(id) on delete cascade,
  title            text not null,
  asset_path       text not null,
  category         text not null default '',
  severity         text not null default 'medium',
  confidence       text not null default 'suspected',
  status           text not null default 'new',
  duplicate_of     text,
  created_at       timestamptz not null default now(),
  data             jsonb not null default '{}'::jsonb
);

create table if not exists finding_events (
  id               text primary key,
  organization_id  text not null,
  finding_id       text not null references findings(id) on delete cascade,
  actor            text not null,
  event            text not null,
  at               timestamptz not null default now(),
  data             jsonb not null default '{}'::jsonb
);

create table if not exists retests (
  id               text primary key,
  organization_id  text not null,
  finding_id       text not null references findings(id) on delete cascade,
  run_id           text,
  result           text not null default 'pending',
  created_at       timestamptz not null default now(),
  data             jsonb not null default '{}'::jsonb
);

create table if not exists report_versions (
  id               text primary key,
  organization_id  text not null,
  project_id       text not null references projects(id) on delete cascade,
  run_id           text not null references scan_runs(id) on delete cascade,
  finding_ids      jsonb not null default '[]'::jsonb,
  evidence_ids     jsonb not null default '[]'::jsonb,
  created_at       timestamptz not null default now(),
  data             jsonb not null default '{}'::jsonb
);

-- Audit log: append-only, never contains raw secrets (PRD section 19).
create table if not exists audit_events (
  id               text primary key,
  organization_id  text not null,
  run_id           text,
  actor            text not null,
  action           text not null,
  decision         text not null default '',
  policy_version   text not null default '',
  detail           text not null default '',
  at               timestamptz not null default now()
);

-- Indexes on the tenant key and the most common lookups.
create index if not exists idx_projects_org         on projects(organization_id);
create index if not exists idx_scope_versions_org   on scope_versions(organization_id, project_id);
create index if not exists idx_scan_runs_org        on scan_runs(organization_id, project_id);
create index if not exists idx_actions_run          on actions(organization_id, run_id);
create index if not exists idx_approvals_action     on approvals(organization_id, action_id);
create index if not exists idx_evidence_project     on evidence(organization_id, project_id);
create index if not exists idx_evidence_delete_at   on evidence(delete_at);
create index if not exists idx_findings_run         on findings(organization_id, run_id);
create index if not exists idx_audit_run            on audit_events(organization_id, run_id);

-- Row Level Security: enabled everywhere, no policies. Only the owning
-- backend role can read or write; RLS is not forced so the owner is not
-- locked out.
do $$
declare t text;
begin
  for t in
    select unnest(array[
      'organizations','users','memberships','projects','assets','authorizations',
      'scope_versions','test_account_refs','scan_runs','hypotheses','actions',
      'approvals','evidence','evidence_access_log','findings','finding_events',
      'retests','report_versions','audit_events'
    ])
  loop
    execute format('alter table %I enable row level security', t);
  end loop;
end $$;

-- Audit log is append-only even for the service role.
create or replace function prevent_audit_mutation() returns trigger as $$
begin
  raise exception 'audit_events is append-only';
end $$ language plpgsql;

drop trigger if exists audit_events_no_update on audit_events;
create trigger audit_events_no_update
  before update or delete on audit_events
  for each row execute function prevent_audit_mutation();
