import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertCircle, CheckCircle, FileSpreadsheet, Link2, Plug, RefreshCw, Server, Settings2, Store, Upload } from 'lucide-react'
import { Link } from 'react-router-dom'
import { api } from '../lib/api'
import { getLocale } from '../lib/i18n'

const providerCards = [
  { provider: 'generic_csv', name: 'Generic CSV', description: 'Import plików sprzedażowych z mapowaniem kolumn.', icon: FileSpreadsheet, action: 'Configure' },
  { provider: 'generic_rest', name: 'Generic REST', description: 'Kontrolowane połączenie HTTPS do API klienta.', icon: Server, action: 'Configure' },
  { provider: 'square', name: 'Square', description: 'Kontrakt adaptera OAuth i webhooków Square.', icon: Store, action: 'Connect' },
  { provider: 'lightspeed', name: 'Lightspeed', description: 'Kontrakt adaptera OAuth i webhooków Lightspeed.', icon: Store, action: 'Connect' },
  { provider: 'local_bridge', name: 'FreshStock Bridge', description: 'Bezpieczny push zdarzeń z lokalnego programu Windows.', icon: Link2, action: 'Setup' },
]

const tabs = ['Overview', 'CSV Import', 'Products Mapping', 'Sync History', 'Errors', 'Settings']
const standardColumns = ['date', 'time', 'transaction_id', 'ean', 'sku', 'external_product_id', 'name', 'quantity', 'unit_price', 'total', 'location']

function formatDate(value?: string) {
  return value ? new Date(value).toLocaleString(getLocale()) : '—'
}

export default function Integrations() {
  const qc = useQueryClient()
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [tab, setTab] = useState('Overview')
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')
  const [bridgeCredentials, setBridgeCredentials] = useState<any>(null)
  const { data: integrations = [] } = useQuery({ queryKey: ['integrations'], queryFn: async () => (await api.get('/integrations')).data })
  const selected = integrations.find((item: any) => item.id === selectedId)

  const createIntegration = useMutation({
    mutationFn: async (payload: any) => (await api.post('/integrations', payload)).data,
    onSuccess: async data => {
      setSelectedId(data.id)
      setTab(data.provider === 'generic_csv' ? 'CSV Import' : 'Overview')
      setError('')
      if (data.provider === 'generic_rest') {
        try {
          await api.post(`/integrations/${data.id}/test`)
          setNotice('Integracja została utworzona i połączenie działa')
        } catch (err: any) {
          setError(err?.response?.data?.detail || 'Integracja została utworzona, ale test połączenia nie powiódł się')
        }
      } else {
        setNotice('Integracja została utworzona')
      }
      qc.invalidateQueries({ queryKey: ['integrations'] })
    },
    onError: (err: any) => setError(err?.response?.data?.detail || 'Nie udało się utworzyć integracji')
  })

  const setupBridge = useMutation({
    mutationFn: async ({ card, storeId }: any) => {
      const integration = (await api.post('/integrations', { provider: card.provider, name: card.name, sync_mode: 'BRIDGE' })).data
      const credentials = (await api.post('/bridge/register', { integration_id: integration.id, store_id: storeId })).data
      return { integration, credentials }
    },
    onSuccess: ({ integration, credentials }) => {
      setSelectedId(integration.id); setTab('Overview'); setBridgeCredentials(credentials)
      setNotice('Bridge został zarejestrowany. Skopiuj sekret — nie będzie ponownie wyświetlony.')
      setError(''); qc.invalidateQueries({ queryKey: ['integrations'] })
    },
    onError: (err: any) => setError(err?.response?.data?.detail || 'Nie udało się skonfigurować Bridge')
  })

  const configureProvider = async (card: any) => {
    const existing = integrations.find((item: any) => item.provider === card.provider && item.status !== 'DISABLED')
    if (existing) { setSelectedId(existing.id); setTab(card.provider === 'generic_csv' ? 'CSV Import' : 'Overview'); return }
    if (card.provider === 'generic_rest') {
      const baseUrl = window.prompt('Base URL API (wyłącznie publiczne HTTPS):', 'https://freshpos-two.vercel.app/api')
      if (!baseUrl) return
      const salesEndpoint = window.prompt('Ścieżka endpointu sprzedaży:', '/sales')
      const productsEndpoint = window.prompt('Ścieżka endpointu produktów:', '/products')
      const refundsEndpoint = window.prompt('Ścieżka endpointu zwrotów:', '/refunds')
      const token = window.prompt('Bearer token POS (zostanie zaszyfrowany):', 'freshpos_sim_demo0000demo0000demo0000')
      if (!salesEndpoint || !productsEndpoint || !refundsEndpoint || !token) {
        setError('Adres, endpointy i Bearer token są wymagane')
        return
      }
      createIntegration.mutate({ provider: card.provider, name: card.name, sync_mode: 'HYBRID', settings: { base_url: baseUrl, sales_endpoint: salesEndpoint, products_endpoint: productsEndpoint, refunds_endpoint: refundsEndpoint, auth_type: 'bearer' }, credentials: token ? { token } : null })
      return
    }
    if (card.provider === 'local_bridge') {
      const storeId = window.prompt('Identyfikator sklepu/stanowiska Bridge:')
      if (!storeId) return
      setupBridge.mutate({ card, storeId })
      return
    }
    createIntegration.mutate({ provider: card.provider, name: card.name, sync_mode: card.provider === 'generic_csv' ? 'CSV' : card.provider === 'local_bridge' ? 'BRIDGE' : 'HYBRID' })
  }

  return (
    <div className="space-y-6">
      <div><h1 className="text-2xl font-bold">Settings → Integrations</h1><p className="text-sm text-gray-500">Modułowy gateway POS/ERP z idempotencją, FEFO i izolacją tenantów.</p></div>
      {notice && <div className="bg-green-50 border border-green-200 text-green-800 rounded-xl p-3 text-sm">{notice}</div>}
      {error && <div className="bg-red-50 border border-red-200 text-red-800 rounded-xl p-3 text-sm">{error}</div>}
      {bridgeCredentials && <div className="bg-amber-50 border border-amber-300 rounded-xl p-4 text-sm"><b>Dane FreshStock Bridge — widoczne tylko teraz</b><div className="mt-2 font-mono break-all">Bridge ID: {bridgeCredentials.bridge_id}</div><div className="font-mono break-all">Secret: {bridgeCredentials.secret}</div><button onClick={() => navigator.clipboard.writeText(JSON.stringify({ bridge_id: bridgeCredentials.bridge_id, secret: bridgeCredentials.secret }))} className="mt-3 border border-amber-600 px-3 py-1.5 rounded-lg">Kopiuj konfigurację</button><button onClick={() => setBridgeCredentials(null)} className="ml-2 px-3 py-1.5">Ukryj</button></div>}

      <div className="grid md:grid-cols-2 xl:grid-cols-5 gap-4">
        {providerCards.map(card => {
          const integration = integrations.find((item: any) => item.provider === card.provider && item.status !== 'DISABLED')
          return <div key={card.provider} className="bg-white border rounded-2xl p-4 flex flex-col gap-3">
            <card.icon className="w-7 h-7 text-green-600" />
            <div><h2 className="font-semibold">{card.name}</h2><p className="text-xs text-gray-500 mt-1">{card.description}</p></div>
            <div className="text-xs mt-auto"><span className={`px-2 py-1 rounded-full ${integration?.health === 'OK' ? 'bg-green-100 text-green-700' : integration?.health === 'ERROR' ? 'bg-red-100 text-red-700' : integration?.health === 'WARNING' ? 'bg-amber-100 text-amber-700' : 'bg-gray-100 text-gray-600'}`}>{integration ? `${integration.status} · ${integration.health}` : 'NOT CONFIGURED'}</span></div>
            <button onClick={() => configureProvider(card)} disabled={createIntegration.isPending} className="border border-green-600 text-green-700 rounded-xl py-2 text-sm font-medium">{integration ? 'Open' : card.action}</button>
          </div>
        })}
      </div>

      {integrations.length > 0 && <div className="bg-white border rounded-2xl p-4 flex flex-wrap gap-2">{integrations.map((item: any) => <button key={item.id} onClick={() => { setSelectedId(item.id); setTab('Overview') }} className={`px-3 py-2 rounded-xl text-sm ${selectedId === item.id ? 'bg-green-600 text-white' : 'bg-gray-100'}`}>{item.name} · {item.status}</button>)}</div>}

      {selected && <div className="bg-white border rounded-2xl overflow-hidden">
        <div className="border-b px-4 flex gap-1 overflow-x-auto">{tabs.filter(name => selected.provider === 'generic_csv' || name !== 'CSV Import').map(name => <button key={name} onClick={() => setTab(name)} className={`px-4 py-3 text-sm whitespace-nowrap border-b-2 ${tab === name ? 'border-green-600 text-green-700' : 'border-transparent text-gray-500'}`}>{name}</button>)}</div>
        <div className="p-5">
          {tab === 'Overview' && <Overview integration={selected} />}
          {tab === 'CSV Import' && <CSVImport integration={selected} onComplete={() => { qc.invalidateQueries({ queryKey: ['integrations'] }); setNotice('Import zakończony') }} />}
          {tab === 'Products Mapping' && <Mappings integration={selected} />}
          {tab === 'Sync History' && <SyncHistory integration={selected} />}
          {tab === 'Errors' && <Errors integration={selected} />}
          {tab === 'Settings' && <IntegrationSettings integration={selected} onChange={() => qc.invalidateQueries({ queryKey: ['integrations'] })} />}
        </div>
      </div>}
    </div>
  )
}

function Overview({ integration }: { integration: any }) {
  return <div className="grid sm:grid-cols-2 lg:grid-cols-7 gap-4">
    {[['HEALTH', integration.health], ['STATUS', integration.status], ['LAST SYNC', formatDate(integration.last_sync_at)], ['LAST SUCCESS', formatDate(integration.last_success_at)], ['SALES TODAY', `${integration.sales_today_count || 0} / ${(integration.sales_today_amount || 0).toFixed(2)} PLN`], ['UNMAPPED PRODUCTS', integration.unmapped_products], ['ERRORS', integration.error_count]].map(([label, value]) => <div key={String(label)} className="bg-gray-50 rounded-xl p-4"><div className="text-xs text-gray-500">{label}</div><div className="font-bold mt-1">{value}</div></div>)}
    <div className={`sm:col-span-2 lg:col-span-7 rounded-xl p-3 text-sm ${integration.health === 'OK' ? 'bg-green-50 text-green-800' : integration.health === 'ERROR' ? 'bg-red-50 text-red-800' : 'bg-amber-50 text-amber-800'}`}>{integration.health_reason}{integration.bridge_last_seen ? ` · Bridge: ${formatDate(integration.bridge_last_seen)}${integration.bridge_version ? ` · v${integration.bridge_version}` : ''}` : ''}</div>
    <div className="sm:col-span-2 lg:col-span-7 text-xs text-gray-500">Capabilities: {Object.entries(integration.capabilities || {}).filter(([, enabled]) => enabled).map(([name]) => name).join(', ') || 'brak'}</div>
  </div>
}

function CSVImport({ integration, onComplete }: { integration: any, onComplete: () => void }) {
  const { data: templates = [] } = useQuery({ queryKey: ['csv-templates', integration.id], queryFn: async () => (await api.get('/integrations/csv/templates', { params: { integration_id: integration.id } })).data })
  const [file, setFile] = useState<File | null>(null)
  const [headers, setHeaders] = useState<string[]>([])
  const [delimiter, setDelimiter] = useState(',')
  const [dateFormat, setDateFormat] = useState('%Y-%m-%d')
  const [templateName, setTemplateName] = useState('My POS Export')
  const [selectedTemplateId, setSelectedTemplateId] = useState('')
  const [mapping, setMapping] = useState<any>({ transaction_id: 'transaction_id', date: 'date', time: null, ean: 'ean', sku: 'sku', external_product_id: 'external_product_id', name: 'name', quantity: 'quantity', unit_price: 'unit_price', total: 'total', location: 'location' })
  const [preview, setPreview] = useState<any>(null)
  const [message, setMessage] = useState('')

  const loadHeaders = async (selected: File | null) => {
    setPreview(null); setMessage('')
    if (!selected) { setFile(null); setHeaders([]); setMessage('Wybierz plik CSV.'); return }
    if (!selected.name.toLowerCase().endsWith('.csv')) { setFile(null); setHeaders([]); setMessage('Nieprawidłowy format pliku. Wybierz plik CSV.'); return }
    const content = await selected.slice(0, 8192).text()
    if (!content.trim()) { setFile(null); setHeaders([]); setMessage('Plik CSV jest pusty.'); return }
    const lines = content.split(/\r?\n/).filter(line => line.trim())
    if (lines.length < 2) { setFile(null); setHeaders([]); setMessage('CSV musi zawierać nagłówek i co najmniej jeden wiersz danych.'); return }
    const firstLine = lines[0] || ''
    const parsed = firstLine.split(delimiter === '\t' ? '\t' : delimiter).map(value => value.replace(/^"|"$/g, '').trim())
    if (!parsed.length || parsed.some(value => !value)) { setFile(null); setHeaders([]); setMessage('Nagłówek CSV jest nieprawidłowy.'); return }
    setFile(selected)
    setHeaders(parsed)
    setMapping((current: any) => Object.fromEntries(Object.entries(current).map(([key, value]) => [key, parsed.includes(String(value)) ? value : (parsed.includes(key) ? key : '')])))
  }
  const formData = () => {
    if (!integration?.id) throw new Error('Wybierz integrację Generic CSV.')
    if (!file) throw new Error('Wybierz poprawny, niepusty plik CSV.')
    const missing = ['transaction_id', 'quantity', 'unit_price'].filter(key => !mapping[key] || !headers.includes(mapping[key]))
    if (missing.length) throw new Error(`Uzupełnij wymagane mapowanie: ${missing.join(', ')}.`)
    if (!mapping.ean && !mapping.sku && !mapping.external_product_id) throw new Error('Zmapuj co najmniej jedno pole produktu: EAN, SKU lub external_product_id.')
    const data = new FormData(); data.append('file', file); data.append('integration_id', String(integration.id)); data.append('mapping', JSON.stringify(mapping)); data.append('delimiter', delimiter); data.append('date_format', dateFormat)
    if (selectedTemplateId) data.append('template_id', selectedTemplateId); else if (templateName) data.append('template_name', templateName)
    return data
  }
  const errorMessage = (err: any) => typeof err?.response?.data?.detail === 'string' ? err.response.data.detail : (err?.response?.status === 422 ? 'Plik CSV lub mapowanie są nieprawidłowe. Sprawdź wymagane kolumny i spróbuj ponownie.' : err.message || 'Nie udało się przetworzyć pliku CSV.')
  const previewMut = useMutation({ mutationFn: async () => (await api.post('/integrations/csv/preview', formData())).data, onSuccess: data => { setMessage(''); setPreview(data) }, onError: (err: any) => setMessage(errorMessage(err)) })
  const importMut = useMutation({ mutationFn: async () => (await api.post('/integrations/csv/import', formData())).data, onSuccess: data => { setMessage(`Import: ${data.processed} przetworzono, ${data.failed} błędów`); onComplete() }, onError: (err: any) => setMessage(errorMessage(err)) })

  const choices = ['', ...headers]
  return <div className="space-y-5">
    <div className="grid md:grid-cols-5 gap-3"><label className="text-xs">Zapisany szablon<select value={selectedTemplateId} onChange={event => { const id = event.target.value; setSelectedTemplateId(id); const template = templates.find((item: any) => String(item.id) === id); if (template) { setMapping(template.column_mapping); setDelimiter(template.delimiter); setDateFormat(template.date_format || '%Y-%m-%d') } }} className="block w-full border rounded-lg p-2 text-sm"><option value="">Nowe mapowanie</option>{templates.map((item: any) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><label className="text-xs">Separator<select value={delimiter} onChange={event => setDelimiter(event.target.value)} className="block w-full border rounded-lg p-2 text-sm"><option value=",">Przecinek</option><option value=";">Średnik</option><option value={'\t'}>Tab</option><option value="|">|</option></select></label><label className="text-xs">Format daty<input value={dateFormat} onChange={event => setDateFormat(event.target.value)} className="block w-full border rounded-lg p-2 text-sm" /></label><label className="text-xs">Nazwa nowego szablonu<input value={templateName} onChange={event => setTemplateName(event.target.value)} disabled={!!selectedTemplateId} className="block w-full border rounded-lg p-2 text-sm disabled:bg-gray-100" /></label><label className="text-xs">Plik CSV<input type="file" accept=".csv,text/csv" onChange={event => loadHeaders(event.target.files?.[0] || null)} className="block w-full text-sm mt-2" /></label></div>
    {headers.length > 0 && <div><h3 className="font-medium mb-2">Mapowanie kolumn</h3><div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-2">{standardColumns.map(key => <label key={key} className="text-xs">{key}{['transaction_id','quantity','unit_price'].includes(key) && ' *'}<select value={mapping[key] || ''} onChange={event => setMapping({ ...mapping, [key]: event.target.value || null })} className="block border rounded-lg p-2 w-full text-sm">{choices.map(choice => <option key={choice} value={choice}>{choice || '— brak —'}</option>)}</select></label>)}</div></div>}
    <div className="flex gap-2"><button onClick={() => previewMut.mutate()} disabled={!file || previewMut.isPending} className="border border-green-600 text-green-700 px-4 py-2 rounded-xl flex items-center gap-2 disabled:opacity-40"><Upload className="w-4 h-4" /> Podgląd</button><button onClick={() => importMut.mutate()} disabled={!preview || preview.unmapped > 0 || preview.invalid > 0 || importMut.isPending} className="bg-green-600 text-white px-4 py-2 rounded-xl disabled:opacity-40">Zatwierdź import</button></div>
    {message && <div className="bg-blue-50 p-3 rounded-xl text-sm">{message}</div>}
    {preview && <><div className="grid grid-cols-5 gap-2 text-center text-sm">{[['Records',preview.records],['Matched',preview.matched],['Unmapped',preview.unmapped],['Invalid',preview.invalid],['Duplicate',preview.duplicate]].map(([label,value]) => <div key={String(label)} className="bg-gray-50 rounded-xl p-3"><div className="text-xs text-gray-500">{label}</div><b>{value}</b></div>)}</div><div className="overflow-x-auto border rounded-xl"><table className="w-full text-xs"><thead className="bg-gray-50"><tr><th className="p-2">Transaction</th><th>POS Product</th><th>FreshStock Product</th><th>Status</th></tr></thead><tbody>{preview.preview?.map((row: any, index: number) => <tr key={index} className="border-t"><td className="p-2">{row.transaction_id}</td><td>{row.name || row.ean || row.sku}</td><td>{row.freshstock_product_name || '—'}</td><td>{row.status}</td></tr>)}</tbody></table></div></>}
  </div>
}

function Mappings({ integration }: { integration: any }) {
  const qc = useQueryClient()
  const { data: mappings = [] } = useQuery({ queryKey: ['integration-mappings', integration.id], queryFn: async () => (await api.get(`/integrations/${integration.id}/mappings`)).data })
  const { data: errors = [] } = useQuery({ queryKey: ['integration-errors', integration.id], queryFn: async () => (await api.get(`/integrations/${integration.id}/errors`, { params: { resolved: false } })).data })
  const { data: products = [] } = useQuery({ queryKey: ['products'], queryFn: async () => (await api.get('/products')).data })
  const [choices, setChoices] = useState<Record<number, string>>({})
  const mappingMut = useMutation({ mutationFn: async ({ error, productId }: any) => { const payload = error.payload || {}; await api.post(`/integrations/${integration.id}/mappings`, { external_product_id: payload.external_product_id, freshstock_product_id: Number(productId), ean: payload.ean, sku: payload.sku, mapping_method: 'MANUAL' }); await api.post(`/integrations/${integration.id}/errors/${error.id}/resolve`) }, onSuccess: () => { qc.invalidateQueries({ queryKey: ['integration-mappings', integration.id] }); qc.invalidateQueries({ queryKey: ['integration-errors', integration.id] }) } })
  const unmapped = errors.filter((item: any) => item.error_type === 'UNMAPPED_PRODUCT')
  return <div className="space-y-5"><div><h3 className="font-semibold mb-2">Produkty niedopasowane</h3>{unmapped.map((item: any) => <div key={item.id} className="border rounded-xl p-3 flex flex-wrap items-center gap-3"><div className="flex-1"><b>{item.payload?.name || item.payload?.external_product_id}</b><div className="text-xs text-gray-500">EAN {item.payload?.ean || '—'} · SKU {item.payload?.sku || '—'}</div></div><select value={choices[item.id] || ''} onChange={event => setChoices({ ...choices, [item.id]: event.target.value })} className="border rounded-lg p-2"><option value="">FreshStock Product</option>{products.map((product: any) => <option key={product.id} value={product.id}>{product.name} ({product.sku})</option>)}</select><button onClick={() => mappingMut.mutate({ error: item, productId: choices[item.id] })} disabled={!choices[item.id]} className="bg-green-600 text-white px-3 py-2 rounded-lg disabled:opacity-40">Mapuj</button><Link to={`/products/new?ean=${encodeURIComponent(item.payload?.ean || '')}&name=${encodeURIComponent(item.payload?.name || '')}`} className="border px-3 py-2 rounded-lg">Create new FreshStock product</Link></div>)}{!unmapped.length && <p className="text-sm text-gray-500">Brak produktów wymagających mapowania.</p>}</div><div><h3 className="font-semibold mb-2">Aktywne mapowania</h3><div className="divide-y border rounded-xl">{mappings.map((row: any) => <div key={row.id} className="p-3 text-sm flex justify-between"><span>{row.external_product_id}</span><span>{row.freshstock_product_name} · {row.mapping_method}</span></div>)}</div></div></div>
}

function SyncHistory({ integration }: { integration: any }) {
  const { data: logs = [] } = useQuery({ queryKey: ['integration-logs', integration.id], queryFn: async () => (await api.get(`/integrations/${integration.id}/logs`)).data })
  return <div className="overflow-x-auto"><table className="w-full text-sm"><thead><tr><th className="text-left p-2">Start</th><th>Status</th><th>Typ</th><th>Received</th><th>Processed</th><th>Failed</th></tr></thead><tbody>{logs.map((row: any) => <tr key={row.id} className="border-t"><td className="p-2">{formatDate(row.started_at)}</td><td className="text-center">{row.status}</td><td className="text-center">{row.sync_type}</td><td className="text-center">{row.records_received}</td><td className="text-center">{row.records_processed}</td><td className="text-center">{row.records_failed}</td></tr>)}</tbody></table></div>
}

function Errors({ integration }: { integration: any }) {
  const qc = useQueryClient()
  const { data: errors = [] } = useQuery({ queryKey: ['integration-errors', integration.id], queryFn: async () => (await api.get(`/integrations/${integration.id}/errors`)).data })
  const { data: returns = [] } = useQuery({ queryKey: ['integration-returns', integration.id], queryFn: async () => (await api.get(`/integrations/${integration.id}/returns`, { params: { status: 'RETURN_PENDING' } })).data })
  const resolveMut = useMutation({ mutationFn: async (id: number) => api.post(`/integrations/${integration.id}/errors/${id}/resolve`), onSuccess: () => qc.invalidateQueries({ queryKey: ['integration-errors', integration.id] }) })
  const returnMut = useMutation({ mutationFn: async ({ id, action }: any) => api.post(`/integrations/${integration.id}/returns/${id}/resolve`, { action }), onSuccess: () => { qc.invalidateQueries({ queryKey: ['integration-returns', integration.id] }); qc.invalidateQueries({ queryKey: ['integration-errors', integration.id] }) } })
  return <div className="space-y-4">{returns.map((item: any) => <div key={`return-${item.id}`} className="border border-amber-300 bg-amber-50 rounded-xl p-4"><b>Zwrot #{item.id} wymaga decyzji</b><div className="text-xs text-gray-600 mt-1">Pozycje: {item.items?.requested?.map((row: any) => `${row.name || row.external_product_id} × ${row.quantity}`).join(', ')}</div><div className="mt-3 flex gap-2"><button onClick={() => returnMut.mutate({ id: item.id, action: 'RETURN_TO_STOCK' })} className="bg-green-600 text-white px-3 py-2 rounded-lg text-sm">Przyjmij na sugerowaną partię</button><button onClick={() => returnMut.mutate({ id: item.id, action: 'WASTE' })} className="border border-red-400 text-red-700 px-3 py-2 rounded-lg text-sm">Skieruj do strat</button></div></div>)}{errors.map((row: any) => <div key={row.id} className={`border rounded-xl p-3 flex gap-3 ${row.resolved ? 'opacity-50' : ''}`}><AlertCircle className="w-5 h-5 text-orange-500" /><div className="flex-1"><b className="text-sm">{row.error_type}</b><div className="text-sm">{row.message}</div><div className="text-xs text-gray-500">{formatDate(row.created_at)}</div></div>{!row.resolved && row.error_type !== 'RETURN_PENDING' && <button onClick={() => resolveMut.mutate(row.id)} className="text-green-700 text-sm">Resolve</button>}</div>)}{!errors.length && !returns.length && <p className="text-sm text-gray-500">Brak błędów.</p>}</div>
}

function IntegrationSettings({ integration, onChange }: { integration: any, onChange: () => void }) {
  const [message, setMessage] = useState('')
  const canSync = integration.status === 'ACTIVE' && integration.capabilities?.sales_read && integration.provider !== 'generic_csv' && integration.provider !== 'local_bridge'
  const testMut = useMutation({ mutationFn: async () => (await api.post(`/integrations/${integration.id}/test`)).data, onSuccess: data => { setMessage(data.message || (data.ok ? 'Połączenie działa' : 'Adapter wymaga konfiguracji')); onChange() }, onError: (err: any) => setMessage(err?.response?.data?.detail || 'Test nieudany') })
  const syncMut = useMutation({ mutationFn: async () => {
    let processed = 0, received = 0, failed = 0, page = 0, data: any
    do {
      data = (await api.post(`/integrations/${integration.id}/sync`)).data
      processed += data.processed; received += data.received; failed += data.failed; page += 1
      setMessage(`Synchronizacja: ${processed} przetworzono · partia ${page}${data.has_more ? '…' : ''}`)
    } while (data.has_more && page < 100)
    return { processed, received, failed }
  }, onSuccess: data => { setMessage(`Sync zakończony: ${data.processed}/${data.received}, błędy ${data.failed}`); onChange() }, onError: (err: any) => setMessage(err?.response?.data?.detail || 'Synchronizacja przerwana — ponowienie wznowi ją od ostatniej partii') })
  const disableMut = useMutation({ mutationFn: async () => (await api.delete(`/integrations/${integration.id}`)).data, onSuccess: data => { setMessage(data.message); onChange() } })
  return <div className="space-y-4"><div className="flex flex-wrap gap-2"><button onClick={() => testMut.mutate()} className="border px-4 py-2 rounded-xl flex gap-2"><Plug className="w-4 h-4" /> Test Connection</button>{canSync && <button onClick={() => syncMut.mutate()} disabled={syncMut.isPending} className="bg-green-600 text-white px-4 py-2 rounded-xl flex gap-2 disabled:opacity-50"><RefreshCw className="w-4 h-4" /> Sync Now</button>}<button onClick={() => window.confirm('Wyłączyć integrację i usunąć zapisane credentials?') && disableMut.mutate()} className="border border-red-300 text-red-700 px-4 py-2 rounded-xl flex gap-2"><Settings2 className="w-4 h-4" /> Disable</button></div>{message && <div className="bg-blue-50 p-3 rounded-xl text-sm">{message}</div>}<div className="text-xs text-gray-500"><CheckCircle className="w-4 h-4 inline mr-1" /> Credentials są szyfrowane i nigdy nie są zwracane przez API.</div></div>
}
