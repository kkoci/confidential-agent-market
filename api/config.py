import os
from dotenv import load_dotenv

load_dotenv()

_raw_anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_API_KEY: str | None = _raw_anthropic_key if _raw_anthropic_key and not _raw_anthropic_key.endswith("...") else None
AGENT_MODEL: str = os.getenv("AGENT_MODEL", "claude-sonnet-4-6")

# Kite-specific: funded testnet wallet provided in KITE_X402_PATCH.md
PAY_TO_ADDRESS: str = os.getenv("PAY_TO_ADDRESS", "0x4812fC05e79ddc616346d10A8826B2bdf5e6ab20")

# Pieverse facilitator — NOT x402.org
FACILITATOR_URL: str = os.getenv("FACILITATOR_URL", "https://facilitator.pieverse.io")

# Kite chain
KITE_RPC_URL: str = os.getenv("KITE_RPC_URL", "https://rpc-testnet.gokite.ai/")
KITE_CHAIN_ID: int = int(os.getenv("KITE_CHAIN_ID", "2368"))
KITE_NETWORK: str = "kite-testnet"  # NOT eip155:2368 — gokite-aa scheme uses this string

# Kite X402 USD (KXUSD) on Kite testnet — 18 decimals
TESTNET_ASSET: str = os.getenv("TESTNET_ASSET", "0x1b7425d288ea676FCBc65c29711fccF0B6D5c293")

# Set to "true" to skip X-PAYMENT verification in local dev
SKIP_PAYMENT_CHECK: bool = os.getenv("SKIP_PAYMENT_CHECK", "false").lower() == "true"

ESCROW_CONTRACT_ADDRESS: str = os.getenv("ESCROW_CONTRACT_ADDRESS", "")

PHALA_API_KEY: str = os.getenv("PHALA_API_KEY", "")
PHALA_CVM_ENDPOINT: str = os.getenv("PHALA_CVM_ENDPOINT", "")

# Agent wallet — signs escrow transactions on-chain; testnet only, never commit
AGENT_PRIVATE_KEY: str = os.getenv("AGENT_PRIVATE_KEY", "")
