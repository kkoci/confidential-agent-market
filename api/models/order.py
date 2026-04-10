from enum import Enum
from decimal import Decimal
from pydantic import BaseModel, Field, field_validator


class OrderSide(str, Enum):
    buy = "buy"
    sell = "sell"


class Order(BaseModel):
    asset: str = Field(..., examples=["WKITE"])
    price: Decimal = Field(..., gt=0, examples=["0.95"])
    quantity: Decimal = Field(..., gt=0, examples=["100"])
    side: OrderSide

    @field_validator("price", "quantity", mode="before")
    @classmethod
    def coerce_str_to_decimal(cls, v: object) -> object:
        if isinstance(v, str):
            return Decimal(v)
        return v


class OrderResponse(BaseModel):
    order_id: str
    status: str
    asset: str
    price: Decimal
    quantity: Decimal
    side: OrderSide
    message: str = ""
