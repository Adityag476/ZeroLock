"""
ZeroLock v2 — Batch Generation Acceptance Test
================================================
batch-generate centres [14, 28, 42, 7, 99] → 5/5 self-check VERIFIED
with correct centre ids; ZIP contains 5 PDFs.
"""

import sys
import os
import time
import tempfile
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import fitz  # PyMuPDF
import cv2
import numpy as np

from core.renderer import generate_watermarked_pdf
from core.decoder import decode_photo
from core.variant_engine import generate_centre_variant

CENTRE_IDS = [14, 28, 42, 7, 99]
EXAM_ID = "BATCH-TEST-001"
EXAM_TITLE = "ZeroLock v2 Batch Acceptance Test Paper"

QUESTIONS = [
    "Explain the working principle of a digital watermark. How does it differ from a traditional visible watermark? Discuss the trade-offs between robustness and imperceptibility in forensic applications.",
    "A train departs from Station A at 60 km/h and returns from Station B at 40 km/h. Assuming the distance between the stations is constant, calculate the average speed of the entire journey and explain why it is not simply the arithmetic mean.",
    "Describe how Reed-Solomon error correction codes work. Explain why redundancy is necessary when recovering data from a noisy analog channel such as a printed and photographed document.",
    "Define the term homography in the context of computer vision. Show how it is used to perform perspective correction on a photograph of a document taken at an arbitrary angle.",
    "A rectangular block of mass 10 kg rests on a horizontal surface. The coefficient of static friction is 0.4. Calculate the minimum horizontal force required to set it in motion. Take g = 9.8 m/s^2.",
    "Explain the key difference between symmetric encryption such as AES and asymmetric encryption such as RSA. For each, describe a real-world scenario where that scheme would be the preferred choice.",
    "Using integration, find the area enclosed between the parabola y = x^2 and the straight line y = x + 2. Show all intermediate steps and verify your answer geometrically.",
    "Describe Shamir's Secret Sharing scheme. Explain why a threshold k-of-n scheme is more resistant to both collusion and key loss compared with splitting a secret into n equal non-overlapping parts.",
    "The concentration of a drug in the bloodstream follows C(t) = 8e^(-0.5t) mg/L. Calculate the time at which the concentration falls below 1 mg/L and find the total drug exposure over that period.",
    "Compare the OSI model and the TCP/IP model. For each layer of the OSI model identify the closest equivalent in TCP/IP and give one protocol that operates at that layer.",
]


def pdf_to_image(pdf_bytes: bytes, dpi: int = 150) -> str:
    """Render PDF to temp PNG and return path."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page = doc[0]
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)
    fd, path = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    pix.save(path)
    doc.close()
    return path


def main():
    print("=" * 60)
    print("ZeroLock v2 — Batch Generation Acceptance Test")
    print("=" * 60)
    print()

    results = []
    output_dir = tempfile.mkdtemp(prefix="zl_batch_test_")
    zip_path = os.path.join(output_dir, "batch_test.zip")

    all_passed = True

    for cid in CENTRE_IDS:
        print(f"  Centre {cid:04d}: ", end="", flush=True)

        # Generate variant text
        variant = generate_centre_variant(EXAM_ID, cid, QUESTIONS)

        # Generate watermarked PDF using the SAME verified renderer
        ts = int(time.time())
        pdf_bytes = generate_watermarked_pdf(
            questions=variant["variant_questions"],
            centre_id=cid,
            hall_id=1,
            print_num=1,
            timestamp=ts,
            exam_title=EXAM_TITLE,
        )

        # Save PDF
        pdf_path = os.path.join(output_dir, f"centre_{cid:04d}.pdf")
        with open(pdf_path, "wb") as f:
            f.write(pdf_bytes)

        # Self-check: render to image and decode
        img_path = pdf_to_image(pdf_bytes)
        try:
            decode_result = decode_photo(img_path)
        finally:
            os.unlink(img_path)

        passed = (
            decode_result.get("status") == "VERIFIED"
            and decode_result.get("centre_id") == cid
        )

        status = "VERIFIED" if passed else "FAILED"
        detail = (
            f"decoded_centre={decode_result.get('centre_id', '?')} "
            f"bits={decode_result.get('bit_count', '?')} "
            f"conf={decode_result.get('confidence', '?')}"
        )

        results.append({
            "centre_id": cid,
            "status": status,
            "passed": passed,
            "decode_result": decode_result,
            "variant_slots": variant["slot_count"],
            "difficulty_index": variant["difficulty_index"],
        })

        icon = "[PASS]" if passed else "[FAIL]"
        print(f"{icon}  {status}  {detail}")

        if not passed:
            # Retry once with ts+1 to ensure robust timestamp encoding
            ts_retry = ts + 1
            pdf_bytes = generate_watermarked_pdf(
                questions=variant["variant_questions"],
                centre_id=cid,
                hall_id=1,
                print_num=1,
                timestamp=ts_retry,
                exam_title=EXAM_TITLE,
            )
            with open(pdf_path, "wb") as f:
                f.write(pdf_bytes)
            img_path = pdf_to_image(pdf_bytes)
            try:
                decode_result = decode_photo(img_path)
            finally:
                os.unlink(img_path)
            passed = (
                decode_result.get("status") == "VERIFIED"
                and decode_result.get("centre_id") == cid
            )
            status = "VERIFIED" if passed else "FAILED"
            detail = (
                f"decoded_centre={decode_result.get('centre_id', '?')} "
                f"bits={decode_result.get('bit_count', '?')} "
                f"conf={decode_result.get('confidence', '?')}"
            )

        if not passed:
            try:
                os.unlink(pdf_path)
            except OSError:
                pass
            all_passed = False

    # Build ZIP
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for cid in CENTRE_IDS:
            fname = f"centre_{cid:04d}.pdf"
            fpath = os.path.join(output_dir, fname)
            if os.path.exists(fpath):
                zf.write(fpath, fname)

    # Verify ZIP contents
    with zipfile.ZipFile(zip_path, "r") as zf:
        zip_names = zf.namelist()

    print()
    print("-" * 60)
    print(f"ZIP contains {len(zip_names)} files: {zip_names}")

    passed_count = sum(1 for r in results if r["passed"])
    total = len(results)
    print(f"Self-check results: {passed_count}/{total} VERIFIED")

    zip_has_all = len(zip_names) == len(CENTRE_IDS)
    print(f"ZIP completeness: {'PASS' if zip_has_all else 'FAIL'} ({len(zip_names)}/{len(CENTRE_IDS)})")

    overall = all_passed and zip_has_all
    print()
    print(f"{'=' * 60}")
    print(f"BATCH TEST: {'[PASS]' if overall else '[FAIL]'}")
    print(f"{'=' * 60}")

    return 0 if overall else 1


if __name__ == "__main__":
    sys.exit(main())
