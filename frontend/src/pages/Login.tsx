import { useEffect, useState } from 'react'
import { useAuth } from '../hooks/useAuth'
import { useNavigate } from 'react-router-dom'
import { api } from '../lib/api'
import { useLanguage } from '../lib/i18n'

export default function Login() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [bootstrapRequired, setBootstrapRequired] = useState(false)
  const [checkingBootstrap, setCheckingBootstrap] = useState(true)
  const [owner, setOwner] = useState({ full_name: '', email: '', username: '', password: '', password2: '' })
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [store, setStore] = useState({ store_name: '', full_name: '', email: '', username: '', password: '', password2: '' })
  const { login } = useAuth()
  const { language } = useLanguage()
  const navigate = useNavigate()

  useEffect(() => {
    api.get('/auth/bootstrap-status')
      .then(res => setBootstrapRequired(Boolean(res.data.required)))
      .catch(() => setBootstrapRequired(false))
      .finally(() => setCheckingBootstrap(false))
  }, [])

  const createOwner = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    if (owner.password !== owner.password2) {
      setError('Hasła nie są identyczne')
      return
    }
    if (owner.password.length < 10) {
      setError('Hasło musi mieć co najmniej 10 znaków')
      return
    }
    setLoading(true)
    try {
      const res = await api.post('/auth/bootstrap', {
        full_name: owner.full_name,
        email: owner.email,
        username: owner.username,
        password: owner.password,
      })
      localStorage.setItem('access_token', res.data.access_token)
      localStorage.setItem('refresh_token', res.data.refresh_token)
      window.location.href = '/'
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Nie udało się utworzyć właściciela')
    } finally {
      setLoading(false)
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await login(username, password)
      navigate('/')
    } catch (err: any) {
      console.error('Login error:', err)
      const detail = err.response?.data?.detail || err.message || 'Błąd logowania - sprawdź czy backend działa'
      const status = err.response?.status ? ` (HTTP ${err.response.status})` : ''
      const apiUrl = api.defaults.baseURL || '/api'
      setError(`${detail}${status} - API: ${apiUrl}`)
    } finally {
      setLoading(false)
    }
  }

  const registerStore = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    if (store.password !== store.password2) {
      setError('Hasła nie są identyczne')
      return
    }
    if (store.password.length < 12 || !/[a-z]/.test(store.password) || !/[A-Z]/.test(store.password) || !/\d/.test(store.password)) {
      setError('Hasło musi mieć co najmniej 12 znaków oraz zawierać małą literę, wielką literę i cyfrę')
      return
    }
    setLoading(true)
    try {
      const res = await api.post('/auth/register-store', {
        store_name: store.store_name,
        full_name: store.full_name,
        email: store.email,
        username: store.username,
        password: store.password,
        language,
      })
      localStorage.setItem('access_token', res.data.access_token)
      localStorage.setItem('refresh_token', res.data.refresh_token)
      window.location.href = '/setup'
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Nie udało się utworzyć nowego sklepu')
    } finally {
      setLoading(false)
    }
  }

  const changeMode = (next: 'login' | 'register') => {
    setError('')
    setMode(next)
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-green-50 to-emerald-100 flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        <div className="bg-white rounded-2xl shadow-xl p-8 border border-gray-100">
          <div className="text-center mb-8">
            <img src="/brand/freshstock-logo.png" alt="FreshStock" className="mx-auto mb-2 h-28 w-64 object-contain mix-blend-multiply" />
            <p className="text-gray-500 mt-1">System zarządzania sklepem spożywczym</p>
          </div>

          {checkingBootstrap ? (
            <p className="py-8 text-center text-sm text-gray-500">Sprawdzanie konfiguracji konta…</p>
          ) : bootstrapRequired ? (
            <form onSubmit={createOwner} className="space-y-4">
              <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-4">
                <h2 className="font-bold text-emerald-900">Utwórz pierwszego właściciela</h2>
                <p className="mt-1 text-xs text-emerald-700">To jednorazowa konfiguracja. Utworzone konto otrzyma rolę OWNER.</p>
              </div>
              <input required minLength={2} value={owner.full_name} onChange={e=>setOwner({...owner,full_name:e.target.value})} className="w-full px-4 py-3 rounded-xl border border-gray-200" placeholder="Imię i nazwisko" />
              <input required type="email" value={owner.email} onChange={e=>setOwner({...owner,email:e.target.value})} className="w-full px-4 py-3 rounded-xl border border-gray-200" placeholder="E-mail" />
              <input required minLength={3} pattern="[A-Za-z0-9_.-]+" value={owner.username} onChange={e=>setOwner({...owner,username:e.target.value})} className="w-full px-4 py-3 rounded-xl border border-gray-200" placeholder="Login" />
              <input required minLength={10} type="password" value={owner.password} onChange={e=>setOwner({...owner,password:e.target.value})} className="w-full px-4 py-3 rounded-xl border border-gray-200" placeholder="Hasło (minimum 10 znaków)" />
              <input required minLength={10} type="password" value={owner.password2} onChange={e=>setOwner({...owner,password2:e.target.value})} className="w-full px-4 py-3 rounded-xl border border-gray-200" placeholder="Powtórz hasło" />
              {error && <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-xl text-sm">{error}</div>}
              <button disabled={loading} className="w-full bg-green-600 hover:bg-green-700 text-white font-medium py-3 rounded-xl disabled:opacity-50">{loading ? 'Tworzenie…' : 'Utwórz konto OWNER'}</button>
            </form>
          ) : mode === 'register' ? (
            <form onSubmit={registerStore} className="space-y-4">
              <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-4">
                <h2 className="font-bold text-emerald-900">Załóż nowy, niezależny sklep</h2>
                <p className="mt-1 text-xs text-emerald-700">Dane, użytkownicy i magazyn tego sklepu będą całkowicie oddzielone od innych sklepów.</p>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Nazwa sklepu</label>
                <input required minLength={2} maxLength={255} value={store.store_name} onChange={e => setStore({...store, store_name: e.target.value})} className="w-full px-4 py-3 rounded-xl border border-gray-200" placeholder="Nazwa nowego sklepu" />
              </div>
              <p className="text-xs font-bold uppercase tracking-wide text-gray-500">Dane właściciela</p>
              <input required minLength={2} maxLength={255} value={store.full_name} onChange={e => setStore({...store, full_name: e.target.value})} className="w-full px-4 py-3 rounded-xl border border-gray-200" placeholder="Imię i nazwisko" />
              <input required type="email" value={store.email} onChange={e => setStore({...store, email: e.target.value})} className="w-full px-4 py-3 rounded-xl border border-gray-200" placeholder="E-mail" />
              <input required minLength={3} maxLength={100} pattern="[A-Za-z0-9_.-]+" value={store.username} onChange={e => setStore({...store, username: e.target.value})} className="w-full px-4 py-3 rounded-xl border border-gray-200" placeholder="Login" />
              <input required minLength={12} maxLength={128} type="password" value={store.password} onChange={e => setStore({...store, password: e.target.value})} className="w-full px-4 py-3 rounded-xl border border-gray-200" placeholder="Hasło (minimum 12 znaków)" />
              <input required minLength={12} maxLength={128} type="password" value={store.password2} onChange={e => setStore({...store, password2: e.target.value})} className="w-full px-4 py-3 rounded-xl border border-gray-200" placeholder="Powtórz hasło" />
              <p className="text-xs text-gray-500">Hasło musi zawierać małą literę, wielką literę i cyfrę.</p>
              {error && <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-xl text-sm">{error}</div>}
              <button disabled={loading} className="w-full bg-green-600 hover:bg-green-700 text-white font-medium py-3 rounded-xl disabled:opacity-50">{loading ? 'Tworzenie sklepu…' : 'Utwórz niezależny sklep'}</button>
              <button type="button" onClick={() => changeMode('login')} className="w-full text-sm font-medium text-green-700 hover:text-green-800">Masz już konto? Zaloguj się</button>
            </form>
          ) : <>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label htmlFor="login-username" className="block text-sm font-medium text-gray-700 mb-1">Login lub Email</label>
              <input
                id="login-username"
                type="text"
                value={username}
                onChange={e => setUsername(e.target.value)}
                className="w-full px-4 py-3 rounded-xl border border-gray-200 focus:border-green-500 focus:ring-2 focus:ring-green-100 outline-none transition"
                placeholder="Wpisz login lub adres e-mail"
                required
              />
            </div>
            <div>
              <label htmlFor="login-password" className="block text-sm font-medium text-gray-700 mb-1">Hasło</label>
              <input
                id="login-password"
                type="password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                className="w-full px-4 py-3 rounded-xl border border-gray-200 focus:border-green-500 focus:ring-2 focus:ring-green-100 outline-none transition"
                placeholder="••••••••"
                required
              />
            </div>

            {error && (
              <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-xl text-sm">
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full bg-green-600 hover:bg-green-700 text-white font-medium py-3 rounded-xl transition disabled:opacity-50"
            >
              {loading ? 'Logowanie...' : 'Zaloguj się'}
            </button>
          </form>
          <div className="mt-6 border-t border-gray-100 pt-5 text-center">
            <p className="mb-3 text-sm text-gray-500">Nie masz jeszcze sklepu w FreshStock?</p>
            <button type="button" onClick={() => changeMode('register')} className="w-full rounded-xl border border-green-600 px-4 py-3 font-medium text-green-700 transition hover:bg-green-50">Załóż nowy sklep</button>
          </div>
          </>}

        </div>
        <p className="text-center text-xs text-gray-500 mt-4">FreshStock v1.0 • PWA Ready • FEFO • EAN Scanner</p>
      </div>
    </div>
  )
}
