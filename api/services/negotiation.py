import json
import re

import anthropic

from api.config import AGENT_MODEL, ANTHROPIC_API_KEY

_client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None

# Strip ```json … ``` code fences if Claude wraps the response.
_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*(.+?)\s*```\s*$", re.DOTALL)


def _parse_json(text: str) -> dict | None:
    text = text.strip()
    m = _FENCE_RE.match(text)
    if m:
        text = m.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _buyer_system(p: dict) -> str:
    return (
        f"You are a buyer agent in a sealed 5-round negotiation. "
        f"You want to buy {p['quantity']} of {p['asset']}.\n\n"
        f"PRICING:\n"
        f"- Target price (ideal): {p['target_price']}\n"
        f"- Maximum price (HARD CEILING — never exceed): {p['max_price']}\n\n"
        f"STRATEGY — you have 5 rounds, then the deal dies:\n"
        f"- Round 1: open near your target ({p['target_price']}).\n"
        f"- Each later round: move your offer UP by roughly "
        f"({p['max_price']} - {p['target_price']}) / 4.\n"
        f"- By round 4-5 you should be at or just under your maximum.\n"
        f"- Do NOT accept before round 3 — haggle for at least 2 full rounds "
        f"even if a deal looks possible earlier. This is mandatory.\n"
        f"- In round 3 or later, ACCEPT (set \"accept\": true) when the seller's "
        f"most recent counter is at or below your maximum ({p['max_price']}).\n\n"
        f"OUTPUT FORMAT — respond with ONLY a single-line JSON object, no prose, "
        f"no markdown fences:\n"
        f'{{"price": <float>, "quantity": <float>, "accept": <bool>}}'
    )


def _seller_system(p: dict) -> str:
    return (
        f"You are a seller agent in a sealed 5-round negotiation. "
        f"You want to sell {p['quantity']} of {p['asset']}.\n\n"
        f"PRICING:\n"
        f"- Ask price (ideal): {p['ask_price']}\n"
        f"- Floor price (HARD FLOOR — never go below): {p['floor_price']}\n\n"
        f"STRATEGY — you have 5 rounds, then the deal dies:\n"
        f"- Round 1: counter near your ask ({p['ask_price']}).\n"
        f"- Each later round: move your counter DOWN by roughly "
        f"({p['ask_price']} - {p['floor_price']}) / 4.\n"
        f"- By round 4-5 you should be at or just above your floor.\n"
        f"- Do NOT accept before round 3 — haggle for at least 2 full rounds "
        f"even if a deal looks possible earlier. This is mandatory.\n"
        f"- In round 3 or later, ACCEPT (set \"accept\": true) when the buyer's "
        f"most recent offer is at or above your floor ({p['floor_price']}).\n\n"
        f"OUTPUT FORMAT — respond with ONLY a single-line JSON object, no prose, "
        f"no markdown fences:\n"
        f'{{"price": <float>, "quantity": <float>, "accept": <bool>}}'
    )


async def run_negotiation(buyer_params: dict, seller_params: dict) -> dict:
    """
    Run sealed negotiation between buyer and seller agents (max 5 rounds).
    Falls back to a deterministic simulator when ANTHROPIC_API_KEY is not set.
    Phase 2: runs inside Phala Cloud TDX.
    """
    if _client is None:
        return _simulate_negotiation(buyer_params, seller_params)
    return await _live_negotiation(buyer_params, seller_params)


def _simulate_negotiation(buyer_params: dict, seller_params: dict) -> dict:
    """
    Deterministic mock: meets in the middle if ranges overlap, else no_match.
    attestation field is set to SIMULATED_NO_API_KEY so it's grep-safe in logs.
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
    from api.services.tee import build_report_data, get_attestation

    buyer_system = _buyer_system(buyer_params)
    seller_system = _seller_system(seller_params)

    # Shared transcript visible to both agents — fixes the "buyer never sees
    # seller's counter" bug that prevented convergence.
    exchanges: list[str] = []
    last_seller_price: float | None = None

    for round_num in range(5):
        rounds_left = 5 - round_num
        transcript = "\n".join(exchanges) if exchanges else "(opening round — no offers yet)"

        # ── BUYER TURN ──────────────────────────────────────────────────────
        buyer_msg = (
            f"Round {round_num + 1} of 5 ({rounds_left} rounds remain).\n"
            f"Negotiation so far:\n{transcript}\n\n"
            f"Make your move."
        )
        buyer_resp = await _client.messages.create(
            model=AGENT_MODEL,
            max_tokens=200,
            system=buyer_system,
            messages=[{"role": "user", "content": buyer_msg}],
        )
        buyer_json = _parse_json(buyer_resp.content[0].text)
        if buyer_json is None:
            exchanges.append(f"R{round_num + 1} buyer: <invalid JSON>")
            continue
        exchanges.append(
            f"R{round_num + 1} buyer: price={buyer_json.get('price')}, "
            f"accept={buyer_json.get('accept')}"
        )

        # Buyer accepting only counts from round 2+ (needs a seller counter to accept)
        if buyer_json.get("accept") and last_seller_price is not None:
            result = {
                "status": "matched",
                "agreed_price": last_seller_price,
                "quantity": buyer_json.get("quantity", seller_params["quantity"]),
                "rounds": round_num + 1,
                "message": f"Buyer accepted seller's counter in round {round_num + 1}.",
            }
            report_data = build_report_data(result)
            result["attestation"] = await get_attestation(report_data)
            return result

        # ── SELLER TURN ─────────────────────────────────────────────────────
        seller_msg = (
            f"Round {round_num + 1} of 5 ({rounds_left} rounds remain).\n"
            f"Negotiation so far:\n" + "\n".join(exchanges) + "\n\n"
            f"Respond to the buyer."
        )
        seller_resp = await _client.messages.create(
            model=AGENT_MODEL,
            max_tokens=200,
            system=seller_system,
            messages=[{"role": "user", "content": seller_msg}],
        )
        seller_json = _parse_json(seller_resp.content[0].text)
        if seller_json is None:
            exchanges.append(f"R{round_num + 1} seller: <invalid JSON>")
            continue
        exchanges.append(
            f"R{round_num + 1} seller: counter={seller_json.get('price')}, "
            f"accept={seller_json.get('accept')}"
        )
        last_seller_price = seller_json.get("price")

        # Seller accepts buyer's just-made offer
        if seller_json.get("accept"):
            result = {
                "status": "matched",
                "agreed_price": buyer_json.get("price"),
                "quantity": buyer_json.get("quantity", seller_params["quantity"]),
                "rounds": round_num + 1,
                "message": f"Seller accepted buyer's offer in round {round_num + 1}.",
            }
            report_data = build_report_data(result)
            result["attestation"] = await get_attestation(report_data)
            return result

    result = {
        "status": "no_match",
        "rounds": 5,
        "agreed_price": None,
        "quantity": None,
        "message": "No agreement reached after 5 rounds.",
    }
    report_data = build_report_data(result)
    result["attestation"] = await get_attestation(report_data)
    return result
