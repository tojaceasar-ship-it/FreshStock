import { test, expect, Page } from '@playwright/test'
import path from 'node:path'

const STOCK = 'https://frontend-navy-nu-73.vercel.app/'
const POS = 'https://freshpos-two.vercel.app/'
const evidence = path.resolve('..', 'audit', 'remote-master')
const state = path.join(evidence, 'owner-storage-state.json')

const products = [
  ['MLE-002','5901234560002','Jogurt Naturalny 400g','2.10','2.99'],
  ['MLE-003','5901234560003','Ser Żółty Gouda 300g','6.10','8.99'],
  ['MLE-004','5901234560004','Masło 200g','3.40','5.49'],
  ['MLE-005','5901234560005','Śmietana 18% 200ml','1.70','2.79'],
  ['NAP-001','5901234560009','Woda Mineralna 1.5L','1.10','2.19'],
  ['NAP-002','5901234560010','Coca-Cola 1L','3.20','4.99'],
  ['NAP-003','5901234560011','Monster Mango 500ml','4.20','6.99'],
  ['NAP-005','5901234560013','Red Bull 250ml','3.80','5.99'],
  ['PIE-001','5901234560020','Chleb pełnoziarnisty','2.00','4.20'],
  ['MRO-001','5901234560037','Warzywa mrożone 450g','4.50','7.90'],
] as const

async function createProduct(page: Page, row: typeof products[number]) {
  await page.goto(`${STOCK}products/new`)
  await expect(page.getByRole('heading', { name: 'Nowy produkt' })).toBeVisible()
  const inputs = page.locator('main input')
  await inputs.nth(0).fill(row[0]); await inputs.nth(1).fill(row[1]); await inputs.nth(2).fill(row[2])
  const nums = page.locator('main input[type="number"]')
  await nums.nth(0).fill(row[3]); await nums.nth(1).fill(row[4]); await nums.nth(2).fill('5'); await nums.nth(3).fill('30'); await nums.nth(4).fill('10')
  await page.getByRole('button', { name: 'Utwórz produkt' }).click()
  await expect(page.getByRole('heading', { name: row[2] })).toBeVisible({ timeout: 20_000 })
}

test('wdrożony sklep: produkty, dostawa z partiami FEFO i Generic REST', async ({ browser }) => {
  test.setTimeout(300_000)
  const context = await browser.newContext({ storageState: state, viewport: { width: 1600, height: 1000 } })
  const stock = await context.newPage(); const pos = await context.newPage()
  await Promise.all([stock.goto(STOCK), pos.goto(POS)])
  await expect(stock.getByRole('link', { name: 'Produkty' })).toBeVisible()
  await expect(pos).toHaveTitle(/FreshPOS/)

  for (const product of products) await createProduct(stock, product)
  await stock.goto(`${STOCK}products`)
  await expect(stock.getByText('Jogurt Naturalny 400g')).toBeVisible()
  await stock.screenshot({ path: path.join(evidence, '07-produkty-utworzone.png'), fullPage: true })

  await stock.goto(`${STOCK}deliveries`)
  await stock.getByRole('button', { name: /Nowa dostawa/ }).click()
  await stock.locator('select').filter({ hasText: 'QA Supplier Onboarding' }).selectOption({ label: 'QA Supplier Onboarding' })
  await stock.getByPlaceholder('FV/123/2026').fill(`QA-FV-${Date.now()}`)
  const addItem = stock.getByRole('button', { name: '+ Pozycja' })
  for (let i = 1; i < 11; i++) await addItem.click()
  const itemRows = stock.locator('main div.grid.md\\:grid-cols-6')
  const early = new Date(Date.now() + 3 * 86400000).toISOString().slice(0,10)
  const later = new Date(Date.now() + 10 * 86400000).toISOString().slice(0,10)
  const locationName = 'Magazyn główny'
  const deliveryLines = [products[0], products[0], ...products.slice(1)]
  for (let i = 0; i < deliveryLines.length; i++) {
    const row = itemRows.nth(i); const product = deliveryLines[i]
    await row.locator('select').nth(0).selectOption({ label: `${product[2]} (${product[0]})` })
    await row.locator('input[type="number"]').nth(0).fill(i === 0 ? '3' : i === 1 ? '10' : '20')
    await row.locator('input[type="number"]').nth(1).fill(product[3])
    await row.locator('input[type="date"]').fill(i === 0 ? early : later)
    await row.getByPlaceholder('Nr partii').fill(`QA-${product[0]}-${i + 1}`)
    await row.locator('select').nth(1).selectOption({ label: locationName })
  }
  await stock.screenshot({ path: path.join(evidence, '08-dostawa-dwie-partie-fefo.png'), fullPage: true })
  await stock.getByRole('button', { name: 'Zatwierdź dostawę' }).click()
  await expect(stock.getByText(/QA-FV-/).first()).toBeVisible({ timeout: 30_000 })

  await stock.goto(`${STOCK}batches`)
  await expect(stock.getByText('QA-MLE-002-1')).toBeVisible()
  await expect(stock.getByText('QA-MLE-002-2')).toBeVisible()
  await stock.screenshot({ path: path.join(evidence, '09-partie-fefo-3-plus-10.png'), fullPage: true })

  await stock.goto(`${STOCK}integrations`)
  const genericCard = stock.getByText('Generic REST', { exact: true }).first().locator('..').locator('..')
  const action = genericCard.getByRole('button')
  if (await action.getAttribute('disabled') === null && /Konfiguruj|Configure/.test(await action.innerText())) {
    const answers = ['https://freshpos-two.vercel.app/api','/sales','/products','/refunds','freshpos_sim_demo0000demo0000demo0000']
    let index = 0
    stock.on('dialog', async dialog => dialog.accept(answers[index++] || ''))
    await action.click()
    await expect(stock.getByText(/Integracja została utworzona|połączenie/).first()).toBeVisible({ timeout: 30_000 })
  }
  await stock.screenshot({ path: path.join(evidence, '10-integracja-generic-rest.png'), fullPage: true })
  await context.storageState({ path: state })
  await context.close()
})
