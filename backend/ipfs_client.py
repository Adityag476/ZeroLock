"""
ZeroLeak Backend — IPFS via Pinata
"""

import os
import requests

PINATA_API_KEY    = os.environ.get("PINATA_API_KEY", "")
PINATA_API_SECRET = os.environ.get("PINATA_API_SECRET", "")
PINATA_BASE       = "https://api.pinata.cloud"


def pin_json(data: dict, name: str = "zeroleak-paper") -> str:
    """Pin a JSON object to IPFS via Pinata. Returns IPFS CID."""
    if not PINATA_API_KEY:
        # Mock CID for dev without Pinata credentials
        import hashlib, json
        return "Qm" + hashlib.sha256(json.dumps(data).encode()).hexdigest()[:44]

    headers = {
        "pinata_api_key":        PINATA_API_KEY,
        "pinata_secret_api_key": PINATA_API_SECRET,
        "Content-Type":          "application/json",
    }
    payload = {
        "pinataContent":  data,
        "pinataMetadata": {"name": name},
    }
    resp = requests.post(f"{PINATA_BASE}/pinning/pinJSONToIPFS", json=payload, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.json()["IpfsHash"]


def pin_bytes(data: bytes, filename: str = "paper.enc") -> str:
    """Pin raw bytes to IPFS via Pinata. Returns IPFS CID."""
    if not PINATA_API_KEY:
        import hashlib
        return "Qm" + hashlib.sha256(data).hexdigest()[:44]

    headers = {
        "pinata_api_key":        PINATA_API_KEY,
        "pinata_secret_api_key": PINATA_API_SECRET,
    }
    files = {"file": (filename, data, "application/octet-stream")}
    resp = requests.post(f"{PINATA_BASE}/pinning/pinFileToIPFS", files=files, headers=headers, timeout=60)
    resp.raise_for_status()
    return resp.json()["IpfsHash"]


def get_ipfs_url(cid: str) -> str:
    return f"https://gateway.pinata.cloud/ipfs/{cid}"
