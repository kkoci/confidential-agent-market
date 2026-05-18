"""
Pytest configuration.

Environment variables are set BEFORE any api module is imported so that
api/config.py reads them correctly (it runs at module-load time).
"""
import os

# Force dev-mode settings for the entire test session
os.environ["SKIP_PAYMENT_CHECK"]     = "true"
os.environ["ANTHROPIC_API_KEY"]      = ""    # forces simulator — no real API calls
os.environ["ESCROW_CONTRACT_ADDRESS"] = ""   # disables on-chain escrow
os.environ["AGENT_PRIVATE_KEY"]      = ""

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.routes.market import _bids, _asks


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def clear_order_book():
    """Reset the in-memory order book before and after every test."""
    _bids.clear()
    _asks.clear()
    yield
    _bids.clear()
    _asks.clear()


# ── Shared order payloads ─────────────────────────────────────────────────────

BID_PAYLOAD = {"asset": "WKITE", "price": "1.00", "quantity": "100", "side": "buy"}
ASK_PAYLOAD = {"asset": "WKITE", "price": "0.95", "quantity": "100", "side": "sell"}

# Buyer max  = 1.00 * 1.05 = 1.05
# Seller min = 0.95 * 0.95 = 0.9025
# → ranges overlap → simulator returns "matched"
OVERLAPPING_BID = {"asset": "WKITE", "price": "1.00", "quantity": "100", "side": "buy"}
OVERLAPPING_ASK = {"asset": "WKITE", "price": "0.95", "quantity": "100", "side": "sell"}

# Buyer max  = 0.50 * 1.05 = 0.525
# Seller min = 2.00 * 0.95 = 1.90
# → no overlap → simulator returns "no_match"
NO_MATCH_BID = {"asset": "WKITE", "price": "0.50", "quantity": "100", "side": "buy"}
NO_MATCH_ASK = {"asset": "WKITE", "price": "2.00", "quantity": "100", "side": "sell"}
