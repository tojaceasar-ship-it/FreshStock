import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { lazy, Suspense } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AuthProvider, useAuth } from './hooks/useAuth'
import Layout from './components/Layout'
import Login from './pages/Login'
import Products from './pages/Products'
import ProductDetail from './pages/ProductDetail'
import ProductForm from './pages/ProductForm'
import Batches from './pages/Batches'
import Deliveries from './pages/Deliveries'
import Orders from './pages/Orders'
import Sales from './pages/Sales'
import Waste from './pages/Waste'
import Alerts from './pages/Alerts'
import Reports from './pages/Reports'
import Locations from './pages/Locations'
import Inventory from './pages/Inventory'
import AI from './pages/AI'
import Users from './pages/Users'
import { useQuery } from '@tanstack/react-query'
import { api } from './lib/api'
import PwaUpdater from './components/PwaUpdater'
import { LanguageSwitcher } from './lib/i18n'
import { FeatureGate, PlanProvider } from './hooks/usePlan'
import Pricing from './pages/Pricing'
import Subscription from './pages/Subscription'

const Dashboard = lazy(() => import('./pages/Dashboard'))
const Scanner = lazy(() => import('./pages/Scanner'))
const Integrations = lazy(() => import('./pages/Integrations'))
const StoreSetup = lazy(() => import('./pages/StoreSetup'))
const Promotions = lazy(() => import('./pages/Promotions'))
const Tasks = lazy(() => import('./pages/Tasks'))
const Today = lazy(() => import('./pages/Today'))
const Savings = lazy(() => import('./pages/Savings'))

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false
    }
  }
})

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth()
  if (loading) return <div className="min-h-screen flex items-center justify-center">Ładowanie...</div>
  if (!user) return <Navigate to="/login" replace />
  return <>{children}</>
}

function SetupGate({ children }: { children: React.ReactNode }) {
  const { user } = useAuth()
  const { data, isLoading } = useQuery({ queryKey: ['onboarding-status'], queryFn: async () => (await api.get('/onboarding')).data, enabled: user?.role === 'OWNER' })
  if (user?.role === 'OWNER' && isLoading) return <div className="min-h-screen flex items-center justify-center">Sprawdzanie konfiguracji…</div>
  if (user?.role === 'OWNER' && data?.status !== 'COMPLETED') return <Navigate to="/setup" replace />
  return <>{children}</>
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <PwaUpdater />
        <LanguageSwitcher />
        <BrowserRouter>
          <PlanProvider>
          <Suspense fallback={<div className="min-h-screen flex items-center justify-center">Ładowanie…</div>}><Routes>
            <Route path="/login" element={<Login />} />
            <Route path="/pricing" element={<Pricing />} />
            <Route path="/setup" element={<ProtectedRoute><StoreSetup /></ProtectedRoute>} />
            <Route path="/" element={<ProtectedRoute><SetupGate><Layout /></SetupGate></ProtectedRoute>}>
              <Route index element={<Dashboard />} />
              <Route path="today" element={<FeatureGate feature="freshstock_today"><Today /></FeatureGate>} />
              <Route path="products" element={<Products />} />
              <Route path="products/new" element={<ProductForm />} />
              <Route path="products/:id" element={<ProductDetail />} />
              <Route path="batches" element={<Batches />} />
              <Route path="deliveries" element={<Deliveries />} />
              <Route path="orders" element={<Orders />} />
              <Route path="sales" element={<Sales />} />
              <Route path="waste" element={<Waste />} />
              <Route path="promotions" element={<Promotions />} />
              <Route path="alerts" element={<Alerts />} />
              <Route path="scanner" element={<Scanner />} />
              <Route path="reports" element={<Reports />} />
              <Route path="savings" element={<FeatureGate feature="savings_dashboard"><Savings /></FeatureGate>} />
              <Route path="locations" element={<Locations />} />
              <Route path="inventory" element={<Inventory />} />
              <Route path="ai" element={<FeatureGate feature="ai_restock"><AI /></FeatureGate>} />
              <Route path="users" element={<Users />} />
              <Route path="integrations" element={<Integrations />} />
              <Route path="tasks" element={<Tasks />} />
              <Route path="settings/store" element={<StoreSetup settingsMode />} />
              <Route path="subscription" element={<Subscription />} />
            </Route>
          </Routes></Suspense>
          </PlanProvider>
        </BrowserRouter>
      </AuthProvider>
    </QueryClientProvider>
  )
}
