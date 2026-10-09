import { useQuery } from '@tanstack/react-query'
import { api } from '../lib/api'
import { formatCurrency, formatDate, daysUntil, getExpiryColor } from '../lib/utils'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'

export default function Batches() {
  const { user } = useAuth()
  const [filter, setFilter] = useState('all')
  const { data } = useQuery({
    queryKey: ['batches', filter],
    queryFn: async () => {
      const params: any = {}
      if (filter === 'expired') params.expired = true
      if (filter === 'today') {
        const res = await api.get('/dashboard/expiry')
        return res.data.today?.items || []
      }
      if (filter !== 'all' && filter !== 'expired' && filter !== 'today') {
        params.expiring_in_days = parseInt(filter)
      }
      if (filter === 'all' || filter === 'expired') {
        const res = await api.get('/batches', { params })
        return res.data
      } else if (filter === 'today') {
        return []
      } else {
        const res = await api.get('/batches', { params })
        return res.data
      }
    }
  })

  const { data: overview } = useQuery({
    queryKey: ['expiry-overview'],
    queryFn: async () => (await api.get('/batches/expiry/overview')).data
  })

  const { data: expiryDashboard } = useQuery({
    queryKey: ['expiry-dashboard'],
    queryFn: async () => (await api.get('/dashboard/expiry')).data
  })

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Daty ważności / Partie</h1>

      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-3">
        {[
          { key: 'expired', label: 'Przeterminowane', color: 'bg-red-50 border-red-200 text-red-700' },
          { key: 'today', label: 'Dzisiaj', color: 'bg-orange-50 border-orange-200 text-orange-700' },
          { key: '1', label: '1 dzień', color: 'bg-amber-50 border-amber-200 text-amber-700' },
          { key: '3', label: '3 dni', color: 'bg-yellow-50 border-yellow-200 text-yellow-700' },
          { key: '7', label: '7 dni', color: 'bg-lime-50 border-lime-200 text-lime-700' },
          { key: '14', label: '14 dni', color: 'bg-blue-50 border-blue-200 text-blue-700' },
          { key: '30', label: '30 dni', color: 'bg-gray-50 border-gray-200 text-gray-700' },
        ].map(cat => {
          const bucket = expiryDashboard?.[cat.key]
          const count = bucket?.count ?? overview?.buckets?.[cat.key === 'expired' ? 'expired' : cat.key === 'today' ? 'today' : `${cat.key}_days`] ?? 0
          return (
            <button key={cat.key} onClick={() => setFilter(cat.key)} className={`p-4 rounded-xl border text-left ${filter === cat.key ? 'ring-2 ring-green-500' : ''} ${cat.color}`}>
              <div className="text-2xl font-bold">{count}</div>
              <div className="text-xs font-medium">{cat.label}</div>
              {bucket?.total_value && <div className="text-xs mt-1">{formatCurrency(bucket.total_value)}</div>}
            </button>
          )
        })}
      </div>

      <div className="bg-white rounded-2xl border overflow-hidden">
        <div className="p-4 border-b flex items-center justify-between">
          <h3 className="font-semibold">Partie - {filter === 'all' ? 'Wszystkie' : filter}</h3>
          <select value={filter} onChange={e => setFilter(e.target.value)} className="border rounded-xl px-3 py-1.5 text-sm">
            <option value="all">Wszystkie</option>
            <option value="expired">Przeterminowane</option>
            <option value="today">Dzisiaj</option>
            <option value="1">1 dzień</option>
            <option value="3">3 dni</option>
            <option value="7">7 dni</option>
            <option value="14">14 dni</option>
            <option value="30">30 dni</option>
          </select>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-xs uppercase text-gray-500">
              <tr><th className="px-4 py-2 text-left">Produkt</th><th className="px-4 py-2">Partia</th><th className="px-4 py-2">Data ważności</th><th className="px-4 py-2">Dni</th><th className="px-4 py-2">Ilość</th><th className="px-4 py-2">Wartość</th><th className="px-4 py-2">Działanie</th></tr>
            </thead>
            <tbody className="divide-y">
              {(filter === 'today' || filter === '1' || filter === '3' || filter === '7' || filter === '14' || filter === '30' ? expiryDashboard?.[filter]?.items : data)?.map((b: any) => {
                const days = b.days_until ?? daysUntil(b.expiry_date)
                return (
                  <tr key={b.batch_id || b.id} className="hover:bg-gray-50">
                    <td className="px-4 py-2"><div className="font-medium">{b.product_name}</div><div className="text-xs text-gray-500">{b.sku} • {b.ean || ''}</div></td>
                    <td className="px-4 py-2 text-xs">{b.batch_number}</td>
                    <td className="px-4 py-2">{formatDate(b.expiry_date)}</td>
                    <td className="px-4 py-2"><span className={`px-2 py-1 rounded-full text-xs border ${getExpiryColor(days)}`}>{days !== null ? `${days}d` : '-'}</span></td>
                    <td className="px-4 py-2 font-medium">{b.quantity ?? b.quantity_available} {b.product_unit || ''}</td>
                    <td className="px-4 py-2">{formatCurrency(b.value || 0)}</td>
                    <td className="px-4 py-2"><div className="flex flex-wrap justify-center gap-1"><span className="text-xs bg-blue-50 text-blue-700 px-2 py-1 rounded-full">{days !== null && days <= 7 ? 'Przecena' : days !== null && days < 0 ? 'Strata' : 'OK'}</span>{(user?.role==='OWNER'||user?.role==='MANAGER')&&<Link to={`/tasks?${new URLSearchParams({new:'1',title:`Sprawdź datę: ${b.product_name}`,task_type:'EXPIRY_CHECK',priority:days!==null&&days<=1?'CRITICAL':'HIGH',product_id:String(b.product_id||''),batch_id:String(b.batch_id||b.id),quantity:String(b.quantity||'')})}`} className="text-xs bg-green-600 text-white px-2 py-1 rounded-full">Zadanie</Link>}</div></td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
