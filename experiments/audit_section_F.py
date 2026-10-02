import os
import sys
import io
import time
import cv2
import numpy as np
import fitz

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

from core.renderer import generate_watermarked_pdf
from core.decoder import decode_photo

results = {}

print("=== Starting Section F Audit ===")

# Standard 10 questions from gate_test for F1-F6
QUESTIONS_10 = [
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

def render_pdf_to_img(pdf_bytes, dpi=150):
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page = doc[0]
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)
    img_bytes = pix.tobytes("png")
    buf = np.frombuffer(img_bytes, dtype=np.uint8)
    img = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    doc.close()
    return img

# Generate C14 PDF
pdf_c14 = generate_watermarked_pdf(
    questions=QUESTIONS_10,
    centre_id=14,
    hall_id=3,
    print_num=1,
    timestamp=1726500000,
    exam_title="Standard Forensic Benchmark Exam",
)
img_c14 = render_pdf_to_img(pdf_c14, dpi=150)

# F1: Render C14 PDF @150 DPI -> decode VERIFIED 14, conf >= 0.9
print("\n--- F1: Baseline decode at 150 DPI ---")
cv2.imwrite("temp_f1.png", img_c14)
dec_f1 = decode_photo("temp_f1.png")
print(f"F1 decode: {dec_f1}")
f1_pass = (dec_f1.get("status") == "VERIFIED") and (dec_f1.get("centre_id") == 14) and (dec_f1.get("confidence", 0.0) >= 0.9)
results["F1"] = {"pass": f1_pass, "data": dec_f1}

# F2: JPEG Q55 of same -> VERIFIED 14
print("\n--- F2: JPEG Q55 compression ---")
cv2.imwrite("temp_f2.jpg", img_c14, [cv2.IMWRITE_JPEG_QUALITY, 55])
dec_f2 = decode_photo("temp_f2.jpg")
print(f"F2 decode: {dec_f2}")
f2_pass = (dec_f2.get("status") == "VERIFIED") and (dec_f2.get("centre_id") == 14)
results["F2"] = {"pass": f2_pass, "data": dec_f2}

# F3: +20 brightness, 3° rotation -> VERIFIED 14
print("\n--- F3: +20 brightness, 3 deg rotation ---")
h, w = img_c14.shape[:2]
bright = cv2.convertScaleAbs(img_c14, alpha=1.15, beta=20)
M = cv2.getRotationMatrix2D((w / 2, h / 2), 3.0, 0.94)
rot = cv2.warpAffine(bright, M, (w, h), borderValue=(255, 255, 255))
cv2.imwrite("temp_f3.jpg", rot, [cv2.IMWRITE_JPEG_QUALITY, 85])
dec_f3 = decode_photo("temp_f3.jpg")
print(f"F3 decode: {dec_f3}")
f3_pass = (dec_f3.get("status") == "VERIFIED") and (dec_f3.get("centre_id") == 14)
results["F3"] = {"pass": f3_pass, "data": dec_f3}

# F4: Unwatermarked clean page -> UNKNOWN, zero blame (never a centre id)
print("\n--- F4: Unwatermarked page ---")
clean_img = np.full((1754, 1241, 3), 255, dtype=np.uint8)
cv2.putText(clean_img, "Unwatermarked regular document text.", (100, 200), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 2)
cv2.imwrite("temp_f4.png", clean_img)
dec_f4 = decode_photo("temp_f4.png")
print(f"F4 decode: {dec_f4}")
f4_pass = (dec_f4.get("status") == "UNKNOWN") and (dec_f4.get("centre_id") is None)
results["F4"] = {"pass": f4_pass, "data": dec_f4}

# F5: Photo with one anchor covered (paste grey box over crosshair) -> parallelogram fallback -> VERIFIED
print("\n--- F5: One anchor covered (parallelogram fallback) ---")
img_covered = img_c14.copy()
# Paste grey box over top-left crosshair (located at approx 46, 46)
cv2.rectangle(img_covered, (20, 20), (75, 75), (128, 128, 128), -1)
cv2.imwrite("temp_f5.png", img_covered)
dec_f5 = decode_photo("temp_f5.png")
print(f"F5 decode: {dec_f5}")
f5_pass = (dec_f5.get("status") == "VERIFIED") and (dec_f5.get("centre_id") == 14)
results["F5"] = {"pass": f5_pass, "data": dec_f5}

# F6: 70% centre-crop -> either compact recovery VERIFIED or honest UNKNOWN — NEVER a wrong centre
print("\n--- F6: 70% centre crop ---")
ch0, ch1 = int(h * 0.15), int(h * 0.85)
cw0, cw1 = int(w * 0.15), int(w * 0.85)
crop = img_c14[ch0:ch1, cw0:cw1]
cv2.imwrite("temp_f6.png", crop)
dec_f6 = decode_photo("temp_f6.png")
print(f"F6 decode: {dec_f6}")
cid_f6 = dec_f6.get("centre_id")
f6_pass = (cid_f6 is None) or (cid_f6 == 14)  # NEVER a wrong centre
results["F6"] = {"pass": f6_pass, "data": dec_f6}

# F7: Math-heavy paper (Tutorial 4) photo -> VERIFIED correct centre (min_ink fix holds)
print("\n--- F7: Math-heavy paper (Tutorial 4) photo ---")
from backend.paper_parse import parse_upload
t4_bytes = open("experiments/fixtures/TY_DSP_26-27_Tutorial_4.pdf", "rb").read()
parsed_t4 = parse_upload(t4_bytes, "t4.pdf")
pdf_t4 = generate_watermarked_pdf(
    questions=parsed_t4["questions"],
    centre_id=14,
    hall_id=3,
    print_num=1,
    timestamp=1726500000,
    exam_title="DSP Tutorial 4 Math",
)
img_t4 = render_pdf_to_img(pdf_t4, dpi=150)
cv2.imwrite("temp_f7.jpg", img_t4, [cv2.IMWRITE_JPEG_QUALITY, 85])
dec_f7 = decode_photo("temp_f7.jpg")
print(f"F7 decode: {dec_f7}")
f7_pass = (dec_f7.get("status") == "VERIFIED") and (dec_f7.get("centre_id") == 14)
results["F7"] = {"pass": f7_pass, "data": dec_f7}

print("\n=== SUMMARY OF SECTION F ===")
for k, v in results.items():
    print(f"{k}: {'PASS' if v['pass'] else 'FAIL'} | {v}")
