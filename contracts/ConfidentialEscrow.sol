// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title ConfidentialEscrow
 * @notice Holds KXUSD in escrow and releases funds only after the
 *         authorised TEE agent submits a TEE attestation on settlement.
 *
 * Deployment target: Kite testnet (chain ID 2368)
 * Payment token:     Kite X402 USD (KXUSD)  0x1b7425d288ea676FCBc65c29711fccF0B6D5c293
 *
 * Flow:
 *   1. Buyer calls deposit() — KXUSD transferred into this contract.
 *   2. TEE agent runs sealed negotiation off-chain (Phala Cloud TDX).
 *   3. On match, agent calls settle() with a DCAP attestation quote.
 *      The quote is stored on-chain for auditability.
 *   4. KXUSD is transferred to the seller.
 *   5. On no-match or timeout, agent or buyer calls cancel() → KXUSD refunded.
 *
 * Note: attestation quote verification is currently off-chain (agent is trusted).
 * A future upgrade will call an on-chain DCAP verifier (DealProof pattern).
 */

interface IERC20 {
    function transferFrom(address from, address to, uint256 amount) external returns (bool);
    function transfer(address to, uint256 amount) external returns (bool);
}

contract ConfidentialEscrow {
    /// @notice Test USDT token address (18 decimals, Kite testnet)
    address public immutable USDT;

    /// @notice TEE agent wallet — only this address may call settle/cancel
    address public immutable agent;

    struct Escrow {
        address buyer;
        address seller;
        uint256 amount;    // in USDT wei (18 decimals)
        bool    settled;
        bool    cancelled;
    }

    /// @dev escrowId → escrow state; escrowId = keccak256(bidId + askId) in practice
    mapping(bytes32 => Escrow) public escrows;

    // ── Events ────────────────────────────────────────────────────────────────

    event EscrowCreated(
        bytes32 indexed escrowId,
        address indexed buyer,
        address indexed seller,
        uint256 amount
    );

    event EscrowSettled(
        bytes32 indexed escrowId,
        bytes   attestation,   // full DCAP TDX quote stored for auditability
        uint256 amount
    );

    event EscrowCancelled(
        bytes32 indexed escrowId,
        address refundedTo,
        uint256 amount
    );

    // ── Errors ────────────────────────────────────────────────────────────────

    error EscrowAlreadyExists(bytes32 escrowId);
    error EscrowNotFound(bytes32 escrowId);
    error EscrowAlreadyFinalized(bytes32 escrowId);
    error Unauthorized();
    error TransferFailed();

    // ── Constructor ───────────────────────────────────────────────────────────

    constructor(address _usdt, address _agent) {
        require(_usdt  != address(0), "zero usdt");
        require(_agent != address(0), "zero agent");
        USDT  = _usdt;
        agent = _agent;
    }

    // ── External functions ────────────────────────────────────────────────────

    /**
     * @notice Buyer locks USDT into escrow.
     * @dev    Caller must have approved this contract on the USDT token first.
     * @param  escrowId  Unique identifier derived from bid + ask IDs
     * @param  seller    Address that will receive funds on settlement
     * @param  amount    Amount of USDT (in 18-decimal wei) to escrow
     */
    function deposit(bytes32 escrowId, address seller, uint256 amount) external {
        if (escrows[escrowId].buyer != address(0)) revert EscrowAlreadyExists(escrowId);
        if (!IERC20(USDT).transferFrom(msg.sender, address(this), amount)) revert TransferFailed();

        escrows[escrowId] = Escrow({
            buyer:     msg.sender,
            seller:    seller,
            amount:    amount,
            settled:   false,
            cancelled: false
        });

        emit EscrowCreated(escrowId, msg.sender, seller, amount);
    }

    /**
     * @notice TEE agent releases escrowed USDT to the seller.
     * @dev    Only the authorised agent address may call this.
     *         The attestation quote is stored on-chain for auditability.
     * @param  escrowId    Escrow to settle
     * @param  attestation Raw DCAP TDX quote bytes from the Phala CVM
     */
    function settle(bytes32 escrowId, bytes calldata attestation) external {
        if (msg.sender != agent) revert Unauthorized();

        Escrow storage e = escrows[escrowId];
        if (e.buyer == address(0))    revert EscrowNotFound(escrowId);
        if (e.settled || e.cancelled) revert EscrowAlreadyFinalized(escrowId);

        e.settled = true;
        if (!IERC20(USDT).transfer(e.seller, e.amount)) revert TransferFailed();

        emit EscrowSettled(escrowId, attestation, e.amount);
    }

    /**
     * @notice Cancel escrow and refund USDT to buyer.
     * @dev    Callable by the buyer or the TEE agent (e.g. on negotiation failure).
     * @param  escrowId  Escrow to cancel
     */
    function cancel(bytes32 escrowId) external {
        Escrow storage e = escrows[escrowId];
        if (e.buyer == address(0))                       revert EscrowNotFound(escrowId);
        if (msg.sender != e.buyer && msg.sender != agent) revert Unauthorized();
        if (e.settled || e.cancelled)                    revert EscrowAlreadyFinalized(escrowId);

        e.cancelled = true;
        if (!IERC20(USDT).transfer(e.buyer, e.amount)) revert TransferFailed();

        emit EscrowCancelled(escrowId, e.buyer, e.amount);
    }

    /**
     * @notice Read escrow state without modifying it.
     */
    function getEscrow(bytes32 escrowId) external view returns (Escrow memory) {
        return escrows[escrowId];
    }
}
