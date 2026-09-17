"""
ZeroLeak Core — AES-256-GCM Encryption + Shamir's Secret Sharing
=================================================================
Provides:
  - encrypt_pdf / decrypt_pdf   — AES-256-GCM authenticated encryption
  - split_key / reconstruct_key — Shamir 3-of-5 key sharing (GF(256))
"""

from __future__ import annotations
import os
import json
import base64
import hashlib
import secrets
from typing import Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# ---------------------------------------------------------------------------
# AES-256-GCM
# ---------------------------------------------------------------------------

def generate_key() -> bytes:
    """Generate a cryptographically random 256-bit AES key."""
    return secrets.token_bytes(32)


def encrypt_pdf(plaintext: bytes, key: Optional[bytes] = None) -> dict:
    """
    Encrypt arbitrary bytes with AES-256-GCM.

    Args:
        plaintext: Raw PDF bytes (or any bytes)
        key:       32-byte AES key. If None, a new key is generated.

    Returns:
        dict with keys: key_hex, nonce_b64, ciphertext_b64, sha256_plain
    """
    if key is None:
        key = generate_key()
    if len(key) != 32:
        raise ValueError("AES key must be exactly 32 bytes")

    nonce = secrets.token_bytes(12)        # 96-bit nonce for GCM
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)

    sha256_plain = hashlib.sha256(plaintext).hexdigest()

    return {
        "key_hex":        key.hex(),
        "nonce_b64":      base64.b64encode(nonce).decode(),
        "ciphertext_b64": base64.b64encode(ciphertext).decode(),
        "sha256_plain":   sha256_plain,
    }


def decrypt_pdf(key_hex: str, nonce_b64: str, ciphertext_b64: str) -> bytes:
    """
    Decrypt an AES-256-GCM encrypted blob.

    Returns:
        Decrypted plaintext bytes.

    Raises:
        cryptography.exceptions.InvalidTag if the ciphertext is tampered.
    """
    key        = bytes.fromhex(key_hex)
    nonce      = base64.b64decode(nonce_b64)
    ciphertext = base64.b64decode(ciphertext_b64)

    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ciphertext, None)


# ---------------------------------------------------------------------------
# Shamir's Secret Sharing  (3-of-5, GF(256) polynomial)
# GF(2^8) with generator polynomial 0x11D (x^8+x^4+x^3+x^2+1)
# Standard primitive used by most Shamir implementations
# ---------------------------------------------------------------------------

_GF_PRIM = 0x11D   # x^8 + x^4 + x^3 + x^2 + 1
_GF_EXP = [0] * 512
_GF_LOG = [0] * 256


def _build_gf_tables() -> None:
    x = 1
    for i in range(255):
        _GF_EXP[i] = x
        _GF_EXP[i + 255] = x   # extend for wraparound
        _GF_LOG[x] = i
        x <<= 1
        if x & 0x100:
            x ^= _GF_PRIM
        x &= 0xFF
    # x now equals 1 again (cyclic). Last entry not set.
    _GF_LOG[0] = 0   # undefined but set to 0 to avoid IndexError


_build_gf_tables()


def _gf_mul(a: int, b: int) -> int:
    """Multiply two elements in GF(2^8) using log/exp tables."""
    if a == 0 or b == 0:
        return 0
    return _GF_EXP[(_GF_LOG[a] + _GF_LOG[b]) % 255]


def _gf_inv(a: int) -> int:
    """Multiplicative inverse in GF(2^8) via log tables: a^(-1) = g^(255 - log(a))."""
    if a == 0:
        raise ZeroDivisionError("No inverse for 0 in GF(256)")
    return _GF_EXP[(255 - _GF_LOG[a]) % 255]


def _eval_poly(coeffs: list[int], x: int) -> int:
    """Evaluate polynomial over GF(256) via Horner's method.
    coeffs[0] = constant term, coeffs[k] = coefficient of x^k."""
    result = 0
    for c in reversed(coeffs):
        result = _gf_mul(result, x) ^ c
    return result


def split_key(key_hex: str, threshold: int = 3, shares: int = 5) -> list[dict]:
    """
    Split a 32-byte AES key into `shares` Shamir shares, any `threshold` of
    which can reconstruct the secret.

    Returns:
        List of dicts: [{"share_id": int, "share_hex": str}, ...]
    """
    secret_bytes = bytes.fromhex(key_hex)
    all_shares: list[dict] = []

    byte_shares: list[list[int]] = [[] for _ in range(shares)]

    for byte in secret_bytes:
        # Random polynomial of degree (threshold-1) with secret as constant term
        coeffs = [byte] + [secrets.randbelow(256) for _ in range(threshold - 1)]
        for i in range(1, shares + 1):
            byte_shares[i - 1].append(_eval_poly(coeffs, i))

    for i in range(shares):
        share_bytes = bytes(byte_shares[i])
        all_shares.append({
            "share_id":  i + 1,
            "share_hex": share_bytes.hex(),
        })

    return all_shares


def reconstruct_key(share_list: list[dict]) -> str:
    """
    Reconstruct the AES key from a list of Shamir shares.

    Args:
        share_list: At least `threshold` dicts with share_id and share_hex.

    Returns:
        key_hex: Reconstructed 32-byte key as hex string.
    """
    xs = [s["share_id"] for s in share_list]
    ys = [bytes.fromhex(s["share_hex"]) for s in share_list]
    key_length = len(ys[0])

    secret_bytes = []
    for byte_idx in range(key_length):
        # Lagrange interpolation at x=0 over GF(256)
        secret = 0
        for i, xi in enumerate(xs):
            yi = ys[i][byte_idx]
            # Numerator: product of (0 XOR xj) for j != i  = product of xj
            num = 1
            for j, xj in enumerate(xs):
                if i != j:
                    num = _gf_mul(num, xj)
            # Denominator: product of (xi XOR xj) for j != i
            den = 1
            for j, xj in enumerate(xs):
                if i != j:
                    den = _gf_mul(den, xi ^ xj)
            # Lagrange basis coefficient
            basis = _gf_mul(num, _gf_inv(den))
            term = _gf_mul(yi, basis)
            secret ^= term
        secret_bytes.append(secret)

    return bytes(secret_bytes).hex()


# ---------------------------------------------------------------------------
# Quick smoke test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import pprint

    # --- AES round-trip ---
    sample_pdf = b"Hello, ZeroLeak! This is the exam content." * 100
    enc = encrypt_pdf(sample_pdf)
    print("Encrypted. Key:", enc["key_hex"][:16], "...")
    decrypted = decrypt_pdf(enc["key_hex"], enc["nonce_b64"], enc["ciphertext_b64"])
    assert decrypted == sample_pdf, "AES decrypt mismatch!"
    print("✅  AES-256-GCM round-trip OK")

    # --- Shamir 3-of-5 ---
    shares = split_key(enc["key_hex"])
    print(f"Split into {len(shares)} shares")

    # Reconstruct from any 3
    recon = reconstruct_key(shares[:3])
    assert recon == enc["key_hex"], f"Shamir mismatch!\n{recon}\n{enc['key_hex']}"
    print("✅  Shamir 3-of-5 reconstruct OK")

    recon2 = reconstruct_key([shares[1], shares[3], shares[4]])
    assert recon2 == enc["key_hex"]
    print("✅  Shamir alternate-3 reconstruct OK")
