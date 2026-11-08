// Types and Hebrew labels for the billing & service module (/billing API).

export interface BlCustomer { id: string; workspace_id: string; client_id?: string | null; name: string; email: string; phone: string; contact_person: string; address: string; status: string; bill_hours: boolean; hourly_rate?: number | string | null; notes?: string; payment_method?: string; vat_id?: string; created_at: string; users?: number; subscriptions?: number; open_tickets?: number; unpaid?: number }
export interface BlProduct { id: string; workspace_id: string; project_id?: string | null; name: string; description: string; price: number | string; has_light_user: boolean; light_user_price: number | string; features?: string[]; created_at: string; customers?: number; users?: number; light?: number }
export interface BlService { id: string; workspace_id: string; description: string; price: number | string; recurring: boolean; created_at: string }
export interface BlSubscription { id: string; workspace_id: string; customer_id: string; kind: 'product' | 'service'; product_id?: string | null; service_id?: string | null; user_count: number; light_user_count: number; quantity: number | string; valid_from: string; valid_until?: string | null; product_name?: string; service_name?: string; customer_name?: string }
export interface BlEmployee { id: string; workspace_id: string; user_id?: string | null; name: string; email: string; phone: string; position: string; role: string; hourly_rate?: number | string | null; active: boolean; created_at: string; user_email?: string; minutes_month?: number; open_tickets?: number }
export interface BlTicket { id: string; workspace_id: string; number: number; number_label?: string; customer_id: string; customer_name?: string; product_id?: string | null; product_name?: string; employee_id?: string | null; employee_name?: string; title: string; description: string; status: string; priority: string; contact_person: string; contact_phone: string; group_name: string; image_url: string; opened_at: string; closed_at?: string | null; minutes?: number; created_at: string }
export interface BlTimeEntry { id: string; ticket_id: string; employee_id?: string | null; employee_name?: string; description: string; minutes: number; entry_date: string; billed_charge_id?: string | null; created_at: string }
export interface BlExternalUpdate { id: string; ticket_id: string; contact_name: string; contact_phone: string; content: string; minutes?: number | null; update_date: string; created_at: string }
export interface BlCharge { id: string; workspace_id: string; customer_id: string; customer_name?: string; period: string; status: string; subtotal: number | string; vat_pct: number | string; vat: number | string; total: number | string; issued_at?: string | null; paid_at?: string | null; notes?: string; source?: string; lines?: number; created_at: string }
export interface BlChargeLine { id: string; charge_id: string; kind: string; ref_id?: string | null; description: string; quantity: number | string; unit_price: number | string; total: number | string }
export interface BlExpense { id: string; workspace_id: string; name: string; amount: number | string; currency: string; rate_used: number | string; rate_source?: string; amount_ils: number | string; category: string; expense_date: string; description: string; recurring: boolean; created_at: string }
export interface BlKnowledge { id: string; workspace_id: string; product_id?: string | null; product_name?: string; title: string; content: string; category: string; tags?: string[]; created_at: string }
export interface BlActivity { id: string; type: 'ticket' | 'time_entry' | 'external_update'; at: string; ticket_id: string; ticket_number?: number; title: string; customer_name: string; actor: string; detail: string; minutes?: number | null }
export interface BlSettings { vat_pct: number; hourly_rate: number; currency: string; ticket_prefix: string; business: { name?: string; address?: string; vat_id?: string; phone?: string; email?: string }; fx_defaults: Record<string, number> }
export interface BlOverview { months: string[]; revenue: number[]; paid: number[]; expenses: number[]; tickets_opened: number[]; hours: number[]; revenue_month: number; expenses_month: number; hours_month: number; open_tickets: number; unpaid_total: number; unpaid_count: number; customers: number; avg_resolution_minutes: number; users_by_product: { name: string; users: number }[]; recent: BlActivity[]; drafts: number }
export interface BlHoursReport { entries: { id: string; entry_date: string; ticket_id: string; ticket_number?: number; ticket_title: string; customer_id: string; customer_name: string; employee_name: string; minutes: number; description: string; billed: boolean }[]; total_minutes: number; total_hours: number; by_employee: { employee_name: string; minutes: number }[]; by_ticket: { ticket_id: string; ticket_number?: number; ticket_title: string; minutes: number }[]; customer_name: string }
export interface BlCustomerDetail { customer: BlCustomer; subscriptions: BlSubscription[]; tickets: BlTicket[]; charges: BlCharge[]; hours_month: number; usage_month?: { totals: Record<string, number>; by_provider: { provider: string; metrics: Record<string, number> }[] } | null }

export const ticketStatus: Record<string, string> = { open: 'פתוחה', in_progress: 'בטיפול', resolved: 'נפתרה', closed: 'סגורה' }
export const ticketStatusTone: Record<string, string> = { open: 'bg-sky-100 text-sky-800', in_progress: 'bg-amber-100 text-amber-800', resolved: 'bg-emerald-100 text-emerald-800', closed: 'bg-slate-200 text-slate-600' }
export const ticketPriority: Record<string, string> = { low: 'נמוכה', medium: 'בינונית', high: 'גבוהה', critical: 'קריטית' }
export const priorityTone: Record<string, string> = { low: 'bg-slate-100 text-slate-600', medium: 'bg-sky-100 text-sky-800', high: 'bg-orange-100 text-orange-800', critical: 'bg-rose-100 text-rose-800' }
export const customerStatus: Record<string, string> = { active: 'פעיל', frozen: 'מוקפא', closed: 'סגור' }
export const employeeRole: Record<string, string> = { admin: 'מנהל מערכת', manager: 'מנהל', support: 'תמיכה' }
export const chargeStatus: Record<string, string> = { draft: 'טיוטה', issued: 'הופק', paid: 'שולם', cancelled: 'בוטל' }
export const chargeTone: Record<string, string> = { draft: 'bg-slate-100 text-slate-700', issued: 'bg-amber-100 text-amber-800', paid: 'bg-emerald-100 text-emerald-800', cancelled: 'bg-rose-100 text-rose-800' }
export const lineKind: Record<string, string> = { product: 'משתמשים', light: 'משתמשי Light', service: 'שירות', hours: 'שעות טיפול', manual: 'ידני', usage: 'שימוש' }
export const expenseCategory: Record<string, string> = { software: 'תוכנה', database: 'דאטהבייס', staff: 'עובדים', equipment: 'ציוד', office: 'משרד', infra: 'תשתית', other: 'אחר' }
export const activityType: Record<string, string> = { ticket: 'קריאה נפתחה', time_entry: 'רישום זמן', external_update: 'עדכון מהלקוח' }

export function ils(n: number | string | undefined | null): string {
  const v = Number(n ?? 0)
  return new Intl.NumberFormat('he-IL', { style: 'currency', currency: 'ILS', maximumFractionDigits: 2 }).format(isNaN(v) ? 0 : v)
}
export function hhmm(minutes: number | null | undefined): string {
  const m = Math.max(0, Math.round(minutes ?? 0))
  return `${Math.floor(m / 60)}:${String(m % 60).padStart(2, '0')}`
}
export function periodLabel(period: string): string {
  const months = ['ינואר', 'פברואר', 'מרץ', 'אפריל', 'מאי', 'יוני', 'יולי', 'אוגוסט', 'ספטמבר', 'אוקטובר', 'נובמבר', 'דצמבר']
  const m = Number(period.slice(5, 7))
  return m >= 1 && m <= 12 ? `${months[m - 1]} ${period.slice(0, 4)}` : period
}
export function currentPeriod(): string { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}` }
export function today(): string { return new Date().toISOString().slice(0, 10) }
export function monthStart(): string { return `${currentPeriod()}-01` }
