"""
Kite gokite-aa x402 payment layer.
Replaces Coinbase x402[fastapi] middleware — Kite uses its own scheme and Pieverse facilitator.
Reference: KITE_X402_PATCH.md, https://github.com/gokite-ai/x402
"""
import base64
import json
from typing import Callable

import httpx
from fastapi import Depends, Request
from fastapi.responses import JSONResponse

from api.config import (
    FACILITATOR_URL,
    KITE_NETWORK,
    PAY_TO_ADDRESS,
    SKIP_PAYMENT_CHECK,
    TESTNET_ASSET,
)


class KitePaymentRequired(Exception):
    def __init__(self, resource_url: str, description: str, amount: str) -> None:
        self.resource_url = resource_url
        self.description = description
        self.amount = amount


def payment_required_response(resource_url: str, description: str, amount: str) -> JSONResponse:
    return JSONResponse(
        status_code=402,
        content={
            "error": "X-PAYMENT header is required",
            "accepts": [
                {
                    "scheme": "gokite-aa",
                    "network": KITE_NETWORK,
                    "maxAmountRequired": amount,
                    "resource": resource_url,
                    "description": description,
                    "mimeType": "application/json",
                    "payTo": PAY_TO_ADDRESS,
                    "maxTimeoutSeconds": 300,
                    "asset": TESTNET_ASSET,
                    "extra": None,
                    "merchantName": "Confidential Agent Market",
                }
            ],
            "x402Version": 1,
        },
    )


async def verify_and_settle(payment_header: str) -> bool:
    """Decode X-PAYMENT header (base64 JSON) and settle via Pieverse /v2/settle."""
    try:
        decoded = json.loads(base64.b64decode(payment_header).decode())
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{FACILITATOR_URL}/v2/settle",
                json={
                    "authorization": decoded.get("authorization"),
                    "signature": decoded.get("signature"),
                    "network": KITE_NETWORK,
                },
            )
        return resp.status_code == 200
    except Exception:
        return False


def require_payment(amount: str, description: str) -> Callable:
    """
    Dependency factory. Usage:
        @router.post("/market/bid")
        async def bid(order: Order, _=require_payment("10000000000000000", "Submit bid")):
    """
    async def _check(request: Request) -> None:
        if SKIP_PAYMENT_CHECK:
            return
        header = request.headers.get("X-PAYMENT")
        if not header:
            raise KitePaymentRequired(str(request.url), description, amount)
        settled = await verify_and_settle(header)
        if not settled:
            raise KitePaymentRequired(str(request.url), description, amount)

    return Depends(_check)
