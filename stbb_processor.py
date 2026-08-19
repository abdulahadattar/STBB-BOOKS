#!/usr/bin/env python3
"""STBB PDF Processor - Split chapters and flatten"""

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
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

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

def get_session():
    session = requests.Session()
    session.headers.update(HEADERS)
    return session

def sanitize(name):
    return re.sub(r'[<>:"/\\|?*]', '', name).strip()

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
    if os.path.exists(dest_path):
        return dest_path
    url = f"{BASE_URL}/ebooks/pdf_proxy.php?id={book_id}&download=1"
    resp = session.get(url, timeout=120, stream=True)
    resp.raise_for_status()
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    with open(dest_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=65536):
            if chunk:
                f.write(chunk)
    return dest_path

def get_pdf_info(pdf_path):
    """Get page count and text content from PDF"""
    result = subprocess.run(["pdfinfo", pdf_path], capture_output=True, text=True)
    pages = 0
    for line in result.stdout.splitlines():
        if line.startswith("Pages:"):
            pages = int(line.split(":")[1].strip())
            break
    
    # Extract text with pdftotext
    text_result = subprocess.run(["pdftotext", "-layout", pdf_path, "-"], capture_output=True, text=True)
    return pages, text_result.stdout

def extract_chapters(text, pages):
    """Extract chapter boundaries from PDF text"""
    chapters = []
    
    # Patterns that indicate chapter/unit starts
    # Common patterns in STBB books
    patterns = [
        r'^(?:Chapter|Unit|Lesson|Part|Section)\s+(\d+)',
        r'^(?:Chapter|Unit|Lesson|Part|Section)\s+([A-Z])',
        r'^(\d+\.)\s+[A-Z]',
        r'^CHAPTER\s+(\d+)',
        r'^UNIT\s+(\d+)',
        r'^(?:Chapter|Unit)\s+(\d+):',
    ]
    
    # Split text by pages - we need to know page boundaries
    # pdftotext with -layout doesn't give page numbers directly
    # Let's use pdftotext with page mode
    return chapters

def extract_text_by_page(pdf_path):
    """Extract text content page by page"""
    pages_text = []
    for i in range(1, 1000):
        result = subprocess.run(
            ["pdftotext", "-f", str(i), "-l", str(i), "-layout", pdf_path, "-"],
            capture_output=True, text=True
        )
        text = result.stdout.strip()
        if not text and i > 1:
            break
        pages_text.append(text)
    return pages_text

def detect_chapters(pdf_path):
    """Detect chapters from PDF table of contents and page content"""
    pages_text = extract_text_by_page(pdf_path)
    total_pages = len(pages_text)
    
    if total_pages == 0:
        return []
    
    # Look for table of contents patterns
    chapters = []
    
    # Pattern 1: Look for "Unit X:" or "Chapter X:" on single pages
    chapter_pattern = re.compile(
        r'^\s*(?:Unit|Chapter|Lesson|Part)\s+(\d+)\s*[:\.\-–—]\s*(.+?)(?:\s{2,}|\t|\n|$)',
        re.MULTILINE | re.IGNORECASE
    )
    
    for page_idx, text in enumerate(pages_text):
        matches = chapter_pattern.findall(text)
        for num, title in matches:
            chapters.append({
                "num": int(num),
                "title": title.strip()[:100],
                "page_start": page_idx + 1,
                "page_end": None
            })
    
    # Pattern 2: If no matches, look for bold headings at top of pages
    if not chapters:
        page_start_pattern = re.compile(
            r'^\s*(?:Unit|Chapter)\s+(\d+)',
            re.MULTILINE | re.IGNORECASE
        )
        for page_idx, text in enumerate(pages_text[:min(20, total_pages)]):
            if page_start_pattern.search(text):
                chapters.append({
                    "num": len(chapters) + 1,
                    "title": f"Chapter {len(chapters) + 1}",
                    "page_start": page_idx + 1,
                    "page_end": None
                })
    
    # Pattern 3: If still no chapters, try page count heuristic
    if not chapters and total_pages > 5:
        # Split into equal chunks as fallback
        chunk_size = max(5, total_pages // 5)
        for i in range(0, total_pages, chunk_size):
            chapters.append({
                "num": len(chapters) + 1,
                "title": f"Part {len(chapters) + 1}",
                "page_start": i + 1,
                "page_end": min(i + chunk_size, total_pages)
            })
    
    # Set page ends
    for i in range(len(chapters) - 1):
        chapters[i]["page_end"] = chapters[i + 1]["page_start"] - 1
    if chapters:
        chapters[-1]["page_end"] = total_pages
    
    return chapters

def split_pdf_into_chapters(pdf_path, class_name, subject_name):
    """Split PDF into chapter PDFs using pdftoppm flatten"""
    chapters = detect_chapters(pdf_path)
    if not chapters:
        print(f"  No chapters detected, copying whole book")
        return []
    
    output_dir = os.path.join(WORKSPACE, sanitize(class_name), sanitize(subject_name))
    os.makedirs(output_dir, exist_ok=True)
    
    created_files = []
    for chapter in chapters:
        start = chapter["page_start"]
        end = chapter["page_end"]
        title = sanitize(chapter["title"])
        filename = f"Chapter {chapter['num']:02d} - {title}.pdf"
        filepath = os.path.join(output_dir, filename)
        
        # Flatten by converting to images and back
        flatten_pdf(pdf_path, filepath, start, end)
        created_files.append(filepath)
    
    return created_files

def flatten_pdf(input_pdf, output_pdf, start_page, end_page):
    """Convert PDF pages to images and back to create flattened (non-OCR) PDF"""
    temp_dir = output_pdf + "_temp"
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)
    os.makedirs(temp_dir)
    
    try:
        # Convert pages to images using pdftoppm
        cmd = [
            "pdftoppm",
            "-f", str(start_page),
            "-l", str(end_page),
            "-png",
            "-r", "150",
            input_pdf,
            os.path.join(temp_dir, "page")
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        
        # Collect images and create PDF
        images = sorted([
            os.path.join(temp_dir, f) 
            for f in os.listdir(temp_dir) 
            if f.endswith('.png')
        ])
        
        if images:
            # Use img2pdf to create PDF from images
            with open(output_pdf, "wb") as f:
                f.write(img2pdf.convert(images))
        else:
            raise Exception("No images generated")
    finally:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)

def extract_subject_from_title(title):
    """Extract subject name from book title"""
    # Remove common prefixes and suffixes
    title = re.sub(r'^\ud83d\udcd6\w+\s*', '', title)
    title = re.sub(r'\s*•\s*\d{4}(-\d{2})?$', '', title)
    
    # Remove grade/class suffixes
    patterns = [
        r'\s+(I|II|III|IV|V|VI|VII|VIII|IX|X|XI|XII|Kachi|ECCE)$',
        r'\s+(I|II|III|IV|V|VI|VII|VIII|IX|X|XI|XII|Kachi|ECCE)\s+(I|II|III|IV|V|VI|VII|VIII|IX|X|XI|XII|Kachi|ECCE)$',
    ]
    for pat in patterns:
        title = re.sub(pat, '', title, flags=re.IGNORECASE).strip()
    
    # Common subject mappings
    title_lower = title.lower()
    if 'biology' in title_lower:
        return 'Biology'
    elif 'chemistry' in title_lower or 'chemsitry' in title_lower:
        return 'Chemistry'
    elif 'physics' in title_lower:
        return 'Physics'
    elif 'math' in title_lower:
        return 'Mathematics'
    elif 'english' in title_lower and 'stage' not in title_lower:
        return 'English'
    elif 'secondary stage english' in title_lower:
        return 'Secondary Stage English'
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
        return title.strip()

def process_all_books():
    session = get_session()
    
    # Load book list
    with open(os.path.join(WORKSPACE, "book_list.json"), "r") as f:
        all_books = json.load(f)
    
    # Process each class
    for class_name, books in all_books.items():
        print(f"\n=== Processing {class_name} ===")
        for book in books:
            book_id = book["id"]
            raw_title = book["title"]
            subject = extract_subject_from_title(raw_title)
            
            print(f"\nProcessing: {raw_title} -> Subject: {subject}")
            
            # Download raw PDF
            raw_dir = os.path.join(WORKSPACE, "_raw", sanitize(class_name))
            raw_path = os.path.join(raw_dir, f"{sanitize(raw_title)}.pdf")
            download_book(session, book_id, raw_path)
            
            # Split into chapters
            created = split_pdf_into_chapters(raw_path, class_name, subject)
            print(f"  Created {len(created)} chapter files")
            
            time.sleep(1)

if __name__ == "__main__":
    process_all_books()
