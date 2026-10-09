import { useState, useEffect, useRef } from 'react'
import { api } from '../lib/api'
import { formatCurrency } from '../lib/utils'
import { Search, Camera, Globe, Database, AlertCircle, CheckCircle, Plus } from 'lucide-react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { useAuth } from '../hooks/useAuth'
import { reportScanEvent, scanSignal, scannerDeviceId } from '../lib/scannerFeedback'

function isValidGtin(value:string) {
  if (!/^\d+$/.test(value) || ![8, 12, 13, 14].includes(value.length)) return false
  const digits=value.split('').map(Number), check=digits.pop()!
  const sum=digits.reverse().reduce((total,digit,index)=>total+digit*(index%2===0?3:1),0)
  return (10-(sum%10))%10===check
}

export default function Scanner() {
  const { user } = useAuth()
  const [code, setCode] = useState('')
  const [result, setResult] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [scanning, setScanning] = useState(false)
  const [cameraStarting, setCameraStarting] = useState(false)
  const [cameras, setCameras] = useState<any[]>([])
  const [selectedCamera, setSelectedCamera] = useState('')
  const [cameraInfo, setCameraInfo] = useState('')
  const [torchSupported, setTorchSupported] = useState(false)
  const [torchOn, setTorchOn] = useState(false)
  const [zoomRange, setZoomRange] = useState<{min:number,max:number,step:number,value:number}|null>(null)
  const [scanFeedback, setScanFeedback] = useState('')
  const [batches, setBatches] = useState<any[]>([])
  const [continuousMode, setContinuousMode] = useState(true)
  const [recentScans, setRecentScans] = useState<{code:string,name:string,at:number}[]>([])
  const scannerRef = useRef<any>(null)
  const mountedRef = useRef(true)
  const candidateRef = useRef<{code:string,count:number,lastAt:number}>({code:'',count:0,lastAt:0})
  const processingRef = useRef(false)
  const continuousRef = useRef(true)
  const scanStartedAtRef = useRef(0)
  const lastRejectedRef = useRef({code:'',at:0})
  useEffect(() => { continuousRef.current = continuousMode }, [continuousMode])
  const canSeeStats = user?.role === 'OWNER' || user?.role === 'MANAGER'
  const { data: scanStats } = useQuery({ queryKey: ['scanner-stats'], queryFn: async () => (await api.get('/scanner/stats', { params: { days: 30 } })).data, enabled: canSeeStats })

  const lookup = async (ean: string, scanMeta?: {format?:string,duration_ms?:number}) => {
    if (!ean.trim()) return
    setError('')
    setResult(null)
    setBatches([])
    setLoading(true)
    try {
      // Checks the store first, then the official Open Facts databases.
      const res = await api.get(`/products/barcode/${ean.trim()}`)
      setResult(res.data)
      if (scanMeta) {
        reportScanEvent({ context: 'product', outcome: res.data.source === 'not_found' ? 'not_found' : 'accepted', barcode_format: scanMeta.format, code_length: ean.trim().length, duration_ms: scanMeta.duration_ms })
        setRecentScans(current => [{ code: ean.trim(), name: res.data.product?.name || res.data.suggestion?.name || 'Nieznany produkt', at: Date.now() }, ...current].slice(0, 8))
      }

      // If found locally, also fetch batches
      if (res.data.source === 'local' && res.data.product) {
        const bRes = await api.get(`/products/${res.data.product.id}/batches`)
        setBatches(bRes.data)
      }
    } catch (e: any) {
      setError('Błąd podczas wyszukiwania: ' + (e?.response?.data?.detail || e.message))
      if (scanMeta) reportScanEvent({ context: 'product', outcome: 'error', barcode_format: scanMeta.format, code_length: ean.trim().length, duration_ms: scanMeta.duration_ms, error_reason: e?.response ? `http_${e.response.status}` : 'network' })
    } finally {
      setLoading(false)
    }
  }

  const handleScan = () => { if (code) lookup(code) }

  const stopScanner = async () => {
    const scanner = scannerRef.current
    scannerRef.current = null
    if (scanner?.isScanning) {
      try { await scanner.stop() } catch { /* camera may already be closed */ }
    }
    try { scanner?.clear() } catch { /* reader may already be cleared */ }
    candidateRef.current={code:'',count:0,lastAt:0}; processingRef.current=false
    if (mountedRef.current) { setScanning(false); setTorchOn(false); setTorchSupported(false); setZoomRange(null); setCameraInfo(''); setScanFeedback('') }
  }

  const cameraError = (err: any) => {
    const name = err?.name || ''
    const message = String(err?.message || err || '')
    if (name === 'NotAllowedError' || /permission|notallowed/i.test(message)) return 'Brak zgody na kamerę. W ustawieniach przeglądarki zezwól FreshStock na używanie kamery.'
    if (name === 'NotFoundError' || /notfound|no camera/i.test(message)) return 'Nie znaleziono kamery w tym urządzeniu.'
    if (name === 'NotReadableError' || /could not start|notreadable|track start/i.test(message)) return 'Kamera jest używana przez inną aplikację. Zamknij ją i spróbuj ponownie.'
    if (!window.isSecureContext) return 'Kamera wymaga bezpiecznego połączenia HTTPS.'
    return `Nie udało się uruchomić kamery${message ? `: ${message}` : '.'}`
  }

  const startScanner = async () => {
    if (cameraStarting || scanning) return
    setError('')
    setScanFeedback('Szukam kodu…')
    scanStartedAtRef.current=Date.now()
    candidateRef.current={code:'',count:0,lastAt:0}; processingRef.current=false
    setCameraStarting(true)
    try {
      if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) throw new Error('Kamera nie jest obsługiwana w tej przeglądarce lub połączenie nie jest bezpieczne')
      const { Html5Qrcode, Html5QrcodeSupportedFormats } = await import('html5-qrcode')
      const devices = await Html5Qrcode.getCameras()
      if (!devices.length) throw new DOMException('Nie znaleziono kamery', 'NotFoundError')
      if (!mountedRef.current) return
      setCameras(devices)
      const rear = devices.find((device: any) => /back|rear|environment|tył|t背/i.test(device.label)) || devices[devices.length - 1]
      const cameraId = selectedCamera || rear.id
      setSelectedCamera(cameraId)
      const scanner = new Html5Qrcode('reader', {
        formatsToSupport: [Html5QrcodeSupportedFormats.EAN_13, Html5QrcodeSupportedFormats.EAN_8, Html5QrcodeSupportedFormats.CODE_128, Html5QrcodeSupportedFormats.UPC_A, Html5QrcodeSupportedFormats.UPC_E],
        verbose: false,
      })
      scannerRef.current = scanner
      const videoConstraints: any = {
        deviceId: { exact: cameraId },
        width: { ideal: 1920 },
        height: { ideal: 1080 },
        frameRate: { ideal: 30 },
        advanced: [{ focusMode: 'continuous' }],
      }
      await scanner.start(
        cameraId,
        { fps: 15, aspectRatio: 16 / 9, videoConstraints, qrbox: (width: number, height: number) => ({ width: Math.min(width * .9, 520), height: Math.min(height * .55, 240) }) },
        async (decoded: string, decodedResult: any) => {
          if (!scannerRef.current || processingRef.current) return
          const normalized=decoded.trim().replace(/\s+/g,'')
          if (!normalized) return
          const numeric=/^\d+$/.test(normalized)
          const formatName=String(decodedResult?.result?.format?.formatName||'')
          const isUpce=/UPC_E/i.test(formatName)
          const standardGtin=numeric && [8,12,13,14].includes(normalized.length) && !isUpce
          if (standardGtin && !isValidGtin(normalized)) {
            candidateRef.current={code:'',count:0,lastAt:0}
            setScanFeedback('Odczyt odrzucony — nie zgadza się cyfra kontrolna. Ustaw kod ponownie w ramce.')
            const now=Date.now()
            if(lastRejectedRef.current.code!==normalized||now-lastRejectedRef.current.at>2500){lastRejectedRef.current={code:normalized,at:now};scanSignal(false);reportScanEvent({context:'product',outcome:'rejected',barcode_format:formatName||undefined,code_length:normalized.length,duration_ms:now-scanStartedAtRef.current,error_reason:'checksum'})}
            return
          }
          const now=Date.now(), previous=candidateRef.current
          const count=previous.code===normalized && now-previous.lastAt<1800 ? previous.count+1 : 1
          candidateRef.current={code:normalized,count,lastAt:now}
          const required=standardGtin?2:3
          if(count<required){setScanFeedback(`Weryfikacja kodu ${count}/${required}…`);return}
          processingRef.current=true
          setScanFeedback('Kod potwierdzony')
          setCode(normalized)
          scanSignal(true)
          const meta={format:formatName||undefined,duration_ms:Date.now()-scanStartedAtRef.current}
          if(!continuousRef.current){await stopScanner();await lookup(normalized,meta);return}
          await lookup(normalized,meta)
          candidateRef.current={code:'',count:0,lastAt:0};processingRef.current=false;scanStartedAtRef.current=Date.now()
          setScanFeedback('Gotowe — pokaż kolejny kod')
        },
        () => {}
      )
      if (mountedRef.current) {
        setScanning(true)
        const settings = scanner.getRunningTrackSettings?.() || {}
        setCameraInfo(settings.width && settings.height ? `${settings.width} × ${settings.height}` : 'HD')
        try {
          const capabilities = scanner.getRunningTrackCameraCapabilities()
          const torch = capabilities.torchFeature()
          setTorchSupported(torch.isSupported())
          const zoom = capabilities.zoomFeature()
          if (zoom.isSupported()) {
            const min=zoom.min(), max=zoom.max(), step=zoom.step() || .1
            const value=Math.min(max, Math.max(min, zoom.value() || min))
            setZoomRange({min,max,step,value})
          }
        } catch { /* capabilities vary by browser */ }
      }
    } catch (err: any) {
      await stopScanner()
      if (mountedRef.current) setError(cameraError(err))
    } finally {
      if (mountedRef.current) setCameraStarting(false)
    }
  }

  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
      const scanner = scannerRef.current
      scannerRef.current = null
      if (scanner?.isScanning) scanner.stop().catch(() => {})
    }
  }, [])

  const toggleTorch = async () => {
    try {
      const feature = scannerRef.current?.getRunningTrackCameraCapabilities().torchFeature()
      const next = !torchOn
      await feature.apply(next); setTorchOn(next)
    } catch { setError('Nie udało się zmienić ustawienia latarki.') }
  }

  const changeZoom = async (value:number) => {
    if (!zoomRange) return
    setZoomRange({...zoomRange,value})
    try { await scannerRef.current?.getRunningTrackCameraCapabilities().zoomFeature().apply(value) } catch { /* keep scanning */ }
  }

  const sourceLabel = result?.source === 'local'
    ? { icon: <Database className="w-4 h-4" />, label: 'Znaleziono w bazie sklepu', color: 'bg-green-50 border-green-200 text-green-800' }
    : result?.source === 'open_food_facts'
    ? { icon: <Globe className="w-4 h-4" />, label: 'Znaleziono w bazach Open Facts — nie ma w bazie sklepu', color: 'bg-blue-50 border-blue-200 text-blue-800' }
    : result?.source === 'not_found'
    ? { icon: <AlertCircle className="w-4 h-4" />, label: 'Nie znaleziono nigdzie — wpisz dane ręcznie', color: 'bg-orange-50 border-orange-200 text-orange-800' }
    : null

  return (
    <div className="space-y-6 max-w-2xl mx-auto">
      <h1 className="text-2xl font-bold">Skaner kodów kreskowych</h1>

      {/* Search bar */}
      <div className="bg-white rounded-2xl border p-6 space-y-4">
        <div className="flex items-center justify-between gap-3 rounded-xl bg-green-50 border border-green-200 p-3"><div><div className="font-semibold text-sm">Tryb ciągły</div><div className="text-xs text-gray-500">Kamera pozostaje aktywna po poprawnym odczycie.</div></div><button type="button" onClick={()=>setContinuousMode(value=>!value)} className={`w-12 h-7 rounded-full p-1 transition ${continuousMode?'bg-green-600':'bg-gray-300'}`}><span className={`block w-5 h-5 bg-white rounded-full transition ${continuousMode?'translate-x-5':''}`}/></button></div>
        <div className="flex gap-2">
          <input
            value={code}
            onChange={e => setCode(e.target.value)}
            placeholder="Wpisz EAN, UPC lub SKU albo zeskanuj"
            className="flex-1 border rounded-xl px-4 py-3 text-lg"
            onKeyDown={e => e.key === 'Enter' && handleScan()}
          />
          <button
            onClick={handleScan}
            disabled={loading}
            className="bg-green-600 text-white px-6 py-3 rounded-xl font-medium flex items-center gap-2 disabled:opacity-50"
          >
            {loading ? <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin" /> : <Search className="w-5 h-5" />}
            Szukaj
          </button>
        </div>
        {cameras.length > 1 && (
          <label className="block text-sm"><span className="font-medium text-gray-700">Kamera</span><select value={selectedCamera} onChange={async e => { const id=e.target.value; await stopScanner(); setSelectedCamera(id) }} className="mt-1 w-full border rounded-xl px-3 py-2 bg-white">{cameras.map(camera => <option key={camera.id} value={camera.id}>{camera.label || `Kamera ${camera.id.slice(0, 6)}`}</option>)}</select></label>
        )}
        <button
          onClick={scanning ? stopScanner : startScanner}
          disabled={cameraStarting}
          className="w-full border-2 border-dashed border-gray-300 rounded-xl py-4 text-gray-600 hover:bg-gray-50 flex items-center justify-center gap-2"
        >
          <Camera className="w-5 h-5" />
          {cameraStarting ? 'Uruchamianie kamery…' : scanning ? 'Zatrzymaj skanowanie' : 'Skanuj kamerą (EAN-13, QR, Code128)'}
        </button>
        <div id="reader" className={`w-full rounded-xl overflow-hidden bg-black ${scanning || cameraStarting ? 'min-h-52' : 'hidden'}`} />
        {scanning && (
          <div className="rounded-xl bg-gray-50 border p-3 space-y-3">
            <div className="flex items-center justify-between gap-3"><span className="text-xs text-gray-500">Jakość obrazu: <b className="text-gray-800">{cameraInfo}</b></span>{torchSupported&&<button type="button" onClick={toggleTorch} className={`px-3 py-1.5 rounded-lg text-xs font-semibold ${torchOn?'bg-amber-400 text-amber-950':'bg-gray-800 text-white'}`}>{torchOn?'Wyłącz latarkę':'Włącz latarkę'}</button>}</div>
            {zoomRange&&<label className="flex items-center gap-3 text-xs text-gray-600"><span>Zoom</span><input className="flex-1 accent-green-600" type="range" min={zoomRange.min} max={zoomRange.max} step={zoomRange.step} value={zoomRange.value} onChange={e=>changeZoom(Number(e.target.value))}/><span>{zoomRange.value.toFixed(1)}×</span></label>}
            <p className="text-[11px] text-gray-500">Trzymaj kod poziomo, wypełnij nim zieloną ramkę i odsuń telefon, jeśli obraz nie może złapać ostrości.</p>
            {scanFeedback&&<p className="text-center text-sm font-semibold text-green-700">{scanFeedback}</p>}
          </div>
        )}

        {/* Lookup logic explanation */}
        <div className="text-xs text-gray-400 flex items-center gap-3">
          <span className="flex items-center gap-1"><Database className="w-3 h-3" /> Baza sklepu</span>
          <span>→</span>
          <span className="flex items-center gap-1"><Globe className="w-3 h-3" /> Open Facts</span>
          <span>→</span>
          <span className="flex items-center gap-1"><Plus className="w-3 h-3" /> Dodaj ręcznie</span>
        </div>

        {error && <div className="bg-red-50 border border-red-200 text-red-700 p-3 rounded-xl text-sm">{error}</div>}
      </div>

      {recentScans.length>0&&<div className="bg-white rounded-2xl border p-4"><h2 className="font-semibold text-sm mb-2">Ostatnie skany na tym urządzeniu</h2><div className="divide-y">{recentScans.map(item=><div key={`${item.code}-${item.at}`} className="py-2 flex justify-between gap-3 text-sm"><span className="truncate">{item.name}</span><span className="font-mono text-xs text-gray-500">{item.code}</span></div>)}</div></div>}

      {canSeeStats&&scanStats&&<div className="bg-white rounded-2xl border p-5 space-y-3"><div className="flex justify-between"><h2 className="font-semibold">Jakość skanowania · 30 dni</h2><span className="text-xs text-gray-400">Urządzenie {scannerDeviceId().slice(0,8)}</span></div><div className="grid grid-cols-3 gap-2 text-center"><div className="bg-gray-50 rounded-xl p-3"><div className="text-xs text-gray-500">Odczyty</div><b>{scanStats.total}</b></div><div className="bg-green-50 rounded-xl p-3"><div className="text-xs text-gray-500">Poprawne</div><b>{scanStats.accepted}</b></div><div className="bg-amber-50 rounded-xl p-3"><div className="text-xs text-gray-500">Skuteczność</div><b>{scanStats.success_rate}%</b></div></div><div className="text-xs text-gray-500">Urządzenia: {scanStats.devices?.map((device:any)=>`${device.platform} ${device.device_id.slice(0,8)}… — ${device.success_rate}%`).join(' · ')||'brak danych'}</div></div>}

      {/* Source badge */}
      {sourceLabel && (
        <div className={`border rounded-xl p-3 flex items-center gap-2 text-sm font-medium ${sourceLabel.color}`}>
          {sourceLabel.icon}
          {sourceLabel.label}
        </div>
      )}

      {/* LOCAL RESULT */}
      {result?.source === 'local' && result.product && (
        <div className="bg-white rounded-2xl border p-6 space-y-4">
          <div className="flex items-center gap-2 text-green-600 font-semibold text-sm">
            <CheckCircle className="w-4 h-4" /> Produkt w bazie sklepu
          </div>
          <div className="flex gap-4">
            <div className="w-16 h-16 bg-gray-100 rounded-xl flex items-center justify-center font-bold text-xl text-gray-400">
              {result.product.sku?.slice(0, 2)}
            </div>
            <div>
              <div className="font-bold text-lg">{result.product.name}</div>
              <div className="text-sm text-gray-500">{result.product.sku} • {result.product.ean} • {result.product.brand}</div>
              <div className="text-lg font-bold mt-1">
                {formatCurrency(result.product.selling_price)}
                <span className="text-sm font-normal text-gray-500 ml-2">zakup {formatCurrency(result.product.purchase_price)}</span>
              </div>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3 text-sm">
            <div className="bg-gray-50 p-3 rounded-xl">
              <div className="text-xs text-gray-500">Stan całkowity</div>
              <div className="font-bold text-lg">{result.product.total_stock} {result.product.unit}</div>
            </div>
            <div className="bg-gray-50 p-3 rounded-xl">
              <div className="text-xs text-gray-500">Min / Cel</div>
              <div className="font-bold">{result.product.min_stock} / {result.product.target_stock}</div>
            </div>
          </div>
          {batches.length > 0 && (
            <div>
              <h4 className="font-semibold text-sm mb-2">Partie (FEFO)</h4>
              <div className="space-y-2">
                {batches.map((b: any) => (
                  <div key={b.id} className="flex justify-between text-sm p-2 bg-gray-50 rounded-xl">
                    <span>{b.batch_number} - {b.expiry_date || 'brak daty'}</span>
                    <span className="font-medium">{b.quantity_available} szt</span>
                  </div>
                ))}
              </div>
            </div>
          )}
          <div className="grid grid-cols-3 gap-2">
            <Link to="/deliveries" className="bg-green-600 text-white py-3 rounded-xl text-sm font-medium text-center">PRZYJMIJ</Link>
            <button className="bg-blue-600 text-white py-3 rounded-xl text-sm font-medium">PRZENIEŚ</button>
            <Link to="/sales" className="bg-orange-600 text-white py-3 rounded-xl text-sm font-medium text-center">SPRZEDAŻ</Link>
            <Link to="/waste" className="bg-red-600 text-white py-3 rounded-xl text-sm font-medium text-center">STRATA</Link>
            <Link to="/promotions" className="bg-purple-600 text-white py-3 rounded-xl text-sm font-medium text-center">PRZECENA</Link>
            <Link to={`/products/${result.product.id}`} className="bg-gray-200 text-gray-800 py-3 rounded-xl text-sm font-medium text-center">INFO</Link>
          </div>
        </div>
      )}

      {/* OPEN FOOD FACTS RESULT */}
      {result?.source === 'open_food_facts' && result.suggestion && (
        <div className="bg-white rounded-2xl border p-6 space-y-4">
          <div className="flex items-center gap-2 text-blue-600 font-semibold text-sm">
            <Globe className="w-4 h-4" /> Znaleziono w internecie (Open Facts: {result.suggestion.product_type || 'produkt'})
          </div>
          <div className="flex gap-4">
            {result.suggestion.image_url ? (
              <img src={result.suggestion.image_url} alt={result.suggestion.name} className="w-20 h-20 object-contain rounded-xl border bg-gray-50" />
            ) : (
              <div className="w-20 h-20 bg-gray-100 rounded-xl flex items-center justify-center text-gray-400 text-xs">Brak zdjęcia</div>
            )}
            <div className="flex-1">
              <div className="font-bold text-lg">{result.suggestion.name}</div>
              {result.suggestion.brand && <div className="text-sm text-gray-500">Marka: {result.suggestion.brand}</div>}
              {result.suggestion.quantity && <div className="text-sm text-gray-500">Ilość: {result.suggestion.quantity}</div>}
              <div className="text-xs text-gray-400 mt-1">EAN: {result.suggestion.ean}</div>
            </div>
          </div>
          {result.suggestion.ingredients && (
            <div className="bg-gray-50 rounded-xl p-3 text-xs text-gray-600">
              <div className="font-medium mb-1">Skład:</div>
              {result.suggestion.ingredients}
            </div>
          )}
          <div className="bg-blue-50 border border-blue-200 rounded-xl p-3 text-sm text-blue-800">
            Tego produktu nie ma jeszcze w bazie sklepu. Możesz go dodać jako nowy produkt — dane zostaną wstępnie uzupełnione.
          </div>
          <Link
            to={`/products/new?ean=${result.suggestion.ean}&name=${encodeURIComponent(result.suggestion.name)}&brand=${encodeURIComponent(result.suggestion.brand || '')}`}
            className="w-full bg-green-600 text-white py-3 rounded-xl font-medium flex items-center justify-center gap-2"
          >
            <Plus className="w-5 h-5" />
            Dodaj produkt do bazy sklepu
          </Link>
        </div>
      )}

      {/* NOT FOUND */}
      {result?.source === 'not_found' && (
        <div className="bg-white rounded-2xl border p-6 space-y-4">
          <div className="flex items-center gap-2 text-orange-600 font-semibold text-sm">
            <AlertCircle className="w-4 h-4" /> Produkt nieznany
          </div>
          <p className="text-gray-600 text-sm">
            Kod <span className="font-mono font-bold">{result.suggestion?.ean}</span> nie został znaleziony ani w bazie sklepu, ani w globalnych bazach Open Facts.
          </p>
          <Link
            to={`/products/new?ean=${result.suggestion?.ean}`}
            className="w-full bg-green-600 text-white py-3 rounded-xl font-medium flex items-center justify-center gap-2"
          >
            <Plus className="w-5 h-5" />
            Dodaj nowy produkt ręcznie
          </Link>
        </div>
      )}
    </div>
  )
}
