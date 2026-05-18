# Confidential Agent Negotiation Market

**Kite AI Global Hackathon 2026 | Novel Track | FeelTech Ltd**

A decentralised OTC market where AI agents negotiate trade terms inside a Trusted Execution Environment (Intel TDX via Phala Cloud). Negotiation terms stay sealed until atomic on-chain settlement — no frontrunning, no MEV, no intent leakage.

---

## How It Works

```
Browser (deal-room FE)
        │  clicks "Start Sealed Negotiation"
        ▼
FastAPI Backend (Phala Cloud CVM — Intel TDX)
  POST /market/bid     $0.01 Test USDT (x402 gokite-aa)
  POST /market/ask     $0.01 Test USDT (x402 gokite-aa)
  POST /market/settle  $0.05 Test USDT (x402 gokite-aa)
        │
        ▼
Negotiation Engine (inside the TEE)
  Buyer Agent (Claude Haiku) ←→ max 5 rounds ←→ Seller Agent (Claude Haiku)
  Terms encrypted at rest — DCAP attestation on match
        │
        ▼
ConfidentialEscrow.sol (Kite Testnet, chain 2368)
  settle(escrowId, attestation) → release KXUSD → emit EscrowSettled
```

The backend runs **inside a Phala Cloud CVM** (Confidential Virtual Machine). Every settlement produces a DCAP TDX quote that proves the negotiation happened inside a genuine Intel TDX enclave — verifiable on-chain without trusting any intermediary.

---

## Repository Structure

```
confidential-agent-market/
├── api/                         ← Python backend (FastAPI)
│   ├── main.py                  ← app entry point, CORS, 402 handler
│   ├── config.py                ← all env vars with documented defaults
│   ├── routes/
│   │   ├── market.py            ← POST /market/bid, /ask, /settle  GET /market/status
│   │   └── health.py            ← GET /health (free, no payment)
│   ├── services/
│   │   ├── payment.py           ← gokite-aa x402 flow (Pieverse facilitator)
│   │   ├── negotiation.py       ← Claude Haiku negotiation loop + simulator fallback
│   │   ├── tee.py               ← Phala CVM DCAP attestation (dstack-sdk + HTTP fallback)
│   │   └── escrow.py            ← web3.py async client for ConfidentialEscrow.sol
│   └── models/
│       ├── order.py             ← Order, OrderResponse (Pydantic v2)
│       └── settlement.py        ← SettleRequest, SettlementResult
├── deal-room/                   ← Next.js 14 frontend (static export → Vercel)
│   ├── src/
│   │   ├── app/                 ← App Router: layout.tsx + page.tsx
│   │   ├── components/
│   │   │   ├── DealRoom.tsx     ← main component — orchestrates the full flow
│   │   │   ├── TEEStatusBar.tsx ← top banner polling Phala CVM /health every 10s
│   │   │   ├── NegotiationLog.tsx   ← animated round-by-round transcript
│   │   │   ├── AttestationPanel.tsx ← collapsible DCAP quote viewer (parse + copy)
│   │   │   └── SettlementCard.tsx   ← on-chain tx confirmation + KiteScan link
│   │   └── lib/
│   │       ├── kite.ts          ← viem public client for Kite Testnet (chain 2368)
│   │       └── escrow.ts        ← read ConfidentialEscrow state via viem
│   ├── .env.example             ← copy to .env.local and fill in values
│   ├── package.json             ← Next 14, Tailwind, lucide-react, viem
│   └── next.config.js           ← output: 'export' → dist/
├── agents/                      ← standalone agent scripts
├── contracts/                   ← ConfidentialEscrow.sol
├── tests/
└── .env.example                 ← backend env template
```

---

## Backend

### What it does

- Exposes four paid HTTP endpoints using Kite's `gokite-aa` x402 payment scheme
- On `/market/settle`, spins up two Claude Haiku agents that negotiate in up to 5 rounds inside the TEE
- Gets a DCAP TDX attestation quote from the Phala guest agent (dstack-sdk, falls back to HTTP, falls back to a clearly-marked mock outside CVM)
- If `ESCROW_CONTRACT_ADDRESS` and `AGENT_PRIVATE_KEY` are set, calls `ConfidentialEscrow.settle()` on Kite testnet via web3.py and returns the tx hash
- Falls back to a deterministic simulator when `ANTHROPIC_API_KEY` is absent (useful for local testing)

### Run locally

```bash
pip install -r requirements.txt
cp .env.example .env          # edit as needed
```

Minimum for local dev — skip all payments and use the simulator:

```bash
SKIP_PAYMENT_CHECK=true uvicorn api.main:app --reload
```

Swagger docs at `http://localhost:8000/docs`.

### Run with real agents (no payments)

```bash
ANTHROPIC_API_KEY=sk-ant-... SKIP_PAYMENT_CHECK=true uvicorn api.main:app --reload
```

### Full live testnet flow

```bash
ANTHROPIC_API_KEY=sk-ant-... \
PAY_TO_ADDRESS=0xYourWallet \
AGENT_PRIVATE_KEY=0x... \
ESCROW_CONTRACT_ADDRESS=0xBB2835fC4d189340a98084A50DD0B36b4Ff50Ca2 \
uvicorn api.main:app --reload
```

### Deploy to Phala Cloud (production)

The backend is containerised and runs on Phala Cloud CVM for TEE attestation. Build and push the Docker image, then deploy via the Phala dashboard or CLI. The CVM endpoint URL takes the form:

```
https://<hash>-8000.dstack-pha-prod5.phala.network
```

This URL goes into the frontend's `NEXT_PUBLIC_CVM_URL`.

### Backend environment variables

| Variable | Default | Notes |
|---|---|---|
| `ANTHROPIC_API_KEY` | *(none)* | Omit → deterministic simulator |
| `AGENT_MODEL` | `claude-haiku-4-5-20251001` | Swap to `claude-sonnet-4-6` for final demo |
| `PAY_TO_ADDRESS` | `0x4812fC...ab20` | Funded testnet wallet — safe default |
| `FACILITATOR_URL` | `https://facilitator.pieverse.io` | Pieverse, not x402.org |
| `SKIP_PAYMENT_CHECK` | `false` | `true` to bypass 402 locally |
| `KITE_RPC_URL` | `https://rpc-testnet.gokite.ai/` | |
| `KITE_CHAIN_ID` | `2368` | 2366 for mainnet |
| `TESTNET_ASSET` | `0x0fF539...63` | KXUSD (18 decimals) — not USDC.e |
| `ESCROW_CONTRACT_ADDRESS` | *(empty)* | Deploy contract first; omit to skip on-chain settle |
| `AGENT_PRIVATE_KEY` | *(none)* | Testnet only — never commit |
| `PHALA_CVM_ENDPOINT` | *(empty)* | HTTP fallback for tappd; not needed inside CVM |

---

## Frontend (deal-room)

### What it does

A dark-themed Next.js 14 app that demos the full deal flow in a browser:

1. **TEE Status Bar** — polls Phala CVM `/health` every 10 seconds; shows LIVE / DOWN
2. **Start Sealed Negotiation** — places a buy bid (WKITE @ 1.00) and sell ask (WKITE @ 0.95) simultaneously via the CVM API
3. **Negotiation Log** — animates intermediate rounds while the TEE negotiates; shows the final agreed price from the API response
4. **Attestation Panel** — collapsible panel showing the raw DCAP TDX quote with parsed TEE type, quote size, and copy-to-clipboard
5. **Settlement Card** — if the API returns a `tx_hash`, shows the on-chain confirmation with a KiteScan link

### Run locally

```bash
cd deal-room
cp .env.example .env.local    # add your NEXT_PUBLIC_CVM_URL
npm install
npm run dev
```

Open `http://localhost:3000`.

### Deploy to Vercel

**1. Set the env var on Vercel:**

```bash
cd deal-room
vercel env add NEXT_PUBLIC_CVM_URL production
# paste your Phala CVM URL when prompted
```

Optionally override the demo wallet:

```bash
vercel env add NEXT_PUBLIC_WALLET_ADDRESS production
```

**2. Deploy:**

```bash
vercel --prod
```

The app is a static export (`output: 'export'` in `next.config.js`) so it deploys as a CDN-served bundle with no serverless functions. All API calls go directly from the browser to the Phala CVM URL — CORS is already enabled on the backend (`api/main.py` v0.1.7).

**When the Phala CVM URL changes** (new deployment), update the env var on Vercel and redeploy — `NEXT_PUBLIC_*` vars are baked in at build time.

### Frontend environment variables

| Variable | Default | Notes |
|---|---|---|
| `NEXT_PUBLIC_CVM_URL` | *(empty)* | Full Phala CVM URL — required for the app to work |
| `NEXT_PUBLIC_WALLET_ADDRESS` | `0x4812fC...ab20` | Demo wallet used as buyer/seller address |

---

## x402 Payment Flow (gokite-aa)

Kite uses its own x402 scheme — **not** the Coinbase `exact` scheme.

```
1. Client calls endpoint with no X-PAYMENT header
2. Service returns HTTP 402 with gokite-aa payment details
3. Client constructs X-PAYMENT header (base64-encoded JSON with EIP-3009 authorization + signature)
4. Client retries with X-PAYMENT header
5. Service calls POST https://facilitator.pieverse.io/v2/settle
6. Facilitator executes transferWithAuthorization on-chain
7. Service delivers response
```

| Endpoint | Cost (wei) | USD equiv |
|---|---|---|
| `POST /market/bid` | `10000000000000000` | ~$0.01 |
| `POST /market/ask` | `10000000000000000` | ~$0.01 |
| `GET /market/status` | `1000000000000000` | ~$0.001 |
| `POST /market/settle` | `50000000000000000` | ~$0.05 |

---

## Kite Network

| Network | RPC | Chain ID | Explorer |
|---|---|---|---|
| Testnet | `https://rpc-testnet.gokite.ai/` | 2368 | `https://testnet.kitescan.ai/` |
| Mainnet | `https://rpc.gokite.ai/` | 2366 | `https://kitescan.ai/` |
| Faucet | `https://faucet.gokite.ai` | — | — |

**Deployed contracts:**
- ConfidentialEscrow: `0xBB2835fC4d189340a98084A50DD0B36b4Ff50Ca2` (Kite testnet)
- KXUSD (Test USDT): `0x1b7425d288ea676FCBc65c29711fccF0B6D5c293`
- Pieverse facilitator: `0x12343e649e6b2b2b77649DFAb88f103c02F3C78b`

---

## Status

### Backend (v0.1.7)
- [x] FastAPI + x402 `gokite-aa` payment flow (Pieverse facilitator)
- [x] Claude Haiku negotiation loop + deterministic simulator fallback
- [x] DCAP attestation via Phala CVM (`tee.py` — dstack-sdk + HTTP fallback)
- [x] `ConfidentialEscrow.sol` client via web3.py (`escrow.py`)
- [x] CORS enabled for Vercel frontend
- [x] Deployed on Phala Cloud TDX

### Frontend (deal-room)
- [x] Next.js 14 static export — Tailwind, lucide-react, viem
- [x] TEE status bar with live CVM health polling
- [x] Animated negotiation transcript
- [x] DCAP attestation panel (quote parsing, copy-to-clipboard)
- [x] On-chain settlement card with KiteScan link
- [x] All hardcoded values extracted to env vars / derived constants

### Remaining
- [ ] Swap `AGENT_MODEL` to `claude-sonnet-4-6` for final demo
- [ ] Full funded escrow end-to-end: deposit → negotiate → DCAP attest → on-chain release
