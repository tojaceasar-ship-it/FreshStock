import { useQuery } from '@tanstack/react-query'
import { api } from '../lib/api'
import { useState } from 'react'
import { formatCurrency } from '../lib/utils'
import { Link, useSearchParams } from 'react-router-dom'
import { Search, Plus, AlertTriangle } from 'lucide-react'

export default function Products() {
  const [params] = useSearchParams()
  const [search, setSearch] = useState(params.get('q') || '')
  const [filter, setFilter] = useState('all')
  const [page, setPage] = useState(1)
  const pageSize = 100

  const { data, isLoading, isError } = useQuery({
    queryKey: ['products', search, filter, page],
    queryFn: async () => {
      const query: any = { offset: (page - 1) * pageSize, limit: pageSize }
      if (search) query.search = search
      if (filter === 'low') query.low_stock = true
      if (filter === 'active') query.is_active = true
      const res = await api.get('/products', { params: query })
      return { products: res.data, total: Number(res.headers['x-total-count'] || res.data.length) }
    }
  })
  const products = data?.products
  const total = data?.total || 0
  const pageCount = Math.max(1, Math.ceil(total / pageSize))

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">Produkty</h1>
          <p className="text-gray-500">{total} produktów</p>
        </div>
        <Link to="/products/new" className="inline-flex items-center gap-2 bg-green-600 text-white px-4 py-2.5 rounded-xl hover:bg-green-700 font-medium">
          <Plus className="w-4 h-4" /> Nowy produkt
        </Link>
      </div>

      <div className="bg-white rounded-2xl border border-gray-200 p-4">
        <div className="flex flex-col sm:flex-row gap-3">
          <div className="relative flex-1">
            <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
            <input
              value={search}
              onChange={e => { setSearch(e.target.value); setPage(1) }}
              placeholder="Szukaj po nazwie, SKU, EAN, marce..."
              className="w-full pl-10 pr-4 py-2.5 border border-gray-200 rounded-xl focus:border-green-500 focus:ring-2 focus:ring-green-100 outline-none"
            />
          </div>
          <select value={filter} onChange={e => { setFilter(e.target.value); setPage(1) }} className="px-4 py-2.5 border border-gray-200 rounded-xl">
            <option value="all">Wszystkie</option>
            <option value="low">Niski stan</option>
            <option value="active">Aktywne</option>
          </select>
        </div>
      </div>

      <div className="bg-white rounded-2xl border border-gray-200 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr className="text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">
                <th className="px-4 py-3">Produkt</th>
                <th className="px-4 py-3">Kategoria</th>
                <th className="px-4 py-3">Cena</th>
                <th className="px-4 py-3">Stan</th>
                <th className="px-4 py-3">Min/Cel</th>
                <th className="px-4 py-3">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {isLoading ? (
                <tr><td colSpan={6} className="px-4 py-8 text-center text-gray-500">Ładowanie...</td></tr>
              ) : isError ? (
                <tr><td colSpan={6} className="px-4 py-8 text-center text-red-600">Nie udało się pobrać produktów.</td></tr>
              ) : !products?.length ? (
                <tr><td colSpan={6} className="px-4 py-8 text-center text-gray-500">Brak produktów spełniających kryteria.</td></tr>
              ) : products?.map((p: any) => (
                <tr key={p.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3">
                    <Link to={`/products/${p.id}`} className="flex items-center gap-3">
                      <div className="w-10 h-10 bg-gray-100 rounded-xl flex items-center justify-center text-xs font-bold">{p.sku.slice(0,2)}</div>
                      <div>
                        <div className="font-medium text-gray-900">{p.name}</div>
                        <div className="text-xs text-gray-500">{p.sku} • {p.ean || 'brak EAN'} • {p.brand || ''}</div>
                      </div>
                    </Link>
                  </td>
                  <td className="px-4 py-3 text-sm">{p.category_name || '-'}</td>
                  <td className="px-4 py-3 text-sm">
                    <div>{formatCurrency(p.selling_price)}</div>
                    <div className="text-xs text-gray-500">zakup {formatCurrency(p.purchase_price)}</div>
                  </td>
                  <td className="px-4 py-3">
                    <div className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium ${
                      p.total_stock === 0 ? 'bg-red-100 text-red-700' :
                      p.total_stock <= p.min_stock ? 'bg-orange-100 text-orange-700' :
                      'bg-green-100 text-green-700'
                    }`}>
                      {p.total_stock <= p.min_stock && <AlertTriangle className="w-3 h-3" />}
                      {p.total_stock} {p.unit}
                    </div>
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-600">{p.min_stock} / {p.target_stock}</td>
                  <td className="px-4 py-3">
                    <span className={`px-2 py-1 rounded-full text-xs ${p.is_active ? 'bg-green-50 text-green-700' : 'bg-gray-100 text-gray-600'}`}>
                      {p.is_active ? 'Aktywny' : 'Nieaktywny'}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {total > pageSize && <div className="flex items-center justify-between border-t border-gray-200 px-4 py-3">
          <button disabled={page === 1} onClick={() => setPage(value => Math.max(1, value - 1))} className="rounded-lg border px-3 py-2 text-sm disabled:opacity-40">Poprzednia</button>
          <span className="text-sm text-gray-600">Strona {page} z {pageCount}</span>
          <button disabled={page >= pageCount} onClick={() => setPage(value => Math.min(pageCount, value + 1))} className="rounded-lg border px-3 py-2 text-sm disabled:opacity-40">Następna</button>
        </div>}
      </div>
    </div>
  )
}
