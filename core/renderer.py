"""
ZeroLeak Core — Watermarked PDF Renderer
=========================================
Uses ReportLab to generate exam papers with:
  1. Four corner crosshair anchors for OpenCV homography correction
  2. Inter-word space modulation steganography (bit=1 → wide gap, bit=0 → narrow gap)

Encoding:
    Base word gap : 12 pt
    Wide gap (1)  : 15 pt  (+3 pt)
    Narrow gap (0):  9 pt  (-3 pt)
    Delta         :  6 pt  — survives print→camera→JPEG pipeline
"""

from __future__ import annotations
import io
import os
from typing import Optional

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
# pt = 1.0 in ReportLab (1 pt == 1 ReportLab unit)
from reportlab.lib import colors

# ---------------------------------------------------------------------------
# Layout constants
# ---------------------------------------------------------------------------
PAGE_W, PAGE_H = A4                 # 595.28 × 841.89 pt
MARGIN_X       = 50.0               # left/right margin (pt)
MARGIN_TOP     = PAGE_H - 60.0      # top text start
MARGIN_BOTTOM  = 60.0               # bottom bound

FONT_NAME  = "Helvetica"
FONT_SIZE  = 11.0
LINE_HEIGHT = 16.0

# Word-gap steganography parameters
BASE_GAP   = 12.0   # pt — baseline inter-word space
WIDE_GAP   = 15.0   # pt — encodes bit 1
NARROW_GAP =  9.0   # pt — encodes bit 0
DELTA      = WIDE_GAP - BASE_GAP   # 3 pt (each direction)

# Corner crosshair parameters (margin corners for homography)
ANCHOR_OFFSET = 22.0   # pt inset from page edge
ANCHOR_SIZE   = 8.0    # pt arm length


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _draw_crosshair(c: canvas.Canvas, x: float, y: float) -> None:
    """Draw a small + crosshair at (x, y) in pt coordinates."""
    c.saveState()
    c.setStrokeColor(colors.black)
    c.setLineWidth(1.0)
    c.line(x - ANCHOR_SIZE, y, x + ANCHOR_SIZE, y)
    c.line(x, y - ANCHOR_SIZE, x, y + ANCHOR_SIZE)
    # Tiny filled square at centre for easier contour detection
    c.setFillColor(colors.black)
    c.rect(x - 2, y - 2, 4, 4, stroke=0, fill=1)
    c.restoreState()


def _draw_anchors(c: canvas.Canvas) -> dict:
    """
    Draw the four corner crosshairs and return their positions.
    Returns dict with keys: tl, tr, bl, br  →  (x, y) in pt
    """
    positions = {
        "tl": (ANCHOR_OFFSET, PAGE_H - ANCHOR_OFFSET),
        "tr": (PAGE_W - ANCHOR_OFFSET, PAGE_H - ANCHOR_OFFSET),
        "bl": (ANCHOR_OFFSET, ANCHOR_OFFSET),
        "br": (PAGE_W - ANCHOR_OFFSET, ANCHOR_OFFSET),
    }
    for _, (x, y) in positions.items():
        _draw_crosshair(c, x, y)
    return positions


def _word_width(c: canvas.Canvas, word: str) -> float:
    """Return rendered width of word in current font."""
    return c.stringWidth(word, FONT_NAME, FONT_SIZE)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_watermarked_pdf(
    questions: list[str],
    centre_id: int,
    hall_id: int,
    print_num: int,
    timestamp: int,
    exam_title: str = "Secure Examination Paper",
    output_path: Optional[str] = None,
    mode: str = "standard",
) -> bytes:
    """
    Generate a watermarked exam-paper PDF.

    The inter-word spaces carry a Reed-Solomon encoded payload (standard mode)
    or a 48-bit whitened payload with repetition & voting (compact mode).
    Every inter-word gap encodes one bit:
        wide  (15 pt) → 1
        narrow ( 9 pt) → 0
    """
    if mode == "compact":
        from core.payload import generate_compact_bitstream
        stego_bits = generate_compact_bitstream(centre_id, hall_id, print_num, 500)
    else:
        from core.payload import encode_payload
        stego_bits = encode_payload(centre_id, hall_id, print_num, timestamp)
    bit_idx = 0

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)

    # --- Page 1 ---
    _draw_anchors(c)

    # Header
    c.setFont("Helvetica-Bold", 14)
    c.drawCentredString(PAGE_W / 2, MARGIN_TOP + 20, exam_title)
    c.setFont("Helvetica", 9)
    c.drawCentredString(
        PAGE_W / 2, MARGIN_TOP + 6,
        f"[Centre {centre_id:04d} | Hall {hall_id:03d} | Print #{print_num:04d}]  — CONFIDENTIAL",
    )
    c.setLineWidth(0.5)
    c.line(MARGIN_X, MARGIN_TOP, PAGE_W - MARGIN_X, MARGIN_TOP)

    # Body — flow questions with word-gap stego
    c.setFont(FONT_NAME, FONT_SIZE)
    current_y = MARGIN_TOP - LINE_HEIGHT * 1.5
    q_num = 1

    for question in questions:
        # Pre-wrap question into lines with prefix
        prefix = f"Q{q_num}."
        words = [prefix] + question.split()
        
        q_lines = []
        cur_line = []
        cur_w = 0.0
        max_line_w = PAGE_W - 2 * MARGIN_X

        for word in words:
            font_to_use = "Helvetica-Bold" if word == prefix else FONT_NAME
            ww = c.stringWidth(word, font_to_use, FONT_SIZE)
            gap_est = BASE_GAP
            if cur_line and (cur_w + gap_est + ww > max_line_w):
                q_lines.append(cur_line)
                cur_line = [word]
                cur_w = ww
            else:
                if cur_line:
                    cur_w += gap_est
                cur_line.append(word)
                cur_w += ww
        if cur_line:
            q_lines.append(cur_line)

        # Check page overflow
        if current_y - len(q_lines) * LINE_HEIGHT < MARGIN_BOTTOM:
            c.showPage()
            _draw_anchors(c)
            current_y = PAGE_H - 80.0

        # Render lines and inter-word stego gaps
        for line in q_lines:
            x = MARGIN_X
            for i, word in enumerate(line):
                font_to_use = "Helvetica-Bold" if word == prefix else FONT_NAME
                c.setFont(font_to_use, FONT_SIZE)
                c.drawString(x, current_y, word)
                x += c.stringWidth(word, font_to_use, FONT_SIZE)

                if i < len(line) - 1:
                    bit = stego_bits[bit_idx % len(stego_bits)]
                    bit_idx += 1
                    gap = WIDE_GAP if bit else NARROW_GAP
                    x += gap

            current_y -= LINE_HEIGHT

        current_y -= LINE_HEIGHT * 0.4
        q_num += 1

    # Footer
    c.setFont("Helvetica-Oblique", 8)
    c.setFillColor(colors.grey)
    c.drawCentredString(PAGE_W / 2, 30, "ZeroLeak Forensic Watermark — Unauthorised reproduction is traceable")
    c.setFillColor(colors.black)

    c.save()
    pdf_bytes = buf.getvalue()

    if output_path:
        os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(pdf_bytes)

    return pdf_bytes


# ---------------------------------------------------------------------------
# Quick smoke test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import time

    questions = [
        "Explain the working principle of a digital watermark and how it differs from traditional visible watermarks used in physical documents.",
        "A train travels from station A to station B at 60 km/h and returns at 40 km/h. Calculate the average speed for the entire journey.",
        "Describe the mechanism by which Reed-Solomon error correction codes can recover data lost or corrupted during transmission over a noisy channel.",
        "Define the term 'homography' in the context of computer vision and explain how it is used to correct perspective distortion in scanned documents.",
        "A body of mass 5 kg is acted upon by a force of 20 N at an angle of 30 degrees to the horizontal. Find the horizontal and vertical components.",
        "Explain the difference between symmetric and asymmetric encryption, giving one example of each and describing the security trade-offs involved.",
        "Calculate the area enclosed between the curve y = x^2 and the line y = 4 using integration, showing all steps clearly.",
        "Describe the process of Shamir's Secret Sharing and explain why a threshold scheme is more secure than splitting a key into equal independent parts.",
    ]

    ts = int(time.time())
    pdf = generate_watermarked_pdf(
        questions=questions,
        centre_id=14,
        hall_id=3,
        print_num=17,
        timestamp=ts,
        exam_title="ZeroLeak Test Examination Paper",
        output_path="demo/sample_papers/test_watermarked.pdf",
    )
    print(f"✅  Generated PDF: {len(pdf):,} bytes → demo/sample_papers/test_watermarked.pdf")
