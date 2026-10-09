import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../lib/api'
import { useState } from 'react'
import { formatCurrency, formatDateTime } from '../lib/utils'
import { Plus } from 'lucide-react'
import { parseQuantity, quantityStep } from '../lib/quantity'

export default function Deliveries() {
  const [showNew, setShowNew] = useState(false)
  const [form, setForm] = useState({ supplier_id: '', document_number: '', items: [{ product_id: '', quantity_received: '10', purchase_price: '0', expiry_date: '', batch_number: '', location_id: '' }] })
  const qc = useQueryClient()
  const { data: deliveries } = useQuery({ queryKey: ['deliveries'], queryFn: async () => (await api.get('/deliveries')).data })
  const { data: suppliers } = useQuery({ queryKey: ['suppliers'], queryFn: async () => (await api.get('/suppliers')).data })
  const { data: products } = useQuery({ queryKey: ['products-list'], queryFn: async () => (await api.get('/products')).data })
  const { data: locations } = useQuery({ queryKey: ['locations'], queryFn: async () => (await api.get('/locations')).data })

  const mutation = useMutation({
    mutationFn: async (payload: any) => (await api.post('/deliveries', payload)).data,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['deliveries'] }); setShowNew(false); setForm({ supplier_id: '', document_number: '', items: [{ product_id: '', quantity_received: '10', purchase_price: '0', expiry_date: '', batch_number: '', location_id: '' }] }) }
  })

  const handleSubmit = () => {
    const payload = {
      supplier_id: form.supplier_id ? parseInt(form.supplier_id) : null,
      document_number: form.document_number,
      items: form.items.map((it: any) => ({
        product_id: parseInt(it.product_id),
        quantity_received: parseQuantity(it.quantity_received, products?.find((p: any) => p.id === Number(it.product_id))?.unit),
        quantity_ordered: parseQuantity(it.quantity_received, products?.find((p: any) => p.id === Number(it.product_id))?.unit),
        purchase_price: parseFloat(it.purchase_price),
        expiry_date: it.expiry_date || null,
        batch_number: it.batch_number || null,
        location_id: it.location_id ? parseInt(it.location_id) : null
      }))
    }
    mutation.mutate(payload)
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Dostawy</h1>
        <button onClick={() => setShowNew(!showNew)} className="bg-green-600 text-white px-4 py-2 rounded-xl flex items-center gap-2"><Plus className="w-4 h-4" /> Nowa dostawa</button>
      </div>

      {showNew && (
        <div className="bg-white rounded-2xl border p-6 space-y-4">
          <h3 className="font-semibold">Przyjęcie dostawy (workflow)</h3>
          <div className="grid md:grid-cols-3 gap-4">
            <div><label className="text-sm">Dostawca</label><select value={form.supplier_id} onChange={e => setForm({...form, supplier_id: e.target.value})} className="w-full border rounded-xl px-3 py-2"><option value="">Wybierz</option>{suppliers?.map((s: any) => <option key={s.id} value={s.id}>{s.name}</option>)}</select></div>
            <div><label className="text-sm">Nr dokumentu</label><input value={form.document_number} onChange={e => setForm({...form, document_number: e.target.value})} className="w-full border rounded-xl px-3 py-2" placeholder="FV/123/2026" /></div>
          </div>
          {form.items.map((item: any, idx: number) => (
            <div key={idx} className="grid md:grid-cols-6 gap-3 p-3 bg-gray-50 rounded-xl">
              <select value={item.product_id} onChange={e => { const items = [...form.items]; items[idx].product_id = e.target.value; const prod = products?.find((p: any) => p.id === parseInt(e.target.value)); if (prod) items[idx].purchase_price = String(prod.purchase_price); setForm({...form, items}) }} className="border rounded-xl px-2 py-2 text-sm"><option value="">Produkt</option>{products?.map((p: any) => <option key={p.id} value={p.id}>{p.name} ({p.sku})</option>)}</select>
              <input type="number" min="0" step={quantityStep(products?.find((p: any) => p.id === Number(item.product_id))?.unit)} value={item.quantity_received} onChange={e => { const items = [...form.items]; items[idx].quantity_received = e.target.value; setForm({...form, items}) }} className="border rounded-xl px-2 py-2 text-sm" placeholder="Ilość" />
              <input type="number" step="0.01" value={item.purchase_price} onChange={e => { const items = [...form.items]; items[idx].purchase_price = e.target.value; setForm({...form, items}) }} className="border rounded-xl px-2 py-2 text-sm" placeholder="Cena zakupu" />
              <input type="date" value={item.expiry_date} onChange={e => { const items = [...form.items]; items[idx].expiry_date = e.target.value; setForm({...form, items}) }} className="border rounded-xl px-2 py-2 text-sm" />
              <input value={item.batch_number} onChange={e => { const items = [...form.items]; items[idx].batch_number = e.target.value; setForm({...form, items}) }} className="border rounded-xl px-2 py-2 text-sm" placeholder="Nr partii" />
              <select value={item.location_id} onChange={e => { const items = [...form.items]; items[idx].location_id = e.target.value; setForm({...form, items}) }} className="border rounded-xl px-2 py-2 text-sm"><option value="">Lokalizacja</option>{locations?.map((l: any) => <option key={l.id} value={l.id}>{l.name}</option>)}</select>
            </div>
          ))}
          <div className="flex gap-2">
            <button onClick={() => setForm({...form, items: [...form.items, { product_id: '', quantity_received: '10', purchase_price: '0', expiry_date: '', batch_number: '', location_id: '' }]})} className="px-4 py-2 border rounded-xl text-sm">+ Pozycja</button>
            <button onClick={handleSubmit} disabled={mutation.isPending} className="px-6 py-2 bg-green-600 text-white rounded-xl text-sm">Zatwierdź dostawę</button>
          </div>
          {mutation.isError && <div className="text-red-600 text-sm">{(mutation.error as any).response?.data?.detail || 'Błąd'}</div>}
        </div>
      )}

      <div className="bg-white rounded-2xl border overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-xs uppercase text-gray-500"><tr><th className="px-4 py-3 text-left">Dokument</th><th className="px-4 py-3">Dostawca</th><th className="px-4 py-3">Wartość</th><th className="px-4 py-3">Data</th><th className="px-4 py-3">Pozycje</th></tr></thead>
          <tbody className="divide-y">{deliveries?.map((d: any) => <tr key={d.id} className="hover:bg-gray-50"><td className="px-4 py-3 font-medium">{d.document_number}</td><td className="px-4 py-3">{d.supplier_name || '-'}</td><td className="px-4 py-3">{formatCurrency(d.total_value)}</td><td className="px-4 py-3">{formatDateTime(d.created_at)}</td><td className="px-4 py-3">{d.items?.length || 0} poz</td></tr>)}</tbody>
        </table>
      </div>
    </div>
  )
}
