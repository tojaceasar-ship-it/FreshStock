import { useQuery } from '@tanstack/react-query'
import { api } from '../lib/api'
import { Link } from 'react-router-dom'

export default function AI() {
  const { data: insights } = useQuery({ queryKey: ['ai-insights'], queryFn: async () => (await api.post('/ai/insights')).data })

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">AI Insights - Asystent</h1>
      <div className="bg-gradient-to-br from-purple-50 to-indigo-50 border border-purple-200 rounded-2xl p-6">
        <p className="text-sm text-purple-800">Moduł AI przygotowany pod LLM. Obecnie używa reguł biznesowych (sprzedaż, stany, daty, straty). W przyszłości: pogoda, trendy, dostawy, promocje. Endpoint: POST /api/ai/insights</p>
      </div>
      <div className="grid gap-4">
        {insights?.map((ins: any, i: number) => (
          <div key={i} className="bg-white border rounded-2xl p-5">
            <div className="flex items-start justify-between"><div><div className="font-semibold">{ins.title}</div><div className="text-sm text-gray-600 mt-2">{ins.message}</div><div className="text-xs mt-3 flex flex-wrap gap-2"><span className="bg-gray-100 px-2 py-1 rounded-full">{ins.type}</span><span className={`px-2 py-1 rounded-full ${ins.severity === 'critical' ? 'bg-red-100 text-red-700' : ins.severity === 'high' ? 'bg-orange-100 text-orange-700' : 'bg-blue-100 text-blue-700'}`}>{ins.severity}</span><span className="bg-green-50 text-green-700 px-2 py-1 rounded-full">{ins.action}</span><Link to={`/tasks?${new URLSearchParams({new:'1',source:'AI',title:ins.title,task_type:ins.type==='expiry_waste'?'EXPIRY_CHECK':ins.type==='stockout_risk'?'RESTOCK':'GENERAL',priority:String(ins.severity||'MEDIUM').toUpperCase(),...(ins.product_id?{product_id:String(ins.product_id)}:{}),...(ins.data?.batch_id?{batch_id:String(ins.data.batch_id)}:{}),...(ins.data?.quantity?{quantity:String(ins.data.quantity)}:{})})}`} className="rounded-full bg-purple-600 px-3 py-1 text-white">Utwórz zadanie</Link></div></div><div className="ml-4 text-xs bg-gray-50 p-3 rounded-xl"><pre>{JSON.stringify(ins.data, null, 2)}</pre></div></div>
          </div>
        ))}
      </div>
    </div>
  )
}
