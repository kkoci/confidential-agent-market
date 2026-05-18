'use client'

import { useEffect, useState } from 'react'
import { Shield, Activity } from 'lucide-react'

const CVM_URL = process.env.NEXT_PUBLIC_CVM_URL ?? ''

export default function TEEStatusBar() {
  const [status, setStatus] = useState<'checking' | 'online' | 'offline'>('checking')

  useEffect(() => {
    const check = async () => {
      try {
        const res = await fetch(`${CVM_URL}/health`, { method: 'GET' })
        setStatus(res.ok ? 'online' : 'offline')
      } catch {
        setStatus('offline')
      }
    }
    check()
    const iv = setInterval(check, 10000)
    return () => clearInterval(iv)
  }, [])

  return (
    <div className="fixed top-0 left-0 right-0 z-50 border-b border-[var(--border)] bg-[var(--card)]/80 backdrop-blur-md">
      <div className="max-w-6xl mx-auto px-4 h-12 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Shield className="w-4 h-4 text-emerald-400" />
          <span className="text-sm font-medium text-emerald-400">TDX SECURE</span>
          <span className="text-xs text-[var(--text-dim)] hidden sm:inline">Intel TDX v4 • Phala CVM</span>
        </div>

        <div className="flex items-center gap-3 text-xs">
          <div className="flex items-center gap-1.5">
            <Activity className="w-3.5 h-3.5" />
            <span className="text-[var(--text-dim)]">CVM:</span>
            <span className="font-mono text-[var(--text-dim)]">{CVM_URL ? CVM_URL.split('-')[0].split('//')[1].slice(0, 8) + '…' : 'not set'}</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className={`w-2 h-2 rounded-full ${status === 'online' ? 'bg-emerald-400 pulse-dot' : status === 'checking' ? 'bg-amber-400' : 'bg-red-400'}`} />
            <span className={status === 'online' ? 'text-emerald-400' : status === 'checking' ? 'text-amber-400' : 'text-red-400'}>
              {status === 'online' ? 'LIVE' : status === 'checking' ? '…' : 'DOWN'}
            </span>
          </div>
        </div>
      </div>
    </div>
  )
}
