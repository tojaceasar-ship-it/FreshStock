import { test, expect } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'

const STOCK = 'https://frontend-navy-nu-73.vercel.app/'
const evidence = path.resolve('..', 'audit', 'remote-master')
const state = path.join(evidence, 'owner-storage-state.json')

test('operacje biznesowe: waste, inventory, task oraz wszystkie ekrany', async ({ browser }) => {
  test.setTimeout(240_000)
  const context = await browser.newContext({ storageState: state, viewport: { width: 1600, height: 1000 } })
  const page = await context.newPage(); await page.goto(STOCK)

  await page.getByRole('link', { name: 'Straty' }).click()
  await page.locator('main select').nth(0).selectOption({ label: 'Jogurt Naturalny 400g' })
  await page.locator('main input[type="number"]').fill('1')
  await page.locator('main select').nth(1).selectOption('damaged')
  await page.getByPlaceholder('Powód').fill('QA damaged during handling')
  await page.getByRole('button', { name: 'Zgłoś' }).click()
  await expect(page.locator('tbody').getByText(/damaged|uszkodzone/i).first()).toBeVisible({ timeout: 20_000 })
  await page.screenshot({ path: path.join(evidence, '16-waste-damaged.png'), fullPage: true })

  await page.getByRole('link', { name: 'Inwentaryzacja' }).click()
  await page.locator('main select').first().selectOption({ label: 'Magazyn główny' })
  await page.getByRole('button', { name: 'Utwórz sesję i rozpocznij skanowanie' }).click()
  const ean = page.getByPlaceholder('EAN produktu'); await ean.fill('5901234560002'); await ean.press('Enter')
  await expect(page.getByText('Jogurt Naturalny 400g').last()).toBeVisible({ timeout: 20_000 })
  await page.getByLabel('Stan fizyczny').fill('7')
  await page.getByRole('button', { name: 'Dodaj' }).click()
  await expect(page.getByText(/różnica/i)).toBeVisible()
  await page.getByRole('button', { name: 'Zakończ i skoryguj stany' }).click()
  await expect(page.locator('tbody').getByText(/zakończone|completed/i).first()).toBeVisible({ timeout: 20_000 })
  await page.screenshot({ path: path.join(evidence, '17-inventory-count-completed.png'), fullPage: true })

  await page.getByRole('link', { name: 'Zadania' }).click()
  await page.getByRole('button', { name: 'Nowe zadanie' }).click()
  await page.getByLabel('Tytuł *').fill('Sprawdź daty jogurtów QA')
  await page.getByLabel('Opis').fill('Pełny test przepływu Owner do Employee')
  await page.getByLabel('Przypisz do').selectOption('role:EMPLOYEE')
  await page.getByLabel('Typ').selectOption('EXPIRY_CHECK')
  await page.getByLabel('Priorytet').selectOption('HIGH')
  await page.getByLabel('Produkt').selectOption({ label: 'Jogurt Naturalny 400g' })
  await page.getByLabel(/Checklist/).fill('Sprawdź partię\nSprawdź termin\nDodaj komentarz')
  await page.getByRole('button', { name: 'Przypisz zadanie' }).click()
  await expect(page.getByRole('heading', { name: 'Sprawdź daty jogurtów QA' })).toBeVisible({ timeout: 20_000 })
  await page.screenshot({ path: path.join(evidence, '18-owner-task-created.png'), fullPage: true })
  await page.keyboard.press('Escape')

  const links = ['Dashboard','Dzisiaj','Produkty','Partie / Daty','Dostawy','Zamówienia','Sprzedaż','Przeceny','Lokalizacje','Alerty','Raporty','Oszczędności','Skaner','AI Insights','Użytkownicy','Integracje','Konfiguracja sklepu']
  const inventory: any[] = []
  for (const name of links) {
    const link = page.getByRole('link', { name, exact: true })
    if (await link.count() === 0) { inventory.push({ name, status: 'BLOCKED', reason: 'link absent' }); continue }
    await link.click(); await page.waitForTimeout(150)
    inventory.push({ name, status: 'EXECUTED', url: page.url(), headings: await page.getByRole('heading').allTextContents(), buttons: await page.getByRole('button').allTextContents() })
  }
  fs.writeFileSync(path.join(evidence, 'live-function-inventory.json'), JSON.stringify(inventory, null, 2))
  await context.storageState({ path: state }); await context.close()
})
