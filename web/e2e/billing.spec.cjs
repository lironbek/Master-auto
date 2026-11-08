// Billing & service module browser E2E: settings -> customer -> product + service
// -> subscriptions -> ticket + time -> external link (public page) -> charges
// (generate, issue, print) -> hours report -> expenses -> knowledge.
// Run: node e2e/billing.spec.cjs <baseUrl> <shotsDir>
const { chromium } = require('playwright');
const fs = require('node:fs');
const [,, base = 'http://localhost:5173', shots = 'e2e/shots-billing'] = process.argv
let page; const errors = [];
(async () => {
  fs.mkdirSync(shots, { recursive: true })
  const browser = await chromium.launch()
  const ctx = await browser.newContext({ viewport: { width: 1366, height: 900 }, deviceScaleFactor: 1 })
  page = await ctx.newPage()
  page.on('pageerror', e => errors.push(String(e)))
  page.on('console', m => { if (m.type() === 'error' && !m.text().includes('ERR_TUNNEL') && !m.text().includes('fonts.g')) errors.push(m.text()) })
  const snap = (n) => page.screenshot({ path: `${shots}/${n}.png`, fullPage: true })
  const assert = (c, m) => { if (!c) throw new Error('ASSERT: ' + m) }
  const email = `bl-${Date.now()}@example.test`

  await page.goto(base + '/login')
  await page.getByRole('button', { name: 'פתיחת ארגון חדש' }).click()
  await page.getByLabel('שם הארגון').fill('BEKMAN IT')
  await page.getByLabel('אימייל', { exact: true }).fill(email)
  await page.getByLabel('סיסמה').fill('correct-horse-battery')
  await page.getByRole('button', { name: 'פתיחת ארגון וכניסה' }).click()
  await page.waitForURL(base + '/')
  await page.getByLabel('שם המרחב').fill('Comax')
  await page.getByRole('button', { name: 'יצירת מרחב' }).click()
  await page.getByText('הפרויקטים והאוטומציות שלך').waitFor()

  // settings
  await page.goto(base + '/billing/settings')
  await page.getByLabel('מע״מ %').fill('18')
  await page.getByLabel('תעריף שעה ברירת מחדל (₪)').fill('250')
  await page.getByLabel('שם העסק').fill('BEKMAN IT')
  await page.getByRole('button', { name: 'שמירה' }).first().click()
  await page.getByText('ההגדרות נשמרו').waitFor()

  // catalog
  await page.goto(base + '/billing/catalog')
  await page.getByLabel('שם', { exact: true }).fill('שירותי IT')
  await page.getByLabel('מחיר למשתמש לחודש (₪)').fill('120')
  await page.getByRole('button', { name: 'הוספה' }).click()
  await page.getByRole('cell', { name: 'שירותי IT' }).waitFor()
  await page.getByRole('button', { name: /שירותים \(/ }).click()
  await page.getByLabel('תיאור', { exact: true }).fill('בנק שעות חודשי')
  await page.getByLabel('מחיר (₪)').fill('1000')
  await page.getByLabel('חיוב מתחדש כל חודש').check()
  await page.getByRole('button', { name: 'הוספה' }).click()
  await page.getByRole('cell', { name: 'בנק שעות חודשי' }).waitFor()
  await snap('01-catalog')

  // employee
  await page.goto(base + '/billing/employees')
  await page.getByLabel('שם', { exact: true }).fill('לירון')
  await page.getByRole('button', { name: 'הוספה' }).click()
  await page.getByRole('cell', { name: /לירון/ }).waitFor()

  // customer + subscriptions
  await page.goto(base + '/billing/customers')
  await page.getByRole('button', { name: 'לקוח חדש' }).click()
  await page.getByLabel('שם', { exact: true }).fill('נווה מיכאל')
  await page.getByLabel('איש קשר').fill('אבי')
  await page.getByLabel('טלפון').fill('0501234567')
  await page.getByRole('button', { name: 'יצירה' }).click()
  await page.getByRole('link', { name: 'נווה מיכאל' }).click()
  await page.waitForURL(/\/billing\/customers\//)
  const monthStart = new Date().toISOString().slice(0, 8) + '01'
  await page.getByLabel('משתמשים', { exact: true }).fill('10')
  await page.getByLabel('מתאריך').fill(monthStart)
  await page.getByRole('button', { name: 'הוספה' }).click()
  await page.getByRole('cell', { name: /שירותי IT/ }).waitFor()
  await page.getByRole('button', { name: 'שירות', exact: true }).click()
  await page.getByLabel('מתאריך').fill(monthStart)
  await page.getByRole('button', { name: 'הוספה' }).click()
  await page.getByRole('cell', { name: /בנק שעות חודשי/ }).waitFor()
  await snap('02-customer')

  // ticket + time
  await page.getByRole('link', { name: 'קריאה חדשה' }).click()
  await page.waitForURL(/\/billing\/tickets\?new=1/)
  await page.getByLabel('כותרת', { exact: true }).fill('AP פינת חי לא מגיב')
  await page.getByLabel('זמן ראשוני (דקות)').fill('60')
  await page.getByRole('button', { name: 'פתיחת קריאה' }).click()
  await page.getByRole('link', { name: 'AP פינת חי לא מגיב' }).click()
  await page.waitForURL(/\/billing\/tickets\//)
  await page.getByLabel('דקות').fill('30')
  await page.getByLabel('תיאור הטיפול').fill('הוחלף מתג')
  await page.getByRole('button', { name: 'הוסף רישום' }).click()
  await page.getByText('1:30').first().waitFor()
  await snap('03-ticket')

  // external link -> public page
  await page.getByRole('button', { name: 'צור קישור' }).click()
  const linkInput = page.locator('input[readonly]')
  await linkInput.waitFor()
  const url = await linkInput.inputValue()
  const pub = await ctx.newPage()
  await pub.goto(url.replace(/^https?:\/\/[^/]+/, base))
  await pub.getByText('AP פינת חי לא מגיב').waitFor()
  await pub.getByLabel('מטפל *').fill('אבי מהלקוח')
  await pub.getByLabel('מה נעשה *').fill('בדקתי את החיבור, עובד')
  await pub.getByLabel('זמן טיפול (בדקות)').fill('15')
  await pub.getByRole('button', { name: 'שליחת עדכון' }).click()
  await pub.getByText('תודה, העדכון התקבל').waitFor()
  await pub.screenshot({ path: `${shots}/04-public-update.png`, fullPage: true })
  await pub.close()
  await page.reload()
  await page.getByText('בדקתי את החיבור, עובד').waitFor()

  // charges: generate, open, issue, print
  await page.goto(base + '/billing/charges')
  page.once('dialog', d => d.accept())
  await page.getByRole('button', { name: /הפק טיוטות/ }).click()
  await page.getByText(/נוצרו 1 טיוטות/).waitFor()
  await page.getByRole('link', { name: 'נווה מיכאל' }).click()
  await page.waitForURL(/\/billing\/charges\//)
  await page.getByText('בנק שעות חודשי').waitFor()
  assert((await page.getByText(/2,200\.00/).count()) >= 1, 'subtotal 10×120 + 1000 = 2,200')   // no hours line: customer is not billed by hours
  await snap('05-charge-draft')
  page.once('dialog', d => d.accept())
  await page.getByRole('button', { name: 'הפק', exact: true }).click()
  await page.getByText('הופק', { exact: true }).first().waitFor()
  const [printPage] = await Promise.all([ctx.waitForEvent('page'), page.getByRole('button', { name: /הדפסה/ }).click()])
  await printPage.waitForLoadState()
  await printPage.getByText('סה"כ לתשלום').waitFor()
  await printPage.screenshot({ path: `${shots}/06-charge-print.png`, fullPage: true })
  await printPage.close()

  // hours report
  await page.goto(base + '/billing/reports/hours')
  await page.getByText('1:30').first().waitFor()
  await snap('07-hours')

  // expenses
  await page.goto(base + '/billing/expenses')
  await page.getByLabel('שם', { exact: true }).fill('Vercel Pro')
  await page.getByLabel('סכום', { exact: true }).fill('20')
  await page.getByLabel('מטבע').selectOption('USD')
  await page.getByRole('button', { name: 'הוספה' }).click()
  await page.getByRole('cell', { name: /Vercel Pro/ }).waitFor()
  assert((await page.getByText(/74\.00/).count()) >= 1, 'USD 20 × default 3.7 = 74')

  // knowledge
  await page.goto(base + '/billing/knowledge')
  await page.getByRole('button', { name: 'מאמר חדש' }).click()
  await page.getByLabel('כותרת', { exact: true }).fill('הדפסה בין VLAN')
  await page.getByLabel('תוכן').fill('לפתוח פורט 9100 בפוליסה')
  await page.getByRole('button', { name: 'שמירה' }).click()
  await page.getByRole('button', { name: /הדפסה בין VLAN/ }).click()
  await page.getByText('לפתוח פורט 9100').waitFor()

  // dashboard
  await page.goto(base + '/billing')
  await page.getByText('הכנסות החודש').waitFor()
  await page.getByText('AP פינת חי לא מגיב').first().waitFor()
  await snap('08-billing-dashboard')

  await browser.close()
  if (errors.length) { console.log('errors:', errors); process.exit(1) }
  console.log('BILLING E2E OK')
})().catch(async e => { console.error(e); try { await page.screenshot({ path: `${shots}/zz-failure.png`, fullPage: true }); console.log('URL:', page.url(), 'errors:', errors) } catch {} process.exit(1) })
