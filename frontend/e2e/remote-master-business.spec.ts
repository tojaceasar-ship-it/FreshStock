import { test, expect, Page } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'

const STOCK = 'https://frontend-navy-nu-73.vercel.app/'
const POS = 'https://freshpos-two.vercel.app/'
const evidence = path.resolve('..', 'audit', 'remote-master')

async function shot(page: Page, name: string) {
  await page.screenshot({ path: path.join(evidence, name), fullPage: true })
}

async function next(page: Page) {
  await page.getByRole('button', { name: 'Kontynuuj' }).click()
  await expect(page.getByText(/Krok \d+ z 14/)).toBeVisible()
}

test('MASTER: nowy sklep i pełny onboarding przez wdrożony UI w dwóch kartach', async ({ browser }) => {
  test.setTimeout(240_000)
  fs.mkdirSync(evidence, { recursive: true })
  const stamp = Date.now()
  const short = String(stamp).slice(-8)
  const storeName = `FreshStock QA E2E ${stamp}`
  const password = `QaStore${short}Ab!`
  const context = await browser.newContext({ viewport: { width: 1600, height: 1000 } })
  await context.addInitScript(() => localStorage.setItem('freshstock.language.v1', 'pl'))
  const stock = await context.newPage()
  const pos = await context.newPage()
  const browserErrors: string[] = []
  stock.on('console', message => { if (message.type() === 'error') browserErrors.push(`console: ${message.text()}`) })
  stock.on('pageerror', error => browserErrors.push(`pageerror: ${error.message}`))
  await Promise.all([stock.goto(STOCK), pos.goto(POS)])
  await expect(stock).toHaveURL(/\/login/)
  await expect(pos).toHaveTitle(/FreshPOS/)
  await shot(pos, '01-pos-równolegle.png')

  await stock.getByRole('button', { name: /Załóż nowy sklep|Create a new store/ }).click()
  await stock.getByPlaceholder('Nazwa nowego sklepu').fill(storeName)
  await stock.getByPlaceholder('Imię i nazwisko').fill('Owner QA E2E')
  await stock.getByPlaceholder('E-mail').fill(`owner.${stamp}@freshstock-e2e.pl`)
  await stock.getByPlaceholder('Login').fill(`owner_${short}`)
  await stock.getByPlaceholder('Hasło (minimum 12 znaków)').fill(password)
  await stock.getByPlaceholder('Powtórz hasło').fill(password)
  await shot(stock, '02-rejestracja-sklepu.png')
  const registerResponsePromise = stock.waitForResponse(response => response.url().includes('/auth/register-store'))
  await stock.getByRole('button', { name: 'Utwórz niezależny sklep' }).click()
  const registerResponse = await registerResponsePromise
  const registerStatus = registerResponse.status()
  let registerBody = '[response body unavailable after navigation]'
  try { registerBody = await registerResponse.text() } catch { /* navigation may release a successful body */ }
  fs.writeFileSync(path.join(evidence, 'registration-diagnostic.json'), JSON.stringify({
    timestamp: new Date().toISOString(), status: registerStatus,
    response: registerStatus >= 400 ? registerBody : '[success body redacted]', browserErrors,
  }, null, 2))
  expect(registerStatus, `register-store failed: ${registerBody}`).toBeLessThan(400)
  await expect(stock).toHaveURL(/\/setup/, { timeout: 30_000 })

  await stock.getByRole('button', { name: 'Supermarket' }).click(); await next(stock)
  await stock.getByLabel('Nazwa sklepu *').fill(storeName)
  await stock.getByLabel('Nazwa firmy').fill('FreshStock QA Test Company')
  await stock.getByLabel('Adres').fill('Testowa 1, 00-001 Warszawa')
  await stock.getByLabel('NIP / VAT').fill('PL0000000000')
  await stock.getByLabel('Waluta *').fill('EUR')
  await stock.getByLabel('Powierzchnia sklepu (m²)').fill('650')
  await stock.getByLabel('Liczba pracowników').fill('12')
  await stock.getByLabel('Przybliżona liczba SKU').fill('3500')
  await stock.getByLabel('Liczba stanowisk POS').fill('4')
  await next(stock)

  for (const location of ['Sala sprzedaży', 'Magazyn główny', 'Chłodnia', 'Mroźnia', 'Zaplecze']) {
    await stock.getByRole('button', { name: location, exact: true }).click()
  }
  await shot(stock, '03-lokalizacje.png'); await next(stock)
  await stock.getByRole('button', { name: /Zaawansowany/ }).click(); await next(stock)
  await stock.getByRole('button', { name: /Włącz kolejność/ }).click(); await next(stock)
  await stock.getByRole('button', { name: 'Włącz sugestie' }).click(); await next(stock)
  await stock.getByLabel('Częstotliwość dostaw').selectOption('SEVERAL_WEEK')
  await stock.getByLabel('Wymagać daty ważności przy odbiorze?').selectOption('ALWAYS')
  await stock.getByLabel('Śledzić numery partii?').selectOption('ALWAYS'); await next(stock)
  await stock.getByRole('button', { name: 'Zewnętrzny POS' }).click()
  await stock.getByRole('button', { name: 'Generic REST' }).click(); await next(stock)
  await stock.getByRole('button', { name: 'Zacznij bez produktów' }).click(); await next(stock)
  await stock.getByRole('button', { name: 'Dodaj dostawcę' }).click()
  await stock.getByLabel('Nazwa *').fill('QA Supplier Onboarding')
  await stock.getByLabel(/E-?mail/).fill(`supplier.${stamp}@freshstock-e2e.pl`)
  await stock.getByLabel('Telefon').fill('+48100000000')
  await stock.getByLabel('NIP / VAT').fill('PL1111111111'); await next(stock)

  const roles = ['MANAGER', 'WAREHOUSE', 'EMPLOYEE', 'VIEWER']
  for (let i = 0; i < roles.length; i++) {
    await stock.getByRole('button', { name: '+ Zaproś użytkownika' }).click()
    await stock.getByLabel('Imię i nazwisko').nth(i).fill(`${roles[i]} QA`)
    await stock.getByLabel(/E-?mail/).nth(i).fill(`${roles[i].toLowerCase()}.${stamp}@freshstock-e2e.pl`)
    await stock.getByLabel('Rola').nth(i).selectOption(roles[i])
    await stock.getByLabel('Hasło startowe (min. 12 znaków)').nth(i).fill(password)
  }
  await shot(stock, '04-użytkownicy-role.png'); await next(stock)
  await next(stock)
  for (const priority of ['Straty przez terminy ważności', 'Braki magazynowe', 'Inwentaryzacja', 'Zamawianie', 'Organizacja sklepu']) {
    await stock.getByRole('button', { name: priority, exact: true }).click()
  }
  await next(stock)
  await shot(stock, '05-podsumowanie-onboardingu.png')
  await stock.getByRole('button', { name: 'Zakończ konfigurację' }).click()
  await expect(stock).toHaveURL(STOCK, { timeout: 30_000 })
  await expect(stock.getByRole('link', { name: 'Produkty' })).toBeVisible()
  await shot(stock, '06-dashboard-nowego-sklepu.png')

  await stock.getByRole('link', { name: 'Użytkownicy' }).click()
  const userRows = stock.locator('main tbody tr')
  await expect(userRows).toHaveCount(5)
  await expect(stock.getByText('Cezary ja (Cezary)')).toHaveCount(0)
  await shot(stock, '06b-tenant-users-isolated.png')

  const links = await stock.getByRole('link').allTextContents()
  const posButtons = await pos.getByRole('button').allTextContents()
  fs.writeFileSync(path.join(evidence, 'tenant-summary.json'), JSON.stringify({
    timestamp: new Date().toISOString(), storeName, freshStockUrl: stock.url(), freshPosUrl: pos.url(),
    discoveredFreshStockLinks: links, discoveredFreshPosActions: posButtons,
    credentials: 'redacted',
  }, null, 2))
  await context.storageState({ path: path.join(evidence, 'owner-storage-state.json') })
  await context.close()
})
