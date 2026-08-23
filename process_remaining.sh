#!/bin/bash
# Process remaining books one at a time
cd /workspace/4fba1b35-c093-4694-aa80-9a73b48e2a0f/sessions/agent_84289d02-76d0-4c73-9933-d3f6f6db2218/STBB-BOOKS

BOOKS=(
  "198|Chemsitry X|Grade 10|Chemistry"
  "204|Computer Science X|Grade 10|Computer Science"
  "235|Pak Studies X|Grade 10|Pakistan Studies"
  "205|Math X|Grade 10|Mathematics"
  "201|Secondary Stage English X|Grade 10|Secondary Stage English"
  "267|Islamiyat IX-X|Grade 10|Islamiyat"
  "219|Biology XI|Grade 11|Biology"
  "206|Chemistry XI|Grade 11|Chemistry"
  "203|English XI|Grade 11|English"
  "207|Math XI|Grade 11|Mathematics"
  "221|Physics XI|Grade 11|Physics"
  "228|Biology XII|Grade 12|Biology"
  "218|Chemistry XII|Grade 12|Chemistry"
  "225|Math XII|Grade 12|Mathematics"
  "215|Physics XII|Grade 12|Physics"
  "117|Biology IX|Grade 9|Biology"
  "195|Chemsitry IX|Grade 9|Chemistry"
  "121|Computer Science IX|Grade 9|Computer Science"
  "180|Math IX|Grade 9|Mathematics"
  "147|My English IX|Grade 9|English"
  "174|Physics IX|Grade 9|Physics"
  "247|Religious Studies IX-X|Grade 9|Islamiyat"
)

for book in "${BOOKS[@]}"; do
  IFS='|' read -r id title class subject <<< "$book"
  echo "=========================================="
  echo "Processing: $class - $title (ID: $id)"
  echo "=========================================="
  
  if python3 process_one_book.py "$id" "$title" "$class" "$subject"; then
    echo "SUCCESS: $class $title"
    git add -A
    git commit -m "Add $class $title chapters"
    git pull --rebase origin main
    git push
    echo "188" >> /tmp/processed_ids.txt
    echo "$id" >> .tmp_processed
  else
    echo "FAILED: $class $title"
    echo "$id" >> .tmp_failed
  fi
  
  echo ""
done

echo "=========================================="
echo "Processing complete"
echo "=========================================="
