// Control Center browser E2E: register -> workspace -> project -> external report
// (creates an asset + event without a real provider) -> inbox assign -> session
// -> cost -> key -> agent run -> overview. Run: node e2e/cc.spec.cjs <baseUrl> <shotsDir>
const { chromium } = require('playwright');
const fs = require('node:fs');
const [,, base = 'http://localhost:5173', shots = 'e2e/shots-cc'] = process.argv
let page; const errors = [];
(async () => {
  fs.mkdirSync(shots, { recursive: true })
  const browser = await chromium.launch()
  page = await browser.newPage({ viewport: { width: 1280, height: 860 }, deviceScaleFactor: 1 })
  page.on('pageerror', e => errors.push(String(e)))
  page.on('console', m => { if (m.type() === 'error' && !m.text().includes('ERR_TUNNEL')) errors.push(m.text()) })
  const snap = (n) => page.screenshot({ path: `${shots}/${n}.png`, fullPage: true })
  const assert = (c, m) => { if (!c) throw new Error('ASSERT: ' + m) }
  const email = `cc-${Date.now()}@example.test`

  await page.goto(base + '/login')
  await page.getByRole('button', { name: 'פתיחת ארגון חדש' }).click()
  await page.getByLabel('שם הארגון').fill('הארגון של לירון')
  await page.getByLabel('אימייל', { exact: true }).fill(email)
  await page.getByLabel('סיסמה').fill('correct-horse-battery')
  await page.getByRole('button', { name: 'פתיחת ארגון וכניסה' }).click()
  await page.waitForURL(base + '/')

  // First run: create a workspace
  await page.getByLabel('שם המרחב').fill('פרויקטים פרטיים')
  await page.getByRole('button', { name: 'יצירת מרחב' }).click()
  await page.getByText('מרכז הבקרה').first().waitFor()
  await snap('01-overview-empty')

  // Project
  await page.getByRole('link', { name: 'פרויקטים', exact: true }).first().click()
  await page.getByRole('button', { name: 'פרויקט חדש' }).click()
  await page.getByLabel('שם', { exact: true }).fill('BuildFlow')
  await page.getByLabel('בעלים').fill('לירון')
  await page.getByLabel('תיאור').fill('ניהול פרויקטי בנייה')
  await page.getByLabel('תקציב חודשי ($)').fill('80')
  await page.getByRole('button', { name: 'יצירה' }).click()
  await page.getByRole('link', { name: 'BuildFlow' }).first().waitFor()
  await snap('02-projects')

  // External reporter: get a token, then post a heartbeat with fetch from the page (same origin)
  await page.getByRole('link', { name: 'חיבורים' }).first().click()
  await page.getByRole('button', { name: /צור\/חדש טוקן/ }).click()
  const pre = await page.locator('pre').first().textContent()
  const token = /X-Report-Token: ([^"\s]+)/.exec(pre)[1]
  const wsId = /"workspace_id":"(\w+)"/.exec(pre)[1]
  await snap('03-connections')
  for (const [ext, result] of [['run-1', 'success'], ['run-2', 'failure']]) {
    const r = await page.evaluate(async ({ token, wsId, ext, result }) => {
      const res = await fetch('/api/cc/report', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Report-Token': token },
        body: JSON.stringify({ workspace_id: wsId, service: 'nightly-backup', external_id: ext, kind: 'heartbeat', result, environment: 'production', title: `Backup ${ext}` }) })
      return res.status
    }, { token, wsId, ext, result })
    assert(r === 200, 'report accepted')
  }

  // Inbox: assign the new service asset to BuildFlow
  await page.getByRole('link', { name: 'תיבת מיון' }).first().click()
  await page.getByText('nightly-backup').waitFor()
  await snap('04-inbox')
  await page.getByRole('listitem').first().locator('select').selectOption({ label: 'BuildFlow' })
  await page.getByRole('listitem').first().getByRole('button', { name: 'שייך', exact: true }).click()
  await page.getByText('תיבת המיון ריקה').waitFor()

  // Catalog shows the asset with its project
  await page.getByRole('link', { name: 'קטלוג נכסים' }).first().click()
  await page.getByRole('link', { name: 'nightly-backup' }).waitFor()
  await snap('05-assets')

  // Project page: failure in production, events, session, cost, agent
  await page.getByRole('link', { name: 'פרויקטים', exact: true }).first().click()
  await page.getByRole('link', { name: 'BuildFlow' }).first().click()
  await page.waitForURL(/\/projects\/prj_/)
  await page.getByText('כשל בייצור').first().waitFor()
  await snap('06-project-summary')
  await page.getByRole('button', { name: 'סשנים' }).click()
  await page.getByLabel('כותרת').fill('דוח חריגות תקציב')
  await page.getByLabel('מטרה').fill('השוואת תכנון מול ביצוע')
  await page.getByRole('button', { name: 'פתיחת סשן' }).click()
  await page.getByRole('link', { name: 'דוח חריגות תקציב' }).waitFor()
  await page.getByRole('link', { name: 'דוח חריגות תקציב' }).click()
  await page.waitForURL(/\/sessions\/ses_/)
  await page.getByText('הצעות שיוך').waitFor()
  await page.getByRole('button', { name: 'שייך', exact: true }).first().click()
  await page.getByText('ציר הפעילות').waitFor()
  await snap('07-session')
  await page.getByLabel('תוצר').fill('דוח ראשון')
  await page.getByRole('button', { name: 'סמן כהושלם' }).click()
  await page.getByText('הושלם').first().waitFor()

  // Costs + key
  await page.getByRole('link', { name: 'עלויות' }).first().click()
  await page.getByLabel('ספק').fill('Supabase')
  await page.getByLabel('סכום').fill('25')
  await page.getByLabel('מתאריך').fill('2026-11-01')
  await page.getByLabel('עד תאריך').fill('2026-11-30')
  await page.getByRole('button', { name: 'הוספה' }).click()
  await page.getByText('$25.00').first().waitFor()
  await page.getByRole('button', { name: /מפתחות וזהויות/ }).click()
  await page.getByLabel('שם', { exact: true }).fill('Anthropic · BuildFlow')
  await page.getByLabel('המפתח').fill('sk-ant-not-a-real-key-0000')
  await page.getByRole('button', { name: 'שמירה מוצפנת' }).click()
  await page.getByText('••••0000').waitFor()
  await snap('08-costs-keys')

  // Agent: create, run (deterministic), view result
  await page.getByRole('link', { name: 'סוכנים' }).first().click()
  await page.getByRole('button', { name: 'סוכן חדש' }).click()
  await page.getByLabel('שם', { exact: true }).fill('סקירת מצב משרד')
  await page.getByLabel('הוראות משימה').fill('סכם חריגות ועלויות')
  await page.getByRole('button', { name: 'שמירה', exact: true }).click()
  await page.getByText('סקירת מצב משרד').first().waitFor()
  await page.locator('table select').first().selectOption({ label: 'BuildFlow' })
  await page.getByRole('button', { name: 'הפעל' }).click()
  await page.waitForURL(/\/agents\/runs\/arun_/)
  await page.getByText('תוצר הריצה').waitFor()
  const body = await page.content()
  assert(body.includes('BuildFlow') && body.includes('catalog.read'), 'run result and steps rendered')
  assert(!body.includes('sk-ant-not-a-real-key'), 'secret never rendered')
  await snap('09-agent-run')

  // Overview populated, security module reachable
  await page.getByRole('link', { name: 'סקירה' }).first().click()
  await page.getByText('דורש תשומת לב').waitFor()
  await snap('10-overview')
  await page.getByRole('link', { name: 'לוח סקרים' }).first().click()
  await page.getByText('לוח בקרה').first().waitFor()
  await snap('11-security-dashboard')

  await browser.close()
  if (errors.length) { console.log('errors:', errors); process.exit(1) }
  console.log('CC E2E OK')
})().catch(async e => { console.error(e); try { await page.screenshot({ path: `${shots}/zz-failure.png`, fullPage: true }); console.log('URL:', page.url(), 'errors:', errors) } catch {} process.exit(1) })
