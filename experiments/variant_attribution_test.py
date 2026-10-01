"""
ZeroLock v2 — Variant Attribution Acceptance Test
===================================================
For each of 5 centres:
  (a) Paste variant plaintext into inspector → correct centre, separation ≥ +50%
  (b) OCR-simulate the variant text (typo injection 2%) → still correct centre

Also: difficulty-invariance check over all 5 variants → index 1.00 each.
"""

import sys
import os
import random

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.variant_engine import (
    generate_centre_variant,
    inspect_variant_text,
    compute_difficulty_index,
)

CENTRE_IDS = [14, 28, 42, 7, 99]
EXAM_ID = "BATCH-TEST-001"

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

ANSWER_KEY = (
    "Q1: Watermarks embed hidden data into documents. "
    "Q2: Average speed = 2*60*40/(60+40) = 48 km/h. Distance is constant. "
    "Q3: RS codes use polynomial evaluation over GF(2^8). With 10 parity symbols, corrects up to 5 errors. "
    "Q4: Homography H is a 3x3 projective matrix. Perspective correction uses H to map 4 source to 4 destination points. "
    "Q5: F = mu * m * g = 0.4 * 10 * 9.8 = 39.2 N. Take g = 9.8 m/s^2. "
    "Q6: Symmetric (AES) uses same key. Asymmetric (RSA) uses key pair. "
    "Q7: Area = integral from -1 to 2 of (x+2-x^2) dx = 4.5 sq units. "
    "Q8: Shamir splits secret into k-of-n shares using polynomial interpolation. "
    "Q9: C(t) = 8e^(-0.5t) < 1 => t > 2*ln(8) = 4.16 s. Exposure = 16*(1-e^(-0.5*4.16)) = 14.0 mg*s/L. "
    "Q10: OSI has 7 layers. TCP/IP has 4 layers. Application layer: HTTP."
)


def inject_typos(text: str, rate: float = 0.02) -> str:
    """Simulate OCR errors by injecting character-level typos at the given rate."""
    random.seed(42)  # Reproducible
    chars = list(text)
    typo_chars = "abcdefghijklmnopqrstuvwxyz0123456789"
    for i in range(len(chars)):
        if random.random() < rate and chars[i].isalnum():
            chars[i] = random.choice(typo_chars)
    return "".join(chars)


def main():
    print("=" * 60)
    print("ZeroLock v2 — Variant Attribution Acceptance Test")
    print("=" * 60)
    print()

    # Pre-generate all variants
    variants = {}
    for cid in CENTRE_IDS:
        variants[cid] = generate_centre_variant(EXAM_ID, cid, QUESTIONS, ANSWER_KEY)

    results_a = []   # Clean text attribution
    results_b = []   # OCR-simulated attribution
    results_di = []  # Difficulty invariance

    print("--- Part A: Clean variant text attribution ---")
    for cid in CENTRE_IDS:
        v = variants[cid]
        # Simulate leaked text: paste all variant questions
        leaked = "\n".join(v["variant_questions"])

        result = inspect_variant_text(
            leaked_text=leaked,
            exam_id=EXAM_ID,
            questions=QUESTIONS,
            centre_ids=CENTRE_IDS,
            answer_key_text=ANSWER_KEY,
        )

        correct = result.get("implicated_centre_id") == cid
        separation = result.get("separation_margin", 0.0)
        sep_ok = separation >= 50.0

        icon = "[PASS]" if (correct and sep_ok) else "[FAIL]"
        print(f"  Centre {cid:04d}: {icon}  "
              f"attributed={result.get('implicated_centre_id', '?')}  "
              f"confidence={result.get('confidence', 0)}%  "
              f"separation=+{separation}%")

        results_a.append({
            "centre_id": cid,
            "correct": correct,
            "separation_ok": sep_ok,
            "passed": correct and sep_ok,
            "result": result,
        })

    print()
    print("--- Part B: OCR-simulated text attribution (2% typo injection) ---")
    for cid in CENTRE_IDS:
        v = variants[cid]
        leaked = "\n".join(v["variant_questions"])
        leaked_ocr = inject_typos(leaked, rate=0.02)

        result = inspect_variant_text(
            leaked_text=leaked_ocr,
            exam_id=EXAM_ID,
            questions=QUESTIONS,
            centre_ids=CENTRE_IDS,
            answer_key_text=ANSWER_KEY,
        )

        correct = result.get("implicated_centre_id") == cid
        icon = "[PASS]" if correct else "[FAIL]"
        print(f"  Centre {cid:04d}: {icon}  "
              f"attributed={result.get('implicated_centre_id', '?')}  "
              f"confidence={result.get('confidence', 0)}%  "
              f"separation=+{result.get('separation_margin', 0)}%")

        results_b.append({
            "centre_id": cid,
            "correct": correct,
            "passed": correct,
            "result": result,
        })

    print()
    print("--- Part C: Difficulty invariance check ---")
    for cid in CENTRE_IDS:
        v = variants[cid]
        di = compute_difficulty_index(QUESTIONS, v["variant_questions"])
        passed = di == 1.00
        icon = "[PASS]" if passed else "[FAIL]"
        print(f"  Centre {cid:04d}: {icon}  difficulty_index={di}")
        results_di.append({"centre_id": cid, "index": di, "passed": passed})

    print()
    print("-" * 60)

    a_pass = sum(1 for r in results_a if r["passed"])
    b_pass = sum(1 for r in results_b if r["passed"])
    di_pass = sum(1 for r in results_di if r["passed"])
    total = len(CENTRE_IDS)

    print(f"Part A (clean attribution):    {a_pass}/{total}")
    print(f"Part B (OCR 2% typo):          {b_pass}/{total}")
    print(f"Part C (difficulty invariance): {di_pass}/{total}")

    overall = (a_pass == total) and (b_pass == total) and (di_pass == total)
    print()
    print(f"{'=' * 60}")
    print(f"VARIANT ATTRIBUTION TEST: {'[PASS]' if overall else '[FAIL]'}")
    print(f"{'=' * 60}")

    return 0 if overall else 1


if __name__ == "__main__":
    sys.exit(main())
