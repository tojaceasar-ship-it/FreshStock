import { api } from './api'

const DEVICE_KEY = 'freshstock.scanner.device.v1'

export function scannerDeviceId() {
  let id = localStorage.getItem(DEVICE_KEY)
  if (!id) {
    id = globalThis.crypto?.randomUUID?.() || `device-${Date.now()}-${Math.random().toString(36).slice(2)}`
    localStorage.setItem(DEVICE_KEY, id)
  }
  return id
}

export function scannerPlatform() {
  const value = navigator.userAgent
  if (/android/i.test(value)) return 'android'
  if (/iphone|ipad|ipod/i.test(value)) return 'ios'
  if (/windows/i.test(value)) return 'windows'
  if (/macintosh|mac os/i.test(value)) return 'macos'
  return 'other'
}

export function scanSignal(success = true) {
  try {
    navigator.vibrate?.(success ? 80 : [50, 40, 50])
    const AudioContextClass = window.AudioContext || (window as any).webkitAudioContext
    if (!AudioContextClass) return
    const context = new AudioContextClass()
    const oscillator = context.createOscillator()
    const gain = context.createGain()
    oscillator.type = 'sine'
    oscillator.frequency.value = success ? 880 : 220
    gain.gain.setValueAtTime(0.08, context.currentTime)
    gain.gain.exponentialRampToValueAtTime(0.001, context.currentTime + 0.12)
    oscillator.connect(gain); gain.connect(context.destination)
    oscillator.start(); oscillator.stop(context.currentTime + 0.12)
    oscillator.onended = () => context.close().catch(() => {})
  } catch { /* feedback is best-effort */ }
}

export function reportScanEvent(payload: {
  context: 'product' | 'inventory'
  outcome: 'accepted' | 'rejected' | 'not_found' | 'error'
  barcode_format?: string
  code_length?: number
  duration_ms?: number
  error_reason?: string
}) {
  api.post('/scanner/events', {
    ...payload,
    device_id: scannerDeviceId(),
    platform: scannerPlatform(),
  }).catch(() => {})
}
