-- Control Center (PRD "מרכז הבקרה" v2, section 6). Shares the organisation
-- tenant with the PT module; every table carries organization_id and most
-- carry workspace_id (the permission boundary, PRD section 2).

create table if not exists workspaces (
  id               text primary key,
  organization_id  text not null,
  name             text not null,
  kind             text not null default 'personal',   -- personal | client | work
  created_at       timestamptz not null default now(),
  data             jsonb not null default '{}'::jsonb
);

create table if not exists workspace_members (
  id               text primary key,
  organization_id  text not null,
  workspace_id     text not null references workspaces(id) on delete cascade,
  user_id          text not null,
  role             text not null default 'viewer',      -- admin | editor | viewer
  created_at       timestamptz not null default now(),
  data             jsonb not null default '{}'::jsonb,
  unique (workspace_id, user_id)
);

create table if not exists cc_projects (
  id               text primary key,
  organization_id  text not null,
  workspace_id     text not null references workspaces(id) on delete cascade,
  name             text not null,
  owner            text not null default '',
  importance       text not null default 'normal',      -- critical | high | normal | low
  status           text not null default 'active',      -- active | archived
  environment      text not null default 'unclassified',
  created_at       timestamptz not null default now(),
  data             jsonb not null default '{}'::jsonb   -- description, budget_usd, default_key_id
);

-- A provider account the workspace is allowed to read (PRD section 4).
create table if not exists connections (
  id               text primary key,
  organization_id  text not null,
  workspace_id     text not null references workspaces(id) on delete cascade,
  provider         text not null,                       -- github | vercel | supabase | n8n | reporter
  account_label    text not null default '',
  status           text not null default 'new',         -- ok | partial | rate_limited | reauth | disconnected | new
  last_sync_at     timestamptz,
  last_attempt_at  timestamptz,
  last_error       text not null default '',
  created_at       timestamptz not null default now(),
  data             jsonb not null default '{}'::jsonb   -- capabilities, scope (allowlist), secret_enc, cursor
);

-- Provider keys for AI usage (PRD 9.2). The real key is encrypted in data.
create table if not exists provider_keys (
  id               text primary key,
  organization_id  text not null,
  workspace_id     text not null references workspaces(id) on delete cascade,
  name             text not null,
  provider         text not null,                       -- anthropic | openai | other
  account_label    text not null default '',
  masked           text not null default '',
  scope            text not null default 'model_calls',
  created_at       timestamptz not null default now(),
  data             jsonb not null default '{}'::jsonb
);

create table if not exists assets (
  id                text primary key,
  organization_id   text not null,
  workspace_id      text not null references workspaces(id) on delete cascade,
  connection_id     text references connections(id) on delete set null,
  external_id       text not null,
  kind              text not null,                      -- repo | vercel_project | supabase_project | workflow | service | bot
  name              text not null,
  provider          text not null,
  environment       text not null default 'unclassified',
  state             text not null default '',
  url               text not null default '',
  description       text not null default '',
  last_seen_at      timestamptz,
  source_updated_at timestamptz,
  removed_at        timestamptz,
  created_at        timestamptz not null default now(),
  data              jsonb not null default '{}'::jsonb,
  unique (workspace_id, provider, kind, external_id)
);

create table if not exists project_assets (
  id               text primary key,
  organization_id  text not null,
  project_id       text not null references cc_projects(id) on delete cascade,
  asset_id         text not null references assets(id) on delete cascade,
  source           text not null default 'manual',      -- manual | auto | suggested
  created_at       timestamptz not null default now(),
  data             jsonb not null default '{}'::jsonb,
  unique (project_id, asset_id)
);

create table if not exists work_sessions (
  id               text primary key,
  organization_id  text not null,
  workspace_id     text not null references workspaces(id) on delete cascade,
  project_id       text not null references cc_projects(id) on delete cascade,
  title            text not null,
  goal             text not null default '',
  owner            text not null default '',
  tool             text not null default 'manual',      -- manual | claude_code | codex | other
  status           text not null default 'open',        -- open | waiting | done | cancelled
  external_id      text,
  started_at       timestamptz not null default now(),
  ended_at         timestamptz,
  created_at       timestamptz not null default now(),
  data             jsonb not null default '{}'::jsonb   -- outcome, links[], follow_up
);

create table if not exists activity_events (
  id               text primary key,
  organization_id  text not null,
  workspace_id     text not null references workspaces(id) on delete cascade,
  connection_id    text references connections(id) on delete set null,
  asset_id         text references assets(id) on delete set null,
  project_id       text references cc_projects(id) on delete set null,
  session_id       text references work_sessions(id) on delete set null,
  external_id      text not null,
  kind             text not null,                       -- deployment | workflow_run | pull_request | execution | heartbeat | session
  result           text not null default 'unknown',     -- success | failure | running | cancelled | unknown
  environment      text not null default 'unclassified',
  title            text not null default '',
  url              text not null default '',
  occurred_at      timestamptz not null,
  ingested_at      timestamptz not null default now(),
  created_at       timestamptz not null default now(),
  data             jsonb not null default '{}'::jsonb,
  unique (workspace_id, connection_id, external_id)
);

create table if not exists inbox_items (
  id                     text primary key,
  organization_id        text not null,
  workspace_id           text not null references workspaces(id) on delete cascade,
  asset_id               text references assets(id) on delete cascade,
  kind                   text not null,                 -- new_asset | mismatch | duplicate | missing_source
  status                 text not null default 'open',  -- open | resolved | dismissed
  suggested_project_id   text,
  reason                 text not null default '',
  created_at             timestamptz not null default now(),
  data                   jsonb not null default '{}'::jsonb
);

create table if not exists cost_entries (
  id               text primary key,
  organization_id  text not null,
  workspace_id     text not null references workspaces(id) on delete cascade,
  project_id       text references cc_projects(id) on delete set null,
  provider         text not null,
  kind             text not null,                       -- reported | usage | estimate | allocation | subscription
  amount           numeric(14,4) not null default 0,
  currency         text not null default 'USD',
  period_start     date,
  period_end       date,
  created_at       timestamptz not null default now(),
  data             jsonb not null default '{}'::jsonb   -- tokens_in, tokens_out, source, key_id, run_id, note
);

create table if not exists cc_agents (
  id               text primary key,
  organization_id  text not null,
  workspace_id     text not null references workspaces(id) on delete cascade,
  project_id       text references cc_projects(id) on delete cascade,  -- null = general agent
  name             text not null,
  owner            text not null default '',
  provider         text not null default 'anthropic',
  model            text not null default 'claude-opus-5-5',
  key_id           text,
  enabled          boolean not null default true,
  version          integer not null default 1,
  created_at       timestamptz not null default now(),
  data             jsonb not null default '{}'::jsonb   -- instructions, tools[], allowed_projects[], limits{}, approval_rule
);

create table if not exists agent_runs (
  id               text primary key,
  organization_id  text not null,
  workspace_id     text not null references workspaces(id) on delete cascade,
  agent_id         text not null references cc_agents(id) on delete cascade,
  project_id       text not null references cc_projects(id) on delete cascade,
  session_id       text references work_sessions(id) on delete set null,
  status           text not null default 'queued',      -- queued | running | awaiting_approval | completed | failed | cancelled
  started_at       timestamptz,
  finished_at      timestamptz,
  created_at       timestamptz not null default now(),
  data             jsonb not null default '{}'::jsonb   -- config_version, steps[], result, usage{}, cost, error, idempotency_key
);

create table if not exists alerts (
  id               text primary key,
  organization_id  text not null,
  workspace_id     text not null references workspaces(id) on delete cascade,
  kind             text not null,                       -- failure | repeated_failure | sync_delay | permission | budget
  target_kind      text not null default '',
  target_id        text not null default '',
  status           text not null default 'open',        -- open | acknowledged | snoozed
  message          text not null default '',
  created_at       timestamptz not null default now(),
  data             jsonb not null default '{}'::jsonb
);

create index if not exists idx_ws_org              on workspaces(organization_id);
create index if not exists idx_cc_projects_ws      on cc_projects(organization_id, workspace_id);
create index if not exists idx_connections_ws      on connections(organization_id, workspace_id);
create index if not exists idx_assets_ws           on assets(organization_id, workspace_id);
create index if not exists idx_project_assets_p    on project_assets(organization_id, project_id);
create index if not exists idx_sessions_project    on work_sessions(organization_id, project_id);
create index if not exists idx_events_ws_time      on activity_events(organization_id, workspace_id, occurred_at desc);
create index if not exists idx_events_asset        on activity_events(asset_id);
create index if not exists idx_inbox_ws            on inbox_items(organization_id, workspace_id, status);
create index if not exists idx_costs_project       on cost_entries(organization_id, project_id);
create index if not exists idx_agent_runs_project  on agent_runs(organization_id, project_id);

do $$
declare t text;
begin
  for t in
    select unnest(array['workspaces','workspace_members','cc_projects','connections','provider_keys',
      'assets','project_assets','work_sessions','activity_events','inbox_items','cost_entries',
      'cc_agents','agent_runs','alerts'])
  loop
    execute format('alter table %I enable row level security', t);
  end loop;
end $$;
