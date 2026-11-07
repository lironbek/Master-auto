-- Authentication: sessions and unique emails per organisation.
-- Password hashes live in users.data (scrypt); they never appear in the API.

create table if not exists sessions (
  id               text primary key,
  organization_id  text not null,
  user_id          text not null references users(id) on delete cascade,
  token_hash       text not null unique,
  expires_at       timestamptz not null,
  created_at       timestamptz not null default now(),
  data             jsonb not null default '{}'::jsonb
);

create unique index if not exists idx_users_email_unique on users(lower(email));
create index if not exists idx_sessions_user on sessions(user_id);
create index if not exists idx_sessions_expires on sessions(expires_at);
create index if not exists idx_memberships_user on memberships(organization_id, user_id);
create index if not exists idx_report_versions_project on report_versions(organization_id, project_id);

alter table sessions enable row level security;
