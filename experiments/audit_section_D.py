import os
import sys
import io
import time
import json
import zipfile
import requests
import fitz

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

from core.decoder import decode_photo

BASE_URL = "http://localhost:8000"
results = {}

print("=== Starting Section D Audit ===")

# First: Create an exam using Tutorial 4 (12 questions) for D1, D2, D3, D5
print("\n--- Uploading Tutorial 4 for Batch Job ---")
with open("experiments/fixtures/TY_DSP_26-27_Tutorial_4.pdf", "rb") as f:
    r_ex = requests.post(
        f"{BASE_URL}/api/exams/",
        files={"file": ("T4_Batch.pdf", f, "application/pdf")},
        data={"name": "DSP Tutorial 4 Batch", "release_time": str(time.time() + 3600.0)}
    )
exam_id = r_ex.json()["exam_id"]
print(f"Exam created: {exam_id}")

# D1: Trigger batch generate for [14, 28, 42]
print("\n--- D1: Batch generate for centres [14, 28, 42] ---")
r_gen = requests.post(
    f"{BASE_URL}/api/batch/generate",
    json={
        "exam_id": exam_id,
        "centre_ids": [14, 28, 42],
        "answer_key_text": "Q1: 100\nQ2: 200\nQ3: 300"
    }
)
print(f"Generate response: {r_gen.status_code}, {r_gen.json()}")
job_id = r_gen.json()["job_id"]

# Poll status until COMPLETED
max_polls = 60
status_data = {}
for i in range(max_polls):
    time.sleep(1.0)
    r_st = requests.get(f"{BASE_URL}/api/batch/status/{job_id}")
    status_data = r_st.json()
    st = status_data.get("status")
    prog = status_data.get("progress")
    print(f"Poll {i+1}: status={st}, progress={prog}")
    if st in ("COMPLETED", "FAILED"):
        break

centres = status_data.get("centres", {})
all_verified = (
    len(centres) == 3
    and all(c.get("self_check") == "VERIFIED" for c in centres.values())
)
d1_pass = (status_data.get("status") == "COMPLETED") and all_verified
print(f"D1: status={status_data.get('status')}, all_verified={all_verified}")
results["D1"] = {"pass": d1_pass, "status": status_data.get("status"), "centres": centres}

# D2: ZIP contains 3 PDFs + 3 DOCX; DOCX names carry _working_copy if round-trip unverifiable
print("\n--- D2: Check ZIP contents ---")
r_zip = requests.get(f"{BASE_URL}/api/batch/download/{job_id}")
print(f"Download ZIP status: {r_zip.status_code}, size: {len(r_zip.content)} bytes")
zf = zipfile.ZipFile(io.BytesIO(r_zip.content))
namelist = zf.namelist()
print(f"Files in ZIP: {namelist}")

pdfs = [n for n in namelist if n.endswith(".pdf")]
docxs = [n for n in namelist if n.endswith(".docx")]
has_3_pdfs = len(pdfs) == 3
has_3_docxs = len(docxs) == 3
# Check naming convention: _working_copy if not verified via libreoffice
docx_valid_names = all("_working_copy.docx" in n or re.match(r"centre_\d{4}\.docx", n) for n in docxs)
d2_pass = (r_zip.status_code == 200) and has_3_pdfs and has_3_docxs and docx_valid_names
print(f"has_3_pdfs={has_3_pdfs}, has_3_docxs={has_3_docxs}, docx_valid_names={docx_valid_names}")
results["D2"] = {"pass": d2_pass, "namelist": namelist}

# D3: Decode each zipped PDF -> correct centre, Print #1
print("\n--- D3: Decode each zipped PDF ---")
d3_results = {}
d3_all_pass = True
for cid in [14, 28, 42]:
    fname = f"centre_{cid:04d}.pdf"
    pdf_bytes = zf.read(fname)
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    mat = fitz.Matrix(150 / 72, 150 / 72)
    pix = doc[0].get_pixmap(matrix=mat, colorspace=fitz.csRGB)
    pix.save(f"temp_batch_{cid}.png")
    dec = decode_photo(f"temp_batch_{cid}.png")
    c_pass = (dec.get("status") == "VERIFIED") and (dec.get("centre_id") == cid) and (dec.get("print_num") == 1)
    print(f"Decoded {fname}: status={dec.get('status')}, centre={dec.get('centre_id')} (exp {cid}), print_num={dec.get('print_num')} (exp 1)")
    d3_results[cid] = {"pass": c_pass, "decoded": dec}
    if not c_pass:
        d3_all_pass = False

results["D3"] = {"pass": d3_all_pass, "details": d3_results}

# D4: Batch on a short (compact) paper -> still 3/3 VERIFIED
print("\n--- D4: Batch on short (compact) paper ---")
with open("experiments/fixtures/TY_DSP_26-27_Tutorial_6.pdf", "rb") as f:
    r_ex_short = requests.post(
        f"{BASE_URL}/api/exams/",
        files={"file": ("T6_Short_Batch.pdf", f, "application/pdf")},
        data={"name": "DSP Short Compact Batch", "release_time": str(time.time() + 3600.0)}
    )
short_exam_id = r_ex_short.json()["exam_id"]
r_gen_short = requests.post(
    f"{BASE_URL}/api/batch/generate",
    json={
        "exam_id": short_exam_id,
        "centre_ids": [14, 28, 42],
    }
)
short_job_id = r_gen_short.json()["job_id"]
for _ in range(max_polls):
    time.sleep(1.0)
    r_st = requests.get(f"{BASE_URL}/api/batch/status/{short_job_id}")
    st_data = r_st.json()
    if st_data.get("status") in ("COMPLETED", "FAILED"):
        break

short_centres = st_data.get("centres", {})
short_all_verified = (
    len(short_centres) == 3
    and all(c.get("self_check") == "VERIFIED" for c in short_centres.values())
)
d4_pass = (st_data.get("status") == "COMPLETED") and short_all_verified
print(f"D4: status={st_data.get('status')}, short_all_verified={short_all_verified}")
results["D4"] = {"pass": d4_pass, "status": st_data.get("status"), "centres": short_centres}

# D5: Evaluation-board key export downloadable; contains per-centre variant maps
print("\n--- D5: Evaluation-board key export ---")
r_keys = requests.get(f"{BASE_URL}/api/batch/answer-keys/{job_id}")
print(f"Answer keys status: {r_keys.status_code}")
keys_data = r_keys.json() if r_keys.status_code == 200 else {}
print(f"Keys data: {keys_data}")
has_answer_keys = (
    r_keys.status_code == 200
    and "centre_keys" in keys_data
    and len(keys_data["centre_keys"]) == 3
    and all("number_map" in k and "centre_id" in k for k in keys_data["centre_keys"])
)
d5_pass = has_answer_keys
results["D5"] = {"pass": d5_pass, "status": r_keys.status_code, "key_count": len(keys_data.get("centre_keys", []))}

print("\n=== SUMMARY OF SECTION D ===")
for k, v in results.items():
    print(f"{k}: {'PASS' if v['pass'] else 'FAIL'} | {v}")
