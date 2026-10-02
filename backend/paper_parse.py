"""
ZeroLock — Document Content Parser & Capacity Guard
===================================================
Extracts title, preamble, and questions from uploaded exam documents (PDF & DOCX).
Strips institutional headers/footers, folds sub-parts, preserves Unicode mathematics,
and enforces capacity bounds for forensic watermark embedding.
"""

from __future__ import annotations

import io
import re
from typing import Optional

# Institutional headers, footers, metadata and separator patterns to strip
JUNK_PATTERNS = [
    r'^Date:.*',
    r'^\*+$',
    r'.*Pune Institute of Computer Technology.*',
    r'.*Department of Electronics.*',
    r'.*Digital Signal Processing Tutorial.*',
    r'^Class:.*',
    r'^Academic Year:.*',
    r'^Semester:.*',
    r'^\d{4,6}[A-Z0-9]+$',                  # Course codes like 2625PC53
    r'^Page\s+\d+(\s+of\s+\d+)?$',
    r'^Confidential.*',
    r'^Roll\s+No:?.*',
]

MIN_WORD_THRESHOLD = 30
COMPACT_WORD_THRESHOLD = 200


class ParseError(Exception):
    """Raised when an uploaded document cannot be parsed or decoded."""
    pass


class CapacityError(Exception):
    """Raised when document content is too short for reliable watermark embedding."""
    pass


def _extract_text_from_pdf(file_bytes: bytes) -> str:
    """Extract raw text from PDF stream using fitz (PyMuPDF)."""
    try:
        import fitz
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        text = "\n".join(page.get_text() for page in doc)
        doc.close()
        return text
    except Exception as e:
        raise ParseError(f"Failed to read PDF document: {e}")


def _extract_text_from_docx(file_bytes: bytes) -> str:
    """Extract raw text from DOCX stream using python-docx."""
    try:
        import docx
        doc = docx.Document(io.BytesIO(file_bytes))
        lines = [p.text for p in doc.paragraphs]
        return "\n".join(lines)
    except Exception as e:
        raise ParseError(f"Failed to read DOCX document: {e}")


def parse_upload(file_bytes: bytes, filename: str) -> dict:
    """
    Parse uploaded exam file and return structured question paper.

    Returns:
        dict: {
            "title": str,
            "preamble": list[str],
            "questions": list[str],
            "engine": "compact" | "standard",
            "word_count": int,
        }

    Raises:
        ParseError: If file is unreadable or malformed.
        CapacityError: If document lacks sufficient capacity for watermarking.
    """
    if not file_bytes:
        raise ParseError("Uploaded file is empty.")

    fn = filename.lower()
    if fn.endswith(".pdf"):
        raw_text = _extract_text_from_pdf(file_bytes)
    elif fn.endswith(".docx") or fn.endswith(".doc"):
        raw_text = _extract_text_from_docx(file_bytes)
    elif fn.endswith(".txt"):
        try:
            raw_text = file_bytes.decode("utf-8")
        except UnicodeDecodeError:
            raw_text = file_bytes.decode("latin-1", errors="replace")
    else:
        raise ParseError(f"Unsupported file format '{filename}'. Please upload a PDF or DOCX file.")

    raw_lines = [l.strip() for l in raw_text.split("\n") if l.strip()]
    if not raw_lines:
        raise ParseError("Document contains no readable text. Please upload a text-based PDF or DOCX.")

    # Strip institutional junk lines
    clean_lines = []
    for l in raw_lines:
        if any(re.match(p, l, re.IGNORECASE) for p in JUNK_PATTERNS):
            continue
        clean_lines.append(l)

    if not clean_lines:
        raise ParseError("Document contained only metadata or headers with no examination questions.")

    # Separate preamble/title from body
    preamble = []
    body_lines = []
    found_first_q = False

    for idx, l in enumerate(clean_lines):
        if not found_first_q:
            # First question detection (e.g. "1.", "1)", "Q1", "Question 1")
            if re.match(r'^(?:Q(?:uestion)?\s*)?1[.)]\s*', l):
                found_first_q = True
                body_lines.append(l)
            else:
                preamble.append(l)
        else:
            body_lines.append(l)

    # If no numbered first question was found, treat entire clean text as body
    if not found_first_q:
        body_lines = clean_lines
        preamble = []

    # Segment questions and fold sub-parts
    questions = []
    curr_q = []
    expected_q_num = 1

    for idx, l in enumerate(body_lines):
        m = re.match(r'^(?:Q(?:uestion)?\s*)?([1-9]\d*)[.)]\s*(.*)', l)
        m_lone = re.match(r'^([1-9]\d*)[.)]?$', l)
        num = None
        rem = ""
        if m:
            num = int(m.group(1))
            rem = m.group(2).strip()
        elif m_lone:
            num = int(m_lone.group(1))
            rem = ""

        # Only treat as a new question start if number matches expected sequence.
        # This keeps sub-points (e.g. 1. Input sequence ..., 2. Output sequence ...) inside Q11.
        if num == expected_q_num:
            if curr_q:
                questions.append(" ".join(curr_q))
                curr_q = []
            expected_q_num += 1
            if rem:
                curr_q.append(rem)
        else:
            curr_q.append(l)

    if curr_q:
        questions.append(" ".join(curr_q))

    # Fallback: if no questions segmented, treat whole body as single question
    if not questions and body_lines:
        questions = [" ".join(body_lines)]

    # Compute word count over questions
    total_q_text = " ".join(questions)
    words = total_q_text.split()
    word_count = len(words)

    # Capacity guard
    if word_count < MIN_WORD_THRESHOLD:
        raise CapacityError(
            f"Paper too short ({word_count} words). Minimum {MIN_WORD_THRESHOLD} words required "
            "for forensic watermark gap modulation."
        )

    # Title extraction
    title = preamble[0] if preamble else "Examination Paper"
    remaining_preamble = preamble[1:] if len(preamble) > 1 else []

    engine = "compact" if word_count < COMPACT_WORD_THRESHOLD else "standard"

    return {
        "title": title,
        "preamble": remaining_preamble,
        "questions": questions,
        "engine": engine,
        "word_count": word_count,
    }
