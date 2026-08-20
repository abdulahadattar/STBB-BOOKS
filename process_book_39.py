#!/usr/bin/env python3
"""
Process Grade 1 - General Knowledge I (id=39)
Steps: download -> inspect pages -> detect Unit markers -> split into chapters
       -> flatten to grayscale JPEG -> assemble PDFs -> verify -> git commit -> delete raw
"""

import os
import re
import sys
import json
import time
import shutil
import subprocess
import urllib.request
import urllib.error

WORKSPACE = "/workspace/4fba1b35-c093-4694-aa80-9a73b48e2a0f/sessions/agent_fb1dc3f1-092e-4f66-aa62-7dbf088f2b51"
BOOK_ID = "39"
CLASS_NAME = "Grade 1"
RAW_TITLE = "General Knowledge I"
SUBJECT = "General Knowledge"
BASE_URL = "https://portal.stbb.edu.pk"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


def log(msg):
    print(msg, flush=True)


def sanitize(name):
    name = re.sub(r'[<>:"/\\|?*]', '', name)
    name = re.sub(r'\s+', ' ', name).strip()
    return name


def download_book(book_id, dest_path):
    if os.path.exists(dest_path) and os.path.getsize(dest_path) > 100000:
        log(f"  Already downloaded: {dest_path}")
        return dest_path
    url = f"{BASE_URL}/ebooks/pdf_proxy.php?id={book_id}&download=1"
    log(f"  Downloading from {url}")
    req = urllib.request.Request(url, headers=HEADERS)
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    with urllib.request.urlopen(req, timeout=300) as resp:
        with open(dest_path, 'wb') as f:
            while True:
                chunk = resp.read(262144)
                if not chunk:
                    break
                f.write(chunk)
    log(f"  Downloaded to {dest_path} ({os.path.getsize(dest_path)} bytes)")
    return dest_path


def get_pdf_page_count(pdf_path):
    result = subprocess.run(["pdfinfo", pdf_path], capture_output=True, text=True)
    for line in result.stdout.splitlines():
        if line.startswith("Pages:"):
            return int(line.split(":")[1].strip())
    return 0


def extract_text_page(pdf_path, page):
    result = subprocess.run(
        ["pdftotext", "-f", str(page), "-l", str(page), "-layout", pdf_path, "-"],
        capture_output=True, text=True
    )
    return result.stdout.strip()


def detect_chapters(pdf_path):
    total = get_pdf_page_count(pdf_path)
    if total == 0:
        log("  WARNING: Could not determine page count")
        return []
    log(f"  Total pages: {total}")

    unit_num_re = re.compile(r'Unit\s+[-–—]?\s*(\d+)', re.IGNORECASE)
    unit_starts = []

    for page in range(1, total + 1):
        text = extract_text_page(pdf_path, page)
        if not text:
            continue
        match = unit_num_re.search(text)
        if match:
            unit_starts.append((page, int(match.group(1))))

    if not unit_starts:
        log("  No Unit markers found")
        return []

    log(f"  Found unit markers on pages: {unit_starts}")

    # Deduplicate by unit number
    seen_units = set()
    unique_starts = []
    for page, num in unit_starts:
        if num not in seen_units:
            seen_units.add(num)
            unique_starts.append((page, num))

    # Extract title for each unit
    body_stops = re.compile(
        r'^(The|A|An|and|Encourage|Note|Anechoic|Transverse|Crest|Trough|Refracting|Compressed|Stretched|Circular|Incident|Direction|Rigid|Whales|Defect|Display|Light|Lamp|Vibrator|Elastic|banana|girl|Nucleus|Electron|Proton|Karachi|KUNUPP|Note for|Follow the|While teaching)\b',
        re.IGNORECASE
    )

    chapters = []
    for page, num in unique_starts:
        text = extract_text_page(pdf_path, page)
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        title_parts = []
        for i, line in enumerate(lines):
            m = unit_num_re.search(line)
            if not m:
                continue
            for j in range(i + 1, min(i + 4, len(lines))):
                part = lines[j]
                if re.match(r'^\d+$', part):
                    continue
                if len(part) < 2:
                    continue
                if body_stops.match(part):
                    break
                if len(part) > 50:
                    break
                title_parts.append(part)
                if len(' '.join(title_parts)) > 70:
                    break
                if len(title_parts) >= 2:
                    break
            break

        title = ' '.join(title_parts).strip()
        title = re.sub(r'\s+', ' ', title)
        if not title or len(title) < 3:
            title = f"Unit {num}"

        chapters.append({
            "num": num,
            "title": title,
            "page_start": page,
            "page_end": None
        })

    # Calculate page ranges
    for i in range(len(chapters) - 1):
        chapters[i]["page_end"] = chapters[i + 1]["page_start"] - 1
    if chapters:
        chapters[-1]["page_end"] = total

    # Filter tiny chapters
    chapters = [ch for ch in chapters if (ch["page_end"] - ch["page_start"] + 1) >= 2]

    log(f"  Detected {len(chapters)} chapters")
    for ch in chapters:
        log(f"    Unit {ch['num']}: {ch['title']} (pages {ch['page_start']}-{ch['page_end']})")

    return chapters


def flatten_pdf(input_pdf, output_pdf, start_page, end_page):
    temp_dir = output_pdf + "_temp"
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)
    os.makedirs(temp_dir)

    try:
        cmd = [
            "pdftoppm",
            "-f", str(start_page),
            "-l", str(end_page),
            "-jpeg",
            "-jpegopt", "quality=80",
            "-r", "120",
            "-gray",
            input_pdf,
            os.path.join(temp_dir, "page")
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            log(f"  pdftoppm error: {result.stderr[:200]}")
            return False

        images = sorted([
            os.path.join(temp_dir, f)
            for f in os.listdir(temp_dir)
            if f.endswith('.jpg')
        ])

        if not images:
            log("  No images generated")
            return False

        # Use pure Python jpegs_to_pdf
        sys.path.insert(0, WORKSPACE)
        from jpegs_to_pdf import jpegs_to_pdf
        jpegs_to_pdf(images, output_pdf)

        size_kb = os.path.getsize(output_pdf) // 1024
        log(f"  Flattened: {os.path.basename(output_pdf)} ({size_kb}KB, {len(images)} pages)")
        return True
    finally:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)


def git_commit(message):
    try:
        subprocess.run(["git", "config", "http.postBuffer", "524288000"], check=True, capture_output=True)
        subprocess.run(["git", "add", "-A"], check=True, capture_output=True, text=True)
        subprocess.run(["git", "commit", "-m", message], check=True, capture_output=True, text=True)
        log(f"  Git committed: {message}")
        return True
    except subprocess.CalledProcessError as e:
        log(f"  Git commit error: {e.stderr[:200] if e.stderr else str(e)}")
        return False


def git_push_with_retry(max_retries=3):
    for attempt in range(max_retries):
        try:
            subprocess.run(["git", "push"], check=True, capture_output=True, text=True, timeout=120)
            log(f"  Git push succeeded on attempt {attempt + 1}")
            return True
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr[:300] if e.stderr else str(e)
            log(f"  Git push attempt {attempt + 1} failed: {error_msg}")
            if attempt < max_retries - 1:
                wait = 10 * (attempt + 1)
                log(f"  Waiting {wait}s before retry...")
                time.sleep(wait)
            else:
                log(f"  Git push failed after {max_retries} attempts")
                return False
        except Exception as e:
            log(f"  Git push error: {str(e)[:200]}")
            if attempt < max_retries - 1:
                time.sleep(10 * (attempt + 1))
            else:
                return False
    return False


def main():
    log("="*60)
    log(f"Processing: {CLASS_NAME} - {RAW_TITLE} (id={BOOK_ID})")
    log("="*60)

    raw_dir = os.path.join(WORKSPACE, "_raw", sanitize(CLASS_NAME))
    raw_path = os.path.join(raw_dir, f"{sanitize(RAW_TITLE)}.pdf")

    # Step 1: Download
    download_book(BOOK_ID, raw_path)

    # Step 2 & 3: Verify and get page count
    size_mb = os.path.getsize(raw_path) // (1024 * 1024)
    total_pages = get_pdf_page_count(raw_path)
    log(f"  Verified: {total_pages} pages, {size_mb}MB")

    # Step 4 & 5: Inspect pages for Unit markers
    chapters = detect_chapters(raw_path)

    # Step 6: Determine chapter boundaries
    if not chapters:
        log("  No chapters detected, flattening entire book")
        output_dir = os.path.join(WORKSPACE, sanitize(CLASS_NAME), sanitize(SUBJECT))
        os.makedirs(output_dir, exist_ok=True)
        filename = f"{sanitize(SUBJECT)} - Full Book.pdf"
        filepath = os.path.join(output_dir, filename)
        flatten_pdf(raw_path, filepath, 1, total_pages)
        git_commit(f"Add {CLASS_NAME} {SUBJECT} full book")
        git_push_with_retry()
        os.remove(raw_path)
        log("  Cleaned up raw PDF")
        return

    # Step 7 & 8: Create output directory
    output_dir = os.path.join(WORKSPACE, sanitize(CLASS_NAME), sanitize(SUBJECT))
    os.makedirs(output_dir, exist_ok=True)

    # Step 9: For each chapter, assemble PDF
    created = []
    for ch in chapters:
        start = ch["page_start"]
        end = ch["page_end"]
        title = sanitize(ch["title"])
        filename = f"Chapter {ch['num']:02d} - {title}.pdf"
        filepath = os.path.join(output_dir, filename)

        if os.path.exists(filepath) and os.path.getsize(filepath) > 10000:
            log(f"  Already exists: {filename}")
            created.append(filepath)
            continue

        success = flatten_pdf(raw_path, filepath, start, end)
        if success:
            created.append(filepath)
        else:
            log(f"  FAILED to create: {filename}")

    # Step 10: Verify output PDFs
    log(f"\n  Verification:")
    all_ok = True
    for f in created:
        if os.path.exists(f) and os.path.getsize(f) > 0:
            log(f"    OK: {os.path.basename(f)} ({os.path.getsize(f)//1024}KB)")
        else:
            log(f"    MISSING or EMPTY: {os.path.basename(f)}")
            all_ok = False

    # Step 11: Git commit and push
    if all_ok:
        git_commit(f"Add {CLASS_NAME} {SUBJECT} chapters")
        git_push_with_retry()
    else:
        log("  WARNING: Some chapters failed, committing what we have")
        git_commit(f"Add {CLASS_NAME} {SUBJECT} chapters (partial)")

    # Step 12: Delete raw PDF
    if os.path.exists(raw_path):
        os.remove(raw_path)
        log(f"  Cleaned up raw PDF")

    # Step 13: Report
    log("\n" + "="*60)
    log(f"COMPLETE: {CLASS_NAME} {SUBJECT}")
    log(f"Chapters found: {len(chapters)}")
    log(f"Chapters created: {len(created)}")
    for f in created:
        log(f"  - {os.path.basename(f)} ({os.path.getsize(f)//1024}KB)")
    log("="*60)


if __name__ == "__main__":
    main()
