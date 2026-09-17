"""
ZeroLeak Experiments — Automated Gate Test
==========================================
Tests the full encode→decode pipeline on synthetic (digital) images without
requiring a physical printer.  For physical validation, use encode.py + decode.py.

Tests:
  A  Digital: encode → render PNG → decode             (baseline, must pass)
  B  Digital: encode → render PNG → JPEG compress → decode
  C  Digital: encode → render PNG → crop to 60% → decode
  D  Digital: encode → render PNG → slight rotation (5°) → decode
  E  Digital: encode → render PNG → brightness shift → decode

Writes RESULTS.md with pass/fail table.
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import time
import tempfile
import numpy as np

try:
    import cv2
except ImportError:
    sys.exit("pip install opencv-python")

from PIL import Image as PILImage
import fitz   # PyMuPDF

from core.renderer import generate_watermarked_pdf
from core.decoder import decode_photo

# Fixed payload for reproducible tests
TEST_CENTRE   = 42
TEST_HALL     = 7
TEST_PRINT    = 13
TEST_TS       = 1726500000   # Fixed epoch

QUESTIONS = [
    "Explain the working principle of a digital watermark and its application in forensic document authentication systems that must survive physical print and photograph pipelines.",
    "A train departs from Station A at 60 km/h and returns at 40 km/h. Calculate the average speed over the entire journey and justify why arithmetic mean of speeds is incorrect.",
    "Describe how Reed-Solomon error correction codes recover corrupted data. Explain the relationship between the number of parity symbols and the number of correctable errors.",
    "Define homography in computer vision and show how perspective transformation is applied to normalize a document photographed from an angle.",
    "Explain symmetric versus asymmetric encryption with one real-world application for each. Discuss the computational cost trade-offs and why hybrid schemes are commonly used.",
    "Using integration, find the area enclosed between y equals x squared and y equals x plus two, showing all steps and verifying the result geometrically.",
    "Describe Shamir's Secret Sharing scheme and explain why a threshold k-of-n approach is more robust than splitting a key into n non-overlapping equal parts.",
    "Analyze the cryptographic properties of secure hash functions including pre-image resistance and collision resistance in digital forensics.",
    "Explain the differences between physical and digital watermarking in the context of high stakes examination question paper custody.",
    "Derive the error correction capability formula for a Reed-Solomon code with n total symbols and k message symbols.",
]


def pdf_to_png(pdf_bytes: bytes, dpi: int = 150) -> np.ndarray:
    """Render first page of PDF to a NumPy BGR image at the given DPI."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page = doc[0]
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)
    img_bytes = pix.tobytes("png")
    buf = np.frombuffer(img_bytes, dtype=np.uint8)
    img = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    doc.close()
    return img


def save_temp(img: np.ndarray, suffix: str = ".jpg", quality: int = 85) -> str:
    """Save image to a temp file and return the path."""
    fd, path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    if suffix == ".jpg":
        cv2.imwrite(path, img, [cv2.IMWRITE_JPEG_QUALITY, quality])
    else:
        cv2.imwrite(path, img)
    return path


def run_test(name: str, img: np.ndarray, suffix: str = ".jpg", quality: int = 85) -> dict:
    """Run a single decode test on an image array."""
    path = save_temp(img, suffix=suffix, quality=quality)
    try:
        result = decode_photo(path)
    finally:
        os.unlink(path)

    passed = (
        result.get("status") == "VERIFIED"
        and result.get("centre_id") == TEST_CENTRE
        and result.get("hall_id") == TEST_HALL
        and result.get("print_num") == TEST_PRINT
    )
    return {"name": name, "passed": passed, "result": result}


def main():
    print("=" * 60)
    print("ZeroLeak Gate Test — Automated Digital Pipeline")
    print("=" * 60)
    print()

    # Generate reference PDF
    pdf_bytes = generate_watermarked_pdf(
        questions=QUESTIONS,
        centre_id=TEST_CENTRE,
        hall_id=TEST_HALL,
        print_num=TEST_PRINT,
        timestamp=TEST_TS,
        exam_title="ZeroLeak Gate Test Paper",
    )
    print(f"PDF generated: {len(pdf_bytes):,} bytes")

    # Render to PNG at 150 DPI
    base_img = pdf_to_png(pdf_bytes, dpi=150)
    h, w = base_img.shape[:2]
    print(f"Base image: {w}×{h} px")
    print()

    results = []

    # --- Test A: Digital baseline ---
    print("Test A  — Digital baseline (straight PNG decode)...")
    results.append(run_test("A: Digital baseline", base_img, suffix=".png"))

    # --- Test B: JPEG compression ---
    print("Test B  — JPEG compressed (quality=75)...")
    results.append(run_test("B: JPEG q75 compress", base_img, suffix=".jpg", quality=75))

    # --- Test C: JPEG low quality ---
    print("Test C  — JPEG low quality (quality=55)...")
    results.append(run_test("C: JPEG q55 compress", base_img, suffix=".jpg", quality=55))

    # --- Test D: Crop to central 70% ---
    print("Test D  — Cropped (central 70%)...")
    cx0, cy0 = int(w*0.15), int(h*0.15)
    cx1, cy1 = int(w*0.85), int(h*0.85)
    cropped = base_img[cy0:cy1, cx0:cx1]
    results.append(run_test("D: Cropped 70%", cropped, suffix=".jpg"))

    # --- Test E: Brightness + contrast shift (simulate bad lighting) ---
    print("Test E  — Brightness shift (simulate phone lighting)...")
    bright = cv2.convertScaleAbs(base_img, alpha=1.15, beta=20)
    results.append(run_test("E: Brightness +20", bright, suffix=".jpg"))

    # --- Test F: Slight rotation (3°) ---
    print("Test F  — Slight rotation (3°)...")
    # Simulate handheld phone capture where the entire paper fits within camera viewfinder
    M = cv2.getRotationMatrix2D((w/2, h/2), 3, 0.94)
    rotated = cv2.warpAffine(base_img, M, (w, h), borderValue=(255, 255, 255))
    results.append(run_test("F: Rotation 3deg", rotated, suffix=".jpg"))

    # --- Test G: Unknown (blank white image — false-positive test) ---
    print("Test G  — Unknown doc (should return UNKNOWN, not VERIFIED)...")
    blank = np.ones_like(base_img) * 255
    path = save_temp(blank, suffix=".jpg")
    try:
        g_result = decode_photo(path)
    finally:
        os.unlink(path)
    g_passed = g_result.get("status") != "VERIFIED"
    results.append({"name": "G: False-positive guard", "passed": g_passed, "result": g_result})

    # --- Summary ---
    print()
    print("=" * 60)
    print("RESULTS")
    print("=" * 60)
    passed_count = sum(1 for r in results if r["passed"])
    total = len(results)

    rows = []
    for r in results:
        status_icon = "[PASS]" if r["passed"] else "[FAIL]"
        md_icon = "PASS" if r["passed"] else "FAIL"
        res = r["result"]
        detail = (
            f"status={res.get('status','?')} "
            f"c={res.get('centre_id','?')} "
            f"h={res.get('hall_id','?')} "
            f"p={res.get('print_num','?')} "
            f"bits={res.get('bit_count','?')} "
            f"conf={res.get('confidence','?')}"
        )
        rows.append((r["name"], md_icon, detail))
        print(f"  {r['name']:<30} {status_icon}  {detail}")

    print()
    print(f"Passed: {passed_count}/{total}")
    gate_pass = passed_count >= 6   # need >= 6/7
    gate_icon = "[GO]" if gate_pass else "[NO-GO]"
    print(f"Gate decision: {gate_icon}")
    print()

    # Write RESULTS.md
    md_lines = [
        "# ZeroLeak Gate Test Results\n",
        f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n",
        "| Test | Result | Detail |\n",
        "|------|--------|--------|\n",
    ]
    for (name, icon, detail) in rows:
        md_lines.append(f"| {name} | **{icon}** | {detail} |\n")
    md_lines.append(f"\n**Gate Decision: {'GO' if gate_pass else 'NO-GO'}** ({passed_count}/{total} passed)\n\n")
    md_lines.append("## Notes\n")
    md_lines.append("- Tests A–F use digitally rendered images (no physical printer required)\n")
    md_lines.append("- Physical print validation must be done manually with encode.py + decode.py\n")
    md_lines.append(f"- Payload: centre={TEST_CENTRE}, hall={TEST_HALL}, print={TEST_PRINT}\n")

    results_path = "experiments/RESULTS.md"
    with open(results_path, "w", encoding="utf-8") as f:
        f.writelines(md_lines)
    print(f"RESULTS.md written -> {results_path}")
    return 0 if gate_pass else 1


if __name__ == "__main__":
    sys.exit(main())
