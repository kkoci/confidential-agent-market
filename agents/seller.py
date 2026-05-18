#!/usr/bin/env python3
"""
Seller agent for Confidential Agent Market.

Uses Claude claude-sonnet-4-6 to decide on ask parameters, then submits the ask
via x402 gokite-aa payment headers.

Usage:
    export ANTHROPIC_API_KEY=sk-ant-...
    export SELLER_PRIVATE_KEY=0x...       # Kite testnet wallet with KITE for gas
    python -m agents.seller

Optional:
    export MARKET_URL=http://localhost:8000
    export ASSET=WKITE
    export FLOOR_PRICE=0.95               # minimum acceptable price
    export ASK_PRICE=1.05                 # initial asking price
    export QUANTITY=100
"""
import asyncio
import base64
import json
import os
import secrets
import time
from decimal import Decimal

import httpx
from anthropic import AsyncAnthropic
from eth_account import Account

# ── Configuration ─────────────────────────────────────────────────────────────

MARKET_URL         = os.getenv("MARKET_URL",        "http://localhost:8000")
ANTHROPIC_API_KEY  = os.getenv("ANTHROPIC_API_KEY",  "")
SELLER_PRIVATE_KEY = os.getenv("SELLER_PRIVATE_KEY", "")
ASSET              = os.getenv("ASSET",              "WKITE")
FLOOR_PRICE        = Decimal(os.getenv("FLOOR_PRICE", "0.95"))
ASK_PRICE          = Decimal(os.getenv("ASK_PRICE",   "1.05"))
QUANTITY           = Decimal(os.getenv("QUANTITY",    "100"))

# Kite testnet constants
TESTNET_ASSET  = "0x1b7425d288ea676FCBc65c29711fccF0B6D5c293"   # Kite X402 USD (KXUSD), 18 decimals
KITE_CHAIN_ID  = 2368
KITE_NETWORK   = "kite-testnet"
TOKEN_NAME     = "Kite X402 USD"
TOKEN_VERSION  = "1"

_ASK_AMOUNT = "10000000000000000"    # $0.01


# ── EIP-3009 payment header construction ──────────────────────────────────────
# (Identical logic to buyer.py — factoring out is a Phase 2 concern)

def _build_payment_header(
    private_key: str,
    pay_to: str,
    amount_wei: str,
    valid_seconds: int = 300,
) -> str:
    account = Account.from_key(private_key)
    nonce   = "0x" + secrets.token_hex(32)
    now     = int(time.time())

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
            "to":          pay_to,
            "value":       int(amount_wei),
            "validAfter":  0,
            "validBefore": now + valid_seconds,
            "nonce":       nonce,
        },
    }

    signed    = account.sign_typed_data(full_message=typed_data)
    signature = "0x" + signed.signature.hex()

    authorization = {
        "from":        account.address,
        "to":          pay_to,
        "value":       amount_wei,
        "validAfter":  "0",
        "validBefore": str(now + valid_seconds),
        "nonce":       nonce,
    }

    payload = json.dumps({"authorization": authorization, "signature": signature})
    return base64.b64encode(payload.encode()).decode()


async def _call_with_payment(
    client: httpx.AsyncClient,
    method: str,
    path: str,
    private_key: str,
    amount: str,
    **kwargs,
) -> dict:
    url  = f"{MARKET_URL}{path}"
    resp = await client.request(method, url, **kwargs)
    if resp.status_code != 402:
        resp.raise_for_status()
        return resp.json()

    pay_to         = resp.json()["accepts"][0]["payTo"]
    payment_header = _build_payment_header(private_key, pay_to, amount)
    headers        = {**kwargs.pop("headers", {}), "X-PAYMENT": payment_header}

    resp = await client.request(method, url, headers=headers, **kwargs)
    resp.raise_for_status()
    return resp.json()


# ── Claude agent logic ────────────────────────────────────────────────────────

async def decide_ask(anthropic_client: AsyncAnthropic) -> dict:
    """
    Ask Claude to produce final ask parameters as JSON.
    Returns {"asset": str, "price": str, "quantity": str, "side": "sell"}.
    """
    response = await anthropic_client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=256,
        system=(
            "You are an autonomous seller agent on a confidential OTC market. "
            "Your task: decide ask parameters and respond ONLY with valid JSON. "
            "No markdown, no explanation — just the JSON object. "
            'Format: {"asset": string, "price": string, "quantity": string, "side": "sell"}'
        ),
        messages=[
            {
                "role": "user",
                "content": (
                    f"Asset: {ASSET}\n"
                    f"Floor price (minimum acceptable): {FLOOR_PRICE}\n"
                    f"Initial asking price: {ASK_PRICE}\n"
                    f"Quantity available: {QUANTITY}\n"
                    "Decide: post the ask at the asking price to leave negotiation room."
                ),
            }
        ],
    )

    text = response.content[0].text.strip()
    ask  = json.loads(text)
    ask["price"]    = str(ask.get("price", ASK_PRICE))
    ask["quantity"] = str(ask.get("quantity", QUANTITY))
    ask["side"]     = "sell"
    return ask


# ── Main ──────────────────────────────────────────────────────────────────────

async def main() -> None:
    if not SELLER_PRIVATE_KEY:
        raise SystemExit("SELLER_PRIVATE_KEY not set. Export your Kite testnet wallet key.")

    anthropic_client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None

    async with httpx.AsyncClient(timeout=30.0) as http:
        # 1. Claude decides the ask
        if anthropic_client:
            print("[seller] Asking Claude to decide ask parameters…")
            ask_body = await decide_ask(anthropic_client)
        else:
            ask_body = {"asset": ASSET, "price": str(ASK_PRICE), "quantity": str(QUANTITY), "side": "sell"}
        print(f"[seller] Ask: {ask_body}")

        # 2. Submit ask (pay $0.01)
        ask_result = await _call_with_payment(
            http, "POST", "/market/ask",
            SELLER_PRIVATE_KEY, _ASK_AMOUNT,
            json=ask_body,
        )
        ask_id = ask_result["order_id"]
        print(f"[seller] Ask accepted: {ask_id}")
        print(f"[seller] Share this with the buyer: ASK_ORDER_ID={ask_id}")


if __name__ == "__main__":
    asyncio.run(main())
