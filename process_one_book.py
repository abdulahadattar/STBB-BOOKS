#!/usr/bin/env python3
"""Process ONE book at a time with strict timeouts and verification"""

import os
import sys
import json
import re
import subprocess
import urllib.request
import urllib.error
import time
import shutil

WORKSPACE = "/workspace/4fba1b35-c093-4694-aa80-9a73b48e2a0f/sessions/agent_84289d02-76d0-4c73-9933-d3f6f6db2218/STBB-BOOKS"
BASE_URL = "https://portal.stbb.edu.pk"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


def log(msg):
    print(msg, flush=True)


def sanitize(name):
    name = re.sub(r'[<>:"/\\|?*]', '', name)
    name = re.sub(r'\s+', ' ', name).strip()
    return name


def run_cmd(cmd, timeout=120, check=True):
    """Run command with timeout"""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=check
        )
        return result
    except subprocess.TimeoutExpired:
        log(f"  TIMEOUT: {' '.join(cmd)}")
        return None
    except subprocess.CalledProcessError as e:
        log(f"  ERROR: {' '.join(cmd)} -> {e.stderr[:200] if e.stderr else e}")
        return None


def download_pdf(book_id, title, class_name):
    raw_dir = os.path.join(WORKSPACE, "_raw", sanitize(class_name))
    os.makedirs(raw_dir, exist_ok=True)
    raw_path = os.path.join(raw_dir, f"{sanitize(title)}.pdf")
    
    if os.path.exists(raw_path) and os.path.getsize(raw_path) > 10000:
        log(f"  Raw PDF already exists: {raw_path}")
        return raw_path
    
    url = f"{BASE_URL}/ebooks/pdf_proxy.php?id={book_id}&download=1"
    log(f"  Downloading from {url}")
    
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            with open(raw_path, 'wb') as f:
                while True:
                    chunk = resp.read(262144)
                    if not chunk:
                        break
                    f.write(chunk)
    except Exception as e:
        log(f"  Download failed: {e}")
        if os.path.exists(raw_path):
            os.remove(raw_path)
        return None
    
    size_mb = os.path.getsize(raw_path) / (1024 * 1024)
    log(f"  Downloaded: {size_mb:.1f}MB")
    return raw_path


def get_pdf_page_count(pdf_path):
    result = run_cmd(["pdfinfo", pdf_path], timeout=30)
    if not result:
        return 0
    for line in result.stdout.splitlines():
        if line.startswith("Pages:"):
            return int(line.split(":")[1].strip())
    return 0


def extract_text_page(pdf_path, page):
    result = run_cmd(
        ["pdftotext", "-f", str(page), "-l", str(page), "-layout", pdf_path, "-"],
        timeout=30
    )
    return result.stdout.strip() if result else ""


def extract_chapter_title(txt, page):
    """Extract chapter/unit title from page text"""
    lines = [l.strip() for l in txt.splitlines() if l.strip()]
    title_parts = []
    
    def try_extract(marker_re, prefix_re, start_idx):
        """Try to extract title starting from marker at start_idx"""
        for i in range(start_idx, len(lines)):
            line = lines[i]
            m = re.search(marker_re, line, re.IGNORECASE)
            if not m:
                continue
            
            # Find number line (could be same line or next 1-2 lines)
            num_line = i
            if not re.search(r'\d+', m.group(0)):
                for j in range(i + 1, min(i + 3, len(lines))):
                    if re.match(r'^\s*\d+', lines[j]):
                        num_line = j
                        break
                else:
                    continue
            
            # Extract text from marker line (before number line)
            marker_text = re.sub(prefix_re, '', line, flags=re.IGNORECASE).strip(': -').strip()
            if marker_text and len(marker_text) > 2:
                title_parts.append(marker_text)
            
            # Collect title text between marker line and number line
            for k in range(i + 1, num_line):
                part = lines[k]
                if len(part) < 3:
                    continue
                title_parts.append(part)
            
            # Check if number line has text after number
            after_num = re.sub(r'^\s*\d+\s*', '', lines[num_line]).strip()
            if after_num and len(after_num) > 2:
                title_parts.append(after_num)
            
            # Look at next few lines for more title text
            for j in range(num_line + 1, min(num_line + 4, len(lines))):
                part = lines[j]
                if re.match(r'^\d+$', part):
                    continue
                if len(part) < 3:
                    continue
                if re.search(r'(Major Concept|In this Unit|Introduction|Ø|Time Allocation)', part, re.IGNORECASE):
                    break
                if len(part) > 60:
                    break
                title_parts.append(part)
                if len(title_parts) >= 3:
                    break
            return True
        return False
    
    # Try Chapter pattern first
    if not try_extract(r'Chapter', r'Chapter\s*', 0):
        # Try Unit pattern (use word boundary to avoid matching "Units")
        if not try_extract(r'Unit\b', r'Unit\s*', 0):
            # Fallback for Time Allocation pages: extract title from first lines
            for i, line in enumerate(lines):
                if re.search(r'Time Allocation', line, re.IGNORECASE):
                    # Collect lines before Time Allocation
                    for k in range(i):
                        part = lines[k]
                        if len(part) < 3:
                            continue
                        if re.search(r'(Major Concept|In this Unit|Introduction|Ø)', part, re.IGNORECASE):
                            break
                        if len(part) > 60:
                            break
                        title_parts.append(part)
                    break
    
    title = ' '.join(title_parts).strip() if title_parts else f'Unit {page}'
    title = re.sub(r'\s+', ' ', title).strip()
    title = title.strip(': -')
    return title if len(title) >= 2 else f'Unit {page}'


def page_has_marker(txt):
    """Check if page has chapter/unit marker, handling multi-line layouts"""
    if re.search(r'(?:Chapter|Unit)\s+[-–—]?\s*\d+', txt, re.IGNORECASE | re.DOTALL):
        return True
    if re.search(r'Time Allocation', txt, re.IGNORECASE):
        return True
    lines = txt.splitlines()
    for i, line in enumerate(lines):
        if re.search(r'Chapter\s+$', line, re.IGNORECASE):
            for j in range(i + 1, min(i + 3, len(lines))):
                if re.match(r'^\s*\d+', lines[j]):
                    return True
        if re.search(r'Unit\s+[-–—]?\s*$', line, re.IGNORECASE):
            for j in range(i + 1, min(i + 3, len(lines))):
                if re.match(r'^\s*\d+', lines[j]):
                    return True
    return False


def is_toc_page(txt):
    """Check if page is a table of contents (contains multiple chapter markers)"""
    chapters = re.findall(r'(?:Chapter|Unit)\s+[-–—]?\s*\d+', txt, re.IGNORECASE)
    if len(chapters) >= 3:
        return True
    lines = txt.splitlines()
    count = 0
    for i, line in enumerate(lines):
        if re.search(r'(?:Chapter|Unit)', line, re.IGNORECASE):
            for j in range(i + 1, min(i + 3, len(lines))):
                if re.match(r'^\s*\d+', lines[j]):
                    count += 1
                    break
    return count >= 3


def detect_chapters(pdf_path):
    total = get_pdf_page_count(pdf_path)
    if total == 0:
        return []
    
    marker_pages = []
    for i in range(1, total + 1):
        txt = extract_text_page(pdf_path, i)
        if not txt:
            continue
        if page_has_marker(txt):
            if is_toc_page(txt):
                continue
            marker_pages.append(i)
    
    if not marker_pages:
        return []
    
    filtered = []
    for p in marker_pages:
        if not filtered or p - filtered[-1] > 2:
            filtered.append(p)
    marker_pages = filtered
    
    chapters = []
    for idx, p in enumerate(marker_pages):
        txt = extract_text_page(pdf_path, p)
        title = extract_chapter_title(txt, idx + 1)
        end_page = marker_pages[idx + 1] - 1 if idx + 1 < len(marker_pages) else total
        chapters.append({
            'num': idx + 1,
            'page': p,
            'end': end_page,
            'title': title
        })
    
    chapters = [c for c in chapters if (c['end'] - c['page'] + 1) >= 2]
    
    for i, ch in enumerate(chapters):
        ch['num'] = i + 1
    
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
        result = run_cmd(cmd, timeout=120, check=False)
        if not result or result.returncode != 0:
            log(f"  pdftoppm error: {result.stderr[:200] if result else 'timeout'}")
            return False
        
        images = sorted([
            os.path.join(temp_dir, f)
            for f in os.listdir(temp_dir)
            if f.endswith('.jpg')
        ])
        
        if not images:
            log("  No images generated")
            return False
        
        cmd = ["python3", os.path.join(WORKSPACE, "jpegs_to_pdf.py"), output_pdf] + images
        result = run_cmd(cmd, timeout=120, check=False)
        if not result or result.returncode != 0:
            log(f"  jpegs_to_pdf error: {result.stderr[:200] if result else 'timeout'}")
            return False
        
        size_kb = os.path.getsize(output_pdf) // 1024
        log(f"  Flattened: {os.path.basename(output_pdf)} ({size_kb}KB, {len(images)} pages)")
        return True
    finally:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)


def process_book(book_id, title, class_name, subject):
    log(f"\n{'='*60}")
    log(f"Processing: {class_name} - {title}")
    log(f"Subject: {subject}")
    
    raw_path = download_pdf(book_id, title, class_name)
    if not raw_path:
        return False
    
    try:
        total_pages = get_pdf_page_count(raw_path)
        log(f"  Total pages: {total_pages}")
        
        chapters = detect_chapters(raw_path)
        log(f"  Detected {len(chapters)} chapters")
        for ch in chapters:
            log(f"    Chapter {ch['num']:02d}: {ch['title']} (pages {ch['page']}-{ch['end']})")
        
        if not chapters:
            log("  No chapters detected, flattening entire book")
            output_dir = os.path.join(WORKSPACE, sanitize(class_name), sanitize(subject))
            os.makedirs(output_dir, exist_ok=True)
            filename = f"{sanitize(subject)} - Full Book.pdf"
            filepath = os.path.join(output_dir, filename)
            
            if os.path.exists(filepath) and os.path.getsize(filepath) > 10000:
                log(f"  Already exists: {filename}")
                return True
            
            success = flatten_pdf(raw_path, filepath, 1, total_pages)
            return success
        
        output_dir = os.path.join(WORKSPACE, sanitize(class_name), sanitize(subject))
        os.makedirs(output_dir, exist_ok=True)
        
        created = []
        for ch in chapters:
            start = ch['page']
            end = ch['end']
            title_text = sanitize(ch['title'])
            filename = f"Chapter {ch['num']:02d} - {title_text}.pdf"
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
        return len(created) > 0
        
    except Exception as e:
        log(f"  ERROR: {e}")
        return False
    finally:
        if os.path.exists(raw_path):
            os.remove(raw_path)
            log(f"  Cleaned up raw PDF")


if __name__ == "__main__":
    if len(sys.argv) < 5:
        print("Usage: process_one_book.py <book_id> <title> <class_name> <subject>")
        sys.exit(1)
    
    book_id = sys.argv[1]
    title = sys.argv[2]
    class_name = sys.argv[3]
    subject = sys.argv[4]
    
    success = process_book(book_id, title, class_name, subject)
    sys.exit(0 if success else 1)
