# STBB eBooks Processing — Self-Healing Webhook Workflow

## How It Works

A GitHub issue triggers a Kilo webhook session. That session downloads **one** book, splits it into chapter PDFs, verifies them, pushes them, and then triggers the next session. If anything goes wrong, it documents the exact blocker and exits — no infinite loops.

---

## What Each Session Must Do (Step by Step)

### 1. Pick ONE book
- Read `progress.json` → `processed` array
- Read `book_list.json` → pick the next unprocessed book from the Grades 9–12 priority list
- **Only one book per session. No exceptions.**

### 2. Download the raw PDF
- URL pattern: `https://portal.stbb.edu.pk/ebooks/pdf_proxy.php?id=<BOOK_ID>&download=1`
- Save to `/tmp/<book_id>.pdf`
- Verify download: `pdfinfo /tmp/<book_id>.pdf` → must report total pages
- If 404/rate-limited → mark `blocked:portal` in `progress.json`, open GitHub issue, **exit**

### 3. Find chapter boundaries
- Run: `pdftotext -f <page> -l <page> -layout /tmp/<book_id>.pdf -` for each page
- Look for **either**:
  - `Chapter N` or `Unit N` markers
  - **OR** pages with `Time Allocation` (STBB unit info pages)
- **Critical:** Record exact start/end page for every chapter
- **Do NOT guess.** If boundaries are unclear → mark `blocked:split`, open issue, **exit**

### 4. Split and flatten each chapter
For each chapter page range:
```bash
pdftoppm -gray -r 120 -f <start> -l <end> /tmp/<book_id>.pdf chapter_prefix
python jpegs_to_pdf.py chapter_prefix-*.jpg "Grade N/Subject/Chapter NN - <Unit Title>.pdf"
```
- Output must be **non-OCR PDF**: no text layer, just images
- `jpegs_to_pdf.py` is the approved tool — it embeds JPEGs directly, no re-encoding
- **Do NOT use** `stbb_one.py`, `stbb_final.py`, `stbb_pure.py`, `stbb_processor.py`, `start_processing.sh` — they freeze and produce corrupt output

### 5. Verify EVERY chapter PDF
```bash
pdfinfo "Grade N/Subject/Chapter NN - <Unit Title>.pdf"   # must have pages > 0
pdftotext "Grade N/Subject/Chapter NN - <Unit Title>.pdf" - | head -5  # must be EMPTY (no OCR)
```
- If `pdfinfo` fails or pages = 0 → **corrupt**, do not commit
- If `pdftotext` returns text → **has OCR layer**, re-flatten
- Open the PDF visually if possible — confirm it renders
- **All chapters must verify before any commit**

### 6. Commit and push
```bash
git add "Grade N/Subject/Chapter NN - <Unit Title>.pdf"
git commit -m "Add Grade N Subject: Chapter NN - <Unit Title>"
git pull --rebase origin main
git push origin main
```
- One commit per chapter is ideal, but at minimum: one commit per book
- If push fails with HTTP 413/502 → split into smaller commits, retry
- If push fails for other reasons → mark `blocked:git`, open issue, **exit**

### 7. Update progress.json
```json
{
  "processed": ["188", "198", ...],
  "failed": [...],
  "blocked": [...]
}
```
- Append book ID to `processed`
- Commit and push `progress.json`

### 8. Clean up
```bash
rm /tmp/<book_id>.pdf chapter_prefix-*.jpg
```

### 9. Trigger next session
- Comment on the triggering issue: `✅ Completed Grade N Subject. Next: <next book>`
- If there are more unprocessed books → open a new issue for the next book with label `auto-trigger`
- That new issue triggers the next Kilo webhook session automatically
- **If no books remain → post "All done" and close the chain**

---

## Self-Healing: What Each Session Learns

Each session must leave a **learning trail** in `progress.json` and/or the issue comment so the next session avoids wasted effort.

### What to document
| Field | Purpose |
|-------|---------|
| `blocker` | Exact failure mode (`blocked:split`, `blocked:pdf`, `blocked:portal`, `blocked:tool`, `blocked:git`) |
| `detail` | What was tried, what pages were inspected, exact error |
| `avoid` | **What the next session should NOT do** (e.g. "Do not use `pdftotext` on pages 5-22; they are images only") |
| `use_instead` | **What worked** (e.g. "Use `pdfimages -j` for this book; it's image-based") |

### Example learning entry
```json
{
  "id": "198",
  "title": "Chemsitry X",
  "grade": "10",
  "subject": "Chemistry",
  "blocker": "blocked:split",
  "issue": 42,
  "detail": "Pages 5,23,37 are unit title pages without 'Chapter' markers. pdftotext extracts garbage.",
  "avoid": "Do not use text-based chapter detection on pages 1-60",
  "use_instead": "Manually specify ranges: Unit 1=5-22, Unit 2=23-36, Unit 3=37-59",
  "timestamp": "2026-08-23T02:00:00Z"
}
```

### How next session uses it
- Read `progress.json` → `blocked` array
- Read the linked GitHub issue → full discussion
- **Apply the lesson** → skip the failed approach, use the working one

---

## Fixing Corrupt Existing Uploads

Many current chapter PDFs in `Grade 10/Chemistry/`, `Grade 10/Biology/`, etc. are **corrupt or have OCR layers**. Each session must:

1. Scan its target directory before adding new files:
   ```bash
   for f in "Grade N/Subject/"*.pdf; do
     pdfinfo "$f" || echo "CORRUPT: $f"
     pdftotext "$f" - | head -1 | grep -q . && echo "HAS_OCR: $f"
   done
   ```
2. If corrupt/OCR files exist → **re-upload the correct version**
3. Git will track the replacement; old corrupt version is overwritten in history

**Priority:** Fix corrupt files in the book you're currently processing before adding new books.

---

## Hard Rules (Non-Negotiable)

| Rule | Why |
|------|-----|
| **One book per session** | Prevents 4+ hour hangs |
| **Exit after one book** | Success or documented blocker — no retry loops |
| **Verify before commit** | Corrupt PDFs waste hours and bandwidth |
| **No forbidden scripts** | `stbb_*.py`, `start_processing.sh` freeze forever |
| **Issue before exit** | Next session needs context |
| **Pass learning forward** | `progress.json` + issue comments = institutional memory |
| **Never touch Grade 9/Physics or Grade 10/Physics** | Old full-book PDFs are preserved |
| **English medium only** | Download URLs must use `?medium=English` |

---

## Session Pseudocode

```python
def session(issue_number):
    issue = github.get_issue(issue_number)
    book = get_next_book(progress.json)

    # Download
    raw = download(f"https://portal.stbb.edu.pk/ebooks/pdf_proxy.php?id={book.id}&download=1")
    if not raw:
        document_blocker(book, "blocked:portal", "Download failed")
        exit()

    # Split
    ranges = find_chapters(raw)
    if not ranges:
        document_blocker(book, "blocked:split", "Cannot detect chapter boundaries", detail=pages_tried)
        exit()

    # Flatten + verify + commit per chapter
    for start, end, title in ranges:
        flatten(raw, start, end, title)
        verify_pdf(output_path)
        git_add_commit_push(output_path, book, title)

    # Done
    mark_processed(book.id)
    issue.comment(f"✅ Completed {book.title} — {len(ranges)} chapters")
    trigger_next_issue(book)
    exit()
```

---

## Why This Doesn't Get Stuck

| Old Problem | New Fix |
|-------------|---------|
| Script loops forever | Session = single book, then exit |
| Corrupt PDFs uploaded | Verify before commit; re-upload corrupt ones |
| Hidden state lost on crash | `progress.json` + GitHub issues = persistent state |
| No learning between sessions | `avoid` / `use_instead` fields in `progress.json` |
| Disk fills with raw PDFs | Delete raw PDF after each chapter |
| Chemistry X bad titles | Document exact page ranges, mark `blocked:split`, next session uses manual ranges |
| Next session has no context | Issue comments + `progress.json` contain full handoff |

---

## Quick Reference

| Task | Command |
|------|---------|
| See all unprocessed books | `cat book_list.json \| jq '.["Grade 9"]'` |
| Check progress | `cat progress.json \| jq` |
| Find blocked books | `cat progress.json \| jq '.blocked'` |
| Verify PDFs in directory | `for f in *.pdf; do pdfinfo "$f" \|\& grep Pages; done` |
| Check for OCR layer | `pdftotext file.pdf - \| head -5` (empty = good) |
| Manually trigger next | Open issue titled "Process: <book>" with label `auto-trigger` |

---

**Every session either succeeds and triggers the next, or leaves a precise trail for the next. No session loops forever.**
