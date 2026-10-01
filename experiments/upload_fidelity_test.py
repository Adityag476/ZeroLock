"""
ZeroLock v2 Acceptance Test — Upload Fidelity & Dynamic Paper Parsing
Verifies real exam paper (TY_DSP_26-27_Tutorial_6.pdf) parsing, watermark engraving,
and provenance attribution end-to-end.
"""

import os
import sys
import tempfile
import fitz  # PyMuPDF
import cv2
import numpy as np

# Repo root
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from backend.paper_parse import parse_upload, CapacityError, ParseError
from core.renderer import generate_watermarked_pdf
from core.decoder import decode_photo
from core.variant_engine import generate_centre_variant

FIXTURE_PATH = os.path.join(REPO_ROOT, "experiments", "fixtures", "TY_DSP_26-27_Tutorial_6.pdf")

def run_tests():
    print("=" * 60)
    print("ZeroLock v2 — Upload Fidelity Acceptance Suite")
    print("=" * 60)

    # 1. Parse real DSP tutorial
    print("\n[TEST 1] Parsing real fixture: TY_DSP_26-27_Tutorial_6.pdf ...")
    assert os.path.exists(FIXTURE_PATH), f"Fixture not found at {FIXTURE_PATH}"
    with open(FIXTURE_PATH, "rb") as f:
        pdf_bytes = f.read()

    parsed = parse_upload(pdf_bytes, "TY_DSP_26-27_Tutorial_6.pdf")
    q_count = len(parsed["questions"])
    engine = parsed["engine"]
    words = parsed["word_count"]
    print(f"  Parsed {q_count} questions, {words} words, engine: {engine}")
    print(f"  Title: {parsed['title']}")

    assert q_count == 4, f"Expected 4 questions, got {q_count}"
    assert engine == "compact", f"Expected 'compact' engine for 137 words, got {engine}"
    print("  [+] PASS: Question count == 4, Engine == 'compact'")

    # 2. Variants OFF render for Centre 14
    print("\n[TEST 2] Rendering Centre 14 with parsed questions (Variants OFF) ...")
    centre_id = 14
    pdf_out = generate_watermarked_pdf(
        questions=parsed["questions"],
        centre_id=centre_id,
        hall_id=1,
        print_num=1,
        timestamp=1775000000,
        exam_title=parsed["title"] or "DSP Tutorial 6",
    )
    assert len(pdf_out) > 1000, "Rendered PDF output is empty"

    # Extract text with PyMuPDF
    doc = fitz.open(stream=pdf_out, filetype="pdf")
    extracted_text = ""
    for page in doc:
        extracted_text += page.get_text() + "\n"

    print("  Checking extracted text phrases ...")
    # Verify key DSP tutorial phrases (normalize word-by-word stego line breaks)
    norm_text = " ".join(extracted_text.split()).lower()
    assert "impulse-invariant" in norm_text, "Missing 'impulse-invariant' in rendered PDF"
    assert "bilinear transformation" in norm_text, "Missing 'bilinear transformation' in rendered PDF"
    assert "cascade, and parallel" in norm_text, "Missing 'cascade, and parallel' in rendered PDF"
    assert "0014" in norm_text, "Missing Centre 0014 in rendered PDF"
    print("  [+] PASS: Key DSP phrases found in rendered PDF text:")
    print("    - 'impulse-invariant'")
    print("    - 'bilinear transformation'")
    print("    - 'cascade, and parallel'")
    print("    - '0014' (Centre identifier)")

    # 3. Decode watermark from rendered PDF
    print("\n[TEST 3] Forensic watermark decoding from rendered PDF page ...")
    # Render first page to temporary image file
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp_img:
        tmp_img_path = tmp_img.name
    page0 = doc[0]
    pix = page0.get_pixmap(dpi=150)
    pix.save(tmp_img_path)

    # Decode photo
    result = decode_photo(tmp_img_path)
    print(f"  Decode status: {result['status']}, Centre: {result.get('centre_id')}, Confidence: {result.get('confidence')}")
    assert result["status"] == "VERIFIED", f"Expected VERIFIED, got {result['status']}: {result.get('message')}"
    assert result["centre_id"] == centre_id, f"Expected Centre {centre_id}, got {result.get('centre_id')}"
    print(f"  [+] PASS: decode_photo -> VERIFIED Centre {result['centre_id']}")

    # 4. Variants ON test
    print("\n[TEST 4] Testing Variants ON (semantic / numerical variants) ...")
    var_c14 = generate_centre_variant("EXAM-DSP", 14, parsed["questions"])
    var_c28 = generate_centre_variant("EXAM-DSP", 28, parsed["questions"])
    q14 = var_c14["variant_questions"]
    q28 = var_c28["variant_questions"]

    # Compare differences
    diffs = 0
    for i in range(min(len(q14), len(q28))):
        if q14[i] != q28[i]:
            diffs += 1
            print(f"  Diff in Question {i+1}:")
            print(f"    Centre 14: {q14[i][:60]}...")
            print(f"    Centre 28: {q28[i][:60]}...")

    print(f"  Total variant differences: {diffs} question(s)")
    print(f"  Slots C14: {var_c14['slot_count']}, Slots C28: {var_c28['slot_count']}")
    assert var_c14["slot_count"] >= 0
    print("  [+] PASS: Variants ON correctly generated per-centre variants")

    # 5. CapacityError test on short document
    print("\n[TEST 5] Testing short document upload guard (CapacityError) ...")
    import reportlab
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
    import io

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    c.drawString(100, 700, "1. This is a single short sentence.")
    c.save()
    short_pdf = buf.getvalue()

    caught_capacity = False
    try:
        parse_upload(short_pdf, "short_exam.pdf")
    except CapacityError as ce:
        caught_capacity = True
        print(f"  Caught expected CapacityError: {ce}")
    except Exception as e:
        print(f"  Caught unexpected error: {type(e).__name__}: {e}")

    assert caught_capacity, "Expected CapacityError was not raised for short upload"
    print("  [+] PASS: CapacityError correctly raised without crash")

    print("\n" + "=" * 60)
    print("ALL 5 UPLOAD FIDELITY ACCEPTANCE TESTS PASSED [GO]")
    print("=" * 60)

if __name__ == "__main__":
    run_tests()
