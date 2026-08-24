#!/usr/bin/env python3
"""Direct book uploader for Windows: download, image-flatten, commit."""

import os
import sys
import re
import json
import glob
import shutil
import urllib.request
import pymupdf

try:
    from jpegs_to_pdf import jpegs_to_pdf
except Exception:
    jpegs_to_pdf = None

REPO = os.path.dirname(os.path.abspath(__file__))
BASE_URL = "https://portal.stbb.edu.pk"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


def sanitize(name):
    name = re.sub(r'[<>:"/\\|?*]', '', name)
    name = re.sub(r'\s+', ' ', name).strip()
    return name


def download(book_id, title, class_name):
    raw_dir = os.path.join(REPO, "_raw", sanitize(class_name))
    os.makedirs(raw_dir, exist_ok=True)
    raw_path = os.path.join(raw_dir, f"{sanitize(title)}.pdf")
    if os.path.exists(raw_path) and os.path.getsize(raw_path) > 10000:
        return raw_path
    url = f"{BASE_URL}/ebooks/pdf_proxy.php?id={book_id}&download=1"
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=300) as resp, open(raw_path, 'wb') as f:
        while True:
            chunk = resp.read(262144)
            if not chunk:
                break
            f.write(chunk)
    return raw_path


def page_text(pdf_path, page_number):
    with pymupdf.open(pdf_path) as doc:
        if 1 <= page_number <= doc.page_count:
            return doc[page_number - 1].get_text()
    return ""


def has_chapter_marker(txt):
    return bool(re.search(r'(?:Chapter|Unit)\s+[-–—]?\s*\d+', txt, re.IGNORECASE)) or bool(re.search(r'Time Allocation', txt, re.IGNORECASE))


def detect_chapters(pdf_path):
    with pymupdf.open(pdf_path) as doc:
        total = doc.page_count
    pages = []
    for i in range(1, min(total, 80) + 1):
        txt = page_text(pdf_path, i)
        if not txt:
            continue
        chapters = re.findall(r'(?:Chapter|Unit)\s+[-–—]?\s*\d+', txt, re.IGNORECASE)
        if len(chapters) >= 3:
            continue
        if has_chapter_marker(txt):
            pages.append(i)
    filtered = []
    for p in pages:
        if not filtered or p - filtered[-1] > 2:
            filtered.append(p)
    chapters = []
    for idx, p in enumerate(filtered):
        end = filtered[idx + 1] - 1 if idx + 1 < len(filtered) else total
        title = f"Unit {p}"
        txt = page_text(pdf_path, p)
        lines = [line.strip() for line in txt.splitlines() if line.strip()]
        for line in lines:
            m = re.search(r'(?:Chapter|Unit)\s+[-–—]?\s*(\d+)\s*[-–—]?\s*(.+)', line, re.IGNORECASE)
            if m:
                title = f"Chapter {m.group(1)} - {m.group(2).strip()}"
                break
        chapters.append({"num": idx + 1, "page": p, "end": end, "title": title})
    chapters = [c for c in chapters if (c["end"] - c["page"] + 1) >= 2]
    # Merge consecutive chapters with identical detected titles to avoid 3-page duplicates
    merged = []
    for c in chapters:
        if merged and merged[-1]["title"] == c["title"]:
            merged[-1]["end"] = c["end"]
        else:
            merged.append(c)
    for i, ch in enumerate(merged):
        ch["num"] = i + 1
    return merged


def flatten_pdf(input_pdf, output_pdf, start_page, end_page):
    temp_dir = output_pdf + "_temp"
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)
    os.makedirs(temp_dir, exist_ok=True)
    try:
        images = []
        with pymupdf.open(input_pdf) as doc:
            for i in range(start_page - 1, min(end_page, doc.page_count)):
                page = doc.load_page(i)
                pix = page.get_pixmap(matrix=pymupdf.Matrix(1.5, 1.5), alpha=False)
                img_path = os.path.join(temp_dir, f"page_{i+1:04d}.jpg")
                os.makedirs(os.path.dirname(img_path), exist_ok=True)
                pix.save(img_path, output="jpeg", jpg_quality=80)
                images.append(img_path)
        if not images:
            return False
        if jpegs_to_pdf is None:
            raise RuntimeError("jpegs_to_pdf is not available")
        jpegs_to_pdf(images, output_pdf)
        return os.path.exists(output_pdf) and os.path.getsize(output_pdf) > 10000
    finally:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)


def process_book(book_id, title, class_name, subject):
    print(f"\n{'='*60}")
    print(f"Processing: {class_name} - {title}")
    print(f"Subject: {subject}")
    raw_path = download(book_id, title, class_name)
    if not raw_path or not os.path.exists(raw_path):
        print("  Download failed")
        return False
    size_mb = os.path.getsize(raw_path) / (1024 * 1024)
    print(f"  Downloaded: {size_mb:.1f}MB")
    chapters = detect_chapters(raw_path)
    print(f"  Detected {len(chapters)} chapters")
    for ch in chapters:
        print(f"    Chapter {ch['num']:02d}: {ch['title']} (pages {ch['page']}-{ch['end']})")
    output_dir = os.path.join(REPO, sanitize(class_name), sanitize(subject))
    os.makedirs(output_dir, exist_ok=True)
    if not chapters:
        filename = f"{sanitize(subject)} - Full Book.pdf"
        filepath = os.path.join(output_dir, filename)
        if os.path.exists(filepath) and os.path.getsize(filepath) > 10000:
            print(f"  Already exists: {filename}")
            return True
        success = flatten_pdf(raw_path, filepath, 1, pymupdf.open(raw_path).page_count)
        print(f"  Flattened full book: {success}")
        if success and os.path.getsize(filepath) > 95 * 1024 * 1024:
            print(f"  Splitting oversized full book: {filename}")
            # Remove oversized file after split
            os.remove(filepath)
            chunk = 50
            with pymupdf.open(raw_path) as doc:
                total = doc.page_count
            parts = 0
            for start in range(1, total + 1, chunk):
                end = min(start + chunk - 1, total)
                part_path = os.path.join(output_dir, f"{sanitize(subject)} - Part {len(parts)}.pdf")
                if os.path.exists(part_path) and os.path.getsize(part_path) > 10000:
                    parts += 1
                    continue
                part_success = flatten_pdf(raw_path, part_path, start, end)
                if part_success:
                    parts += 1
                    print(f"    Created part {parts}: {part_path}")
            return parts > 0
        return success
    created = []
    for ch in chapters:
        start = ch["page"]
        end = ch["end"]
        title_text = sanitize(ch["title"])
        filename = f"Chapter {ch['num']:02d} - {title_text}.pdf"
        filepath = os.path.join(output_dir, filename)
        if os.path.exists(filepath) and os.path.getsize(filepath) > 10000:
            print(f"  Already exists: {filename}")
            created.append(filepath)
            continue
        success = flatten_pdf(raw_path, filepath, start, end)
        if success:
            created.append(filepath)
        else:
            print(f"  FAILED to create: {filename}")
    print(f"  Created {len(created)} chapter files")
    return len(created) > 0


if __name__ == "__main__":
    if len(sys.argv) < 5:
        print("Usage: upload_one_book.py <book_id> <title> <class_name> <subject>")
        sys.exit(1)
    success = process_book(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4])
    sys.exit(0 if success else 1)
