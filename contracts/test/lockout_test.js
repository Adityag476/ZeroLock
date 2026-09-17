const { expect } = require("chai");
const { ethers, network } = require("hardhat");

describe("PaperVault Anti-Grinding Lockout", function () {
  let vault, admin, centre;
  const paperId = ethers.keccak256(ethers.toUtf8Bytes("EXAM-TEST-101"));
  const paperHash = ethers.keccak256(ethers.toUtf8Bytes("content-sha256"));
  const ipfsCid = "QmTest1234567890abcdef";
  const centreId = ethers.keccak256(ethers.toUtf8Bytes("CENTRE-14"));
  const correctOtp = 884422n;
  const otpHash = ethers.keccak256(ethers.solidityPacked(["bytes32", "bytes32", "uint64"], [paperId, centreId, correctOtp]));

  beforeEach(async function () {
    [admin, centre] = await ethers.getSigners();
    const PaperVault = await ethers.getContractFactory("PaperVault");
    vault = await PaperVault.deploy();
    await vault.waitForDeployment();

    const now = Math.floor(Date.now() / 1000);
    const unlockTime = now + 10; // unlocks in 10s

    await vault.registerPaper(paperId, paperHash, ipfsCid, unlockTime, centreId, otpHash);

    // Fast-forward time past unlock
    await network.provider.send("evm_increaseTime", [20]);
    await network.provider.send("evm_mine");
  });

  it("should track failed attempts and lock out after 5 invalid guesses", async function () {
    const wrongOtp = 111111n;

    // Fail 4 times (returns 0, emits event, increments state on-chain)
    for (let i = 1; i <= 4; i++) {
      const tx = await vault.unlockPaper(paperId, centreId, wrongOtp);
      await tx.wait();
      
      const key = ethers.keccak256(ethers.solidityPacked(["bytes32", "bytes32"], [paperId, centreId]));
      expect(await vault.failedAttempts(key)).to.equal(i);
    }

    // 5th failed attempt increments counter to 5
    const tx5 = await vault.unlockPaper(paperId, centreId, wrongOtp);
    await tx5.wait();

    const key = ethers.keccak256(ethers.solidityPacked(["bytes32", "bytes32"], [paperId, centreId]));
    expect(await vault.failedAttempts(key)).to.equal(5);

    // 6th attempt (even with correct OTP) must REVERT with CenterLockedExceededAttempts
    await expect(
      vault.unlockPaper(paperId, centreId, correctOtp)
    ).to.be.revertedWithCustomError(vault, "CenterLockedExceededAttempts");
  });

  it("should unlock successfully with correct OTP on first attempt and reset failed counter", async function () {
    const tx = await vault.unlockPaper(paperId, centreId, correctOtp);
    const receipt = await tx.wait();

    const key = ethers.keccak256(ethers.solidityPacked(["bytes32", "bytes32"], [paperId, centreId]));
    expect(await vault.failedAttempts(key)).to.equal(0);
    expect(await vault.printInstances(paperId)).to.equal(1);
  });

  it("should support 12-character alphanumeric high-entropy token secrets", async function () {
    const paperId2 = ethers.keccak256(ethers.toUtf8Bytes("EXAM-ENTROPY-202"));
    const secretToken = "xK9#mQ2$vL8!"; // High entropy string token
    const secretHash = ethers.keccak256(ethers.solidityPacked(["bytes32", "bytes32", "string"], [paperId2, centreId, secretToken]));

    const now = Math.floor(Date.now() / 1000);
    await vault.registerPaper(paperId2, paperHash, ipfsCid, now - 10, centreId, secretHash);

    // Wrong secret token fails and returns 0
    const txFail = await vault.unlockPaperSecret(paperId2, centreId, "wrongToken12");
    await txFail.wait();

    const key2 = ethers.keccak256(ethers.solidityPacked(["bytes32", "bytes32"], [paperId2, centreId]));
    expect(await vault.failedAttempts(key2)).to.equal(1);

    // Valid secret token succeeds
    const txPass = await vault.unlockPaperSecret(paperId2, centreId, secretToken);
    await txPass.wait();

    expect(await vault.failedAttempts(key2)).to.equal(0);
    expect(await vault.printInstances(paperId2)).to.equal(1);
  });
});
