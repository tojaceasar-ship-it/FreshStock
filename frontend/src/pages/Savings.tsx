import { useQuery } from '@tanstack/react-query'
import { ArrowDownRight, BadgeEuro, ShieldCheck, Sparkles, TrendingUp } from 'lucide-react'
import { api } from '../lib/api'
import { formatCurrency } from '../lib/utils'
import { AppCard } from '../components/ui/AppCard'

export default function Savings() {
  const { data, isLoading } = useQuery({ queryKey: ['savings', 30], queryFn: async () => (await api.get('/savings', { params: { days: 30 } })).data })
  if (isLoading) return <div className="h-64 animate-pulse rounded-2xl bg-gray-200" />
  const summary = data?.summary || {}
  const opportunities = data?.opportunities || {}
  const money = (value: number) => formatCurrency(value, data?.currency || 'PLN')

  return (
    <div className="space-y-6">
      <div><div className="flex items-center gap-2 text-sm font-semibold text-green-700"><BadgeEuro className="h-4 w-4" /> Savings Dashboard</div><h1 className="text-2xl font-bold">Oszczędności FreshStock</h1><p className="text-sm text-gray-500">Zweryfikowane wyniki z rzeczywistej sprzedaży przecenionych partii — ostatnie 30 dni.</p></div>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Card icon={ShieldCheck} label="Zweryfikowane oszczędności" value={money(summary.verified_savings || 0)} description="Koszt towaru pokryty sprzedażą" tone="green" />
        <Card icon={TrendingUp} label="Odzyskany przychód" value={money(summary.recovered_revenue || 0)} description={`${summary.units_rescued || 0} uratowanych sztuk`} tone="blue" />
        <Card icon={BadgeEuro} label="Chroniona marża" value={money(summary.protected_margin || 0)} description="Przychód ponad pokryty koszt" tone="emerald" />
        <Card icon={ArrowDownRight} label="Straty w okresie" value={money(summary.current_waste || 0)} description={`Poprzedni okres: ${money(summary.previous_waste || 0)}`} tone="red" />
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <AppCard variant="financial" className="border-amber-100"><div className="flex items-center gap-2 font-bold text-amber-900"><Sparkles className="h-5 w-5" /> Kolejne możliwości</div><div className="mt-5 text-[34px] font-extrabold text-amber-900">{money(opportunities.at_risk_cost || 0)}</div><p className="mt-1 text-sm text-amber-800">kosztu nadal zagrożonego w {opportunities.count || 0} partiach</p><div className="mt-5 rounded-2xl bg-white/80 p-4 text-sm shadow-sm"><b>{money(opportunities.potential_recovered_revenue || 0)}</b> potencjalnego przychodu po sugerowanych przecenach</div></AppCard>
        <AppCard variant="list" padding="none" className="lg:col-span-2"><div className="border-b border-slate-100 p-6 font-bold">Najwięcej uratowane według produktu</div><div className="divide-y divide-slate-100">{data?.by_product?.map((row: any) => <div key={row.product_id} className="flex items-center justify-between p-5 text-sm"><div><div className="font-semibold">{row.product_name}</div><div className="text-xs text-gray-500">{row.units} szt. · przychód {money(row.recovered_revenue)}</div></div><div className="font-bold text-green-700">{money(row.protected_cost)}</div></div>)}{!data?.by_product?.length && <div className="p-10 text-center text-sm text-gray-500">🎉<br/>Pierwsze wyniki pojawią się po sprzedaży partii objętej Smart Markdown.</div>}</div></AppCard>
      </div>

      <AppCard><h2 className="font-bold">Jak liczymy wynik?</h2><div className="mt-4 grid gap-4 text-sm text-gray-600 md:grid-cols-3"><p><b className="text-gray-900">Zweryfikowane oszczędności:</b> {data?.methodology?.verified_savings}</p><p><b className="text-gray-900">Odzyskany przychód:</b> {data?.methodology?.recovered_revenue}</p><p><b className="text-gray-900">Zmiana strat:</b> {data?.methodology?.waste_reduction}</p></div><p className="mt-4 text-xs text-gray-400">{data?.methodology?.tracking_started}</p></AppCard>
    </div>
  )
}

function Card({ icon: Icon, label, value, description, tone }: any) {
  const colors: Record<string, string> = { green: 'bg-green-100 text-green-700', blue: 'bg-blue-100 text-blue-700', emerald: 'bg-emerald-100 text-emerald-700', red: 'bg-red-100 text-red-700' }
  return <AppCard variant="kpi"><div className={`mb-5 flex h-12 w-12 items-center justify-center rounded-full ${colors[tone]}`}><Icon className="h-5 w-5" /></div><div className="text-sm font-medium text-slate-600">{label}</div><div className="mt-2 text-[34px] font-extrabold leading-none tracking-tight">{value}</div><div className="mt-3 text-sm text-gray-500">{description}</div></AppCard>
}
