"""
ZeroLeak Core — Payload Encoding & Reed-Solomon ECC
=====================================================
Encodes [Magic | CentreID | HallID | PrintNum | Timestamp] into a
Reed-Solomon protected bitstream for embedding in watermarked PDFs.

Payload layout (80 raw bits):
    Magic       16 bits  (0xAB CD  — sync word)
    CentreID    16 bits  (0–65535)
    HallID       8 bits  (0–255)
    PrintNum     8 bits  (0–255)
    Timestamp   32 bits  (Unix epoch)
Total raw: 80 bits = 10 bytes

RS-encoded: RSCodec(10) adds 10 ECC bytes → 20 bytes = 160 bits
Page capacity: ~40 lines × 7 inter-word gaps ≈ 280 bits → fits with headroom.
"""

from __future__ import annotations
import struct
import zlib
from reedsolo import RSCodec, ReedSolomonError

# --- Constants ---
MAGIC = 0xABCD                  # 16-bit sync word
RS_ECC_SYMBOLS = 10             # Reed-Solomon parity symbols (corrects ≤5 symbol errors)
PAYLOAD_RAW_BYTES = 10          # bytes before RS encoding
PAYLOAD_TOTAL_BYTES = PAYLOAD_RAW_BYTES + RS_ECC_SYMBOLS  # 20 bytes → 160 bits

_rs = RSCodec(RS_ECC_SYMBOLS)


def pack_payload(centre_id: int, hall_id: int, print_num: int, timestamp: int) -> bytes:
    """
    Pack metadata into a 10-byte raw payload.

    Args:
        centre_id:  Exam centre identifier (0–65535)
        hall_id:    Hall/room identifier    (0–255)
        print_num:  Sequential print number (0–255)
        timestamp:  Unix epoch seconds      (uint32)

    Returns:
        10-byte raw payload bytes
    """
    return struct.pack(">HHBBI", MAGIC, centre_id, hall_id, print_num, timestamp)


def encode_payload(centre_id: int, hall_id: int, print_num: int, timestamp: int) -> list[int]:
    """
    Encode metadata into a Reed-Solomon protected list of bits.

    Returns:
        List of 160 bits (ints 0/1) ready for embedding.
    """
    raw = pack_payload(centre_id, hall_id, print_num, timestamp)
    encoded: bytes = bytes(_rs.encode(bytearray(raw)))
    bits: list[int] = []
    for byte in encoded:
        for shift in range(7, -1, -1):
            bits.append((byte >> shift) & 1)
    return bits


def decode_payload(bits: list[int]) -> dict | None:
    """
    Decode a Reed-Solomon protected bitstream back into metadata.

    Args:
        bits: List of ints (0/1), at least 160 elements (may be longer; uses first 160)

    Returns:
        Dict with keys: magic, centre_id, hall_id, print_num, timestamp, valid
        Returns None if RS decode fails catastrophically.
    """
    if len(bits) < 160:
        return {"valid": False, "error": f"Too few bits: {len(bits)} < 160"}

    # Pack bits → bytes
    raw_bytes = bytearray()
    for i in range(0, 160, 8):
        byte = 0
        for j in range(8):
            byte = (byte << 1) | bits[i + j]
        raw_bytes.append(byte)

    try:
        decoded, _, _ = _rs.decode(raw_bytes)
        decoded = bytes(decoded)
    except ReedSolomonError as e:
        return {"valid": False, "error": f"RS decode failed: {e}"}

    if len(decoded) < PAYLOAD_RAW_BYTES:
        return {"valid": False, "error": "Decoded payload too short"}

    magic, centre_id, hall_id, print_num, timestamp = struct.unpack(">HHBBI", decoded[:10])

    if magic != MAGIC:
        return {"valid": False, "error": f"Magic mismatch: 0x{magic:04X} != 0x{MAGIC:04X}"}

    return {
        "valid":      True,
        "magic":      f"0x{magic:04X}",
        "centre_id":  centre_id,
        "hall_id":    hall_id,
        "print_num":  print_num,
        "timestamp":  timestamp,
    }


# ---------------------------------------------------------------------------
# Compact 48-Bit Payload Engine with Whitening & Repeated Voting
# (Recommended for short question papers and diagram-dense exams)
# ---------------------------------------------------------------------------
WHITENING_MASK = bytes([0xAA, 0x55, 0xF0, 0x0F, 0xCC, 0x33])  # LFSR polynomial mask

def pack_payload_48(centre_id: int, hall_id: int, print_num: int) -> bytes:
    """
    Packs payload into 48 bits (6 bytes):
    - Magic Sync Word : 16 bits (0xABCD)
    - Centre ID       : 16 bits (0–65535)
    - Hall ID         : 8 bits  (0–255)
    - Print Instance  : 8 bits  (0–255)
    Applies XOR whitening to equalize 0/1 transition density on physical paper.
    """
    raw_bytes = struct.pack(">HHBB", MAGIC, centre_id & 0xFFFF, hall_id & 0xFF, print_num & 0xFF)
    return bytes(b ^ m for b, m in zip(raw_bytes, WHITENING_MASK))


def unpack_payload_48(whitened_bytes: bytes) -> dict:
    if len(whitened_bytes) != 6:
        raise ValueError(f"Expected 6 bytes, got {len(whitened_bytes)}")
    raw_bytes = bytes(b ^ m for b, m in zip(whitened_bytes, WHITENING_MASK))
    magic, centre_id, hall_id, print_num = struct.unpack(">HHBB", raw_bytes)
    if magic != MAGIC:
        raise ValueError(f"Sync Header Mismatch: Expected {hex(MAGIC)}, got {hex(magic)}")
    return {
        "valid": True,
        "magic": f"0x{magic:04X}",
        "centre_id": centre_id,
        "hall_id": hall_id,
        "print_num": print_num,
        "timestamp": 0,
        "mode": "compact-48",
    }


def generate_compact_bitstream(centre_id: int, hall_id: int, print_num: int, total_gaps: int) -> list[int]:
    """Generates a repeating sequence of the 48-bit whitened codeword across all page gaps."""
    whitened = pack_payload_48(centre_id, hall_id, print_num)
    codeword_bits = []
    for byte in whitened:
        for shift in range(7, -1, -1):
            codeword_bits.append((byte >> shift) & 1)
    reps = (total_gaps // 48) + 1
    return (codeword_bits * reps)[:total_gaps]


def decode_compact_bitstream(extracted_bits: list[int]) -> dict | None:
    """Recovers 48-bit codeword from a partial or noisy crop using circular cross-correlation."""
    if len(extracted_bits) < 48:
        return None

    # Expected sync word in whitened domain
    whitened_magic = struct.pack(">H", MAGIC ^ ((WHITENING_MASK[0] << 8) | WHITENING_MASK[1]))
    target_magic_bits = []
    for byte in whitened_magic:
        for shift in range(7, -1, -1):
            target_magic_bits.append((byte >> shift) & 1)

    best_offset = -1
    max_corr = -1
    max_scan = min(len(extracted_bits) - 48 + 1, 120)

    for offset in range(max_scan):
        slice_bits = extracted_bits[offset : offset + 16]
        corr = sum(1 for a, b in zip(slice_bits, target_magic_bits) if a == b)
        if corr > max_corr:
            max_corr = corr
            best_offset = offset

    if max_corr < 14 or best_offset < 0:  # Allow up to 2 bit errors in sync word
        return None

    candidate_bits = extracted_bits[best_offset : best_offset + 48]
    byte_array = bytearray()
    for i in range(0, 48, 8):
        byte_val = 0
        for bit in candidate_bits[i : i + 8]:
            byte_val = (byte_val << 1) | bit
        byte_array.append(byte_val)

    try:
        res = unpack_payload_48(bytes(byte_array))
        res["bit_offset"] = best_offset
        return res
    except ValueError:
        return None


def sliding_decode(bits: list[int]) -> dict | None:
    """
    Slide a 160-bit window over the recovered bitstream to find the magic word.
    If no 160-bit standard RS decode is found, falls back to 48-bit compact whitened decode.
    """
    # 1. Try standard 160-bit Reed-Solomon window
    max_offset = max(0, len(bits) - 159)
    for offset in range(max_offset):
        window = bits[offset: offset + 160]
        result = decode_payload(window)
        if result and result.get("valid"):
            result["bit_offset"] = offset
            result["mode"] = "standard-160"
            return result

    # 2. Try compact 48-bit whitened decode
    if len(bits) >= 48:
        res_compact = decode_compact_bitstream(bits)
        if res_compact and res_compact.get("valid"):
            return res_compact

    return None


# ---------------------------------------------------------------------------
# Quick smoke test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import time, pprint
    ts = int(time.time())
    
    # 1. Test Standard 160-bit RS
    bits_160 = encode_payload(centre_id=14, hall_id=3, print_num=17, timestamp=ts)
    print(f"Encoded standard: {len(bits_160)} bits")
    res_160 = sliding_decode(bits_160)
    assert res_160["valid"] and res_160["centre_id"] == 14, "Standard decode failed!"
    print("✅  Standard 160-bit RS OK")

    # 2. Test Compact 48-bit Whitened
    bits_48 = generate_compact_bitstream(centre_id=42, hall_id=7, print_num=13, total_gaps=96)
    print(f"Encoded compact: {len(bits_48)} bits")
    res_48 = decode_compact_bitstream(bits_48)
    assert res_48["valid"] and res_48["centre_id"] == 42, "Compact decode failed!"
    print("✅  Compact 48-bit Whitened OK")
