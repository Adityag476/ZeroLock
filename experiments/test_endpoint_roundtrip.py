import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import urllib.request
import json
import fitz
import pprint
from core.decoder import decode_photo

def test_endpoint_roundtrip():
    # 1. Fetch exam from running FastAPI endpoint
    exams = json.loads(urllib.request.urlopen("http://127.0.0.1:8000/api/exams/").read())
    exam_id = exams[0]["id"]
    url = f"http://127.0.0.1:8000/api/print/{exam_id}?centre_id=14&hall_id=3"
    print(f"Fetching live endpoint PDF from: {url}")
    pdf_bytes = urllib.request.urlopen(url).read()
    print(f"PDF bytes received: {len(pdf_bytes)}")

    # 2. Render PDF to image using PyMuPDF at 150 DPI and save
    os.makedirs("demo_assets", exist_ok=True)
    pdf_path = "demo_assets/test_endpoint_output.pdf"
    png_path = "demo_assets/test_endpoint_rendered.png"
    
    with open(pdf_path, "wb") as f:
        f.write(pdf_bytes)

    doc = fitz.open(pdf_path)
    page = doc[0]
    pix = page.get_pixmap(dpi=150)
    pix.save(png_path)
    print(f"Rendered PNG saved to: {png_path} ({pix.width}x{pix.height})")

    # 3. Decode via ZeroLock forensic pipeline
    result = decode_photo(png_path)
    print("\n--- Forensic Decoder Output ---")
    pprint.pprint(result)
    print("--------------------------------\n")

    assert result["status"] == "VERIFIED", f"Expected VERIFIED, got {result['status']}"
    assert result["centre_id"] == 14, f"Expected Centre 14, got {result['centre_id']}"
    assert result["hall_id"] == 3, f"Expected Hall 3, got {result['hall_id']}"
    print(f"[PASS] Successfully Decoded: Centre #{result['centre_id']} / Hall #{result['hall_id']} / Print #{result['print_num']}")
    print(">>> LIVE ENDPOINT ROUND-TRIP TEST PASSED: 100% SUCCESS!")

if __name__ == "__main__":
    test_endpoint_roundtrip()
