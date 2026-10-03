// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title ExamVault
 * @notice ZeroLeak — Forensic Exam Custody Contract
 *
 * Stores encrypted exam paper metadata on-chain.
 * Releases decryption permission only after the scheduled unlock time.
 * All access events are logged as immutable on-chain events.
 *
 * Demo:
 *   - Early call to unlock() → REVERT "TIMELOCK: release window not open"
 *   - After hardhat_increaseTime → unlock succeeds → PaperUnlocked emitted
 */
contract ExamVault {

    // -------------------------------------------------------------------------
    // Data structures
    // -------------------------------------------------------------------------

    struct Paper {
        bytes32  contentHash;    // SHA-256 of plaintext PDF (integrity anchor)
        string   ipfsCid;        // Pinata IPFS CID of AES-encrypted PDF
        uint64   unlockTime;     // Unix timestamp: earliest allowed unlock
        bool     registered;
    }

    // -------------------------------------------------------------------------
    // State
    // -------------------------------------------------------------------------

    address public admin;

    /// paperId → Paper metadata
    mapping(bytes32 => Paper) public papers;

    /// paperId → centreId → has this centre been granted access?
    mapping(bytes32 => mapping(bytes32 => bool)) public accessGranted;

    /// paperId → centreId → keccak256(centreId ++ otp)  (set at registration)
    mapping(bytes32 => mapping(bytes32 => bytes32)) public otpHash;

    /// paperId → sequential print-instance counter per centre
    mapping(bytes32 => mapping(bytes32 => uint32)) public printCount;

    /// Anti-grinding lockout: max 5 failed attempts per centre
    uint8 public constant MAX_FAILED_ATTEMPTS = 5;
    mapping(bytes32 => mapping(bytes32 => uint8)) public failedAttempts;

    // -------------------------------------------------------------------------
    // Events (immutable audit trail)
    // -------------------------------------------------------------------------

    event PaperRegistered(
        bytes32 indexed paperId,
        bytes32 contentHash,
        string  ipfsCid,
        uint64  unlockTime
    );

    event CentreAuthorized(
        bytes32 indexed paperId,
        bytes32 indexed centreId
    );

    event PaperUnlocked(
        bytes32 indexed paperId,
        bytes32 indexed centreId,
        uint64  unlockedAt,
        uint32  printInstance
    );

    event EarlyUnlockAttempt(
        bytes32 indexed paperId,
        bytes32 indexed centreId,
        uint64  attemptedAt,
        uint64  unlockTime
    );

    // -------------------------------------------------------------------------
    // Modifiers
    // -------------------------------------------------------------------------

    modifier onlyAdmin() {
        require(msg.sender == admin, "ExamVault: caller is not admin");
        _;
    }

    // -------------------------------------------------------------------------
    // Constructor
    // -------------------------------------------------------------------------

    constructor() {
        admin = msg.sender;
    }

    // -------------------------------------------------------------------------
    // Admin: register a paper
    // -------------------------------------------------------------------------

    /**
     * @notice Register a new exam paper with its encrypted IPFS CID and unlock time.
     * @param paperId      Unique identifier (keccak256 of exam name + date)
     * @param contentHash  SHA-256 of the original plaintext PDF
     * @param ipfsCid      IPFS content identifier for the AES-GCM encrypted blob
     * @param unlockTime   Unix timestamp after which centres may unlock
     */
    function registerPaper(
        bytes32 paperId,
        bytes32 contentHash,
        string calldata ipfsCid,
        uint64  unlockTime
    ) external onlyAdmin {
        require(!papers[paperId].registered, "ExamVault: paper already registered");
        require(unlockTime > uint64(block.timestamp), "ExamVault: unlock time must be in the future");

        papers[paperId] = Paper({
            contentHash: contentHash,
            ipfsCid:     ipfsCid,
            unlockTime:  unlockTime,
            registered:  true
        });

        emit PaperRegistered(paperId, contentHash, ipfsCid, unlockTime);
    }

    // -------------------------------------------------------------------------
    // Admin: authorize a centre with an OTP hash
    // -------------------------------------------------------------------------

    /**
     * @notice Whitelist a centre and set its OTP commitment.
     * @param paperId    The exam paper identifier.
     * @param centreId   The centre identifier (bytes32, e.g. keccak256("CENTRE-14")).
     * @param _otpHash   keccak256(abi.encodePacked(centreId, otp)) computed off-chain.
     */
    function authoriseCentre(
        bytes32 paperId,
        bytes32 centreId,
        bytes32 _otpHash
    ) external onlyAdmin {
        require(papers[paperId].registered, "ExamVault: paper not registered");
        otpHash[paperId][centreId] = _otpHash;
        emit CentreAuthorized(paperId, centreId);
    }

    // -------------------------------------------------------------------------
    // Centre: request unlock
    // -------------------------------------------------------------------------

    /**
     * @notice Attempt to unlock a paper for printing.
     *         REVERTS if called before unlockTime ("TIMELOCK: release window not open").
     *         REVERTS if OTP is wrong.
     *         Emits PaperUnlocked with a sequential print instance counter.
     *
     * @param paperId   The exam paper identifier.
     * @param centreId  The centre's identifier.
     * @param otp       The one-time password (plaintext uint64, matched against stored hash).
     *
     * @return printInstance  Sequential print number for this centre (used in stego payload).
     */
    function unlock(
        bytes32 paperId,
        bytes32 centreId,
        uint64  otp
    ) external returns (uint32 printInstance) {
        Paper memory p = papers[paperId];
        require(p.registered, "ExamVault: paper not registered");

        // --- THE TIME-LOCK (demo moment #1 — early call reverts here) ---
        if (uint64(block.timestamp) < p.unlockTime) {
            emit EarlyUnlockAttempt(paperId, centreId, uint64(block.timestamp), p.unlockTime);
            revert("TIMELOCK: release window not open");
        }

        // --- OTP verification with Anti-Grinding Lockout Rate-Limit ---
        bytes32 expected = otpHash[paperId][centreId];
        require(expected != bytes32(0), "ExamVault: centre not authorised for this paper");
        require(failedAttempts[paperId][centreId] < MAX_FAILED_ATTEMPTS, "ExamVault: LOCKED due to exceeding 5 failed attempts");

        if (keccak256(abi.encodePacked(centreId, otp)) != expected) {
            failedAttempts[paperId][centreId] += 1;
            revert("ExamVault: OTP mismatch");
        }
        failedAttempts[paperId][centreId] = 0;

        // --- Increment print counter ---
        printCount[paperId][centreId] += 1;
        printInstance = printCount[paperId][centreId];

        // --- Mark access granted ---
        accessGranted[paperId][centreId] = true;

        emit PaperUnlocked(paperId, centreId, uint64(block.timestamp), printInstance);
        return printInstance;
    }

    // -------------------------------------------------------------------------
    // View helpers
    // -------------------------------------------------------------------------

    function getPaper(bytes32 paperId) external view returns (Paper memory) {
        return papers[paperId];
    }

    function timeUntilUnlock(bytes32 paperId) external view returns (int256) {
        Paper memory p = papers[paperId];
        if (!p.registered) return type(int256).min;
        return int256(uint256(p.unlockTime)) - int256(block.timestamp);
    }

    function transferAdmin(address newAdmin) external onlyAdmin {
        require(newAdmin != address(0), "ExamVault: zero address");
        admin = newAdmin;
    }
}
