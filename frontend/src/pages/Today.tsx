import { useEffect } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { AlertTriangle, CalendarCheck, Clock, Play, RefreshCw, Sparkles } from 'lucide-react'
import { api } from '../lib/api'
import { useAuth } from '../hooks/useAuth'
import { getLocale } from '../lib/i18n'
import { AppCard } from '../components/ui/AppCard'

const closed = ['COMPLETED', 'CANCELLED', 'SKIPPED']

export default function Today() {
  const { user } = useAuth()
  const qc = useQueryClient()
  const canGenerate = user?.role === 'OWNER' || user?.role === 'MANAGER'
  const { data, isLoading } = useQuery({
    queryKey: ['freshstock-today'],
    queryFn: async () => (await api.get('/today')).data,
    refetchInterval: 30000,
  })
  const generate = useMutation({
    mutationFn: async () => (await api.post('/today/generate')).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['freshstock-today'] })
      qc.invalidateQueries({ queryKey: ['tasks'] })
      qc.invalidateQueries({ queryKey: ['task-summary'] })
    },
  })
  const start = useMutation({
    mutationFn: async (id: number) => (await api.post(`/tasks/${id}/start`)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['freshstock-today'] }),
  })

  useEffect(() => {
    if (canGenerate) generate.mutate()
    // Generate exactly once when entering the daily view; the API is idempotent.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [canGenerate])

  if (isLoading) return <div className="h-64 animate-pulse rounded-2xl bg-gray-200" />
  const tasks = (data?.tasks || []).filter((task: any) => !closed.includes(task.stored_status))
  const summary = data?.summary || {}

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div><div className="flex items-center gap-2 text-sm font-semibold text-green-700"><Sparkles className="h-4 w-4" /> FreshStock Today</div><h1 className="text-2xl font-bold">Co jest najważniejsze dzisiaj?</h1><p className="text-sm text-gray-500">Jedna lista z terminów ważności, braków, alertów i zadań zespołu.</p></div>
        {canGenerate && <button onClick={() => generate.mutate()} disabled={generate.isPending} className="flex items-center gap-2 rounded-xl border bg-white px-4 py-2 text-sm font-semibold disabled:opacity-50"><RefreshCw className={`h-4 w-4 ${generate.isPending ? 'animate-spin' : ''}`} /> Odśwież plan</button>}
      </div>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Metric label="Do wykonania" value={summary.total || 0} tone="green" />
        <Metric label="Krytyczne" value={summary.critical || 0} tone="red" />
        <Metric label="Po terminie" value={summary.overdue || 0} tone="orange" />
        <Metric label="W toku" value={summary.in_progress || 0} tone="blue" />
      </div>

      <AppCard variant="list" padding="none">
        <div className="border-b p-4"><h2 className="font-bold">Plan dnia</h2><p className="text-xs text-gray-500">Najpierw zadania o największym ryzyku finansowym i operacyjnym.</p></div>
        <div className="divide-y">
          {tasks.map((task: any, index: number) => (
            <div key={task.id} className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center">
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-gray-100 text-sm font-bold">{index + 1}</div>
              <div className="min-w-0 flex-1"><div className="flex flex-wrap items-center gap-2"><span className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${task.priority === 'CRITICAL' ? 'bg-red-100 text-red-700' : task.priority === 'HIGH' ? 'bg-orange-100 text-orange-700' : 'bg-blue-100 text-blue-700'}`}>{task.priority}</span><span className="text-xs text-gray-500">{task.task_type}</span></div><div className="mt-1 font-semibold">{task.title}</div><div className="mt-1 flex flex-wrap gap-3 text-xs text-gray-500">{task.assigned_user_name || task.assigned_role || 'do podjęcia'}{task.due_at && <span className="flex items-center gap-1"><Clock className="h-3 w-3" />{new Date(task.due_at).toLocaleTimeString(getLocale(), { hour: '2-digit', minute: '2-digit' })}</span>}</div></div>
              <div className="flex gap-2">{task.stored_status === 'TODO' && <button onClick={() => start.mutate(task.id)} className="flex items-center gap-1 rounded-xl bg-green-600 px-3 py-2 text-xs font-bold text-white"><Play className="h-3 w-3" /> Rozpocznij</button>}<Link to="/tasks" className="rounded-xl border px-3 py-2 text-xs font-bold">Szczegóły</Link></div>
            </div>
          ))}
          {!tasks.length && <div className="p-12 text-center"><CalendarCheck className="mx-auto mb-3 h-10 w-10 text-green-600" /><div className="font-semibold">Plan dnia wykonany</div><p className="text-sm text-gray-500">Brak pilnych zadań. Świetna robota!</p></div>}
        </div>
      </AppCard>
      {generate.isError && <div className="flex items-center gap-2 rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700"><AlertTriangle className="h-4 w-4" /> Nie udało się wygenerować planu dnia.</div>}
    </div>
  )
}

function Metric({ label, value, tone }: { label: string; value: number; tone: string }) {
  const colors: Record<string, string> = { green: 'border-green-200 bg-green-50 text-green-700', red: 'border-red-200 bg-red-50 text-red-700', orange: 'border-orange-200 bg-orange-50 text-orange-700', blue: 'border-blue-200 bg-blue-50 text-blue-700' }
  return <AppCard variant="kpi" padding="compact" className={colors[tone]}><div className="text-sm font-medium">{label}</div><div className="mt-2 text-[32px] font-extrabold leading-none">{value}</div></AppCard>
}
