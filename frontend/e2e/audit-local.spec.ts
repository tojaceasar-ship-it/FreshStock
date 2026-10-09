import { expect, test } from '@playwright/test'

test('audit performance store login, product pagination and direct navigation', async ({ page }) => {
  await page.goto('/login')
  await page.locator('#login-username').fill('audit_10_owner')
  await page.locator('#login-password').fill('Audit-only-2026!')
  await page.locator('form button[type="submit"]').click()
  await expect(page).not.toHaveURL(/\/login/)

  await page.goto('/products')
  await expect(page.getByText(/10000 (produktów|products)/)).toBeVisible()
  await expect(page.getByText(/(Strona|Page) 1 (z|of) 100/)).toBeVisible()
  await expect(page.locator('tbody tr')).toHaveCount(100)
  await page.getByRole('button', { name: /Następna|Next/ }).click()
  await expect(page.getByText(/(Strona|Page) 2 (z|of) 100/)).toBeVisible()
  await expect(page.locator('tbody tr')).toHaveCount(100)

  await page.getByPlaceholder(/Szukaj po nazwie|Search by name/i).fill('S10-PERF-09999')
  await expect(page.getByText(/1 (produktów|products)/)).toBeVisible()
  await expect(page.getByText('S10-PERF-09999', { exact: false })).toBeVisible()
})

test('audit products remains usable at mobile viewport', async ({ page, request }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  const apiUrl = process.env.AUDIT_API_URL || 'http://127.0.0.1:8010'
  const login = await request.post(`${apiUrl}/api/auth/login`, { data: { username: 'audit_01_owner', password: 'Audit-only-2026!' } })
  expect(login.ok()).toBeTruthy()
  const tokens = await login.json()
  await page.addInitScript(({ access, refresh }) => {
    localStorage.setItem('access_token', access)
    localStorage.setItem('refresh_token', refresh)
  }, { access: tokens.access_token, refresh: tokens.refresh_token })
  await page.goto('/products')
  await expect(page.getByRole('heading', { name: /Produkty|Products/ })).toBeVisible()
  await expect(page.getByPlaceholder(/Szukaj po nazwie|Search by name/i)).toBeVisible()
  await expect(page.locator('tbody tr')).toHaveCount(30)
})
