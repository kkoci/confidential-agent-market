import json
import anthropic
from api.config import AGENT_MODEL, ANTHROPIC_API_KEY

_client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None


async def run_negotiation(buyer_params: dict, seller_params: dict) -> dict:
    """
    Run sealed negotiation between buyer and seller agents (max 5 rounds).
    Falls back to a deterministic simulator when ANTHROPIC_API_KEY is not set.
    Phase 2: will run inside Phala Cloud TDX.
    """
    if _client is None:
        return _simulate_negotiation(buyer_params, seller_params)
    return await _live_negotiation(buyer_params, seller_params)


def _simulate_negotiation(buyer_params: dict, seller_params: dict) -> dict:
    """
    Deterministic mock: meets in the middle if ranges overlap, else no_match.
    Used when ANTHROPIC_API_KEY is absent.
    """
    buyer_max = buyer_params["max_price"]
    seller_floor = seller_params["floor_price"]

    if buyer_max >= seller_floor:
        agreed_price = round((buyer_max + seller_floor) / 2, 6)
        quantity = min(buyer_params["quantity"], seller_params["quantity"])
        return {
            "status": "matched",
            "agreed_price": agreed_price,
            "quantity": quantity,
            "rounds": 2,
            "attestation": "SIMULATED_NO_API_KEY",
            "message": "Simulated match (no ANTHROPIC_API_KEY). Set key for live agents.",
        }

    return {
        "status": "no_match",
        "rounds": 5,
        "agreed_price": None,
        "quantity": None,
        "attestation": "SIMULATED_NO_API_KEY",
        "message": "Simulated no-match (buyer max < seller floor). No ANTHROPIC_API_KEY set.",
    }


async def _live_negotiation(buyer_params: dict, seller_params: dict) -> dict:
    history: list[dict] = []

    for round_num in range(5):
        buyer_response = await _client.messages.create(
            model=AGENT_MODEL,
            max_tokens=256,
            system=(
                f"You are a buyer agent negotiating to purchase {buyer_params['asset']}. "
                f"Your target price is {buyer_params['target_price']}. "
                f"Max price you will pay: {buyer_params['max_price']}. "
                f"Quantity needed: {buyer_params['quantity']}. "
                "Respond ONLY with valid JSON: "
                '{"price": float, "quantity": float, "accept": bool}'
            ),
            messages=history
            + [{"role": "user", "content": f"Round {round_num + 1}. Make your offer."}],
        )
        buyer_text = buyer_response.content[0].text.strip()
        history.append({"role": "user", "content": f"Round {round_num + 1}. Make your offer."})
        history.append({"role": "assistant", "content": buyer_text})

        seller_response = await _client.messages.create(
            model=AGENT_MODEL,
            max_tokens=256,
            system=(
                f"You are a seller agent negotiating to sell {seller_params['asset']}. "
                f"Your floor price is {seller_params['floor_price']}. "
                f"Your asking price is {seller_params['ask_price']}. "
                f"Quantity available: {seller_params['quantity']}. "
                "Respond ONLY with valid JSON: "
                '{"price": float, "quantity": float, "accept": bool, "counter": float}'
            ),
            messages=[{"role": "user", "content": f"Buyer offers: {buyer_text}"}],
        )
        seller_text = seller_response.content[0].text.strip()

        try:
            buyer_json = json.loads(buyer_text)
            seller_json = json.loads(seller_text)
        except json.JSONDecodeError:
            continue

        if buyer_json.get("accept") or seller_json.get("accept"):
            agreed_price = buyer_json.get("price", seller_json.get("price"))
            quantity = buyer_json.get("quantity", seller_params["quantity"])
            return {
                "status": "matched",
                "agreed_price": agreed_price,
                "quantity": quantity,
                "rounds": round_num + 1,
                "attestation": "MOCK_ATTESTATION_TODO",
                "message": f"Deal agreed in round {round_num + 1}.",
            }

    return {
        "status": "no_match",
        "rounds": 5,
        "agreed_price": None,
        "quantity": None,
        "attestation": "MOCK_ATTESTATION_TODO",
        "message": "No agreement reached after 5 rounds.",
    }
