import { createContext, ReactNode, useContext, useEffect, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Lock, X } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { api } from '../lib/api'
import { useAuth } from './useAuth'

export type Capabilities = {
  plan: 'STANDARD'|'PRO'|'BUSINESS'|'ENTERPRISE'
  status: string
  price_monthly: number|null
  features: Record<string, boolean>
  limits: Record<string, {used:number; max:number|null}>
  trial_ends_at?: string
  current_period_end?: string
  cancel_at_period_end: boolean
}

const benefits: Record<string, [string,string]> = {
  shelf_mode: ['Shelf Mode', 'Przenieś codzienne zadania pracowników bezpośrednio na telefon.'],
  freshstock_today: ['FreshStock Today', 'Zobacz najważniejsze ryzyka i działania na jednej liście.'],
  savings_dashboard: ['Oszczędności', 'Mierz realnie odzyskaną marżę i ograniczone straty.'],
  ai_restock: ['AI Insights', 'Prognozuj zamówienia, przeceny i ryzyko strat.'],
  multi_store: ['Multi-store', 'Zarządzaj wieloma sklepami z jednego konta.'],
  generic_rest: ['Integracja POS realtime', 'Synchronizuj sprzedaż i stany automatycznie.'],
}

type PlanContextValue = {
  capabilities?: Capabilities
  loading: boolean
  canUseFeature: (feature:string)=>boolean
  showUpgrade: (feature:string)=>void
  refresh: ()=>Promise<unknown>
}
const PlanContext = createContext<PlanContextValue|undefined>(undefined)

export function PlanProvider({children}:{children:ReactNode}) {
  const {user} = useAuth()
  const navigate = useNavigate()
  const [blocked, setBlocked] = useState<string|null>(null)
  const query = useQuery({queryKey:['capabilities'], queryFn:async()=>(await api.get('/me/capabilities')).data as Capabilities, enabled:!!user, staleTime:30_000})
  useEffect(() => {
    const listener = (event:Event) => setBlocked((event as CustomEvent).detail?.feature || 'premium')
    window.addEventListener('freshstock:feature-blocked', listener)
    return () => window.removeEventListener('freshstock:feature-blocked', listener)
  }, [])
  const value = useMemo(()=>({capabilities:query.data, loading:query.isLoading, canUseFeature:(f:string)=>!!query.data?.features?.[f], showUpgrade:setBlocked, refresh:query.refetch}),[query.data,query.isLoading,query.refetch])
  const [title, copy] = benefits[blocked || ''] || ['Funkcja premium','Ta funkcja jest dostępna w wyższym planie FreshStock.']
  return <PlanContext.Provider value={value}>{children}{blocked&&<div className="fixed inset-0 z-[100] flex items-center justify-center bg-slate-950/50 p-4" onClick={()=>setBlocked(null)}><div className="w-full max-w-md rounded-3xl bg-white p-7 shadow-2xl" onClick={e=>e.stopPropagation()}><button className="float-right rounded-lg p-1 text-gray-400 hover:bg-gray-100" onClick={()=>setBlocked(null)}><X/></button><div className="mb-4 inline-flex rounded-2xl bg-green-100 p-3 text-green-700"><Lock/></div><h2 className="text-2xl font-bold text-slate-900">{title}</h2><p className="mt-2 text-gray-600">{copy}</p><p className="mt-4 text-sm font-semibold text-green-700">Dostępne w FreshStock {blocked==='multi_store'?'Business':'Pro'}.</p><button onClick={()=>{setBlocked(null);navigate('/subscription')}} className="mt-6 w-full rounded-xl bg-green-600 px-4 py-3 font-semibold text-white hover:bg-green-700">Zobacz plany</button></div></div>}</PlanContext.Provider>
}

// The provider, gate and hook intentionally share one context module.
// eslint-disable-next-line react-refresh/only-export-components
export function usePlan(){const value=useContext(PlanContext);if(!value)throw new Error('usePlan must be used within PlanProvider');return value}

export function FeatureGate({feature,children}:{feature:string;children:ReactNode}){
  const {canUseFeature,loading,showUpgrade}=usePlan()
  if(loading)return <div className="p-8 text-gray-500">Sprawdzanie planu…</div>
  if(!canUseFeature(feature))return <div className="mx-auto max-w-xl rounded-3xl border bg-white p-10 text-center shadow-sm"><Lock className="mx-auto mb-4 h-10 w-10 text-green-600"/><h2 className="text-2xl font-bold">{benefits[feature]?.[0]||'Funkcja premium'}</h2><p className="mt-3 text-gray-600">{benefits[feature]?.[1]||'Rozszerz plan, aby uzyskać dostęp.'}</p><button onClick={()=>showUpgrade(feature)} className="mt-6 rounded-xl bg-green-600 px-5 py-3 font-semibold text-white">Upgrade</button></div>
  return <>{children}</>
}
