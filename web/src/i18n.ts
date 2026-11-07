// Hebrew labels for controlled vocabularies (PRD sections 5, 8, 12).

export const runStatus: Record<string, string> = {
  created: 'נוצרה', running: 'רצה', paused: 'מושהית', stopped: 'נעצרה', completed: 'הושלמה', failed: 'נכשלה',
}
export const scopeStatus: Record<string, string> = { draft: 'טיוטה', approved: 'מאושר', superseded: 'הוחלף' }
export const severity: Record<string, string> = { low: 'נמוכה', medium: 'בינונית', high: 'גבוהה', critical: 'קריטית' }
export const confidence: Record<string, string> = { suspected: 'חשד', verified: 'מאומת', needs_manual: 'דורש אימות ידני' }
export const findingStatus: Record<string, string> = {
  new: 'חדש', in_review: 'בסקירה', approved: 'מאושר', in_progress: 'בטיפול', awaiting_retest: 'ממתין לבדיקה חוזרת',
  fixed: 'תוקן', accepted_risk: 'התקבל כסיכון', false_positive: 'תוצאת שווא',
}
export const findingTransitions: Record<string, string[]> = {
  new: ['in_review', 'false_positive'],
  in_review: ['approved', 'false_positive', 'new'],
  approved: ['in_progress', 'accepted_risk'],
  in_progress: ['awaiting_retest', 'accepted_risk'],
  awaiting_retest: ['fixed', 'in_progress'],
  fixed: [], accepted_risk: [], false_positive: [],
}
export const mode: Record<string, string> = { passive: 'סקירה פסיבית', active: 'אקטיבי מבוקר', authenticated: 'עם הזדהות', red_team: 'תרחיש צוות אדום' }
export const role: Record<string, string> = {
  org_admin: 'מנהל ארגון', survey_manager: 'מנהל סקר', pt_tester: 'בודק PT', developer: 'מפתח', executive: 'הנהלה', auditor: 'מבקר', client: 'לקוח',
}
export const decision: Record<string, string> = {
  allow: 'אושר', block: 'נחסם', require_approval: 'דורש אישור', halt: 'עצירה', ok: 'תקין', error: 'שגיאה', ignored_injection: 'הזרקה זוהתה והתעלמנו', blocked: 'נחסם',
  completed: 'הושלם', stopped: 'נעצר',
}
export const auditAction: Record<string, string> = {
  'project.create': 'פרויקט נוצר', 'authorization.create': 'מסמך הרשאה נוסף', 'scope.create': 'היקף נוצר', 'scope.approve': 'היקף אושר',
  'run.create': 'ריצה נוצרה', 'run.start': 'ריצה החלה', 'run.stop': 'ריצה נעצרה', 'run.finish': 'ריצה הסתיימה',
  hypothesis: 'השערה', policy: 'החלטת מדיניות', execute: 'ביצוע', observe: 'תצפית', 'finding.create': 'ממצא נוצר', 'finding.status': 'סטטוס ממצא שונה',
  'evidence.store_refused': 'שמירת ראיה סורבה', 'report.create': 'דוח הופק', 'report.refused': 'הפקת דוח סורבה',
  // control-center actions share the same audit log
  'cc.workspace.create': 'מרחב נוצר', 'cc.workspace.member': 'חבר מרחב עודכן', 'cc.workspace.report_token': 'טוקן דיווח חודש',
  'cc.project.create': 'פרויקט בקרה נוצר', 'cc.project.update': 'פרויקט בקרה עודכן', 'cc.project.link_pt': 'סקר אבטחה קושר לפרויקט',
  'cc.asset.assign': 'נכס שויך', 'cc.asset.unassign': 'שיוך נכס הוסר', 'cc.asset.update': 'נכס עודכן',
  'cc.connection.create': 'חיבור נוצר', 'cc.connection.update': 'חיבור עודכן', 'cc.connection.sync': 'סנכרון חיבור', 'cc.connection.disconnect': 'חיבור נותק',
  'cc.inbox.dismiss': 'הצעת שיוך נדחתה', 'cc.session.create': 'סשן נפתח', 'cc.session.update': 'סשן עודכן', 'cc.session.link': 'אירוע קושר לסשן',
  'cc.cost.create': 'רשומת עלות נוספה', 'cc.key.create': 'מפתח ספק נוסף', 'cc.key.rotate': 'סבב מפתח ספק',
  'cc.agent.create': 'סוכן נוצר', 'cc.agent.update': 'סוכן עודכן', 'cc.agent.run': 'ריצת סוכן החלה', 'cc.agent.run.finish': 'ריצת סוכן הסתיימה', 'cc.agent.run.cancel': 'ריצת סוכן בוטלה',
  'cc.seed.inventory': 'מלאי התחלתי נזרע', 'cc.client.create': 'לקוח נוצר', 'cc.client.update': 'לקוח עודכן',
  'cc.asset.source_delete': 'ריפוזיטורי נמחק במקור', 'cc.asset.source_archive': 'ריפוזיטורי אורכב במקור',
}
export const evidenceKind: Record<string, string> = {
  password_exposure: 'חשיפת סיסמה', secret_exposure: 'חשיפת סוד', info_disclosure: 'חשיפת מידע', record_access: 'גישה לרשומה', screenshot: 'צילום מסך',
}
export const modules: Record<string, string> = {
  'passive.security_headers': 'כותרות אבטחה (פסיבי)', 'passive.cookie_flags': 'דגלי Cookies (פסיבי)',
}

export function t(map: Record<string, string>, key: string | undefined | null): string {
  if (!key) return ''
  return map[key] ?? key
}

export function fmtDate(iso?: string | null): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (isNaN(d.getTime())) return iso
  return d.toLocaleString('he-IL', { dateStyle: 'short', timeStyle: 'short' })
}

// --- Control Center -----------------------------------------------------------
export const provider: Record<string, string> = { github: 'GitHub', vercel: 'Vercel', supabase: 'Supabase', n8n: 'n8n', reporter: 'מדווח חיצוני', anthropic: 'Anthropic', openai: 'OpenAI' }
export const assetKind: Record<string, string> = { repo: 'ריפוזיטורי', vercel_project: 'פרויקט Vercel', supabase_project: 'פרויקט Supabase', workflow: 'Workflow', service: 'שירות', bot: 'בוט' }
export const environment: Record<string, string> = { development: 'פיתוח', test: 'בדיקות', preview: 'Preview', production: 'Production', unclassified: 'לא מסווג' }
export const connStatus: Record<string, string> = { ok: 'תקין', partial: 'חלקי', rate_limited: 'מוגבל קצב', reauth: 'דורש התחברות מחדש', disconnected: 'מנותק', new: 'חדש', error: 'שגיאה זמנית' }
export const eventKind: Record<string, string> = { deployment: 'פריסה', workflow_run: 'ריצת Actions', pull_request: 'PR', execution: 'ריצת Workflow', heartbeat: 'Heartbeat', session: 'סשן' }
export const eventResult: Record<string, string> = { success: 'הצלחה', failure: 'כשל', running: 'בתהליך', cancelled: 'בוטל', unknown: 'אין דיווח' }
export const sessionStatus: Record<string, string> = { open: 'פתוח', waiting: 'ממתין', done: 'הושלם', cancelled: 'בוטל' }
export const sessionTool: Record<string, string> = { manual: 'ידני', claude_code: 'Claude Code', codex: 'Codex', other: 'אחר' }
export const importance: Record<string, string> = { critical: 'קריטי', high: 'גבוה', normal: 'רגיל', low: 'נמוך' }
export const inboxKind: Record<string, string> = { new_asset: 'נכס חדש', mismatch: 'חוסר התאמה', duplicate: 'כפילות אפשרית', missing_source: 'מקור שנעלם' }
export const costKind: Record<string, string> = { reported: 'חיוב מדווח', usage: 'שימוש AI', estimate: 'אומדן', allocation: 'הקצאה משותפת', subscription: 'מנוי חיצוני' }
export const runStatusCc: Record<string, string> = { queued: 'ממתין', running: 'רץ', awaiting_approval: 'ממתין לאישור', completed: 'הושלם', failed: 'נכשל', cancelled: 'בוטל' }
export const alertKind: Record<string, string> = { failure: 'כשל בייצור', repeated_failure: 'כשלים חוזרים', sync_delay: 'עיכוב בסנכרון', permission: 'בעיית הרשאה', budget: 'תקציב' }
export const wsRole: Record<string, string> = { admin: 'מנהל', editor: 'עורך', viewer: 'צופה' }
export const coverage: Record<string, string> = { full: 'מלא', partial: 'חלקי', inventory_only: 'מלאי בלבד', blocked: 'חסום' }
export const usageProvider: Record<string, string> = { claude: 'Claude', anthropic: 'Claude', gemini: 'Gemini', openai: 'OpenAI', ocr: 'OCR', whatsapp: 'WhatsApp', telegram: 'Telegram', sms: 'SMS', email: 'אימייל', other: 'אחר' }
export const metricLabel: Record<string, string> = { requests: 'קריאות', tokens_in: 'טוקני קלט', tokens_out: 'טוקני פלט', tokens_cached: 'טוקנים מהמטמון', messages: 'הודעות', recipients: 'נמענים', pages: 'עמודים', characters: 'תווים', minutes: 'דקות', units: 'יחידות' }
export function usd(n: number | string | undefined | null): string {
  const v = Number(n ?? 0)
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(isNaN(v) ? 0 : v)
}
export function qty(n: number | undefined | null): string { return new Intl.NumberFormat('he-IL').format(n ?? 0) }
