import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../lib/api'
import { getLocale } from '../lib/i18n'
import { Link } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'

export default function Alerts() {
  const { user } = useAuth()
  const canCreateTask = user?.role === 'OWNER' || user?.role === 'MANAGER'
  const qc = useQueryClient()
  const { data: alerts } = useQuery({ queryKey: ['alerts'], queryFn: async () => (await api.get('/alerts')).data })
  const generate = useMutation({ mutationFn: async () => (await api.post('/alerts/generate')).data, onSuccess: () => qc.invalidateQueries({ queryKey: ['alerts'] }) })
  const read = useMutation({ mutationFn: async (id: number) => (await api.put(`/alerts/${id}/read`)).data, onSuccess: () => qc.invalidateQueries({ queryKey: ['alerts'] }) })
  const resolve = useMutation({ mutationFn: async (id: number) => (await api.put(`/alerts/${id}/resolve`)).data, onSuccess: () => qc.invalidateQueries({ queryKey: ['alerts'] }) })

  const severityColor = (s: string) => s === 'critical' ? 'bg-red-50 border-red-200 text-red-800' : s === 'high' ? 'bg-orange-50 border-orange-200 text-orange-800' : s === 'medium' ? 'bg-amber-50 border-amber-200 text-amber-800' : 'bg-blue-50 border-blue-200 text-blue-800'

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between"><h1 className="text-2xl font-bold">Alerty</h1><button onClick={() => generate.mutate()} className="bg-green-600 text-white px-4 py-2 rounded-xl text-sm">Generuj alerty</button></div>
      <div className="grid gap-3">
        {alerts?.map((a: any) => (
          <div key={a.id} className={`p-4 rounded-2xl border ${severityColor(a.severity)} ${a.is_resolved ? 'opacity-60' : ''}`}>
            <div className="flex items-start justify-between">
              <div><div className="font-semibold text-sm">{a.title}</div><div className="text-sm mt-1">{a.message}</div><div className="text-xs mt-2 opacity-70">{a.alert_type} • {new Date(a.created_at).toLocaleString(getLocale())} {a.product_name && `• ${a.product_name}`}</div></div>
              <div className="flex gap-2 ml-4">
                {canCreateTask && <Link to={`/tasks?${new URLSearchParams({new:'1',source:'ALERT',title:`Sprawdź: ${a.title}`,task_type:a.alert_type==='expired'||a.alert_type==='expiring_soon'?'EXPIRY_CHECK':a.alert_type==='low_stock'||a.alert_type==='out_of_stock'?'RESTOCK':'GENERAL',priority:String(a.severity||'MEDIUM').toUpperCase(),...(a.product_id?{product_id:String(a.product_id)}:{}),...(a.batch_id?{batch_id:String(a.batch_id)}:{})})}`} className="text-xs bg-green-600 text-white px-3 py-1 rounded-full">Utwórz zadanie</Link>}
                {!a.is_read && <button onClick={() => read.mutate(a.id)} className="text-xs bg-white border px-2 py-1 rounded-full">Przeczytane</button>}
                {!a.is_resolved && <button onClick={() => resolve.mutate(a.id)} className="text-xs bg-gray-900 text-white px-3 py-1 rounded-full">Rozwiąż</button>}
              </div>
            </div>
          </div>
        ))}
        {!alerts?.length && <div className="bg-white border rounded-2xl p-8 text-center text-gray-500">Brak alertów - wszystko OK ✅</div>}
      </div>
    </div>
  )
}
