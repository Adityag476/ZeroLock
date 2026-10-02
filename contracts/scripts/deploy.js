const { ethers, network } = require("hardhat");
const fs = require("fs");

async function main() {
  const [deployer] = await ethers.getSigners();
  console.log("Deploying with account:", deployer.address);
  console.log("Network:", network.name);

  const ExamVault = await ethers.getContractFactory("ExamVault");
  const vault = await ExamVault.deploy();
  await vault.waitForDeployment();

  const address = await vault.getAddress();
  console.log("✅  ExamVault deployed to:", address);

  // Save address for frontend and backend
  const deployment = {
    network:   network.name,
    address,
    deployer:  deployer.address,
    timestamp: new Date().toISOString(),
  };

  const path = require("path");
  const rootDir = path.resolve(__dirname, "../..");
  const outPath = path.join(rootDir, "backend/contract_address.json");
  fs.mkdirSync(path.dirname(outPath), { recursive: true });
  fs.writeFileSync(outPath, JSON.stringify(deployment, null, 2));
  console.log("Contract address saved to:", outPath);

  // Also export ABI for frontend
  const artifact = require(path.join(rootDir, "artifacts/contracts/ExamVault.sol/ExamVault.json"));
  const abiPath = path.join(rootDir, "frontend/src/abi/ExamVault.json");
  fs.mkdirSync(path.dirname(abiPath), { recursive: true });
  fs.writeFileSync(abiPath, JSON.stringify(artifact.abi, null, 2));
  console.log("ABI exported to frontend/src/abi/ExamVault.json");
}

main().catch((err) => {
  console.error(err);
  process.exitCode = 1;
});
