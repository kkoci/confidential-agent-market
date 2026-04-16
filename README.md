# Confidential Agent Negotiation Market

**Kite AI Global Hackathon 2026 | Novel Track | FeelTech Ltd**

A decentralised OTC market where AI agents negotiate trade terms inside a Trusted Execution Environment (Intel TDX via Phala Cloud). Negotiation terms stay sealed until atomic on-chain settlement — no frontrunning, no MEV, no intent leakage.

---

## Architecture

```
Buyer Agent (Claude Haiku)
        │  x402 payment (gokite-aa / Kite testnet)
        ▼
FastAPI Service  ──────────────────────────────────────
  POST /market/bid     $0.01 Test USDT
  POST /market/ask     $0.01 Test USDT
  GET  /market/status  $0.001 Test USDT
  POST /market/settle  $0.05 Test USDT
        │
        ▼
TEE Negotiation Engine (Phala Cloud TDX)        ← Phase 2
  Buyer Agent  ←→ negotiation loop ←→ Seller Agent
  max 5 rounds — terms encrypted at rest
  DCAP attestation on match
        │
        ▼
ConfidentialEscrow.sol (Kite Chain)             ← Phase 2
  verifyAttestation() → release funds → emit Settlement
```

---

## Project Structure

```
confidential-agent-market/
├── api/
│   ├── main.py                  ← FastAPI app + 402 exception handler
│   ├── config.py                ← all env vars with documented defaults
│   ├── routes/
│   │   ├── market.py            ← /market/bid, /ask, /status, /settle
│   │   └── health.py            ← GET /health (no payment)
│   ├── services/
│   │   ├── payment.py           ← gokite-aa 402 flow (Pieverse facilitator)
│   │   └── negotiation.py       ← agent negotiation loop + simulator fallback
│   └── models/
│       ├── order.py             ← Order, OrderResponse (Pydantic v2)
│       └── settlement.py        ← SettleRequest, SettlementResult
├── agents/                      ← Phase 2: standalone agent scripts
├── contracts/                   ← Phase 2: ConfidentialEscrow.sol
├── tests/
├── .env.example
├── CLAUDE.md
└── KITE_X402_PATCH.md
```

---

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env`. At minimum for local dev set `SKIP_PAYMENT_CHECK=true` (see Fallbacks below).

### 3. Run

```bash
uvicorn api.main:app --reload
```

Docs at `http://localhost:8000/docs`.

---

## Environment Variables

| Variable | Default | Required | Notes |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | *(none)* | No | Omit to use negotiation simulator |
| `AGENT_MODEL` | `claude-haiku-4-5-20251001` | No | Swap to `claude-sonnet-4-6` for demo |
| `PAY_TO_ADDRESS` | `0x46D636...8868` | No | Funded testnet wallet — safe default |
| `FACILITATOR_URL` | `https://facilitator.pieverse.io` | No | Pieverse, not x402.org |
| `SKIP_PAYMENT_CHECK` | `false` | No | Set `true` to bypass 402 locally |
| `KITE_RPC_URL` | `https://rpc-testnet.gokite.ai/` | No | |
| `KITE_CHAIN_ID` | `2368` | No | 2366 for mainnet |
| `TESTNET_ASSET` | `0x0fF539...63` | No | Test USDT — not USDC.e |
| `ESCROW_CONTRACT_ADDRESS` | *(empty)* | Phase 2 | Deploy contract first |
| `PHALA_API_KEY` | *(empty)* | Phase 2 | |
| `PHALA_CVM_ENDPOINT` | *(empty)* | Phase 2 | |
| `AGENT_PRIVATE_KEY` | *(none)* | Phase 2 | Testnet only — never commit |

---

## Fallbacks

### No `ANTHROPIC_API_KEY`

The negotiation engine falls back to a **deterministic simulator**:

- If buyer max price ≥ seller floor price → returns `status: matched` at the midpoint price
- Otherwise → returns `status: no_match`
- `attestation` field reads `"SIMULATED_NO_API_KEY"` so it's visible in every response

This lets you test the full HTTP/payment flow without spending API credits.

### No `PAY_TO_ADDRESS`

Defaults to the pre-funded Kite testnet wallet from `KITE_X402_PATCH.md`:
`0x4812fC05e79ddc616346d10A8826B2bdf5e6ab20`

Payment verification still fires normally. Set your own address before mainnet.

### `SKIP_PAYMENT_CHECK=true`

Bypasses the `X-PAYMENT` header check and Pieverse settlement call entirely. All endpoints return 200 with no payment required. Use this for local development and route testing.

---

## Payment Flow (gokite-aa scheme)

Kite uses its own x402 scheme — **not** the Coinbase `exact` scheme. The Coinbase `x402[fastapi]` PyPI middleware does not work here.

```
1. Agent calls endpoint with no X-PAYMENT header
2. Service returns HTTP 402:
   {
     "error": "X-PAYMENT header is required",
     "accepts": [{
       "scheme": "gokite-aa",
       "network": "kite-testnet",
       "maxAmountRequired": "10000000000000000",
       "payTo": "0x46D636...8868",
       "asset": "0x0fF539...63",   ← Test USDT (18 decimals)
       ...
     }],
     "x402Version": 1
   }
3. Agent constructs X-PAYMENT header (base64-encoded JSON):
   { "authorization": {...}, "signature": "0x..." }
4. Agent retries request with X-PAYMENT header
5. Service calls POST https://facilitator.pieverse.io/v2/settle
6. Facilitator executes transferWithAuthorization on-chain to payTo
7. Service delivers response
```

Token amounts use 18 decimals (Test USDT):

| Endpoint | Amount (wei) | USD equiv |
|---|---|---|
| `POST /market/bid` | `10000000000000000` | ~$0.01 |
| `POST /market/ask` | `10000000000000000` | ~$0.01 |
| `GET /market/status` | `1000000000000000` | ~$0.001 |
| `POST /market/settle` | `50000000000000000` | ~$0.05 |

---

## Testing

### Option A — Full bypass (no wallet, no API key)

```bash
SKIP_PAYMENT_CHECK=true uvicorn api.main:app --reload
```

Test all endpoints directly:

```bash
# Health (always free)
curl http://localhost:8000/health

# Submit a bid
curl -X POST http://localhost:8000/market/bid \
  -H "Content-Type: application/json" \
  -d '{"asset":"WKITE","price":"0.95","quantity":"100","side":"buy"}'

# Submit an ask
curl -X POST http://localhost:8000/market/ask \
  -H "Content-Type: application/json" \
  -d '{"asset":"WKITE","price":"1.00","quantity":"100","side":"sell"}'

# Check book depth
curl http://localhost:8000/market/status

# Trigger settlement (replace IDs with values from bid/ask responses)
curl -X POST http://localhost:8000/market/settle \
  -H "Content-Type: application/json" \
  -d '{
    "bid_id": "<bid_order_id>",
    "ask_id": "<ask_order_id>",
    "buyer_address": "0xBuyer...",
    "seller_address": "0xSeller..."
  }'
```

### Option B — Test 402 fires correctly (payment required)

```bash
uvicorn api.main:app --reload  # SKIP_PAYMENT_CHECK not set
curl -X POST http://localhost:8000/market/bid \
  -H "Content-Type: application/json" \
  -d '{"asset":"WKITE","price":"0.95","quantity":"100","side":"buy"}'
# → HTTP 402 with gokite-aa payment details
```

### Option C — Live agents, payment bypassed

```bash
ANTHROPIC_API_KEY=sk-ant-... SKIP_PAYMENT_CHECK=true uvicorn api.main:app --reload
```

Then hit `/market/settle` — negotiation runs against real Claude Haiku. Watch the `rounds` and `attestation` fields in the response.

### Option D — Full live flow (testnet)

Requires:
- Wallet funded with Test USDT from `https://faucet.gokite.ai`
- `AGENT_PRIVATE_KEY` set
- Kite-compatible x402 client (see `https://github.com/gokite-ai/x402`)

```bash
ANTHROPIC_API_KEY=sk-ant-... \
PAY_TO_ADDRESS=0xYourWallet \
AGENT_PRIVATE_KEY=0x... \
uvicorn api.main:app --reload
```

---

## Reference 402 Response

Mirrors the Kite reference implementation at `https://x402.dev.gokite.ai/api/weather?location=London`:

```json
{
  "error": "X-PAYMENT header is required",
  "accepts": [{
    "scheme": "gokite-aa",
    "network": "kite-testnet",
    "maxAmountRequired": "10000000000000000",
    "resource": "http://localhost:8000/market/bid",
    "description": "Confidential Agent Market — submit buy bid",
    "mimeType": "application/json",
    "payTo": "0x4812fC05e79ddc616346d10A8826B2bdf5e6ab20",
    "maxTimeoutSeconds": 300,
    "asset": "0x8794c866DB97E0E7c1a0E2CF51D3E1460cB37F9e",
    "extra": null,
    "merchantName": "Confidential Agent Market"
  }],
  "x402Version": 1
}
```

---

## Kite Network Info

| Network | RPC | Chain ID | Explorer |
|---|---|---|---|
| Testnet | `https://rpc-testnet.gokite.ai/` | 2368 | `https://testnet.kitescan.ai/` |
| Mainnet | `https://rpc.gokite.ai/` | 2366 | `https://kitescan.ai/` |
| Faucet | `https://faucet.gokite.ai` | — | — |

**Testnet contracts:**
- Test USDT: `0x8794c866DB97E0E7c1a0E2CF51D3E1460cB37F9e`
- Pieverse facilitator: `0x12343e649e6b2b2b77649DFAb88f103c02F3C78b`

**Mainnet contracts:**
- USDC.e: `0x7aB6f3ed87C42eF0aDb67Ed95090f8bF5240149e`
- WKITE: `0xcc788DC0486CD2BaacFf287eea1902cc09FbA570`

---

## Phase 2 Additions (in progress)

- [ ] Real TEE negotiation via Phala Cloud TDX — port DCAP attestation from DealProof
- [ ] `ConfidentialEscrow.sol` deployed on Kite testnet
- [ ] Full settle flow: negotiate → DCAP attest → escrow release → on-chain `Settlement` event
- [ ] `api/services/tee.py` — Phala Cloud CVM client
- [ ] `api/services/escrow.py` — web3.py escrow interaction
- [ ] Swap `AGENT_MODEL` to `claude-sonnet-4-6` for final demo
