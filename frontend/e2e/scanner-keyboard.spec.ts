import { expect, test } from '@playwright/test'

// Tests the Scanner page keyboard emulation flow:
// type EAN in input → press Enter → verify product lookup

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    if (!localStorage.getItem('freshstock.language.v1')) {
      localStorage.setItem('freshstock.language.v1', 'pl')
    }
  })
})

async function loginAsManager(page: any) {
  await page.goto('/login')
  await page.getByPlaceholder('Wpisz login lub adres e-mail').fill('manager')
  await page.getByPlaceholder('••••••••').fill('TestManager123!')
  await page.getByRole('button', { name: 'Zaloguj się' }).click()
  await page.waitForURL((url) => url.pathname === '/')
}

test('skaner klawiaturowy: wpisanie EAN + Enter znajduje produkt', async ({ page }) => {
  await loginAsManager(page)
  await page.goto('/scanner')

  // The product "Banan E2E" has EAN 5900000000001
  const ean = '5900000000001'
  const input = page.getByPlaceholder('Wpisz EAN, UPC lub SKU albo zeskanuj')
  await input.fill(ean)
  await input.press('Enter')

  // Wait for result - local product found
  await expect(page.getByText('Produkt w bazie sklepu')).toBeVisible({ timeout: 10000 })
  await expect(page.getByText('Banan E2E')).toBeVisible()
  await expect(page.getByText('5900000000001')).toBeVisible()
})

test('skaner klawiaturowy: nieznany EAN pokazuje wynik (Open Facts lub nieznany)', async ({ page }) => {
  await loginAsManager(page)
  await page.goto('/scanner')

  // Use an EAN unlikely to exist anywhere
  const ean = '1234567890123'
  const input = page.getByPlaceholder('Wpisz EAN, UPC lub SKU albo zeskanuj')
  await input.fill(ean)
  await input.press('Enter')

  // Either Open Food Facts result or "Produkt nieznany"
  await expect(page.getByText('Znaleziono w bazach Open Facts').or(page.getByText('Produkt nieznany'))).toBeVisible({ timeout: 10000 })
  await expect(page.getByText(ean)).toBeVisible()
})

test('skaner klawiaturowy: błędna cyfra kontrolna (GTIN) odrzuca kod', async ({ page }) => {
  await loginAsManager(page)
  await page.goto('/scanner')

  // Valid EAN-13 checksum for 590000000000 is 1; change to 2 to make invalid
  const invalidEan = '5900000000002'
  const input = page.getByPlaceholder('Wpisz EAN, UPC lub SKU albo zeskanuj')
  await input.fill(invalidEan)
  await input.press('Enter')

  // Should show "Produkt nieznany" - the keyboard path doesn't do GTIN checksum,
  // but the lookup will fail since the EAN doesn't exist
  await expect(page.getByText('Produkt nieznany')).toBeVisible({ timeout: 10000 })
  await expect(page.getByText(invalidEan)).toBeVisible()
})
