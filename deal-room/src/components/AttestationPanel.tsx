'use client'

import { useState } from 'react'
import { Lock, ChevronDown, ChevronUp, Copy, Check } from 'lucide-react'

interface Props {
  attestation: string
}

export default function AttestationPanel({ attestation }: Props) {
  const [open, setOpen] = useState(false)
  const [copied, setCopied] = useState(false)

  if (attestation.startsWith('SIMULATED') || attestation.startsWith('NOT_IN_CVM')) {
    return (
      <div className="border border-[var(--border)] rounded-lg bg-[var(--card)] px-4 py-3 flex items-center gap-2">
        <Lock className="w-4 h-4 text-amber-400" />
        <span className="text-xs text-amber-400">Simulator Mode — real TDX quote available on Phala CVM</span>
      </div>
    )
  }

  const clean = attestation.replace(/^0x/, '')
  const byteLen = clean.length / 2
  const version = parseInt(clean.slice(2, 4) + clean.slice(0, 2), 16)
  const teeType = parseInt(clean.slice(8, 10) + clean.slice(6, 8), 16)

  const copy = () => {
    navigator.clipboard.writeText(attestation)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="border border-[var(--border)] rounded-lg bg-[var(--card)] overflow-hidden glow">
      <button
        onClick={() => setOpen(!open)}
        className="w-full px-4 py-3 flex items-center justify-between hover:bg-white/5 transition-colors"
      >
        <div className="flex items-center gap-2">
          <Lock className="w-4 h-4 text-emerald-400" />
          <span className="text-sm font-medium">Cryptographic Attestation</span>
          <span className="text-xs px-2 py-0.5 rounded-full bg-emerald-400/10 text-emerald-400 border border-emerald-400/20">
            {teeType === 0x81 ? 'Intel TDX' : 'TEE'} v{version}
          </span>
        </div>
        {open ? <ChevronUp className="w-4 h-4 text-[var(--text-dim)]" /> : <ChevronDown className="w-4 h-4 text-[var(--text-dim)]" />}
      </button>

      {open && (
        <div className="px-4 pb-4 border-t border-[var(--border)]">
          <div className="mt-3 grid grid-cols-3 gap-2 text-xs mb-3">
            <div className="bg-black/40 rounded p-2 border border-[var(--border)]">
              <div className="text-[var(--text-dim)] mb-1">TEE Type</div>
              <div className="font-mono text-emerald-400">{teeType === 0x81 ? 'TDX' : `0x${teeType.toString(16)}`}</div>
            </div>
            <div className="bg-black/40 rounded p-2 border border-[var(--border)]">
              <div className="text-[var(--text-dim)] mb-1">Quote Size</div>
              <div className="font-mono">{byteLen.toLocaleString()} bytes</div>
            </div>
            <div className="bg-black/40 rounded p-2 border border-[var(--border)]">
              <div className="text-[var(--text-dim)] mb-1">Format</div>
              <div className="font-mono">DCAP</div>
            </div>
          </div>

          <div className="relative">
            <div className="bg-black/60 rounded border border-[var(--border)] p-3 font-mono text-xs text-[var(--text-dim)] break-all max-h-40 overflow-y-auto">
              {clean.slice(0, 128)}…{clean.slice(-64)}
            </div>
            <button
              onClick={copy}
              className="absolute top-2 right-2 p-1.5 rounded bg-[var(--card)] border border-[var(--border)] hover:border-emerald-400/50 transition-colors"
            >
              {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
            </button>
          </div>

          <div className="mt-3 flex gap-2">
            <a
              href="https://testnet.kitescan.ai/address/0xBB2835fC4d189340a98084A50DD0B36b4Ff50Ca2"
              target="_blank"
              className="text-xs px-3 py-1.5 rounded bg-emerald-400/10 text-emerald-400 border border-emerald-400/20 hover:bg-emerald-400/20 transition-colors"
            >
              View Contract
            </a>
          </div>
        </div>
      )}
    </div>
  )
}
