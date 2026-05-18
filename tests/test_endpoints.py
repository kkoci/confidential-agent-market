"""
Endpoint tests for all four market routes + health.
All tests run with SKIP_PAYMENT_CHECK=true (set in conftest.py).
"""
import pytest
from fastapi.testclient import TestClient

from tests.conftest import (
    BID_PAYLOAD,
    ASK_PAYLOAD,
    NO_MATCH_BID,
    NO_MATCH_ASK,
    OVERLAPPING_BID,
    OVERLAPPING_ASK,
)


# ── /health ───────────────────────────────────────────────────────────────────

def test_health_returns_200(client: TestClient):
    resp = client.get("/health")
    assert resp.status_code == 200


def test_health_response_shape(client: TestClient):
    data = client.get("/health").json()
    assert "status" in data


# ── /market/bid ───────────────────────────────────────────────────────────────

def test_bid_accepted(client: TestClient):
    resp = client.post("/market/bid", json=BID_PAYLOAD)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "accepted"
    assert "order_id" in data
    assert data["asset"] == "WKITE"
    assert data["side"] == "buy"


def test_bid_returns_uuid(client: TestClient):
    resp = client.post("/market/bid", json=BID_PAYLOAD)
    order_id = resp.json()["order_id"]
    # Must be a non-empty UUID-shaped string
    assert len(order_id) == 36
    assert order_id.count("-") == 4


def test_bid_missing_field_returns_422(client: TestClient):
    resp = client.post("/market/bid", json={"asset": "WKITE", "price": "1.00"})
    assert resp.status_code == 422


def test_bid_negative_price_returns_422(client: TestClient):
    resp = client.post("/market/bid", json={**BID_PAYLOAD, "price": "-1"})
    assert resp.status_code == 422


def test_bid_payment_required_when_check_enabled(client: TestClient, monkeypatch):
    import api.services.payment as pm
    monkeypatch.setattr(pm, "SKIP_PAYMENT_CHECK", False)

    resp = client.post("/market/bid", json=BID_PAYLOAD)
    assert resp.status_code == 402
    data = resp.json()
    assert data["x402Version"] == 1
    assert data["accepts"][0]["scheme"] == "gokite-aa"
    assert data["accepts"][0]["network"] == "kite-testnet"
    assert "maxAmountRequired" in data["accepts"][0]


# ── /market/ask ───────────────────────────────────────────────────────────────

def test_ask_accepted(client: TestClient):
    resp = client.post("/market/ask", json=ASK_PAYLOAD)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "accepted"
    assert data["side"] == "sell"


def test_ask_missing_field_returns_422(client: TestClient):
    resp = client.post("/market/ask", json={"asset": "WKITE"})
    assert resp.status_code == 422


def test_ask_payment_required_when_check_enabled(client: TestClient, monkeypatch):
    import api.services.payment as pm
    monkeypatch.setattr(pm, "SKIP_PAYMENT_CHECK", False)

    resp = client.post("/market/ask", json=ASK_PAYLOAD)
    assert resp.status_code == 402
    assert resp.json()["accepts"][0]["scheme"] == "gokite-aa"


# ── /market/status ────────────────────────────────────────────────────────────

def test_status_empty_book(client: TestClient):
    data = client.get("/market/status").json()
    assert data["bids"] == 0
    assert data["asks"] == 0
    assert data["status"] == "open"


def test_status_reflects_submitted_orders(client: TestClient):
    client.post("/market/bid", json=BID_PAYLOAD)
    client.post("/market/bid", json=BID_PAYLOAD)
    client.post("/market/ask", json=ASK_PAYLOAD)

    data = client.get("/market/status").json()
    assert data["bids"] == 2
    assert data["asks"] == 1


def test_status_payment_required_when_check_enabled(client: TestClient, monkeypatch):
    import api.services.payment as pm
    monkeypatch.setattr(pm, "SKIP_PAYMENT_CHECK", False)

    resp = client.get("/market/status")
    assert resp.status_code == 402


# ── /market/settle ────────────────────────────────────────────────────────────

def test_settle_nonexistent_orders_returns_error(client: TestClient):
    resp = client.post("/market/settle", json={
        "bid_id":         "00000000-0000-0000-0000-000000000000",
        "ask_id":         "00000000-0000-0000-0000-000000000001",
        "buyer_address":  "0xBuyer",
        "seller_address": "0xSeller",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "error"
    assert "not found" in data["message"].lower()


def test_settle_matched_orders_returns_matched(client: TestClient):
    bid_id = client.post("/market/bid", json=OVERLAPPING_BID).json()["order_id"]
    ask_id = client.post("/market/ask", json=OVERLAPPING_ASK).json()["order_id"]

    resp = client.post("/market/settle", json={
        "bid_id":         bid_id,
        "ask_id":         ask_id,
        "buyer_address":  "0xBuyer",
        "seller_address": "0xSeller",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "matched"
    assert data["agreed_price"] is not None
    assert data["quantity"] is not None
    assert data["asset"] == "WKITE"


def test_settle_removes_orders_from_book_on_match(client: TestClient):
    bid_id = client.post("/market/bid", json=OVERLAPPING_BID).json()["order_id"]
    ask_id = client.post("/market/ask", json=OVERLAPPING_ASK).json()["order_id"]

    client.post("/market/settle", json={
        "bid_id": bid_id, "ask_id": ask_id,
        "buyer_address": "0xB", "seller_address": "0xS",
    })

    status = client.get("/market/status").json()
    assert status["bids"] == 0
    assert status["asks"] == 0


def test_settle_no_match_keeps_orders_in_book(client: TestClient):
    bid_id = client.post("/market/bid", json=NO_MATCH_BID).json()["order_id"]
    ask_id = client.post("/market/ask", json=NO_MATCH_ASK).json()["order_id"]

    resp = client.post("/market/settle", json={
        "bid_id": bid_id, "ask_id": ask_id,
        "buyer_address": "0xB", "seller_address": "0xS",
    })
    assert resp.json()["status"] == "no_match"

    status = client.get("/market/status").json()
    assert status["bids"] == 1
    assert status["asks"] == 1


def test_settle_result_has_attestation(client: TestClient):
    bid_id = client.post("/market/bid", json=OVERLAPPING_BID).json()["order_id"]
    ask_id = client.post("/market/ask", json=OVERLAPPING_ASK).json()["order_id"]

    resp = client.post("/market/settle", json={
        "bid_id": bid_id, "ask_id": ask_id,
        "buyer_address": "0xB", "seller_address": "0xS",
    })
    data = resp.json()
    assert "attestation" in data
    assert data["attestation"]  # non-empty string


def test_settle_payment_required_when_check_enabled(client: TestClient, monkeypatch):
    import api.services.payment as pm
    monkeypatch.setattr(pm, "SKIP_PAYMENT_CHECK", False)

    resp = client.post("/market/settle", json={
        "bid_id": "x", "ask_id": "y",
        "buyer_address": "0xB", "seller_address": "0xS",
    })
    assert resp.status_code == 402


def test_settle_missing_field_returns_422(client: TestClient):
    resp = client.post("/market/settle", json={"bid_id": "x"})
    assert resp.status_code == 422
