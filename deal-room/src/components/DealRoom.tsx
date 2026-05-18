'use client'

import { useState, useCallback } from 'react'
import { Play, RotateCcw, Loader2, AlertTriangle } from 'lucide-react'
import NegotiationLog from './NegotiationLog'
import AttestationPanel from './AttestationPanel'
import SettlementCard from './SettlementCard'

const CVM_URL = process.env.NEXT_PUBLIC_CVM_URL ?? ''
const WALLET = process.env.NEXT_PUBLIC_WALLET_ADDRESS ?? '0x4812fC05e79ddc616346d10A8826B2bdf5e6ab20'

const ASSET = 'WKITE'
const BID_PRICE = 1.00   // buyer's max
const ASK_PRICE = 0.95   // seller's floor
const QUANTITY = '10'
const SPREAD = BID_PRICE - ASK_PRICE

type Phase = 'idle' | 'placing' | 'negotiating' | 'complete' | 'error'

interface DealResult {
  status: string
  rounds: number
  agreed_price: string
  attestation: string
  tx_hash?: string
  gasUsed?: number
  blockNumber?: number
}

export default function DealRoom() {
  const [phase, setPhase] = useState<Phase>('idle')
  const [error, setError] = useState<string>('')
  const [result, setResult] = useState<DealResult | null>(null)
  const [simulatedRounds, setSimulatedRounds] = useState<Array<{round: number, side: 'buyer' | 'seller', price: string, isFinal?: boolean}>>([])

  const sleep = (ms: number) => new Promise(r => setTimeout(r, ms))

  const runDeal = useCallback(async () => {
    setPhase('placing')
    setError('')
    setResult(null)
    setSimulatedRounds([])

    try {
      const [bidRes, askRes] = await Promise.all([
        fetch(`${CVM_URL}/market/bid`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ asset: ASSET, price: BID_PRICE.toFixed(2), quantity: QUANTITY, side: 'buy' }),
        }),
        fetch(`${CVM_URL}/market/ask`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ asset: ASSET, price: ASK_PRICE.toFixed(2), quantity: QUANTITY, side: 'sell' }),
        }),
      ])

      if (!bidRes.ok || !askRes.ok) throw new Error('Failed to place orders')

      const bid = await bidRes.json()
      const ask = await askRes.json()

      setPhase('negotiating')

      const fakeRounds = [
        { round: 1, side: 'buyer' as const, price: `$${(BID_PRICE - SPREAD * 0.4).toFixed(4)}` },
        { round: 2, side: 'seller' as const, price: `$${(ASK_PRICE - SPREAD * 0.2).toFixed(4)}` },
      ]

      for (const r of fakeRounds) {
        setSimulatedRounds(prev => [...prev, r])
        await sleep(1200)
      }

      const settleRes = await fetch(`${CVM_URL}/market/settle`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          bid_id: bid.order_id,
          ask_id: ask.order_id,
          buyer_address: WALLET,
          seller_address: WALLET,
        }),
      })

      if (!settleRes.ok) throw new Error('Settlement failed')
      const data = await settleRes.json()

      const finalRound = {
        round: data.rounds,
        side: 'buyer' as const,
        price: `$${data.agreed_price}`,
        isFinal: true,
      }
      setSimulatedRounds(prev => [...prev, finalRound])

      setResult({
        status: data.status,
        rounds: data.rounds,
        agreed_price: data.agreed_price,
        attestation: data.attestation,
        tx_hash: data.tx_hash,
      })

      setPhase('complete')
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Unknown error')
      setPhase('error')
    }
  }, [])

  return (
    <div className="max-w-2xl mx-auto">
      <div className="text-center mb-8">
        <h1 className="text-3xl font-bold mb-2 tracking-tight">Confidential Deal Room</h1>
        <p className="text-sm text-[var(--text-dim)] max-w-md mx-auto">
          Two AI agents negotiate inside an Intel TDX enclave.
          The negotiation is sealed. The proof is cryptographic.
          The settlement is on-chain.
        </p>
      </div>

      {phase === 'idle' && (
        <button
          onClick={runDeal}
          className="w-full py-4 rounded-lg bg-emerald-500 hover:bg-emerald-400 text-black font-semibold text-lg transition-all hover:scale-[1.02] active:scale-[0.98] flex items-center justify-center gap-2"
        >
          <Play className="w-5 h-5" />
          Start Sealed Negotiation
        </button>
      )}

      {phase === 'error' && (
        <div className="mb-6 p-4 rounded-lg bg-red-400/10 border border-red-400/20 text-red-400 text-sm flex items-start gap-2">
          <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
          <div>
            <div className="font-medium mb-1">Deal Failed</div>
            <div className="font-mono text-xs opacity-80">{error}</div>
            <button
              onClick={() => setPhase('idle')}
              className="mt-3 text-xs underline hover:no-underline"
            >
              Try Again
            </button>
          </div>
        </div>
      )}

      {(phase === 'placing' || phase === 'negotiating') && (
        <div className="w-full py-6 rounded-lg bg-[var(--card)] border border-[var(--border)] flex flex-col items-center justify-center gap-3">
          <Loader2 className="w-6 h-6 text-emerald-400 animate-spin" />
          <div className="text-sm font-medium">
            {phase === 'placing' ? 'Placing sealed orders…' : 'Agents negotiating inside TEE…'}
          </div>
          <div className="text-xs text-[var(--text-dim)] font-mono">
            {phase === 'negotiating' ? 'Intel TDX • Phala CVM • Claude Haiku' : 'x402 payment check • Order validation'}
          </div>
        </div>
      )}

      {phase === 'complete' && result && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <span className="text-xs text-[var(--text-dim)] uppercase tracking-wider">Deal Complete</span>
            <button
              onClick={() => setPhase('idle')}
              className="text-xs flex items-center gap-1 text-emerald-400 hover:text-emerald-300 transition-colors"
            >
              <RotateCcw className="w-3 h-3" />
              New Deal
            </button>
          </div>

          <NegotiationLog
            rounds={simulatedRounds}
            status={result.status}
            agreedPrice={result.agreed_price}
          />

          <AttestationPanel attestation={result.attestation} />

          {result.tx_hash && (
            <SettlementCard
              txHash={result.tx_hash}
              gasUsed={result.gasUsed}
              blockNumber={result.blockNumber}
            />
          )}

          {!result.tx_hash && (
            <div className="p-3 rounded border border-amber-400/20 bg-amber-400/5 text-xs text-amber-400 text-center">
              Running in simulator mode — add ANTHROPIC_API_KEY + ESCROW_CONTRACT_ADDRESS + AGENT_PRIVATE_KEY to docker run for full on-chain settlement
            </div>
          )}
        </div>
      )}
    </div>
  )
}
