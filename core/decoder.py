"""
ZeroLeak Core — Forensic Decoder Pipeline
==========================================
OpenCV-based pipeline to recover a watermark payload from a phone photo
of a ZeroLeak-watermarked printed exam page.

Pipeline:
  1. Grayscale + adaptive threshold
  2. Detect 4 corner crosshair anchors via contour matching
  3. Homography → warpPerspective to canonical A4 plane (595×842 pt @ 150 DPI)
  4. Horizontal projection → text-line segmentation
  5. Per-line: connected components → word bounding boxes → inter-word gap widths
  6. Gap threshold → bitstream
  7. Sliding magic-bit correlator + Reed-Solomon decode → payload

Returns one of three outcomes (ChatGPT's design):
    VERIFIED   — valid decode + DB match
    CORRUPTED  — partial signal, RS fails
    UNKNOWN    — no ZeroLeak watermark detected
"""

from __future__ import annotations
import os
import sys
import numpy as np
from typing import Optional

try:
    import cv2
except ImportError:
    sys.exit("OpenCV not found. Run: pip install opencv-python")

from core.payload import sliding_decode

# Gap sizes in pt (must match renderer.py)
WIDE_GAP   = 15.0   # pt — bit=1
NARROW_GAP =  9.0   # pt — bit=0
BASE_GAP   = 12.0   # pt — neutral baseline

# ---------------------------------------------------------------------------
# Constants (calibrated to 150 DPI scan of an A4 page: 595×842 pt)
# ---------------------------------------------------------------------------
PT_TO_PX     = 150.0 / 72.0                                # ~2.0833 px/pt
TARGET_W     = int(round(595 * PT_TO_PX))                  # 1240 pixels
TARGET_H     = int(round(842 * PT_TO_PX))                  # 1754 pixels

# Anchor canonical coordinates (22 pt inset from each edge)
ANCHOR_OFFSET_PT = 22.0
AX0 = ANCHOR_OFFSET_PT * PT_TO_PX
AY0 = ANCHOR_OFFSET_PT * PT_TO_PX
AX1 = TARGET_W - AX0
AY1 = TARGET_H - AY0

# Gap classification threshold (pixels at 150 DPI)
# WIDE=15pt→31.25px, NARROW=9pt→18.75px, mid-point ≈ 25.0 px
THRESHOLD_PX = (WIDE_GAP + NARROW_GAP) / 2 * PT_TO_PX

# Intra-word kerning is ~6-10 px; inter-word gaps are ≥ 18.75 px
MIN_GAP_PX   = 14   # pixels (ignore intra-word letter gaps)

# Corner search bounds
ANCHOR_REGION_FRAC = 0.18
ANCHOR_MIN_AREA    = 35
ANCHOR_MAX_AREA    = 1000
ANCHOR_ASPECT_LO   = 0.7
ANCHOR_ASPECT_HI   = 1.4


# ---------------------------------------------------------------------------
# Step 1 — Preprocessing
# ---------------------------------------------------------------------------

def preprocess(image: np.ndarray) -> np.ndarray:
    """Convert to grayscale and adaptive threshold."""
    if len(image.shape) == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray = image.copy()

    binary = cv2.adaptiveThreshold(
        gray, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        blockSize=21,
        C=8,
    )
    return binary


# ---------------------------------------------------------------------------
# Step 2 — Anchor detection
# ---------------------------------------------------------------------------

def _find_corner_blobs(binary: np.ndarray) -> list[tuple[float, float]]:
    """
    Find the 4 corner crosshair anchors by searching near the corners
    and selecting the candidate closest to the true image corner.
    """
    h, w = binary.shape
    corner_defs = [
        (0, 0, int(w * ANCHOR_REGION_FRAC), int(h * ANCHOR_REGION_FRAC), 0, 0),                       # TL
        (int(w * (1 - ANCHOR_REGION_FRAC)), 0, w, int(h * ANCHOR_REGION_FRAC), w, 0),                # TR
        (0, int(h * (1 - ANCHOR_REGION_FRAC)), int(w * ANCHOR_REGION_FRAC), h, 0, h),                # BL
        (int(w * (1 - ANCHOR_REGION_FRAC)), int(h * (1 - ANCHOR_REGION_FRAC)), w, h, w, h),          # BR
    ]

    centers = []
    for (x0, y0, x1, y1, cx_corner, cy_corner) in corner_defs:
        region = binary[y0:y1, x0:x1]
        cnts, _ = cv2.findContours(region, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        candidates = []
        for cnt in cnts:
            area = cv2.contourArea(cnt)
            if not (ANCHOR_MIN_AREA <= area <= ANCHOR_MAX_AREA):
                continue
            bx, by, bw, bh = cv2.boundingRect(cnt)
            aspect = bw / (bh + 1e-6)
            if not (ANCHOR_ASPECT_LO <= aspect <= ANCHOR_ASPECT_HI):
                continue
            cx = x0 + bx + bw / 2.0
            cy = y0 + by + bh / 2.0
            dist = float(np.hypot(cx - cx_corner, cy - cy_corner))
            score = (1.0 - abs(1.0 - aspect)) / (dist + 1.0)
            candidates.append((score, (cx, cy)))

        if candidates:
            candidates.sort(key=lambda item: item[0], reverse=True)
            centers.append(candidates[0][1])

    return centers


def detect_anchors(binary: np.ndarray) -> Optional[np.ndarray]:
    """
    Detect the 4 corner crosshair anchors.
    Returns 4×2 float32 array ordered [TL, TR, BL, BR], or None.
    """
    centers = _find_corner_blobs(binary)
    if len(centers) < 4:
        return None

    h, w = binary.shape
    # Cluster into top and bottom halves
    centers.sort(key=lambda p: p[1])
    top = sorted(centers[:2], key=lambda p: p[0])
    bot = sorted(centers[2:], key=lambda p: p[0])

    if len(top) < 2 or len(bot) < 2:
        return None

    pts = np.float32([top[0], top[1], bot[0], bot[1]])
    return pts   # TL, TR, BL, BR


# ---------------------------------------------------------------------------
# Step 3 — Homography + warp
# ---------------------------------------------------------------------------

def rectify(image: np.ndarray, anchors: np.ndarray) -> np.ndarray:
    """
    Apply perspective transform to map anchor corners to their exact canonical A4 locations.
    """
    src = np.float32([
        [anchors[0][0], anchors[0][1]],   # TL
        [anchors[1][0], anchors[1][1]],   # TR
        [anchors[2][0], anchors[2][1]],   # BL
        [anchors[3][0], anchors[3][1]],   # BR
    ])
    dst = np.float32([
        [AX0, AY0],   # TL
        [AX1, AY0],   # TR
        [AX0, AY1],   # BL
        [AX1, AY1],   # BR
    ])
    H, _ = cv2.findHomography(src, dst, cv2.RANSAC, 5.0)
    warped = cv2.warpPerspective(image, H, (TARGET_W, TARGET_H))
    return warped


# ---------------------------------------------------------------------------
# Step 4 — Line segmentation
# ---------------------------------------------------------------------------

def segment_lines(gray_canonical: np.ndarray) -> list[tuple[int, int]]:
    """
    Find text-line vertical extents via horizontal projection profile.
    Returns list of (y_start, y_end) pairs in the question body region.
    """
    _, binary = cv2.threshold(gray_canonical, 200, 255, cv2.THRESH_BINARY_INV)
    proj = np.sum(binary, axis=1) // 255

    # Skip header region (exam title, metadata, dividing rule) and bottom footer
    skip_top    = int(round(65.0 * PT_TO_PX))    # ~135 px
    skip_bottom = int(round(800.0 * PT_TO_PX))   # ~1666 px

    in_line = False
    start = 0
    lines = []
    threshold = 20   # at least 20 ink pixels across the row

    for y in range(skip_top, skip_bottom):
        val = proj[y]
        if val >= threshold and not in_line:
            in_line = True
            start = y
        elif val < threshold and in_line:
            in_line = False
            height = y - start
            if 8 <= height <= 40:
                lines.append((start, y))

    return lines


# ---------------------------------------------------------------------------
# Step 5 — Gap extraction
# ---------------------------------------------------------------------------

def extract_gaps_from_line(
    gray: np.ndarray,
    y0: int,
    y1: int,
) -> list[float]:
    """
    Extract inter-word gap widths (in pixels) from a single text line.
    """
    row = gray[y0:y1, :]
    _, binary = cv2.threshold(row, 200, 255, cv2.THRESH_BINARY_INV)
    proj = np.sum(binary, axis=0) // 255

    line_h = max(1, y1 - y0)
    min_ink = max(1, line_h // 4)

    in_word = False
    word_end = 0
    gaps = []

    for x, val in enumerate(proj):
        if val >= min_ink and not in_word:
            if word_end > 0:
                gap_w = x - word_end
                if gap_w >= MIN_GAP_PX:
                    gaps.append(float(gap_w))
            in_word = True
        elif val < min_ink and in_word:
            in_word = False
            word_end = x

    return gaps



# ---------------------------------------------------------------------------
# Step 6 — Gap → bits
# ---------------------------------------------------------------------------

def gaps_to_bits(gaps: list[float]) -> list[int]:
    """
    Classify each gap as 0 (narrow) or 1 (wide).
    Uses the midpoint between the lower quartile (narrow) and upper quartile (wide)
    to handle print scale, photo zoom, and perspective normalization changes.
    """
    if not gaps:
        return []
    p25 = float(np.percentile(gaps, 25))
    p75 = float(np.percentile(gaps, 75))
    if p75 - p25 < 3.0:
        th = THRESHOLD_PX
    else:
        th = (p25 + p75) / 2.0

    return [1 if g >= th else 0 for g in gaps]


# ---------------------------------------------------------------------------
# Full pipeline
# ---------------------------------------------------------------------------

def decode_photo(
    image_path: str,
    debug_dir: Optional[str] = None,
) -> dict:
    """
    Full forensic decoding pipeline.

    Args:
        image_path: Path to a phone photo (JPEG/PNG) of a watermarked paper.
        debug_dir:  If given, save intermediate images here for inspection.

    Returns:
        dict with keys:
            status      — "VERIFIED" | "CORRUPTED" | "UNKNOWN"
            centre_id   — int (if VERIFIED)
            hall_id     — int (if VERIFIED)
            print_num   — int (if VERIFIED)
            timestamp   — int (if VERIFIED)
            confidence  — float 0..1
            message     — human-readable explanation
            bit_count   — total bits extracted
    """
    if debug_dir:
        os.makedirs(debug_dir, exist_ok=True)

    # Load
    image = cv2.imread(image_path)
    if image is None:
        return {"status": "UNKNOWN", "message": "Cannot read image file", "confidence": 0.0}

    binary = preprocess(image)
    if debug_dir:
        cv2.imwrite(os.path.join(debug_dir, "1_binary.png"), binary)

    # Anchor detection
    anchors = detect_anchors(binary)
    if anchors is None:
        # Fallback: try without perspective correction
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape)==3 else image
        canonical = cv2.resize(gray, (TARGET_W, TARGET_H))
        anchor_found = False
    else:
        warped_full = rectify(image, anchors)
        canonical = cv2.cvtColor(warped_full, cv2.COLOR_BGR2GRAY) if len(warped_full.shape)==3 else warped_full
        anchor_found = True
        if debug_dir:
            cv2.imwrite(os.path.join(debug_dir, "2_warped.png"), warped_full)

    # Line segmentation
    lines = segment_lines(canonical)
    if not lines:
        return {
            "status":     "UNKNOWN",
            "message":    "No text lines detected in image",
            "confidence": 0.0,
            "bit_count":  0,
            "anchor_found": anchor_found,
        }

    if debug_dir:
        vis = cv2.cvtColor(canonical, cv2.COLOR_GRAY2BGR)
        for (y0, y1) in lines:
            cv2.rectangle(vis, (0, y0), (TARGET_W, y1), (0, 255, 0), 1)
        cv2.imwrite(os.path.join(debug_dir, "3_lines.png"), vis)

    # Extract all gaps
    all_gaps: list[float] = []
    for (y0, y1) in lines:
        gaps = extract_gaps_from_line(canonical, y0, y1)
        all_gaps.extend(gaps)

    if len(all_gaps) < 40:
        return {
            "status":     "UNKNOWN",
            "message":    f"Too few inter-word gaps ({len(all_gaps)}) — need at least 40",
            "confidence": 0.0,
            "bit_count":  len(all_gaps),
            "anchor_found": anchor_found,
        }

    bits = gaps_to_bits(all_gaps)

    # Sliding Reed-Solomon decode
    result = sliding_decode(bits)

    p25 = float(np.percentile(all_gaps, 25)) if all_gaps else 0.0
    p75 = float(np.percentile(all_gaps, 75)) if all_gaps else 0.0
    th = THRESHOLD_PX if (p75 - p25 < 3.0) else (p25 + p75) / 2.0
    gap_sample = [round(float(g), 1) for g in all_gaps[:64]]

    if result is None or not result.get("valid"):
        return {
            "status":     "CORRUPTED",
            "message":    "Watermark signal found but Reed-Solomon decode failed",
            "confidence": float(len(bits)) / 280,
            "bit_count":  len(bits),
            "anchor_found": anchor_found,
            "threshold":  round(float(th), 1),
            "gap_sample": gap_sample,
        }

    confidence = min(1.0, len(bits) / 200)   # scale by how many bits we got

    return {
        "status":       "VERIFIED",
        "centre_id":    result["centre_id"],
        "hall_id":      result["hall_id"],
        "print_num":    result["print_num"],
        "timestamp":    result["timestamp"],
        "confidence":   round(confidence, 3),
        "bit_count":    len(bits),
        "bit_offset":   result.get("bit_offset", 0),
        "anchor_found": anchor_found,
        "threshold":    round(float(th), 1),
        "gap_sample":   gap_sample,
        "message":      (
            f"LEAK TRACED — Centre {result['centre_id']} · "
            f"Hall {result['hall_id']} · Print #{result['print_num']} · "
            f"Epoch {result['timestamp']}"
        ),
    }


# ---------------------------------------------------------------------------
# CLI usage
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys, pprint
    if len(sys.argv) < 2:
        print("Usage: python core/decoder.py <image_path> [debug_dir]")
        sys.exit(1)
    img = sys.argv[1]
    dbg = sys.argv[2] if len(sys.argv) > 2 else None
    result = decode_photo(img, debug_dir=dbg)
    pprint.pprint(result)
