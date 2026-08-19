#!/usr/bin/env python3
"""STBB eBooks Processor - Pure stdlib, no pip dependencies"""

import os
import re
import sys
import json
import time
import shutil
import subprocess
import urllib.request
import urllib.error
from jpegs_to_pdf import jpegs_to_pdf

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


def log(msg):
    print(msg, flush=True)


def get_session():
    """Use urllib with headers"""
    return None  # We'll use urllib directly


def sanitize(name):
    name = re.sub(r'[<>:"/\\|?*]', '', name)
    name = re.sub(r'\s+', ' ', name).strip()
    return name


def load_progress():
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, "r") as f:
            return json.load(f)
    return {"processed": [], "failed": []}


def save_progress(progress):
    with open(PROGRESS_FILE, "w") as f:
        json.dump(progress, f, indent=2)


def url_open(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=120) as resp:
        return resp.read()


def url_open_stream(url, dest_path):
    req = urllib.request.Request(url, headers=HEADERS)
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    with urllib.request.urlopen(req, timeout=300) as resp:
        with open(dest_path, 'wb') as f:
            while True:
                chunk = resp.read(262144)
                if not chunk:
                    break
                f.write(chunk)
    return dest_path


def fetch_class_books(class_id):
    url = f"{BASE_URL}/ebooks/class.php?id={class_id}&medium={MEDIUM}"
    html = url_open(url).decode('utf-8', errors='replace')
    
    books = []
    seen = set()
    
    # Find all book.php?id=NNN links
    for match in re.finditer(r'href="(https://portal\.stbb\.edu\.pk/ebooks/book\.php\?id=(\d+))"', html):
        href = match.group(1)
        book_id = match.group(2)
        if book_id in seen:
            continue
        seen.add(book_id)
        
        # Find the book-title div within 2000 chars after the link
        section = html[match.start():match.start()+2000]
        title_match = re.search(r'<div[^>]*class="book-title"[^>]*>([^<]+)</div>', section)
        if title_match:
            title = title_match.group(1).strip()
        else:
            title = f"Book {book_id}"
        
        books.append({"id": book_id, "title": title})
    
    return books


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


def extract_text_page(pdf_path, page):
    result = subprocess.run(
        ["pdftotext", "-f", str(page), "-l", str(page), "-layout", pdf_path, "-"],
        capture_output=True, text=True
    )
    return result.stdout.strip()


def detect_chapters(pdf_path):
    total = get_pdf_page_count(pdf_path)
    if total == 0:
        return []
    
    unit_num_re = re.compile(r'Unit\s+[-–—]?\s*(\d+)', re.IGNORECASE)
    unit_title_re = re.compile(r'Unit\s+([A-Z][A-Z\s]{3,})', re.IGNORECASE)
    body_stops = re.compile(
        r'^(The|A|An|and|Encourage|Note|Anechoic|Transverse|Crest|Trough|Refracting|Compressed|Stretched|Circular|Incident|Direction|Rigid|Whales|Defect|Display|Light|Lamp|Vibrator|Elastic|banana|girl|Nucleus|Electron|Proton|Karachi|KUNUPP|Note for|Follow the|While teaching)\b',
        re.IGNORECASE
    )
    
    unit_pages = []
    for i in range(1, total + 1):
        txt = extract_text_page(pdf_path, i)
        if not txt:
            continue
        m = unit_num_re.search(txt)
        if m:
            unit_pages.append((i, int(m.group(1)), 'num'))
            continue
        m = unit_title_re.search(txt)
        if m:
            unit_pages.append((i, m.group(1).strip(), 'title'))
    
    # Deduplicate and assign sequential numbers
    chapters = []
    seen_pages = set()
    seen_nums = set()
    seq = 0
    for p, num_or_title, kind in unit_pages:
        if p in seen_pages:
            continue
        seen_pages.add(p)
        if kind == 'num':
            if num_or_title in seen_nums:
                continue
            seen_nums.add(num_or_title)
            seq = num_or_title
            chapters.append({'num': seq, 'page': p, 'title': None})
        else:
            seq += 1
            chapters.append({'num': seq, 'page': p, 'title': num_or_title})
    
    # Extract titles and validate
    valid_chapters = []
    for ch in chapters:
        txt = extract_text_page(pdf_path, ch['page'])
        lines = [l.strip() for l in txt.splitlines() if l.strip()]
        title_parts = []
        for i, line in enumerate(lines):
            m = unit_num_re.search(line)
            if not m:
                continue
            after = unit_num_re.sub('', line).strip(': -').strip()
            if after and not after.isdigit() and len(after) > 2:
                title_parts.append(after)
            for j in range(i + 1, min(i + 4, len(lines))):
                part = lines[j]
                if re.match(r'^\d+$', part):
                    continue
                if len(part) < 2:
                    continue
                if body_stops.match(part):
                    break
                if len(part) > 40:
                    break
                title_parts.append(part)
                if len(title_parts) >= 2:
                    break
            break
        ch['title'] = ' '.join(title_parts).strip() if title_parts else f'Unit {ch["num"]}'
        
        # Validate: reject false positives
        if re.match(r'^(ensuring|Follow the|While teaching|Note for|Encourage students)\b', ch['title'], re.IGNORECASE):
            continue
        if len(ch['title']) < 3:
            continue
        valid_chapters.append(ch)
    
    chapters = valid_chapters
    
    # Recalculate sequential numbers after filtering
    for i, ch in enumerate(chapters):
        ch['num'] = i + 1
    
    # Calculate ranges
    for i in range(len(chapters) - 1):
        chapters[i]['end'] = chapters[i + 1]['page'] - 1
    if chapters:
        chapters[-1]['end'] = total
    
    # Filter tiny chapters
    chapters = [c for c in chapters if (c['end'] - c['page'] + 1) >= 2]
    
    return chapters


def flatten_pdf(input_pdf, output_pdf, start_page, end_page):
    """Flatten PDF pages to JPEG and reassemble using pure Python"""
    temp_dir = output_pdf + "_temp"
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)
    os.makedirs(temp_dir)
    
    try:
        # Convert pages to JPEG
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
        
        # Use pure Python JPEG-to-PDF converter
        jpegs_to_pdf(images, output_pdf)
        
        size_kb = os.path.getsize(output_pdf) // 1024
        log(f"  Flattened: {os.path.basename(output_pdf)} ({size_kb}KB, {len(images)} pages)")
        return True
    finally:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)


def process_book(book_id, raw_title, class_name):
    subject = extract_subject_from_title(raw_title)
    log(f"\n{'='*60}")
    log(f"Processing: {class_name} - {raw_title}")
    log(f"Subject: {subject}")
    
    raw_dir = os.path.join(WORKSPACE, "_raw", sanitize(class_name))
    raw_path = os.path.join(raw_dir, f"{sanitize(raw_title)}.pdf")
    
    try:
        # Download
        url = f"{BASE_URL}/ebooks/pdf_proxy.php?id={book_id}&download=1"
        log(f"  Downloading from {url}")
        url_open_stream(url, raw_path)
        total_pages = get_pdf_page_count(raw_path)
        size_mb = os.path.getsize(raw_path) // (1024 * 1024)
        log(f"  Downloaded: {total_pages} pages, {size_mb}MB")
        
        # Detect chapters
        chapters = detect_chapters(raw_path)
        log(f"  Detected {len(chapters)} chapters")
        for ch in chapters:
            log(f"    Unit {ch['num']}: {ch['title']} (pages {ch['page']}-{ch['end']})")
        
        if not chapters:
            log("  No chapters detected, flattening entire book")
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
            start = ch['page']
            end = ch['end']
            title = sanitize(ch['title'])
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
        log(f"  ERROR: {e}")
        raise
    finally:
        # Clean up raw PDF
        if os.path.exists(raw_path):
            os.remove(raw_path)
            log(f"  Cleaned up raw PDF")


def git_commit_and_push(message):
    """Commit and push changes"""
    try:
        subprocess.run(["git", "add", "-A"], check=True, capture_output=True, text=True)
        subprocess.run(["git", "commit", "-m", message], check=True, capture_output=True, text=True)
        subprocess.run(["git", "push"], check=True, capture_output=True, text=True)
        log(f"  Git: {message}")
    except subprocess.CalledProcessError as e:
        log(f"  Git error: {e.stderr[:200] if e.stderr else str(e)}")


def main():
    log("="*60)
    log("STBB eBooks Processor Started")
    log("="*60)
    
    progress = load_progress()
    
    # First collect all books
    all_books = {}
    for cls in CLASSES:
        books = fetch_class_books(cls["id"])
        all_books[cls["name"]] = books
        time.sleep(1)
    
    # Save book list
    with open(os.path.join(WORKSPACE, "book_list.json"), "w") as f:
        json.dump(all_books, f, indent=2)
    
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
                process_book(book_id, raw_title, class_name)
                progress["processed"].append(book_id)
                save_progress(progress)
                done += 1
                
                # Commit after each book
                subject = extract_subject_from_title(raw_title)
                git_commit_and_push(f"Add {class_name} {subject} chapters")
                
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
