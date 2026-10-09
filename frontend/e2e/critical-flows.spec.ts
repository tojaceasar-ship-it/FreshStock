import { expect, test } from '@playwright/test'

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    if (!localStorage.getItem('freshstock.language.v1')) {
      localStorage.setItem('freshstock.language.v1', 'pl')
    }
  })
})

test('formularz logowania pokazuje kontrolowany błąd API', async ({ page }) => {
  await page.route('**/api/auth/bootstrap-status', route => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ required: false }),
  }))
  await page.route('**/api/auth/login', route => route.fulfill({
    status: 401,
    contentType: 'application/json',
    body: JSON.stringify({ detail: 'Nieprawidłowe dane logowania' }),
  }))

  await page.goto('/login')
  await expect(page.getByRole('heading', { name: 'FreshStock' })).toBeVisible()
  await page.getByPlaceholder('Wpisz login lub adres e-mail').fill('nieznany')
  await page.getByPlaceholder('••••••••').fill('nieprawidłowe')
  await page.getByRole('button', { name: 'Zaloguj się' }).click()
  await expect(page.getByText(/Nieprawidłowe dane logowania.*HTTP 401.*API: \/api/)).toBeVisible()
})

test('pierwsze uruchomienie pokazuje formularz utworzenia ownera', async ({ page }) => {
  await page.route('**/api/auth/bootstrap-status', route => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ required: true }),
  }))

  await page.goto('/login')
  await expect(page.getByRole('heading', { name: 'Utwórz pierwszego właściciela' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Utwórz konto OWNER' })).toBeVisible()
  await expect(page.getByPlaceholder('Login')).toBeVisible()
})

test('rejestracja tworzy nowy niezależny sklep i kieruje do konfiguracji', async ({ page }) => {
  let registration: Record<string, string> | undefined
  await page.route('**/api/**', async route => {
    const pathname = new URL(route.request().url()).pathname
    if (pathname.endsWith('/auth/bootstrap-status')) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ required: false }) })
    }
    if (pathname.endsWith('/auth/register-store')) {
      registration = route.request().postDataJSON()
      return route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify({ access_token: 'new-store-token', refresh_token: 'new-store-refresh', token_type: 'bearer', expires_in: 1800 }) })
    }
    if (pathname.endsWith('/auth/me')) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ id: 17, tenant_id: 9, email: 'anna@example.com', username: 'anna', full_name: 'Anna Owner', role: 'OWNER', is_active: true }) })
    }
    if (pathname.endsWith('/onboarding')) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ status: 'NOT_STARTED', current_step: 1, completed_steps: [], step_data: {}, settings: {}, priorities: [], notifications: null, locations: [], tasks: [] }) })
    }
    return route.fulfill({ status: 200, contentType: 'application/json', body: '[]' })
  })

  await page.goto('/login')
  await page.getByRole('button', { name: 'Załóż nowy sklep' }).click()
  await page.getByPlaceholder('Nazwa nowego sklepu').fill('Sklep Anny')
  await page.getByPlaceholder('Imię i nazwisko').fill('Anna Owner')
  await page.getByPlaceholder('E-mail').fill('anna@example.com')
  await page.getByPlaceholder('Login').fill('anna')
  await page.getByPlaceholder('Hasło (minimum 12 znaków)').fill('StrongPassword2026')
  await page.getByPlaceholder('Powtórz hasło').fill('StrongPassword2026')
  await page.getByRole('button', { name: 'Utwórz niezależny sklep' }).click()

  await expect(page).toHaveURL(/\/setup$/)
  await expect(page.getByRole('heading', { name: 'Skonfiguruj swój sklep' })).toBeVisible()
  expect(registration).toMatchObject({ store_name: 'Sklep Anny', email: 'anna@example.com', username: 'anna', language: 'pl' })
})

test('owner otwiera skaner i widzi statystyki jakości', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('access_token', 'e2e-token'))
  await page.route('**/api/**', route => {
    const pathname = new URL(route.request().url()).pathname
    const payload = pathname.endsWith('/auth/me')
      ? { id: 1, email: 'owner@example.com', username: 'owner', full_name: 'Owner', role: 'OWNER', is_active: true }
      : pathname.endsWith('/onboarding')
        ? { status: 'COMPLETED' }
        : pathname.endsWith('/scanner/stats')
          ? { total: 3, accepted: 2, rejected: 1, success_rate: 66.7, devices: [] }
          : []
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(payload) })
  })

  await page.goto('/scanner')
  await expect(page.getByRole('heading', { name: 'Skaner kodów kreskowych' })).toBeVisible()
  await expect(page.getByText('Tryb ciągły')).toBeVisible()
  await expect(page.getByText('Jakość skanowania · 30 dni')).toBeVisible()
  await expect(page.getByText('66.7%')).toBeVisible()
})

test('zalogowany owner korzysta z angielskiego i niderlandzkiego interfejsu', async ({ page }) => {
  await page.addInitScript(() => {
    if (!localStorage.getItem('access_token')) {
      localStorage.setItem('access_token', 'e2e-token')
      localStorage.setItem('freshstock.language.v1', 'en')
    }
  })
  await page.route('**/api/**', route => {
    const pathname = new URL(route.request().url()).pathname
    const payload = pathname.endsWith('/auth/me')
      ? { id: 1, email: 'owner@example.com', username: 'owner', full_name: 'Owner', role: 'OWNER', is_active: true }
      : pathname.endsWith('/onboarding')
        ? { status: 'COMPLETED' }
        : pathname.endsWith('/scanner/stats')
          ? { total: 3, accepted: 2, rejected: 1, success_rate: 66.7, devices: [] }
          : []
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(payload) })
  })

  await page.goto('/scanner')
  await expect(page.getByRole('heading', { name: 'Barcode scanner' })).toBeVisible()
  await expect(page.getByText('Products', { exact: true })).toBeVisible()
  await expect(page.getByText('Deliveries', { exact: true })).toBeVisible()
  await expect(page.getByText('Scan quality · 30 days')).toBeVisible()

  await Promise.all([page.waitForNavigation(), page.getByLabel('Language').selectOption('nl')])
  await expect(page.getByRole('heading', { name: 'Barcodescanner' })).toBeVisible()
  await expect(page.getByText('Producten', { exact: true })).toBeVisible()
  await expect(page.getByText('Leveringen', { exact: true })).toBeVisible()
  await expect(page.getByText('Scankwaliteit · 30 dagen')).toBeVisible()
})

test('owner tworzy zadanie dla roli pracownika w Task Management', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('access_token', 'owner-task-token'))
  let createdPayload: Record<string, any> | undefined
  const task = { id: 73, tenant_id: 1, title: 'Sprawdź chłodnię', description: null, task_type: 'EXPIRY_CHECK', priority: 'HIGH', status: 'TODO', stored_status: 'TODO', assigned_user_id: null, assigned_user_name: null, assigned_role: 'EMPLOYEE', source: 'OWNER', due_at: null, product_id: null, product_name: null, batch_id: null, batch_number: null, location_id: null, location_name: null, quantity: null, requires_photo: false, requires_scan: false, requires_comment: false, recurrence_rule: null, recurrence_days: [], checklist_completed: 0, checklist_total: 1, comments_count: 0, attachments_count: 0, checklist: [{ id: 1, text: 'Sprawdź temperaturę', position: 0, is_completed: false }], comments: [], attachments: [], activity: [], created_at: new Date().toISOString(), updated_at: new Date().toISOString() }
  await page.route('**/api/**', route => {
    const request = route.request()
    const pathname = new URL(request.url()).pathname
    let payload: any = []
    let status = 200
    if (pathname.endsWith('/auth/me')) payload = { id: 1, tenant_id: 1, email: 'owner@example.com', username: 'owner', full_name: 'Owner', role: 'OWNER', is_active: true }
    else if (pathname.endsWith('/onboarding')) payload = { status: 'COMPLETED' }
    else if (pathname.endsWith('/tasks/summary')) payload = { total: 0, active: 0, today: 0, counts: { TODO: 0, IN_PROGRESS: 0, COMPLETED: 0, BLOCKED: 0, OVERDUE: 0 }, by_user: [] }
    else if (pathname.endsWith('/tasks') && request.method() === 'POST') { createdPayload = request.postDataJSON(); payload = task; status = 201 }
    else if (pathname.endsWith('/tasks/73')) payload = task
    else if (pathname.endsWith('/users')) payload = [{ id: 2, full_name: 'Jan Kowalski', role: 'EMPLOYEE', is_active: true }]
    return route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(payload) })
  })

  await page.goto('/tasks')
  await expect(page.getByRole('heading', { name: 'Zadania zespołu' })).toBeVisible()
  await page.getByRole('button', { name: /Nowe zadanie/ }).first().click()
  await page.getByLabel('Tytuł *').fill('Sprawdź chłodnię')
  await page.getByLabel('Przypisz do').selectOption('role:EMPLOYEE')
  await page.getByLabel('Typ').selectOption('EXPIRY_CHECK')
  await page.getByLabel('Priorytet').selectOption('HIGH')
  await page.getByLabel('Checklist — jeden krok w wierszu').fill('Sprawdź temperaturę')
  await page.getByRole('button', { name: 'Przypisz zadanie' }).click()

  await expect(page.getByRole('heading', { name: 'Sprawdź chłodnię' })).toBeVisible()
  expect(createdPayload).toMatchObject({ title: 'Sprawdź chłodnię', assigned_role: 'EMPLOYEE', task_type: 'EXPIRY_CHECK', priority: 'HIGH', checklist: ['Sprawdź temperaturę'] })
})

test('pracownik widzi zadania jako pierwszą sekcję dashboardu i może je rozpocząć', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('access_token', 'employee-task-token'))
  let started = false
  const employeeTask = { id: 5, title: 'Usuń przeterminowany nabiał', task_type: 'EXPIRY_CHECK', priority: 'CRITICAL', status: 'TODO', stored_status: 'TODO', assigned_user_id: 4, assigned_user_name: 'Jan', assigned_role: null, due_at: new Date().toISOString(), location_name: 'Chłodnia', product_name: null }
  await page.route('**/api/**', route => {
    const request = route.request()
    const pathname = new URL(request.url()).pathname
    let payload: any = []
    if (pathname.endsWith('/auth/me')) payload = { id: 4, tenant_id: 1, email: 'jan@example.com', username: 'jan', full_name: 'Jan Kowalski', role: 'EMPLOYEE', is_active: true }
    else if (pathname.endsWith('/dashboard')) payload = { requires_attention: {}, kpi: {}, expiring_products: [] }
    else if (pathname.endsWith('/tasks/summary')) payload = { total: 1, active: 1, today: 1, counts: { TODO: 1, IN_PROGRESS: 0, COMPLETED: 0, BLOCKED: 0, OVERDUE: 0 }, by_user: [] }
    else if (pathname.endsWith('/tasks/5/start')) { started = true; payload = { ...employeeTask, status: 'IN_PROGRESS', stored_status: 'IN_PROGRESS' } }
    else if (pathname.endsWith('/tasks')) payload = [employeeTask]
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(payload) })
  })

  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Moje zadania' })).toBeVisible()
  await expect(page.getByText('Usuń przeterminowany nabiał')).toBeVisible()
  await page.getByRole('button', { name: 'ROZPOCZNIJ', exact: true }).click()
  await expect.poll(() => started).toBeTruthy()
})

test('przełącza interfejs między polskim, angielskim i niderlandzkim', async ({ page }) => {
  await page.route('**/api/auth/bootstrap-status', route => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ required: false }),
  }))

  await page.goto('/login')
  const language = page.getByLabel('Language')
  await expect(language).toHaveValue('pl')
  await expect(page.getByRole('button', { name: 'Zaloguj się' })).toBeVisible()

  await Promise.all([page.waitForNavigation(), language.selectOption('en')])
  await expect(page.getByText('Grocery store management system')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Sign in' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Create a new store' })).toBeVisible()

  await Promise.all([page.waitForNavigation(), page.getByLabel('Language').selectOption('nl')])
  await expect(page.getByText('Beheersysteem voor levensmiddelenwinkels')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Inloggen' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Nieuwe winkel aanmaken' })).toBeVisible()

  await page.reload()
  await expect(page.getByLabel('Language')).toHaveValue('nl')
  await expect(page.getByRole('button', { name: 'Inloggen' })).toBeVisible()
})

test('FreshStock Today generuje plan bez duplikowania interfejsu zadań', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('access_token', 'today-owner-token'))
  let generated = false
  const task = { id: 201, title: 'Przecena: Jogurt −45%', task_type: 'MARKDOWN', priority: 'HIGH', status: 'TODO', stored_status: 'TODO', assigned_role: 'EMPLOYEE', assigned_user_name: null, due_at: new Date().toISOString() }
  await page.route('**/api/**', route => {
    const request = route.request()
    const pathname = new URL(request.url()).pathname
    let payload: any = []
    if (pathname.endsWith('/auth/me')) payload = { id: 1, tenant_id: 1, email: 'owner@example.com', username: 'owner', full_name: 'Owner', role: 'OWNER', is_active: true }
    else if (pathname.endsWith('/onboarding')) payload = { status: 'COMPLETED' }
    else if (pathname.endsWith('/today/generate')) { generated = true; payload = { date: '2026-09-27', created: 1, task_ids: [201] } }
    else if (pathname.endsWith('/today')) payload = { date: '2026-09-27', summary: { total: 1, critical: 0, overdue: 0, in_progress: 0 }, tasks: [task] }
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(payload) })
  })

  await page.goto('/today')
  await expect(page.getByRole('heading', { name: 'Co jest najważniejsze dzisiaj?' })).toBeVisible()
  await expect(page.getByText('Przecena: Jogurt −45%')).toBeVisible()
  await expect.poll(() => generated).toBeTruthy()
})

test('Savings Dashboard pokazuje wyłącznie zweryfikowane oszczędności', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('access_token', 'savings-owner-token'))
  await page.route('**/api/**', route => {
    const pathname = new URL(route.request().url()).pathname
    let payload: any = []
    if (pathname.endsWith('/auth/me')) payload = { id: 1, tenant_id: 1, email: 'owner@example.com', username: 'owner', full_name: 'Owner', role: 'OWNER', is_active: true }
    else if (pathname.endsWith('/onboarding')) payload = { status: 'COMPLETED' }
    else if (pathname.endsWith('/savings')) payload = { currency: 'PLN', summary: { verified_savings: 125.5, recovered_revenue: 180, protected_margin: 54.5, units_rescued: 24, current_waste: 30, previous_waste: 50 }, opportunities: { count: 2, at_risk_cost: 80, potential_recovered_revenue: 110 }, by_product: [{ product_id: 7, product_name: 'Jogurt', units: 24, recovered_revenue: 180, protected_cost: 125.5 }], methodology: { verified_savings: 'Metoda A', recovered_revenue: 'Metoda B', waste_reduction: 'Metoda C', tracking_started: 'Od wersji 008' } }
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(payload) })
  })

  await page.goto('/savings')
  await expect(page.getByRole('heading', { name: 'Oszczędności FreshStock' })).toBeVisible()
  await expect(page.getByText('125,50 zł').first()).toBeVisible()
  await expect(page.getByText('Jogurt')).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Jak liczymy wynik?' })).toBeVisible()
})

test('Smart Markdown uzasadnia cenę i aktywuje ją po zatwierdzeniu', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('access_token', 'markdown-owner-token'))
  let approved = false
  let createdPayload: Record<string, any> | undefined
  const suggestion = { product_id: 7, product_name: 'Jogurt', sku: 'JOG-1', batch_id: 12, batch_number: 'LOT-12', expiry_date: '2026-09-29', days_until_expiry: 2, quantity: 20, at_risk_quantity: 18, avg_daily_sales: 0.1, projected_sales_before_expiry: 0.3, sell_through_risk_percent: 90, original_price: 10, suggested_price: 5.5, discount_percent: 45, purchase_price: 5, margin_floor_applied: false, confidence: 'MEDIUM', explanation: '2 dni do terminu; zagrożone 18 z 20 szt.', potential_recovered_revenue: 99 }
  await page.route('**/api/**', route => {
    const request = route.request()
    const pathname = new URL(request.url()).pathname
    let payload: any = []
    let status = 200
    if (pathname.endsWith('/auth/me')) payload = { id: 1, tenant_id: 1, email: 'owner@example.com', username: 'owner', full_name: 'Owner', role: 'OWNER', is_active: true }
    else if (pathname.endsWith('/onboarding')) payload = { status: 'COMPLETED' }
    else if (pathname.endsWith('/promotions/suggestions')) payload = [suggestion]
    else if (pathname.endsWith('/promotions') && request.method() === 'POST') { createdPayload = request.postDataJSON(); payload = { id: 31, product_id: 7, product_name: 'Jogurt', batch_id: 12, original_price: 10, discounted_price: 5.5, discount_percent: 45, reason: suggestion.explanation, status: 'suggested', strategy: 'SMART_MARKDOWN', recommendation_data: {}, created_at: new Date().toISOString() }; status = 201 }
    else if (pathname.endsWith('/promotions/31/approve')) { approved = true; payload = { message: 'Approved' } }
    return route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(payload) })
  })

  await page.goto('/promotions')
  await expect(page.getByRole('heading', { name: 'Inteligentne przeceny' })).toBeVisible()
  await expect(page.getByText('Ryzyko niesprzedania: 90%')).toBeVisible()
  await page.getByRole('button', { name: 'Zatwierdź i aktywuj' }).click()
  await expect.poll(() => approved).toBeTruthy()
  expect(createdPayload).toMatchObject({ product_id: 7, batch_id: 12, discounted_price: 5.5, strategy: 'SMART_MARKDOWN' })
})
