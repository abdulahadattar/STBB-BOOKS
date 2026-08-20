# STBB eBooks Processing - README

## Current Status
- New chapter-organized PDFs are being created alongside them
- Script is ready but NOT running (needs manual execution)

## Files Ready (remove batch scirpts then update readme)
- `stbb_one.py` - Main processor script
- `jpegs_to_pdf.py` - Pure-Python PDF builder
- `start_processing.sh` - Easy start script
- `progress.json` - Tracks which books are done
- `book_list.json` - List of all books to process

## How to Start (YOU MUST RUN THIS)

## What the Script Does
1. Downloads one PDF at a time from STBB website(if mulit agent then assign each grade to each agent to process one book at time manully not blind scipit that gets stuck and skips chapters miss 
   https://ebooks.stbb.edu.pk/?medium=English (only english curriculum books)
3. Inspects every page to find Unit/Chapter markers
4. Splits into chapters using any fastest solution you find (grayscale, 120 DPI, quality 80)
   try not to use convert jpg then into pdf it is time consuming find faster way to faltten and just remove ocr text 
6. Creates non-OCR flattened PDFs
7. Verifies each chapter file
8. Commits to git after each book
9. Pushes each grade to GitHub with automatic retries
10. Deletes raw PDFs after processing
11. NEVER touches old Physics PDFs

## If Git Push Fails (HTTP 413/502)
The old Physics PDFs are large and may cause push failures. If this happens:


# Push new chapters
git add -A
git commit -m "Add new chapters"
git push



## Progress Tracking
- `progress.json` - Contains list of processed book IDs
- Script automatically skips already-processed books
- If interrupted, just re-run the script

## Known Issues
- Some chapter titles may be generic ("Unit 2") due to PDF text extraction limits
- Git push may fail due to large file sizes (retry logic handles this)
- Some books may have unusual chapter structures
- dont use unattended scripts they some time get stuck stops try to use some sort of loop or way to keep checking progress of process manully instead of blind script
- remove batch process scripts dont use them

## Time Estimate
- ~5-10 minutes per book (download + processing + push)
- 63 books total = ~5-10 hours

## Monitoring
Check progress
