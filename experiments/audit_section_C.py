import os
import sys
import io
import time
import json
import requests
import fitz

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

from core.decoder import decode_photo
from PIL import Image

BASE_URL = "http://localhost:8000"
results = {}

print("=== Starting Section C Audit ===")

# First, check C4: Print BEFORE unlock on a fresh future-dated exam -> denied
print("\n--- C4: Print BEFORE unlock on fresh future exam ---")
t6_path = "experiments/fixtures/TY_DSP_26-27_Tutorial_6.pdf"
future_time = time.time() + 7200.0
with open(t6_path, "rb") as f:
    r_locked = requests.post(
        f"{BASE_URL}/api/exams/",
        files={"file": ("future_exam.pdf", f, "application/pdf")},
        data={"name": "Future Exam C4", "release_time": str(future_time)}
    )
locked_id = r_locked.json()["exam_id"]
r_print_early = requests.get(f"{BASE_URL}/api/print/{locked_id}?centre_id=14&hall_id=3")
print(f"Early print status: {r_print_early.status_code}")
print(f"Early print text: {r_print_early.text}")
c4_pass = (r_print_early.status_code == 403) and ("timelock" in r_print_early.text.lower())
results["C4"] = {"pass": c4_pass, "status": r_print_early.status_code, "text": r_print_early.text}

# Now create an exam to unlock and use for C1, C2, C5, C6
print("\n--- Creating Exam 1 for C1, C2, C5, C6 ---")
with open(t6_path, "rb") as f:
    r_ex1 = requests.post(
        f"{BASE_URL}/api/exams/",
        files={"file": ("T6_Exam1.pdf", f, "application/pdf")},
        data={"name": "DSP Exam 1", "release_time": str(time.time() + 3600.0)}
    )
exam1_id = r_ex1.json()["exam_id"]

# Unlock via warp + unlock
requests.post(f"{BASE_URL}/api/unlock/{exam1_id}/warp")
r_unl = requests.post(f"{BASE_URL}/api/unlock/{exam1_id}", json={"centre_id": 14, "hall_id": 3, "otp": "secret123"})
print(f"Unlock status: {r_unl.status_code}, response: {r_unl.json()}")

# C1: Print C14/H3 -> 200 PDF; decode -> VERIFIED 14/3/Print #1
print("\n--- C1: Print C14/H3 (Print #1) ---")
r_p1 = requests.get(f"{BASE_URL}/api/print/{exam1_id}?centre_id=14&hall_id=3")
print(f"Print 1 status: {r_p1.status_code}, length: {len(r_p1.content)} bytes")

# Decode Print 1
doc1 = fitz.open(stream=r_p1.content, filetype="pdf")
pix1 = doc1[0].get_pixmap(dpi=150)
pix1.save("temp_c1.png")
dec1 = decode_photo("temp_c1.png")
print(f"Decoded C1: status={dec1['status']}, centre={dec1.get('centre_id')}, hall={dec1.get('hall_id')}, print_num={dec1.get('print_num')}, conf={dec1.get('confidence')}")
c1_pass = (r_p1.status_code == 200) and (dec1["status"] == "VERIFIED") and (dec1.get("centre_id") == 14) and (dec1.get("hall_id") == 3) and (dec1.get("print_num") == 1)
results["C1"] = {"pass": c1_pass, "status": r_p1.status_code, "decoded": dec1}

# C2: Print C14/H3 again -> Print #2 (counter scoped per exam+centre+hall)
print("\n--- C2: Print C14/H3 again (Print #2) ---")
r_p2 = requests.get(f"{BASE_URL}/api/print/{exam1_id}?centre_id=14&hall_id=3")
print(f"Print 2 status: {r_p2.status_code}, length: {len(r_p2.content)} bytes")
doc2 = fitz.open(stream=r_p2.content, filetype="pdf")
pix2 = doc2[0].get_pixmap(dpi=150)
pix2.save("temp_c2.png")
dec2 = decode_photo("temp_c2.png")
print(f"Decoded C2: status={dec2['status']}, centre={dec2.get('centre_id')}, hall={dec2.get('hall_id')}, print_num={dec2.get('print_num')}, conf={dec2.get('confidence')}")
c2_pass = (r_p2.status_code == 200) and (dec2["status"] == "VERIFIED") and (dec2.get("centre_id") == 14) and (dec2.get("hall_id") == 3) and (dec2.get("print_num") == 2)
results["C2"] = {"pass": c2_pass, "status": r_p2.status_code, "decoded": dec2}

# C3: Print C14/H3 for the SECOND exam -> Print #1 (scoping across exams)
print("\n--- C3: Print C14/H3 for SECOND exam (Print #1) ---")
with open(t6_path, "rb") as f:
    r_ex2 = requests.post(
        f"{BASE_URL}/api/exams/",
        files={"file": ("T6_Exam2.pdf", f, "application/pdf")},
        data={"name": "DSP Exam 2", "release_time": str(time.time() + 3600.0)}
    )
exam2_id = r_ex2.json()["exam_id"]
requests.post(f"{BASE_URL}/api/unlock/{exam2_id}/warp")
requests.post(f"{BASE_URL}/api/unlock/{exam2_id}", json={"centre_id": 14, "hall_id": 3, "otp": "secret123"})

r_p3 = requests.get(f"{BASE_URL}/api/print/{exam2_id}?centre_id=14&hall_id=3")
print(f"Print exam2 status: {r_p3.status_code}, length: {len(r_p3.content)} bytes")
doc3 = fitz.open(stream=r_p3.content, filetype="pdf")
pix3 = doc3[0].get_pixmap(dpi=150)
pix3.save("temp_c3.png")
dec3 = decode_photo("temp_c3.png")
print(f"Decoded C3: status={dec3['status']}, centre={dec3.get('centre_id')}, hall={dec3.get('hall_id')}, print_num={dec3.get('print_num')}, conf={dec3.get('confidence')}")
c3_pass = (r_p3.status_code == 200) and (dec3["status"] == "VERIFIED") and (dec3.get("centre_id") == 14) and (dec3.get("hall_id") == 3) and (dec3.get("print_num") == 1)
results["C3"] = {"pass": c3_pass, "status": r_p3.status_code, "decoded": dec3}

# C5: Extract PDF text -> uploaded questions verbatim (no fixture text anywhere)
print("\n--- C5: Verbatim question text extraction ---")
text_extracted = doc1[0].get_text()
print("First 300 chars of extracted text:\n", text_extracted[:300])
norm_text = " ".join(text_extracted.split())
c5_has_dsp = ("impulse-invariant" in norm_text.lower()) and ("analog filter" in norm_text.lower())
# Verify fixture text like "Sample Exam Question" or "Mock" is not there
c5_no_fixture = ("fixture" not in norm_text.lower()) and ("sample exam" not in norm_text.lower())
c5_pass = c5_has_dsp and c5_no_fixture
print(f"c5_has_dsp={c5_has_dsp}, c5_no_fixture={c5_no_fixture}")
results["C5"] = {"pass": c5_pass, "has_dsp": c5_has_dsp, "no_fixture": c5_no_fixture}

# C6: Header line shows zero-padded Centre/Hall/Print exactly as UI claims
print("\n--- C6: Header zero-padding check ---")
expected_header_part = "[Centre 0014 | Hall 003 | Print #0001]"
print(f"Looking for '{expected_header_part}' in extracted text...")
c6_pass = expected_header_part in text_extracted
print(f"Found expected header: {c6_pass}")
results["C6"] = {"pass": c6_pass, "expected_header": expected_header_part}

print("\n=== SUMMARY OF SECTION C ===")
for k, v in results.items():
    print(f"{k}: {'PASS' if v['pass'] else 'FAIL'} | {v}")
