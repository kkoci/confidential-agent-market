from decimal import Decimal
from pydantic import BaseModel, Field


class SettleRequest(BaseModel):
    bid_id: str = Field(..., description="Order ID of the accepted bid")
    ask_id: str = Field(..., description="Order ID of the accepted ask")
    buyer_address: str = Field(..., description="Buyer wallet address")
    seller_address: str = Field(..., description="Seller wallet address")


class SettlementResult(BaseModel):
    status: str  # "matched" | "no_match" | "error"
    agreed_price: Decimal | None = None
    quantity: Decimal | None = None
    asset: str | None = None
    rounds: int = 0
    attestation: str = "MOCK_ATTESTATION_TODO"
    tx_hash: str | None = None
    message: str = ""
