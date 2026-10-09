import { Outlet, NavLink, useNavigate, useLocation } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'
import { 
  LayoutDashboard, Package, Truck, ShoppingCart, AlertTriangle,
  BarChart3, LogOut, ScanLine, Archive, Tag, Trash2,
  ClipboardList, Users, MapPin, Brain, Menu, X, Bell, Home, Plug, Settings, CalendarCheck, BadgeEuro, Lock, CreditCard, Search, Store, ChevronDown
} from 'lucide-react'
import { useState, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../lib/api'
import { usePlan } from '../hooks/usePlan'

const navItems: Array<{path:string;icon:any;label:string;roles:string[];feature?:string}> = [
  { path: '/', icon: LayoutDashboard, label: 'Dashboard', roles: ['OWNER','MANAGER','WAREHOUSE','EMPLOYEE','VIEWER'] },
  { path: '/today', icon: CalendarCheck, label: 'Dzisiaj', roles: ['OWNER','MANAGER','WAREHOUSE','EMPLOYEE'], feature:'freshstock_today' },
  { path: '/tasks', icon: ClipboardList, label: 'Zadania', roles: ['OWNER','MANAGER','WAREHOUSE','EMPLOYEE'] },
  { path: '/products', icon: Package, label: 'Produkty', roles: ['OWNER','MANAGER','WAREHOUSE','EMPLOYEE','VIEWER'] },
  { path: '/batches', icon: Archive, label: 'Partie / Daty', roles: ['OWNER','MANAGER','WAREHOUSE','EMPLOYEE'] },
  { path: '/deliveries', icon: Truck, label: 'Dostawy', roles: ['OWNER','MANAGER','WAREHOUSE'] },
  { path: '/orders', icon: ShoppingCart, label: 'Zamówienia', roles: ['OWNER','MANAGER'] },
  { path: '/sales', icon: BarChart3, label: 'Sprzedaż', roles: ['OWNER','MANAGER','VIEWER'] },
  { path: '/waste', icon: Trash2, label: 'Straty', roles: ['OWNER','MANAGER','WAREHOUSE','EMPLOYEE'] },
  { path: '/promotions', icon: Tag, label: 'Przeceny', roles: ['OWNER','MANAGER'] },
  { path: '/inventory', icon: ClipboardList, label: 'Inwentaryzacja', roles: ['OWNER','MANAGER','WAREHOUSE'] },
  { path: '/locations', icon: MapPin, label: 'Lokalizacje', roles: ['OWNER','MANAGER','WAREHOUSE'] },
  { path: '/alerts', icon: AlertTriangle, label: 'Alerty', roles: ['OWNER','MANAGER','WAREHOUSE','EMPLOYEE'] },
  { path: '/reports', icon: BarChart3, label: 'Raporty', roles: ['OWNER','MANAGER','VIEWER'] },
  { path: '/savings', icon: BadgeEuro, label: 'Oszczędności', roles: ['OWNER','MANAGER','VIEWER'], feature:'savings_dashboard' },
  { path: '/scanner', icon: ScanLine, label: 'Skaner', roles: ['OWNER','MANAGER','WAREHOUSE','EMPLOYEE'] },
  { path: '/ai', icon: Brain, label: 'AI Insights', roles: ['OWNER','MANAGER'], feature:'ai_restock' },
  { path: '/users', icon: Users, label: 'Użytkownicy', roles: ['OWNER'] },
  { path: '/integrations', icon: Plug, label: 'Integracje', roles: ['OWNER','MANAGER'] },
  { path: '/settings/store', icon: Settings, label: 'Konfiguracja sklepu', roles: ['OWNER'] },
  { path: '/subscription', icon: CreditCard, label: 'Subskrypcja', roles: ['OWNER'] },
]

// Bottom nav for mobile - only most important for EMPLOYEE
const bottomNavItems = [
  { path: '/today', icon: CalendarCheck, label: 'Dzisiaj' },
  { path: '/tasks', icon: ClipboardList, label: 'Zadania' },
  { path: '/scanner', icon: ScanLine, label: 'Skaner' },
  { path: '/waste', icon: Trash2, label: 'Straty' },
  { path: '/alerts', icon: AlertTriangle, label: 'Alerty' },
]
const bottomNavAll = [
  { path: '/', icon: Home, label: 'Home' },
  { path: '/products', icon: Package, label: 'Towar' },
  { path: '/scanner', icon: ScanLine, label: 'Skaner' },
  { path: '/batches', icon: Archive, label: 'Partie' },
  { path: '/alerts', icon: AlertTriangle, label: 'Alerty' },
]

function InstallPrompt() {
  const [deferred, setDeferred] = useState<any>(null)
  const [show, setShow] = useState(false)
  useEffect(() => {
    const h = (e: any) => { e.preventDefault(); setDeferred(e); setShow(true) }
    window.addEventListener('beforeinstallprompt', h)
    return () => window.removeEventListener('beforeinstallprompt', h)
  }, [])
  if (!show) return null
  return (
    <div className="bg-green-600 text-white px-4 py-3 flex items-center justify-between text-sm">
      <span>📲 Zainstaluj FreshStock na telefonie</span>
      <div className="flex gap-2">
        <button onClick={() => setShow(false)} className="px-3 py-1 text-white/80">Później</button>
        <button onClick={async () => { if(deferred) { deferred.prompt(); await deferred.userChoice; setShow(false)} }} className="bg-white text-green-700 px-4 py-1.5 rounded-full font-bold text-xs">ZAINSTALUJ</button>
      </div>
    </div>
  )
}

export default function Layout() {
  const { user, logout } = useAuth()
  const [mobileOpen, setMobileOpen] = useState(false)
  const [globalSearch, setGlobalSearch] = useState('')
  const navigate = useNavigate()
  const location = useLocation()
  const { canUseFeature, showUpgrade, capabilities } = usePlan()

  const { data: alertsCount } = useQuery({
    queryKey: ['alerts-count'],
    queryFn: async () => {
      const res = await api.get('/alerts', { params: { is_resolved: false } })
      return res.data.length
    },
    refetchInterval: 30000
  })

  const filteredNav = navItems.filter(item => user && item.roles.includes(user.role))
  const isEmployee = user?.role === 'EMPLOYEE'
  const bottomItems = isEmployee ? bottomNavItems : bottomNavAll

  return (
    <div className="min-h-screen bg-gray-50 flex">
      {/* Mobile overlay */}
      {mobileOpen && (
        <div className="fixed inset-0 bg-black/50 z-40 lg:hidden" onClick={() => setMobileOpen(false)} />
      )}

      {/* Sidebar - desktop only */}
      <aside className={`
        fixed lg:static inset-y-0 left-0 z-50 w-60 bg-white border-r border-slate-100 flex flex-col
        transform transition-transform duration-200 ease-in-out lg:transform-none
        ${mobileOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}
      `}>
        <div className="px-5 py-5 border-b border-slate-100 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="h-11 w-11 overflow-hidden rounded-xl"><img src="/brand/freshstock-logo.png" alt="" className="h-11 w-11 origin-top scale-[1.55] object-contain" /></div>
            <div><h1 className="text-lg font-extrabold tracking-tight text-slate-950"><span className="text-green-600">Fresh</span>Stock</h1><p className="text-[10px] font-medium text-slate-400">Smart Inventory</p></div>
          </div>
          <button onClick={() => setMobileOpen(false)} className="lg:hidden p-1">
            <X className="w-5 h-5" />
          </button>
        </div>

        <nav className="flex-1 overflow-y-auto px-3 py-5 space-y-1.5">
          {filteredNav.map(item => (
            <NavLink
              key={item.path}
              to={item.path}
              onClick={(event) => { if(item.feature && !canUseFeature(item.feature)){event.preventDefault();showUpgrade(item.feature)} setMobileOpen(false) }}
              className={({ isActive }) => `
                relative flex min-h-11 items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all
                ${isActive ? 'bg-emerald-50 text-emerald-800 font-bold before:absolute before:-left-3 before:h-7 before:w-1 before:rounded-r-full before:bg-green-600' : 'text-slate-600 hover:bg-slate-50 hover:text-slate-950'}
              `}
            >
              <item.icon className="w-5 h-5" />
              {item.label}
              {item.feature && !canUseFeature(item.feature) && <Lock className="ml-auto h-4 w-4 text-gray-400" />}
              {item.path === '/alerts' && alertsCount ? (
                <span className="ml-auto bg-red-500 text-white text-xs px-2 py-0.5 rounded-full">{alertsCount}</span>
              ) : null}
            </NavLink>
          ))}
        </nav>

        <div className="px-3 pb-3"><div className="rounded-2xl bg-gradient-to-br from-emerald-50 to-sky-50 p-4 ring-1 ring-emerald-100"><div className="mb-2 text-xl">🌿</div><p className="text-xs font-extrabold text-emerald-950">Mniej strat.</p><p className="text-xs font-extrabold text-emerald-800">Większy zysk.</p><p className="mt-1 text-[10px] text-emerald-700">Świeższy handel.</p></div></div>
        <div className="p-4 border-t border-slate-100">
          <div className="flex items-center gap-3 mb-3">
            <div className="w-8 h-8 bg-green-100 text-green-700 rounded-full flex items-center justify-center text-sm font-bold">
              {user?.full_name?.charAt(0) || 'U'}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-gray-900 truncate">{user?.full_name}</p>
              <p className="text-xs text-gray-500 truncate">{user?.role} {isEmployee ? '• 📱 Mobile' : ''}</p>
              {capabilities?.plan && <p className="text-[10px] font-bold text-green-700">PLAN {capabilities.plan}</p>}
            </div>
          </div>
          <button
            onClick={logout}
            className="w-full flex items-center gap-2 px-3 py-2 text-sm text-gray-600 hover:bg-gray-50 rounded-xl"
          >
            <LogOut className="w-4 h-4" /> Wyloguj
          </button>
        </div>
      </aside>

      {/* Main */}
      <div className="flex-1 flex flex-col min-w-0 pb-16 lg:pb-0">
        <InstallPrompt />
        <header className="sticky top-0 z-30 bg-white/90 backdrop-blur-xl border-b border-slate-100 px-4 lg:px-6 py-3 flex items-center gap-4">
          <div className="flex items-center gap-3">
            <button onClick={() => setMobileOpen(true)} className="lg:hidden p-2 -ml-2">
              <Menu className="w-6 h-6" />
            </button>
            <div className="lg:hidden flex items-center gap-2">
              <div className="h-8 w-8 overflow-hidden rounded-lg"><img src="/brand/freshstock-logo.png" alt="" className="h-8 w-8 origin-top scale-[1.55] object-contain" /></div><span className="font-extrabold"><span className="text-green-600">Fresh</span>Stock</span>
              {isEmployee && <span className="text-[10px] bg-green-100 text-green-700 px-2 py-0.5 rounded-full font-bold">PRACOWNIK</span>}
            </div>
          </div>
          <form onSubmit={(e)=>{e.preventDefault();if(globalSearch.trim())navigate(`/products?q=${encodeURIComponent(globalSearch.trim())}`)}} className="relative hidden max-w-2xl flex-1 md:block">
            <Search className="absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <input value={globalSearch} onChange={e=>setGlobalSearch(e.target.value)} placeholder="Szukaj produktów, SKU, EAN, partii, dostaw, zamówień…" className="w-full rounded-2xl bg-slate-50 py-2.5 pl-11 pr-14 text-sm outline-none ring-1 ring-slate-200/60 transition focus:bg-white focus:ring-2 focus:ring-green-200" />
            <span className="absolute right-3 top-1/2 -translate-y-1/2 rounded-md bg-white px-2 py-1 text-[10px] font-bold text-slate-400 ring-1 ring-slate-200">⌘ K</span>
          </form>
          <div className="ml-auto flex items-center gap-2">
            <button className="hidden items-center gap-2 rounded-xl bg-white px-3 py-2 text-left ring-1 ring-slate-200 lg:flex"><span className="grid h-8 w-8 place-items-center rounded-lg bg-green-100 text-green-700"><Store className="h-4 w-4"/></span><span><b className="block text-xs">Sklep główny</b><small className="block max-w-28 truncate text-[10px] text-slate-400">FreshStock</small></span><ChevronDown className="h-3 w-3 text-slate-400"/></button>
            <button onClick={() => navigate('/alerts')} className="relative p-2 hover:bg-gray-100 rounded-xl">
              <Bell className="w-5 h-5 text-gray-600" />
              {alertsCount ? <span className="absolute top-1 right-1 w-2.5 h-2.5 bg-red-500 rounded-full border-2 border-white"></span> : null}
            </button>
            <button onClick={()=>navigate('/subscription')} className="hidden items-center gap-2 rounded-xl px-2 py-1.5 hover:bg-slate-50 sm:flex"><span className="grid h-8 w-8 place-items-center rounded-full bg-gradient-to-br from-green-500 to-emerald-700 text-xs font-bold text-white">{user?.full_name?.split(' ').map(x=>x[0]).join('').slice(0,2)||'U'}</span><span className="hidden text-left xl:block"><b className="block max-w-28 truncate text-xs">{user?.full_name}</b><small className="block text-[10px] text-slate-400">{user?.role}</small></span><ChevronDown className="h-3 w-3 text-slate-400"/></button>
          </div>
        </header>

        <main className="flex-1 p-4 lg:p-6 xl:p-7 overflow-auto bg-[#f7f9fc]">
          <Outlet />
        </main>

        {/* Bottom Nav - MOBILE ONLY */}
        <nav className="lg:hidden fixed bottom-0 left-0 right-0 bg-white border-t border-gray-200 flex justify-around items-center py-1.5 pb-[calc(0.375rem+env(safe-area-inset-bottom))] z-30">
          {bottomItems.map(item => {
            const active = location.pathname === item.path
            return (
              <NavLink
                key={item.path}
                to={item.path}
                className={`flex flex-col items-center justify-center px-3 py-1.5 rounded-xl min-w-[56px] ${active ? 'text-green-600' : 'text-gray-400'}`}
              >
                <div className={`p-1.5 rounded-xl ${active ? 'bg-green-50' : ''}`}>
                  <item.icon className={`w-6 h-6 ${active ? 'text-green-600' : 'text-gray-500'}`} />
                </div>
                <span className={`text-[10px] font-medium mt-0.5 ${active ? 'text-green-700' : 'text-gray-500'}`}>{item.label}</span>
              </NavLink>
            )
          })}
        </nav>
      </div>
    </div>
  )
}
