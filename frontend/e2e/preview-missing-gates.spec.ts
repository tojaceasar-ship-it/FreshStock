import { expect, test, type APIRequestContext, type Page } from '@playwright/test'

const backend = process.env.PREVIEW_BACKEND_URL
const frontend = process.env.PREVIEW_FRONTEND_URL
const backendBypass = process.env.PREVIEW_BACKEND_BYPASS
const frontendBypass = process.env.PREVIEW_FRONTEND_BYPASS
const enabled = Boolean(backend && frontend && backendBypass && frontendBypass)

test.skip(!enabled, 'Preview URLs and bypass secrets are required')
test.describe.configure({ mode: 'serial' })

async function login(request: APIRequestContext, username = 'manager', password = 'TestManager123!') {
  const response = await request.post(`${backend}/api/auth/login`, {
    headers: { 'x-vercel-protection-bypass': backendBypass! }, data: { username, password },
  })
  expect(response.status()).toBe(200)
  return (await response.json()).access_token as string
}

function headers(token: string, extra: Record<string, string> = {}) {
  return { 'x-vercel-protection-bypass': backendBypass!, Authorization: `Bearer ${token}`, ...extra }
}

async function firstId(request: APIRequestContext, token: string, path: string) {
  const response = await request.get(`${backend}/api/${path}`, { headers: headers(token) })
  expect(response.status()).toBe(200)
  return Number((await response.json())[0].id)
}

async function createStockedProduct(request: APIRequestContext, token: string, runId: string, initial = 20) {
  const supplierId = await firstId(request, token, 'suppliers')
  const locationId = await firstId(request, token, 'locations')
  const created = await request.post(`${backend}/api/products`, {
    headers: headers(token), data: {
      sku: `QA-${runId}`, ean: `9${runId.replace(/\D/g, '').slice(-11).padStart(11, '0')}1`,
      name: `QA ${runId}`, purchase_price: '1.00', selling_price: '2.00',
      min_stock: 10, target_stock: 30, safety_stock: 2, default_supplier_id: supplierId,
    },
  })
  expect(created.status()).toBe(200)
  const product = await created.json()
  if (initial > 0) {
    const delivery = await request.post(`${backend}/api/deliveries`, {
      headers: headers(token), data: {
        supplier_id: supplierId, document_number: `INIT-${runId}`,
        items: [{ product_id: product.id, quantity_ordered: initial, quantity_received: initial,
          purchase_price: '1.00', batch_number: `INIT-${runId}`, location_id: locationId }],
      },
    })
    expect(delivery.status()).toBe(200)
  }
  return { product, supplierId, locationId }
}

async function productStock(request: APIRequestContext, token: string, id: number) {
  const response = await request.get(`${backend}/api/products/${id}`, { headers: headers(token) })
  expect(response.status()).toBe(200)
  return Number((await response.json()).total_stock)
}

async function browserLogin(page: Page) {
  await page.addInitScript(() => localStorage.setItem('freshstock.language.v1', 'pl'))
  await page.route(`${backend}/**`, route => route.continue({
    headers: { ...route.request().headers(), 'x-vercel-protection-bypass': backendBypass! },
  }))
  await page.goto(`${frontend}/login?x-vercel-protection-bypass=${frontendBypass}&x-vercel-set-bypass-cookie=true`)
  await page.getByPlaceholder('Wpisz login lub adres e-mail').fill('manager')
  await page.getByPlaceholder('••••••••').fill('TestManager123!')
  await page.getByRole('button', { name: 'Zaloguj się' }).click()
  await page.waitForURL(url => url.pathname === '/')
}

test('double-submit uses an isolated run product and creates exactly one sale', async ({ page, request }) => {
  const runId = `DS-${Date.now()}`
  const token = await login(request)
  const { product } = await createStockedProduct(request, token, runId)
  const before = await productStock(request, token, product.id)
  const posts: string[] = []
  await browserLogin(page)
  page.on('request', req => { if (req.method() === 'POST' && req.url().endsWith('/api/sales')) posts.push(req.url()) })
  await page.goto(`${frontend}/sales`)
  const select = page.locator('main select').first()
  await select.selectOption(String(product.id)); await select.dispatchEvent('change')
  await page.getByRole('button', { name: 'Sprzedaj (FEFO)' }).dblclick()
  await expect.poll(() => productStock(request, token, product.id)).toBe(before - 1)
  expect(posts).toHaveLength(1)
})

test('Generic CSV import changes stock once and replay is duplicate', async ({ request }) => {
  const runId = `CSV-${Date.now()}`
  const token = await login(request)
  const { product } = await createStockedProduct(request, token, runId)
  const before = await productStock(request, token, product.id)
  const integrationResponse = await request.post(`${backend}/api/integrations`, {
    headers: headers(token), data: { provider: 'generic_csv', name: `Generic CSV ${runId}`, sync_mode: 'CSV' },
  })
  expect(integrationResponse.status()).toBe(200)
  const integration = await integrationResponse.json()
  const transaction = `TX-${runId}`
  const csv = `transaction_id,date,sku,name,quantity,unit_price,total\n${transaction},2026-10-09,${product.sku},${product.name},1,2.00,2.00\n`
  const mapping = JSON.stringify({ transaction_id:'transaction_id', date:'date', sku:'sku', name:'name', quantity:'quantity', unit_price:'unit_price', total:'total' })
  const multipart = { integration_id: String(integration.id), mapping, delimiter: ',', date_format: '%Y-%m-%d', file: { name:`${runId}.csv`, mimeType:'text/csv', buffer:Buffer.from(csv) } }
  const first = await request.post(`${backend}/api/integrations/csv/import`, { headers: headers(token), multipart })
  expect(first.status()).toBe(200); expect((await first.json()).processed).toBe(1)
  expect(await productStock(request, token, product.id)).toBe(before - 1)
  const second = await request.post(`${backend}/api/integrations/csv/import`, { headers: headers(token), multipart })
  expect(second.status()).toBe(200); expect((await second.json()).results[0].duplicate).toBeTruthy()
  expect(await productStock(request, token, product.id)).toBe(before - 1)
})

test('full order cycle records suggestion, PO, partial/full receipt, stock, batch, history and dashboard', async ({ request }) => {
  const runId = `ORD-${Date.now()}`
  const token = await login(request)
  const { product, supplierId, locationId } = await createStockedProduct(request, token, runId, 1)
  const before = await productStock(request, token, product.id)
  const suggestions = await request.get(`${backend}/api/purchase-orders/suggestions`, { headers: headers(token) })
  expect(suggestions.status()).toBe(200); expect((await suggestions.json()).some((x:any) => x.product_id === product.id)).toBeTruthy()
  const poResponse = await request.post(`${backend}/api/purchase-orders`, { headers: headers(token), data: {
    supplier_id:supplierId, notes:runId, items:[{product_id:product.id, quantity:10, purchase_price:'1.00'}],
  } })
  expect(poResponse.status()).toBe(200); const po = await poResponse.json()
  for (const status of ['sent','confirmed']) {
    const response = await request.put(`${backend}/api/purchase-orders/${po.id}/status?status=${status}`, {
      headers:headers(token, { 'Idempotency-Key': `${runId}-${status}` }),
    })
    expect(response.status(), `${status}: ${await response.text()}`).toBe(200)
  }
  for (const [qty, suffix] of [[4,'P'],[6,'F']] as const) {
    const response = await request.post(`${backend}/api/deliveries`, { headers:headers(token), data:{
      supplier_id:supplierId,purchase_order_id:po.id,document_number:`${runId}-${suffix}`,
      items:[{product_id:product.id,quantity_ordered:10,quantity_received:qty,purchase_price:'1.00',batch_number:`${runId}-${suffix}`,location_id:locationId}],
    } })
    expect(response.status()).toBe(200)
  }
  expect(await productStock(request, token, product.id)).toBe(before + 10)
  const finalPo = await request.get(`${backend}/api/purchase-orders/${po.id}`, { headers:headers(token) })
  expect((await finalPo.json()).status).toBe('delivered')
  const deliveries = await request.get(`${backend}/api/deliveries`, { headers:headers(token) })
  const docs=(await deliveries.json()).filter((x:any)=>x.purchase_order_id===po.id)
  expect(docs).toHaveLength(2); expect(docs.every((x:any)=>x.items[0].batch_number.startsWith(runId))).toBeTruthy()
  const dashboard = await request.get(`${backend}/api/dashboard`, { headers:headers(token) })
  expect(dashboard.status()).toBe(200); expect(JSON.stringify(await dashboard.json())).toContain(runId)
})

test('monitoring contract allows Viewer because Viewer has dashboard:read', async ({ request }) => {
  const viewer = await login(request, 'viewer', 'TestViewer123!')
  const response = await request.get(`${backend}/api/monitoring/metrics`, { headers:headers(viewer) })
  expect(response.status()).toBe(200)
})
