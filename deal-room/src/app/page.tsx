import TEEStatusBar from '@/components/TEEStatusBar'
import DealRoom from '@/components/DealRoom'

export default function Home() {
  return (
    <main className="min-h-screen bg-[var(--bg)] pt-16 pb-12 px-4">
      <TEEStatusBar />
      <DealRoom />

      <div className="max-w-2xl mx-auto mt-12 pt-6 border-t border-[var(--border)] text-center text-xs text-[var(--text-dim)] space-y-1">
        <p>Kite AI Global Hackathon 2026 • Novel Track</p>
        <p className="font-mono">ConfidentialEscrow: 0xBB28…Ca2 • CVM: Phala TDX</p>
      </div>
    </main>
  )
}
