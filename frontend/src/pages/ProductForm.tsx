import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { api } from '../lib/api'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { parseQuantity, quantityStep } from '../lib/quantity'

export default function ProductForm() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  
  const { data: categories } = useQuery({ queryKey: ['categories'], queryFn: async () => (await api.get('/categories')).data })
  const { data: suppliers } = useQuery({ queryKey: ['suppliers'], queryFn: async () => (await api.get('/suppliers')).data })
  
  const [form, setForm] = useState({ 
    sku: '', 
    ean: searchParams.get('ean') || '', 
    name: searchParams.get('name') || '', 
    brand: searchParams.get('brand') || '', 
    category_id: '', 
    purchase_price: 0, 
    selling_price: 0, 
    min_stock: 5, 
    target_stock: 20, 
    safety_stock: 3, 
    unit: 'szt', 
    requires_expiry_control: true, 
    default_supplier_id: '' 
  })

  const mut = useMutation({
    mutationFn: async (p: any) => (await api.post('/products', p)).data,
    onSuccess: (data) => navigate(`/products/${data.id}`)
  })

  const handle = () => {
    mut.mutate({
      sku: form.sku, ean: form.ean || null, name: form.name, brand: form.brand || null,
      category_id: form.category_id ? parseInt(form.category_id) : null,
      default_supplier_id: form.default_supplier_id ? parseInt(form.default_supplier_id) : null,
      purchase_price: parseFloat(form.purchase_price as any), selling_price: parseFloat(form.selling_price as any),
      min_stock: parseQuantity(form.min_stock, form.unit, true), target_stock: parseQuantity(form.target_stock, form.unit, true), safety_stock: parseQuantity(form.safety_stock, form.unit, true),
      unit: form.unit, requires_expiry_control: form.requires_expiry_control
    })
  }

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <h1 className="text-2xl font-bold">Nowy produkt</h1>
      <div className="bg-white border rounded-2xl p-6 grid md:grid-cols-2 gap-4">
        <div><label className="text-sm">SKU*</label><input value={form.sku} onChange={e => setForm({...form, sku: e.target.value})} className="w-full border rounded-xl px-3 py-2" /></div>
        <div><label className="text-sm">EAN</label><input value={form.ean} onChange={e => setForm({...form, ean: e.target.value})} className="w-full border rounded-xl px-3 py-2" /></div>
        <div className="md:col-span-2"><label className="text-sm">Nazwa*</label><input value={form.name} onChange={e => setForm({...form, name: e.target.value})} className="w-full border rounded-xl px-3 py-2" /></div>
        <div><label className="text-sm">Marka</label><input value={form.brand} onChange={e => setForm({...form, brand: e.target.value})} className="w-full border rounded-xl px-3 py-2" /></div>
        <div><label className="text-sm">Jednostka</label><select value={form.unit} onChange={e => setForm({...form, unit: e.target.value})} className="w-full border rounded-xl px-3 py-2"><option value="szt">szt</option><option value="kg">kg</option><option value="l">l</option><option value="opak">opak</option></select></div>
        <div><label className="text-sm">Kategoria</label><select value={form.category_id} onChange={e => setForm({...form, category_id: e.target.value})} className="w-full border rounded-xl px-3 py-2"><option value="">Wybierz</option>{categories?.map((c: any) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></div>
        <div><label className="text-sm">Dostawca domyślny</label><select value={form.default_supplier_id} onChange={e => setForm({...form, default_supplier_id: e.target.value})} className="w-full border rounded-xl px-3 py-2"><option value="">Wybierz</option>{suppliers?.map((s: any) => <option key={s.id} value={s.id}>{s.name}</option>)}</select></div>
        <div><label className="text-sm">Cena zakupu*</label><input type="number" step="0.01" value={form.purchase_price} onChange={e => setForm({...form, purchase_price: parseFloat(e.target.value) as any})} className="w-full border rounded-xl px-3 py-2" /></div>
        <div><label className="text-sm">Cena sprzedaży*</label><input type="number" step="0.01" value={form.selling_price} onChange={e => setForm({...form, selling_price: parseFloat(e.target.value) as any})} className="w-full border rounded-xl px-3 py-2" /></div>
        <div><label className="text-sm">Min stan</label><input type="number" min="0" step={quantityStep(form.unit)} value={form.min_stock} onChange={e => setForm({...form, min_stock: e.target.value as any})} className="w-full border rounded-xl px-3 py-2" /></div>
        <div><label className="text-sm">Docelowy stan</label><input type="number" min="0" step={quantityStep(form.unit)} value={form.target_stock} onChange={e => setForm({...form, target_stock: e.target.value as any})} className="w-full border rounded-xl px-3 py-2" /></div>
        <div><label className="text-sm">Zapas bezpieczeństwa</label><input type="number" min="0" step={quantityStep(form.unit)} value={form.safety_stock} onChange={e => setForm({...form, safety_stock: e.target.value as any})} className="w-full border rounded-xl px-3 py-2" /></div>
        <div className="flex items-center gap-2"><input type="checkbox" checked={form.requires_expiry_control} onChange={e => setForm({...form, requires_expiry_control: e.target.checked})} /> <label className="text-sm">Wymaga kontroli daty ważności</label></div>
        <div className="md:col-span-2 flex gap-2"><button onClick={handle} disabled={mut.isPending} className="bg-green-600 text-white px-6 py-2.5 rounded-xl">Utwórz produkt</button><button onClick={() => navigate('/products')} className="border px-6 py-2.5 rounded-xl">Anuluj</button></div>
        {mut.isError && (
          <div className="md:col-span-2 text-red-600 text-sm">
            {typeof (mut.error as any).response?.data?.detail === 'string'
              ? (mut.error as any).response?.data?.detail
              : "Błąd walidacji - sprawdź czy poprawnie wypełniłeś wszystkie wymagane pola (SKU, Nazwa, Cena)."}
          </div>
        )}
      </div>
    </div>
  )
}
