-- Findings from the Supabase advisors (performance: unindexed foreign keys;
-- security: mutable search_path on a trigger function).

-- Pin the trigger function's search_path so it cannot be hijacked by a
-- role-level setting.
alter function prevent_audit_mutation() set search_path = '';

-- Covering indexes for foreign keys used in joins/cascades.
create index if not exists idx_actions_run           on actions(run_id);
create index if not exists idx_approvals_run         on approvals(run_id);
create index if not exists idx_assets_project        on assets(project_id);
create index if not exists idx_authorizations_proj   on authorizations(project_id);
create index if not exists idx_evidence_project      on evidence(project_id);
create index if not exists idx_finding_events_f      on finding_events(finding_id);
create index if not exists idx_findings_project      on findings(project_id);
create index if not exists idx_findings_run_fk       on findings(run_id);
create index if not exists idx_hypotheses_run        on hypotheses(run_id);
create index if not exists idx_report_versions_proj  on report_versions(project_id);
create index if not exists idx_report_versions_run   on report_versions(run_id);
create index if not exists idx_retests_finding       on retests(finding_id);
create index if not exists idx_scan_runs_project     on scan_runs(project_id);
create index if not exists idx_scan_runs_scope       on scan_runs(scope_version_id);
create index if not exists idx_test_account_refs_p   on test_account_refs(project_id);
create index if not exists idx_users_org             on users(organization_id);

create index if not exists idx_activity_events_conn  on activity_events(connection_id);
create index if not exists idx_activity_events_proj  on activity_events(project_id);
create index if not exists idx_activity_events_sess  on activity_events(session_id);
create index if not exists idx_agent_runs_agent      on agent_runs(agent_id);
create index if not exists idx_agent_runs_proj_fk    on agent_runs(project_id);
create index if not exists idx_agent_runs_session    on agent_runs(session_id);
create index if not exists idx_agent_runs_ws         on agent_runs(workspace_id);
create index if not exists idx_alerts_ws             on alerts(workspace_id);
create index if not exists idx_cc_agents_project     on cc_agents(project_id);
create index if not exists idx_cc_agents_ws          on cc_agents(workspace_id);
create index if not exists idx_cc_assets_conn        on cc_assets(connection_id);
create index if not exists idx_cc_projects_ws_fk     on cc_projects(workspace_id);
create index if not exists idx_connections_ws_fk     on connections(workspace_id);
create index if not exists idx_cost_entries_proj     on cost_entries(project_id);
create index if not exists idx_cost_entries_ws       on cost_entries(workspace_id);
create index if not exists idx_inbox_asset           on inbox_items(asset_id);
create index if not exists idx_inbox_ws_fk           on inbox_items(workspace_id);
create index if not exists idx_project_assets_asset  on project_assets(asset_id);
create index if not exists idx_provider_keys_ws      on provider_keys(workspace_id);
create index if not exists idx_work_sessions_proj    on work_sessions(project_id);
create index if not exists idx_work_sessions_ws      on work_sessions(workspace_id);
