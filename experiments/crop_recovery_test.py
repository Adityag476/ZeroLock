"""
ZeroLock — Anchorless Crop Recovery Acceptance Test Suite
=========================================================
Verifies marginless / anchorless crop recovery across:
  C1: Gate-render centre 42: crops 70% / 50% / 40% (questions only, zero anchors) -> all VERIFIED centre 42
  C2: Real case: screenshot-style crop of physics paper (header + Q1-Q4, no crosshairs) -> VERIFIED centre 14
  C3: Same crops rotated 10° and 15° -> VERIFIED
  C4: 25-question-line crop from two different centres -> correct distinct centres, zero cross-talk
  C5: 1-question crop (<40 gaps) -> UNKNOWN with guidance message (honest)
  C6: Unwatermarked crop -> UNKNOWN, never a centre
"""

import os
import sys
import tempfile
import cv2
import numpy as np
import io
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.renderer import generate_watermarked_pdf
from core.decoder import decode_photo
from experiments.gate_test import QUESTIONS, TEST_CENTRE, TEST_HALL, TEST_PRINT, TEST_TS, pdf_to_png


def test_c1_gate_crops():
    print("\n[C1] Gate-render Centre 42: crops 70% / 50% / 40% (questions only, zero anchors)...")
    pdf_bytes = generate_watermarked_pdf(
        questions=QUESTIONS,
        centre_id=42,
        hall_id=7,
        print_num=13,
        timestamp=TEST_TS,
        exam_title="ZeroLeak Gate Test Paper",
        mode="compact",
    )
    base_img = pdf_to_png(pdf_bytes, dpi=150)
    h, w = base_img.shape[:2]

    crops = [
        ("70%", int(h * 0.15), int(h * 0.85)),
        ("50%", int(h * 0.25), int(h * 0.75)),
        ("40%", int(h * 0.30), int(h * 0.70)),
    ]

    for label, y0, y1 in crops:
        # Horizontally inside crosshairs (x=45 and x=1195), containing only text lines
        crop = base_img[y0:y1, int(w * 0.07):int(w * 0.93)]
        fd, path = tempfile.mkstemp(suffix=".jpg")
        os.close(fd)
        try:
            cv2.imwrite(path, crop, [cv2.IMWRITE_JPEG_QUALITY, 85])
            res = decode_photo(path)
        finally:
            os.unlink(path)

        assert res.get("status") == "VERIFIED", f"C1 ({label}) expected VERIFIED, got {res.get('status')}"
        assert res.get("centre_id") == 42, f"C1 ({label}) expected Centre 42, got {res.get('centre_id')}"
        assert res.get("mode") == "anchorless-crop", f"C1 ({label}) expected mode 'anchorless-crop', got {res.get('mode')}"
        assert res.get("confidence", 0) >= 0.85, f"C1 ({label}) expected conf >= 0.85, got {res.get('confidence')}"
        print(f"  [+] Crop {label}: VERIFIED Centre {res['centre_id']} · Hall {res['hall_id']} · Print #{res['print_num']} · mode={res['mode']} · conf={res['confidence']}")


def test_c2_real_physics_crop():
    print("\n[C2] Real Case: Physics Paper Screenshot Crop (Header + Q1-Q4, no crosshairs)...")
    crop_path = os.path.join(os.path.dirname(__file__), "fixtures", "crop_physics.png")
    os.makedirs(os.path.dirname(crop_path), exist_ok=True)

    if not os.path.exists(crop_path):
        # Generate and save fixture if missing
        pdf_A = generate_watermarked_pdf(
            questions=QUESTIONS[:4],
            centre_id=14,
            hall_id=3,
            print_num=1,
            timestamp=1710000000,
            exam_title="National Physics Examination 2026",
            mode="compact",
        )
        img_A = pdf_to_png(pdf_A, dpi=150)
        crop_physics = img_A[70:860, 75:1165]
        cv2.imwrite(crop_path, crop_physics)

    res = decode_photo(crop_path)
    assert res.get("status") == "VERIFIED", f"C2 expected VERIFIED, got {res.get('status')}"
    assert res.get("centre_id") == 14, f"C2 expected Centre 14, got {res.get('centre_id')}"
    assert res.get("hall_id") == 3, f"C2 expected Hall 3, got {res.get('hall_id')}"
    assert res.get("mode") == "anchorless-crop", f"C2 expected mode 'anchorless-crop', got {res.get('mode')}"
    print(f"  [+] Real Physics Crop: VERIFIED Centre {res['centre_id']} · Hall {res['hall_id']} · Print #{res['print_num']} · mode={res['mode']}")


def test_c3_rotated_crops():
    print("\n[C3] Rotated Crops: 10° and 15° Optical Tilts...")
    pdf_bytes = generate_watermarked_pdf(
        questions=QUESTIONS,
        centre_id=42,
        hall_id=7,
        print_num=13,
        timestamp=TEST_TS,
        exam_title="ZeroLeak Gate Test Paper",
        mode="compact",
    )
    base_img = pdf_to_png(pdf_bytes, dpi=150)
    h, w = base_img.shape[:2]
    crop = base_img[int(h * 0.15):int(h * 0.85), int(w * 0.07):int(w * 0.93)]
    ch, cw_img = crop.shape[:2]

    for angle in [10, 15]:
        M = cv2.getRotationMatrix2D((cw_img / 2.0, ch / 2.0), angle, 0.90)
        rot_crop = cv2.warpAffine(crop, M, (cw_img, ch), borderValue=(255, 255, 255))
        fd, path = tempfile.mkstemp(suffix=".jpg")
        os.close(fd)
        try:
            cv2.imwrite(path, rot_crop, [cv2.IMWRITE_JPEG_QUALITY, 85])
            res = decode_photo(path)
        finally:
            os.unlink(path)

        assert res.get("status") == "VERIFIED", f"C3 ({angle}°) expected VERIFIED, got {res.get('status')}"
        assert res.get("centre_id") == 42, f"C3 ({angle}°) expected Centre 42, got {res.get('centre_id')}"
        assert res.get("mode") == "anchorless-crop", f"C3 ({angle}°) expected mode 'anchorless-crop', got {res.get('mode')}"
        print(f"  [+] Rotation {angle}°: VERIFIED Centre {res['centre_id']} · Hall {res['hall_id']} · mode={res['mode']} · conf={res['confidence']}")


def test_c4_multi_centre_isolation():
    print("\n[C4] Multi-Centre Isolation: Crops from Centre 14 vs Centre 28...")
    # Centre 14
    pdf_14 = generate_watermarked_pdf(QUESTIONS, 14, 3, 1, TEST_TS, "Exam C14", mode="compact")
    img_14 = pdf_to_png(pdf_14)
    crop_14 = img_14[int(img_14.shape[0] * 0.15):int(img_14.shape[0] * 0.85), int(img_14.shape[1] * 0.07):int(img_14.shape[1] * 0.93)]
    
    # Centre 28
    pdf_28 = generate_watermarked_pdf(QUESTIONS, 28, 1, 1, TEST_TS, "Exam C28", mode="compact")
    img_28 = pdf_to_png(pdf_28)
    crop_28 = img_28[int(img_28.shape[0] * 0.15):int(img_28.shape[0] * 0.85), int(img_28.shape[1] * 0.07):int(img_28.shape[1] * 0.93)]

    fd1, path1 = tempfile.mkstemp(suffix=".png")
    fd2, path2 = tempfile.mkstemp(suffix=".png")
    os.close(fd1); os.close(fd2)
    try:
        cv2.imwrite(path1, crop_14)
        cv2.imwrite(path2, crop_28)
        res_14 = decode_photo(path1)
        res_28 = decode_photo(path2)
    finally:
        os.unlink(path1); os.unlink(path2)

    assert res_14.get("status") == "VERIFIED" and res_14.get("centre_id") == 14
    assert res_28.get("status") == "VERIFIED" and res_28.get("centre_id") == 28
    assert res_14.get("centre_id") != res_28.get("centre_id")
    print(f"  [+] Centre 14 crop attributed to: Centre {res_14['centre_id']} (zero cross-talk)")
    print(f"  [+] Centre 28 crop attributed to: Centre {res_28['centre_id']} (zero cross-talk)")


def test_c5_short_crop_guard():
    print("\n[C5] 1-Question Crop (<40 gaps) Defensive Guard...")
    pdf = generate_watermarked_pdf(QUESTIONS, TEST_CENTRE, TEST_HALL, TEST_PRINT, TEST_TS, "Gate", mode="compact")
    img = pdf_to_png(pdf)
    crop_1q = img[150:230, 80:1150] # single text line (~20 gaps)

    fd, path = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    try:
        cv2.imwrite(path, crop_1q)
        res = decode_photo(path)
    finally:
        os.unlink(path)

    assert res.get("status") == "UNKNOWN", f"C5 expected UNKNOWN, got {res.get('status')}"
    assert "Crop too small" in res.get("message", "") or "at least ~40 word gaps" in res.get("message", "")
    print(f"  [+] 1-Question crop returned honest UNKNOWN: '{res['message']}'")


def test_c6_unwatermarked_crop_guard():
    print("\n[C6] Unwatermarked Document Crop Guard...")
    # Generate unwatermarked PDF with standard 12pt gaps
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    y = 700
    words = "Explain the working principle of digital documents and examine why physical examination paper security is essential in modern high stakes testing environments".split()
    for _ in range(8):
        x = 80
        for w in words:
            c.drawString(x, y, w)
            x += c.stringWidth(w, "Helvetica", 10) + 12.0
        y -= 25
    c.save()

    img = pdf_to_png(buf.getvalue(), dpi=150)
    crop = img[int(img.shape[0] * 0.15):int(img.shape[0] * 0.55), 70:1150]

    fd, path = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    try:
        cv2.imwrite(path, crop)
        res = decode_photo(path)
    finally:
        os.unlink(path)

    assert res.get("status") == "UNKNOWN", f"C6 expected UNKNOWN, got {res.get('status')}"
    assert res.get("centre_id") is None, f"C6 must never attribute a centre, got {res.get('centre_id')}"
    print(f"  [+] Unwatermarked crop returned honest UNKNOWN: '{res['message']}' (no centre attributed)")


def test_c7_stage0_hijack_fallthrough():
    """C7: if the anchor detector ever misfires on a crop (env-specific false
    positive) and routes it into the fiducial path, the pipeline must fall
    through to the anchorless engine instead of returning the stage-0 failure.
    Simulated by monkeypatching detect_anchors to return fake corners."""
    print("\n[C7] Stage-0 Hijack Fallthrough (misrouted crop self-heals)...")
    import core.decoder as dec
    fixture = os.path.join(os.path.dirname(__file__), "fixtures", "crop_89.png")
    assert os.path.exists(fixture), "fixtures/crop_89.png missing"
    img = cv2.imread(fixture)
    h, w = img.shape[:2]

    orig = dec.detect_anchors
    try:
        dec.detect_anchors = lambda b: np.array(
            [[10, 10], [w - 10, 10], [w - 10, h - 10], [10, h - 10]], "float32")
        res = decode_photo(fixture)
    finally:
        dec.detect_anchors = orig

    assert res.get("status") == "VERIFIED", f"C7 expected VERIFIED via fallthrough, got {res.get('status')}: {res.get('message')}"
    assert res.get("mode") == "anchorless-crop", f"C7 expected anchorless-crop mode, got {res.get('mode')}"
    assert res.get("centre_id") == 89, f"C7 expected Centre 89, got {res.get('centre_id')}"
    print(f"  [+] Hijacked crop self-healed: {res['message']}")


def test_c8_fallthrough_size_guard():
    """C8: the stage-0->stage-1 fallthrough must NOT fire on full-page-sized
    images (a failing full-page decode must not be second-guessed by the
    anchorless engine)."""
    print("\n[C8] Fallthrough Size Guard (full-page not second-guessed)...")
    import core.decoder as dec
    full = np.full((dec.TARGET_H, dec.TARGET_W, 3), 255, np.uint8)
    small = cv2.imread(os.path.join(os.path.dirname(__file__), "fixtures", "crop_physics.png"))
    fh, fw = small.shape[:2]
    full[100:100 + fh, 100:100 + fw] = small

    orig = dec.detect_anchors
    try:
        dec.detect_anchors = lambda b: np.array(
            [[10, 10], [dec.TARGET_W - 10, 10],
             [dec.TARGET_W - 10, dec.TARGET_H - 10], [10, dec.TARGET_H - 10]], "float32")
        path = os.path.join(tempfile.gettempdir(), "c8_full.png")
        cv2.imwrite(path, full)
        try:
            res = decode_photo(path)
        finally:
            os.unlink(path)
    finally:
        dec.detect_anchors = orig

    assert res.get("mode") != "anchorless-crop", f"C8 guard leaked: full-page image used anchorless fallthrough"
    assert res.get("status") != "VERIFIED", "C8 expected non-verified stage-0 outcome on garbage full-page warp"
    print(f"  [+] Full-page hijack stayed in fiducial path: {res.get('status')} / {res.get('mode')}")


def main():
    print("=" * 70)
    print("ZeroLock — Anchorless Crop Recovery Acceptance Test Suite")
    print("=" * 70)

    test_c1_gate_crops()
    test_c2_real_physics_crop()
    test_c3_rotated_crops()
    test_c4_multi_centre_isolation()
    test_c5_short_crop_guard()
    test_c6_unwatermarked_crop_guard()
    test_c7_stage0_hijack_fallthrough()
    test_c8_fallthrough_size_guard()

    print("\n" + "=" * 70)
    print("ALL 8 CROP RECOVERY ACCEPTANCE SUITES PASSED [GO]")
    print("=" * 70)


if __name__ == "__main__":
    main()
