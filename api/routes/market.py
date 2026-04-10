import uuid
from fastapi import APIRouter
from api.models.order import Order, OrderResponse, OrderSide
from api.models.settlement import SettleRequest, SettlementResult
from api.services.payment import require_payment

router = APIRouter(prefix="/market")

# Test USDT has 18 decimals: 10^16 = $0.01, 10^15 = $0.001, 5*10^16 = $0.05
_BID_AMOUNT = "10000000000000000"    # $0.01
_ASK_AMOUNT = "10000000000000000"    # $0.01
_STATUS_AMOUNT = "1000000000000000"  # $0.001
_SETTLE_AMOUNT = "50000000000000000" # $0.05

# In-memory order book — Phase 1 placeholder
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
    Trigger negotiation and on-chain settlement.
    Phase 1: runs negotiation locally with mock attestation.
    Phase 2: sealed inside Phala Cloud TDX.
    """
    from api.services.negotiation import run_negotiation

    bid = _bids.get(request.bid_id)
    ask = _asks.get(request.ask_id)

    if bid is None or ask is None:
        return SettlementResult(
            status="error",
            message=f"Order not found: bid={request.bid_id} ask={request.ask_id}",
        )

    buyer_params = {
        "asset": bid["asset"],
        "target_price": float(bid["price"]),
        "max_price": float(bid["price"]) * 1.05,
        "quantity": float(bid["quantity"]),
    }
    seller_params = {
        "asset": ask["asset"],
        "floor_price": float(ask["price"]) * 0.95,
        "ask_price": float(ask["price"]),
        "quantity": float(ask["quantity"]),
    }

    result = await run_negotiation(buyer_params, seller_params)

    if result["status"] == "matched":
        _bids.pop(request.bid_id, None)
        _asks.pop(request.ask_id, None)

    return SettlementResult(**result, asset=bid["asset"])
