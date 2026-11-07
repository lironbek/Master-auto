-- Usage metering per client (PRD 9.3 "שימוש AI" extended to any metered API:
-- model calls, OCR pages, WhatsApp/Telegram messages and recipients), reported by
-- the integrations that make the calls (n8n, bots, apps) through the workspace
-- reporter token, plus the agent runs made by this system.

create table if not exists clients (
  id               text primary key,
  organization_id  text not null,
  workspace_id     text not null references workspaces(id) on delete cascade,
  name             text not null,
  external_ref     text not null default '',      -- CRM id / customer number
  created_at       timestamptz not null default now(),
  data             jsonb not null default '{}'::jsonb,   -- notes, contact, source
  unique (workspace_id, name)
);

create table if not exists usage_entries (
  id               text primary key,
  organization_id  text not null,
  workspace_id     text not null references workspaces(id) on delete cascade,
  project_id       text references cc_projects(id) on delete set null,
  client_id        text references clients(id) on delete set null,
  provider         text not null,                 -- claude | gemini | openai | ocr | whatsapp | telegram | other
  metric           text not null,                 -- requests | tokens_in | tokens_out | tokens_cached | messages | recipients | pages | characters | minutes | units
  quantity         numeric(18,4) not null default 0,
  unit             text not null default '',
  interface        text not null default '',      -- which integration made the calls: n8n/<workflow>, app name, bot, agent:<name>
  model            text not null default '',
  external_id      text,                          -- reporter's id for de-duplication
  occurred_at      timestamptz not null,
  period_start     date,
  created_at       timestamptz not null default now(),
  data             jsonb not null default '{}'::jsonb   -- source, key_id, run_id, meta
);

create unique index if not exists idx_usage_dedup on usage_entries (workspace_id, external_id) where external_id is not null;
create index if not exists idx_usage_ws_time    on usage_entries (organization_id, workspace_id, occurred_at desc);
create index if not exists idx_usage_client     on usage_entries (client_id);
create index if not exists idx_usage_project    on usage_entries (project_id);
create index if not exists idx_clients_ws       on clients (organization_id, workspace_id);

alter table clients enable row level security;
alter table usage_entries enable row level security;
