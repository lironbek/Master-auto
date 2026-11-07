-- Health scans per project (deterministic findings from the providers' metadata),
-- kept as rows so they can be compared over time. Asset profiles live in
-- cc_assets.data.profile; the project summary in cc_projects.data.profile_summary.

create table if not exists project_scans (
  id               text primary key,
  organization_id  text not null,
  workspace_id     text not null references workspaces(id) on delete cascade,
  project_id       text not null references cc_projects(id) on delete cascade,
  kind             text not null default 'health',       -- health | (future: code, security)
  status           text not null default 'completed',
  grade            text not null default '',             -- A | B | C
  created_at       timestamptz not null default now(),
  finished_at      timestamptz,
  data             jsonb not null default '{}'::jsonb    -- findings[], counts{}, summary{}, actor, assets
);

create index if not exists idx_project_scans_project on project_scans (organization_id, project_id, created_at desc);
alter table project_scans enable row level security;
