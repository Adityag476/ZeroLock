"""
ZeroLock — Physical Photo Matrix Evaluator (Gate 2)
===================================================
Evaluates photographs of physically printed papers taken with a phone camera.
Reads images from evidence/gate2/photos/ and outputs the empirical matrix.
"""

import os
import sys
import glob

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.decoder import decode_photo


def main():
    print("=" * 70)
    print("ZeroLock — Physical Print Matrix Evaluator (Gate 2)")
    print("=" * 70)

    photo_dir = os.path.join("evidence", "gate2", "photos")
    if not os.path.exists(photo_dir):
        os.makedirs(photo_dir, exist_ok=True)
        print(f"\n[INFO] Directory created: {photo_dir}")
        print("Drop your 5 phone camera photos (.jpg / .png) into this directory.")
        print("Example filenames:")
        print("  p1_flat_scan.jpg")
        print("  p1_angled_tilt_15deg.jpg")
        print("  p1_high_tilt_25deg.jpg")
        print("  p1_hard_shadow_lamp.jpg")
        print("  p2_folded_creased.jpg")
        return

    exts = ("*.jpg", "*.jpeg", "*.png")
    photo_files = []
    for ext in exts:
        photo_files.extend(glob.glob(os.path.join(photo_dir, ext)))

    photo_files = sorted(photo_files)

    if not photo_files:
        print(f"\n[AWAITING PHOTOS] No images found in {photo_dir}.")
        print("Please place your phone camera photos in that directory and rerun.")
        return

    print(f"\nFound {len(photo_files)} photo(s) to analyze:\n")
    print(f"{'Filename':<30} {'Status':<12} {'Centre':<10} {'Hall':<6} {'Print':<8} {'Bits':<6} {'Conf'}")
    print("-" * 80)

    csv_rows = []

    for path in photo_files:
        fname = os.path.basename(path)
        res = decode_photo(path)

        status = res.get("status", "UNKNOWN")
        centre = res.get("centre_id", "?")
        hall = res.get("hall_id", "?")
        print_num = res.get("print_num", "?")
        bits = res.get("bit_count", 0)
        conf = res.get("confidence", 0.0)
        anchors = "4/4" if res.get("anchor_found") else "0/4"

        print(f"{fname:<30} {status:<12} {centre:<10} {hall:<6} {print_num:<8} {bits:<6} {conf:.2f}")

        attributed = f"Centre {centre}" if status == "VERIFIED" else "Unresolved"
        conf_pct = f"{int(conf * 100)}%" if status == "VERIFIED" else "0%"

        csv_rows.append({
            "file": fname,
            "anchors": anchors,
            "status": status,
            "attributed": attributed,
            "confidence": conf_pct,
            "raw": res,
        })

    print("-" * 80)
    print("\nSummary CSV Rows:")
    print("File,Anchors,Status,Attributed,Confidence")
    for r in csv_rows:
        print(f"{r['file']},{r['anchors']},{r['status']},{r['attributed']},{r['confidence']}")


if __name__ == "__main__":
    main()
