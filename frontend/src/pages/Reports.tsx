import { useQuery } from '@tanstack/react-query'
import { api } from '../lib/api'
import { formatCurrency } from '../lib/utils'

export default function Reports() {
  const { data: sales } = useQuery({ queryKey: ['report-sales'], queryFn: async () => (await api.get('/reports/sales')).data })
  const { data: waste } = useQuery({ queryKey: ['report-waste'], queryFn: async () => (await api.get('/reports/waste')).data })
  const { data: inv } = useQuery({ queryKey: ['report-inv'], queryFn: async () => (await api.get('/reports/inventory-value')).data })
  const { data: rotation } = useQuery({ queryKey: ['report-rotation'], queryFn: async () => (await api.get('/reports/rotation')).data })

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Raporty</h1>

      <div className="grid md:grid-cols-3 gap-4">
        <div className="bg-white border rounded-2xl p-5"><div className="text-sm text-gray-500">Sprzedaż 30d</div><div className="text-2xl font-bold">{formatCurrency(sales?.total_value || 0)}</div><div className="text-xs text-gray-500">{sales?.total_quantity} szt</div></div>
        <div className="bg-white border rounded-2xl p-5"><div className="text-sm text-gray-500">Straty 30d</div><div className="text-2xl font-bold text-red-600">{formatCurrency(waste?.total_value || 0)}</div></div>
        <div className="bg-white border rounded-2xl p-5"><div className="text-sm text-gray-500">Wartość magazynu (koszt)</div><div className="text-2xl font-bold">{formatCurrency(inv?.total_cost_value || 0)}</div><div className="text-xs text-gray-500">Detalic: {formatCurrency(inv?.total_retail_value || 0)}</div></div>
      </div>

      <div className="grid lg:grid-cols-2 gap-6">
        <div className="bg-white border rounded-2xl p-6">
          <h3 className="font-semibold mb-4">Sprzedaż wg produktów</h3>
          <div className="space-y-2 max-h-96 overflow-auto">{sales?.by_product?.slice(0,15).map((p: any) => <div key={p.product_id} className="flex justify-between text-sm p-2 hover:bg-gray-50 rounded-xl"><span className="truncate flex-1">{p.product_name}</span><span className="font-medium ml-2">{p.quantity} szt • {formatCurrency(p.value)}</span></div>)}</div>
        </div>
        <div className="bg-white border rounded-2xl p-6">
          <h3 className="font-semibold mb-4">Rotacja</h3>
          <div className="overflow-auto max-h-96">
            <table className="w-full text-xs"><thead className="text-gray-500 uppercase"><tr><th className="text-left">Produkt</th><th>Stan</th><th>Śr/d</th><th>Dni do końca</th><th>Turnover</th></tr></thead><tbody>{rotation?.slice(0,20).map((r: any) => <tr key={r.product_id} className="border-t"><td className="py-2 truncate max-w-[150px]">{r.product_name}</td><td className="text-center">{r.current_stock}</td><td className="text-center">{r.avg_daily_sales}</td><td className="text-center">{r.days_until_stockout ?? '∞'}</td><td className="text-center">{r.stock_turnover}</td></tr>)}</tbody></table>
          </div>
        </div>
      </div>

      <div className="bg-white border rounded-2xl p-6">
        <h3 className="font-semibold mb-4">Wartość wg kategorii</h3>
        <div className="grid md:grid-cols-3 gap-3">{inv?.by_category?.map((c: any) => <div key={c.category} className="bg-gray-50 p-3 rounded-xl"><div className="font-medium text-sm">{c.category}</div><div className="text-xs text-gray-500">{c.quantity} szt</div><div className="text-sm font-bold">{formatCurrency(c.cost_value)} koszt / {formatCurrency(c.retail_value)} detal</div></div>)}</div>
      </div>
    </div>
  )
}
