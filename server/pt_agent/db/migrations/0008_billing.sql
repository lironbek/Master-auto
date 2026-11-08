-- Billing & service module (docs/BILLING-MIGRATION-PLAN.md): the "מערכת ניהול
-- חיוב ושירות" that used to live in its own Lovable app + Supabase project, now
-- a module of the control center on the shared database. Every table carries
-- organization_id + workspace_id like the rest of the system; legacy_id keeps
-- the UUID from the old database so an import can be verified row by row.

create table if not exists bl_customers (
  id               text primary key,
  organization_id  text not null,
  workspace_id     text not null references workspaces(id) on delete cascade,
  client_id        text references clients(id) on delete set null,   -- same customer in usage metering
  name             text not null,
  email            text not null default '',
  phone            text not null default '',
  contact_person   text not null default '',
  address          text not null default '',
  status           text not null default 'active',          -- active | frozen | closed
  bill_hours       boolean not null default false,          -- add a "hours" line to the monthly charge
  hourly_rate      numeric(12,2),                           -- overrides the default rate
  legacy_id        text,
  created_at       timestamptz not null default now(),
  data             jsonb not null default '{}'::jsonb       -- notes, payment_method, vat_id
);

create table if not exists bl_products (
  id               text primary key,
  organization_id  text not null,
  workspace_id     text not null references workspaces(id) on delete cascade,
  project_id       text references cc_projects(id) on delete set null,   -- where the product's code/deploys live
  name             text not null,
  description      text not null default '',
  price            numeric(12,2) not null default 0,        -- per user per month
  has_light_user   boolean not null default false,
  light_user_price numeric(12,2) not null default 0,
  legacy_id        text,
  created_at       timestamptz not null default now(),
  data             jsonb not null default '{}'::jsonb
);

create table if not exists bl_services (
  id               text primary key,
  organization_id  text not null,
  workspace_id     text not null references workspaces(id) on delete cascade,
  description      text not null,
  price            numeric(12,2) not null default 0,
  recurring        boolean not null default false,
  legacy_id        text,
  created_at       timestamptz not null default now(),
  data             jsonb not null default '{}'::jsonb
);

-- What a customer pays for: product seats (kind=product) or a service (kind=service).
create table if not exists bl_subscriptions (
  id               text primary key,
  organization_id  text not null,
  workspace_id     text not null references workspaces(id) on delete cascade,
  customer_id      text not null references bl_customers(id) on delete cascade,
  kind             text not null default 'product',         -- product | service
  product_id       text references bl_products(id) on delete cascade,
  service_id       text references bl_services(id) on delete cascade,
  user_count       integer not null default 0,
  light_user_count integer not null default 0,
  quantity         numeric(12,2) not null default 1,
  valid_from       date not null default current_date,
  valid_until      date,
  legacy_id        text,
  created_at       timestamptz not null default now(),
  data             jsonb not null default '{}'::jsonb
);

create table if not exists bl_employees (
  id               text primary key,
  organization_id  text not null,
  workspace_id     text not null references workspaces(id) on delete cascade,
  user_id          text references users(id) on delete set null,   -- control-center login, if any
  name             text not null,
  email            text not null default '',
  phone            text not null default '',
  position         text not null default '',
  role             text not null default 'support',         -- admin | manager | support
  hourly_rate      numeric(12,2),
  active           boolean not null default true,
  legacy_id        text,
  created_at       timestamptz not null default now(),
  data             jsonb not null default '{}'::jsonb
);

create table if not exists bl_tickets (
  id               text primary key,
  organization_id  text not null,
  workspace_id     text not null references workspaces(id) on delete cascade,
  number           integer not null default 0,              -- SC-000123, per workspace
  customer_id      text not null references bl_customers(id) on delete cascade,
  product_id       text references bl_products(id) on delete set null,
  employee_id      text references bl_employees(id) on delete set null,
  title            text not null,
  description      text not null default '',
  status           text not null default 'open',            -- open | in_progress | resolved | closed
  priority         text not null default 'medium',          -- low | medium | high | critical
  contact_person   text not null default '',
  contact_phone    text not null default '',
  group_name       text not null default '',
  image_url        text not null default '',
  opened_at        timestamptz not null default now(),
  closed_at        timestamptz,
  legacy_id        text,
  created_at       timestamptz not null default now(),
  data             jsonb not null default '{}'::jsonb
);

create table if not exists bl_time_entries (
  id               text primary key,
  organization_id  text not null,
  workspace_id     text not null references workspaces(id) on delete cascade,
  ticket_id        text not null references bl_tickets(id) on delete cascade,
  employee_id      text references bl_employees(id) on delete set null,
  description      text not null default '',
  minutes          integer not null default 0,
  entry_date       date not null default current_date,
  billed_charge_id text,                                     -- set once the minutes were billed
  legacy_id        text,
  created_at       timestamptz not null default now(),
  data             jsonb not null default '{}'::jsonb
);

create table if not exists bl_external_updates (
  id               text primary key,
  organization_id  text not null,
  workspace_id     text not null references workspaces(id) on delete cascade,
  ticket_id        text not null references bl_tickets(id) on delete cascade,
  contact_name     text not null,
  contact_phone    text not null default '',
  content          text not null,
  minutes          integer,
  update_date      date not null default current_date,
  legacy_id        text,
  created_at       timestamptz not null default now(),
  data             jsonb not null default '{}'::jsonb
);

create table if not exists bl_charges (
  id               text primary key,
  organization_id  text not null,
  workspace_id     text not null references workspaces(id) on delete cascade,
  customer_id      text not null references bl_customers(id) on delete cascade,
  period           text not null,                           -- YYYY-MM
  status           text not null default 'draft',           -- draft | issued | paid | cancelled
  subtotal         numeric(12,2) not null default 0,
  vat_pct          numeric(5,2) not null default 0,
  vat              numeric(12,2) not null default 0,
  total            numeric(12,2) not null default 0,
  issued_at        timestamptz,
  paid_at          timestamptz,
  legacy_id        text,
  created_at       timestamptz not null default now(),
  data             jsonb not null default '{}'::jsonb,      -- notes, source, generated_at
  unique (workspace_id, customer_id, period)
);

create table if not exists bl_charge_lines (
  id               text primary key,
  organization_id  text not null,
  workspace_id     text not null references workspaces(id) on delete cascade,
  charge_id        text not null references bl_charges(id) on delete cascade,
  kind             text not null default 'manual',          -- product | light | service | hours | manual | usage
  ref_id           text,                                    -- product / service / subscription id
  description      text not null,
  quantity         numeric(12,2) not null default 1,
  unit_price       numeric(12,2) not null default 0,
  total            numeric(12,2) not null default 0,
  legacy_id        text,
  created_at       timestamptz not null default now(),
  data             jsonb not null default '{}'::jsonb
);

create table if not exists bl_expenses (
  id               text primary key,
  organization_id  text not null,
  workspace_id     text not null references workspaces(id) on delete cascade,
  name             text not null,
  amount           numeric(12,2) not null default 0,
  currency         text not null default 'ILS',
  rate_used        numeric(12,4) not null default 1,
  amount_ils       numeric(12,2) not null default 0,
  category         text not null default 'other',           -- software | database | staff | equipment | office | infra | other
  expense_date     date not null default current_date,
  description      text not null default '',
  recurring        boolean not null default false,
  legacy_id        text,
  created_at       timestamptz not null default now(),
  data             jsonb not null default '{}'::jsonb
);

create table if not exists bl_knowledge (
  id               text primary key,
  organization_id  text not null,
  workspace_id     text not null references workspaces(id) on delete cascade,
  product_id       text references bl_products(id) on delete set null,
  title            text not null,
  content          text not null default '',
  category         text not null default '',
  legacy_id        text,
  created_at       timestamptz not null default now(),
  data             jsonb not null default '{}'::jsonb       -- tags[]
);

create table if not exists bl_fx_rates (
  id               text primary key,
  organization_id  text not null,
  currency         text not null,                           -- USD | EUR
  rate_date        date not null,
  rate             numeric(12,4) not null,
  created_at       timestamptz not null default now(),
  data             jsonb not null default '{}'::jsonb,
  unique (organization_id, currency, rate_date)
);

create table if not exists bl_settings (
  id               text primary key,                        -- one row per workspace: "set_<ws>"
  organization_id  text not null,
  workspace_id     text not null references workspaces(id) on delete cascade,
  created_at       timestamptz not null default now(),
  data             jsonb not null default '{}'::jsonb,      -- vat_pct, hourly_rate, currency, ticket_prefix, business{name,address,vat_id}
  unique (workspace_id)
);

create index if not exists idx_bl_customers_ws on bl_customers (organization_id, workspace_id);
create index if not exists idx_bl_subs_customer on bl_subscriptions (customer_id);
create index if not exists idx_bl_tickets_ws on bl_tickets (organization_id, workspace_id, opened_at desc);
create index if not exists idx_bl_tickets_customer on bl_tickets (customer_id);
create index if not exists idx_bl_time_ticket on bl_time_entries (ticket_id);
create index if not exists idx_bl_time_date on bl_time_entries (organization_id, workspace_id, entry_date);
create index if not exists idx_bl_charges_customer on bl_charges (customer_id, period);
create index if not exists idx_bl_lines_charge on bl_charge_lines (charge_id);
create index if not exists idx_bl_expenses_date on bl_expenses (organization_id, workspace_id, expense_date desc);

alter table bl_customers enable row level security;
alter table bl_products enable row level security;
alter table bl_services enable row level security;
alter table bl_subscriptions enable row level security;
alter table bl_employees enable row level security;
alter table bl_tickets enable row level security;
alter table bl_time_entries enable row level security;
alter table bl_external_updates enable row level security;
alter table bl_charges enable row level security;
alter table bl_charge_lines enable row level security;
alter table bl_expenses enable row level security;
alter table bl_knowledge enable row level security;
alter table bl_fx_rates enable row level security;
alter table bl_settings enable row level security;
