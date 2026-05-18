"""
Unit tests for api/services/negotiation.py.
All tests run in simulator mode (ANTHROPIC_API_KEY="" set in conftest.py).
Live-negotiation path is tested with mocked Anthropic client.
"""
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.services.negotiation import _simulate_negotiation, run_negotiation


# ── Simulator tests ───────────────────────────────────────────────────────────

class TestSimulateNegotiation:
    def test_match_when_ranges_overlap(self):
        result = _simulate_negotiation(
            buyer_params={"max_price": 1.05, "quantity": 100},
            seller_params={"floor_price": 0.95, "quantity": 100},
        )
        assert result["status"] == "matched"
        assert result["agreed_price"] is not None
        assert result["quantity"] == 100

    def test_agreed_price_is_midpoint(self):
        result = _simulate_negotiation(
            buyer_params={"max_price": 1.10, "quantity": 50},
            seller_params={"floor_price": 0.90, "quantity": 50},
        )
        # midpoint of 1.10 and 0.90 = 1.00
        assert abs(result["agreed_price"] - 1.00) < 1e-6

    def test_no_match_when_no_overlap(self):
        result = _simulate_negotiation(
            buyer_params={"max_price": 0.80, "quantity": 100},
            seller_params={"floor_price": 1.20, "quantity": 100},
        )
        assert result["status"] == "no_match"
        assert result["agreed_price"] is None
        assert result["quantity"] is None

    def test_quantity_is_min_of_both(self):
        result = _simulate_negotiation(
            buyer_params={"max_price": 1.0, "quantity": 30},
            seller_params={"floor_price": 0.9, "quantity": 80},
        )
        assert result["quantity"] == 30

    def test_match_at_equal_boundary(self):
        # buyer_max == seller_floor → should match (>= condition)
        result = _simulate_negotiation(
            buyer_params={"max_price": 1.00, "quantity": 10},
            seller_params={"floor_price": 1.00, "quantity": 10},
        )
        assert result["status"] == "matched"
        assert abs(result["agreed_price"] - 1.00) < 1e-6

    def test_simulator_attestation_marker(self):
        result = _simulate_negotiation(
            buyer_params={"max_price": 1.0, "quantity": 10},
            seller_params={"floor_price": 0.9, "quantity": 10},
        )
        assert result["attestation"] == "SIMULATED_NO_API_KEY"

    def test_result_has_all_required_fields(self):
        result = _simulate_negotiation(
            buyer_params={"max_price": 1.0, "quantity": 10},
            seller_params={"floor_price": 0.9, "quantity": 10},
        )
        required = {"status", "agreed_price", "quantity", "rounds", "attestation", "message"}
        assert required.issubset(result.keys())

    def test_rounds_is_positive_integer(self):
        result = _simulate_negotiation(
            buyer_params={"max_price": 1.0, "quantity": 10},
            seller_params={"floor_price": 0.9, "quantity": 10},
        )
        assert isinstance(result["rounds"], int)
        assert result["rounds"] > 0


# ── run_negotiation dispatcher ────────────────────────────────────────────────

class TestRunNegotiationDispatch:
    """run_negotiation should call simulator when _client is None."""

    def test_run_negotiation_uses_simulator_without_client(self):
        # conftest sets ANTHROPIC_API_KEY="" so _client is None at module level
        result = asyncio.get_event_loop().run_until_complete(
            run_negotiation(
                buyer_params={"asset": "WKITE", "target_price": 1.0, "max_price": 1.05, "quantity": 100},
                seller_params={"asset": "WKITE", "floor_price": 0.9, "ask_price": 1.0, "quantity": 100},
            )
        )
        assert result["status"] in ("matched", "no_match")
        assert "attestation" in result


# ── Live negotiation (mocked Anthropic) ──────────────────────────────────────

def _make_mock_response(text: str) -> MagicMock:
    """Produce a fake Anthropic response object whose .content[0].text == text."""
    content_block = MagicMock()
    content_block.text = text
    msg = MagicMock()
    msg.content = [content_block]
    return msg


class TestLiveNegotiation:
    """Tests for _live_negotiation with a mocked AsyncAnthropic client."""

    @pytest.mark.asyncio
    async def test_deal_on_first_round_when_buyer_accepts(self):
        buyer_accept   = json.dumps({"price": 1.00, "quantity": 100, "accept": True})
        seller_counter = json.dumps({"price": 1.00, "quantity": 100, "accept": False, "counter": 1.00})

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(
            side_effect=[
                _make_mock_response(buyer_accept),
                _make_mock_response(seller_counter),
            ]
        )

        with patch("api.services.negotiation._client", mock_client), \
             patch("api.services.tee.get_attestation", AsyncMock(return_value="MOCK_QUOTE")):
            from api.services.negotiation import _live_negotiation
            result = await _live_negotiation(
                buyer_params={"asset": "WKITE", "target_price": 1.0, "max_price": 1.05, "quantity": 100},
                seller_params={"asset": "WKITE", "floor_price": 0.9, "ask_price": 1.0, "quantity": 100},
            )

        assert result["status"] == "matched"
        assert result["rounds"] == 1
        assert result["agreed_price"] == 1.00
        assert result["attestation"] == "MOCK_QUOTE"

    @pytest.mark.asyncio
    async def test_deal_when_seller_accepts(self):
        buyer_offer    = json.dumps({"price": 0.98, "quantity": 100, "accept": False})
        seller_accept  = json.dumps({"price": 0.98, "quantity": 100, "accept": True, "counter": 0.98})

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(
            side_effect=[
                _make_mock_response(buyer_offer),
                _make_mock_response(seller_accept),
            ]
        )

        with patch("api.services.negotiation._client", mock_client), \
             patch("api.services.tee.get_attestation", AsyncMock(return_value="MOCK_QUOTE")):
            from api.services.negotiation import _live_negotiation
            result = await _live_negotiation(
                buyer_params={"asset": "WKITE", "target_price": 1.0, "max_price": 1.05, "quantity": 100},
                seller_params={"asset": "WKITE", "floor_price": 0.9, "ask_price": 1.0, "quantity": 100},
            )

        assert result["status"] == "matched"
        assert result["attestation"] == "MOCK_QUOTE"

    @pytest.mark.asyncio
    async def test_no_match_after_5_rounds(self):
        buyer_offer   = json.dumps({"price": 0.50, "quantity": 100, "accept": False})
        seller_refuse = json.dumps({"price": 2.00, "quantity": 100, "accept": False, "counter": 2.00})

        # 5 rounds × 2 calls each = 10 calls
        responses = [_make_mock_response(buyer_offer), _make_mock_response(seller_refuse)] * 5

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(side_effect=responses)

        with patch("api.services.negotiation._client", mock_client), \
             patch("api.services.tee.get_attestation", AsyncMock(return_value="MOCK_QUOTE")):
            from api.services.negotiation import _live_negotiation
            result = await _live_negotiation(
                buyer_params={"asset": "WKITE", "target_price": 0.5, "max_price": 0.55, "quantity": 100},
                seller_params={"asset": "WKITE", "floor_price": 1.9, "ask_price": 2.0, "quantity": 100},
            )

        assert result["status"] == "no_match"
        assert result["rounds"] == 5
        assert result["agreed_price"] is None

    @pytest.mark.asyncio
    async def test_invalid_json_from_model_is_skipped(self):
        """
        If a model returns non-JSON, the round is skipped.
        The negotiation should still complete (match or no_match).
        """
        bad_response  = _make_mock_response("Sorry I cannot help with that.")
        good_buyer    = _make_mock_response(json.dumps({"price": 1.00, "quantity": 10, "accept": True}))
        good_seller   = _make_mock_response(json.dumps({"price": 1.00, "quantity": 10, "accept": False, "counter": 1.00}))

        mock_client = AsyncMock()
        # Round 1: bad JSON → skipped; Round 2: good JSON → accept
        mock_client.messages.create = AsyncMock(
            side_effect=[
                bad_response,    # buyer round 1
                bad_response,    # seller round 1  (both bad → continue)
                good_buyer,      # buyer round 2
                good_seller,     # seller round 2
            ]
        )

        with patch("api.services.negotiation._client", mock_client), \
             patch("api.services.tee.get_attestation", AsyncMock(return_value="MOCK_QUOTE")):
            from api.services.negotiation import _live_negotiation
            result = await _live_negotiation(
                buyer_params={"asset": "WKITE", "target_price": 1.0, "max_price": 1.05, "quantity": 10},
                seller_params={"asset": "WKITE", "floor_price": 0.9, "ask_price": 1.0, "quantity": 10},
            )

        assert result["status"] == "matched"
