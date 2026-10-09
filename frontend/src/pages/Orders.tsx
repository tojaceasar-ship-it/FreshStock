import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertCircle, CalendarDays, Check, Minus, PackageCheck, Plus, RefreshCw, Search, ShoppingCart, Truck } from 'lucide-react'
import { api } from '../lib/api'
import { formatCurrency } from '../lib/utils'

type Suggestion = {
  product_id: number
  product_name: string
  sku: string
  ean?: string
  current_stock: number
  min_stock: number
  target_stock: number
  safety_stock: number
  avg_daily_sales: number
  lead_time_days: number
  reorder_point: number
  suggested_quantity: number
  supplier_id?: number | null
  supplier_name?: string | null
  purchase_price: number
}

type DraftLine = {
  selected: boolean
  quantity: number
  purchase_price: number
}

type PurchaseOrder = {
  id: number
  order_number: string
  supplier_name?: string | null
  status: string
  total_value: number
  created_at: string
  expected_delivery_date?: string | null
  items?: unknown[]
}

const supplierKey = (s: Suggestion) => String(s.supplier_id || 'none')

export default function Orders() {
  const queryClient = useQueryClient()
  const { data: pos = [] } = useQuery<PurchaseOrder[]>({ queryKey: ['pos'], queryFn: async () => (await api.get('/purchase-orders')).data })
  const { data: suggestions = [], refetch, isFetching } = useQuery<Suggestion[]>({ queryKey: ['suggestions'], queryFn: async () => (await api.get('/purchase-orders/suggestions')).data })
  const [tab, setTab] = useState('suggestions')
  const [draft, setDraft] = useState<Record<number, DraftLine>>({})
  const [activeSupplier, setActiveSupplier] = useState<string>('all')
  const [search, setSearch] = useState('')
  const [expectedDeliveryDate, setExpectedDeliveryDate] = useState('')
  const [notes, setNotes] = useState('Utworzone z sugestii uzupełnienia stanów.')

  const rows = useMemo(() => {
    const term = search.trim().toLowerCase()
    return suggestions.filter((s) => {
      const matchesSupplier = activeSupplier === 'all' || supplierKey(s) === activeSupplier
      const matchesSearch = !term || [s.product_name, s.sku, s.ean, s.supplier_name].filter(Boolean).some((v) => String(v).toLowerCase().includes(term))
      return matchesSupplier && matchesSearch
    })
  }, [activeSupplier, search, suggestions])

  const selectedLines = useMemo(() => {
    return suggestions
      .map((s) => ({ suggestion: s, line: draft[s.product_id] }))
      .filter(({ line }) => line?.selected && line.quantity > 0)
  }, [draft, suggestions])

  const groupedSelected = useMemo(() => {
    return selectedLines.reduce<Record<string, { supplier_id: number | null, supplier_name: string, items: { suggestion: Suggestion, line: DraftLine }[], total: number }>>((acc, item) => {
      const key = supplierKey(item.suggestion)
      if (!acc[key]) {
        acc[key] = {
          supplier_id: item.suggestion.supplier_id || null,
          supplier_name: item.suggestion.supplier_name || 'Brak dostawcy',
          items: [],
          total: 0
        }
      }
      acc[key].items.push(item)
      acc[key].total += item.line.quantity * item.line.purchase_price
      return acc
    }, {})
  }, [selectedLines])

  const supplierTabs = useMemo(() => {
    const grouped = suggestions.reduce<Record<string, { name: string, count: number, total: number }>>((acc, s) => {
      const key = supplierKey(s)
      if (!acc[key]) acc[key] = { name: s.supplier_name || 'Brak dostawcy', count: 0, total: 0 }
      acc[key].count += 1
      acc[key].total += s.suggested_quantity * s.purchase_price
      return acc
    }, {})
    return Object.entries(grouped).map(([key, value]) => ({ key, ...value }))
  }, [suggestions])

  const selectedTotal = selectedLines.reduce((sum, item) => sum + item.line.quantity * item.line.purchase_price, 0)
  const canCreate = selectedLines.length > 0 && !groupedSelected.none

  const createOrders = useMutation({
    mutationFn: async () => {
      const groups = Object.values(groupedSelected).filter((group) => group.supplier_id)
      const created = []
      for (const group of groups) {
        const res = await api.post('/purchase-orders', {
          supplier_id: group.supplier_id,
          expected_delivery_date: expectedDeliveryDate || null,
          notes,
          items: group.items.map(({ suggestion, line }) => ({
            product_id: suggestion.product_id,
            quantity: line.quantity,
            purchase_price: line.purchase_price
          }))
        })
        created.push(res.data)
      }
      return created
    },
    onSuccess: () => {
      setDraft({})
      setTab('orders')
      queryClient.invalidateQueries({ queryKey: ['pos'] })
      queryClient.invalidateQueries({ queryKey: ['suggestions'] })
    }
  })

  const setLine = (s: Suggestion, changes: Partial<DraftLine>) => {
    setDraft((current) => {
      const existing = current[s.product_id] || { selected: false, quantity: s.suggested_quantity, purchase_price: s.purchase_price }
      return { ...current, [s.product_id]: { ...existing, ...changes } }
    })
  }

  const toggleLine = (s: Suggestion) => {
    const current = draft[s.product_id]
    setLine(s, { selected: !current?.selected, quantity: current?.quantity || s.suggested_quantity, purchase_price: current?.purchase_price || s.purchase_price })
  }

  const selectSupplier = (key: string, selected: boolean) => {
    setDraft((current) => {
      const next = { ...current }
      suggestions.filter((s) => supplierKey(s) === key).forEach((s) => {
        const existing = next[s.product_id] || { selected: false, quantity: s.suggested_quantity, purchase_price: s.purchase_price }
        next[s.product_id] = { ...existing, selected }
      })
      return next
    })
  }

  const selectAllVisible = () => {
    setDraft((current) => {
      const next = { ...current }
      rows.forEach((s) => {
        const existing = next[s.product_id] || { selected: false, quantity: s.suggested_quantity, purchase_price: s.purchase_price }
        next[s.product_id] = { ...existing, selected: true }
      })
      return next
    })
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <h1 className="text-2xl font-bold">Zamówienia</h1>
        {tab === 'suggestions' && (
          <button onClick={() => refetch()} className="inline-flex items-center justify-center gap-2 rounded-lg border bg-white px-3 py-2 text-sm hover:bg-gray-50">
            <RefreshCw className={`h-4 w-4 ${isFetching ? 'animate-spin' : ''}`} />
            Odśwież sugestie
          </button>
        )}
      </div>

      <div className="flex gap-2">
        <button onClick={() => setTab('suggestions')} className={`rounded-lg px-4 py-2 ${tab === 'suggestions' ? 'bg-green-600 text-white' : 'border bg-white'}`}>Sugerowane zamówienia</button>
        <button onClick={() => setTab('orders')} className={`rounded-lg px-4 py-2 ${tab === 'orders' ? 'bg-green-600 text-white' : 'border bg-white'}`}>Zamówienia</button>
      </div>

      {tab === 'suggestions' && (
        <div className="grid gap-4 xl:grid-cols-[1fr_360px]">
          <div className="space-y-4">
            <div className="rounded-lg border bg-white">
              <div className="border-b p-4">
                <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                  <div>
                    <h3 className="font-semibold">Lista produktów do uzupełnienia</h3>
                    <p className="text-sm text-gray-500">Sugestia bazuje na sprzedaży, czasie dostawy i zapasie bezpieczeństwa.</p>
                  </div>
                  <div className="relative w-full lg:w-80">
                    <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-gray-400" />
                    <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Szukaj produktu, SKU, EAN..." className="w-full rounded-lg border py-2 pl-9 pr-3 text-sm outline-none focus:border-green-500" />
                  </div>
                </div>
              </div>

              <div className="flex gap-2 overflow-x-auto border-b p-3">
                <button onClick={() => setActiveSupplier('all')} className={`whitespace-nowrap rounded-lg px-3 py-2 text-sm ${activeSupplier === 'all' ? 'bg-gray-900 text-white' : 'bg-gray-100 hover:bg-gray-200'}`}>Wszyscy ({suggestions.length})</button>
                {supplierTabs.map((supplier) => (
                  <button key={supplier.key} onClick={() => setActiveSupplier(supplier.key)} className={`whitespace-nowrap rounded-lg px-3 py-2 text-sm ${activeSupplier === supplier.key ? 'bg-gray-900 text-white' : 'bg-gray-100 hover:bg-gray-200'}`}>
                    {supplier.name} ({supplier.count})
                  </button>
                ))}
              </div>

              <div className="flex flex-wrap items-center justify-between gap-2 border-b bg-gray-50 px-4 py-3">
                <button onClick={selectAllVisible} className="inline-flex items-center gap-2 rounded-lg bg-green-600 px-3 py-2 text-sm font-medium text-white hover:bg-green-700">
                  <Check className="h-4 w-4" />
                  Wybierz widoczne
                </button>
                <div className="text-sm text-gray-600">{selectedLines.length} wybranych pozycji • {formatCurrency(selectedTotal)}</div>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="bg-gray-50 text-xs uppercase text-gray-500">
                    <tr>
                      <th className="px-4 py-3 text-left">Wybór</th>
                      <th className="px-4 py-3 text-left">Produkt</th>
                      <th className="px-4 py-3 text-center">Stan</th>
                      <th className="px-4 py-3 text-center">Min/Cel</th>
                      <th className="px-4 py-3 text-center">Sprzedaż</th>
                      <th className="px-4 py-3 text-center">Zamówić</th>
                      <th className="px-4 py-3 text-right">Cena</th>
                      <th className="px-4 py-3 text-right">Wartość</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y">
                    {rows.map((s) => {
                      const line = draft[s.product_id] || { selected: false, quantity: s.suggested_quantity, purchase_price: s.purchase_price }
                      const value = line.quantity * line.purchase_price
                      return (
                        <tr key={s.product_id} className={line.selected ? 'bg-green-50/60' : 'hover:bg-gray-50'}>
                          <td className="px-4 py-3">
                            <input type="checkbox" checked={line.selected} onChange={() => toggleLine(s)} className="h-4 w-4 rounded border-gray-300 text-green-600 focus:ring-green-500" />
                          </td>
                          <td className="min-w-64 px-4 py-3">
                            <div className="font-medium">{s.product_name}</div>
                            <div className="text-xs text-gray-500">{s.sku}{s.ean ? ` • ${s.ean}` : ''}</div>
                            <div className="mt-1 inline-flex items-center gap-1 rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-600">
                              <Truck className="h-3 w-3" />
                              {s.supplier_name || 'Brak dostawcy'}
                            </div>
                          </td>
                          <td className="px-4 py-3 text-center"><span className="rounded-full bg-red-100 px-2 py-1 text-xs text-red-700">{s.current_stock}</span></td>
                          <td className="px-4 py-3 text-center">{s.min_stock}/{s.target_stock}</td>
                          <td className="px-4 py-3 text-center">{s.avg_daily_sales}/dzień</td>
                          <td className="px-4 py-3">
                            <div className="mx-auto flex w-36 items-center justify-center gap-1">
                              <button onClick={() => setLine(s, { selected: true, quantity: Math.max(1, line.quantity - 1) })} className="rounded-lg border p-2 hover:bg-gray-50" aria-label="Zmniejsz ilość"><Minus className="h-3 w-3" /></button>
                              <input type="number" min={1} value={line.quantity} onChange={(e) => setLine(s, { selected: true, quantity: Math.max(1, Number(e.target.value) || 1) })} className="w-16 rounded-lg border px-2 py-1.5 text-center" />
                              <button onClick={() => setLine(s, { selected: true, quantity: line.quantity + 1 })} className="rounded-lg border p-2 hover:bg-gray-50" aria-label="Zwiększ ilość"><Plus className="h-3 w-3" /></button>
                            </div>
                            <div className="mt-1 text-center text-xs text-gray-500">sug. {s.suggested_quantity}</div>
                          </td>
                          <td className="px-4 py-3 text-right">
                            <input type="number" min={0} step="0.01" value={line.purchase_price} onChange={(e) => setLine(s, { selected: true, purchase_price: Math.max(0, Number(e.target.value) || 0) })} className="w-24 rounded-lg border px-2 py-1.5 text-right" />
                          </td>
                          <td className="px-4 py-3 text-right font-semibold">{formatCurrency(value)}</td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
                {!rows.length && <div className="p-8 text-center text-gray-500">Brak produktów dla wybranego filtra.</div>}
              </div>
            </div>
          </div>

          <aside className="space-y-4">
            <div className="rounded-lg border bg-white p-4">
              <div className="mb-4 flex items-center gap-2">
                <ShoppingCart className="h-5 w-5 text-green-600" />
                <h3 className="font-semibold">Koszyk zamówień</h3>
              </div>

              <label className="mb-3 block text-sm">
                <span className="mb-1 flex items-center gap-1 text-gray-600"><CalendarDays className="h-4 w-4" /> Planowana dostawa</span>
                <input type="date" value={expectedDeliveryDate} onChange={(e) => setExpectedDeliveryDate(e.target.value)} className="w-full rounded-lg border px-3 py-2" />
              </label>

              <label className="mb-4 block text-sm">
                <span className="mb-1 block text-gray-600">Notatka do zamówień</span>
                <textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={3} className="w-full rounded-lg border px-3 py-2" />
              </label>

              <div className="space-y-3">
                {Object.entries(groupedSelected).map(([key, group]) => (
                  <div key={key} className="rounded-lg border p-3">
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <div className="font-medium">{group.supplier_name}</div>
                        <div className="text-xs text-gray-500">{group.items.length} pozycji</div>
                      </div>
                      <button onClick={() => selectSupplier(key, false)} className="text-xs text-gray-500 hover:text-red-600">Wyczyść</button>
                    </div>
                    <div className="mt-2 text-lg font-bold">{formatCurrency(group.total)}</div>
                    {!group.supplier_id && (
                      <div className="mt-2 flex gap-2 rounded-lg bg-amber-50 p-2 text-xs text-amber-800">
                        <AlertCircle className="h-4 w-4 shrink-0" />
                        Uzupełnij dostawcę w produkcie, aby utworzyć zamówienie.
                      </div>
                    )}
                  </div>
                ))}
                {!selectedLines.length && <div className="rounded-lg border border-dashed p-6 text-center text-sm text-gray-500">Wybierz produkty z listy, a system sam podzieli zamówienia po dostawcach.</div>}
              </div>

              <button disabled={!canCreate || createOrders.isPending} onClick={() => createOrders.mutate()} className="mt-4 inline-flex w-full items-center justify-center gap-2 rounded-lg bg-green-600 px-4 py-3 font-semibold text-white hover:bg-green-700 disabled:cursor-not-allowed disabled:bg-gray-300">
                <PackageCheck className="h-5 w-5" />
                {createOrders.isPending ? 'Tworzę zamówienia...' : 'Utwórz zamówienia'}
              </button>

              {createOrders.isError && <div className="mt-3 rounded-lg bg-red-50 p-3 text-sm text-red-700">Nie udało się utworzyć zamówień. Sprawdź uprawnienia i spróbuj ponownie.</div>}
            </div>

            <div className="rounded-lg border bg-white p-4">
              <h3 className="mb-3 font-semibold">Szybki wybór dostawcy</h3>
              <div className="space-y-2">
                {supplierTabs.map((supplier) => (
                  <button key={supplier.key} onClick={() => selectSupplier(supplier.key, true)} className="flex w-full items-center justify-between rounded-lg border px-3 py-2 text-left text-sm hover:bg-gray-50">
                    <span>{supplier.name}</span>
                    <span className="text-gray-500">{formatCurrency(supplier.total)}</span>
                  </button>
                ))}
              </div>
            </div>
          </aside>
        </div>
      )}

      {tab === 'orders' && (
        <div className="overflow-hidden rounded-lg border bg-white">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-xs uppercase text-gray-500">
              <tr><th className="px-4 py-3 text-left">Nr zamówienia</th><th className="px-4 py-3 text-left">Dostawca</th><th className="px-4 py-3">Status</th><th className="px-4 py-3">Wartość</th><th className="px-4 py-3">Planowana dostawa</th><th className="px-4 py-3">Pozycje</th></tr>
            </thead>
            <tbody className="divide-y">
              {pos.map((p) => (
                <tr key={p.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3 font-medium">{p.order_number}</td>
                  <td className="px-4 py-3">{p.supplier_name || '-'}</td>
                  <td className="px-4 py-3 text-center"><span className="rounded-full bg-blue-50 px-2 py-1 text-xs text-blue-700">{p.status}</span></td>
                  <td className="px-4 py-3 text-center">{formatCurrency(Number(p.total_value || 0))}</td>
                  <td className="px-4 py-3 text-center">{p.expected_delivery_date || '-'}</td>
                  <td className="px-4 py-3 text-center">{p.items?.length || 0}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {!pos.length && <div className="p-8 text-center text-gray-500">Nie ma jeszcze zamówień.</div>}
        </div>
      )}
    </div>
  )
}
