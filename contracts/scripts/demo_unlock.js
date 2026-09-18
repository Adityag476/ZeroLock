/**
 * ZeroLock Time-Lock Verification Script
 * ======================================
 * Tests:
 *   1. Register a paper with unlock time = now + 60 seconds
 *   2. Attempt early unlock → EVM Revert (TimeLockActive)
 *   3. hardhat_increaseTime → advance past unlock time
 *   4. Unlock → success + PaperUnlocked event
 *
 * Run: npx hardhat run scripts/demo_unlock.js --network localhost
 */

const { ethers, network } = require("hardhat");
const fs = require("fs");

async function main() {
  const [admin, centre] = await ethers.getSigners();

  // Load deployed address
  const deployment = JSON.parse(fs.readFileSync("../backend/contract_address.json", "utf8"));
  const artifact   = require("../artifacts/contracts/ExamVault.sol/ExamVault.json");
  const vault      = new ethers.Contract(deployment.address, artifact.abi, admin);

  console.log("ExamVault at:", deployment.address);
  console.log("Admin:       ", admin.address);
  console.log("Centre:      ", centre.address);
  console.log();

  // Paper setup
  const paperId     = ethers.keccak256(ethers.toUtf8Bytes("EXAM-2026-MATH"));
  const contentHash = ethers.keccak256(ethers.toUtf8Bytes("sha256-of-exam-pdf"));
  const ipfsCid     = "QmExampleCIDForDemoOnly1234567890abcdef";
  const now         = Math.floor(Date.now() / 1000);
  const unlockTime  = now + 60;   // unlock in 60 seconds

  const centreId = ethers.keccak256(ethers.toUtf8Bytes("CENTRE-14"));
  const otp      = 999888n;
  const otpHash  = ethers.keccak256(
    ethers.solidityPacked(["bytes32", "uint64"], [centreId, otp])
  );

  // 1. Register paper
  console.log("📋  Registering paper...");
  await (await vault.registerPaper(paperId, contentHash, ipfsCid, unlockTime)).wait();
  console.log("    Paper registered. UnlockTime:", new Date(unlockTime * 1000).toISOString());

  // 2. Authorise centre
  await (await vault.authoriseCentre(paperId, centreId, otpHash)).wait();
  console.log("    Centre authorised.");
  console.log();

  // 3. Early unlock attempt → should REVERT
  console.log("🔒  Attempting early unlock (should REVERT)...");
  const centreVault = vault.connect(centre);
  try {
    const tx = await centreVault.unlock(paperId, centreId, otp, { gasLimit: 200000 });
    await tx.wait();
    console.log("    ❌  ERROR: Should have reverted!");
  } catch (err) {
    const reason = err?.reason || err?.message || String(err);
    if (reason.includes("TIMELOCK")) {
      console.log("    ✅  REVERTED: 'TIMELOCK: release window not open'");
    } else {
      console.log("    ⚠️   Reverted with:", reason);
    }
  }
  console.log();

  // 4. Advance time past unlock
  const remaining = unlockTime - Math.floor(Date.now() / 1000) + 5;
  console.log(`⏩  Advancing blockchain time by ${remaining}s...`);
  await network.provider.send("evm_increaseTime", [remaining]);
  await network.provider.send("evm_mine");
  console.log("    Time advanced.");
  console.log();

  // 5. Unlock — should succeed
  console.log("🔓  Unlocking paper...");
  const tx = await centreVault.unlock(paperId, centreId, otp, { gasLimit: 200000 });
  const receipt = await tx.wait();

  const event = receipt.logs
    .map(log => { try { return vault.interface.parseLog(log); } catch { return null; } })
    .find(e => e && e.name === "PaperUnlocked");

  if (event) {
    console.log("    ✅  PaperUnlocked event emitted:");
    console.log("        paperId:      ", event.args.paperId);
    console.log("        centreId:     ", event.args.centreId);
    console.log("        unlockedAt:   ", new Date(Number(event.args.unlockedAt) * 1000).toISOString());
    console.log("        printInstance:", event.args.printInstance.toString());
  } else {
    console.log("    Unlock tx succeeded. Tx:", receipt.hash);
  }
  console.log();
  console.log("🏆  Demo flow complete. Paper unlocked and print #1 authorized.");
}

main().catch(console.error);
