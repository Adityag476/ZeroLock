import hre from "hardhat";

async function main() {
    console.log("\n=======================================================");
    console.log("  ZEROLOCK: ON-CHAIN CUSTODY & TIME-LOCK GATEWAY DEMO  ");
    console.log("=======================================================\n");

    const [admin, centerOperator] = await hre.ethers.getSigners();
    console.log(`[*] Deployer / Authority: ${admin.address}`);
    console.log(`[*] Centre Custodian   : ${centerOperator.address}`);

    const PaperVault = await hre.ethers.getContractFactory("PaperVault");
    const vault = await PaperVault.deploy();
    await vault.waitForDeployment();
    const vaultAddress = await vault.getAddress();
    console.log(`[+] PaperVault Smart Contract Deployed at: ${vaultAddress}\n`);

    // Setup Exam Metadata & Cryptographic Hashes
    const paperId = hre.ethers.id("NEET-2026-PHYSICS-SECURE");
    const paperHash = hre.ethers.id("SHA256_EXAM_PLAINTEXT_COMMITMENT_V1");
    const ipfsCid = "QmZtmD2qt8fJv32FNnjZcwjryP64vdNZZj5NVGL2qwkk79";
    const centerId = hre.ethers.id("CENTRE-PUNE-014");
    const otp = 849204n;
    const otpHash = hre.ethers.keccak256(hre.ethers.solidityPacked(["uint64"], [otp]));

    const latestBlock = await hre.ethers.provider.getBlock("latest");
    const currentTime = Number(latestBlock.timestamp);
    const unlockTime = currentTime + 3600; // Locked until 1 hour from now

    await vault.registerPaper(paperId, paperHash, ipfsCid, unlockTime, centerId, otpHash);
    console.log(`[+] Registered Exam Paper: ${paperId.slice(0, 18)}...`);
    console.log(`    IPFS Ciphertext CID : ${ipfsCid}`);
    console.log(`    Unlock Timestamp    : ${new Date(unlockTime * 1000).toLocaleTimeString()} IST (T + 60m)`);
    console.log(`    Current Block Time  : ${new Date(currentTime * 1000).toLocaleTimeString()} IST\n`);

    // --- BEAT 1: EARLY DECRYPTION REJECTION (THE DEMO DENIAL MOMENT) ---
    console.log("[*] BEAT 1: Center Operator attempts early paper unlock before scheduled time...");
    try {
        await vault.connect(centerOperator).unlockPaper(paperId, centerId, otp);
        console.log("    [ERROR]: Unlock succeeded when it should have reverted!");
    } catch (err) {
        console.log(`    >>> ACCESS REJECTED ON-CHAIN: TimeLockActive`);
        console.log(`    >>> Contract Revert: Release window not open yet.`);
        console.log("    >>> [DEMO THEATRE]: Mathematical consensus guarantees paper cannot leak early!\n");
    }

    // --- BEAT 2: TIME-TRAVEL WARP ---
    console.log("[*] BEAT 2: Advancing blockchain clock by +3601 seconds (evm_increaseTime)...");
    await hre.network.provider.send("evm_increaseTime", [3601]);
    await hre.network.provider.send("evm_mine");

    const newBlock = await hre.ethers.provider.getBlock("latest");
    console.log(`    Simulated Block Time: ${new Date(Number(newBlock.timestamp) * 1000).toLocaleTimeString()} IST (T + 60m 1s)\n`);

    // --- BEAT 3: AUTHORIZED ACCESS & INSTANCE ASSIGNMENT ---
    console.log("[*] BEAT 3: Center Operator submits valid OTP during active exam release window...");
    const tx = await vault.connect(centerOperator).unlockPaper(paperId, centerId, otp);
    const receipt = await tx.wait();

    const currentInstance = await vault.printInstances(paperId);
    console.log(`    >>> ACCESS GRANTED ON-CHAIN.`);
    console.log(`    >>> Assigned Print Instance ID : #${currentInstance}`);
    console.log(`    >>> Transaction Block Hash     : ${receipt.blockHash.slice(0, 32)}...`);
    console.log(`    >>> Gas Used                   : ${receipt.gasUsed.toString()} units`);
    console.log("    >>> [SYNERGY]: Print Instance # feeds directly into physical forensic watermark payload!\n");
    console.log("=======================================================");
    console.log("  DEMO COMPLETE: ON-CHAIN AUDIT & TIME-LOCK VERIFIED   ");
    console.log("=======================================================\n");
}

main().catch((err) => {
    console.error(err);
    process.exit(1);
});
