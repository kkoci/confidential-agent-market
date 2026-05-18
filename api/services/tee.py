"""
TEE attestation service — Intel TDX via Phala Cloud.

Inside a Phala Cloud CVM the dstack guest-agent listens on a Unix socket.
Modern Phala (dstack 0.5+) exposes /var/run/dstack.sock; older deployments
used /var/run/tappd.sock. This module checks both so the service works
across versions, with a clearly-marked mock for non-CVM environments.
"""
import hashlib
import json
import logging
import os

import httpx

from api.config import PHALA_CVM_ENDPOINT

logger = logging.getLogger(__name__)

# Phala guest-agent HTTP fallback (rarely used; the socket is the primary path)
_TAPPD_HTTP = PHALA_CVM_ENDPOINT or "http://localhost:8545"

# Socket paths to probe — modern first, legacy second
_DSTACK_SOCKET = "/var/run/dstack.sock"
_TAPPD_SOCKET = "/var/run/tappd.sock"

# Legacy tappd RPC path (only used by AsyncTappdClient fallback)
_QUOTE_PATH = "/prpc/Tappd.TdxQuote"


def _socket_path() -> str | None:
    """Return the first existing guest-agent socket path, or None."""
    if os.path.exists(_DSTACK_SOCKET):
        return _DSTACK_SOCKET
    if os.path.exists(_TAPPD_SOCKET):
        return _TAPPD_SOCKET
    return None


def is_in_cvm() -> bool:
    """Return True if a Phala guest-agent socket exists (i.e. we're inside a CVM)."""
    return _socket_path() is not None or bool(PHALA_CVM_ENDPOINT)


def build_report_data(negotiation_result: dict) -> bytes:
    """
    Produce 64 bytes of deterministic report data from a negotiation result.
    First 32 bytes: SHA-256 of the canonical JSON of the result fields.
    Last 32 bytes: zeroes (reserved for future extensions).
    """
    canonical = json.dumps(
        {
            "status": negotiation_result.get("status"),
            "agreed_price": str(negotiation_result.get("agreed_price", "")),
            "quantity": str(negotiation_result.get("quantity", "")),
            "asset": negotiation_result.get("asset", ""),
            "rounds": negotiation_result.get("rounds", 0),
        },
        sort_keys=True,
    ).encode()
    digest = hashlib.sha256(canonical).digest()  # 32 bytes
    return digest + bytes(32)                     # pad to 64 bytes (TDX report data field)


async def _quote_via_dstack_sdk(report_data: bytes) -> tuple[str | None, str | None]:
    """
    Get a TDX quote via dstack-sdk's AsyncDstackClient. Returns (quote, error).

    Pass the socket path explicitly so we don't depend on the SDK's default
    (which moved from /var/run/tappd.sock to /var/run/dstack.sock in 0.5.x).
    """
    try:
        from dstack_sdk import AsyncDstackClient  # type: ignore[import]
    except ImportError as exc:
        return None, f"import:AsyncDstackClient:{exc}"

    sock = _socket_path()
    if sock is None:
        return None, "no-socket-found"

    try:
        client = AsyncDstackClient(endpoint=sock)
        result = await client.get_quote(report_data)
        quote = getattr(result, "quote", None)
        if quote:
            logger.info("dstack-sdk returned quote (%d chars) via %s", len(quote), sock)
            return quote, None
        return None, f"empty-quote:{type(result).__name__}"
    except Exception as exc:
        logger.exception("dstack-sdk get_quote failed")
        return None, f"{type(exc).__name__}:{exc}"


async def _quote_via_http(report_data: bytes) -> tuple[str | None, str | None]:
    """Try the tappd HTTP endpoint directly. Returns (quote, error_marker)."""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{_TAPPD_HTTP}{_QUOTE_PATH}",
                json={"report_data": report_data.hex()},
            )
            if resp.status_code == 200:
                data = resp.json()
                quote = (
                    data.get("quote")
                    or data.get("tdxQuote")
                    or data.get("tdx_quote")
                )
                if quote:
                    return quote, None
                return None, f"http-200-no-quote:{list(data.keys())[:5]}"
            return None, f"http-{resp.status_code}:{resp.text[:120]}"
    except Exception as exc:
        return None, f"http-exc:{type(exc).__name__}:{exc}"


async def get_attestation(report_data: bytes) -> str:
    """
    Return a TDX DCAP quote as a hex string.

    Tries (in order):
      1. dstack-sdk Python package (Phala-provided SDK)
      2. Direct HTTP to tappd daemon
      3. Clearly-marked mock for dev / non-CVM environments

    On failure inside a CVM, the returned marker embeds the underlying error
    so it can be surfaced to API consumers even when container logs aren't
    reachable.
    """
    if is_in_cvm():
        quote, sdk_err = await _quote_via_dstack_sdk(report_data)
        if quote:
            return quote

        quote, http_err = await _quote_via_http(report_data)
        if quote:
            return quote

        err = f"sdk={sdk_err}|http={http_err}"
        return f"CVM_QUOTE_FAILED:{report_data[:16].hex()}:{err}"

    return f"NOT_IN_CVM:{report_data[:16].hex()}"
