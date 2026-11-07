// Browser E2E: register -> project -> authorization -> scope -> approve ->
// run (live) -> finding -> evidence -> report -> audit. Run with:
//   node e2e/flow.spec.mjs <baseUrl> <targetHost:port> <screenshotDir>
const { chromium } = require('playwright')
const fs = require('node:fs');

const [,, base = 'http://localhost:5173', target = 'target.test:8081', shots = 'e2e/shots'] = process.argv
let page; const errors = [];
(async () => {
fs.mkdirSync(shots, { recursive: true })
const browser = await chromium.launch()
page = await browser.newPage({ viewport: { width: 1280, height: 860 }, deviceScaleFactor: 1 })
page.on('pageerror', e => errors.push(String(e)))
page.on('console', m => { if (m.type() === 'error' && !m.text().includes('ERR_TUNNEL')) errors.push(m.text()) })
const snap = async (name) => page.screenshot({ path: `${shots}/${name}.png`, fullPage: true })
const assert = (cond, msg) => { if (!cond) { throw new Error('ASSERT: ' + msg) } }

const email = `e2e-${Date.now()}@example.test`

// Login page → register org
await page.goto(base + '/login')
await snap('01-login')
await page.getByRole('button', { name: 'פתיחת ארגון חדש' }).click()
await page.getByLabel('שם הארגון').fill('ארגון בדיקה')
await page.getByLabel('שם מלא').fill('דנה בודקת')
await page.getByLabel('אימייל', { exact: true }).fill(email)
await page.getByLabel('סיסמה').fill('correct-horse-battery')
await page.getByRole('button', { name: 'פתיחת ארגון וכניסה' }).click()
await page.waitForURL(base + '/')
await page.getByLabel('שם המרחב').fill('מרחב בדיקות')
await page.getByRole('button', { name: 'יצירת מרחב' }).click()
await page.getByRole('link', { name: 'לוח סקרים' }).first().click()
await page.getByText('לוח בקרה').first().waitFor()
await snap('02-dashboard-empty')

// Project
await page.getByRole('link', { name: 'פרויקטים והיקף' }).first().click()
await page.getByRole('button', { name: 'פרויקט חדש' }).click()
await page.getByLabel('שם', { exact: true }).fill('אתר מעבדה')
await page.getByLabel('תיאור', { exact: true }).fill('יעד סינתטי לבדיקת הזרימה')
await page.getByRole('button', { name: 'יצירה' }).click()
await page.getByRole('link', { name: /אתר מעבדה/ }).click()
await page.waitForURL(/\/security\/projects\/prj_/)

// Authorization
await page.getByRole('button', { name: 'מסמך הרשאה' }).click()
await page.getByLabel('מאשר', { exact: true }).fill('דנה')
await page.getByLabel('סמכות המאשר').fill('CISO')
await page.getByLabel('אסמכתא למסמך').fill('DOC-1')
await page.getByText('אימות שליטה בוצע').click()
await page.getByRole('button', { name: 'שמירה' }).click()
await page.getByText('CISO').waitFor()

// Scope
await page.getByRole('button', { name: 'היקף בדיקה חדש' }).click()
const [host, port] = target.split(':')
await page.getByLabel('סכמה').selectOption('http')
await page.getByLabel(/שם מארח/).fill(host)
await page.getByLabel('פורט', { exact: true }).fill(port)
await snap('03-scope-wizard')
await page.getByRole('button', { name: 'יצירת גרסת היקף' }).click()
await page.getByText('טיוטה').waitFor()
await page.getByRole('button', { name: 'אישור' }).click()
await page.getByText('מאושר').first().waitFor()
await snap('04-project')

// Run (autostart)
await page.getByRole('button', { name: 'הפעלת ריצה' }).click()
await page.waitForURL(/\/security\/runs\/run_/)
await page.getByText('ריצה הסתיימה').waitFor({ timeout: 60_000 })
await snap('05-live-run')
const finishedBadge = await page.getByText('הושלמה').first().isVisible()
assert(finishedBadge, 'run should complete')
const injection = await page.getByText('הזרקה זוהתה והתעלמנו').count()
assert(injection >= 1, 'prompt-injection event should be logged and ignored')
const html = await page.content()
assert(!html.includes('SYNTHETIC-LAB-SECRET-123'), 'raw synthetic secret must never reach the UI')

// Finding + evidence
await page.getByRole('link', { name: /Cookie without Secure/ }).first().click()
await page.waitForURL(/\/security\/findings\/find_/)
await page.getByText('השפעה שהוכחה').waitFor()
await page.getByText('[REDACTED]').first().waitFor()
await snap('06-finding')
const fhtml = await page.content()
assert(!fhtml.includes('SYNTHETIC-LAB-SECRET-123'), 'evidence card must be redacted')
await page.getByRole('button', { name: /בסקירה/ }).click()
await page.locator('.badge', { hasText: 'בסקירה' }).first().waitFor()

// Evidence vault
await page.getByRole('link', { name: 'כספת ראיות' }).first().click()
await page.getByRole('button', { name: 'צפייה' }).first().click()
await page.getByText('יומן גישה').waitFor()
await snap('07-evidence-vault')

// Report
await page.getByRole('link', { name: 'דוחות' }).first().click()
await page.locator('.card select').first().selectOption({ index: 1 })
await page.getByRole('button', { name: 'הפקה' }).click()
await page.getByText('Security report').waitFor()
await snap('08-report')

// Audit + dashboard
await page.getByRole('link', { name: 'ביקורת' }).first().click()
await page.getByText('החלטת מדיניות').first().waitFor()
await snap('09-audit')
await page.getByRole('link', { name: 'לוח סקרים' }).first().click()
await page.getByText('ממצאים פתוחים').waitFor()
await snap('10-dashboard')

await browser.close()
if (errors.length) { console.log('console/page errors:', errors); process.exit(1) }
console.log('E2E OK')

})().catch(async e => { console.error(e); try { await page.screenshot({ path: `${shots}/zz-failure.png`, fullPage: true }); console.log('URL at failure:', page.url()); console.log('errors:', errors) } catch {} process.exit(1) })
