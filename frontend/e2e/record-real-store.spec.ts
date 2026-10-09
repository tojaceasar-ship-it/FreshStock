import { expect, test } from '@playwright/test'

const pauseMs = Number(process.env.RECORDING_PAUSE_MS || '0')
const holdMs = Number(process.env.RECORDING_HOLD_MS || '0')

async function pause(page: any, label: string, multiplier = 1) {
  console.log(`[recording] ${label}`)
  await page.waitForTimeout(pauseMs * multiplier)
}

async function api(request: any, method: 'get' | 'post' | 'put', path: string, token: string, data?: unknown) {
  const response = await request[method](path, {
    headers: { Authorization: `Bearer ${token}` },
    data,
  })
  expect(response.ok(), `${method.toUpperCase()} ${path} -> ${response.status()} ${await response.text()}`).toBeTruthy()
  return response.json()
}

test.describe.configure({ mode: 'serial', timeout: 180_000 })

test('NAGRANIE: realny przebieg sklepu FreshStock w przeglądarce', async ({ page, request }) => {
  test.setTimeout(180_000)
  const suffix = String(Date.now()).slice(-8)
  const storeName = `Sklep Nagranie ${suffix}`
  const ownerName = 'Anna Kierownik'
  const username = `record${suffix}`
  const email = `record.${suffix}@freshstock-qa.localhost.pl`
  const password = 'RecordStore2026'
  const supplierName = `Mlekovita Nagranie ${suffix}`
  const sku = `REC-${suffix}`
  const ean = `5907777${suffix.slice(-6)}`
  const productName = `Jogurt Nagranie ${suffix}`
  const tomorrow = new Date(Date.now() + 24 * 60 * 60 * 1000)
  const expiry = tomorrow.toISOString().slice(0, 10)

  await page.addInitScript(() => {
    localStorage.setItem('freshstock.language.v1', 'pl')
  })
  await page.goto('/login')
  await expect(page.getByRole('heading', { name: 'FreshStock' })).toBeVisible()
  await pause(page, 'Start: ekran logowania')

  await page.getByRole('button', { name: /Załóż nowy sklep|Create a new store/ }).click()
  await pause(page, 'Formularz tworzenia nowego sklepu')
  await page.getByPlaceholder('Nazwa nowego sklepu').fill(storeName)
  await page.getByPlaceholder('Imię i nazwisko').fill(ownerName)
  await page.getByPlaceholder('E-mail').fill(email)
  await page.getByPlaceholder('Login').fill(username)
  await page.getByPlaceholder('Hasło (minimum 12 znaków)').fill(password)
  await page.getByPlaceholder('Powtórz hasło').fill(password)
  await pause(page, 'Wypełnione dane sklepu i właściciela')
  await page.getByRole('button', { name: 'Utwórz niezależny sklep' }).click()
  await expect(page).toHaveURL(/\/setup$/)
  await expect(page.getByRole('heading', { name: 'Skonfiguruj swój sklep' })).toBeVisible()
  await pause(page, 'Nowy sklep utworzony, ekran konfiguracji', 2)

  const token = await page.evaluate(() => localStorage.getItem('access_token') || '')
  expect(token).toBeTruthy()

  const setupSteps: Record<number, unknown> = {
    1: { business_type: 'GROCERY', store_size: 'SMALL' },
    2: { store_name: storeName, country: 'PL', currency: 'PLN', timezone: 'Europe/Warsaw', language: 'pl' },
    3: { locations: [{ key: 'SALES_FLOOR', name: 'Sala sprzedaży' }, { key: 'MAIN_WAREHOUSE', name: 'Magazyn' }] },
    4: { fefo_enabled: true, expiry_rules: [1, 3, 7] },
    5: { markdown_suggestions_enabled: true, markdown_rules: [{ days: 3, discount: 30 }] },
    6: { ordering_enabled: true },
    7: { delivery_frequency: 'SEVERAL_WEEK', require_expiry_on_receiving: 'EXPIRY_MANAGED', batch_tracking: 'REQUIRED' },
    8: { sales_method: 'EXTERNAL_POS', provider: 'generic_rest' },
    9: { method: 'START_EMPTY' },
    10: { mode: 'SKIP' },
    11: { users: [] },
    12: { alert_rules: { LOW_STOCK: true, OUT_OF_STOCK: true, INVENTORY_DIFFERENCES: true }, channels: ['IN_APP'] },
    13: { business_priorities: ['EXPIRY_WASTE', 'ORDERING', 'STOCKOUTS'] },
    14: {},
  }
  for (const [step, data] of Object.entries(setupSteps)) {
    await api(request, 'put', `/api/onboarding/steps/${step}`, token, {
      data,
      complete: true,
      next_step: Number(step) < 14 ? Number(step) + 1 : 14,
    })
  }
  await api(request, 'post', '/api/suppliers', token, {
    name: supplierName,
    lead_time_days: 2,
    payment_terms: '7 dni',
    min_order_value: 0,
  })
  const locations = await api(request, 'get', '/api/locations', token)
  const location = locations[0]

  await page.goto('/')
  await expect(page.getByText(storeName).or(page.getByRole('heading', { name: /Dashboard|Co wymaga uwagi/ }))).toBeVisible({ timeout: 15_000 })
  await pause(page, 'Dashboard gotowego sklepu po konfiguracji', 2)

  await page.goto('/products/new')
  await expect(page.getByRole('heading', { name: 'Nowy produkt' })).toBeVisible()
  await pause(page, 'Dodawanie produktu z EAN')
  await page.locator('input').nth(0).fill(sku)
  await page.locator('input').nth(1).fill(ean)
  await page.locator('input').nth(2).fill(productName)
  await page.locator('input[type="number"]').nth(0).fill('2.50')
  await page.locator('input[type="number"]').nth(1).fill('4.99')
  await page.locator('input[type="number"]').nth(2).fill('5')
  await page.locator('input[type="number"]').nth(3).fill('30')
  await page.locator('input[type="number"]').nth(4).fill('12')
  await pause(page, 'Produkt uzupełniony: SKU, EAN, ceny, dostawca, minima')
  await page.getByRole('button', { name: 'Utwórz produkt' }).click()
  await expect(page.getByRole('heading', { name: productName })).toBeVisible({ timeout: 15_000 })
  await pause(page, 'Produkt zapisany i widoczny w kartotece', 2)

  await page.goto('/deliveries')
  await expect(page.getByRole('heading', { name: 'Dostawy' })).toBeVisible()
  await pause(page, 'Zakładka Dostawy')
  await page.getByRole('button', { name: /Nowa dostawa/ }).click()
  await page.locator('select').filter({ hasText: supplierName }).selectOption({ label: supplierName })
  await page.getByPlaceholder('FV/123/2026').fill(`REC-FV-${suffix}`)
  await page.locator('select').filter({ hasText: productName }).selectOption({ label: `${productName} (${sku})` })
  await page.locator('input[placeholder="Ilość"]').fill('18')
  await page.locator('input[placeholder="Cena zakupu"]').fill('2.50')
  await page.locator('input[type="date"]').fill(expiry)
  await page.locator('input[placeholder="Nr partii"]').fill(`REC-BATCH-${suffix}`)
  await page.locator('select').filter({ hasText: location.name }).selectOption({ label: location.name })
  await pause(page, 'Przyjęcie dostawy: partia, data ważności, lokalizacja')
  await page.getByRole('button', { name: 'Zatwierdź dostawę' }).click()
  await expect(page.getByText(`REC-FV-${suffix}`)).toBeVisible({ timeout: 15_000 })
  await pause(page, 'Dostawa zapisana, magazyn zwiększony', 2)

  await page.goto('/sales')
  await expect(page.getByRole('heading', { name: 'Sprzedaż (FEFO)' })).toBeVisible()
  await pause(page, 'Zakładka Sprzedaż FEFO')
  await page.locator('select').filter({ hasText: productName }).selectOption({ label: `${productName} - stan 18` })
  await page.locator('input[type="number"]').fill('3')
  await pause(page, 'Sprzedaż 3 sztuk z automatycznym FEFO')
  await page.getByRole('button', { name: 'Sprzedaj (FEFO)' }).click()
  await expect(page.getByText(/ręcznie|manual/i).first()).toBeVisible({ timeout: 15_000 })
  await pause(page, 'Sprzedaż widoczna na liście, stan powinien spaść do 15', 2)

  await page.goto('/products')
  await expect(page.getByText(productName)).toBeVisible()
  await expect(page.getByText(/15 szt|15/).first()).toBeVisible()
  await pause(page, 'Produkty: widać zaktualizowany stan po sprzedaży', 2)

  await page.goto('/orders')
  await expect(page.getByRole('heading', { name: 'Zamówienia' })).toBeVisible()
  await pause(page, 'Zakładka Zamówienia z sugestiami uzupełnienia stanów', 2)

  await page.goto('/')
  await pause(page, 'Powrót na dashboard po operacjach', 2)

  console.log(`[recording] Koniec. Przeglądarka zostaje otwarta przez ${holdMs} ms, żeby dokończyć nagrywanie.`)
  await page.waitForTimeout(holdMs)
})
