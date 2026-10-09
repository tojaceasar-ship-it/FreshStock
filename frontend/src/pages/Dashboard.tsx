import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo } from 'react'
import { Link } from 'react-router-dom'
import {
  ArrowRight, BadgeEuro, Bell, Boxes, CalendarDays, CheckCircle2,
  ClipboardCheck, Package, RefreshCw, ShoppingCart, Sparkles, TrendingDown,
  Truck, WalletCards,
} from 'lucide-react'
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts'
import { api } from '../lib/api'
import { useAuth } from '../hooks/useAuth'
import { usePlan } from '../hooks/usePlan'
import { formatCurrency } from '../lib/utils'
import { getLocale } from '../lib/i18n'
import { AppCard, appCardClass } from '../components/ui/AppCard'

const card = appCardClass
const palette = ['#16a34a','#38bdf8','#fb7185','#fbbf24','#a78bfa','#64748b']

export default function Dashboard() {
  const { user } = useAuth()
  const { canUseFeature } = usePlan()
  const qc = useQueryClient()
  const { data, isLoading, isFetching, refetch } = useQuery({queryKey:['dashboard'],queryFn:async()=>(await api.get('/dashboard')).data})
  const { data: alerts=[] } = useQuery({queryKey:['dashboard-alerts'],queryFn:async()=>(await api.get('/alerts',{params:{is_resolved:false}})).data})
  const { data: tasks=[] } = useQuery({queryKey:['dashboard-tasks'],queryFn:async()=>(await api.get('/tasks')).data})
  const { data: products=[] } = useQuery({queryKey:['dashboard-products'],queryFn:async()=>(await api.get('/products')).data})
  const { data: savings } = useQuery({queryKey:['dashboard-savings'],queryFn:async()=>(await api.get('/savings',{params:{days:30}})).data,enabled:canUseFeature('savings_dashboard')})

  useEffect(()=>{if((user?.role==='OWNER'||user?.role==='MANAGER')&&canUseFeature('freshstock_today'))api.post('/today/generate').then(()=>qc.invalidateQueries({queryKey:['dashboard-tasks']})).catch(()=>undefined)},[user?.role,canUseFeature,qc])

  const categories=useMemo(()=>{const grouped=new Map<string,number>();products.forEach((p:any)=>grouped.set(p.category_name||'Inne',(grouped.get(p.category_name||'Inne')||0)+Number(p.total_stock||0)*Number(p.purchase_price||0)));return [...grouped].map(([name,value])=>({name,value})).sort((a,b)=>b.value-a.value).slice(0,6)},[products])
  if(isLoading)return <DashboardSkeleton />
  const a=data?.requires_attention||{}, k=data?.kpi||{}, activeTasks=tasks.filter((x:any)=>!['COMPLETED','CANCELLED','SKIPPED'].includes(x.status||x.stored_status))
  const todayTiles=[
    {to:'/batches',icon:CalendarDays,tone:'rose',value:(a.today||0)+(a.in_3_days||0),label:'Kończące się terminy',copy:'Do 3 dni. Rozważ promocję.'},
    {to:'/orders',icon:Boxes,tone:'amber',value:(a.low_stock||0)+(a.out_of_stock||0),label:'Niski stan magazynowy',copy:'Uzupełnij przed brakiem.'},
    {to:'/promotions',icon:BadgeEuro,tone:'emerald',value:a.in_7_days||0,label:'Możliwości przecen',copy:'Produkty z krótką datą.'},
    {to:'/alerts',icon:Truck,tone:'blue',value:a.critical_alerts||0,label:'Wymagają sprawdzenia',copy:'Alerty i rozbieżności.'},
  ]
  return <div className="space-y-7 pb-10">
    <header className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div><h1 className="text-2xl font-extrabold tracking-tight text-slate-950 sm:text-3xl">Panel główny</h1><p className="mt-1 text-sm text-slate-500">Witaj, {user?.full_name?.split(' ')[0]||'Użytkowniku'}. Oto najważniejsze informacje o Twoim sklepie na dzisiaj.</p></div>
      <div className="flex items-center gap-3"><span className="hidden text-sm text-slate-500 md:block">{new Date().toLocaleDateString(getLocale(),{weekday:'long',day:'numeric',month:'long',year:'numeric'})}</span><button onClick={()=>refetch()} className="inline-flex items-center gap-2 rounded-xl bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 shadow-sm ring-1 ring-slate-200 hover:bg-slate-50"><RefreshCw className={`h-4 w-4 ${isFetching?'animate-spin':''}`}/>Odśwież dane</button></div>
    </header>

    <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
      <Kpi icon={WalletCards} label="Wartość magazynu" value={formatCurrency(k.inventory_value||0)} meta={`${k.total_sku||0} aktywnych SKU`} tone="green" trend="Magazyn" />
      <Kpi icon={ShoppingCart} label="Sprzedaż dziś" value={formatCurrency(k.sales_today||0)} meta={`${k.sales_count_today||0} transakcji`} tone="emerald" trend="Dzisiaj" />
      <Kpi icon={CalendarDays} label="Krótka data" value={String((a.today||0)+(a.in_3_days||0))} meta="≤ 3 dni do terminu" tone="red" trend="Pilne" />
      <Kpi icon={Package} label="Niski stan" value={String((a.low_stock||0)+(a.out_of_stock||0))} meta="poniżej minimum" tone="amber" trend="Do zamówienia" />
      <Kpi icon={TrendingDown} label="Straty dziś" value={formatCurrency(k.waste_today||0)} meta="koszt zakupu" tone="rose" trend="Straty" />
    </section>

    <section className="rounded-[22px] bg-gradient-to-br from-emerald-50 via-white to-sky-50 p-5 shadow-[0_12px_35px_rgba(16,185,129,.08)] ring-1 ring-emerald-200/70 sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-3"><div className="flex items-center gap-3"><div className="grid h-11 w-11 place-items-center rounded-2xl bg-green-600 text-white shadow-lg shadow-green-600/20"><Sparkles className="h-5 w-5"/></div><div><h2 className="text-xl font-extrabold text-slate-950">FreshStock Today</h2><p className="text-sm text-slate-500">Kluczowe informacje i rekomendacje na dziś.</p></div></div>{canUseFeature('freshstock_today')&&<Link to="/today" className="inline-flex items-center gap-2 rounded-xl bg-white px-4 py-2 text-sm font-semibold text-slate-700 shadow-sm ring-1 ring-slate-200">Zobacz wszystko <ArrowRight className="h-4 w-4"/></Link>}</div>
      <div className="mt-5 grid gap-3 md:grid-cols-2 xl:grid-cols-4">{todayTiles.map(x=><ActionTile key={x.label}{...x}/>)}</div>
    </section>

    <section className="grid gap-5 xl:grid-cols-3">
      <div className={`${card} p-5`}><SectionTitle title="Sprzedaż produktów" subtitle="Najlepsze wyniki z ostatnich 30 dni"/><Bars rows={(data?.top_sellers||[]).map((x:any)=>({label:x.product_name,value:x.value,display:formatCurrency(x.value)}))} color="#22c55e" empty="Brak sprzedaży w tym okresie"/></div>
      <div className={`${card} p-5`}><SectionTitle title="Ryzyko strat" subtitle="Wartość towaru według terminu"/><Bars rows={[{label:'Dzisiaj',value:data?.financial_risk?.today||0,display:formatCurrency(data?.financial_risk?.today||0)},{label:'1–3 dni',value:data?.financial_risk?.in_3_days||0,display:formatCurrency(data?.financial_risk?.in_3_days||0)},{label:'4–7 dni',value:data?.financial_risk?.in_7_days||0,display:formatCurrency(data?.financial_risk?.in_7_days||0)}]} color="#fb7185" empty="Brak zagrożonego towaru"/></div>
      <div className={`${card} p-5`}><SectionTitle title="Kategorie produktów" subtitle="Udział w wartości magazynu"/><div className="mt-3 grid grid-cols-[150px_1fr] items-center gap-3"><div className="h-40"><ResponsiveContainer width="100%" height="100%"><PieChart><Pie data={categories} dataKey="value" nameKey="name" innerRadius={48} outerRadius={68} strokeWidth={3}>{categories.map((_:any,i:number)=><Cell key={i} fill={palette[i%palette.length]}/>)}</Pie><Tooltip formatter={(v:number)=>formatCurrency(v)}/></PieChart></ResponsiveContainer></div><div className="space-y-2">{categories.map((x:any,i:number)=><div key={x.name} className="flex items-center justify-between gap-2 text-xs"><span className="min-w-0 truncate text-slate-600"><i className="mr-2 inline-block h-2 w-2 rounded-full" style={{background:palette[i%palette.length]}}/>{x.name}</span><b>{formatCurrency(x.value)}</b></div>)}{!categories.length&&<span className="text-sm text-slate-400">Brak danych</span>}</div></div></div>
    </section>

    <section className="grid gap-5 xl:grid-cols-[1.15fr_1.15fr_.8fr]">
      <div className={`${card} overflow-hidden`}><PanelHeader icon={CalendarDays} title="Produkty z kończącym się terminem" to="/batches"/><div className="overflow-x-auto"><table className="w-full min-w-[520px] text-left text-sm"><thead className="bg-slate-50/80 text-[11px] uppercase text-slate-400"><tr><th className="px-5 py-3">Produkt</th><th>Partia</th><th>Ilość</th><th>Termin</th><th className="pr-5">Pozostało</th></tr></thead><tbody className="divide-y divide-slate-100">{data?.expiring_products?.slice(0,6).map((x:any)=><tr key={x.batch_id} className="hover:bg-slate-50"><td className="px-5 py-3 font-semibold"><Link to={`/products/${x.product_id}`}>{x.product_name}</Link></td><td className="text-xs text-slate-500">{x.batch_number}</td><td>{x.quantity}</td><td className="text-xs">{x.expiry_date}</td><td className="pr-5"><DaysBadge days={x.days_until}/></td></tr>)}{!data?.expiring_products?.length&&<tr><td colSpan={5} className="p-8 text-center text-slate-400">Brak produktów z krótką datą</td></tr>}</tbody></table></div></div>
      <div className={`${card} overflow-hidden`}><PanelHeader icon={ClipboardCheck} title="Zadania pracowników" to="/tasks" label="Moje zadania"/><div className="divide-y divide-slate-100">{activeTasks.slice(0,6).map((x:any)=><Link to="/tasks" key={x.id} className="grid grid-cols-[22px_1fr_auto] items-center gap-3 px-5 py-3 hover:bg-slate-50"><span className="h-4 w-4 rounded border border-slate-300"/><div className="min-w-0"><p className="truncate text-sm font-semibold">{x.title}</p><p className="mt-1 text-xs text-slate-400">{x.assigned_user_name||x.assigned_role||'Nieprzypisane'} · {x.due_at?new Date(x.due_at).toLocaleDateString(getLocale()):'bez terminu'}</p></div><div className="text-right"><PriorityBadge value={x.priority}/><p className="mt-1 text-[10px] font-bold text-blue-600">{x.status||x.stored_status}</p></div></Link>)}{!activeTasks.length&&<Empty icon={CheckCircle2} text="Wszystkie zadania wykonane"/>}</div></div>
      <div className={`${card} overflow-hidden`}><PanelHeader icon={Bell} title="Ostatnie alerty" to="/alerts"/><div className="divide-y divide-slate-100">{alerts.slice(0,6).map((x:any)=><Link to="/alerts" key={x.id} className="flex gap-3 px-5 py-3 hover:bg-slate-50"><span className={`mt-1 h-2.5 w-2.5 shrink-0 rounded-full ${x.severity==='critical'?'bg-red-500':x.severity==='high'?'bg-orange-400':'bg-blue-400'}`}/><div className="min-w-0 flex-1"><p className="truncate text-sm font-semibold">{x.product_name||x.title}</p><p className="truncate text-xs text-slate-500">{x.message}</p></div><time className="text-[10px] text-slate-400">{new Date(x.created_at).toLocaleTimeString(getLocale(),{hour:'2-digit',minute:'2-digit'})}</time></Link>)}{!alerts.length&&<Empty icon={CheckCircle2} text="Brak aktywnych alertów"/>}</div></div>
    </section>

    <section className="grid gap-5 xl:grid-cols-2">
      <div className={`${card} p-5`}><div className="flex items-start justify-between"><SectionTitle title="Asystent operacyjny" subtitle="Rekomendacje na podstawie bieżących danych"/><span className="rounded-full bg-violet-100 px-3 py-1 text-[10px] font-bold text-violet-700">AI ASSISTANT</span></div><div className="mt-4 grid gap-3 sm:grid-cols-2">{data?.tasks?.slice(0,4).map((x:any,i:number)=><div key={i} className="rounded-2xl bg-slate-50 p-4"><div className="flex items-center justify-between"><PriorityBadge value={x.priority}/><Sparkles className="h-4 w-4 text-violet-500"/></div><p className="mt-3 text-sm font-semibold text-slate-800">{x.action}</p><Link to={`/tasks?${new URLSearchParams({new:'1',source:'SYSTEM',title:x.action,priority:x.priority||'MEDIUM'})}`} className="mt-4 inline-flex items-center gap-1 text-xs font-bold text-green-700">Utwórz zadanie <ArrowRight className="h-3 w-3"/></Link></div>)}{!data?.tasks?.length&&<Empty icon={CheckCircle2} text="Magazyn nie wymaga pilnych działań"/>}</div></div>
      <div className={`${card} p-5`}><SectionTitle title="Oszczędności FreshStock" subtitle="Efekt przecen i ograniczania strat"/><div className="mt-5 grid grid-cols-2 gap-3"><Saving label="Odzyskana wartość" value={savings?.summary?.recovered_revenue}/><Saving label="Chroniona marża" value={savings?.summary?.protected_margin}/><Saving label="Ograniczone straty" value={savings?.summary?.verified_savings}/><Saving label="Łączne oszczędności" value={savings?.summary?.verified_savings} strong/></div>{canUseFeature('savings_dashboard')?<Link to="/savings" className="mt-5 inline-flex items-center gap-2 text-sm font-bold text-green-700">Pełny Savings Dashboard <ArrowRight className="h-4 w-4"/></Link>:<p className="mt-5 text-sm text-slate-500">Pełna analityka oszczędności jest dostępna w planie Pro.</p>}</div>
    </section>
  </div>
}

function Kpi({icon:Icon,label,value,meta,tone,trend}:any){const colors:any={green:'bg-green-100 text-green-700',emerald:'bg-emerald-100 text-emerald-700',red:'bg-red-100 text-red-600',amber:'bg-amber-100 text-amber-700',rose:'bg-rose-100 text-rose-600'};return <AppCard variant="kpi" padding="compact"><div className="flex items-start justify-between"><div className={`grid h-12 w-12 place-items-center rounded-full ${colors[tone]}`}><Icon className="h-5 w-5"/></div><span className="rounded-full bg-slate-50 px-2 py-1 text-[10px] font-bold text-slate-500">{trend}</span></div><p className="mt-5 text-sm font-medium text-slate-600">{label}</p><p className="mt-1 text-[32px] font-extrabold leading-tight tracking-tight text-slate-950">{value}</p><p className="mt-2 text-xs text-slate-400">{meta}</p></AppCard>}
function ActionTile({to,icon:Icon,tone,value,label,copy}:any){const c:any={rose:'bg-rose-50 text-rose-600',amber:'bg-amber-50 text-amber-700',emerald:'bg-emerald-50 text-emerald-700',blue:'bg-sky-50 text-sky-700'};return <Link to={to} className={`group rounded-2xl p-4 transition hover:-translate-y-0.5 hover:shadow-md ${c[tone]}`}><div className="flex items-center gap-3"><span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-white/80"><Icon className="h-5 w-5"/></span><div className="min-w-0 flex-1"><div className="flex items-center justify-between"><b className="text-2xl">{value}</b><ArrowRight className="h-4 w-4 transition group-hover:translate-x-1"/></div><p className="truncate text-xs font-bold">{label}</p><p className="truncate text-[10px] opacity-70">{copy}</p></div></div></Link>}
function SectionTitle({title,subtitle}:{title:string;subtitle:string}){return <div><h3 className="font-bold text-slate-900">{title}</h3><p className="mt-0.5 text-xs text-slate-400">{subtitle}</p></div>}
function Bars({rows,color,empty}:{rows:any[];color:string;empty:string}){const max=Math.max(...rows.map(x=>Number(x.value)),0);return <div className="mt-6 space-y-4">{rows.slice(0,5).map((x:any)=><div key={x.label}><div className="mb-1.5 flex justify-between gap-3 text-xs"><span className="truncate text-slate-600">{x.label}</span><b>{x.display}</b></div><div className="h-2 rounded-full bg-slate-100"><div className="h-full rounded-full transition-all" style={{width:`${max?Math.max(5,x.value/max*100):0}%`,background:color}}/></div></div>)}{!rows.length&&<p className="py-10 text-center text-sm text-slate-400">{empty}</p>}</div>}
function PanelHeader({icon:Icon,title,to,label='Zobacz wszystkie'}:any){return <div className="flex items-center justify-between border-b border-slate-100 px-5 py-4"><h3 className="flex items-center gap-2 font-bold"><Icon className="h-4 w-4 text-green-600"/>{title}</h3><Link to={to} className="text-xs font-semibold text-slate-500 hover:text-green-700">{label}</Link></div>}
function DaysBadge({days}:{days:number}){return <span className={`rounded-full px-2.5 py-1 text-[10px] font-bold ${days<0?'bg-red-600 text-white':days<=2?'bg-red-100 text-red-700':days<=4?'bg-orange-100 text-orange-700':'bg-amber-100 text-amber-700'}`}>{days<0?'Po terminie':`${days} dni`}</span>}
function PriorityBadge({value}:any){return <span className={`rounded-full px-2 py-1 text-[9px] font-extrabold ${value==='CRITICAL'||value==='HIGH'?'bg-red-100 text-red-700':value==='MEDIUM'?'bg-amber-100 text-amber-700':'bg-emerald-100 text-emerald-700'}`}>{value||'NORMAL'}</span>}
function Empty({icon:Icon,text}:any){return <div className="col-span-full p-8 text-center text-sm text-slate-400"><Icon className="mx-auto mb-2 h-7 w-7 text-green-500"/>{text}</div>}
function Saving({label,value,strong}:any){return <div className={`rounded-2xl p-4 ${strong?'bg-green-600 text-white':'bg-slate-50'}`}><p className={`text-xs ${strong?'text-green-100':'text-slate-500'}`}>{label}</p><p className="mt-1 text-xl font-extrabold">{formatCurrency(value||0)}</p></div>}
function DashboardSkeleton(){return <div className="animate-pulse space-y-6"><div className="h-16 rounded-2xl bg-slate-200"/><div className="grid grid-cols-2 gap-3 xl:grid-cols-5">{[1,2,3,4,5].map(x=><div key={x} className="h-36 rounded-2xl bg-slate-200"/>)}</div><div className="h-52 rounded-3xl bg-slate-200"/><div className="grid gap-4 xl:grid-cols-3">{[1,2,3].map(x=><div key={x} className="h-64 rounded-2xl bg-slate-200"/>)}</div></div>}
