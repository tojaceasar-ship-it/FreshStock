import { chromium } from 'playwright'

;(async () => {
  const browser = await chromium.launch()
  const page = await browser.newPage()
  page.on('request', (r) => {
    if (r.url().includes('/api/sales') && r.method() === 'POST') {
      console.log('[POST /api/sales] headers:', JSON.stringify(r.headers(), null, 2))
      const postData = r.postData()
      if (postData) console.log('[POST /api/sales] body:', postData)
    }
  })
  page.on('response', (r) => {
    if (r.url().includes('/api/sales')) {
      console.log('[res]', r.status(), r.request().method(), r.url())
    }
  })

  await page.route('**/api/sales', async (route) => {
    if (route.request().method() === 'POST') {
      await new Promise((r) => setTimeout(r, 800))
    }
    await route.continue()
  })

  await page.addInitScript(() => {
    if (!localStorage.getItem('freshstock.language.v1')) {
      localStorage.setItem('freshstock.language.v1', 'pl')
    }
  })

  await page.goto('http://127.0.0.1:4173/login')
  await page.getByPlaceholder('Wpisz login lub adres e-mail').fill('manager')
  await page.getByPlaceholder('••••••••').fill('TestManager123!')
  await page.getByRole('button', { name: 'Zaloguj się' }).click()
  await page.waitForURL((url) => url.pathname === '/')
  console.log('[login done]', page.url())

  await page.goto('http://127.0.0.1:4173/sales')
  await page.waitForTimeout(2000)

  await page.locator('select').first().selectOption(/Banan E2E/)
  console.log('[product selected]')
  await page.getByRole('button', { name: 'Sprzedaj (FEFO)' }).dblclick()
  console.log('[dblclicked]')
  await page.waitForTimeout(3000)
  console.log('[rows]', await page.locator('table tbody tr').count())
  await browser.close()
})().catch((e) => { console.error('FATAL', String(e).slice(0, 300)); process.exit(1) })