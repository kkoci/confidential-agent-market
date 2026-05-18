"""
web3.py client for ConfidentialEscrow.sol on Kite testnet.

Only active when ESCROW_CONTRACT_ADDRESS and AGENT_PRIVATE_KEY are set.
Call is_available() before using any other method.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from web3 import AsyncWeb3
from web3.types import TxReceipt

from api.config import AGENT_PRIVATE_KEY, ESCROW_CONTRACT_ADDRESS, KITE_CHAIN_ID, KITE_RPC_URL, TESTNET_ASSET

if TYPE_CHECKING:
    pass

_ERC20_ABI: list[dict] = [
    {
        "inputs": [
            {"internalType": "address", "name": "spender", "type": "address"},
            {"internalType": "uint256", "name": "amount",  "type": "uint256"},
        ],
        "name": "approve",
        "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
        "stateMutability": "nonpayable",
        "type": "function",
    },
]

# ABI generated from ConfidentialEscrow.sol — keep in sync with the contract.
_ABI: list[dict] = [
    # deposit(bytes32 escrowId, address seller, uint256 amount)
    {
        "inputs": [
            {"internalType": "bytes32", "name": "escrowId", "type": "bytes32"},
            {"internalType": "address", "name": "seller",   "type": "address"},
            {"internalType": "uint256", "name": "amount",   "type": "uint256"},
        ],
        "name": "deposit",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    # settle(bytes32 escrowId, bytes attestation)
    {
        "inputs": [
            {"internalType": "bytes32", "name": "escrowId",    "type": "bytes32"},
            {"internalType": "bytes",   "name": "attestation", "type": "bytes"},
        ],
        "name": "settle",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    # cancel(bytes32 escrowId)
    {
        "inputs": [
            {"internalType": "bytes32", "name": "escrowId", "type": "bytes32"},
        ],
        "name": "cancel",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    # getEscrow(bytes32 escrowId) returns (Escrow)
    {
        "inputs": [
            {"internalType": "bytes32", "name": "escrowId", "type": "bytes32"},
        ],
        "name": "getEscrow",
        "outputs": [
            {
                "components": [
                    {"internalType": "address", "name": "buyer",     "type": "address"},
                    {"internalType": "address", "name": "seller",    "type": "address"},
                    {"internalType": "uint256", "name": "amount",    "type": "uint256"},
                    {"internalType": "bool",    "name": "settled",   "type": "bool"},
                    {"internalType": "bool",    "name": "cancelled", "type": "bool"},
                ],
                "internalType": "struct ConfidentialEscrow.Escrow",
                "name": "",
                "type": "tuple",
            }
        ],
        "stateMutability": "view",
        "type": "function",
    },
    # EscrowCreated event
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True,  "internalType": "bytes32", "name": "escrowId", "type": "bytes32"},
            {"indexed": True,  "internalType": "address", "name": "buyer",    "type": "address"},
            {"indexed": True,  "internalType": "address", "name": "seller",   "type": "address"},
            {"indexed": False, "internalType": "uint256", "name": "amount",   "type": "uint256"},
        ],
        "name": "EscrowCreated",
        "type": "event",
    },
    # EscrowSettled event
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True,  "internalType": "bytes32", "name": "escrowId",    "type": "bytes32"},
            {"indexed": False, "internalType": "bytes",   "name": "attestation", "type": "bytes"},
            {"indexed": False, "internalType": "uint256", "name": "amount",      "type": "uint256"},
        ],
        "name": "EscrowSettled",
        "type": "event",
    },
    # EscrowCancelled event
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True,  "internalType": "bytes32", "name": "escrowId",   "type": "bytes32"},
            {"indexed": False, "internalType": "address", "name": "refundedTo", "type": "address"},
            {"indexed": False, "internalType": "uint256", "name": "amount",     "type": "uint256"},
        ],
        "name": "EscrowCancelled",
        "type": "event",
    },
]


def is_available() -> bool:
    """True when both the contract address and agent private key are configured."""
    return bool(ESCROW_CONTRACT_ADDRESS and AGENT_PRIVATE_KEY)


def _make_escrow_id(bid_id: str, ask_id: str) -> bytes:
    """Deterministic 32-byte escrow ID from bid + ask UUIDs."""
    w3 = AsyncWeb3()
    return w3.keccak(text=f"{bid_id}:{ask_id}")


class EscrowService:
    """
    Async client for ConfidentialEscrow.sol.

    Usage:
        if is_available():
            svc = EscrowService()
            tx = await svc.settle(bid_id, ask_id, attestation_bytes)
    """

    def __init__(self) -> None:
        self._w3 = AsyncWeb3(AsyncWeb3.AsyncHTTPProvider(KITE_RPC_URL))
        self._account = self._w3.eth.account.from_key(AGENT_PRIVATE_KEY)
        self._contract = self._w3.eth.contract(
            address=AsyncWeb3.to_checksum_address(ESCROW_CONTRACT_ADDRESS),
            abi=_ABI,
        )
        self._kxusd = self._w3.eth.contract(
            address=AsyncWeb3.to_checksum_address(TESTNET_ASSET),
            abi=_ERC20_ABI,
        )

    async def _send(self, fn, gas: int = 200_000) -> str:
        """Build, sign, and broadcast a contract transaction. Returns tx hash."""
        # Use "pending" state so sequential calls get consecutive nonces even
        # before earlier txs are mined.
        nonce = await self._w3.eth.get_transaction_count(self._account.address, "pending")
        gas_price = await self._w3.eth.gas_price

        tx = await fn.build_transaction(
            {
                "from":     self._account.address,
                "nonce":    nonce,
                "gas":      gas,
                "gasPrice": gas_price,
                "chainId":  KITE_CHAIN_ID,
            }
        )
        signed = self._account.sign_transaction(tx)
        tx_hash = await self._w3.eth.send_raw_transaction(signed.raw_transaction)
        return tx_hash.hex()

    async def settle(self, bid_id: str, ask_id: str, attestation: str | bytes) -> str:
        """
        Release escrowed USDT to the seller.

        :param bid_id:       Bid order UUID (used to derive escrow ID)
        :param ask_id:       Ask order UUID (used to derive escrow ID)
        :param attestation:  DCAP TDX quote — hex string or bytes
        :returns:            Transaction hash (0x-prefixed hex)
        """
        escrow_id = _make_escrow_id(bid_id, ask_id)
        if isinstance(attestation, str):
            # NOTE: str.lstrip("0x") strips the CHARACTER SET {0, x} from the
            # left, which mangles any hex starting with '0'. Use removeprefix
            # for the literal '0x' prefix instead.
            attestation = bytes.fromhex(attestation.removeprefix("0x"))
        fn = self._contract.functions.settle(escrow_id, attestation)
        return await self._send(fn, gas=300_000)

    async def cancel(self, bid_id: str, ask_id: str) -> str:
        """Cancel escrow and refund buyer."""
        escrow_id = _make_escrow_id(bid_id, ask_id)
        fn = self._contract.functions.cancel(escrow_id)
        return await self._send(fn)

    async def deposit(
        self, bid_id: str, ask_id: str, seller_address: str, amount_wei: int
    ) -> str:
        """Deposit USDT into escrow (called by buyer before negotiation)."""
        escrow_id = _make_escrow_id(bid_id, ask_id)
        seller = AsyncWeb3.to_checksum_address(seller_address)
        fn = self._contract.functions.deposit(escrow_id, seller, amount_wei)
        return await self._send(fn, gas=150_000)

    async def approve_and_deposit(
        self, bid_id: str, ask_id: str, seller_address: str, amount_wei: int
    ) -> tuple[str, str]:
        """
        KXUSD.approve(escrow, amount) then escrow.deposit(escrowId, seller, amount).

        Uses pending-nonce sequencing so both txs can be submitted without
        waiting for the approve to be mined first.

        Returns (approve_tx_hash, deposit_tx_hash).
        """
        escrow_addr = AsyncWeb3.to_checksum_address(ESCROW_CONTRACT_ADDRESS)
        approve_fn = self._kxusd.functions.approve(escrow_addr, amount_wei)
        approve_tx = await self._send(approve_fn, gas=60_000)
        deposit_tx = await self.deposit(bid_id, ask_id, seller_address, amount_wei)
        return approve_tx, deposit_tx

    async def get_escrow(self, bid_id: str, ask_id: str) -> dict:
        """Read escrow state (view, no gas)."""
        escrow_id = _make_escrow_id(bid_id, ask_id)
        result = await self._contract.functions.getEscrow(escrow_id).call()
        buyer, seller, amount, settled, cancelled = result
        return {
            "buyer":     buyer,
            "seller":    seller,
            "amount":    amount,
            "settled":   settled,
            "cancelled": cancelled,
        }
