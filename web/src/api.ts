// Thin API client. All calls go to /api/* (dev proxy or Vercel rewrite).

const TOKEN_KEY = 'pt.token'

export function getToken(): string | null {
  try { return localStorage.getItem(TOKEN_KEY) } catch { return null }
}
export function setToken(t: string | null) {
  try { t ? localStorage.setItem(TOKEN_KEY, t) : localStorage.removeItem(TOKEN_KEY) } catch { /* ignore */ }
}

// Called when the server rejects the session (401). AuthProvider installs a
// handler that clears the logged-in user so protected routes go back to /login.
let onUnauthorized: () => void = () => {}
export function setUnauthorizedHandler(fn: () => void) { onUnauthorized = fn }

export class ApiError extends Error {
  status: number
  detail: unknown
  constructor(status: number, detail: unknown) {
    super(typeof detail === 'string' ? detail : JSON.stringify(detail))
    this.status = status
    this.detail = detail
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json' }
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  const token = getToken()
  if (token) headers.Authorization = `Bearer ${token}`
  const res = await fetch(`/api${path}`, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) })
  const text = await res.text()
  let data: unknown = null
  try { data = text ? JSON.parse(text) : null } catch { data = text }
  if (!res.ok) {
    if (res.status === 401 && !path.startsWith('/auth/login') && !path.startsWith('/auth/register-org')) { setToken(null); onUnauthorized() }
    const detail = (data && typeof data === 'object' && 'detail' in (data as Record<string, unknown>))
      ? (data as Record<string, unknown>).detail : data
    throw new ApiError(res.status, detail)
  }
  return data as T
}

export const api = {
  get: <T>(p: string) => request<T>('GET', p),
  post: <T>(p: string, b?: unknown) => request<T>('POST', p, b ?? {}),
  patch: <T>(p: string, b: unknown) => request<T>('PATCH', p, b),
  del: <T>(p: string) => request<T>('DELETE', p),
}

// --- types (subset of the backend models) ---------------------------------
export type Role = 'org_admin' | 'survey_manager' | 'pt_tester' | 'developer' | 'executive' | 'auditor' | 'client'
export interface Me { organization: { id: string; name: string }; user: { id: string; email: string; display_name: string; role: Role } }
export interface Project { id: string; name: string; description: string; created_at: string }
export interface Authorization { id: string; project_id: string; approver_name: string; approver_authority: string; valid_from: string; valid_until: string; control_verified: boolean; document_reference: string }
export interface TargetSpec { scheme: string; host: string; ports: number[]; allowed_paths: string[] }
export interface Budget { max_duration_seconds: number; max_requests: number; requests_per_second: number; max_concurrency_per_host: number; max_response_bytes: number; max_model_cost_usd: number }
export interface ScopeVersion { id: string; project_id: string; version: number; status: 'draft' | 'approved' | 'superseded'; authorization_id: string; environment: string; targets: TargetSpec[]; allowed_modules: string[]; allowed_modes: string[]; budget: Budget; approved_by?: string; approved_at?: string; created_at: string }
export interface Run { id: string; project_id: string; scope_version_id: string; mode: string; status: 'created' | 'running' | 'paused' | 'stopped' | 'completed' | 'failed'; started_at?: string; stopped_at?: string; stop_reason: string; created_at: string; summary?: Record<string, number>; budget_used?: { requests: number; elapsed_seconds: number } }
export interface AuditEvent { id: string; run_id?: string; actor: string; action: string; decision: string; policy_version: string; detail: string; at: string }
export interface Action { id: string; run_id: string; target_host: string; module: string; risk: string; created_at: string }
export interface Finding { id: string; project_id: string; run_id: string; title: string; asset_path: string; category: string; severity: 'low' | 'medium' | 'high' | 'critical'; confidence: 'suspected' | 'verified' | 'needs_manual'; status: string; preconditions: string; evidence_ids: string[]; expected_result: string; actual_result: string; proven_impact: string; inferred_impact: string; reproduction: string; remediation: string; limitations: string; created_at: string }
export interface Evidence { id: string; project_id: string; finding_id?: string; kind: string; sensitivity: string; redacted_source: string; redacted_fingerprint: string; checksum: string; redaction_policy_version: string; captured_at: string; delete_at?: string }
export interface AccessLog { evidence_id: string; actor: string; action: string; at: string }
export interface Report { id: string; project_id: string; run_id: string; finding_ids: string[]; evidence_ids: string[]; format: string; content?: string; created_by: string; created_at: string }
export interface Dashboard { projects: number; runs: { total: number; by_status: Record<string, number> }; findings: { total: number; open: number; by_severity: Record<string, number> }; recent_runs: Run[]; recent_findings: Finding[]; recent_events: AuditEvent[]; storage: string }

// --- Control Center types ---------------------------------------------------
export interface Workspace { id: string; name: string; kind: string; created_at: string; report_token?: string; archived_at?: string | null; projects?: number; connections?: number; assets?: number }
export interface CcProject { id: string; workspace_id: string; name: string; description?: string; owner: string; importance: string; status: string; environment: string; budget_usd?: number; default_key_id?: string | null; client_id?: string | null; created_at: string; tone?: 'ok' | 'warn' | 'bad'; last_failure?: CcEvent | null; last_session?: WorkSession | null; asset_count?: number; providers?: string[]; last_activity_at?: string | null }
export interface CcClient { id: string; workspace_id: string; name: string; external_ref: string; notes?: string; created_at: string; projects?: { id: string; name: string }[] }
export interface UsageEntry { id: string; workspace_id: string; project_id?: string | null; client_id?: string | null; provider: string; metric: string; quantity: number | string; unit: string; interface: string; model: string; external_id?: string | null; occurred_at: string; client_name?: string; project_name?: string }
export type Metrics = Record<string, number>
export interface UsageReport { totals: Metrics; by_client: { client_id: string | null; client_name: string; metrics: Metrics; providers: Record<string, Metrics>; interfaces: Record<string, Metrics>; entries: number }[]; by_provider: { provider: string; metrics: Metrics; entries: number }[]; by_interface: { interface: string; provider: string; metrics: Metrics; entries: number }[]; by_project: { project_id: string | null; project_name: string; metrics: Metrics; entries: number }[]; entries_total: number; entries: UsageEntry[]; period: { from: string | null; to: string | null }; providers: string[]; metrics: string[] }
export interface Connection { id: string; workspace_id: string; provider: string; account_label: string; status: string; last_sync_at?: string | null; last_attempt_at?: string | null; last_error: string; secret_masked?: string; config?: Record<string, unknown>; capabilities?: string[]; coverage?: Record<string, string>; notes?: string[]; freshness?: { last_sync_at?: string | null; stale: boolean }; created_at: string }
export interface Asset { id: string; workspace_id: string; connection_id?: string | null; external_id: string; kind: string; name: string; provider: string; environment: string; state: string; url: string; description: string; last_seen_at?: string | null; source_updated_at?: string | null; removed_at?: string | null; meta?: Record<string, string>; project_ids?: string[]; link_source?: string; shared?: boolean; importance?: string }
export interface CcEvent { id: string; workspace_id: string; connection_id?: string | null; asset_id?: string | null; project_id?: string | null; session_id?: string | null; external_id: string; kind: string; result: string; environment: string; title: string; url: string; occurred_at: string; ingested_at: string; meta?: Record<string, string>; project_name?: string }
export interface WorkSession { id: string; workspace_id: string; project_id: string; title: string; goal: string; owner: string; tool: string; status: string; started_at: string; ended_at?: string | null; outcome?: string; links?: string[]; follow_up?: string; event_count?: number; last_activity_at?: string | null; idle?: boolean }
export interface InboxItem { id: string; workspace_id: string; asset_id?: string; kind: string; status: string; suggested_project_id?: string | null; reason: string; created_at: string; asset?: Asset | null }
export interface CostEntry { id: string; workspace_id: string; project_id?: string | null; provider: string; kind: string; amount: number | string; currency: string; period_start?: string | null; period_end?: string | null; note?: string; tokens_in?: number; tokens_out?: number; key_id?: string | null; run_id?: string; model?: string; created_at: string }
export interface ProviderKey { id: string; workspace_id: string; name: string; provider: string; account_label: string; masked: string; scope: string; version?: number; used_by_projects?: string[]; used_by_agents?: string[]; created_at: string }
export interface CcAgent { id: string; workspace_id: string; project_id?: string | null; name: string; instructions: string; owner: string; provider: string; model: string; key_id?: string | null; tools: string[]; allowed_projects: string[]; limits: Record<string, number>; approval_rule: string; enabled: boolean; version: number; created_at: string }
export interface AgentRun { id: string; workspace_id: string; agent_id: string; project_id: string; session_id?: string | null; status: string; started_at?: string | null; finished_at?: string | null; created_at: string; steps?: { tool: string; at: string; note: string }[]; result?: string; usage?: { input: number; output: number }; cost_usd?: number; error?: string; model?: string; agent_name?: string; requested_by?: string }
export interface Alert { id: string; workspace_id: string; kind: string; target_kind: string; target_id: string; status: string; message: string; created_at: string }
export interface ActivityDay { date: string; total: number; failures: number; deployments: number }
export interface OverviewStats { activity: ActivityDay[]; this_week: { events: number; deployments: number; failures: number }; prev_week: { events: number; deployments: number; failures: number }; usage_month: { messages: number; recipients: number; ai_requests: number }; usage_prev_month: { messages: number; recipients: number; ai_requests: number }; usage_by_provider: Record<string, number>; usage_daily: { date: string; messages: number; ai_requests: number }[]; assets_by_provider: Record<string, number> }
export interface Overview { projects: CcProject[]; assets_by_kind: Record<string, number>; assets_total: number; unassigned: number; open_sessions: WorkSession[]; critical_alerts: Alert[]; inbox_open: number; connections: Connection[]; recent_events: CcEvent[]; stats?: OverviewStats }
export interface AssetProfile { layout?: { role: string; path: string; evidence: string[]; entrypoints: string[]; note: string }[]; subprojects?: Record<string, { runtime: string; dependencies: string[]; scripts: Record<string, string>; integrations: string[] }>; vercel_json?: { framework: string; crons: string[]; rewrites: { source: string; destination: string }[] }; at?: string; error?: string; full_name?: string; default_branch?: string; visibility?: string; archived?: boolean; pushed_at?: string; size_kb?: number; open_issues?: number; license?: string; description?: string; languages?: Record<string, number>; files?: number; top_level?: Record<string, number>; manifests?: string[]; workflows?: string[]; has_tests?: boolean; has_readme?: boolean; env_files_committed?: string[]; migrations?: number; dependencies?: Record<string, string>; scripts?: Record<string, string>; framework?: string; runtime?: string; integrations?: string[]; readme_excerpt?: string; name?: string; node_version?: string; root_directory?: string; linked_repo?: string; production_branch?: string; crons?: string[]; protection?: string; env_names?: string[]; env_plain_secret_like?: string[]; domains?: string[]; last_production?: { state: string; at: string; url: string; branch: string }; region?: string; status?: string; postgres_version?: string; tables?: { name: string; rls: boolean; rows: number }[]; policies?: number | null; tables_error?: string }
export interface ArchRun { asset_id: string; name: string; domains: string[]; branch: string; last_production?: { state: string; at: string; url: string; branch: string } | null; env_names: string[]; services: string[] }
export interface ArchNode { id: string; role: string; label: string; repo: string; repo_asset_id?: string | null; path: string; note: string; entrypoints: string[]; evidence: string[]; runtime: string; scripts: Record<string, string>; integrations: string[]; runs_at: ArchRun[]; talks_to?: string[]; asset_id?: string; tables?: { name: string; rls: boolean; rows: number }[] }
export interface Architecture { nodes: ArchNode[]; edges: { from: string; to: string; kind: string }[]; services: { name: string; used_by: string[] }[]; unlinked_vercel: { asset_id: string; name: string; domains: string[]; linked_repo: string }[]; repos_without_layout: string[] }
export interface ProfileSummary { text: string; languages: Record<string, number>; frameworks: string[]; integrations: string[]; repos: number; deployments: number; databases: number; tables: number; domains: string[]; tests_ratio: string; ci_ratio: string; architecture?: Architecture }
export interface ScanFinding { severity: 'high' | 'medium' | 'low' | 'info'; title: string; detail: string; fix: string; source: string; asset_id?: string; asset_name?: string; file?: string; line?: number | null }
export interface ProjectScan { id: string; project_id: string; kind: string; status: string; grade: string; created_at: string; finished_at?: string; actor?: string; findings?: ScanFinding[]; counts?: Record<string, number>; assets?: number; files?: number; model?: string; summary?: Partial<ProfileSummary> & { text?: string; errors?: string[] } }
export interface CcProjectDetail { project: CcProject & { profile_at?: string; last_scan_grade?: string; last_scan_at?: string; last_code_scan_grade?: string; last_code_scan_at?: string }; assets: Asset[]; events: CcEvent[]; sessions: WorkSession[]; costs: CostEntry[]; cost_month_usd: number; agents: CcAgent[]; runs: AgentRun[]; connections: Connection[]; keys: ProviderKey[]; pt_projects: Project[]; client?: CcClient | null; usage_month?: { totals: Metrics; by_provider: { provider: string; metrics: Metrics; entries: number }[]; by_interface: { interface: string; provider: string; metrics: Metrics; entries: number }[] }; profile?: { summary: ProfileSummary | null; at?: string | null; assets: { id: string; name: string; provider: string; kind: string; profile?: AssetProfile | null }[] }; scans?: ProjectScan[]; last_scan?: ProjectScan | null }
export const del = <T,>(p: string) => request<T>('DELETE', p)
export const patch = <T,>(p: string, b: unknown) => request<T>('PATCH', p, b)
