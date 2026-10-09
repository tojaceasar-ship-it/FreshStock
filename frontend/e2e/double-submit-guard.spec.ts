import { expect, test } from '@playwright/test'

// Runs against the local backend through the vite dev-server proxy
// (/api -> http://localhost:8000). Verifies the client-side
// double-submit guard and the Idempotency-Key header.

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    if (!localStorage.getItem('freshstock.language.v1')) {
      localStorage.setItem('freshstock.language.v1', 'pl')
    }
  })
})

test('double-click "Sprzedaj" wysyła dokładnie jedno żądanie z Idempotency-Key', async ({ page }) => {
  const salePosts: { headers: Record<string, string> }[] = []
  page.on('request', (req) => {
    if (req.url().includes('/api/sales') && req.method() === 'POST') {
      salePosts.push({ headers: req.headers() })
    }
  })

  // Hold every POST /api/sales in flight for 800 ms so the second
  // click of the double-click lands while the first request is still
  // pending - exactly the race the guard must collapse.
  await page.route('**/api/sales', async (route) => {
    if (route.request().method() === 'POST') {
      await new Promise((r) => setTimeout(r, 800))
    }
    await route.continue()
  })

  await page.goto('/login')
  await page.getByPlaceholder('Wpisz login lub adres e-mail').fill('manager')
  await page.getByPlaceholder('••••••••').fill('TestManager123!')
  await page.getByRole('button', { name: 'Zaloguj się' }).click()
  // A bare "**/" glob matches every URL - wait for the exact
  // dashboard path instead, so the login POST is never aborted mid-flight.
  await page.waitForURL((url) => url.pathname === '/')

  await page.goto('/sales')
  // Native select + React controlled: selectOption doesn't fire onChange.
  // Target the product select (2nd select on page), select by value, then dispatch change.
  const productSelect = page.locator('main select').first()
  await productSelect.selectOption('1')
  await productSelect.dispatchEvent('change')
  await page.getByRole('button', { name: 'Sprzedaj (FEFO)' }).dblclick()

  // One sale row rendered after the query invalidation.
  await expect(page.locator('table tbody tr')).toHaveCount(1)

  // Exactly one POST reached the network - the second click was
  // deduplicated client-side while the first was in flight.
  expect(salePosts).toHaveLength(1)

  // The mutation carried a UUID-shaped Idempotency-Key, so a
  // token-refresh retry would replay instead of executing twice.
  const key = salePosts[0].headers['idempotency-key']
  expect(key).toMatch(UUID_RE)
})

test('powtórne kliknięcie po odpowiedzi tworzy drugą sprzedaż (guard nie blokuje intencji)', async ({ page }) => {
  await page.goto('/login')
  await page.getByPlaceholder('Wpisz login lub adres e-mail').fill('manager')
  await page.getByPlaceholder('••••••••').fill('TestManager123!')
  await page.getByRole('button', { name: 'Zaloguj się' }).click()
  await page.waitForURL((url) => url.pathname === '/')

  await page.goto('/sales')
  const productSelect = page.locator('main select').first()
  await productSelect.selectOption('1')
  await productSelect.dispatchEvent('change')
  const sell = page.getByRole('button', { name: 'Sprzedaj (FEFO)' })
  await sell.click()
  await expect(page.locator('table tbody tr')).toHaveCount(1)

  // The first request settled, so the guard released the fingerprint -
  // a deliberate second submission must go through.
  await sell.click()
  await expect(page.locator('table tbody tr')).toHaveCount(2)
})
