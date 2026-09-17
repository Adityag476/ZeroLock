"""
ZeroLeak Experiments — Forensic Decoder Gate Test
==================================================
Gate test step 2: Decode a watermark from a photo of a printed paper.
Usage:
    python experiments/decode.py --image photo.jpg [--debug]
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import argparse
import pprint
from core.decoder import decode_photo


def main():
    parser = argparse.ArgumentParser(description="ZeroLeak forensic decoder gate test")
    parser.add_argument("--image",  type=str, required=True, help="Path to phone photo (JPEG/PNG)")
    parser.add_argument("--debug",  action="store_true",     help="Save intermediate images to experiments/debug/")
    args = parser.parse_args()

    debug_dir = "experiments/debug" if args.debug else None

    print(f"Decoding: {args.image}")
    if debug_dir:
        print(f"Debug images → {debug_dir}/")
    print()

    result = decode_photo(args.image, debug_dir=debug_dir)

    status = result.get("status", "UNKNOWN")
    colour = {"VERIFIED": "\033[92m", "CORRUPTED": "\033[93m", "UNKNOWN": "\033[91m"}.get(status, "")
    reset = "\033[0m"

    print(f"Status: {colour}{status}{reset}")
    print()
    pprint.pprint(result)

    if status == "VERIFIED":
        print()
        print(f"  ✅  LEAK TRACED")
        print(f"      Centre  : {result['centre_id']}")
        print(f"      Hall    : {result['hall_id']}")
        print(f"      Print # : {result['print_num']}")
        print(f"      Epoch   : {result['timestamp']}")
        print(f"      Conf    : {result['confidence']*100:.1f}%")
    elif status == "CORRUPTED":
        print()
        print(f"  ⚠️   Partial watermark found but payload could not be recovered.")
        print(f"      Bits extracted: {result.get('bit_count', 0)}")
        print(f"      Try a clearer photo with better lighting.")
    else:
        print()
        print(f"  ❌  No ZeroLeak watermark detected.")
        print(f"      Ensure the image contains a ZeroLeak-printed document.")


if __name__ == "__main__":
    main()
