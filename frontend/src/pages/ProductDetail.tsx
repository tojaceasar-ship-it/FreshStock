import { Link, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { api } from '../lib/api'
import { formatCurrency, formatDate, daysUntil, getExpiryColor } from '../lib/utils'
import { getLocale } from '../lib/i18n'
import { useAuth } from '../hooks/useAuth'

export default function ProductDetail() {
  const { user } = useAuth()
  const { id } = useParams()
  const { data: product } = useQuery({
    queryKey: ['product', id],
    queryFn: async () => (await api.get(`/products/${id}`)).data
  })
  const { data: batches } = useQuery({
    queryKey: ['product-batches', id],
    queryFn: async () => (await api.get(`/products/${id}/batches`)).data,
    enabled: !!id
  })
  const { data: movements } = useQuery({
    queryKey: ['product-movements', id],
    queryFn: async () => (await api.get('/stock-movements', { params: { product_id: id, limit: 20 } })).data,
    enabled: !!id
  })
  const { data: traceability } = useQuery({
    queryKey: ['product-traceability', id],
    queryFn: async () => (await api.get(`/traceability/products/${id}`)).data,
    enabled: !!id
  })

  if (!product) return <div>Ładowanie...</div>

  return (
    <div className="space-y-6">
      <div className="bg-white rounded-2xl border p-6">
        <div className="flex flex-wrap items-start justify-between gap-3"><h1 className="text-2xl font-bold">{product.name}</h1>{(user?.role==='OWNER'||user?.role==='MANAGER')&&<Link to={`/tasks?${new URLSearchParams({new:'1',title:`Sprawdź produkt: ${product.name}`,product_id:String(product.id),task_type:'GENERAL'})}`} className="rounded-xl bg-green-600 px-4 py-2 text-sm font-medium text-white">Utwórz zadanie</Link>}</div>
        <p className="text-gray-500">{product.sku} • {product.ean} • {product.brand}</p>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-6">
          <div className="bg-gray-50 p-4 rounded-xl"><div className="text-xs text-gray-500">Stan</div><div className="text-xl font-bold">{product.total_stock} {product.unit}</div></div>
          <div className="bg-gray-50 p-4 rounded-xl"><div className="text-xs text-gray-500">Cena sprzedaży</div><div className="text-xl font-bold">{formatCurrency(product.selling_price)}</div></div>
          <div className="bg-gray-50 p-4 rounded-xl"><div className="text-xs text-gray-500">Cena zakupu</div><div className="text-xl font-bold">{formatCurrency(product.purchase_price)}</div></div>
          <div className="bg-gray-50 p-4 rounded-xl"><div className="text-xs text-gray-500">Marża</div><div className="text-xl font-bold text-green-600">{(((product.selling_price - product.purchase_price)/product.purchase_price)*100).toFixed(1)}%</div></div>
        </div>
        <div className="mt-4 grid md:grid-cols-3 gap-4 text-sm">
          <div><span className="text-gray-500">Kategoria:</span> {product.category_name || '-'}</div>
          <div><span className="text-gray-500">Min/Cel/Bezpieczny:</span> {product.min_stock}/{product.target_stock}/{product.safety_stock}</div>
          <div><span className="text-gray-500">VAT:</span> {product.vat_rate}% • <span className="text-gray-500">Kontrola daty:</span> {product.requires_expiry_control ? 'Tak' : 'Nie'}</div>
        </div>
      </div>

      <div className="grid lg:grid-cols-2 gap-6">
        <div className="bg-white rounded-2xl border p-6">
          <h3 className="font-semibold mb-4">Partie (FEFO - najstarsze pierwsze)</h3>
          <div className="space-y-2">
            {batches?.map((b: any) => {
              const days = b.expiry_date ? daysUntil(b.expiry_date) : null
              return (
                <div key={b.id} className="flex items-center justify-between p-3 border rounded-xl">
                  <div>
                    <div className="font-medium text-sm">{b.batch_number}</div>
                    <div className="text-xs text-gray-500">Ilość: {b.quantity_available}/{b.quantity_received} • {formatDate(b.expiry_date)} {days !== null && `(${days}d)`}</div>
                  </div>
                  <span className={`text-xs px-2 py-1 rounded-full border ${getExpiryColor(days)}`}>{b.quantity_available} {product.unit}</span>
                </div>
              )
            })}
            {!batches?.length && <p className="text-sm text-gray-500">Brak partii</p>}
          </div>
        </div>

        <div className="bg-white rounded-2xl border p-6">
          <h3 className="font-semibold mb-4">Ostatnie ruchy magazynowe</h3>
          <div className="space-y-2">
            {movements?.map((m: any) => (
              <div key={m.id} className="flex items-center justify-between p-2 text-sm border-b last:border-0">
                <div>
                  <span className={`px-2 py-0.5 rounded text-xs ${m.quantity > 0 ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}`}>{m.movement_type}</span>
                  <span className="ml-2">{m.quantity > 0 ? '+' : ''}{m.quantity}</span>
                </div>
                <div className="text-xs text-gray-500">{new Date(m.created_at).toLocaleString(getLocale())}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="bg-white rounded-2xl border p-6">
        <h3 className="font-semibold mb-4">Traceability — dostawca → partia → sprzedaż / strata</h3>
        <div className="space-y-3">
          {traceability?.batches?.map((lineage: any) => (
            <div key={lineage.batch.id} className="border rounded-xl p-4">
              <div className="font-medium">Partia {lineage.batch.batch_number}</div>
              <div className="text-sm text-gray-600 mt-1">{lineage.supplier?.name || 'Brak dostawcy'} → {lineage.delivery?.document_number || 'Brak dokumentu dostawy'}</div>
              <div className="grid grid-cols-4 gap-2 mt-3 text-center text-xs">
                <div className="bg-blue-50 p-2 rounded-lg">Przyjęto<br/><b>{lineage.summary.received}</b></div>
                <div className="bg-orange-50 p-2 rounded-lg">Sprzedano<br/><b>{lineage.summary.sold}</b></div>
                <div className="bg-red-50 p-2 rounded-lg">Straty<br/><b>{lineage.summary.wasted}</b></div>
                <div className="bg-green-50 p-2 rounded-lg">Dostępne<br/><b>{lineage.summary.available}</b></div>
              </div>
            </div>
          ))}
          {!traceability?.batches?.length && <p className="text-sm text-gray-500">Brak historii partii.</p>}
        </div>
      </div>
    </div>
  )
}
