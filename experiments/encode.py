"""
ZeroLeak Experiments — Minimal Steganography Encoder
=====================================================
Gate test step 1: Generate a watermarked PDF from the command line.
Usage:
    python experiments/encode.py --centre 14 --hall 3 --print 1 --output test_paper.pdf
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import argparse
import time
from core.renderer import generate_watermarked_pdf

SAMPLE_QUESTIONS = [
    "Explain the working principle of a digital watermark. How does it differ from a traditional visible watermark? Discuss the trade-offs between robustness and imperceptibility in forensic applications.",
    "A train departs from Station A at 60 km/h and returns from Station B at 40 km/h. Assuming the distance between the stations is constant, calculate the average speed of the entire journey and explain why it is not simply the arithmetic mean.",
    "Describe how Reed-Solomon error correction codes work. Explain why redundancy is necessary when recovering data from a noisy analog channel such as a printed and photographed document.",
    "Define the term homography in the context of computer vision. Show how it is used to perform perspective correction on a photograph of a document taken at an arbitrary angle.",
    "A rectangular block of mass 10 kg rests on a horizontal surface with coefficient of static friction 0.4. Calculate the minimum horizontal force required to set it in motion. Take g = 9.8 m/s^2.",
    "Explain the key difference between symmetric encryption such as AES and asymmetric encryption such as RSA. For each, describe a real-world scenario where that scheme would be the preferred choice.",
    "Using integration, find the area enclosed between the parabola y = x^2 and the straight line y = x + 2. Show all intermediate steps and verify your answer geometrically.",
    "Describe Shamir's Secret Sharing scheme. Why is a threshold k-of-n scheme more resistant to both collusion and key loss compared with simply dividing the secret into n equal non-overlapping parts?",
    "The concentration of a drug in the bloodstream follows C(t) = 8 e^(-0.5t) mg/L. Calculate the time at which the concentration falls below 1 mg/L and find the total drug exposure over that period.",
    "Compare the OSI model and the TCP/IP model. For each layer of the OSI model identify the closest equivalent in TCP/IP and give one protocol that operates at that layer.",
]


def main():
    parser = argparse.ArgumentParser(description="ZeroLeak watermark encoder gate test")
    parser.add_argument("--centre",  type=int, default=14,   help="Centre ID")
    parser.add_argument("--hall",    type=int, default=3,    help="Hall ID")
    parser.add_argument("--print",   type=int, default=1,    dest="print_num", help="Print number")
    parser.add_argument("--output",  type=str, default="experiments/test_paper.pdf", help="Output PDF path")
    parser.add_argument("--title",   type=str, default="ZeroLeak Gate Test — Examination Paper")
    args = parser.parse_args()

    ts = int(time.time())
    print(f"Encoding payload: centre={args.centre}, hall={args.hall}, print={args.print_num}, ts={ts}")

    os.makedirs(os.path.dirname(args.output) if os.path.dirname(args.output) else ".", exist_ok=True)

    pdf_bytes = generate_watermarked_pdf(
        questions=SAMPLE_QUESTIONS,
        centre_id=args.centre,
        hall_id=args.hall,
        print_num=args.print_num,
        timestamp=ts,
        exam_title=args.title,
        output_path=args.output,
    )

    print(f"✅  PDF written: {args.output}  ({len(pdf_bytes):,} bytes)")
    print()
    print("Next step:")
    print("  1. Print this PDF on a physical printer")
    print("  2. Photograph it with your phone (try straight-on and ~15° tilt)")
    print("  3. Run:  python experiments/decode.py --image <photo.jpg>")
    print(f"  4. Expected output: centre={args.centre}, hall={args.hall}, print={args.print_num}")


if __name__ == "__main__":
    main()
