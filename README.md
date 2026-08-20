# STBB eBooks Processing - README

## Current Status
- Old Physics PDFs are RESTORED and SAFE in the repo
- New chapter-organized PDFs are being created alongside them
- Script is ready but NOT running (needs manual execution)

## Files Ready
- `stbb_one.py` - Main processor script
- `jpegs_to_pdf.py` - Pure-Python PDF builder
- `start_processing.sh` - Easy start script
- `progress.json` - Tracks which books are done
- `book_list.json` - List of all books to process

## How to Start (YOU MUST RUN THIS)

### Option 1: Direct Python
```bash
cd /workspace/4fba1b35-c093-4694-aa80-9a73b48e2a0f/sessions/agent_fb1dc3f1-092e-4f66-aa62-7dbf088f2b51
python3 stbb_one.py
```

### Option 2: Bash Script
```bash
cd /workspace/4fba1b35-c093-4694-aa80-9a73b48e2a0f/sessions/agent_fb1dc3f1-092e-4f66-aa62-7dbf088f2b51
chmod +x start_processing.sh
./start_processing.sh
```

## What the Script Does
1. Downloads one PDF at a time from STBB website
2. Inspects every page to find Unit/Chapter markers
3. Splits into chapters using pdftoppm (grayscale, 120 DPI, quality 80)
4. Creates non-OCR flattened PDFs
5. Verifies each chapter file
6. Commits to git after each book
7. Pushes each grade to GitHub with automatic retries
8. Deletes raw PDFs after processing
9. NEVER touches old Physics PDFs

## If Git Push Fails (HTTP 413/502)
The old Physics PDFs are large and may cause push failures. If this happens:

### Temporary Solution:
```bash
# Move old Physics PDFs out temporarily
mkdir -p /tmp/old_physics
mv Grade\ 9/Physics\ Grade\ 9* /tmp/old_physics/
mv Grade\ 10/Physics\ Grade\ 10* /tmp/old_physics/
mv Grade\ 11/Physics\ Grade\ 11* /tmp/old_physics/
mv Grade\ 12/Physics\ Grade\ 12* /tmp/old_physics/

# Push new chapters
git add -A
git commit -m "Add new chapters"
git push

# Restore old Physics PDFs
mv /tmp/old_physics/* .
git add -A
git commit -m "Restore old Physics PDFs"
git push
```

## Progress Tracking
- `progress.json` - Contains list of processed book IDs
- Script automatically skips already-processed books
- If interrupted, just re-run the script

## Known Issues
- Some chapter titles may be generic ("Unit 2") due to PDF text extraction limits
- Git push may fail due to large file sizes (retry logic handles this)
- Some books may have unusual chapter structures

## Time Estimate
- ~5-10 minutes per book (download + processing + push)
- 63 books total = ~5-10 hours
- Script runs unattended once started

## Monitoring
Check progress with:
```bash
tail -f process.log  # If running in background
cat progress.json    # See what's done
ls -la Grade*/       # See created chapters
```
