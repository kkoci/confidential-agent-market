'use client'

import { ExternalLink, CheckCircle, Fuel } from 'lucide-react'

interface Props {
  txHash: string
  gasUsed?: number
  blockNumber?: number
}

export default function SettlementCard({ txHash, gasUsed, blockNumber }: Props) {
  return (
    <div className="border border-emerald-400/20 rounded-lg bg-emerald-400/5 p-4">
      <div className="flex items-center gap-2 mb-3">
        <CheckCircle className="w-5 h-5 text-emerald-400" />
        <span className="text-sm font-medium text-emerald-400">On-Chain Settlement Confirmed</span>
      </div>

      <div className="space-y-2 text-xs">
        <div className="flex items-center justify-between">
          <span className="text-[var(--text-dim)]">Transaction</span>
          <a
            href={`https://testnet.kitescan.ai/tx/${txHash}`}
            target="_blank"
            className="font-mono text-emerald-400 hover:underline flex items-center gap-1"
          >
            {txHash.slice(0, 14)}…{txHash.slice(-12)}
            <ExternalLink className="w-3 h-3" />
          </a>
        </div>

        {gasUsed && (
          <div className="flex items-center justify-between">
            <span className="text-[var(--text-dim)] flex items-center gap-1">
              <Fuel className="w-3 h-3" /> Gas Used
            </span>
            <span className="font-mono">{gasUsed.toLocaleString()}</span>
          </div>
        )}

        {blockNumber && (
          <div className="flex items-center justify-between">
            <span className="text-[var(--text-dim)]">Block</span>
            <span className="font-mono">{blockNumber.toLocaleString()}</span>
          </div>
        )}

        <div className="flex items-center justify-between">
          <span className="text-[var(--text-dim)]">Contract</span>
          <span className="font-mono text-[var(--text-dim)]">0xBB28…Ca2</span>
        </div>
      </div>
    </div>
  )
}
