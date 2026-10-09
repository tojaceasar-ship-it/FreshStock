import { test, expect, Page } from '@playwright/test'
import path from 'node:path'

const STOCK = 'https://frontend-navy-nu-73.vercel.app/'
const POS = 'https://freshpos-two.vercel.app/'
const evidence = path.resolve('..', 'audit', 'remote-master')
const state = path.join(evidence, 'owner-storage-state.json')

async function sync(page: Page) {
  await page.getByRole('link', { name: 'Integracje' }).click()
  await expect(page.getByRole('heading', { name: /Integracje/ })).toBeVisible()
  const genericCard = page.getByText('Generic REST', { exact: true }).first().locator('..').locator('..')
  const configure = genericCard.getByRole('button', { name: /Konfiguruj|Configure/ })
  if (await configure.count() > 0) {
    const answers = ['https://freshpos-two.vercel.app/api','/sales','/products','/refunds','freshpos_sim_demo0000demo0000demo0000']
    let index = 0
    const handleDialog = async (dialog: any) => dialog.accept(answers[index++] || '')
    page.on('dialog', handleDialog)
    await configure.click()
    await expect(page.getByRole('button').filter({ hasText: /Generic REST ·/ }).last()).toBeVisible({ timeout: 30_000 })
    page.off('dialog', handleDialog)
  }
  const integration = page.getByRole('button').filter({ hasText: /Generic REST ·/ }).last()
  await integration.click()
  await page.getByRole('button', { name: /Ustawienia|Settings/ }).last().click()
  const syncButton = page.getByRole('button', { name: /Sync Now|Synchronizuj/ })
  await expect(syncButton).toBeEnabled()
  await syncButton.click()
  await expect(page.getByText(/Sync zakończony|synchronizacja.*zakończona/i)).toBeVisible({ timeout: 60_000 })
}

test('FreshPOS + FreshStock: FEFO, duplicate, refund, void, unknown i shortage', async ({ browser }) => {
  test.setTimeout(300_000)
  const context = await browser.newContext({ storageState: state, viewport: { width: 1600, height: 1000 } })
  const stock = await context.newPage(); const pos = await context.newPage()
  await Promise.all([stock.goto(`${STOCK}deliveries`), pos.goto(POS)])

  // Wcześniejsza partia 3 szt. dla SKU używanego przez scenariusz FEFO FreshPOS.
  await stock.goto(`${STOCK}batches`)
  if (await stock.getByText('QA-FEFO-EARLY-3').count() === 0) {
    await stock.goto(`${STOCK}deliveries`)
    await stock.getByRole('button', { name: /Nowa dostawa/ }).click()
    await stock.locator('select').filter({ hasText: 'QA Supplier Onboarding' }).selectOption({ label: 'QA Supplier Onboarding' })
    await stock.getByPlaceholder('FV/123/2026').fill(`QA-FEFO-${Date.now()}`)
    await stock.locator('select').filter({ hasText: 'Ser Żółty Gouda 300g' }).selectOption({ label: 'Ser Żółty Gouda 300g (MLE-003)' })
    await stock.getByPlaceholder('Ilość').fill('3')
    await stock.getByPlaceholder('Cena zakupu').fill('6.10')
    await stock.locator('input[type="date"]').fill(new Date(Date.now() + 2 * 86400000).toISOString().slice(0,10))
    await stock.getByPlaceholder('Nr partii').fill('QA-FEFO-EARLY-3')
    await stock.locator('select').filter({ hasText: 'Magazyn główny' }).selectOption({ label: 'Magazyn główny' })
    await stock.getByRole('button', { name: 'Zatwierdź dostawę' }).click()
    await expect(stock.getByText(/QA-FEFO-/).first()).toBeVisible({ timeout: 30_000 })
  }

  await pos.getByRole('button', { name: 'Reset' }).click()
  await pos.getByRole('button').filter({ hasText: 'sprzedaj więcej niż ma pierwsza partia' }).click()
  await expect(pos.getByText(/Sprzedaż 5× Mleko/)).toBeVisible({ timeout: 30_000 })
  await pos.screenshot({ path: path.join(evidence, '11-freshpos-fefo-sale.png'), fullPage: true })
  await sync(stock)
  await stock.goto(`${STOCK}sales`)
  await expect(stock.getByText(/SALE-/).first()).toBeVisible({ timeout: 30_000 })
  await stock.screenshot({ path: path.join(evidence, '12-freshstock-sale-after-pos.png'), fullPage: true })
  await stock.goto(`${STOCK}batches`)
  const earlyRow = stock.getByText('QA-FEFO-EARLY-3').first().locator('xpath=ancestor::tr')
  await expect(earlyRow).toBeVisible()
  await stock.screenshot({ path: path.join(evidence, '13-fefo-earliest-batch-zero.png'), fullPage: true })

  for (const scenario of ['ta sama transakcja ×2', 'zwrot pozycji z wcześniejszej sprzedaży', 'anulowanie całej transakcji', '9999999999999', 'POS sprzeda 20']) {
    await pos.getByRole('button').filter({ hasText: scenario }).click()
  }
  await pos.screenshot({ path: path.join(evidence, '14-pos-error-refund-void-scenarios.png'), fullPage: true })
  await sync(stock)
  await stock.getByRole('link', { name: 'Integracje' }).click()
  await stock.getByRole('button').filter({ hasText: /Generic REST ·/ }).last().click()
  await stock.getByRole('button', { name: /Błędy|Errors/ }).last().click()
  await stock.screenshot({ path: path.join(evidence, '15-integration-errors-and-returns.png'), fullPage: true })
  await context.storageState({ path: state })
  await context.close()
})
