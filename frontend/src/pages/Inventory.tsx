import { useCallback, useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Camera, CheckCircle, CloudOff, Plus, RotateCcw, ScanLine, Wifi } from 'lucide-react'
import { api } from '../lib/api'
import { getLocale } from '../lib/i18n'
import { reportScanEvent, scanSignal } from '../lib/scannerFeedback'

const QUEUE_KEY = 'freshstock.inventory.queue.v1'
const PRODUCT_CACHE_KEY = 'freshstock.inventory.products.v1'

type QueueEntry = {
  id: string
  countId: number
  product: any
  counted_quantity: number
  queuedAt: string
}

function readStorage<T>(key: string, fallback: T): T {
  try { return JSON.parse(localStorage.getItem(key) || '') as T } catch { return fallback }
}

function validGtin(value: string) {
  if (!/^\d+$/.test(value) || ![8, 12, 13, 14].includes(value.length)) return false
  const digits = value.split('').map(Number), check = digits.pop()!
  const sum = digits.reverse().reduce((total, digit, index) => total + digit * (index % 2 === 0 ? 3 : 1), 0)
  return (10 - (sum % 10)) % 10 === check
}

function mergeItem(items: any[], item: any) {
  const index = items.findIndex(current => current.product_id === item.product_id && (current.batch_id || null) === (item.batch_id || null))
  if (index < 0) return [...items, item]
  const next = [...items]; next[index] = item; return next
}

export default function Inventory() {
  const qc = useQueryClient()
  const scannerRef = useRef<any>(null)
  const scanCandidate = useRef({ code: '', count: 0, lastAt: 0 })
  const scanProcessing = useRef(false)
  const productPending = useRef(false)
  const scanStartedAt = useRef(0)
  const lastRejected = useRef({ code: '', at: 0 })
  const syncing = useRef(false)
  const { data: counts } = useQuery({ queryKey: ['counts'], queryFn: async () => (await api.get('/inventory-counts')).data })
  const { data: locations } = useQuery({ queryKey: ['locations'], queryFn: async () => (await api.get('/locations')).data })
  const [locationId, setLocationId] = useState('')
  const [activeCount, setActiveCount] = useState<any>(null)
  const [code, setCode] = useState('')
  const [product, setProduct] = useState<any>(null)
  const [quantity, setQuantity] = useState(1)
  const [scanning, setScanning] = useState(false)
  const [cameraStarting, setCameraStarting] = useState(false)
  const [scanFeedback, setScanFeedback] = useState('')
  const [torchSupported, setTorchSupported] = useState(false)
  const [torchOn, setTorchOn] = useState(false)
  const [zoomRange, setZoomRange] = useState<{min:number,max:number,step:number,value:number}|null>(null)
  const [message, setMessage] = useState('')
  const [online, setOnline] = useState(navigator.onLine)
  const [queue, setQueue] = useState<QueueEntry[]>(() => readStorage(QUEUE_KEY, []))

  const refresh = useCallback(() => qc.invalidateQueries({ queryKey: ['counts'] }), [qc])
  useEffect(() => { localStorage.setItem(QUEUE_KEY, JSON.stringify(queue)) }, [queue])
  useEffect(() => {
    const update = () => setOnline(navigator.onLine)
    window.addEventListener('online', update); window.addEventListener('offline', update)
    return () => { window.removeEventListener('online', update); window.removeEventListener('offline', update) }
  }, [])

  const applyServerItem = useCallback((countId: number, item: any) => {
    setActiveCount((current: any) => current?.id === countId ? { ...current, status: 'in_progress', items: mergeItem((current.items || []).filter((entry: any) => !entry.pending || entry.product_id !== item.product_id), item) } : current)
  }, [])

  const syncQueue = useCallback(async () => {
    if (!navigator.onLine || syncing.current || !queue.length) return
    syncing.current = true
    let remaining = [...queue]
    let synced = 0
    for (const entry of queue) {
      try {
        const item = (await api.post(`/inventory-counts/${entry.countId}/items`, { product_id: entry.product.id, counted_quantity: entry.counted_quantity })).data
        applyServerItem(entry.countId, item)
        remaining = remaining.filter(current => current.id !== entry.id)
        setQueue(remaining)
        synced += 1
      } catch (error: any) {
        if (!error?.response || error.response.status >= 500) break
        remaining = remaining.filter(current => current.id !== entry.id)
        setQueue(remaining)
        setMessage(`Odrzucono zapis offline dla ${entry.product.name}: ${error.response.data?.detail || 'błąd danych'}`)
      }
    }
    syncing.current = false
    if (synced) { setMessage(`Zsynchronizowano ${synced} zapisów offline`); refresh() }
  }, [queue, applyServerItem, refresh])

  useEffect(() => { if (online) syncQueue() }, [online, syncQueue])

  const createMut = useMutation({
    mutationFn: async () => (await api.post('/inventory-counts', { location_id: locationId ? Number(locationId) : null, items: [] })).data,
    onSuccess: data => { setActiveCount(data); setMessage(`Sesja ${data.count_number} rozpoczęta`); refresh() }
  })
  const completeMut = useMutation({
    mutationFn: async (id: number) => { await syncQueue(); if (queue.some(entry => entry.countId === id)) throw new Error('Najpierw zsynchronizuj zapisy offline'); return (await api.post(`/inventory-counts/${id}/complete`)).data },
    onSuccess: () => { setMessage('Inwentaryzacja zakończona, stany zostały skorygowane'); setActiveCount(null); refresh() },
    onError: (error: any) => setMessage(error?.response?.data?.detail || error.message)
  })

  const cacheProduct = (barcode: string, value: any) => {
    const cache = readStorage<Record<string, any>>(PRODUCT_CACHE_KEY, {})
    cache[barcode] = value
    const trimmed = Object.fromEntries(Object.entries(cache).slice(-200))
    localStorage.setItem(PRODUCT_CACHE_KEY, JSON.stringify(trimmed))
  }

  const lookup = async (barcode: string, scanMeta?: {format?:string,duration_ms?:number}) => {
    const value = barcode.trim().replace(/\s+/g, '')
    if (!value) return
    setMessage('')
    try {
      const response = await api.get(`/products/barcode/${encodeURIComponent(value)}`)
      if (response.data.source !== 'local' || !response.data.product) throw new Error('Produktu nie ma w bazie sklepu')
      setProduct(response.data.product); cacheProduct(value, response.data.product)
      setCode(value); setQuantity(1)
      productPending.current=true
      if(scanMeta)reportScanEvent({context:'inventory',outcome:'accepted',barcode_format:scanMeta.format,code_length:value.length,duration_ms:scanMeta.duration_ms})
      return true
    } catch (error: any) {
      const cached = readStorage<Record<string, any>>(PRODUCT_CACHE_KEY, {})[value]
      if (!navigator.onLine && cached) {
        setProduct(cached); setCode(value); setQuantity(1); setMessage('Tryb offline — użyto zapisanych danych produktu')
        productPending.current=true
        if(scanMeta)reportScanEvent({context:'inventory',outcome:'accepted',barcode_format:scanMeta.format,code_length:value.length,duration_ms:scanMeta.duration_ms})
        return true
      } else {
        setProduct(null); setMessage(error?.response?.data?.detail || error.message || 'Nie znaleziono produktu')
        if(scanMeta)reportScanEvent({context:'inventory',outcome:error?.response?.status===404?'not_found':'error',barcode_format:scanMeta.format,code_length:value.length,duration_ms:scanMeta.duration_ms,error_reason:error?.response?`http_${error.response.status}`:'network'})
        return false
      }
    }
  }

  const saveItem = async () => {
    if (!activeCount || !product) return
    const entry: QueueEntry = { id: crypto.randomUUID(), countId: activeCount.id, product, counted_quantity: quantity, queuedAt: new Date().toISOString() }
    if (!navigator.onLine) {
      setQueue(current => [...current.filter(item => !(item.countId === entry.countId && item.product.id === product.id)), entry])
      applyServerItem(activeCount.id, { id: `pending-${entry.id}`, product_id: product.id, product_name: product.name, batch_id: null, system_quantity: product.total_stock || 0, counted_quantity: quantity, difference: quantity - (product.total_stock || 0), pending: true, queue_id: entry.id })
      setMessage(`Zapisano offline: ${product.name}. Synchronizacja nastąpi po odzyskaniu internetu.`)
    } else {
      try {
        const item = (await api.post(`/inventory-counts/${activeCount.id}/items`, { product_id: product.id, counted_quantity: quantity })).data
        applyServerItem(activeCount.id, item); setMessage(`Dodano ${item.product_name}: ${item.counted_quantity} szt. (różnica ${item.difference})`); refresh()
      } catch (error: any) {
        if (!error?.response) {
          setQueue(current => [...current.filter(item => !(item.countId === entry.countId && item.product.id === product.id)), entry])
          applyServerItem(activeCount.id, { id: `pending-${entry.id}`, product_id: product.id, product_name: product.name, batch_id: null, system_quantity: product.total_stock || 0, counted_quantity: quantity, difference: quantity - (product.total_stock || 0), pending: true, queue_id: entry.id })
          setMessage('Połączenie przerwane — zapis trafił do kolejki offline')
        } else setMessage(error.response.data?.detail || 'Nie udało się zapisać pozycji')
      }
    }
    setCode(''); setProduct(null); setQuantity(1)
    productPending.current=false; scanProcessing.current=false; scanCandidate.current={code:'',count:0,lastAt:0}; setScanFeedback('Gotowe — pokaż kolejny kod')
  }

  const undoItem = async (item: any) => {
    if (item.pending) {
      setQueue(current => current.filter(entry => entry.id !== item.queue_id))
      setActiveCount((current: any) => ({ ...current, items: current.items.filter((entry: any) => entry.id !== item.id) }))
      setMessage('Usunięto zapis z kolejki offline')
      return
    }
    try {
      await api.delete(`/inventory-counts/${activeCount.id}/items/${item.id}`)
      setActiveCount((current: any) => ({ ...current, items: current.items.filter((entry: any) => entry.id !== item.id) }))
      setMessage('Cofnięto pozycję inwentaryzacji'); refresh()
    } catch (error: any) { setMessage(error?.response?.data?.detail || 'Nie udało się cofnąć pozycji') }
  }

  const stopScanner = async () => {
    const scanner = scannerRef.current; scannerRef.current = null
    if (scanner?.isScanning) try { await scanner.stop() } catch {
      // Kamera mogła zostać zatrzymana przez przeglądarkę.
    }
    try { scanner?.clear() } catch {
      // Kontener może być już usunięty podczas zmiany widoku.
    }
    setScanning(false); setCameraStarting(false); setTorchSupported(false); setTorchOn(false); setZoomRange(null); scanProcessing.current=false; scanCandidate.current = { code: '', count: 0, lastAt: 0 }
  }

  const startScanner = async () => {
    if (!activeCount || scanning || cameraStarting) return
    setCameraStarting(true); setScanFeedback('Szukam kodu…'); scanStartedAt.current=Date.now()
    try {
      if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) throw new Error('Kamera wymaga bezpiecznego połączenia HTTPS')
      const { Html5Qrcode, Html5QrcodeSupportedFormats } = await import('html5-qrcode')
      const cameras = await Html5Qrcode.getCameras()
      if (!cameras.length) throw new Error('Nie znaleziono kamery')
      const rear = cameras.find((camera: any) => /back|rear|environment|tył/i.test(camera.label)) || cameras[cameras.length - 1]
      const scanner = new Html5Qrcode('inventory-reader', { formatsToSupport: [Html5QrcodeSupportedFormats.EAN_13, Html5QrcodeSupportedFormats.EAN_8, Html5QrcodeSupportedFormats.UPC_A, Html5QrcodeSupportedFormats.CODE_128], verbose: false })
      scannerRef.current = scanner
      const videoConstraints: any = { deviceId: { exact: rear.id }, width: { ideal: 1920 }, height: { ideal: 1080 }, frameRate: { ideal: 30 }, advanced: [{ focusMode: 'continuous' }] }
      await scanner.start(rear.id, { fps: 15, aspectRatio: 16 / 9, videoConstraints, qrbox: (width: number, height: number) => ({ width: Math.min(width * .9, 520), height: Math.min(height * .5, 220) }) }, async (decoded: string, decodedResult:any) => {
        if(scanProcessing.current||productPending.current)return
        const normalized = decoded.trim().replace(/\s+/g, '')
        const format=String(decodedResult?.result?.format?.formatName||'')
        if (/^\d+$/.test(normalized) && [8, 12, 13, 14].includes(normalized.length) && !validGtin(normalized)) { const now=Date.now();setScanFeedback('Odrzucono błędny odczyt — ustaw kod ponownie');if(lastRejected.current.code!==normalized||now-lastRejected.current.at>2500){lastRejected.current={code:normalized,at:now};scanSignal(false);reportScanEvent({context:'inventory',outcome:'rejected',barcode_format:format||undefined,code_length:normalized.length,duration_ms:now-scanStartedAt.current,error_reason:'checksum'})}return }
        const now = Date.now(), previous = scanCandidate.current
        const count = previous.code === normalized && now - previous.lastAt < 1800 ? previous.count + 1 : 1
        scanCandidate.current = { code: normalized, count, lastAt: now }
        if (count < 2) { setScanFeedback('Weryfikacja kodu 1/2…'); return }
        scanProcessing.current=true;setScanFeedback('Kod potwierdzony — wpisz ilość');scanSignal(true);await lookup(normalized,{format:format||undefined,duration_ms:Date.now()-scanStartedAt.current});scanStartedAt.current=Date.now();scanProcessing.current=false;scanCandidate.current={code:'',count:0,lastAt:0}
      }, () => {})
      setScanning(true)
      try{const capabilities=scanner.getRunningTrackCameraCapabilities();const torch=capabilities.torchFeature();setTorchSupported(torch.isSupported());const zoom=capabilities.zoomFeature();if(zoom.isSupported()){const min=zoom.min(),max=zoom.max(),step=zoom.step()||.1,value=Math.min(max,Math.max(min,zoom.value()||min));setZoomRange({min,max,step,value})}}catch{
        // Część przeglądarek nie udostępnia capabilities kamery.
      }
    } catch (error: any) { await stopScanner(); setMessage(error.message || 'Kamera jest niedostępna — wpisz EAN ręcznie') }
  }

  useEffect(() => () => { const scanner = scannerRef.current; if (scanner?.isScanning) scanner.stop().catch(() => {}) }, [])
  const toggleTorch=async()=>{try{const feature=scannerRef.current?.getRunningTrackCameraCapabilities().torchFeature();const next=!torchOn;await feature.apply(next);setTorchOn(next)}catch{setMessage('Latarka nie jest dostępna na tym urządzeniu')}}
  const changeZoom=async(value:number)=>{if(!zoomRange)return;setZoomRange({...zoomRange,value});try{await scannerRef.current?.getRunningTrackCameraCapabilities().zoomFeature().apply(value)}catch{
    setMessage('Zoom nie jest dostępny na tym urządzeniu')
  }}
  const pendingForCount = activeCount ? queue.filter(entry => entry.countId === activeCount.id).length : 0

  return <div className="space-y-6">
    <div className="flex flex-wrap justify-between gap-3"><h1 className="text-2xl font-bold">Inwentaryzacja ze skanerem</h1><div className={`flex items-center gap-2 text-sm px-3 py-1.5 rounded-full ${online ? 'bg-green-50 text-green-700' : 'bg-amber-50 text-amber-700'}`}>{online ? <Wifi className="w-4 h-4" /> : <CloudOff className="w-4 h-4" />}{online ? 'Online' : 'Offline'}{queue.length ? ` · kolejka ${queue.length}` : ''}</div></div>
    {!activeCount ? <div className="bg-white border rounded-2xl p-6 space-y-4"><h2 className="font-semibold">Rozpocznij sesję liczenia</h2><select value={locationId} onChange={event => setLocationId(event.target.value)} className="border rounded-xl px-3 py-2 w-full md:w-80"><option value="">Wszystkie lokalizacje</option>{locations?.map((location: any) => <option key={location.id} value={location.id}>{location.name}</option>)}</select><button onClick={() => createMut.mutate()} disabled={createMut.isPending || !online} className="block bg-green-600 text-white px-4 py-2 rounded-xl disabled:opacity-50">Utwórz sesję i rozpocznij skanowanie</button></div> :
      <div className="bg-white border rounded-2xl p-6 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3"><div><div className="text-xs text-gray-500">Aktywna sesja</div><div className="font-bold">{activeCount.count_number}</div></div><button onClick={() => completeMut.mutate(activeCount.id)} disabled={completeMut.isPending || pendingForCount > 0 || !online} title={pendingForCount ? 'Najpierw zsynchronizuj kolejkę offline' : ''} className="bg-green-700 text-white px-4 py-2 rounded-xl flex items-center gap-2 disabled:opacity-40"><CheckCircle className="w-4 h-4" /> Zakończ i skoryguj stany</button></div>
        {online && queue.length > 0 && <button onClick={syncQueue} className="w-full border border-blue-300 text-blue-700 rounded-xl py-2">Synchronizuj kolejkę teraz ({queue.length})</button>}
        <div className="flex gap-2"><input value={code} onChange={event => setCode(event.target.value)} onKeyDown={event => event.key === 'Enter' && lookup(code)} placeholder="EAN produktu" className="border rounded-xl px-4 py-3 flex-1" autoFocus /><button onClick={() => lookup(code)} className="border px-4 rounded-xl"><ScanLine className="w-5 h-5" /></button></div>
        <button onClick={scanning ? stopScanner : startScanner} disabled={cameraStarting} className="w-full border-2 border-dashed rounded-xl py-3 flex justify-center items-center gap-2 disabled:opacity-50"><Camera className="w-5 h-5" />{cameraStarting ? 'Uruchamianie kamery…' : scanning ? 'Zatrzymaj kamerę' : 'Skanuj kamerą HD'}</button>
        <div id="inventory-reader" className={`overflow-hidden rounded-xl bg-black ${scanning || cameraStarting ? 'min-h-52' : 'hidden'}`} />{scanning && <div className="rounded-xl bg-gray-50 border p-3 space-y-3"><div className="flex justify-between items-center"><p className="text-sm font-semibold text-green-700">{scanFeedback}</p>{torchSupported&&<button type="button" onClick={toggleTorch} className={`px-3 py-1.5 rounded-lg text-xs font-semibold ${torchOn?'bg-amber-400 text-amber-950':'bg-gray-800 text-white'}`}>{torchOn?'Wyłącz latarkę':'Włącz latarkę'}</button>}</div>{zoomRange&&<label className="flex items-center gap-3 text-xs text-gray-600"><span>Zoom</span><input className="flex-1 accent-green-600" type="range" min={zoomRange.min} max={zoomRange.max} step={zoomRange.step} value={zoomRange.value} onChange={event=>changeZoom(Number(event.target.value))}/><span>{zoomRange.value.toFixed(1)}×</span></label>}<p className="text-[11px] text-gray-500">Kamera pozostaje aktywna. Po zapisaniu ilości od razu pokaż kolejny kod.</p></div>}
        {product && <div className="bg-green-50 border border-green-200 rounded-xl p-4 flex flex-wrap gap-4 items-end"><div className="flex-1 min-w-48"><div className="font-semibold">{product.name}</div><div className="text-xs text-gray-500">{product.sku} • system: {product.total_stock} {product.unit}</div></div><label className="text-xs">Stan fizyczny<input type="number" min="0" value={quantity} onChange={event => setQuantity(Math.max(0, Number(event.target.value)))} className="block border rounded-lg px-3 py-2 w-28 text-base" /></label><button onClick={saveItem} className="bg-green-600 text-white px-4 py-2 rounded-xl flex items-center gap-2"><Plus className="w-4 h-4" /> {online ? 'Dodaj' : 'Zapisz offline'}</button></div>}
        {message && <div className="text-sm bg-blue-50 text-blue-800 p-3 rounded-xl">{message}</div>}
        <div className="divide-y border rounded-xl">{activeCount.items?.map((item: any) => <div key={item.id} className={`p-3 flex flex-wrap justify-between gap-2 text-sm ${item.pending ? 'bg-amber-50' : ''}`}><span>{item.product_name}{item.pending && <small className="ml-2 text-amber-700">oczekuje na synchronizację</small>}</span><span className="flex items-center gap-3">system {item.system_quantity} / fizycznie {item.counted_quantity} / <b className={item.difference ? 'text-orange-600' : 'text-green-600'}>{item.difference > 0 ? '+' : ''}{item.difference}</b><button onClick={() => undoItem(item)} className="text-red-600 p-1" title="Cofnij wpis"><RotateCcw className="w-4 h-4" /></button></span></div>)}{!activeCount.items?.length && <div className="p-4 text-sm text-gray-500">Zeskanuj pierwszy produkt.</div>}</div>
      </div>}
    <div className="bg-white border rounded-2xl overflow-x-auto"><table className="w-full text-sm"><thead className="bg-gray-50 text-xs uppercase"><tr><th className="px-4 py-3 text-left">Numer</th><th>Status</th><th>Pozycje</th><th>Data</th><th>Akcja</th></tr></thead><tbody className="divide-y">{counts?.map((count: any) => <tr key={count.id}><td className="px-4 py-3 font-medium">{count.count_number}</td><td className="text-center">{count.status}</td><td className="text-center">{count.items?.length || 0}</td><td className="text-center text-xs">{new Date(count.created_at).toLocaleString(getLocale())}</td><td className="text-center">{count.status !== 'completed' && <button onClick={() => setActiveCount(count)} className="text-green-700 font-medium">Wznów</button>}</td></tr>)}</tbody></table></div>
  </div>
}
