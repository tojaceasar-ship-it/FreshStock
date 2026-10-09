import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, CheckCircle2, ShieldCheck, Sparkles, TrendingDown } from 'lucide-react'
import { api } from '../lib/api'
import { formatCurrency, formatDate } from '../lib/utils'

export default function Promotions() {
  const qc = useQueryClient()
  const { data: suggestions = [], isLoading } = useQuery({ queryKey: ['promo-suggestions'], queryFn: async () => (await api.get('/promotions/suggestions')).data })
  const { data: promos = [] } = useQuery({ queryKey: ['promotions'], queryFn: async () => (await api.get('/promotions')).data })

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['promotions'] })
    qc.invalidateQueries({ queryKey: ['promo-suggestions'] })
    qc.invalidateQueries({ queryKey: ['savings'] })
  }
  const acceptMutation = useMutation({
    mutationFn: async (suggestion: any) => {
      const created = (await api.post('/promotions', {
        product_id: suggestion.product_id,
        batch_id: suggestion.batch_id,
        discounted_price: suggestion.suggested_price,
        reason: suggestion.explanation,
        strategy: 'SMART_MARKDOWN',
        recommendation_data: {
          confidence: suggestion.confidence,
          at_risk_quantity: suggestion.at_risk_quantity,
          avg_daily_sales: suggestion.avg_daily_sales,
          sell_through_risk_percent: suggestion.sell_through_risk_percent,
          margin_floor_applied: suggestion.margin_floor_applied,
        },
      })).data
      await api.put(`/promotions/${created.id}/approve`)
      return created
    },
    onSuccess: refresh,
  })
  const approveMutation = useMutation({ mutationFn: async (id: number) => (await api.put(`/promotions/${id}/approve`)).data, onSuccess: refresh })

  return (
    <div className="space-y-6">
      <div><div className="flex items-center gap-2 text-sm font-semibold text-green-700"><Sparkles className="h-4 w-4" /> Smart Markdown</div><h1 className="text-2xl font-bold">Inteligentne przeceny</h1><p className="text-sm text-gray-500">Cena uwzględnia termin, ilość, tempo sprzedaży i koszt zakupu.</p></div>
      <div className="flex gap-3 rounded-2xl border border-green-200 bg-green-50 p-4 text-sm text-green-900"><ShieldCheck className="h-5 w-5 shrink-0" /><div><b>Bezpieczna rekomendacja:</b> system nie zmienia ceny samodzielnie i nie schodzi poniżej kosztu zakupu. Każda cena wymaga zatwierdzenia kierownika.</div></div>

      <div className="grid gap-4 xl:grid-cols-2">
        {suggestions.map((s: any) => (
          <div key={s.batch_id} className="rounded-2xl border bg-white p-5 shadow-sm">
            <div className="flex items-start justify-between gap-3"><div><div className="font-bold">{s.product_name}</div><div className="text-xs text-gray-500">{s.sku} · partia {s.batch_number} · termin {formatDate(s.expiry_date)}</div></div><span className={`rounded-full px-2.5 py-1 text-xs font-bold ${s.confidence === 'HIGH' ? 'bg-green-100 text-green-700' : s.confidence === 'MEDIUM' ? 'bg-blue-100 text-blue-700' : 'bg-amber-100 text-amber-700'}`}>Pewność: {s.confidence}</span></div>
            <div className="mt-4 grid grid-cols-3 gap-2 text-center"><Mini label="Obecna" value={formatCurrency(s.original_price)} /><Mini label="Sugerowana" value={formatCurrency(s.suggested_price)} strong /><Mini label="Rabat" value={`−${s.discount_percent}%`} /></div>
            <div className="mt-4 rounded-xl bg-gray-50 p-3 text-sm"><div className="flex items-center gap-2 font-semibold"><TrendingDown className="h-4 w-4 text-orange-600" /> Ryzyko niesprzedania: {s.sell_through_risk_percent}%</div><p className="mt-1 text-xs text-gray-600">{s.explanation}</p><div className="mt-2 flex flex-wrap gap-3 text-xs text-gray-500"><span>Tempo: {s.avg_daily_sales} szt./dzień</span><span>Zagrożone: {s.at_risk_quantity}/{s.quantity} szt.</span><span>Możliwy przychód: {formatCurrency(s.potential_recovered_revenue)}</span></div></div>
            {s.margin_floor_applied && <div className="mt-3 flex items-center gap-2 text-xs font-medium text-amber-700"><AlertTriangle className="h-4 w-4" /> Zastosowano dolny limit ceny równy kosztowi zakupu.</div>}
            <button onClick={() => acceptMutation.mutate(s)} disabled={acceptMutation.isPending} className="mt-4 w-full rounded-xl bg-green-600 py-2.5 text-sm font-bold text-white disabled:opacity-50">Zatwierdź i aktywuj</button>
          </div>
        ))}
      </div>
      {!isLoading && !suggestions.length && <div className="rounded-2xl border bg-white p-10 text-center"><CheckCircle2 className="mx-auto mb-3 h-10 w-10 text-green-600" /><div className="font-semibold">Brak partii wymagających przeceny</div><p className="text-sm text-gray-500">System nie wykrył obecnie ryzyka wymagającego obniżki ceny.</p></div>}

      <div className="overflow-hidden rounded-2xl border bg-white"><div className="border-b p-4 font-semibold">Historia i aktywne przeceny</div><div className="overflow-x-auto"><table className="w-full text-sm"><thead className="bg-gray-50 text-xs uppercase"><tr><th className="px-4 py-3 text-left">Produkt</th><th>Cena regularna</th><th>Cena po przecenie</th><th>Rabat</th><th>Status</th><th>Strategia</th><th>Akcja</th></tr></thead><tbody className="divide-y">{promos.map((p: any) => <tr key={p.id}><td className="px-4 py-3 font-medium">{p.product_name}</td><td className="text-center">{formatCurrency(p.original_price)}</td><td className="text-center font-bold">{formatCurrency(p.discounted_price)}</td><td className="text-center">−{Number(p.discount_percent).toFixed(0)}%</td><td className="text-center"><span className="rounded-full bg-blue-50 px-2 py-1 text-xs text-blue-700">{p.status}</span></td><td className="text-center text-xs">{p.strategy}</td><td className="text-center">{p.status === 'suggested' && <button onClick={() => approveMutation.mutate(p.id)} className="rounded-lg bg-blue-600 px-3 py-1.5 text-xs text-white">Aktywuj</button>}</td></tr>)}</tbody></table></div></div>
      {(acceptMutation.isError || approveMutation.isError) && <div className="rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700">Nie udało się zapisać przeceny. Sprawdź dane i spróbuj ponownie.</div>}
    </div>
  )
}

function Mini({ label, value, strong = false }: { label: string; value: string; strong?: boolean }) {
  return <div className="rounded-xl bg-gray-50 p-3"><div className="text-[11px] text-gray-500">{label}</div><div className={`mt-1 ${strong ? 'font-bold text-green-700' : 'font-semibold'}`}>{value}</div></div>
}
