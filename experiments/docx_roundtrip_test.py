"""
ZeroLock v2 — DOCX Round-Trip Acceptance Test
===============================================
Tests DOCX generation with word-spacing steganography.
Verifies that the DOCX can be created and contains
the expected structure (working copy mode if LibreOffice unavailable).
"""

import sys
import os
import time
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

QUESTIONS = [
    "Explain the working principle of a digital watermark. How does it differ from a traditional visible watermark?",
    "A train departs from Station A at 60 km/h and returns from Station B at 40 km/h. Calculate the average speed.",
    "Describe how Reed-Solomon error correction codes work.",
    "Define the term homography in the context of computer vision.",
    "A rectangular block of mass 10 kg rests on a horizontal surface. Calculate the minimum force to move it.",
]


def main():
    print("=" * 60)
    print("ZeroLock v2 — DOCX Round-Trip Acceptance Test")
    print("=" * 60)
    print()

    # Step 1: Check python-docx is available
    try:
        import docx
        print("[PASS]  python-docx is installed")
    except ImportError:
        print("[SKIP]  python-docx not installed — DOCX tests skipped")
        print("        Install with: pip install python-docx")
        print()
        print("=" * 60)
        print("DOCX TEST: [SKIP]")
        print("=" * 60)
        return 0

    # Step 2: Generate stego bits
    from core.payload import encode_payload
    centre_id = 14
    hall_id = 3
    print_num = 1
    ts = int(time.time())

    stego_bits = encode_payload(centre_id, hall_id, print_num, ts)
    print(f"[PASS]  Stego payload encoded: {len(stego_bits)} bits")

    # Step 3: Generate DOCX using the batch route's function
    from backend.routes.batch import _generate_docx

    docx_bytes = _generate_docx(
        questions=QUESTIONS,
        centre_id=centre_id,
        hall_id=hall_id,
        print_num=print_num,
        exam_title="ZeroLock v2 DOCX Round-Trip Test Paper",
        stego_bits=stego_bits,
    )

    if docx_bytes is None:
        print("[FAIL]  DOCX generation returned None")
        return 1

    print(f"[PASS]  DOCX generated: {len(docx_bytes):,} bytes")

    # Step 4: Verify DOCX structure
    tmpdir = tempfile.mkdtemp(prefix="zl_docx_test_")
    docx_path = os.path.join(tmpdir, "test.docx")
    with open(docx_path, "wb") as f:
        f.write(docx_bytes)

    doc = docx.Document(docx_path)

    # Check page count (paragraphs exist)
    para_count = len(doc.paragraphs)
    has_paras = para_count > 5
    print(f"[{'PASS' if has_paras else 'FAIL'}]  Paragraphs: {para_count}")

    # Check that questions are present
    full_text = "\n".join(p.text for p in doc.paragraphs)
    q_found = sum(1 for q in QUESTIONS if q[:30] in full_text)
    all_q_found = q_found == len(QUESTIONS)
    print(f"[{'PASS' if all_q_found else 'FAIL'}]  Questions found: {q_found}/{len(QUESTIONS)}")

    # Check that centre/hall info is present
    has_centre = f"Centre {centre_id:04d}" in full_text
    has_hall = f"Hall {hall_id:03d}" in full_text
    print(f"[{'PASS' if has_centre else 'FAIL'}]  Centre ID in header")
    print(f"[{'PASS' if has_hall else 'FAIL'}]  Hall ID in header")

    # Check font is Times New Roman
    fonts_used = set()
    for para in doc.paragraphs:
        for run in para.runs:
            if run.font.name:
                fonts_used.add(run.font.name)
    has_tnr = "Times New Roman" in fonts_used
    print(f"[{'PASS' if has_tnr else 'FAIL'}]  Font: Times New Roman {'found' if has_tnr else 'not found'}")
    if fonts_used:
        print(f"        Fonts used: {fonts_used}")

    # Check word spacing XML elements exist (stego)
    from docx.oxml.ns import qn
    spacing_elements = 0
    for para in doc.paragraphs:
        for run in para.runs:
            rpr = run._element.find(qn('w:rPr'))
            if rpr is not None:
                sp = rpr.find(qn('w:spacing'))
                if sp is not None:
                    spacing_elements += 1
    has_stego = spacing_elements > 10
    print(f"[{'PASS' if has_stego else 'FAIL'}]  Word-spacing stego elements: {spacing_elements}")

    # Step 5: LibreOffice round-trip (conditional)
    from backend.routes.batch import _docx_roundtrip_check
    rt_result = _docx_roundtrip_check(docx_bytes)
    if rt_result.get("status") == "SKIP":
        print(f"[SKIP]  LibreOffice not available — PDF round-trip skipped")
        print(f"        DOCX ships as 'working copy' (PDF is the official watermarked copy)")
    elif rt_result.get("status") == "VERIFIED":
        print(f"[PASS]  LibreOffice PDF round-trip: VERIFIED")
    else:
        print(f"[WARN]  LibreOffice PDF round-trip: {rt_result.get('status')}")
        print(f"        {rt_result.get('message', '')}")

    # Final verdict
    overall = has_paras and all_q_found and has_centre and has_tnr and has_stego
    print()
    print("=" * 60)
    print(f"DOCX TEST: [{'PASS' if overall else 'FAIL'}]")
    print("=" * 60)

    # Cleanup
    try:
        os.unlink(docx_path)
        os.rmdir(tmpdir)
    except OSError:
        pass

    return 0 if overall else 1


if __name__ == "__main__":
    sys.exit(main())
