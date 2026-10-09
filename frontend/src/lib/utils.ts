import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"
import { getLocale } from './i18n'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function formatCurrency(value: number | string, currency = 'PLN') {
  const num = typeof value === 'string' ? parseFloat(value) : value
  return new Intl.NumberFormat(getLocale(), { style: 'currency', currency }).format(num)
}

export function formatDate(date: string | Date | null | undefined) {
  if (!date) return '-'
  const d = typeof date === 'string' ? new Date(date) : date
  return new Intl.DateTimeFormat(getLocale()).format(d)
}

export function formatDateTime(date: string | Date | null | undefined) {
  if (!date) return '-'
  const d = typeof date === 'string' ? new Date(date) : date
  return new Intl.DateTimeFormat(getLocale(), { dateStyle: 'short', timeStyle: 'short' }).format(d)
}

export function daysUntil(date: string | Date | null) {
  if (!date) return null
  const d = typeof date === 'string' ? new Date(date) : date
  const today = new Date()
  today.setHours(0,0,0,0)
  d.setHours(0,0,0,0)
  const diff = Math.ceil((d.getTime() - today.getTime()) / (1000 * 60 * 60 * 24))
  return diff
}

export function getExpiryColor(days: number | null) {
  if (days === null) return 'text-gray-500 bg-gray-50'
  if (days < 0) return 'text-red-700 bg-red-50 border-red-200'
  if (days === 0) return 'text-red-600 bg-red-50 border-red-200'
  if (days <= 1) return 'text-orange-700 bg-orange-50 border-orange-200'
  if (days <= 3) return 'text-amber-700 bg-amber-50 border-amber-200'
  if (days <= 7) return 'text-yellow-700 bg-yellow-50 border-yellow-200'
  return 'text-green-700 bg-green-50 border-green-200'
}
