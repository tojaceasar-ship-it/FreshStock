import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, Camera, CheckCircle2, ChevronRight, Circle, Clock, MessageSquare, Plus, Repeat2, UserRound, X } from 'lucide-react'
import { useSearchParams } from 'react-router-dom'
import { api } from '../lib/api'
import { getLocale } from '../lib/i18n'
import { useAuth } from '../hooks/useAuth'

const taskTypes = ['GENERAL','EXPIRY_CHECK','RESTOCK','MARKDOWN','WASTE','INVENTORY_COUNT','TRANSFER','DELIVERY_CHECK','CLEANING','PRICE_CHECK','RECALL','CUSTOM']
const priorities = ['CRITICAL','HIGH','MEDIUM','LOW']
const statusColors: Record<string,string> = {
  TODO: 'bg-gray-100 text-gray-700', IN_PROGRESS: 'bg-blue-100 text-blue-700', COMPLETED: 'bg-green-100 text-green-700',
  BLOCKED: 'bg-red-100 text-red-700', OVERDUE: 'bg-red-600 text-white', CANCELLED: 'bg-gray-200 text-gray-500', SKIPPED: 'bg-gray-100 text-gray-500',
}
const priorityColors: Record<string,string> = {
  CRITICAL: 'bg-red-600 text-white', HIGH: 'bg-orange-100 text-orange-700', MEDIUM: 'bg-blue-100 text-blue-700', LOW: 'bg-gray-100 text-gray-600',
}

function dateLabel(value?: string) {
  return value ? new Date(value).toLocaleString(getLocale(), { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }) : 'Bez terminu'
}

export default function Tasks() {
  const { user } = useAuth()
  const manager = user?.role === 'OWNER' || user?.role === 'MANAGER'
  const client = useQueryClient()
  const [searchParams] = useSearchParams()
  const [showCreate, setShowCreate] = useState(searchParams.get('new') === '1')
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [statusFilter, setStatusFilter] = useState('')
  const [error, setError] = useState('')
  const [comment, setComment] = useState('')
  const [form, setForm] = useState({
    title: searchParams.get('title') || '', description: '', task_type: searchParams.get('task_type') || 'GENERAL',
    priority: searchParams.get('priority') || 'MEDIUM', assignment: 'any', due_at: '', product_id: searchParams.get('product_id') || '',
    batch_id: searchParams.get('batch_id') || '', location_id: searchParams.get('location_id') || '', quantity: searchParams.get('quantity') || '',
    requires_photo: false, requires_scan: false, requires_comment: false, checklist: '', recurrence_rule: '', recurrence_days: [] as number[],
    source: searchParams.get('source') || 'OWNER',
  })

  const { data: tasks = [], isLoading } = useQuery({
    queryKey: ['tasks', statusFilter],
    queryFn: async () => (await api.get('/tasks', { params: statusFilter ? { status: statusFilter } : {} })).data,
    refetchInterval: 5000,
  })
  const { data: summary } = useQuery({ queryKey: ['task-summary'], queryFn: async () => (await api.get('/tasks/summary')).data, refetchInterval: 5000 })
  const { data: detail } = useQuery({ queryKey: ['task', selectedId], queryFn: async () => (await api.get(`/tasks/${selectedId}`)).data, enabled: Boolean(selectedId) })
  const { data: users = [] } = useQuery({ queryKey: ['task-users'], queryFn: async () => (await api.get('/users')).data, enabled: manager })
  const { data: products = [] } = useQuery({ queryKey: ['task-products'], queryFn: async () => (await api.get('/products')).data, enabled: manager && showCreate })
  const { data: batches = [] } = useQuery({ queryKey: ['task-batches'], queryFn: async () => (await api.get('/batches')).data, enabled: manager && showCreate })
  const { data: locations = [] } = useQuery({ queryKey: ['task-locations'], queryFn: async () => (await api.get('/locations')).data, enabled: manager && showCreate })

  const refresh = () => {
    client.invalidateQueries({ queryKey: ['tasks'] })
    client.invalidateQueries({ queryKey: ['task-summary'] })
    if (selectedId) client.invalidateQueries({ queryKey: ['task', selectedId] })
  }
  const action = useMutation({
    mutationFn: async ({ path, body }: { path: string; body?: unknown }) => (await api.post(path, body || {})).data,
    onSuccess: refresh,
    onError: (err: any) => setError(err.response?.data?.detail || 'Nie udało się wykonać operacji'),
  })
  const create = useMutation({
    mutationFn: async () => {
      const assigned_user_id = form.assignment.startsWith('user:') ? Number(form.assignment.split(':')[1]) : null
      const assigned_role = form.assignment.startsWith('role:') ? form.assignment.split(':')[1] : null
      return (await api.post('/tasks', {
        title: form.title, description: form.description || null, task_type: form.task_type, priority: form.priority,
        assigned_user_id, assigned_role, due_at: form.due_at ? new Date(form.due_at).toISOString() : null,
        product_id: form.product_id ? Number(form.product_id) : null, batch_id: form.batch_id ? Number(form.batch_id) : null,
        location_id: form.location_id ? Number(form.location_id) : null, quantity: form.quantity ? Number(form.quantity) : null,
        requires_photo: form.requires_photo, requires_scan: form.requires_scan, requires_comment: form.requires_comment,
        checklist: form.checklist.split('\n').map(x => x.trim()).filter(Boolean), recurrence_rule: form.recurrence_rule || null,
        recurrence_days: form.recurrence_days, source: form.source,
      })).data
    },
    onSuccess: task => { setShowCreate(false); setSelectedId(task.id); setError(''); refresh() },
    onError: (err: any) => setError(err.response?.data?.detail || 'Nie udało się przypisać zadania'),
  })
  const addComment = useMutation({
    mutationFn: async () => (await api.post(`/tasks/${selectedId}/comments`, { body: comment })).data,
    onSuccess: () => { setComment(''); refresh() },
    onError: (err: any) => setError(err.response?.data?.detail || 'Nie udało się dodać komentarza'),
  })
  const checklist = useMutation({ mutationFn: async (id: number) => (await api.patch(`/tasks/${selectedId}/checklist/${id}`)).data, onSuccess: refresh })
  const upload = useMutation({
    mutationFn: async (file: File) => { const data = new FormData(); data.append('file', file); return (await api.post(`/tasks/${selectedId}/attachments`, data, { headers: { 'Content-Type': 'multipart/form-data' } })).data },
    onSuccess: refresh,
    onError: (err: any) => setError(err.response?.data?.detail || 'Nie udało się dodać zdjęcia'),
  })

  const openAttachment = async (attachment: any) => {
    const response = await api.get(attachment.download_url)
    const url = response.data?.url
    if (url) window.open(url, '_blank', 'noopener,noreferrer')
  }
  const activeTasks = useMemo(() => tasks.filter((task:any) => !['COMPLETED','CANCELLED','SKIPPED'].includes(task.status)), [tasks])

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div><h1 className="text-2xl font-bold">{manager ? 'Zadania zespołu' : 'Moje zadania'}</h1><p className="text-sm text-gray-500">{manager ? 'Przypisuj pracę i obserwuj realizację bez rankingu pracowników.' : 'Co mam dzisiaj zrobić?'}</p></div>
        {manager && <button onClick={() => setShowCreate(true)} className="flex items-center gap-2 rounded-xl bg-green-600 px-4 py-2.5 font-medium text-white"><Plus className="h-4 w-4" /> Nowe zadanie</button>}
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        {[["Wszystkie",summary?.total||0],["Do zrobienia",summary?.counts?.TODO||0],["W toku",summary?.counts?.IN_PROGRESS||0],["Zakończone",summary?.counts?.COMPLETED||0],["Po terminie",summary?.counts?.OVERDUE||0]].map(([label,value]) => <div key={String(label)} className="rounded-2xl border bg-white p-4"><div className="text-2xl font-bold">{value}</div><div className="text-xs text-gray-500">{label}</div></div>)}
      </div>

      {manager && summary?.by_user?.length > 0 && <div className="rounded-2xl border bg-white p-4"><h2 className="mb-3 font-semibold">Realizacja zespołu</h2><div className="grid gap-3 md:grid-cols-3">{summary.by_user.map((row:any)=><div key={row.user_id} className="rounded-xl bg-gray-50 p-3"><div className="font-medium">{row.name}</div><div className="text-sm text-gray-500">{row.completed}/{row.total} zakończonych{row.overdue ? ` · ${row.overdue} po terminie` : ''}</div></div>)}</div></div>}

      <div className="flex gap-2 overflow-x-auto pb-1">{['','TODO','IN_PROGRESS','BLOCKED','OVERDUE','COMPLETED'].map(value=><button key={value} onClick={()=>setStatusFilter(value)} className={`whitespace-nowrap rounded-full px-3 py-1.5 text-xs font-medium ${statusFilter===value?'bg-gray-900 text-white':'border bg-white text-gray-600'}`}>{value||'AKTYWNE I WSZYSTKIE'}</button>)}</div>

      {error && <div className="flex items-start justify-between rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700"><span>{error}</span><button onClick={()=>setError('')}><X className="h-4 w-4" /></button></div>}
      {isLoading ? <div className="h-40 animate-pulse rounded-2xl bg-gray-200" /> : <div className="space-y-3">
        {(statusFilter ? tasks : activeTasks).map((task:any)=><button key={task.id} onClick={()=>setSelectedId(task.id)} className="w-full rounded-2xl border bg-white p-4 text-left transition hover:border-green-300 hover:shadow-sm">
          <div className="flex items-start gap-3">
            <span className={`shrink-0 rounded-lg px-2 py-1 text-[11px] font-bold ${priorityColors[task.priority]}`}>{task.priority}</span>
            <div className="min-w-0 flex-1"><div className="font-semibold text-gray-900">{task.title}</div><div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs text-gray-500">
              <span className="flex items-center gap-1"><Clock className="h-3 w-3" /> {dateLabel(task.due_at)}</span>
              <span className="flex items-center gap-1"><UserRound className="h-3 w-3" /> {task.assigned_user_name || task.assigned_role || 'Dowolny pracownik'}</span>
              {task.location_name && <span>{task.location_name}</span>}{task.product_name && <span>{task.product_name}</span>}
            </div>{task.checklist_total>0&&<div className="mt-2 text-xs text-gray-500">Checklist: {task.checklist_completed}/{task.checklist_total}</div>}</div>
            <div className="flex items-center gap-2"><span className={`rounded-full px-2 py-1 text-[10px] font-bold ${statusColors[task.status]}`}>{task.status}</span><ChevronRight className="h-4 w-4 text-gray-400" /></div>
          </div>
        </button>)}
        {!(statusFilter ? tasks : activeTasks).length && <div className="rounded-2xl border border-dashed bg-white p-10 text-center text-gray-500">Brak zadań w tym widoku.</div>}
      </div>}

      {showCreate && manager && <div className="fixed inset-0 z-[110] overflow-y-auto bg-black/50 p-4"><div className="mx-auto my-4 max-w-3xl rounded-2xl bg-white p-6 shadow-xl">
        <div className="mb-5 flex items-center justify-between"><div><h2 className="text-xl font-bold">Nowe zadanie</h2><p className="text-sm text-gray-500">Przypisz osobie, roli albo pozostaw do podjęcia.</p></div><button onClick={()=>setShowCreate(false)}><X /></button></div>
        <form onSubmit={e=>{e.preventDefault();create.mutate()}} className="grid gap-4 md:grid-cols-2">
          <label className="md:col-span-2 text-sm">Tytuł *<input required minLength={3} value={form.title} onChange={e=>setForm({...form,title:e.target.value})} className="mt-1 w-full rounded-xl border px-3 py-2.5" /></label>
          <label className="md:col-span-2 text-sm">Opis<textarea value={form.description} onChange={e=>setForm({...form,description:e.target.value})} className="mt-1 min-h-24 w-full rounded-xl border px-3 py-2.5" /></label>
          <label className="text-sm">Przypisz do<select value={form.assignment} onChange={e=>setForm({...form,assignment:e.target.value})} className="mt-1 w-full rounded-xl border px-3 py-2.5"><option value="any">Dowolny dostępny pracownik</option>{users.filter((u:any)=>u.is_active).map((u:any)=><option key={u.id} value={`user:${u.id}`}>{u.full_name} · {u.role}</option>)}<option value="role:EMPLOYEE">Rola EMPLOYEE</option><option value="role:WAREHOUSE">Rola WAREHOUSE</option><option value="role:MANAGER">Rola MANAGER</option></select></label>
          <label className="text-sm">Termin<input type="datetime-local" value={form.due_at} onChange={e=>setForm({...form,due_at:e.target.value})} className="mt-1 w-full rounded-xl border px-3 py-2.5" /></label>
          <label className="text-sm">Typ<select value={form.task_type} onChange={e=>setForm({...form,task_type:e.target.value})} className="mt-1 w-full rounded-xl border px-3 py-2.5">{taskTypes.map(x=><option key={x} value={x}>{x}</option>)}</select></label>
          <label className="text-sm">Priorytet<select value={form.priority} onChange={e=>setForm({...form,priority:e.target.value})} className="mt-1 w-full rounded-xl border px-3 py-2.5">{priorities.map(x=><option key={x} value={x}>{x}</option>)}</select></label>
          <label className="text-sm">Produkt<select value={form.product_id} onChange={e=>setForm({...form,product_id:e.target.value})} className="mt-1 w-full rounded-xl border px-3 py-2.5"><option value="">— opcjonalnie —</option>{products.map((x:any)=><option key={x.id} value={x.id}>{x.name}</option>)}</select></label>
          <label className="text-sm">Partia<select value={form.batch_id} onChange={e=>setForm({...form,batch_id:e.target.value})} className="mt-1 w-full rounded-xl border px-3 py-2.5"><option value="">— opcjonalnie —</option>{batches.map((x:any)=><option key={x.id} value={x.id}>{x.batch_number} · {x.product_name||''}</option>)}</select></label>
          <label className="text-sm">Lokalizacja<select value={form.location_id} onChange={e=>setForm({...form,location_id:e.target.value})} className="mt-1 w-full rounded-xl border px-3 py-2.5"><option value="">— opcjonalnie —</option>{locations.map((x:any)=><option key={x.id} value={x.id}>{x.name}</option>)}</select></label>
          <label className="text-sm">Ilość<input type="number" min="0" step="0.001" value={form.quantity} onChange={e=>setForm({...form,quantity:e.target.value})} className="mt-1 w-full rounded-xl border px-3 py-2.5" /></label>
          <label className="md:col-span-2 text-sm">Checklist — jeden krok w wierszu<textarea value={form.checklist} onChange={e=>setForm({...form,checklist:e.target.value})} className="mt-1 min-h-24 w-full rounded-xl border px-3 py-2.5" placeholder={'Sprawdź jogurty\nSprawdź mleko\nZgłoś straty'} /></label>
          <label className="text-sm">Powtarzanie<select value={form.recurrence_rule} onChange={e=>setForm({...form,recurrence_rule:e.target.value})} className="mt-1 w-full rounded-xl border px-3 py-2.5"><option value="">Nie powtarzaj</option><option value="DAILY">Codziennie</option><option value="WEEKDAYS">Wybrane dni tygodnia</option><option value="WEEKLY">Co tydzień</option></select></label>
          {form.recurrence_rule==='WEEKDAYS'&&<div className="flex flex-wrap items-end gap-1">{['Pn','Wt','Śr','Cz','Pt','So','Nd'].map((x,i)=><button type="button" key={x} onClick={()=>setForm({...form,recurrence_days:form.recurrence_days.includes(i)?form.recurrence_days.filter(d=>d!==i):[...form.recurrence_days,i]})} className={`h-9 w-9 rounded-lg text-xs ${form.recurrence_days.includes(i)?'bg-green-600 text-white':'border'}`}>{x}</button>)}</div>}
          <div className="md:col-span-2 flex flex-wrap gap-4 text-sm">{[['requires_photo','Wymagaj zdjęcia'],['requires_scan','Wymagaj skanu'],['requires_comment','Wymagaj komentarza']].map(([key,label])=><label key={key} className="flex items-center gap-2"><input type="checkbox" checked={(form as any)[key]} onChange={e=>setForm({...form,[key]:e.target.checked})} /> {label}</label>)}</div>
          <div className="md:col-span-2 flex justify-end gap-2"><button type="button" onClick={()=>setShowCreate(false)} className="rounded-xl border px-4 py-2.5">Anuluj</button><button disabled={create.isPending} className="rounded-xl bg-green-600 px-5 py-2.5 font-medium text-white">{create.isPending?'Przypisywanie…':'Przypisz zadanie'}</button></div>
        </form>
      </div></div>}

      {selectedId && detail && <div className="fixed inset-0 z-[110] overflow-y-auto bg-black/50 p-4"><div className="mx-auto my-4 max-w-2xl rounded-2xl bg-white p-6 shadow-xl">
        <div className="flex items-start justify-between gap-3"><div><div className="flex gap-2"><span className={`rounded-lg px-2 py-1 text-[11px] font-bold ${priorityColors[detail.priority]}`}>{detail.priority}</span><span className={`rounded-full px-2 py-1 text-[10px] font-bold ${statusColors[detail.status]}`}>{detail.status}</span></div><h2 className="mt-3 text-xl font-bold">{detail.title}</h2><p className="mt-1 text-sm text-gray-500">{detail.task_type} · {dateLabel(detail.due_at)}</p></div><button onClick={()=>setSelectedId(null)}><X /></button></div>
        {detail.description&&<p className="mt-4 whitespace-pre-wrap rounded-xl bg-gray-50 p-4 text-sm">{detail.description}</p>}
        <div className="mt-4 grid gap-2 text-sm sm:grid-cols-2"><div><b>Wykonawca:</b> {detail.assigned_user_name||detail.assigned_role||'do podjęcia'}</div>{detail.location_name&&<div><b>Lokalizacja:</b> {detail.location_name}</div>}{detail.product_name&&<div><b>Produkt:</b> {detail.product_name}</div>}{detail.quantity!=null&&<div><b>Ilość:</b> {detail.quantity}</div>}</div>
        {detail.checklist?.length>0&&<div className="mt-5"><h3 className="mb-2 font-semibold">Checklist ({detail.checklist_completed}/{detail.checklist_total})</h3><div className="space-y-2">{detail.checklist.map((item:any)=><button key={item.id} onClick={()=>checklist.mutate(item.id)} className="flex w-full items-center gap-2 rounded-xl border p-3 text-left text-sm">{item.is_completed?<CheckCircle2 className="h-5 w-5 text-green-600"/>:<Circle className="h-5 w-5 text-gray-400"/>}<span className={item.is_completed?'text-gray-400 line-through':''}>{item.text}</span></button>)}</div></div>}
        <div className="mt-5 flex flex-wrap gap-2">{!detail.assigned_user_id&&<button onClick={()=>action.mutate({path:`/tasks/${selectedId}/claim`})} className="rounded-xl border border-green-600 px-4 py-2 text-sm font-medium text-green-700">Podejmij zadanie</button>}{['TODO','BLOCKED','OVERDUE'].includes(detail.status)&&<button onClick={()=>action.mutate({path:`/tasks/${selectedId}/start`})} className="rounded-xl bg-blue-600 px-4 py-2 text-sm font-medium text-white">Rozpocznij</button>}{!['COMPLETED','CANCELLED','SKIPPED'].includes(detail.status)&&<button onClick={()=>action.mutate({path:`/tasks/${selectedId}/complete`})} className="rounded-xl bg-green-600 px-4 py-2 text-sm font-medium text-white">Zakończ</button>}{!['COMPLETED','CANCELLED','SKIPPED'].includes(detail.status)&&<button onClick={()=>{const value=window.prompt('Opisz problem');if(value)action.mutate({path:`/tasks/${selectedId}/block`,body:{comment:value}})}} className="rounded-xl border border-red-300 px-4 py-2 text-sm font-medium text-red-700">Zgłoś problem</button>}{manager&&!['COMPLETED','CANCELLED','SKIPPED'].includes(detail.status)&&<button onClick={()=>action.mutate({path:`/tasks/${selectedId}/skip`})} className="rounded-xl border px-4 py-2 text-sm text-gray-600">Pomiń zadanie</button>}{manager&&!['COMPLETED','CANCELLED','SKIPPED'].includes(detail.status)&&<button onClick={()=>action.mutate({path:`/tasks/${selectedId}/cancel`})} className="rounded-xl border px-4 py-2 text-sm text-gray-600">Anuluj zadanie</button>}</div>
        <div className="mt-5 rounded-xl border p-4"><h3 className="mb-3 flex items-center gap-2 font-semibold"><Camera className="h-4 w-4"/> Zdjęcia {detail.requires_photo&&<span className="text-xs text-red-600">wymagane</span>}</h3><div className="flex flex-wrap gap-2">{detail.attachments?.map((item:any)=><button key={item.id} onClick={()=>openAttachment(item)} className="rounded-lg bg-gray-100 px-3 py-2 text-xs">{item.file_name}</button>)}<label className="cursor-pointer rounded-lg border border-dashed px-3 py-2 text-xs text-green-700">+ Dodaj zdjęcie<input type="file" accept="image/jpeg,image/png,image/webp" className="hidden" onChange={e=>e.target.files?.[0]&&upload.mutate(e.target.files[0])}/></label></div></div>
        <div className="mt-5"><h3 className="mb-3 flex items-center gap-2 font-semibold"><MessageSquare className="h-4 w-4"/> Komentarze</h3><div className="space-y-2">{detail.comments?.map((item:any)=><div key={item.id} className="rounded-xl bg-gray-50 p-3 text-sm"><div>{item.body}</div><div className="mt-1 text-xs text-gray-400">{item.user_name} · {dateLabel(item.created_at)}</div></div>)}</div><div className="mt-3 flex gap-2"><input value={comment} onChange={e=>setComment(e.target.value)} placeholder="Dodaj komentarz…" className="min-w-0 flex-1 rounded-xl border px-3 py-2"/><button disabled={!comment.trim()} onClick={()=>addComment.mutate()} className="rounded-xl bg-gray-900 px-4 py-2 text-sm text-white">Dodaj</button></div></div>
        {detail.recurrence_rule&&<div className="mt-4 flex items-center gap-2 rounded-xl bg-purple-50 p-3 text-sm text-purple-700"><Repeat2 className="h-4 w-4"/> Zadanie powtarzalne: {detail.recurrence_rule}</div>}
        {detail.status==='BLOCKED'&&<div className="mt-4 flex items-center gap-2 rounded-xl bg-red-50 p-3 text-sm text-red-700"><AlertTriangle className="h-4 w-4"/> Zadanie oczekuje na rozwiązanie problemu.</div>}
      </div></div>}
    </div>
  )
}
