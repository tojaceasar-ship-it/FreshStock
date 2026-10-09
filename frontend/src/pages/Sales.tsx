import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../lib/api'
import { formatCurrency, formatDateTime } from '../lib/utils'
import { useState } from 'react'
import { parseQuantity, quantityStep } from '../lib/quantity'

export default function Sales() {
  const [form, setForm] = useState({ items: [{ product_id: '', quantity: '1' }] })
  const qc = useQueryClient()
  const { data: sales } = useQuery({ queryKey: ['sales'], queryFn: async () => (await api.get('/sales')).data })
  const { data: products } = useQuery({ queryKey: ['products'], queryFn: async () => (await api.get('/products')).data })

  const mutation = useMutation({
    mutationFn: async (payload: any) => (await api.post('/sales', payload)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sales'] })
  })

  const handleSale = () => {
    mutation.mutate({ source: 'manual', items: form.items.map((i: any) => ({ product_id: parseInt(i.product_id), quantity: parseQuantity(i.quantity, products?.find((p: any) => p.id === Number(i.product_id))?.unit) })) })
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Sprzedaż (FEFO)</h1>
      <div className="bg-white rounded-2xl border p-6">
        <h3 className="font-semibold mb-3">Nowa sprzedaż - automatyczne FEFO (najstarsza partia pierwsza)</h3>
        {form.items.map((it: any, idx: number) => (
          <div key={idx} className="flex gap-3 mb-2">
            <select value={it.product_id} onChange={e => { const items = [...form.items]; items[idx].product_id = e.target.value; setForm({ ...form, items }) }} className="border rounded-xl px-3 py-2 flex-1"><option value="">Produkt</option>{products?.map((p: any) => <option key={p.id} value={p.id}>{p.name} - stan {p.total_stock}</option>)}</select>
            <input type="number" min="0" step={quantityStep(products?.find((p: any) => p.id === Number(it.product_id))?.unit)} value={it.quantity} onChange={e => { const items = [...form.items]; items[idx].quantity = e.target.value; setForm({ ...form, items }) }} className="border rounded-xl px-3 py-2 w-24" />
          </div>
        ))}
        <div className="flex gap-2 mt-3">
          <button onClick={() => setForm({ ...form, items: [...form.items, { product_id: '', quantity: '1' }] })} className="border px-3 py-2 rounded-xl text-sm">+ Pozycja</button>
          <button onClick={handleSale} className="bg-green-600 text-white px-4 py-2 rounded-xl text-sm">Sprzedaj (FEFO)</button>
        </div>
        {mutation.isError && <div className="text-red-600 text-sm mt-2">{(mutation.error as any).response?.data?.detail}</div>}
      </div>

      <div className="bg-white rounded-2xl border overflow-hidden">
        <table className="w-full text-sm"><thead className="bg-gray-50 text-xs uppercase"><tr><th className="px-4 py-3 text-left">Nr</th><th className="px-4 py-3">Data</th><th className="px-4 py-3">Wartość</th><th className="px-4 py-3">Pozycje</th><th className="px-4 py-3">Źródło</th></tr></thead><tbody className="divide-y">{sales?.slice(0,50).map((s: any) => <tr key={s.id}><td className="px-4 py-3 font-medium">{s.sale_number}</td><td className="px-4 py-3">{formatDateTime(s.sale_date)}</td><td className="px-4 py-3">{formatCurrency(s.total_amount)}</td><td className="px-4 py-3">{s.items?.length} poz, {s.items?.map((item: any) => `${item.quantity} ${products?.find((p: any) => p.id === item.product_id)?.unit || ''}`).join(', ')}</td><td className="px-4 py-3"><span className="bg-gray-100 px-2 py-1 rounded-full text-xs">{s.source}</span></td></tr>)}</tbody></table>
      </div>
    </div>
  )
}
