import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../lib/api'
import { useState } from 'react'

export default function Locations() {
  const { data: locations } = useQuery({ queryKey: ['locations'], queryFn: async () => (await api.get('/locations')).data })
  const { data: tree } = useQuery({ queryKey: ['locations-tree'], queryFn: async () => (await api.get('/locations/hierarchy/tree')).data })
  const [form, setForm] = useState({ name: '', code: '', type: 'shelf' })
  const qc = useQueryClient()
  const mut = useMutation({ mutationFn: async (p: any) => (await api.post('/locations', p)).data, onSuccess: () => qc.invalidateQueries({ queryKey: ['locations'] }) })

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Lokalizacje magazynowe</h1>
      <div className="bg-white border rounded-2xl p-6">
        <h3 className="font-semibold mb-3">Nowa lokalizacja</h3>
        <div className="flex gap-3"><input value={form.name} onChange={e => setForm({...form, name: e.target.value})} placeholder="Nazwa" className="border rounded-xl px-3 py-2 flex-1" /><input value={form.code} onChange={e => setForm({...form, code: e.target.value})} placeholder="Kod np. SHELF-A3" className="border rounded-xl px-3 py-2" /><select value={form.type} onChange={e => setForm({...form, type: e.target.value})} className="border rounded-xl px-3 py-2"><option value="store">Sklep</option><option value="warehouse">Magazyn</option><option value="fridge">Chłodnia</option><option value="freezer">Mroźnia</option><option value="shelf">Półka</option><option value="aisle">Alejka</option><option value="backroom">Zaplecze</option></select><button onClick={() => mut.mutate(form)} className="bg-green-600 text-white px-4 py-2 rounded-xl">Dodaj</button></div>
      </div>
      <div className="grid md:grid-cols-2 gap-6">
        <div className="bg-white border rounded-2xl p-6">
          <h3 className="font-semibold mb-3">Lista</h3>
          <div className="space-y-1">{locations?.map((l: any) => <div key={l.id} className="flex justify-between text-sm p-2 bg-gray-50 rounded-xl"><span>{l.name} ({l.code})</span><span className="text-xs bg-blue-50 text-blue-700 px-2 py-1 rounded-full">{l.type}</span></div>)}</div>
        </div>
        <div className="bg-white border rounded-2xl p-6">
          <h3 className="font-semibold mb-3">Hierarchia</h3>
          <pre className="text-xs bg-gray-50 p-3 rounded-xl overflow-auto max-h-96">{JSON.stringify(tree, null, 2)}</pre>
        </div>
      </div>
    </div>
  )
}
