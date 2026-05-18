#!/usr/bin/env python3
"""
Buyer agent for Confidential Agent Market.

Uses Claude claude-sonnet-4-6 to decide on bid parameters, then submits the bid
and triggers settlement — paying each endpoint via x402 gokite-aa headers.

Usage:
    export ANTHROPIC_API_KEY=sk-ant-...
    export BUYER_PRIVATE_KEY=0x...        # Kite testnet wallet with Test USDT
    export SELLER_ADDRESS=0x...           # Counterparty seller address
    python -m agents.buyer

Optional:
    export MARKET_URL=http://localhost:8000   (default)
    export ASSET=WKITE                        (default)
    export TARGET_PRICE=1.00                  (default)
    export QUANTITY=100                       (default)
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

MARKET_URL        = os.getenv("MARKET_URL",       "http://localhost:8000")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
BUYER_PRIVATE_KEY = os.getenv("BUYER_PRIVATE_KEY", "")
SELLER_ADDRESS    = os.getenv("SELLER_ADDRESS",    "")
ASSET             = os.getenv("ASSET",             "WKITE")
TARGET_PRICE      = Decimal(os.getenv("TARGET_PRICE", "1.00"))
QUANTITY          = Decimal(os.getenv("QUANTITY",    "100"))

# Kite testnet constants
TESTNET_ASSET  = "0x1b7425d288ea676FCBc65c29711fccF0B6D5c293"   # Kite X402 USD (KXUSD), 18 decimals
KITE_CHAIN_ID  = 2368
KITE_NETWORK   = "kite-testnet"
TOKEN_NAME     = "Kite X402 USD"   # EIP-712 domain — must match KXUSD contract's name()
TOKEN_VERSION  = "1"

# Payment amounts match the server's payment_required responses (18-decimal wei)
_BID_AMOUNT    = "10000000000000000"    # $0.01
_SETTLE_AMOUNT = "50000000000000000"    # $0.05

# ── EIP-3009 payment header construction ──────────────────────────────────────

def _build_payment_header(
    private_key: str,
    pay_to: str,
    amount_wei: str,
    valid_seconds: int = 300,
) -> str:
    """
    Build and sign an EIP-3009 transferWithAuthorization, then base64-encode
    the {authorization, signature} JSON as the X-PAYMENT header value.

    gokite-aa scheme — Pieverse facilitator calls transferWithAuthorization
    on the KXUSD contract on behalf of the payer.
    """
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
    """
    Make a request; if we get a 402, extract payTo from the response,
    construct the X-PAYMENT header, and retry.
    """
    url = f"{MARKET_URL}{path}"

    # First attempt — no payment header
    resp = await client.request(method, url, **kwargs)
    if resp.status_code != 402:
        resp.raise_for_status()
        return resp.json()

    # Parse 402 to get the payTo address
    data   = resp.json()
    pay_to = data["accepts"][0]["payTo"]

    payment_header = _build_payment_header(private_key, pay_to, amount)
    headers        = {**kwargs.pop("headers", {}), "X-PAYMENT": payment_header}

    resp = await client.request(method, url, headers=headers, **kwargs)
    resp.raise_for_status()
    return resp.json()


# ── Claude agent logic ────────────────────────────────────────────────────────

async def decide_bid(anthropic_client: AsyncAnthropic) -> dict:
    """
    Ask Claude to produce final bid parameters as JSON.
    Returns {"asset": str, "price": str, "quantity": str, "side": "buy"}.
    """
    response = await anthropic_client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=256,
        system=(
            "You are an autonomous buyer agent on a confidential OTC market. "
            "Your task: decide bid parameters and respond ONLY with valid JSON. "
            "No markdown, no explanation — just the JSON object. "
            'Format: {"asset": string, "price": string, "quantity": string, "side": "buy"}'
        ),
        messages=[
            {
                "role": "user",
                "content": (
                    f"Asset: {ASSET}\n"
                    f"Target price: {TARGET_PRICE}\n"
                    f"Quantity: {QUANTITY}\n"
                    "Decide: submit a bid at or slightly below target to leave negotiation room."
                ),
            }
        ],
    )

    text = response.content[0].text.strip()
    bid  = json.loads(text)
    # Normalise price/quantity to strings so Pydantic on the server accepts Decimal
    bid["price"]    = str(bid.get("price", TARGET_PRICE))
    bid["quantity"] = str(bid.get("quantity", QUANTITY))
    bid["side"]     = "buy"
    return bid


# ── Main ──────────────────────────────────────────────────────────────────────

async def main() -> None:
    if not BUYER_PRIVATE_KEY:
        raise SystemExit("BUYER_PRIVATE_KEY not set. Export your Kite testnet wallet key.")
    if not SELLER_ADDRESS:
        raise SystemExit("SELLER_ADDRESS not set. Export the seller's wallet address.")

    anthropic_client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None

    async with httpx.AsyncClient(timeout=30.0) as http:
        # 1. Claude decides the bid
        if anthropic_client:
            print("[buyer] Asking Claude to decide bid parameters…")
            bid_body = await decide_bid(anthropic_client)
        else:
            bid_body = {"asset": ASSET, "price": str(TARGET_PRICE), "quantity": str(QUANTITY), "side": "buy"}
        print(f"[buyer] Bid: {bid_body}")

        # 2. Submit bid (pay $0.01)
        bid_result = await _call_with_payment(
            http, "POST", "/market/bid",
            BUYER_PRIVATE_KEY, _BID_AMOUNT,
            json=bid_body,
        )
        bid_id = bid_result["order_id"]
        print(f"[buyer] Bid accepted: {bid_id}")

        # 3. Check market status (free to skip, just informational)
        try:
            status = await http.get(f"{MARKET_URL}/health")
            print(f"[buyer] Market health: {status.json()}")
        except Exception:
            pass

        # 4. Trigger settlement (pay $0.05)
        # NOTE: In the full Phase 2 flow the seller would have submitted an ask first.
        # Here we hardcode a placeholder ask_id — replace with the real ask UUID.
        ask_id = os.getenv("ASK_ORDER_ID", "")
        if not ask_id:
            print("[buyer] ASK_ORDER_ID not set — skipping settle. Set it to the seller's ask UUID.")
            return

        settle_body = {
            "bid_id":         bid_id,
            "ask_id":         ask_id,
            "buyer_address":  Account.from_key(BUYER_PRIVATE_KEY).address,
            "seller_address": SELLER_ADDRESS,
        }
        print("[buyer] Triggering settlement…")
        result = await _call_with_payment(
            http, "POST", "/market/settle",
            BUYER_PRIVATE_KEY, _SETTLE_AMOUNT,
            json=settle_body,
        )
        print(f"[buyer] Settlement result: {json.dumps(result, indent=2)}")


if __name__ == "__main__":
    asyncio.run(main())
