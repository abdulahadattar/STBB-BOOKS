# STBB eBooks Processing - Manual Workflow

## Current Status (as of August 2025)

**Done (Grades 1–6):** 22 books processed — chapter-organized PDFs in `Grade 1/` through `Grade 6/`.
Must be veirfied are properly chapter wise broken and flattened (non ocred)
**Priority: Grades 9–12** — these are the books to process next (from `book_list.json`):
- **Grade 9**: Biology (117), Chemistry (195), Computer Science (121), Islamiyat 9-10 (267), Math (180), English (147), Physics (174), Religious Studies 9-10 (247)
- **Grade 10**: Biology (188), Chemistry (198), Computer Science (204), Math (205), Pakistan Studies (235), Physics (202), English (201)
- **Grade 11**: Biology (219), Chemistry (206), English (203), Math (207), Physics (221)
- **Grade 12**: Biology (228), Chemistry (218), Math (225), Physics (215)

**Preserved (do not touch):** `Grade 9/Physics/` and `Grade 10/Physics/` — old full-book PDFs already exist.

## Manual Workflow (One Book at a Time)

### 1. Download the raw full-book PDF
```bash
# From STBB portal (English medium only):
# https://ebooks.stbb.edu.pk/?medium=English
# Click the book → download the complete PDF
```

### 2. Inspect & split into chapters
```bash
# Option A: Use pdftoppm (fast, no OCR, grayscale 120 DPI)
pdftoppm -gray -r 120 input.pdf output_prefix

# Option B: Use pdfimages if already image-based
pdfimages -j input.pdf output_prefix
```

### 3. Find Unit/Chapter boundaries
- Open the generated images/pages
- Note page numbers where each Unit/Chapter starts
- Create a mapping: `Unit 1 → pages 1-15`, `Unit 2 → pages 16-30`, etc.

### 4. Flatten each chapter (fast path)
```bash
# For each chapter range, extract pages → JPEG → flatten to non-OCR PDF
# Example using pdftoppm + jpegs_to_pdf.py (pure Python, no deps):
pdftoppm -gray -r 120 -f START_PAGE -l END_PAGE input.pdf chapter_X
python jpegs_to_pdf.py chapter_X-*.jpg "Grade N/Subject/Chapter XX - Unit Y.pdf"
```

### 5. Verify
- Open each output PDF → confirm correct pages, readable, no corruption
- Check file size is reasonable (1-10 MB typical)

### 6. Commit & push
```bash
git add "Grade N/Subject/Chapter XX - Unit Y.pdf"
git commit -m "Add Grade N Subject: Chapter XX - Unit Y"
git push
```
**One book = one commit.** Push after each book completes.

### 7. Update progress.json
Add the book ID to the `processed` array.

### 8. Clean up local raw PDF & temp files
```bash
rm input.pdf chapter_X-*.jpg
```

## Hard Rules
- **One book at a time** — never parallel/automated batch scripts (they skip chapters and hang)
- **English medium only** — filter `?medium=English` on the stbb portal
- **Commit after every book** — atomic, verifiable history
- **Delete raw PDFs after processing** — don't commit them
- always keep improving updating if any script is needed
- every tool or script must be used with proper time limit or better approch  (to prevent freeze )
- each pdf chapter must contain unit number and name a proper naming scheme for all pdf


## Tools in this repo
- `jpegs_to_pdf.py` — pure Python JPEG → PDF 
- `book_list.json` — master list of all books by grade
- `progress.json` — tracks processed book IDs

## Why no automation?
Previous scripts (`stbb_*.py`, `start_processing.sh`) would:
- Hang indefinitely on downloads
- Skip chapters without detection
- Produce corrupted PDFs
- Fill disk with raw PDFs
- Fail git pushes silently

**Manual = verified, every chapter, every time.**

## For Kilo Cloud Agent (webhook sessions)
Use **sparse checkout** to avoid downloading all PDFs:
```bash
git clone --filter=blob:none --sparse https://github.com/abdulahadattar/STBB-BOOKS.git
cd STBB-BOOKS
git sparse-checkout init --cone
git sparse-checkout set .
# Process one book...
git sparse-checkout add "Grade 10/Biology"
# Add new chapters...
git commit && git push
git sparse-checkout remove "Grade 10/Biology"
```
keep updating instrutions with new fidnings in the proceess and when when u hit a wall such as storage or an other issue addd comment or open a new issue on github to create a new webhook kilo session to restart the cycle and continue in the loop
