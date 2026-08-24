#!/usr/bin/env python3
"""JPEG images to PDF using img2pdf, with reportlab fallback."""

import sys
from pathlib import Path

try:
    from img2pdf import convert as img2pdf_convert
except Exception:  # pragma: no cover - fallback path
    img2pdf_convert = None

try:
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import letter
    from PIL import Image
except Exception:  # pragma: no cover - fallback path
    canvas = None


def _img2pdf(image_paths, output_path):
    with open(output_path, "wb") as f:
        f.write(img2pdf_convert(image_paths))


def _reportlab_pdf(image_paths, output_path):
    c = canvas.Canvas(output_path)
    for img_path in image_paths:
        with Image.open(img_path) as im:
            w, h = im.size
        c.setPageSize((w, h))
        c.drawImage(img_path, 0, 0, width=w, height=h)
        c.showPage()
    c.save()


def jpegs_to_pdf(image_paths, output_path):
    if img2pdf_convert:
        _img2pdf(image_paths, output_path)
    elif canvas:
        _reportlab_pdf(image_paths, output_path)
    else:
        raise RuntimeError("Neither img2pdf nor reportlab is available")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: jpegs_to_pdf.py output.pdf input1.jpg [input2.jpg ...]")
        sys.exit(1)
    jpegs_to_pdf(sys.argv[2:], sys.argv[1])
    print(f"Created {sys.argv[1]}")
