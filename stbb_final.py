#!/usr/bin/env python3
"""STBB eBooks Processor - Robust single-threaded downloader/splitter/flattener"""

import os
import re
import sys
import json
import time
import shutil
import subprocess
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from PIL import Image
import img2pdf

WORKSPACE = "/workspace/4fba1b35-c093-4694-aa80-9a73b48e2a0f/sessions/agent_fb1dc3f1-092e-4f66-aa62-7dbf088f2b51"
BASE_URL = "https://portal.stbb.edu.pk"
MEDIUM = "English"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

CLASSES = [
    {"name": "Grade 1", "id": 1},
    {"name": "Grade 2", "id": 3},
    {"name": "Grade 3", "id": 4},
    {"name": "Grade 4", "id": 5},
    {"name": "Grade 5", "id": 6},
    {"name": "Grade 6", "id": 7},
    {"name": "Grade 7", "id": 8},
    {"name": "Grade 8", "id": 9},
    {"name": "Grade 9", "id": 10},
    {"name": "Grade 10", "id": 11},
    {"name": "Grade 11", "id": 14},
    {"name": "Grade 12", "id": 15},
]

PROGRESS_FILE = os.path.join(WORKSPACE, "progress.json")
LOG_FILE = os.path.join(WORKSPACE, "process_log.txt")


def log(msg):
    with open(LOG_FILE, "a") as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} - {msg}\n")
    print(msg)


def get_session():
    session = requests.Session()
    session.headers.update(HEADERS)
    return session


def sanitize(name):
    name = re.sub(r'[<>:"/\\|?*]', '', name)
    name = re.sub(r'\s+', ' ', name).strip()
    return name


def load_progress():
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, "r") as f:
            return json.load(f)
    return {"processed": [], "failed": [], "stats": {}}


def save_progress(progress):
    with open(PROGRESS_FILE, "w") as f:
        json.dump(progress, f, indent=2)


def fetch_class_books(session, class_id):
    url = f"{BASE_URL}/ebooks/class.php?id={class_id}&medium={MEDIUM}"
    resp = session.get(url, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    books = []
    seen = set()
    for a in soup.find_all("a", href=re.compile(r"book\.php\?id=\d+")):
        match = re.search(r"id=(\d+)", a["href"])
        if not match:
            continue
        book_id = match.group(1)
        if book_id in seen:
            continue
        seen.add(book_id)
        title = a.get_text(strip=True)
        if not title:
            container = a.find_parent(["div", "article", "li", "section"])
            if container:
                heading = container.find(["h2", "h3", "h4", "strong", "b"])
                if heading:
                    title = heading.get_text(strip=True)
        if title:
            books.append({"id": book_id, "title": title})
    return books


def download_book(session, book_id, dest_path):
    if os.path.exists(dest_path) and os.path.getsize(dest_path) > 100000:
        return dest_path
    url = f"{BASE_URL}/ebooks/pdf_proxy.php?id={book_id}&download=1"
    log(f"  Downloading from {url}")
    resp = session.get(url, timeout=300, stream=True)
    resp.raise_for_status()
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    with open(dest_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=262144):
            if chunk:
                f.write(chunk)
    return dest_path


def extract_subject_from_title(title):
    title = re.sub(r'^\ud83d\udcd6\w+\s*', '', title)
    title = re.sub(r'\s*•\s*\d{4}(-\d{2})?$', '', title)
    patterns = [
        r'\s+(I|II|III|IV|V|VI|VII|VIII|IX|X|XI|XII|Kachi|ECCE)$',
        r'\s+(I|II|III|IV|V|VI|VII|VIII|IX|X|XI|XII|Kachi|ECCE)\s+(I|II|III|IV|V|VI|VII|VIII|IX|X|XI|XII|Kachi|ECCE)$',
    ]
    for pat in patterns:
        title = re.sub(pat, '', title, flags=re.IGNORECASE).strip()
    title_lower = title.lower()
    if 'biology' in title_lower:
        return 'Biology'
    elif 'chemistry' in title_lower or 'chemsitry' in title_lower:
        return 'Chemistry'
    elif 'physics' in title_lower:
        return 'Physics'
    elif 'math' in title_lower:
        return 'Mathematics'
    elif 'secondary stage english' in title_lower:
        return 'Secondary Stage English'
    elif 'english' in title_lower:
        return 'English'
    elif 'islamiyat' in title_lower or 'religious' in title_lower or 'islmaiyat' in title_lower:
        return 'Islamiyat'
    elif 'pak studies' in title_lower or 'pakistan' in title_lower:
        return 'Pakistan Studies'
    elif 'computer' in title_lower or 'ict' in title_lower:
        return 'Computer Science'
    elif 'science' in title_lower:
        return 'Science'
    elif 'social studies' in title_lower:
        return 'Social Studies'
    elif 'general knowledge' in title_lower:
        return 'General Knowledge'
    elif 'arabic' in title_lower:
        return 'Arabic'
    else:
        return title.strip() if title.strip() else 'Unknown'


def get_pdf_page_count(pdf_path):
    result = subprocess.run(["pdfinfo", pdf_path], capture_output=True, text=True)
    for line in result.stdout.splitlines():
        if line.startswith("Pages:"):
            return int(line.split(":")[1].strip())
    return 0


def extract_text_page(pdf_path, page_num):
    result = subprocess.run(
        ["pdftotext", "-f", str(page_num), "-l", str(page_num), "-layout", pdf_path, "-"],
        capture_output=True, text=True
    )
    return result.stdout.strip()


def detect_chapters_robust(pdf_path):
    """
    Robust chapter detection:
    1. Get total pages
    2. For each page, extract text
    3. Find pages containing 'Unit' followed by a number
    4. Record the unit number and page number
    5. Read title from lines immediately following the unit marker
    6. Deduplicate by unit number
    7. Calculate page ranges
    """
    total_pages = get_pdf_page_count(pdf_path)
    if total_pages == 0:
        log("  WARNING: Could not determine page count")
        return []
    
    log(f"  Total pages: {total_pages}")
    
    # Find all unit start pages
    unit_starts = []
    unit_num_pattern = re.compile(r'Unit\s+[-–—]?\s*(\d+)', re.IGNORECASE)
    
    for page in range(1, total_pages + 1):
        text = extract_text_page(pdf_path, page)
        if not text:
            continue
        match = unit_num_pattern.search(text)
        if match:
            unit_starts.append((page, int(match.group(1))))
    
    if not unit_starts:
        log("  No Unit markers found")
        return []
    
    log(f"  Found unit markers on {len(unit_starts)} pages: {[u[1] for u in unit_starts]}")
    
    # Deduplicate by unit number, keeping first occurrence
    seen_units = set()
    unique_starts = []
    for page, num in unit_starts:
        if num not in seen_units:
            seen_units.add(num)
            unique_starts.append((page, num))
    
    # Extract title for each unit
    chapters = []
    body_stops = re.compile(
        r'^(The|A|An|and|Encourage|Note|Anechoic|Transverse|Crest|Trough|Refracting|Compressed|Stretched|Circular|Incident|Direction|Rigid|Whales|Defect|Display|Light|Lamp|Vibrator|Elastic|banana|girl|Nucleus|Electron|Proton|Karachi|KUNUPP|Note for|Follow the|While teaching)\b',
        re.IGNORECASE
    )
    
    for page, num in unique_starts:
        text = extract_text_page(pdf_path, page)
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        
        title_parts = []
        for i, line in enumerate(lines):
            if unit_num_pattern.search(line):
                # Look at next lines for title
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
    
    # Calculate page ends
    for i in range(len(chapters) - 1):
        chapters[i]["page_end"] = chapters[i + 1]["page_start"] - 1
    if chapters:
        chapters[-1]["page_end"] = total_pages
    
    # Filter out tiny chapters (< 2 pages)
    chapters = [ch for ch in chapters if (ch["page_end"] - ch["page_start"] + 1) >= 2]
    
    log(f"  Detected {len(chapters)} chapters")
    for ch in chapters:
        log(f"    Unit {ch['num']}: {ch['title']} (pages {ch['page_start']}-{ch['page_end']})")
    
    return chapters


def flatten_pdf(input_pdf, output_pdf, start_page, end_page):
    """Flatten PDF pages to JPEG and reassemble"""
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
            "-jpegopt", "quality=85",
            "-r", "150",
            input_pdf,
            os.path.join(temp_dir, "page")
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            log(f"  ERROR: pdftoppm failed: {result.stderr}")
            return False
        
        images = sorted([
            os.path.join(temp_dir, f)
            for f in os.listdir(temp_dir)
            if f.endswith('.jpg')
        ])
        
        if not images:
            log(f"  ERROR: No images generated")
            return False
        
        with open(output_pdf, "wb") as f:
            f.write(img2pdf.convert(images))
        
        size_kb = os.path.getsize(output_pdf) // 1024
        log(f"  Flattened: {os.path.basename(output_pdf)} ({size_kb}KB, {len(images)} pages)")
        return True
    finally:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)


def process_book(session, book_id, raw_title, class_name):
    subject = extract_subject_from_title(raw_title)
    log(f"\n{'='*60}")
    log(f"Processing: {class_name} - {raw_title}")
    log(f"Subject: {subject}")
    
    raw_dir = os.path.join(WORKSPACE, "_raw", sanitize(class_name))
    raw_path = os.path.join(raw_dir, f"{sanitize(raw_title)}.pdf")
    
    try:
        # Download
        download_book(session, book_id, raw_path)
        total_pages = get_pdf_page_count(raw_path)
        size_mb = os.path.getsize(raw_path) // (1024 * 1024)
        log(f"  Downloaded: {total_pages} pages, {size_mb}MB")
        
        # Detect chapters
        chapters = detect_chapters_robust(raw_path)
        
        if not chapters:
            log("  No chapters detected, flattening entire book as one file")
            output_dir = os.path.join(WORKSPACE, sanitize(class_name), sanitize(subject))
            os.makedirs(output_dir, exist_ok=True)
            filename = f"{sanitize(subject)} - Full Book.pdf"
            filepath = os.path.join(output_dir, filename)
            flatten_pdf(raw_path, filepath, 1, total_pages)
            return [filepath]
        
        # Split and flatten each chapter
        output_dir = os.path.join(WORKSPACE, sanitize(class_name), sanitize(subject))
        os.makedirs(output_dir, exist_ok=True)
        
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
        
        log(f"  Created {len(created)} chapter files")
        return created
        
    except Exception as e:
        log(f"  ERROR processing book: {e}")
        raise
    finally:
        # Clean up raw PDF
        if os.path.exists(raw_path):
            os.remove(raw_path)
            log(f"  Cleaned up raw PDF")


def main():
    log("="*60)
    log("STBB eBooks Processor Started")
    log("="*60)
    
    session = get_session()
    progress = load_progress()
    
    with open(os.path.join(WORKSPACE, "book_list.json"), "r") as f:
        all_books = json.load(f)
    
    processed_ids = set(progress["processed"])
    total_books = sum(len(v) for v in all_books.values())
    done = 0
    failed = 0
    
    for class_name, books in all_books.items():
        for book in books:
            if book["id"] in processed_ids:
                done += 1
                continue
            
            raw_title = book["title"]
            book_id = book["id"]
            
            try:
                process_book(session, book_id, raw_title, class_name)
                progress["processed"].append(book_id)
                save_progress(progress)
                done += 1
            except Exception as e:
                log(f"FAILED: {raw_title} - {e}")
                progress["failed"].append({
                    "id": book_id,
                    "title": raw_title,
                    "class": class_name,
                    "error": str(e)
                })
                save_progress(progress)
                failed += 1
            
            log(f"Progress: {done}/{total_books} done, {failed} failed")
            time.sleep(2)
    
    log("\n" + "="*60)
    log("PROCESSING COMPLETE")
    log(f"Total: {total_books}, Done: {done}, Failed: {failed}")
    log("="*60)


if __name__ == "__main__":
    main()
