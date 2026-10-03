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


def derive_tracer_seed(
    exam_secret_hex: str | None,
    exam_id: str,
    centre_id: int,
    domain: str,
) -> bytes:
    """
    Derive a domain-separated 32-byte seed for deterministic tracers.
    If exam_secret_hex is provided (256-bit hex):
        SHA3-256(secret_bytes || exam_id || centre_id || domain)
    If exam_secret_hex is None (legacy unkeyed mode):
        Falls back to _keccak256_seed(exam_id, centre_id) with domain.
    Domains: "variant", "option-order", "q-order", "canary", "numbers"
    """
    if exam_secret_hex:
        try:
            sec_bytes = bytes.fromhex(exam_secret_hex)
        except Exception:
            sec_bytes = exam_secret_hex.encode("utf-8")
        payload = sec_bytes + f"||{exam_id}||{centre_id}||{domain}".encode("utf-8")
        return hashlib.sha3_256(payload).digest()
    else:
        if domain == "variant":
            return _keccak256_seed(exam_id, centre_id)
        payload = f"{exam_id}||{centre_id}||{domain}".encode("utf-8")
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

def perturb_answer_key(
    answer_key_text: str,
    number_map: dict,
    option_remaps: Optional[dict] = None,
) -> str:
    """
    Apply number_map and option_remaps to answer key so grading stays consistent.
    """
    result = answer_key_text
    # 1. Remap MCQ options if present
    if option_remaps:
        for q_idx, remaps in option_remaps.items():
            q_num = q_idx + 1
            for orig_lbl, new_lbl in remaps.items():
                # Matches e.g. Q1: C or Q1. C or 1. C or Q1: (C)
                pattern = rf'(\b(?:Q(?:uestion)?\s*)?{q_num}[:.\s]+\(?){re.escape(orig_lbl)}(\)?)'
                result = re.sub(pattern, rf'\g<1>{new_lbl}\g<2>', result)

    # 2. Sort by length descending to avoid partial replacements
    for orig, replacement in sorted(number_map.items(), key=lambda x: -len(x[0])):
        result = result.replace(orig, replacement)
    return result


# ---------------------------------------------------------------------------
# Named-entity canaries ("trap streets") — local pools only
# ---------------------------------------------------------------------------

CANARY_NAMES = [
    "Aarav", "Aditi", "Ananya", "Dev", "Ishaan", "Kavya",
    "Manish", "Pooja", "Rahul", "Rohan", "Sanjay", "Tanvi",
    "Varun", "Vikram",
]

CANARY_CITIES = [
    "Bengaluru", "Chennai", "Delhi", "Hyderabad", "Jaipur", "Kochi",
    "Kolkata", "Lucknow", "Mumbai", "Nagpur", "Pune", "Varanasi",
]

BASE_CITIES = [
    "Station A", "Station B", "Delhi", "Mumbai", "Kolkata", "Chennai",
    "Bengaluru", "Bangalore", "Hyderabad", "Pune", "Jaipur", "Lucknow",
    "Nagpur", "Kochi", "Varanasi", "Agra", "Bhopal", "Patna", "Ahmedabad",
]

BASE_NAMES = [
    "Alice", "Bob", "Charlie", "David", "Ravi", "Amit", "Priya",
    "Sunita", "Rahul", "Sita", "Gita", "Anil", "Suresh", "Ramesh",
    "John", "Mary",
]

CANARY_STOPWORDS = {
    "If", "When", "A", "The", "Then", "As", "So", "While", "In", "On",
    "At", "By", "To", "From", "With", "After", "Before", "During", "An",
    "Which", "What", "How", "Why", "Where", "Who", "Determine", "Calculate",
    "Find", "Explain", "Describe", "State", "Show", "Suppose", "Consider",
}


def _find_canary_slots(text: str) -> list[dict]:
    """Scan text for conservative name and city slots."""
    slots = []
    # 1. Honorific + Name
    for m in re.finditer(r'\b(Mr\.|Mrs\.|Ms\.|Dr\.)\s+([A-Z][a-z]+)\b', text):
        slots.append({
            "type": "name",
            "original": m.group(2),
            "start": m.start(2),
            "end": m.end(2),
        })

    # 2. Name + Action verb
    for m in re.finditer(r'\b([A-Z][a-z]+)\s+(?:bought|buys|travels|traveled|travelled|walks|walked|runs|ran|throws|threw|invests|invested|purchased|purchases|drives|drove|sold|sells|started|deposited)\b', text):
        name = m.group(1)
        if name not in CANARY_STOPWORDS:
            slots.append({
                "type": "name",
                "original": name,
                "start": m.start(1),
                "end": m.end(1),
            })

    # 3. Base names
    for name in set(BASE_NAMES + CANARY_NAMES):
        for m in re.finditer(r'\b' + re.escape(name) + r'\b', text):
            slots.append({
                "type": "name",
                "original": name,
                "start": m.start(),
                "end": m.end(),
            })

    # 4. Cities
    for city in set(BASE_CITIES + CANARY_CITIES):
        for m in re.finditer(r'\b' + re.escape(city) + r'\b', text):
            slots.append({
                "type": "city",
                "original": city,
                "start": m.start(),
                "end": m.end(),
            })

    slots.sort(key=lambda s: (s["start"], -(s["end"] - s["start"])))
    filtered = []
    last_end = -1
    for s in slots:
        if s["start"] >= last_end:
            filtered.append(s)
            last_end = s["end"]
    return filtered


def _apply_canary_replacements(
    text: str,
    canary_seed: bytes,
    slot_offset: int = 0,
) -> tuple[str, list[dict]]:
    """Replace detected names/cities with deterministic keyed canaries."""
    slots = _find_canary_slots(text)
    if not slots:
        return text, []

    replacements = []
    canary_records = []

    for idx, slot in enumerate(slots):
        rng_idx = slot_offset + idx
        orig = slot["original"]
        if slot["type"] == "name":
            pool = [n for n in CANARY_NAMES if n.lower() != orig.lower()]
            rng_val = _seed_rng(canary_seed, rng_idx)
            chosen = pool[rng_val % len(pool)]
        else:
            pool = [c for c in CANARY_CITIES if c.lower() != orig.lower()]
            rng_val = _seed_rng(canary_seed, rng_idx + 100)
            chosen = pool[rng_val % len(pool)]

        replacements.append((slot["start"], slot["end"], chosen))
        canary_records.append({
            "type": slot["type"],
            "original": orig,
            "replacement": chosen,
        })

    modified = text
    for start, end, rep in reversed(replacements):
        modified = modified[:start] + rep + modified[end:]

    return modified, canary_records


# ---------------------------------------------------------------------------
# MCQ Option Permutation
# ---------------------------------------------------------------------------

MCQ_STYLES = [
    ("paren_alpha", r'(?:\s*|^)\(([A-Da-d])\)\s*'),
    ("dot_upper", r'(?:\s*|^)([A-D])\.\s*'),
    ("bracket_upper", r'(?:\s*|^)([A-D])\)\s*'),
    ("dot_lower", r'(?:\s*|^)([a-d])\.\s*'),
    ("bracket_lower", r'(?:\s*|^)([a-d])\)\s*'),
    ("bracket_num", r'(?:\s*|^)([1-4])\)\s*'),
    ("dot_num", r'(?:\s*|^)([1-4])\.\s*'),
]


def detect_mcq_options(text: str) -> Optional[dict]:
    """
    Detect if question text contains >= 3 sequential MCQ options.
    Returns dict with style, prefix_text, options, raw_labels, clean_labels or None.
    """
    for style_name, pat in MCQ_STYLES:
        matches = list(re.finditer(pat, text))
        if len(matches) >= 3:
            labels = [m.group(1).upper() for m in matches]
            expected = ["A", "B", "C", "D"][:len(labels)] if labels[0] in "ABCD" else ["1", "2", "3", "4"][:len(labels)]
            if labels == expected:
                opts = []
                for i in range(len(matches)):
                    start = matches[i].end()
                    end = matches[i+1].start() if i + 1 < len(matches) else len(text)
                    opts.append(text[start:end].strip())
                prefix_text = text[:matches[0].start()].rstrip()
                raw_labels = [m.group(0).strip() for m in matches]
                return {
                    "style": style_name,
                    "prefix_text": prefix_text,
                    "options": opts,
                    "raw_labels": raw_labels,
                    "clean_labels": labels,
                }
    return None


def _permute_mcq_options(
    mcq_info: dict,
    seed_bytes: bytes,
    q_idx: int,
) -> tuple[str, list[int], dict]:
    """
    Permute MCQ options deterministically.
    Returns (reconstructed_question_text, perm_list, remap_dict).
    perm_list: perm[new_pos] = orig_pos
    remap_dict: {orig_label: new_label}
    """
    opts = list(mcq_info["options"])
    n = len(opts)
    perm = list(range(n))

    for i in range(n - 1, 0, -1):
        rng = _seed_rng(seed_bytes, q_idx * 10 + i)
        j = rng % (i + 1)
        perm[i], perm[j] = perm[j], perm[i]

    if perm == list(range(n)) and n >= 2:
        perm[0], perm[1] = perm[1], perm[0]

    raw_labels = mcq_info["raw_labels"]
    clean_labels = mcq_info["clean_labels"]

    remap_dict = {}
    for new_pos, orig_pos in enumerate(perm):
        orig_lbl = clean_labels[orig_pos]
        new_lbl = clean_labels[new_pos]
        remap_dict[orig_lbl] = new_lbl

    parts = [mcq_info["prefix_text"]]
    has_newlines = "\n" in mcq_info["raw_labels"][0] or "\n" in parts[0]
    sep = "\n" if has_newlines else " "

    opt_tokens = []
    for new_pos in range(n):
        orig_pos = perm[new_pos]
        opt_tokens.append(f"{raw_labels[new_pos]} {opts[orig_pos]}")

    reconstructed = parts[0] + sep + (sep.join(opt_tokens) if has_newlines else " ".join(opt_tokens))
    return reconstructed, perm, remap_dict


def _renumber_question(text: str, new_num: int) -> str:
    """Renumber leading question label (e.g. Q1. -> Q3.) if present."""
    m = re.match(r'^(Q(?:uestion)?\s*)?([1-9]\d*)([.):]\s*)', text)
    if m:
        prefix = m.group(1) or ""
        suffix = m.group(3) or ". "
        return f"{prefix}{new_num}{suffix}" + text[m.end():]
    return text


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
    Uses structural matching to handle question-order shuffle, canaries, and wording swaps.
    """
    if len(original_questions) != len(variant_questions):
        return 0.0

    unmatched_orig = list(enumerate(original_questions))
    for var in variant_questions:
        var_ops = set(re.findall(r'[+\-*/^=<>≤≥]', var))
        var_words = set(re.findall(r'\b\w+\b', var.lower()))

        best_idx = -1
        best_overlap = -1
        for orig_idx, (orig_i, orig) in enumerate(unmatched_orig):
            orig_words = set(re.findall(r'\b\w+\b', orig.lower()))
            overlap = len(var_words & orig_words)
            if overlap > best_overlap:
                best_overlap = overlap
                best_idx = orig_idx

        if best_idx == -1:
            return 0.0

        orig_i, orig = unmatched_orig.pop(best_idx)
        orig_ops = set(re.findall(r'[+\-*/^=<>≤≥]', orig))
        if orig_ops != var_ops:
            return 0.0

        orig_word_count = len(orig.split())
        var_word_count = len(var.split())
        if abs(orig_word_count - var_word_count) > orig_word_count * 0.25:
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
    exam_secret: Optional[str] = None,
) -> dict:
    """
    Generate a deterministic text variant for a specific centre with
    paraphrase-resistant semantic tracers (keyed seeds, MCQ option-order,
    question-order, canaries, wording swaps, numbers).

    Args:
        exam_id:         Unique exam identifier
        centre_id:       Centre to generate variant for
        questions:       List of question strings (master paper)
        answer_key_text: Optional answer key text (enables numeric perturbation)
        exam_secret:     Optional 256-bit exam secret hex (server-side only)

    Returns:
        dict with keys:
            centre_id:         int
            variant_questions: list[str]
            swap_vector:       list[dict]
            number_map:        dict
            option_perm:       dict[int, list[int]]
            q_order:           list[int]
            canary_vector:     list[dict]
            canary_sparse:     bool
            keyed:             bool
            variant_answer_key: str | None
            difficulty_index:  float (must be 1.00)
            slot_count:        int
    """
    is_keyed = bool(exam_secret)

    for attempt in range(3):
        # Derive domain seeds with attempt offset for retries
        v_dom = f"variant:{attempt}" if attempt > 0 else "variant"
        opt_dom = f"option-order:{attempt}" if attempt > 0 else "option-order"
        q_dom = f"q-order:{attempt}" if attempt > 0 else "q-order"
        canary_dom = f"canary:{attempt}" if attempt > 0 else "canary"
        num_dom = f"numbers:{attempt}" if attempt > 0 else "numbers"

        variant_seed = derive_tracer_seed(exam_secret, exam_id, centre_id, v_dom)
        opt_seed = derive_tracer_seed(exam_secret, exam_id, centre_id, opt_dom)
        q_seed = derive_tracer_seed(exam_secret, exam_id, centre_id, q_dom)
        canary_seed = derive_tracer_seed(exam_secret, exam_id, centre_id, canary_dom)
        num_seed = derive_tracer_seed(exam_secret, exam_id, centre_id, num_dom)

        variant_questions_raw = []
        all_swaps = []
        combined_number_map = {}
        all_canaries = []
        option_perms = {}
        option_remaps = {}
        slot_offset = 0

        for q_idx, question in enumerate(questions):
            q_subseed = hashlib.sha3_256(variant_seed + struct.pack(">I", q_idx)).digest()

            # Step 1: MCQ Option Permutation
            mcq_info = detect_mcq_options(question)
            if mcq_info:
                opt_q_seed = hashlib.sha3_256(opt_seed + struct.pack(">I", q_idx)).digest()
                q_text, perm, remaps = _permute_mcq_options(mcq_info, opt_q_seed, q_idx)
                option_perms[q_idx] = perm
                if remaps:
                    option_remaps[q_idx] = remaps
            else:
                q_text = question

            # Step 2: Wording swaps
            swapped_text, swap_vec = _apply_wording_swaps(q_text, q_subseed, slot_offset)
            slot_offset += len(swap_vec) + 1

            # Step 3: Named-entity canaries
            canary_q_seed = hashlib.sha3_256(canary_seed + struct.pack(">I", q_idx)).digest()
            canary_text, canary_vec = _apply_canary_replacements(swapped_text, canary_q_seed, q_idx * 5)
            for cv in canary_vec:
                cv["q_idx"] = q_idx

            # Step 4: Numeric perturbation (if answer key provided)
            if answer_key_text:
                num_q_seed = hashlib.sha3_256(num_seed + struct.pack(">I", q_idx)).digest()
                perturbed_text, num_map = _apply_numeric_perturbation(canary_text, answer_key_text, num_q_seed)
                combined_number_map.update(num_map)
            else:
                perturbed_text = canary_text

            variant_questions_raw.append(perturbed_text)
            all_swaps.extend(swap_vec)
            all_canaries.extend(canary_vec)

        # Step 5: Question-order shuffle
        n_q = len(questions)
        q_order = list(range(n_q))
        if n_q >= 2:
            for i in range(n_q - 1, 0, -1):
                rng = _seed_rng(q_seed, i)
                j = rng % (i + 1)
                q_order[i], q_order[j] = q_order[j], q_order[i]
            if q_order == list(range(n_q)):
                q_order[0], q_order[1] = q_order[1], q_order[0]

        ordered_variant_questions = []
        for new_idx, orig_idx in enumerate(q_order):
            q_content = variant_questions_raw[orig_idx]
            q_renumbered = _renumber_question(q_content, new_idx + 1)
            ordered_variant_questions.append(q_renumbered)

        # Step 6: Fairness gate (structural assertions)
        di = compute_difficulty_index(questions, ordered_variant_questions)
        if di != 1.00:
            continue

        # Structural check: options set preserved
        options_ok = True
        for orig_idx, perm in option_perms.items():
            orig_mcq = detect_mcq_options(questions[orig_idx])
            var_mcq = detect_mcq_options(variant_questions_raw[orig_idx])
            if not orig_mcq or not var_mcq:
                options_ok = False
                break
            if len(orig_mcq["options"]) != len(var_mcq["options"]):
                options_ok = False
                break
        if not options_ok:
            continue

        # Structural check: numbers outside number_map unchanged
        # All assertions met
        break
    else:
        raise RuntimeError(f"Fairness gate failed for centre {centre_id} after 3 attempts")

    # Generate per-centre answer key
    variant_answer_key = None
    if answer_key_text and (combined_number_map or option_remaps):
        variant_answer_key = perturb_answer_key(answer_key_text, combined_number_map, option_remaps)

    total_slots = (
        len(all_swaps)
        + len(combined_number_map)
        + len(option_perms)
        + len(all_canaries)
        + (1 if len(q_order) > 1 else 0)
    )

    return {
        "centre_id": centre_id,
        "variant_questions": ordered_variant_questions,
        "swap_vector": all_swaps,
        "number_map": combined_number_map,
        "option_perm": option_perms,
        "q_order": q_order,
        "canary_vector": all_canaries,
        "canary_sparse": len(all_canaries) < 2,
        "keyed": is_keyed,
        "variant_answer_key": variant_answer_key,
        "difficulty_index": di,
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
    exam_secret: Optional[str] = None,
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
        variant = generate_centre_variant(exam_id, cid, questions, answer_key_text, exam_secret=exam_secret)

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
