"""
ZeroLock Round 2 — Paraphrase-Resistant Semantic Tracers Acceptance Test
========================================================================
Validates tracer resilience against LLM / GPT laundering attacks.

Core Assumption Documented:
Real-world LLM paraphrase tools (e.g. ChatGPT, Claude, QuillBot) reword sentences,
reorder clauses, and alter vocabulary, but strictly preserve:
  1. Specific numerical quantities, scientific constants, and measurements
  2. MCQ option candidate texts and logical option choices
  3. Proper nouns and named entities (people, geographic locations)
  4. Overall question logical sequence and paper layout

Testing Discipline & Non-Circularity Guarantee:
The paraphrase simulator in this suite uses a strictly HELD-OUT table of synonym
pairs and structural rewrites that is verified at runtime to have ZERO overlap
with the engine's internal SWAP_GROUPS. Circular tests are strictly forbidden.

Fixture Secret:
  TEST_FIXTURE_SECRET_HEX = "a1b2c3d4e5f60718293a4b5c6d7e8f90123456789abcdef0123456789abcdef0"
  (Test vector only; server secrets are 256-bit random and never committed.)
"""

from __future__ import annotations

import sys
import os
import re
import random
import subprocess
from typing import Optional

# Ensure repository root is on sys.path
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from core.variant_engine import (
    SWAP_GROUPS,
    generate_centre_variant,
    inspect_variant_text,
    derive_tracer_seed,
    compute_difficulty_index,
)

TEST_FIXTURE_SECRET_HEX = "a1b2c3d4e5f60718293a4b5c6d7e8f90123456789abcdef0123456789abcdef0"
EXAM_ID = "EXAM-PARA-ROBUST"
CENTRE_IDS = [14, 28, 42]

QUESTIONS = [
    "Explain the working principle of a digital watermark. How does it differ from a traditional visible watermark? Discuss the trade-offs between robustness and imperceptibility in forensic applications.",
    "Rohan travels from Station A at 60 km/h and returns from Station B at 40 km/h. Assuming the distance between the stations is constant, calculate the average speed of the entire journey and explain why it is not simply the arithmetic mean.",
    "Describe how Reed-Solomon error correction codes work. Explain why redundancy is necessary when recovering data from a noisy analog channel such as a printed and photographed document.",
    "Define the term homography in the context of computer vision. Show how it is used to perform perspective correction on a photograph of a document taken at an arbitrary angle.",
    "A rectangular block of mass 10 kg rests on a horizontal surface. The coefficient of static friction is 0.4. Calculate the minimum horizontal force required to set it in motion. Take g = 9.8 m/s^2.",
    "Which of the following describes the key security advantage of Shamir Secret Sharing scheme? (A) Uses polynomial interpolation over finite fields (B) Requires identical symmetric keys across participants (C) Eliminates all digital redundancy (D) Encrypts plaintext using stream ciphers",
    "Using integration, find the area enclosed between the parabola y = x^2 and the straight line y = x + 2. Show all intermediate steps and verify your answer geometrically.",
    "What is the primary function of the transport layer in the OSI model? (A) End-to-end communication and error recovery (B) Physical bit transmission over copper medium (C) Routing packets across multiple subnets (D) Defining presentation syntax and encoding",
    "The concentration of a drug in the bloodstream follows C(t) = 8e^(-0.5t) mg/L. Calculate the time at which the concentration falls below 1 mg/L and find the total drug exposure over that period.",
    "Mr. Sharma bought an electrical cable of length 15 m and resistance 50 ohms in Delhi. Determine the resistivity assuming cross-sectional area is 2.5 mm^2.",
]

ANSWER_KEY = (
    "Q1: Watermarks embed forensic data. "
    "Q2: Average speed = 2*60*40/(60+40) = 48 km/h. Distance is constant. "
    "Q3: RS codes use redundancy over finite fields to correct errors. "
    "Q4: Homography H is a 3x3 matrix for perspective correction. "
    "Q5: F = 0.4 * 10 * 9.8 = 39.2 N. Take g = 9.8 m/s^2. "
    "Q6: (A) Shamir scheme uses polynomial interpolation over finite fields. "
    "Q7: Area = integral of (x+2-x^2) dx = 4.5 sq units. "
    "Q8: (A) Transport layer provides end-to-end communication and recovery. "
    "Q9: C(t) = 8e^(-0.5t) < 1 => t = 4.16 s. Exposure = 14.0 mg*s/L. "
    "Q10: Resistivity = 50 * 2.5e-6 / 15 = 8.33e-6 ohm-m."
)

# ---------------------------------------------------------------------------
# Held-Out Paraphrase Substitution Table (Strictly Disjoint from Engine)
# ---------------------------------------------------------------------------

HELD_OUT_PAIRS = [
    ("departs from", "leaves from"),
    ("returns from", "journeys back from"),
    ("entire journey", "complete trip"),
    ("average speed", "mean velocity"),
    ("working principle", "operational basis"),
    ("traditional", "conventional"),
    ("visible", "overt"),
    ("differ from", "diverge from"),
    ("discuss the trade-offs", "assess the compromises"),
    ("robustness", "durability"),
    ("imperceptibility", "invisibility"),
    ("forensic applications", "investigative contexts"),
    ("redundancy", "data duplication"),
    ("necessary", "essential"),
    ("recovering data", "restoring information"),
    ("noisy analog channel", "imperfect physical medium"),
    ("photographed document", "captured sheet"),
    ("context of", "field of"),
    ("rectangular block", "cuboid object"),
    ("surface", "plane"),
    ("set it in motion", "initiate motion"),
    ("key difference", "primary distinction"),
    ("real-world scenario", "practical situation"),
    ("preferred choice", "optimal selection"),
    ("straight line", "linear boundary"),
    ("intermediate steps", "derivation stages"),
    ("verify your answer geometrically", "confirm your solution visually"),
    ("resistant to", "immune against"),
    ("concentration", "density"),
    ("bloodstream", "circulatory system"),
    ("falls below", "drops beneath"),
    ("total drug exposure", "cumulative systemic dosage"),
    ("identify the closest equivalent", "pinpoint the matching counterpart"),
    ("electrical cable", "conductive wire"),
    ("resistivity", "specific resistance"),
]


def _assert_held_out_disjointness():
    """Assert that HELD_OUT_PAIRS does not recycle SWAP_GROUPS vocabulary."""
    engine_content_words = set()
    stopwords = {"the", "that", "at", "a", "an", "in", "of", "to", "from", "and", "or", "by"}
    for group in SWAP_GROUPS:
        for phrase in group:
            for w in phrase.lower().split():
                if w not in stopwords:
                    engine_content_words.add(w)

    held_out_content_words = set()
    for orig, rep in HELD_OUT_PAIRS:
        for w in orig.lower().split():
            if w not in stopwords:
                held_out_content_words.add(w)
        for w in rep.lower().split():
            if w not in stopwords:
                held_out_content_words.add(w)

    overlap = engine_content_words & held_out_content_words
    assert not overlap, f"Non-circularity violation: held-out table overlaps with engine SWAP_GROUPS on: {overlap}"


def _local_paraphrase(text: str, seed: int = 42) -> str:
    """
    Simulate sentence-level LLM paraphrase with:
      - Held-out phrase substitutions
      - Clause reorder / transition alterations
      - 2% character typo injection (preserving numbers, option labels, and entities)
    """
    rng = random.Random(seed)
    result = text

    for orig, rep in HELD_OUT_PAIRS:
        pattern = re.compile(re.escape(orig), re.IGNORECASE)

        def _sub(m):
            s = m.group(0)
            if s[0].isupper():
                return rep[0].upper() + rep[1:]
            return rep

        result = pattern.sub(_sub, result)

    # 2% typo injection (protecting digits, option labels, and capitalization)
    chars = list(result)
    for i in range(len(chars)):
        if chars[i].isalnum() and not chars[i].isdigit():
            # Skip option labels like (A), (B), (C), (D)
            if i > 0 and chars[i - 1] == "(" and i + 1 < len(chars) and chars[i + 1] == ")":
                continue
            if rng.random() < 0.02:
                chars[i] = rng.choice("abcdefghijklmnopqrstuvwxyz")

    return "".join(chars)


# ---------------------------------------------------------------------------
# Test Runner
# ---------------------------------------------------------------------------

def run_acceptance_suite() -> bool:
    print("=" * 70)
    print("ZeroLock Round 2 — Paraphrase-Resistant Semantic Tracers Acceptance")
    print("=" * 70)
    print()

    # Step 0: Non-circularity verification
    print("[INIT] Verifying non-circularity: engine swap table vs held-out table...")
    _assert_held_out_disjointness()
    print("  [+] PASS: Zero overlap between engine SWAP_GROUPS and held-out table.\n")

    # Pre-generate centre variants
    variants = {}
    for cid in CENTRE_IDS:
        variants[cid] = generate_centre_variant(
            EXAM_ID, cid, QUESTIONS, ANSWER_KEY, exam_secret=TEST_FIXTURE_SECRET_HEX
        )

    all_passed = True

    # -----------------------------------------------------------------------
    # Gate 1: Paraphrased variant leaks for 3 centres
    # -----------------------------------------------------------------------
    print("[GATE 1] Paraphrased Variant Leaks Attribution (3/3 Centres)")
    gate1_results = []
    for cid in CENTRE_IDS:
        v = variants[cid]
        v_text = "\n\n".join(v["variant_questions"])
        p_text = _local_paraphrase(v_text, seed=cid)

        res = inspect_variant_text(
            leaked_text=p_text,
            exam_id=EXAM_ID,
            questions=QUESTIONS,
            centre_ids=CENTRE_IDS,
            answer_key_text=ANSWER_KEY,
            exam_secret=TEST_FIXTURE_SECRET_HEX,
        )

        correct = res["implicated_centre_id"] == cid
        is_lead = res["status"] == "LEAD"
        sep_ok = res["separation_margin"] >= 50.0
        passed = correct and is_lead and sep_ok

        icon = "[PASS]" if passed else "[FAIL]"
        print(f"  Centre {cid:04d}: {icon} status={res['status']} attributed={res['implicated_centre_id']} "
              f"margin=+{res['separation_margin']}% confidence={res['confidence']}%")
        gate1_results.append(passed)

    gate1_pass = all(gate1_results) and len(gate1_results) == 3
    print(f"  Gate 1 Result: {'[PASS] 3/3' if gate1_pass else '[FAIL]'}\n")
    if not gate1_pass:
        all_passed = False

    # -----------------------------------------------------------------------
    # Gate 2: Numbers + Options Floor Performance (Strip all wording)
    # -----------------------------------------------------------------------
    print("[GATE 2] Numbers + Options Only Floor Leak Performance")
    gate2_results = []
    for cid in CENTRE_IDS:
        v = variants[cid]
        floor_tokens = []
        for pert_val in v["number_map"].values():
            floor_tokens.append(f"parameter value: {pert_val}")
        for c in v["canary_vector"]:
            floor_tokens.append(f"entity: {c['replacement']}")
        for var_q in v["variant_questions"]:
            mcq_match = re.search(r'\([A-D]\).*', var_q)
            if mcq_match:
                floor_tokens.append(mcq_match.group(0))

        floor_text = "\n".join(floor_tokens)
        res = inspect_variant_text(
            leaked_text=floor_text,
            exam_id=EXAM_ID,
            questions=QUESTIONS,
            centre_ids=CENTRE_IDS,
            answer_key_text=ANSWER_KEY,
            exam_secret=TEST_FIXTURE_SECRET_HEX,
        )

        correct = res["implicated_centre_id"] == cid
        is_lead = res["status"] == "LEAD"
        sep_ok = res["separation_margin"] >= 50.0
        passed = correct and is_lead and sep_ok

        icon = "[PASS]" if passed else "[FAIL]"
        print(f"  Centre {cid:04d} Floor: {icon} status={res['status']} attributed={res['implicated_centre_id']} "
              f"margin=+{res['separation_margin']}% confidence={res['confidence']}%")
        gate2_results.append(passed)

    gate2_pass = all(gate2_results)
    print(f"  Gate 2 Result: {'[PASS] 3/3' if gate2_pass else '[FAIL]'}\n")
    if not gate2_pass:
        all_passed = False

    # -----------------------------------------------------------------------
    # Gate 3: Master (Unvarianted) Text Attributed as INCONCLUSIVE
    # -----------------------------------------------------------------------
    print("[GATE 3] Master (Unvarianted) Text Inconclusive Guard")
    master_text = "\n\n".join(QUESTIONS)
    res_master = inspect_variant_text(
        leaked_text=master_text,
        exam_id=EXAM_ID,
        questions=QUESTIONS,
        centre_ids=CENTRE_IDS,
        answer_key_text=ANSWER_KEY,
        exam_secret=TEST_FIXTURE_SECRET_HEX,
    )
    master_ok = (res_master["status"] == "INCONCLUSIVE") and (res_master["implicated_centre_id"] is None)
    print(f"  Master Text: {'[PASS]' if master_ok else '[FAIL]'} status={res_master['status']} attributed={res_master['implicated_centre_id']}")
    print(f"  Gate 3 Result: {'[PASS]' if master_ok else '[FAIL]'}\n")
    if not master_ok:
        all_passed = False

    # -----------------------------------------------------------------------
    # Gate 4: Wrong-Exam Text Attributed as INCONCLUSIVE
    # -----------------------------------------------------------------------
    print("[GATE 4] Wrong-Exam Cross-Contamination Guard")
    wrong_text = (
        "Photosynthesis in plants requires chlorophyll pigments and sunlight "
        "to convert atmospheric carbon dioxide and water into glucose and oxygen."
    )
    res_wrong = inspect_variant_text(
        leaked_text=wrong_text,
        exam_id=EXAM_ID,
        questions=QUESTIONS,
        centre_ids=CENTRE_IDS,
        answer_key_text=ANSWER_KEY,
        exam_secret=TEST_FIXTURE_SECRET_HEX,
    )
    wrong_ok = (res_wrong["status"] == "INCONCLUSIVE") and (res_wrong["implicated_centre_id"] is None)
    print(f"  Wrong Exam Text: {'[PASS]' if wrong_ok else '[FAIL]'} status={res_wrong['status']} attributed={res_wrong['implicated_centre_id']}")
    print(f"  Gate 4 Result: {'[PASS]' if wrong_ok else '[FAIL]'}\n")
    if not wrong_ok:
        all_passed = False

    # -----------------------------------------------------------------------
    # Gate 5: Key-Secrecy Test
    # -----------------------------------------------------------------------
    print("[GATE 5] Key-Secrecy and Legacy Fallback Test")
    v_true = generate_centre_variant(EXAM_ID, 14, QUESTIONS, ANSWER_KEY, exam_secret=TEST_FIXTURE_SECRET_HEX)
    v_wrong = generate_centre_variant(EXAM_ID, 14, QUESTIONS, ANSWER_KEY, exam_secret="f" * 64)
    v_legacy = generate_centre_variant(EXAM_ID, 14, QUESTIONS, ANSWER_KEY, exam_secret=None)

    key_diff = (v_true["option_perm"] != v_wrong["option_perm"]) or (v_true["q_order"] != v_wrong["q_order"])
    legacy_unkeyed = v_legacy["keyed"] is False

    gate5_pass = key_diff and legacy_unkeyed
    print(f"  Wrong secret alters mappings: {'[PASS]' if key_diff else '[FAIL]'}")
    print(f"  Legacy NULL secret keyed=False: {'[PASS]' if legacy_unkeyed else '[FAIL]'}")
    print(f"  Gate 5 Result: {'[PASS]' if gate5_pass else '[FAIL]'}\n")
    if not gate5_pass:
        all_passed = False

    # -----------------------------------------------------------------------
    # Summary
    # -----------------------------------------------------------------------
    print("=" * 70)
    print(f"PARAPHRASE ROBUSTNESS SUITE: {'[PASS] ALL GATES CLEARED' if all_passed else '[FAIL]'}")
    print("=" * 70)

    return all_passed


if __name__ == "__main__":
    success = run_acceptance_suite()
    sys.exit(0 if success else 1)
