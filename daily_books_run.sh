#!/bin/bash
# Daily auto-run: generate one books channel video + open on desktop.
# Runs via macOS launchd — see com.aivideo.books.plist.
#
# Triggered Tue + Fri at 08:30 Taiwan time (after UTC 0:00 Imagen quota reset).
# If successful, opens the generated mp4 so the user sees it when they
# wake up / unlock their Mac.

PROJECT_DIR="/Users/arlong/Projects/AIvideo"
PYTHON="/Users/arlong/.pyenv/versions/3.10.11/bin/python3"
LOG_DIR="$PROJECT_DIR/logs"
mkdir -p "$LOG_DIR"

LOG_FILE="$LOG_DIR/books_$(date +%Y%m%d).log"

cd "$PROJECT_DIR" || exit 1
export PATH="/opt/homebrew/bin:/Users/arlong/.pyenv/bin:$PATH"
export IMAGEIO_FFMPEG_EXE="/opt/homebrew/bin/ffmpeg"
eval "$(pyenv init -)" 2>/dev/null || true

echo "=== Books v5 run started: $(date) ===" >> "$LOG_FILE"

# Pre-flight health check (same 9 checks crime uses)
"$PYTHON" "$PROJECT_DIR/health_check.py" --verbose >> "$LOG_FILE" 2>&1
HEALTH_EXIT=$?
if [ $HEALTH_EXIT -ne 0 ]; then
    echo "=== Pre-flight health check FAILED: $(date) ===" >> "$LOG_FILE"
    echo "Aborting books run — see Telegram alert" >> "$LOG_FILE"
    exit 1
fi

# Pre-flight: verify Imagen quota is actually available before burning
# 15-20 min on TTS + script just to fail at the first illustration.
echo "Checking Imagen quota availability..." >> "$LOG_FILE"
"$PYTHON" -c "
import os, sys
os.environ.setdefault('IMAGEIO_FFMPEG_EXE', '/opt/homebrew/bin/ffmpeg')
os.chdir('$PROJECT_DIR')
from dotenv import load_dotenv; load_dotenv()
from google import genai
client = genai.Client(api_key=os.getenv('GEMINI_API_KEY'))
try:
    r = client.models.generate_images(
        model='imagen-4.0-fast-generate-001',
        prompt='quota test — a simple blue circle on white background',
        config={'number_of_images': 1, 'aspect_ratio': '1:1'},
    )
    if r.generated_images:
        print('Imagen quota OK — proceeding with books render')
        sys.exit(0)
    print('Imagen returned no image — quota may not be reset')
    sys.exit(1)
except Exception as e:
    if '429' in str(e) or 'RESOURCE_EXHAUSTED' in str(e):
        print(f'Imagen quota NOT yet reset: {str(e)[:150]}')
    else:
        print(f'Imagen API error: {str(e)[:150]}')
    sys.exit(1)
" >> "$LOG_FILE" 2>&1

if [ $? -ne 0 ]; then
    echo "=== Imagen quota NOT available — aborting books run: $(date) ===" >> "$LOG_FILE"
    "$PYTHON" -c "
from telegram_notify import _send_raw
_send_raw('⏸️ [AIvideo Books] 跳過本次 — Imagen 配額尚未重置\n下次嘗試: 下個排程日 (Tue/Fri 15:30)\n或手動跑: python generate_books.py --auto')
" 2>/dev/null
    rm -f "$MARKER_FILE" 2>/dev/null
    exit 0
fi

# Record the timestamp before the run so we can find output dirs created AFTER this point
MARKER_FILE="$LOG_DIR/.books_run_marker_$$"
touch "$MARKER_FILE"

# Run v5 books with auto topic pick (strict Imagen mode, no fallback)
"$PYTHON" "$PROJECT_DIR/generate_books.py" --auto >> "$LOG_FILE" 2>&1
EXIT_CODE=$?
echo "=== Books v5 run finished: $(date) | exit=$EXIT_CODE ===" >> "$LOG_FILE"

if [ $EXIT_CODE -eq 0 ]; then
    # Find the newest books output dir created during this run
    LATEST_DIR=""
    for dir in "$PROJECT_DIR/output"/*books*/; do
        if [ -d "$dir" ] && [ "$dir" -nt "$MARKER_FILE" ] && [ -f "$dir/final_zh.mp4" ]; then
            LATEST_DIR="$dir"
        fi
    done
    rm -f "$MARKER_FILE"

    if [ -n "$LATEST_DIR" ] && [ -f "$LATEST_DIR/final_zh.mp4" ]; then
        echo "Opening result: $LATEST_DIR/final_zh.mp4" >> "$LOG_FILE"
        # Open mp4 in default player — user sees when Mac is unlocked.
        /usr/bin/open "$LATEST_DIR/final_zh.mp4"
    else
        echo "[WARN] Render exit 0 but no final_zh.mp4 found in new books dir" >> "$LOG_FILE"
    fi
else
    # generate_books.py has its own Telegram crash handler; we just log here.
    rm -f "$MARKER_FILE"
    echo "[FAIL] Books render exited $EXIT_CODE — Telegram alert already fired by generate_books.py" >> "$LOG_FILE"
fi

# Keep only last 60 days of books logs
find "$LOG_DIR" -name "books_*.log" -mtime +60 -delete 2>/dev/null
