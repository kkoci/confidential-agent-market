import uuid
from decimal import Decimal
from fastapi import APIRouter
from api.models.order import Order, OrderResponse, OrderSide
from api.models.settlement import SettleRequest, SettlementResult
from api.services.payment import require_payment

router = APIRouter(prefix="/market")

# Test USDT has 18 decimals: 10^16 = $0.01, 10^15 = $0.001, 5*10^16 = $0.05
_BID_AMOUNT    = "10000000000000000"    # $0.01
_ASK_AMOUNT    = "10000000000000000"    # $0.01
_STATUS_AMOUNT = "1000000000000000"     # $0.001
_SETTLE_AMOUNT = "50000000000000000"    # $0.05

# In-memory order book — Phase 1 placeholder (no persistence)
_bids: dict[str, dict] = {}
_asks: dict[str, dict] = {}


@router.post("/bid", response_model=OrderResponse)
async def submit_bid(
    order: Order,
    _=require_payment(_BID_AMOUNT, "Confidential Agent Market — submit buy bid"),
) -> OrderResponse:
    order_id = str(uuid.uuid4())
    _bids[order_id] = order.model_dump()
    return OrderResponse(
        order_id=order_id,
        status="accepted",
        asset=order.asset,
        price=order.price,
        quantity=order.quantity,
        side=OrderSide.buy,
        message="Bid received. Sealed inside negotiation queue.",
    )


@router.post("/ask", response_model=OrderResponse)
async def submit_ask(
    order: Order,
    _=require_payment(_ASK_AMOUNT, "Confidential Agent Market — submit sell ask"),
) -> OrderResponse:
    order_id = str(uuid.uuid4())
    _asks[order_id] = order.model_dump()
    return OrderResponse(
        order_id=order_id,
        status="accepted",
        asset=order.asset,
        price=order.price,
        quantity=order.quantity,
        side=OrderSide.sell,
        message="Ask received. Sealed inside negotiation queue.",
    )


@router.get("/status")
async def market_status(
    _=require_payment(_STATUS_AMOUNT, "Confidential Agent Market — order book status"),
) -> dict:
    return {
        "bids": len(_bids),
        "asks": len(_asks),
        "status": "open",
    }


@router.post("/settle", response_model=SettlementResult)
async def settle(
    request: SettleRequest,
    _=require_payment(_SETTLE_AMOUNT, "Confidential Agent Market — trigger TEE settlement"),
) -> SettlementResult:
    """
    Trigger negotiation, obtain TEE attestation, and optionally settle on-chain.

    Phase 1: negotiation runs locally; attestation is real if inside Phala CVM,
             mock-prefixed otherwise.
    Phase 2: sealed inside Phala Cloud TDX; escrow contract release on match.
    """
    from api.services.negotiation import run_negotiation
    from api.services.escrow import EscrowService, is_available as escrow_available

    bid = _bids.get(request.bid_id)
    ask = _asks.get(request.ask_id)

    if bid is None or ask is None:
        return SettlementResult(
            status="error",
            message=f"Order not found: bid={request.bid_id} ask={request.ask_id}",
        )

    buyer_params = {
        "asset":        bid["asset"],
        "target_price": float(bid["price"]),
        "max_price":    float(bid["price"]) * 1.05,
        "quantity":     float(bid["quantity"]),
    }
    seller_params = {
        "asset":       ask["asset"],
        "floor_price": float(ask["price"]) * 0.95,
        "ask_price":   float(ask["price"]),
        "quantity":    float(ask["quantity"]),
    }

    try:
        result = await run_negotiation(buyer_params, seller_params)
    except Exception as exc:
        return SettlementResult(
            status="error",
            message=f"Negotiation failed: {type(exc).__name__}: {exc}",
        )

    tx_hash: str | None = None

    if result["status"] == "matched":
        _bids.pop(request.bid_id, None)
        _asks.pop(request.ask_id, None)

        # On-chain escrow settlement — only when contract is configured
        if escrow_available():
            try:
                svc = EscrowService()

                # Auto approve+deposit if the escrow hasn't been seeded yet.
                # Compute amount from agreed terms (KXUSD has 18 decimals).
                escrow_state = await svc.get_escrow(request.bid_id, request.ask_id)
                _ZERO = "0x0000000000000000000000000000000000000000"
                if escrow_state["buyer"] in (_ZERO, ""):
                    amount_wei = int(
                        Decimal(str(result["agreed_price"]))
                        * Decimal(str(result["quantity"]))
                        * Decimal("1000000000000000000")
                    )
                    await svc.approve_and_deposit(
                        request.bid_id,
                        request.ask_id,
                        request.seller_address,
                        amount_wei,
                    )

                # Pass the hex string; EscrowService.settle does fromhex().
                # (Using .encode() here would double calldata size as UTF-8
                # bytes and OOG the tx for a ~5 KB DCAP quote.)
                tx_hash = await svc.settle(
                    request.bid_id,
                    request.ask_id,
                    result["attestation"],
                )
            except Exception:
                # Escrow failure doesn't invalidate the negotiation result
                pass

    return SettlementResult(**result, asset=bid["asset"], tx_hash=tx_hash)
