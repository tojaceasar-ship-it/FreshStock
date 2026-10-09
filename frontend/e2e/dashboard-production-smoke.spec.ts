import { test, expect } from '@playwright/test'

test('production dashboard redesign renders without browser errors', async ({ page }) => {
  const baseUrl = process.env.FRESHSTOCK_URL || 'https://freshstock-app.vercel.app'
  const username = process.env.FRESHSTOCK_TEST_USER
  const password = process.env.FRESHSTOCK_TEST_PASSWORD
  test.skip(!username || !password, 'Production smoke credentials are not configured')
  const browserErrors: string[] = []
  page.on('pageerror', error => browserErrors.push(error.message))

  await page.goto(`${baseUrl}/login`)
  await page.locator('input').nth(0).fill(username!)
  await page.locator('input[type="password"]').fill(password!)
  await page.locator('form button[type="submit"]').click()
  await page.waitForURL(url => !url.pathname.includes('/login'), { timeout: 30_000 })
  if (page.url().includes('/setup')) {
    await page.goto(baseUrl)
  }
  await expect(page.getByRole('heading', { name: 'Panel główny' })).toBeVisible({ timeout: 30_000 })
  await expect(page.getByText('FreshStock Today', { exact: true })).toBeVisible()
  await expect(page.getByText(/Wartość magazynu|Inventory value/, { exact: true })).toBeVisible()
  await expect(page.getByText(/Asystent operacyjny|Operations assistant/, { exact: true })).toBeVisible()
  await page.screenshot({ path: 'test-results/dashboard-production.png', fullPage: true })
  expect(browserErrors).toEqual([])
})
