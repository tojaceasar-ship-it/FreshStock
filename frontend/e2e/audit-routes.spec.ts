import { expect, test } from '@playwright/test'

const apiUrl = process.env.AUDIT_API_URL || 'http://127.0.0.1:8010'

test('all application routes render without page errors or server failures', async ({ page, request }) => {
  const login = await request.post(`${apiUrl}/api/auth/login`, {
    data: { username: 'audit_01_owner', password: 'Audit-only-2026!' },
  })
  expect(login.ok()).toBeTruthy()
  const tokens = await login.json()
  const products = await request.get(`${apiUrl}/api/products?limit=1`, {
    headers: { Authorization: `Bearer ${tokens.access_token}` },
  })
  expect(products.ok()).toBeTruthy()
  const productId = (await products.json())[0].id
  await page.addInitScript(({ access, refresh }) => {
    localStorage.setItem('access_token', access)
    localStorage.setItem('refresh_token', refresh)
  }, { access: tokens.access_token, refresh: tokens.refresh_token })

  const pageErrors: string[] = []
  const serverErrors: string[] = []
  page.on('pageerror', error => pageErrors.push(error.message))
  page.on('response', response => {
    if (response.status() >= 500) serverErrors.push(`${response.status()} ${response.url()}`)
  })

  const routes = [
    '/', '/today', '/products', '/products/new', `/products/${productId}`,
    '/batches', '/deliveries', '/orders', '/sales', '/waste', '/promotions',
    '/alerts', '/scanner', '/reports', '/savings', '/locations', '/inventory',
    '/ai', '/users', '/integrations', '/tasks', '/settings/store', '/subscription',
  ]
  for (const route of routes) {
    await page.goto(route)
    await expect(page.locator('body')).not.toBeEmpty()
    await expect(page).not.toHaveURL(/\/login$/)
  }

  expect(pageErrors).toEqual([])
  expect(serverErrors).toEqual([])
})

test('stored script-like product text is rendered inert', async ({ page }) => {
  await page.goto('/login')
  await page.locator('#login-username').fill('audit_09_manager')
  await page.locator('#login-password').fill('Audit-only-2026!')
  await page.locator('form button[type="submit"]').click()
  await expect(page).not.toHaveURL(/\/login$/)
  await page.goto('/products')
  await page.getByPlaceholder(/Szukaj po nazwie|Search by name/i).fill('<script>tekst</script>')
  await expect(page.getByText('<script>tekst</script>', { exact: false }).first()).toBeVisible()
  expect(await page.locator('script').evaluateAll(nodes => nodes.some(node => node.textContent?.includes('tekst')))).toBeFalsy()
})
