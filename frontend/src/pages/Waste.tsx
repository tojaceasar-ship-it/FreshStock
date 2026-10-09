import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../lib/api'
import { formatCurrency } from '../lib/utils'
import { getLocale } from '../lib/i18n'
import { useState } from 'react'
import { parseQuantity, quantityStep } from '../lib/quantity'

export default function Waste() {
  const { data: wastes } = useQuery({ queryKey: ['waste'], queryFn: async () => (await api.get('/waste')).data })
  const { data: stats } = useQuery({ queryKey: ['waste-stats'], queryFn: async () => (await api.get('/waste/stats')).data })
  const { data: products } = useQuery({ queryKey: ['products'], queryFn: async () => (await api.get('/products')).data })
  const [form, setForm] = useState({ product_id: '', quantity: '1', reason: 'expired', notes: '' })
  const qc = useQueryClient()
  const mutation = useMutation({ mutationFn: async (p: any) => (await api.post('/waste', p)).data, onSuccess: () => qc.invalidateQueries({ queryKey: ['waste'] }) })

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Straty</h1>
      <div className="grid md:grid-cols-4 gap-4">
        <div className="bg-white border rounded-2xl p-4"><div className="text-xs text-gray-500">Dziś</div><div className="text-xl font-bold text-red-600">{formatCurrency(stats?.today || 0)}</div></div>
        <div className="bg-white border rounded-2xl p-4"><div className="text-xs text-gray-500">Tydzień</div><div className="text-xl font-bold">{formatCurrency(stats?.week || 0)}</div></div>
        <div className="bg-white border rounded-2xl p-4"><div className="text-xs text-gray-500">Miesiąc</div><div className="text-xl font-bold">{formatCurrency(stats?.month || 0)}</div></div>
        <div className="bg-white border rounded-2xl p-4"><div className="text-xs text-gray-500">Razem</div><div className="text-xl font-bold">{formatCurrency(stats?.total_value || 0)}</div></div>
      </div>

      <div className="bg-white rounded-2xl border p-6">
        <h3 className="font-semibold mb-3">Zgłoś stratę (FEFO jeśli brak partii)</h3>
        <div className="grid md:grid-cols-5 gap-3">
          <select value={form.product_id} onChange={e => setForm({ ...form, product_id: e.target.value })} className="border rounded-xl px-3 py-2"><option value="">Produkt</option>{products?.map((p: any) => <option key={p.id} value={p.id}>{p.name}</option>)}</select>
          <input type="number" min="0" step={quantityStep(products?.find((p: any) => p.id === Number(form.product_id))?.unit)} value={form.quantity} onChange={e => setForm({ ...form, quantity: e.target.value })} className="border rounded-xl px-3 py-2" />
          <select value={form.reason} onChange={e => setForm({ ...form, reason: e.target.value })} className="border rounded-xl px-3 py-2"><option value="expired">Przeterminowane</option><option value="damaged">Uszkodzone</option><option value="spoiled">Zepsute</option><option value="theft">Kradzież</option><option value="inventory_difference">Różnica inwent.</option><option value="other">Inne</option></select>
          <input value={form.notes} onChange={e => setForm({ ...form, notes: e.target.value })} className="border rounded-xl px-3 py-2" placeholder="Powód" />
          <button onClick={() => mutation.mutate({ product_id: parseInt(form.product_id), quantity: parseQuantity(form.quantity, products?.find((p: any) => p.id === Number(form.product_id))?.unit), reason: form.reason, notes: form.notes })} className="bg-red-600 text-white rounded-xl px-4 py-2">Zgłoś</button>
        </div>
      </div>

      <div className="bg-white rounded-2xl border overflow-hidden">
        <table className="w-full text-sm"><thead className="bg-gray-50 text-xs uppercase"><tr><th className="px-4 py-3 text-left">Produkt</th><th className="px-4 py-3">Ilość</th><th className="px-4 py-3">Wartość zakupu</th><th className="px-4 py-3">Powód</th><th className="px-4 py-3">Data</th></tr></thead><tbody className="divide-y">{wastes?.map((w: any) => <tr key={w.id}><td className="px-4 py-3">{w.product_name}</td><td className="px-4 py-3">{w.quantity}</td><td className="px-4 py-3">{formatCurrency(w.purchase_value)}</td><td className="px-4 py-3"><span className="bg-red-50 text-red-700 px-2 py-1 rounded-full text-xs">{w.reason}</span></td><td className="px-4 py-3 text-xs">{new Date(w.created_at).toLocaleString(getLocale())}</td></tr>)}</tbody></table>
      </div>
    </div>
  )
}
