# ZeroLock Round 2: Paraphrase-Resistant Semantic Tracers Acceptance

**Target**: Paraphrase-Resistant Semantic Tracers ("GPT-Laundering Defense")  
**Date**: 2026-10-03  
**Status**: [ALL GATES CLEARED]  

---

## Executive Summary

Round 2 equips ZeroLock with defense against "GPT-laundering" (where an adversary runs a leaked exam paper through an LLM to rewrite all sentences and destroy inter-word physical watermarks and exact synonym substitutions).

By introducing **keyed tracer seeds** (`exam_secret` 256-bit server-side) and fingerprinting properties preserved across LLM paraphrase (numbers, MCQ option ordering, question sequences, and named-entity canaries), ZeroLock attributes leaked reworded text to its source centre with high statistical confidence and tiered institutional verdicts.

### Stretch Items Status
- **Marks-split variants**: **SKIPPED** (as permitted by directive to avoid modifying grading logic, rubric contracts, and evaluation scoring schema).

---

## 1. Paraphrase Robustness Suite (`experiments/paraphrase_robustness_test.py`)

### Non-Circularity Verification
The paraphrase simulation uses a strictly held-out rewording table (`HELD_OUT_PAIRS`) programmatically verified to share **zero overlap** with `SWAP_GROUPS` in `core/variant_engine.py`.

```
======================================================================
ZeroLock Round 2 – Paraphrase-Resistant Semantic Tracers Acceptance
======================================================================

[INIT] Verifying non-circularity: engine swap table vs held-out table...
  [+] PASS: Zero overlap between engine SWAP_GROUPS and held-out table.

[GATE 1] Paraphrased Variant Leaks Attribution (3/3 Centres)
  Centre 0014: [PASS] status=LEAD attributed=14 margin=+53.2% confidence=92.8%
  Centre 0028: [PASS] status=LEAD attributed=28 margin=+104.2% confidence=93.1%
  Centre 0042: [PASS] status=LEAD attributed=42 margin=+144.1% confidence=90.6%
  Gate 1 Result: [PASS] 3/3

[GATE 2] Numbers + Options Only Floor Leak Performance
  Centre 0014 Floor: [PASS] status=LEAD attributed=14 margin=+50.2% confidence=85.0%
  Centre 0028 Floor: [PASS] status=LEAD attributed=28 margin=+61.6% confidence=85.0%
  Centre 0042 Floor: [PASS] status=LEAD attributed=42 margin=+150.7% confidence=82.2%
  Gate 2 Result: [PASS] 3/3

[GATE 3] Master (Unvarianted) Text Inconclusive Guard
  Master Text: [PASS] status=INCONCLUSIVE attributed=None
  Gate 3 Result: [PASS]

[GATE 4] Wrong-Exam Cross-Contamination Guard
  Wrong Exam Text: [PASS] status=INCONCLUSIVE attributed=None
  Gate 4 Result: [PASS]

[GATE 5] Key-Secrecy and Legacy Fallback Test
  Wrong secret alters mappings: [PASS]
  Legacy NULL secret keyed=False: [PASS]
  Gate 5 Result: [PASS]

======================================================================
PARAPHRASE ROBUSTNESS SUITE: [PASS] ALL GATES CLEARED
======================================================================
```

---

## 2. Variant Attribution Suite (`experiments/variant_attribution_test.py`)

```
============================================================
ZeroLock v2 – Variant Attribution Acceptance Test
============================================================

--- Part A: Clean variant text attribution ---
  Centre 0014: [PASS]  attributed=14  confidence=92.0%  separation=+521.4%
  Centre 0028: [PASS]  attributed=28  confidence=94.0%  separation=+146.6%
  Centre 0042: [PASS]  attributed=42  confidence=92.0%  separation=+224.7%
  Centre 0007: [PASS]  attributed=7  confidence=89.0%  separation=+144.5%
  Centre 0099: [PASS]  attributed=99  confidence=92.0%  separation=+284.8%

--- Part B: OCR-simulated text attribution (2% typo injection) ---
  Centre 0014: [PASS]  attributed=14  confidence=93.0%  separation=+453.4%
  Centre 0028: [PASS]  attributed=28  confidence=94.0%  separation=+146.6%
  Centre 0042: [PASS]  attributed=42  confidence=92.0%  separation=+224.7%
  Centre 0007: [PASS]  attributed=7  confidence=89.0%  separation=+144.5%
  Centre 0099: [PASS]  attributed=99  confidence=92.0%  separation=+284.8%

--- Part C: Difficulty invariance check ---
  Centre 0014: [PASS]  difficulty_index=1.0
  Centre 0028: [PASS]  difficulty_index=1.0
  Centre 0042: [PASS]  difficulty_index=1.0
  Centre 0007: [PASS]  difficulty_index=1.0
  Centre 0099: [PASS]  difficulty_index=1.0

------------------------------------------------------------
Part A (clean attribution):    5/5
Part B (OCR 2% typo):          5/5
Part C (difficulty invariance): 5/5

============================================================
VARIANT ATTRIBUTION TEST: [PASS]
============================================================
```

---

## 3. Physical Watermark Gate Test (`experiments/gate_test.py`)

```
============================================================
ZeroLeak Gate Test – Automated Digital Pipeline
============================================================

PDF generated: 5,105 bytes
Base image: 1241×1754 px

Test A  – Digital baseline (straight PNG decode)...
Test B  – JPEG compressed (quality=75)...
Test C  – JPEG low quality (quality=55)...
Test D  – Cropped (central 70% questions block, zero anchors)...
Test E  – Brightness shift (simulate phone lighting)...
Test F  – Slight rotation (3°)...
Test G  – Unknown doc (should return UNKNOWN, not VERIFIED)...

============================================================
RESULTS
============================================================
  A: Digital baseline            [PASS]  status=VERIFIED c=42 h=7 p=13 bits=209 conf=1.0
  B: JPEG q75 compress           [PASS]  status=VERIFIED c=42 h=7 p=13 bits=209 conf=1.0
  C: JPEG q55 compress           [PASS]  status=VERIFIED c=42 h=7 p=13 bits=209 conf=1.0
  D: Cropped 70%                 [PASS]  status=VERIFIED c=42 h=7 p=13 bits=187 conf=1.0
  E: Brightness +20              [PASS]  status=VERIFIED c=42 h=7 p=13 bits=209 conf=1.0
  F: Rotation 3deg               [PASS]  status=VERIFIED c=42 h=7 p=13 bits=209 conf=1.0
  G: False-positive guard        [PASS]  status=UNKNOWN c=? h=? p=? bits=0 conf=0.0

Passed: 7/7
Gate decision: [GO]
```

---

## 4. Anchorless Crop Recovery (`experiments/crop_recovery_test.py`)

```
======================================================================
ZeroLock – Anchorless Crop Recovery Acceptance Test Suite
======================================================================

[C1] Gate-render Centre 42: crops 70% / 50% / 40% (questions only, zero anchors)...
  [+] Crop 70%: VERIFIED Centre 42 · Hall 7 · Print #13 · mode=anchorless-crop · conf=1.0
  [+] Crop 50%: VERIFIED Centre 42 · Hall 7 · Print #13 · mode=anchorless-crop · conf=1.0
  [+] Crop 40%: VERIFIED Centre 42 · Hall 7 · Print #13 · mode=anchorless-crop · conf=1.0

[C2] Real Case: Physics Paper Screenshot Crop (Header + Q1-Q4, no crosshairs)...
  [+] Real Physics Crop: VERIFIED Centre 14 · Hall 3 · Print #1 · mode=anchorless-crop

[C3] Rotated Crops: 10° and 15° Optical Tilts...
  [+] Rotation 10°: VERIFIED Centre 42 · Hall 7 · mode=anchorless-crop · conf=1.0
  [+] Rotation 15°: VERIFIED Centre 42 · Hall 7 · mode=anchorless-crop · conf=1.0

[C4] Multi-Centre Isolation: Crops from Centre 14 vs Centre 28...
  [+] Centre 14 crop attributed to: Centre 14 (zero cross-talk)
  [+] Centre 28 crop attributed to: Centre 28 (zero cross-talk)

[C5] 1-Question Crop (<40 gaps) Defensive Guard...
  [+] 1-Question crop returned honest UNKNOWN: 'Crop too small – at least ~40 word gaps (about two questions) required. (Found 21)'

[C6] Unwatermarked Document Crop Guard...
  [+] Unwatermarked crop returned honest UNKNOWN: 'Candidate match consistency 62.5% < 85% – attribution unresolved' (no centre attributed)

[C7] Stage-0 Hijack Fallthrough (misrouted crop self-heals)...
  [+] Hijacked crop self-healed: LEAK TRACED (Anchorless Crop) · Centre 89 · Hall 1 · Print #1 · Consistency 100.0% (+6.2% margin)

[C8] Fallthrough Size Guard (full-page not second-guessed)...
  [+] Full-page hijack stayed in fiducial path: UNKNOWN / fiducial

======================================================================
ALL 8 CROP RECOVERY ACCEPTANCE SUITES PASSED [GO]
======================================================================
```

---

## 5. Batch Generation Test (`experiments/batch_test.py`)

```
============================================================
ZeroLock v2 – Batch Generation Acceptance Test
============================================================

  Centre 0014: [PASS]  VERIFIED  decoded_centre=14 bits=293 conf=1.0
  Centre 0028: [PASS]  VERIFIED  decoded_centre=28 bits=292 conf=1.0
  Centre 0042: [PASS]  VERIFIED  decoded_centre=42 bits=293 conf=1.0
  Centre 0007: [PASS]  VERIFIED  decoded_centre=7 bits=292 conf=1.0
  Centre 0099: [PASS]  VERIFIED  decoded_centre=99 bits=293 conf=1.0

------------------------------------------------------------
ZIP contains 5 files: ['centre_0014.pdf', 'centre_0028.pdf', 'centre_0042.pdf', 'centre_0007.pdf', 'centre_0099.pdf']
Self-check results: 5/5 VERIFIED
ZIP completeness: PASS (5/5)

============================================================
BATCH TEST: [PASS]
============================================================
```

---

## 6. Upload Fidelity Suite (`experiments/upload_fidelity_test.py`)

```
============================================================
ZeroLock v2 – Upload Fidelity Acceptance Suite
============================================================

[TEST 1] Parsing real fixture: TY_DSP_26-27_Tutorial_6.pdf ...
  Parsed 4 questions, 137 words, engine: compact
  Title: Tutorial 6: Design a digital IIR low-pass filter for a specified cutoff
  [+] PASS: Question count == 4, Engine == 'compact'

[TEST 2] Rendering Centre 14 with parsed questions (Variants OFF) ...
  Checking extracted text phrases ...
  [+] PASS: Key DSP phrases found in rendered PDF text:
    - 'impulse-invariant'
    - 'bilinear transformation'
    - 'cascade, and parallel'
    - '0014' (Centre identifier)

[TEST 3] Forensic watermark decoding from rendered PDF page ...
  Decode status: VERIFIED, Centre: 14, Confidence: 0.645
  [+] PASS: decode_photo -> VERIFIED Centre 14

[TEST 4] Testing Variants ON (semantic / numerical variants) ...
  Diff in Question 4:
    Centre 14: 4 Find the direct Form I, direct Form II, cascade, and paral...
    Centre 28: 4 Evaluate the direct Form I, direct Form II, cascade, and p...
  Total variant differences: 1 question(s)
  Slots C14: 5, Slots C28: 5
  [+] PASS: Variants ON correctly generated per-centre variants

[TEST 5] Testing short document upload guard (CapacityError) ...
  Caught expected CapacityError: Paper too short (6 words). Minimum 30 words required for forensic watermark gap modulation.
  [+] PASS: CapacityError correctly raised without crash

============================================================
ALL 5 UPLOAD FIDELITY ACCEPTANCE TESTS PASSED [GO]
============================================================
```

---

## 7. Hardhat Smart Contracts Suite (`contracts/test/lockout_test.js`)

```
  PaperVault Anti-Grinding Lockout
    √ should track failed attempts and lock out after 5 invalid guesses
    √ should unlock successfully with correct OTP on first attempt and reset failed counter
    √ should support 12-character alphanumeric high-entropy token secrets

  3 passing (353ms)
```

---

## 8. Commit Sequence

1. `aba5187 feat(db): exam_secret column with safe migration`
2. `088c8d8 feat(core): keyed tracer seeds + option/q-order/canary signals`
3. `77f1cce feat(core): multi-signal comparator with Kendall scoring`
4. `b145c0a feat(backend+frontend): tiered LEAD verdicts in investigate + tracer UI`
5. `3cc8ef1 test(round2): paraphrase robustness suite`
6. `docs(evidence): round2 paraphrase acceptance outputs`
