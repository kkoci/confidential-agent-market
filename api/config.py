import os
from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY: str | None = os.getenv("ANTHROPIC_API_KEY")
AGENT_MODEL: str = os.getenv("AGENT_MODEL", "claude-haiku-4-5-20251001")

# Kite-specific: funded testnet wallet provided in KITE_X402_PATCH.md
PAY_TO_ADDRESS: str = os.getenv("PAY_TO_ADDRESS", "0x46D63636B0642D37af42180dd4d1B578923a8868")

# Pieverse facilitator — NOT x402.org
FACILITATOR_URL: str = os.getenv("FACILITATOR_URL", "https://facilitator.pieverse.io")

# Kite chain
KITE_RPC_URL: str = os.getenv("KITE_RPC_URL", "https://rpc-testnet.gokite.ai/")
KITE_CHAIN_ID: int = int(os.getenv("KITE_CHAIN_ID", "2368"))
KITE_NETWORK: str = "kite-testnet"  # NOT eip155:2368 — gokite-aa scheme uses this string

# Test USDT on Kite testnet (NOT USDC.e — that's mainnet only)
TESTNET_ASSET: str = os.getenv("TESTNET_ASSET", "0x0fF5393387ad2f9f691FD6Fd28e07E3969e27e63")

# Set to "true" to skip X-PAYMENT verification in local dev
SKIP_PAYMENT_CHECK: bool = os.getenv("SKIP_PAYMENT_CHECK", "false").lower() == "true"

ESCROW_CONTRACT_ADDRESS: str = os.getenv("ESCROW_CONTRACT_ADDRESS", "")

PHALA_API_KEY: str = os.getenv("PHALA_API_KEY", "")
PHALA_CVM_ENDPOINT: str = os.getenv("PHALA_CVM_ENDPOINT", "")
