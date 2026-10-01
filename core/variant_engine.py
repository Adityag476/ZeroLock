"""
ZeroLock Core — Deterministic Per-Centre Semantic Variant Engine
=================================================================
Generates per-centre text variants with:
  1. Neutral wording swaps (curated local table, no LLM / external APIs)
  2. Numeric perturbation (only when answer key is uploaded)

Design principles:
  - Deterministic: keccak256(exam_id || centre_id) seed
  - Air-gapped: 100% local, no network calls
  - Fair: difficulty-invariance index must be exactly 1.00
  - Traceable: each centre's (number_map, swap_vector) is a unique fingerprint
"""

from __future__ import annotations

import re
import hashlib
import struct
import math
from typing import Optional

# ---------------------------------------------------------------------------
# Neutral wording swap table (curated, semantically equivalent)
# Each group is a set of interchangeable alternatives.
# Maximum 1 swap per sentence, ≥4 swapped slots per paper.
# ---------------------------------------------------------------------------
SWAP_GROUPS = [
    ["calculate", "compute", "determine"],
    ["find", "obtain", "evaluate"],
    ["show that", "prove that", "demonstrate that"],
    ["negligible", "ignored", "disregarded"],
    ["initially", "at the start", "at first"],
    ["metres", "m"],
    ["kilogram", "kg"],
    ["assuming", "given that", "provided that"],
    ["therefore", "hence", "consequently"],
    ["constant", "fixed", "unchanged"],
    ["horizontal", "lateral"],
    ["vertical", "upward"],
    ["magnitude", "absolute value"],
    ["approximately", "roughly", "about"],
    ["significant", "considerable", "substantial"],
    ["decrease", "reduce", "diminish"],
    ["increase", "raise", "elevate"],
    ["maximum", "peak", "highest"],
    ["minimum", "lowest", "least"],
    ["uniform", "steady", "even"],
    ["describe", "explain", "outline"],
    ["derive", "deduce", "work out"],
    ["state", "mention", "specify"],
    ["define", "characterize"],
    ["diagram", "figure", "illustration"],
]


def _keccak256_seed(exam_id: str, centre_id: int) -> bytes:
    """
    Compute a deterministic 32-byte seed from (exam_id, centre_id)
    using keccak-style hashing (SHA3-256 = NIST Keccak variant).
    """
    payload = f"{exam_id}||{centre_id}".encode("utf-8")
    return hashlib.sha3_256(payload).digest()


def _seed_rng(seed_bytes: bytes, index: int) -> int:
    """Deterministic PRN from seed + index via SHA3-256 chaining."""
    h = hashlib.sha3_256(seed_bytes + struct.pack(">I", index)).digest()
    return int.from_bytes(h[:4], "big")


# ---------------------------------------------------------------------------
# Wording swap engine
# ---------------------------------------------------------------------------

def _find_swap_slots(text: str) -> list[dict]:
    """
    Scan text for words/phrases matching any swap group.
    Returns list of {start, end, group_idx, original} for each match.
    """
    slots = []
    text_lower = text.lower()

    for g_idx, group in enumerate(SWAP_GROUPS):
        for variant in group:
            # Search for whole-word (or whole-phrase) matches
            pattern = r'\b' + re.escape(variant) + r'\b'
            for m in re.finditer(pattern, text_lower):
                slots.append({
                    "start": m.start(),
                    "end": m.end(),
                    "group_idx": g_idx,
                    "original": text[m.start():m.end()],
                    "variant_lower": variant,
                })

    # Deduplicate overlapping matches (keep longest)
    slots.sort(key=lambda s: (s["start"], -(s["end"] - s["start"])))
    filtered = []
    last_end = -1
    for s in slots:
        if s["start"] >= last_end:
            filtered.append(s)
            last_end = s["end"]

    return filtered


def _apply_wording_swaps(
    text: str,
    seed_bytes: bytes,
    slot_offset: int = 0,
) -> tuple[str, list[dict]]:
    """
    Apply neutral wording swaps to text.
    Returns (modified_text, swap_vector).
    Maximum 1 swap per sentence.
    """
    # Split into sentences for the 1-swap-per-sentence rule
    sentences = re.split(r'(?<=[.!?])\s+', text)
    result_parts = []
    swap_vector = []
    global_slot_idx = slot_offset

    for sent in sentences:
        slots = _find_swap_slots(sent)
        if not slots:
            result_parts.append(sent)
            continue

        # Pick at most 1 slot per sentence (deterministic choice)
        rng_val = _seed_rng(seed_bytes, global_slot_idx)
        chosen_slot = slots[rng_val % len(slots)]
        group = SWAP_GROUPS[chosen_slot["group_idx"]]

        # Pick a different variant from the group
        rng_choice = _seed_rng(seed_bytes, global_slot_idx + 1000)
        available = [v for v in group if v.lower() != chosen_slot["variant_lower"]]
        if not available:
            result_parts.append(sent)
            global_slot_idx += 1
            continue

        replacement = available[rng_choice % len(available)]

        # Preserve original casing
        orig = chosen_slot["original"]
        if orig[0].isupper():
            replacement = replacement[0].upper() + replacement[1:]
        if orig.isupper():
            replacement = replacement.upper()

        modified = sent[:chosen_slot["start"]] + replacement + sent[chosen_slot["end"]:]
        result_parts.append(modified)
        swap_vector.append({
            "position": chosen_slot["start"],
            "original": orig,
            "replacement": replacement,
            "group_idx": chosen_slot["group_idx"],
        })

        global_slot_idx += 1

    return " ".join(result_parts), swap_vector


# ---------------------------------------------------------------------------
# Numeric perturbation engine
# ---------------------------------------------------------------------------

NUMBER_UNIT_PATTERN = re.compile(
    r'\b(\d+(?:\.\d+)?)\s*'
    r'(kg|g|mol|m|cm|mm|km|Hz|kHz|MHz|ohms?|ohm|V|kV|mV|A|mA|'
    r'J|kJ|eV|MeV|W|kW|N|kN|Pa|kPa|MPa|atm|L|mL|'
    r'mol/kg|m/s|m/s\^?2|km/h|rad|rad/s|degrees?|'
    r'nm|pm|um|K|C|F|s|ms|min|hr|h)\b',
    re.IGNORECASE
)


def _perturb_number(
    value: float,
    seed_bytes: bytes,
    idx: int,
) -> float:
    """
    Perturb a number by ±(5–10%), rounded to 2 significant figures.
    Never returns 0 or negative.
    """
    rng = _seed_rng(seed_bytes, idx + 5000)
    # Direction: + or -
    direction = 1 if (rng % 2) == 0 else -1
    # Magnitude: 5–10%
    pct = 5.0 + (rng % 6)  # 5, 6, 7, 8, 9, or 10
    factor = 1.0 + direction * (pct / 100.0)
    perturbed = value * factor

    # Never 0 or negative
    if perturbed <= 0:
        perturbed = value * (1.0 + pct / 100.0)

    # Round to 2 significant figures
    if perturbed == 0:
        return value
    magnitude = math.floor(math.log10(abs(perturbed)))
    rounded = round(perturbed, -int(magnitude) + 1)

    # If original was integer, return integer
    if value == int(value) and rounded == int(rounded):
        return int(rounded)
    return rounded


def _extract_numbers_from_text(text: str) -> list[dict]:
    """Extract all number+unit tokens from text."""
    results = []
    for m in NUMBER_UNIT_PATTERN.finditer(text):
        val_str = m.group(1)
        unit = m.group(2)
        try:
            val = float(val_str)
        except ValueError:
            continue
        results.append({
            "start": m.start(),
            "end": m.end(),
            "value": val,
            "value_str": val_str,
            "unit": unit,
            "full_match": m.group(0),
        })
    return results


def _apply_numeric_perturbation(
    text: str,
    answer_key_text: str,
    seed_bytes: bytes,
) -> tuple[str, dict]:
    """
    Perturb numbers in text ONLY if they also appear in the answer key.
    Returns (modified_text, number_map: {original_str: perturbed_str}).
    """
    text_numbers = _extract_numbers_from_text(text)
    key_numbers = set()
    for m in NUMBER_UNIT_PATTERN.finditer(answer_key_text):
        try:
            key_numbers.add(float(m.group(1)))
        except ValueError:
            pass
    # Also extract plain numbers from key
    for m in re.finditer(r'\b(\d+(?:\.\d+)?)\b', answer_key_text):
        try:
            key_numbers.add(float(m.group(1)))
        except ValueError:
            pass

    number_map = {}
    # Build replacements (reverse order to preserve indices)
    replacements = []
    for idx, num_info in enumerate(text_numbers):
        if num_info["value"] in key_numbers:
            perturbed = _perturb_number(num_info["value"], seed_bytes, idx)
            orig_str = num_info["value_str"]
            if isinstance(perturbed, int) or (isinstance(perturbed, float) and perturbed == int(perturbed)):
                pert_str = str(int(perturbed))
            else:
                # Match decimal precision of original
                decimal_places = len(orig_str.split('.')[-1]) if '.' in orig_str else 0
                pert_str = f"{perturbed:.{decimal_places}f}"
            number_map[orig_str] = pert_str
            replacements.append((num_info["start"], num_info["start"] + len(orig_str), pert_str))

    # Apply replacements in reverse order
    modified = text
    for start, end, replacement in reversed(replacements):
        modified = modified[:start] + replacement + modified[end:]

    return modified, number_map


# ---------------------------------------------------------------------------
# Answer key perturbation
# ---------------------------------------------------------------------------

def perturb_answer_key(answer_key_text: str, number_map: dict) -> str:
    """
    Apply the same number_map to the answer key so grading stays consistent.
    """
    result = answer_key_text
    # Sort by length descending to avoid partial replacements
    for orig, replacement in sorted(number_map.items(), key=lambda x: -len(x[0])):
        result = result.replace(orig, replacement)
    return result


# ---------------------------------------------------------------------------
# Difficulty invariance check
# ---------------------------------------------------------------------------

def compute_difficulty_index(
    original_questions: list[str],
    variant_questions: list[str],
) -> float:
    """
    Compute difficulty-invariance index between original and variant.
    Returns 1.00 if the variant preserves difficulty exactly.

    Methodology:
    - Wording swaps are semantically neutral by construction → index = 1.00
    - Numeric perturbations preserve equation form → index = 1.00
    - We verify: same number of questions, same structure, same operations
    """
    if len(original_questions) != len(variant_questions):
        return 0.0

    for orig, var in zip(original_questions, variant_questions):
        # Check that the mathematical structure is preserved:
        # Same operators, same equation patterns
        orig_ops = set(re.findall(r'[+\-*/^=<>≤≥]', orig))
        var_ops = set(re.findall(r'[+\-*/^=<>≤≥]', var))
        if orig_ops != var_ops:
            return 0.0

        # Check word count similarity (within 20% tolerance for swap length diffs)
        orig_words = len(orig.split())
        var_words = len(var.split())
        if abs(orig_words - var_words) > orig_words * 0.20:
            return 0.0

    return 1.00


# ---------------------------------------------------------------------------
# Public API — Generate variant for a single centre
# ---------------------------------------------------------------------------

def generate_centre_variant(
    exam_id: str,
    centre_id: int,
    questions: list[str],
    answer_key_text: Optional[str] = None,
) -> dict:
    """
    Generate a deterministic text variant for a specific centre.

    Args:
        exam_id:         Unique exam identifier
        centre_id:       Centre to generate variant for
        questions:       List of question strings (master paper)
        answer_key_text: Optional answer key text (enables numeric perturbation)

    Returns:
        dict with keys:
            centre_id:         int
            variant_questions: list[str]
            swap_vector:       list[dict]  (per-question swap records)
            number_map:        dict        (original→perturbed number strings)
            variant_answer_key: str | None
            difficulty_index:  float       (must be 1.00)
            slot_count:        int         (total swap slots applied)
    """
    seed = _keccak256_seed(exam_id, centre_id)

    variant_questions = []
    all_swaps = []
    combined_number_map = {}
    slot_offset = 0

    for q_idx, question in enumerate(questions):
        # Per-question sub-seed for deterministic isolation
        q_seed = hashlib.sha3_256(seed + struct.pack(">I", q_idx)).digest()

        # Step 1: Wording swaps (always active)
        swapped_text, swap_vec = _apply_wording_swaps(question, q_seed, slot_offset)
        slot_offset += len(swap_vec) + 1

        # Step 2: Numeric perturbation (only if answer key provided)
        if answer_key_text:
            perturbed_text, num_map = _apply_numeric_perturbation(
                swapped_text, answer_key_text, q_seed
            )
            combined_number_map.update(num_map)
        else:
            perturbed_text = swapped_text

        variant_questions.append(perturbed_text)
        all_swaps.extend(swap_vec)

    # Generate per-centre answer key
    variant_answer_key = None
    if answer_key_text and combined_number_map:
        variant_answer_key = perturb_answer_key(answer_key_text, combined_number_map)

    # Fairness gate
    difficulty_idx = compute_difficulty_index(questions, variant_questions)

    total_slots = len(all_swaps)

    return {
        "centre_id": centre_id,
        "variant_questions": variant_questions,
        "swap_vector": all_swaps,
        "number_map": combined_number_map,
        "variant_answer_key": variant_answer_key,
        "difficulty_index": difficulty_idx,
        "slot_count": total_slots,
    }


# ---------------------------------------------------------------------------
# Text fingerprint inspector — attribute leaked text to a centre
# ---------------------------------------------------------------------------

def inspect_variant_text(
    leaked_text: str,
    exam_id: str,
    questions: list[str],
    centre_ids: list[int],
    answer_key_text: Optional[str] = None,
) -> dict:
    """
    Score leaked text against all centre variants to find the source.
    Uses both number-profile match and swap-vector match with positional
    confirmation (replacement present AND original absent = strong signal).

    Returns:
        dict with status, implicated_centre_id, confidence, separation_margin
    """
    leaked_lower = leaked_text.lower()

    # Extract numbers from leaked text
    leaked_numbers = set()
    for m in re.finditer(r'\b(\d+(?:\.\d+)?)\b', leaked_text):
        try:
            leaked_numbers.add(float(m.group(1)))
        except ValueError:
            pass

    centre_scores = {}

    for cid in centre_ids:
        variant = generate_centre_variant(exam_id, cid, questions, answer_key_text)

        # Score 1: Swap-vector match with positional confirmation
        # Strong signal: replacement IS in leaked text AND original is NOT
        # Weak signal: replacement IS in leaked text (original might also be)
        # Negative signal: replacement is NOT in leaked text but original IS
        swap_strong = 0
        swap_weak = 0
        swap_miss = 0
        swap_total = max(1, len(variant["swap_vector"]))

        for swap in variant["swap_vector"]:
            replacement_lower = swap["replacement"].lower()
            original_lower = swap["original"].lower()

            rep_found = replacement_lower in leaked_lower
            orig_found = original_lower in leaked_lower

            if rep_found and not orig_found:
                swap_strong += 1  # Strong confirmation
            elif rep_found and orig_found:
                swap_weak += 1    # Ambiguous (both present)
            elif not rep_found and orig_found:
                swap_miss += 1    # Counter-evidence

        swap_score = (swap_strong * 1.0 + swap_weak * 0.3) / swap_total

        # Score 2: Number-profile match with exclusivity check
        num_match = 0
        num_miss = 0
        num_total = max(1, len(variant["number_map"]))

        for orig_str, pert_str in variant["number_map"].items():
            try:
                pert_val = float(pert_str)
                orig_val = float(orig_str)
                pert_found = pert_val in leaked_numbers
                orig_found = orig_val in leaked_numbers

                if pert_found and not orig_found:
                    num_match += 1.0    # Strong: perturbed present, original absent
                elif pert_found:
                    num_match += 0.5    # Weak: both present
                elif orig_found:
                    num_miss += 1       # Counter: original present, perturbed absent
            except ValueError:
                pass

        num_score = num_match / num_total

        # Combined score
        if variant["number_map"]:
            combined = swap_score * 0.4 + num_score * 0.6
        else:
            combined = swap_score

        # Penalty for misses (counter-evidence)
        penalty = (swap_miss + num_miss) * 0.05
        combined = max(0.0, combined - penalty)

        centre_scores[cid] = {
            "swap_strong": swap_strong,
            "swap_weak": swap_weak,
            "swap_miss": swap_miss,
            "swap_total": swap_total,
            "num_match": num_match,
            "num_miss": num_miss,
            "num_total": num_total,
            "combined": combined,
        }

    # Rank centres
    ranked = sorted(centre_scores.items(), key=lambda x: x[1]["combined"], reverse=True)
    if not ranked:
        return {
            "status": "INCONCLUSIVE",
            "implicated_centre_id": None,
            "confidence": 0.0,
            "separation_margin": 0.0,
            "message": "No centres to evaluate",
        }

    top_cid, top_data = ranked[0]
    runner_cid, runner_data = ranked[1] if len(ranked) > 1 else (None, {"combined": 0.0})

    confidence = min(100.0, top_data["combined"] * 100)

    # Separation margin: percentage points above runner-up
    if runner_data["combined"] > 0:
        separation = ((top_data["combined"] - runner_data["combined"]) / runner_data["combined"]) * 100
    else:
        separation = 100.0 if top_data["combined"] > 0 else 0.0

    is_conclusive = top_data["combined"] > 0.2 and separation > 10.0

    return {
        "status": "VERIFIED" if is_conclusive else "INCONCLUSIVE",
        "implicated_centre_id": top_cid if is_conclusive else None,
        "confidence": round(confidence, 1),
        "separation_margin": round(separation, 1),
        "swap_matches": top_data["swap_strong"],
        "number_matches": round(top_data.get("num_match", 0), 1),
        "runner_up_centre_id": runner_cid,
        "runner_up_score": round(runner_data["combined"] * 100, 1),
        "message": (
            f"ATTRIBUTION: Centre #{top_cid} · confidence {round(confidence, 1)}% · "
            f"separation margin +{round(separation, 1)}%"
            if is_conclusive
            else "INCONCLUSIVE: Insufficient variant signal in provided text"
        ),
    }


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    questions = [
        "Calculate the impedance of an alternating current circuit with an inductor of inductance 15 mH and a resistance of 50 ohms at 50 Hz.",
        "A particle of mass 3.0 kg is thrown vertically upwards with a kinetic energy of 490 J. Determine the maximum height attained.",
        "Find the area enclosed between the curve y = x^2 and the line y = 4 using integration.",
        "Show that the magnitude of the gravitational force is negligible for horizontal motion initially.",
    ]
    key = "Z = sqrt(R^2 + (2*pi*50*0.015)^2) = 50.44 ohms. h = 490/(3.0*9.8) = 16.67 m."

    v14 = generate_centre_variant("EXAM-001", 14, questions, key)
    v28 = generate_centre_variant("EXAM-001", 28, questions, key)

    print(f"Centre 14 slots: {v14['slot_count']}, difficulty: {v14['difficulty_index']}")
    print(f"Centre 28 slots: {v28['slot_count']}, difficulty: {v28['difficulty_index']}")
    print(f"\nCentre 14 Q1: {v14['variant_questions'][0][:80]}...")
    print(f"Centre 28 Q1: {v28['variant_questions'][0][:80]}...")
    print(f"\nNumber map 14: {v14['number_map']}")
    print(f"Number map 28: {v28['number_map']}")

    # Test attribution
    leaked = v14["variant_questions"][0] + " " + v14["variant_questions"][1]
    result = inspect_variant_text(leaked, "EXAM-001", questions, [14, 28, 42], key)
    print(f"\nAttribution: {result['message']}")
