#!/bin/bash
# STBB Processor - Easy Start Script
# Run this from the workspace directory

cd /workspace/4fba1b35-c093-4694-aa80-9a73b48e2a0f/sessions/agent_fb1dc3f1-092e-4f66-aa62-7dbf088f2b51

echo "=========================================="
echo "STBB eBooks Processor"
echo "=========================================="
echo ""

# Check if python3 is available
if ! command -v python3 &> /dev/null; then
    echo "ERROR: python3 not found"
    exit 1
fi

# Check if required tools are available
for tool in pdfinfo pdftotext pdftoppm git; do
    if ! command -v $tool &> /dev/null; then
        echo "WARNING: $tool not found - processing may fail"
    else
        echo "✓ $tool found"
    fi
done

echo ""
echo "Starting processor..."
echo "Press Ctrl+C to stop"
echo ""

# Run the processor
python3 stbb_one.py

echo ""
echo "Processor stopped."
echo "Check process.log for details if it crashed."
