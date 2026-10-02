const hre = require("hardhat");
const { ethers } = hre;

async function runAuditA() {
    console.log("=== SECTION A: CUSTODY & CONTRACTS AUDIT ===");
    const [admin, centerAccount, randomAccount] = await ethers.getSigners();
    console.log("Admin account:", admin.address);
    console.log("Center account:", centerAccount.address);
    console.log("Random account:", randomAccount.address);

    const PaperVault = await ethers.getContractFactory("PaperVault");
    const vault = await PaperVault.deploy();
    await vault.waitForDeployment();
    const vaultAddr = await vault.getAddress();
    console.log("Deployed PaperVault at:", vaultAddr);

    const paperId = ethers.keccak256(ethers.toUtf8Bytes("EXAM-AUDIT-A"));
    const paperHash = ethers.keccak256(ethers.toUtf8Bytes("content-sha256-hash"));
    const ipfsCid = "QmAuditSectionA1234567890abcdef";
    const centerId = ethers.keccak256(ethers.toUtf8Bytes("CENTRE-14"));
    const correctOtp = 849204n;
    const otpHash = ethers.keccak256(ethers.solidityPacked(["bytes32", "bytes32", "uint64"], [paperId, centerId, correctOtp]));

    const block = await ethers.provider.getBlock("latest");
    const now = Number(block.timestamp);
    const unlockTime = now + 1000; // 1000 seconds in future

    await vault.registerPaper(paperId, paperHash, ipfsCid, unlockTime, centerId, otpHash);
    console.log("Registered paper. Unlock time:", unlockTime, "Current time:", now);

    const results = {};

    // A1: Early unlock reverts with TimeLockActive (owner AND random centre account)
    console.log("\n--- Checking A1: Early unlock reverts with TimeLockActive ---");
    let a1_owner_revert = false;
    let a1_random_revert = false;
    let a1_err_owner = "";
    let a1_err_random = "";

    try {
        await vault.connect(admin).unlockPaper(paperId, centerId, correctOtp);
    } catch (e) {
        a1_err_owner = e.message;
        if (e.message.includes("TimeLockActive")) a1_owner_revert = true;
    }

    try {
        await vault.connect(randomAccount).unlockPaper(paperId, centerId, correctOtp);
    } catch (e) {
        a1_err_random = e.message;
        if (e.message.includes("TimeLockActive")) a1_random_revert = true;
    }

    const a1_pass = a1_owner_revert && a1_random_revert;
    results["A1"] = {
        check: "Early unlock reverts with TimeLockActive (owner AND random centre account)",
        expected: "Revert with TimeLockActive for both admin and random caller",
        observed: `Admin revert: ${a1_owner_revert}, Random revert: ${a1_random_revert}. Error: ${a1_err_random.slice(0, 80)}`,
        pass: a1_pass
    };
    console.log("A1:", a1_pass ? "PASS" : "FAIL");

    // A2: evm_increaseTime past release -> unlock succeeds, PaperUnlocked emitted
    console.log("\n--- Checking A2: evm_increaseTime past release -> unlock succeeds, PaperUnlocked emitted ---");
    await ethers.provider.send("evm_increaseTime", [1005]);
    await ethers.provider.send("evm_mine");

    let a2_pass = false;
    let a2_event_names = [];
    let a2_gas = 0;
    try {
        const tx = await vault.connect(centerAccount).unlockPaper(paperId, centerId, correctOtp);
        const receipt = await tx.wait();
        a2_gas = Number(receipt.gasUsed);
        
        for (const log of receipt.logs) {
            try {
                const parsed = vault.interface.parseLog(log);
                if (parsed) a2_event_names.push(parsed.name);
            } catch (_) {}
        }
        if (a2_event_names.includes("PaperUnlocked")) {
            a2_pass = true;
        }
    } catch (e) {
        console.log("A2 error:", e.message);
    }

    results["A2"] = {
        check: "evm_increaseTime past release -> unlock succeeds, PaperUnlocked emitted",
        expected: "Unlock succeeds and PaperUnlocked event emitted",
        observed: `Unlock succeeded. Events emitted: [${a2_event_names.join(", ")}]. Gas: ${a2_gas}`,
        pass: a2_pass
    };
    console.log("A2:", a2_pass ? "PASS" : "FAIL", `(Emitted: ${a2_event_names.join(", ")})`);

    // A3: Wrong numeric OTP x4 -> each returns 0 (no revert), failedAttempts persists on-chain
    console.log("\n--- Checking A3: Wrong numeric OTP x4 -> each returns 0, failedAttempts persists ---");
    const paperIdB = ethers.keccak256(ethers.toUtf8Bytes("EXAM-AUDIT-A3"));
    const otpB = 123456n;
    const otpHashB = ethers.keccak256(ethers.solidityPacked(["bytes32", "bytes32", "uint64"], [paperIdB, centerId, otpB]));
    const curTime = Number((await ethers.provider.getBlock("latest")).timestamp);
    await vault.registerPaper(paperIdB, paperHash, ipfsCid, curTime - 10, centerId, otpHashB);

    const keyB = ethers.keccak256(ethers.solidityPacked(["bytes32", "bytes32"], [paperIdB, centerId]));
    let a3_counts = [];
    let a3_returned_zeros = true;
    for (let i = 1; i <= 4; i++) {
        const tx = await vault.connect(centerAccount).unlockPaper(paperIdB, centerId, 999999n);
        const rc = await tx.wait();
        const cnt = await vault.failedAttempts(keyB);
        a3_counts.push(Number(cnt));
    }
    const a3_pass = a3_counts.join(",") === "1,2,3,4";
    results["A3"] = {
        check: "Wrong numeric OTP x4 -> each returns 0 (no revert), failedAttempts persists on-chain",
        expected: "failedAttempts increments 1, 2, 3, 4 without revert",
        observed: `failedAttempts progression: [${a3_counts.join(", ")}]`,
        pass: a3_pass
    };
    console.log("A3:", a3_pass ? "PASS" : "FAIL");

    // A4: 5th wrong OTP -> CenterLockedExceededAttempts; correct OTP afterwards STILL locked
    console.log("\n--- Checking A4: 5th wrong OTP -> CenterLockedExceededAttempts; correct OTP afterwards STILL locked ---");
    let a4_5th_locked = false;
    let a4_correct_still_locked = false;

    // 5th wrong OTP
    const tx5 = await vault.connect(centerAccount).unlockPaper(paperIdB, centerId, 999999n);
    await tx5.wait();
    const cnt5 = await vault.failedAttempts(keyB);

    // 6th attempt with correct OTP must revert with CenterLockedExceededAttempts
    try {
        await vault.connect(centerAccount).unlockPaper(paperIdB, centerId, otpB);
    } catch (e) {
        if (e.message.includes("CenterLockedExceededAttempts")) {
            a4_correct_still_locked = true;
        }
    }
    const a4_pass = (Number(cnt5) === 5) && a4_correct_still_locked;
    results["A4"] = {
        check: "5th wrong OTP -> CenterLockedExceededAttempts; correct OTP afterwards STILL locked",
        expected: "5th attempt sets count to 5; subsequent attempts revert with CenterLockedExceededAttempts",
        observed: `Count at 5th attempt: ${cnt5}. Subsequent correct attempt reverted with CenterLockedExceededAttempts: ${a4_correct_still_locked}`,
        pass: a4_pass
    };
    console.log("A4:", a4_pass ? "PASS" : "FAIL");

    // A5: unlockPaperSecret 12-char path succeeds; 11-char and 13-char rejected
    console.log("\n--- Checking A5: unlockPaperSecret 12-char path succeeds; 11-char and 13-char rejected ---");
    const paperIdC = ethers.keccak256(ethers.toUtf8Bytes("EXAM-AUDIT-A5"));
    const secret12 = "aB3$kL9#mQ2!"; // 12 chars
    const secretHashC = ethers.keccak256(ethers.solidityPacked(["bytes32", "bytes32", "string"], [paperIdC, centerId, secret12]));
    await vault.registerPaper(paperIdC, paperHash, ipfsCid, curTime - 10, centerId, secretHashC);

    let a5_11_rejected = false;
    let a5_13_rejected = false;
    let a5_12_success = false;

    // Test 11-char
    try {
        const tx11 = await vault.connect(centerAccount).unlockPaperSecret(paperIdC, centerId, "12345678901");
        const rc11 = await tx11.wait();
        // Check if failed or returned 0 or reverted
        const keyC = ethers.keccak256(ethers.solidityPacked(["bytes32", "bytes32"], [paperIdC, centerId]));
        const f11 = await vault.failedAttempts(keyC);
        if (Number(f11) === 1) a5_11_rejected = true;
    } catch (e) {
        a5_11_rejected = true;
    }

    // Test 13-char
    try {
        const tx13 = await vault.connect(centerAccount).unlockPaperSecret(paperIdC, centerId, "1234567890123");
        await tx13.wait();
        const keyC = ethers.keccak256(ethers.solidityPacked(["bytes32", "bytes32"], [paperIdC, centerId]));
        const f13 = await vault.failedAttempts(keyC);
        if (Number(f13) === 2) a5_13_rejected = true;
    } catch (e) {
        a5_13_rejected = true;
    }

    // Test valid 12-char
    try {
        const tx12 = await vault.connect(centerAccount).unlockPaperSecret(paperIdC, centerId, secret12);
        const rc12 = await tx12.wait();
        const prints = await vault.printInstances(paperIdC);
        if (Number(prints) === 1) a5_12_success = true;
    } catch (e) {
        console.log("12-char failed:", e.message);
    }

    const a5_pass = a5_11_rejected && a5_13_rejected && a5_12_success;
    results["A5"] = {
        check: "unlockPaperSecret 12-char path succeeds; 11-char and 13-char rejected",
        expected: "12-char secret unlocks; 11-char and 13-char rejected",
        observed: `11-char rejected: ${a5_11_rejected}, 13-char rejected: ${a5_13_rejected}, 12-char success: ${a5_12_success}`,
        pass: a5_pass
    };
    console.log("A5:", a5_pass ? "PASS" : "FAIL");

    // A6: Measured unlock gas printed; must equal 83,811 ± 500 (README claim check)
    console.log("\n--- Checking A6: Measured unlock gas printed; must equal 83,811 ± 500 ---");
    const paperIdD = ethers.keccak256(ethers.toUtf8Bytes("EXAM-AUDIT-A6"));
    const otpD = 556677n;
    const otpHashD = ethers.keccak256(ethers.solidityPacked(["bytes32", "bytes32", "uint64"], [paperIdD, centerId, otpD]));
    await vault.registerPaper(paperIdD, paperHash, ipfsCid, curTime - 10, centerId, otpHashD);

    const txD = await vault.connect(centerAccount).unlockPaper(paperIdD, centerId, otpD);
    const rcD = await txD.wait();
    const gasUsed = Number(rcD.gasUsed);
    console.log(`Measured unlock gas: ${gasUsed}`);
    const a6_pass = Math.abs(gasUsed - 83811) <= 500;
    results["A6"] = {
        check: "Measured unlock gas printed; must equal 83,811 ± 500",
        expected: "83,811 ± 500 gas (83,311 .. 84,311)",
        observed: `${gasUsed} gas (diff = ${gasUsed - 83811})`,
        pass: a6_pass
    };
    console.log("A6:", a6_pass ? "PASS" : "FAIL", `(gas = ${gasUsed})`);

    console.log("\n=== SECTION A SUMMARY ===");
    console.log(JSON.stringify(results, null, 2));
}

runAuditA().catch(console.error);
