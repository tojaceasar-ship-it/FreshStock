import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../lib/api'
import { useState } from 'react'
import { Trash2 } from 'lucide-react'
import { useAuth } from '../hooks/useAuth'

export default function Users() {
  const { user: currentUser } = useAuth()
  const { data: users } = useQuery({ queryKey: ['users'], queryFn: async () => (await api.get('/users')).data })
  const [form, setForm] = useState({ email: '', username: '', password: '', full_name: '', role: 'EMPLOYEE' })
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const qc = useQueryClient()
  const mut = useMutation({ mutationFn: async (p: any) => (await api.post('/users', p)).data, onSuccess: () => qc.invalidateQueries({ queryKey: ['users'] }) })
  const deleteMut = useMutation({
    mutationFn: async (id: number) => (await api.delete(`/users/${id}`)).data,
    onSuccess: data => {
      setError('')
      setMessage(data.message || 'Użytkownik został usunięty')
      qc.invalidateQueries({ queryKey: ['users'] })
    },
    onError: (err: any) => {
      setMessage('')
      setError(err?.response?.data?.detail || 'Nie udało się usunąć użytkownika')
    }
  })

  const removeUser = (target: any) => {
    setMessage('')
    setError('')
    if (target.id === currentUser?.id) {
      setError('Nie możesz usunąć własnego konta')
      return
    }
    if (window.confirm(`Czy na pewno usunąć użytkownika ${target.full_name} (${target.username})? Tej operacji nie można cofnąć.`)) {
      deleteMut.mutate(target.id)
    }
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Użytkownicy i RBAC</h1>
      {message && <div className="bg-green-50 border border-green-200 text-green-800 p-3 rounded-xl text-sm">{message}</div>}
      {error && <div className="bg-red-50 border border-red-200 text-red-800 p-3 rounded-xl text-sm">{error}</div>}
      <div className="bg-white border rounded-2xl p-6">
        <h3 className="font-semibold mb-3">Nowy użytkownik</h3>
        <div className="grid md:grid-cols-5 gap-3">
          <input value={form.email} onChange={e => setForm({...form, email: e.target.value})} placeholder="Email" className="border rounded-xl px-3 py-2" />
          <input value={form.username} onChange={e => setForm({...form, username: e.target.value})} placeholder="Username" className="border rounded-xl px-3 py-2" />
          <input value={form.full_name} onChange={e => setForm({...form, full_name: e.target.value})} placeholder="Imię i nazwisko" className="border rounded-xl px-3 py-2" />
          <input value={form.password} onChange={e => setForm({...form, password: e.target.value})} placeholder="Hasło" type="password" className="border rounded-xl px-3 py-2" />
          <select value={form.role} onChange={e => setForm({...form, role: e.target.value})} className="border rounded-xl px-3 py-2"><option value="OWNER">OWNER</option><option value="MANAGER">MANAGER</option><option value="WAREHOUSE">WAREHOUSE</option><option value="EMPLOYEE">EMPLOYEE</option><option value="VIEWER">VIEWER</option></select>
        </div>
        <button onClick={() => mut.mutate(form)} className="mt-3 bg-green-600 text-white px-4 py-2 rounded-xl text-sm">Dodaj</button>
      </div>
      <div className="bg-white border rounded-2xl overflow-x-auto"><table className="w-full text-sm"><thead className="bg-gray-50 text-xs uppercase"><tr><th className="px-4 py-3 text-left">Użytkownik</th><th className="px-4 py-3">Email</th><th className="px-4 py-3">Rola</th><th className="px-4 py-3">Aktywny</th><th className="px-4 py-3">Akcje</th></tr></thead><tbody className="divide-y">{users?.map((u: any) => <tr key={u.id}><td className="px-4 py-3 font-medium">{u.full_name} ({u.username})</td><td className="px-4 py-3">{u.email}</td><td className="px-4 py-3 text-center"><span className="bg-blue-50 text-blue-700 px-2 py-1 rounded-full text-xs">{u.role}</span></td><td className="px-4 py-3 text-center">{u.is_active ? '✅' : '❌'}</td><td className="px-4 py-3 text-center"><button onClick={() => removeUser(u)} disabled={u.id === currentUser?.id || (deleteMut.isPending && deleteMut.variables === u.id)} title={u.id === currentUser?.id ? 'Nie możesz usunąć własnego konta' : 'Usuń użytkownika'} className="inline-flex items-center gap-1.5 text-red-600 hover:bg-red-50 px-3 py-1.5 rounded-lg disabled:opacity-30 disabled:cursor-not-allowed"><Trash2 className="w-4 h-4" /> Usuń</button></td></tr>)}</tbody></table></div>
      <div className="bg-gray-50 border rounded-2xl p-4 text-xs"><b>Uprawnienia:</b> OWNER — pełna administracja; MANAGER — katalog, sprzedaż, zamówienia i raporty; WAREHOUSE — dostawy, stany, lokalizacje i inwentaryzacje; EMPLOYEE — skanowanie, sprzedaż i zgłaszanie strat; VIEWER — tylko odczyt.</div>
    </div>
  )
}
