'use client'

import { Bot, ArrowRight, CheckCircle } from 'lucide-react'

interface Round {
  round: number
  side: 'buyer' | 'seller'
  price: string
  isFinal?: boolean
}

interface Props {
  rounds: Round[]
  status: string
  agreedPrice?: string
}

export default function NegotiationLog({ rounds, status, agreedPrice }: Props) {
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between text-xs text-[var(--text-dim)] uppercase tracking-wider mb-2">
        <span>Negotiation Transcript</span>
        <span className="font-mono">{status === 'matched' ? 'SEALED & MATCHED' : status.toUpperCase()}</span>
      </div>

      <div className="space-y-2">
        {rounds.map((r, i) => (
          <div
            key={i}
            className={`flex items-center gap-3 p-3 rounded-lg border transition-all duration-500 ${
              r.isFinal
                ? 'bg-emerald-400/5 border-emerald-400/30'
                : 'bg-[var(--card)] border-[var(--border)]'
            }`}
            style={{ animationDelay: `${i * 200}ms` }}
          >
            <div className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 ${
              r.side === 'buyer' ? 'bg-blue-400/10 text-blue-400' : 'bg-amber-400/10 text-amber-400'
            }`}>
              <Bot className="w-4 h-4" />
            </div>

            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 text-sm">
                <span className={r.side === 'buyer' ? 'text-blue-400' : 'text-amber-400'}>
                  {r.side === 'buyer' ? 'Buyer Agent' : 'Seller Agent'}
                </span>
                <ArrowRight className="w-3 h-3 text-[var(--text-dim)]" />
                <span className="font-mono font-medium">{r.price}</span>
              </div>
              <div className="text-xs text-[var(--text-dim)] mt-0.5">Round {r.round}</div>
            </div>

            {r.isFinal && <CheckCircle className="w-5 h-5 text-emerald-400 shrink-0" />}
          </div>
        ))}
      </div>

      {status === 'matched' && agreedPrice && (
        <div className="mt-4 p-4 rounded-lg bg-emerald-400/5 border border-emerald-400/20 text-center">
          <div className="text-xs text-emerald-400 uppercase tracking-wider mb-1">Final Agreement</div>
          <div className="text-2xl font-mono font-bold text-emerald-400">${agreedPrice}</div>
          <div className="text-xs text-[var(--text-dim)] mt-1">per unit • 10 units total</div>
        </div>
      )}
    </div>
  )
}
