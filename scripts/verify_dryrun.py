#!/usr/bin/env python3
"""
Dry-run: sign a minimal EIP-3009 transferWithAuthorization for KXUSD on Kite
testnet, build the Pieverse v2 paymentPayload + paymentRequirements envelope,
POST it to /v2/settle, and print the full response.

No server, no funded wallet required (verify is signature-only). Use this to
validate TOKEN_NAME / domain / address before flipping SKIP_PAYMENT_CHECK.

Usage (PowerShell):
    $env:TEST_PRIVATE_KEY = "0x<your testnet privkey>"
    python -m scripts.verify_dryrun
"""
import base64
import json
import os
import secrets
import time

import httpx
from eth_account import Account

FACILITATOR_URL = "https://facilitator.pieverse.io"
PAY_TO_ADDRESS  = "0x4812fC05e79ddc616346d10A8826B2bdf5e6ab20"
TESTNET_ASSET   = "0x1b7425d288ea676FCBc65c29711fccF0B6D5c293"   # KXUSD
KITE_CHAIN_ID   = 2368
KITE_NETWORK    = "eip155:2368"
PIEVERSE_SCHEME = "exact"
X402_VERSION    = 2
TOKEN_NAME      = "Kite X402 USD"
TOKEN_VERSION   = "1"

AMOUNT_WEI      = "10000000000000000"   # 0.01 KXUSD (18 decimals)
RESOURCE_URL    = "http://localhost:8000/market/bid"
DESCRIPTION     = "Dry-run verify"


def build_payment_payload(private_key: str) -> dict:
    account = Account.from_key(private_key)
    nonce   = "0x" + secrets.token_hex(32)
    now     = int(time.time())
    valid_before = now + 300

    typed_data = {
        "types": {
            "EIP712Domain": [
                {"name": "name",              "type": "string"},
                {"name": "version",           "type": "string"},
                {"name": "chainId",           "type": "uint256"},
                {"name": "verifyingContract", "type": "address"},
            ],
            "TransferWithAuthorization": [
                {"name": "from",        "type": "address"},
                {"name": "to",          "type": "address"},
                {"name": "value",       "type": "uint256"},
                {"name": "validAfter",  "type": "uint256"},
                {"name": "validBefore", "type": "uint256"},
                {"name": "nonce",       "type": "bytes32"},
            ],
        },
        "primaryType": "TransferWithAuthorization",
        "domain": {
            "name":              TOKEN_NAME,
            "version":           TOKEN_VERSION,
            "chainId":           KITE_CHAIN_ID,
            "verifyingContract": TESTNET_ASSET,
        },
        "message": {
            "from":        account.address,
            "to":          PAY_TO_ADDRESS,
            "value":       int(AMOUNT_WEI),
            "validAfter":  0,
            "validBefore": valid_before,
            "nonce":       nonce,
        },
    }

    signed = account.sign_typed_data(full_message=typed_data)
    signature = signed.signature.hex()
    if not signature.startswith("0x"):
        signature = "0x" + signature

    return {
        "x402Version": X402_VERSION,
        "scheme":      PIEVERSE_SCHEME,
        "network":     KITE_NETWORK,
        "payload": {
            "signature": signature,
            "authorization": {
                "from":        account.address,
                "to":          PAY_TO_ADDRESS,
                "value":       AMOUNT_WEI,
                "validAfter":  "0",
                "validBefore": str(valid_before),
                "nonce":       nonce,
            },
        },
    }


def build_payment_requirements() -> dict:
    return {
        "scheme":            PIEVERSE_SCHEME,
        "network":           KITE_NETWORK,
        "maxAmountRequired": AMOUNT_WEI,
        "resource":          RESOURCE_URL,
        "description":       DESCRIPTION,
        "mimeType":          "application/json",
        "payTo":             PAY_TO_ADDRESS,
        "maxTimeoutSeconds": 300,
        "asset":             TESTNET_ASSET,
        "outputSchema":      None,
        "extra":             None,
    }


def main() -> None:
    private_key = os.getenv("TEST_PRIVATE_KEY", "").strip()
    if not private_key or private_key in ("0x...", "0x"):
        raise SystemExit("TEST_PRIVATE_KEY env var not set. Export a testnet private key first.")

    payment_payload      = build_payment_payload(private_key)
    payment_requirements = build_payment_requirements()
    envelope = {
        "paymentPayload":      payment_payload,
        "paymentRequirements": payment_requirements,
    }

    signer = Account.from_key(private_key).address
    print(f"Signer address:   {signer}")
    print(f"Token (KXUSD):    {TESTNET_ASSET}")
    print(f"EIP-712 domain:   name={TOKEN_NAME!r}, version={TOKEN_VERSION!r}, chainId={KITE_CHAIN_ID}")
    print(f"Facilitator:      {FACILITATOR_URL}/v2/settle")
    print()
    print("Outbound envelope:")
    print(json.dumps(envelope, indent=2))
    print()

    resp = httpx.post(f"{FACILITATOR_URL}/v2/settle", json=envelope, timeout=15.0)
    print(f"HTTP {resp.status_code}")
    print("Response headers:")
    for k, v in resp.headers.items():
        print(f"  {k}: {v}")
    print()
    print("Response body:")
    try:
        print(json.dumps(resp.json(), indent=2))
    except Exception:
        print(resp.text)


if __name__ == "__main__":
    main()
