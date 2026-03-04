import { type ClassValue, clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function riskColor(value: number): string {
  if (value < 0.4) return 'text-green-400'
  if (value < 0.7) return 'text-yellow-400'
  return 'text-red-400'
}

export function riskBg(value: number): string {
  if (value < 0.4) return 'bg-green-500'
  if (value < 0.7) return 'bg-yellow-500'
  return 'bg-red-500'
}

export function formatTs(ts: string): string {
  try {
    return new Date(ts).toLocaleString()
  } catch {
    return ts
  }
}

export function shortId(id: string): string {
  return id.split('-')[0] ?? id.slice(0, 8)
}
