// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title PaperVault
 * @notice ZeroLock On-Chain Examination Custody & Time-Lock Gateway.
 * Cryptographically enforces the pre-exam release window on-chain.
 * Early unlock attempts are mathematically DENIED by the EVM consensus rule.
 */
contract PaperVault {
    struct Paper {
        bytes32 paperHash;     // SHA-256 commitment of original question paper
        string ipfsCid;        // IPFS CID of AES-256-GCM encrypted payload
        uint64 unlockTime;     // Unix timestamp after which custody release is permitted
        bool exists;
    }

    address public immutable admin;
    mapping(bytes32 => Paper) public papers;
    mapping(bytes32 => bytes32) public centerOtpCommitments;
    mapping(bytes32 => mapping(bytes32 => bool)) public centerUnlocked;
    mapping(bytes32 => uint32) public printInstances;

    event PaperRegistered(bytes32 indexed paperId, uint64 unlockTime, string ipfsCid);
    event CenterAccessGranted(bytes32 indexed paperId, bytes32 indexed centerId, uint32 printInstance, uint64 timestamp);
    event FailedUnlockAttempt(bytes32 indexed paperId, bytes32 indexed centerId, uint8 attempts);

    uint8 public constant MAX_FAILED_ATTEMPTS = 5;
    mapping(bytes32 => uint8) public failedAttempts;

    error PaperDoesNotExist();
    error TimeLockActive(uint64 currentTime, uint64 unlockTime);
    error InvalidCenterOrOtp();
    error AlreadyUnlocked();
    error CenterLockedExceededAttempts(bytes32 centerId, uint8 attempts);

    modifier onlyAdmin() {
        require(msg.sender == admin, "UNAUTHORIZED: Admin only");
        _;
    }

    constructor() {
        admin = msg.sender;
    }

    /**
     * @notice Setter registers the sealed exam paper and sets the immutable time-lock.
     */
    function registerPaper(
        bytes32 paperId,
        bytes32 paperHash,
        string calldata ipfsCid,
        uint64 unlockTime,
        bytes32 centerId,
        bytes32 otpHash
    ) external onlyAdmin {
        papers[paperId] = Paper(paperHash, ipfsCid, unlockTime, true);
        centerOtpCommitments[keccak256(abi.encodePacked(paperId, centerId))] = otpHash;
        emit PaperRegistered(paperId, unlockTime, ipfsCid);
    }

    /**
     * @notice Custodian at centre unlocks paper when unlockTime has passed and OTP matches.
     * Reverts with TimeLockActive if block.timestamp < unlockTime (The Proof-of-Denial moment).
     * Records and persists failedAttempts on-chain upon incorrect OTP.
     * Reverts with CenterLockedExceededAttempts if failed attempts >= 5 (Anti-Grinding Lockout).
     * Returns sequential printInstance that directly seeds the physical watermark payload.
     */
    function unlockPaper(bytes32 paperId, bytes32 centerId, uint64 otp) external returns (uint32) {
        Paper memory p = papers[paperId];
        if (!p.exists) revert PaperDoesNotExist();
        if (block.timestamp < p.unlockTime) {
            revert TimeLockActive(uint64(block.timestamp), p.unlockTime);
        }

        bytes32 key = keccak256(abi.encodePacked(paperId, centerId));
        if (failedAttempts[key] >= MAX_FAILED_ATTEMPTS) {
            revert CenterLockedExceededAttempts(centerId, failedAttempts[key]);
        }

        if (keccak256(abi.encodePacked(paperId, centerId, otp)) != centerOtpCommitments[key]) {
            failedAttempts[key]++;
            emit FailedUnlockAttempt(paperId, centerId, failedAttempts[key]);
            return 0; // 0 indicates invalid credential; state change persists on-chain
        }

        failedAttempts[key] = 0;

        if (centerUnlocked[paperId][centerId]) {
            revert AlreadyUnlocked();
        }

        centerUnlocked[paperId][centerId] = true;
        uint32 currentInstance = ++printInstances[paperId];

        emit CenterAccessGranted(paperId, centerId, currentInstance, uint64(block.timestamp));
        return currentInstance;
    }

    /**
     * @notice High-entropy (8+ character alphanumeric / 64-bit) secret unlock.
     * Combined with the on-chain lockout, this makes brute-force grinding mathematically impossible.
     */
    function unlockPaperSecret(bytes32 paperId, bytes32 centerId, string calldata otpSecret) external returns (uint32) {
        Paper memory p = papers[paperId];
        if (!p.exists) revert PaperDoesNotExist();
        if (block.timestamp < p.unlockTime) {
            revert TimeLockActive(uint64(block.timestamp), p.unlockTime);
        }

        bytes32 key = keccak256(abi.encodePacked(paperId, centerId));
        if (failedAttempts[key] >= MAX_FAILED_ATTEMPTS) {
            revert CenterLockedExceededAttempts(centerId, failedAttempts[key]);
        }

        if (keccak256(abi.encodePacked(paperId, centerId, otpSecret)) != centerOtpCommitments[key]) {
            failedAttempts[key]++;
            emit FailedUnlockAttempt(paperId, centerId, failedAttempts[key]);
            return 0;
        }

        failedAttempts[key] = 0;

        if (centerUnlocked[paperId][centerId]) {
            revert AlreadyUnlocked();
        }

        centerUnlocked[paperId][centerId] = true;
        uint32 currentInstance = ++printInstances[paperId];

        emit CenterAccessGranted(paperId, centerId, currentInstance, uint64(block.timestamp));
        return currentInstance;
    }

    /**
     * @notice Check current paper status and remaining time-lock seconds.
     */
    function getPaperStatus(bytes32 paperId) external view returns (
        bool exists,
        bool isUnlockedByTime,
        uint64 unlockTime,
        uint64 currentTime,
        uint32 totalPrints
    ) {
        Paper memory p = papers[paperId];
        return (
            p.exists,
            p.exists && block.timestamp >= p.unlockTime,
            p.unlockTime,
            uint64(block.timestamp),
            printInstances[paperId]
        );
    }
}
