#!/bin/bash
# Daily auto-run: books channel video generation + resume.
# Runs via macOS launchd — see com.aivideo.books.plist.
#
# Flow:
#   1. Health check (9 items)
#   2. Imagen quota pre-flight test
#   3. Check for INCOMPLETE renders (resume_books.py) → finish them first
#   4. If no incomplete + quota remains → start a NEW video (generate_books.py)
#   5. Open result on desktop + Telegram notify
#
# This ensures partially-generated videos (hit quota mid-run) get
# completed before starting new ones. Quota is never wasted.

PROJECT_DIR="/Users/arlong/Projects/AIvideo"
PYTHON="/Users/arlong/.pyenv/versions/3.10.11/bin/python3"
LOG_DIR="$PROJECT_DIR/logs"
mkdir -p "$LOG_DIR"

LOG_FILE="$LOG_DIR/books_$(date +%Y%m%d).log"

cd "$PROJECT_DIR" || exit 1
export PATH="/opt/homebrew/bin:/Users/arlong/.pyenv/bin:$PATH"
export IMAGEIO_FFMPEG_EXE="/opt/homebrew/bin/ffmpeg"
eval "$(pyenv init -)" 2>/dev/null || true

echo "=== Books daily run started: $(date) ===" >> "$LOG_FILE"

# ── Step 1: Health check ─────────────────────────────────────────────────
"$PYTHON" "$PROJECT_DIR/health_check.py" --verbose >> "$LOG_FILE" 2>&1
if [ $? -ne 0 ]; then
    echo "=== Health check FAILED: $(date) ===" >> "$LOG_FILE"
    exit 1
fi

# ── Step 2: Imagen quota pre-flight ──────────────────────────────────────
echo "Checking Imagen quota..." >> "$LOG_FILE"
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
        print('Imagen quota OK')
        sys.exit(0)
    sys.exit(1)
except Exception as e:
    if '429' in str(e) or 'RESOURCE_EXHAUSTED' in str(e):
        print(f'Imagen quota NOT reset: {str(e)[:100]}')
    else:
        print(f'Imagen error: {str(e)[:100]}')
    sys.exit(1)
" >> "$LOG_FILE" 2>&1

if [ $? -ne 0 ]; then
    echo "=== Imagen quota unavailable — skipping: $(date) ===" >> "$LOG_FILE"
    "$PYTHON" -c "
from telegram_notify import _send_raw
_send_raw('⏸️ [Books] Imagen 配額未重置，今天跳過')
" 2>/dev/null
    exit 0
fi

# ── Step 3: Resume incomplete renders first ──────────────────────────────
echo "Checking for incomplete renders..." >> "$LOG_FILE"
"$PYTHON" "$PROJECT_DIR/resume_books.py" >> "$LOG_FILE" 2>&1
RESUME_EXIT=$?

if [ $RESUME_EXIT -eq 0 ]; then
    # Check if resume actually completed a video (vs "no incomplete found")
    if grep -q "Complete\|Done\|已完成" "$LOG_FILE" 2>/dev/null; then
        echo "=== Resume completed a video: $(date) ===" >> "$LOG_FILE"
        # Find and open the completed video
        LATEST_DIR=$(find "$PROJECT_DIR/output" -maxdepth 1 -type d -name "*books*" -newer "$LOG_FILE" 2>/dev/null | sort | tail -1)
        if [ -z "$LATEST_DIR" ]; then
            LATEST_DIR=$(ls -dt "$PROJECT_DIR/output/"*books* 2>/dev/null | head -1)
        fi
        if [ -n "$LATEST_DIR" ]; then
            for vid in "$LATEST_DIR/final_zh_with_intro.mp4" "$LATEST_DIR/final_zh.mp4"; do
                if [ -f "$vid" ]; then
                    /usr/bin/open "$vid"
                    break
                fi
            done
        fi
    fi
fi

# ── Step 4: If quota remains, start a NEW video ─────────────────────────
# Check if we still have quota budget (resume might have used some)
echo "Checking remaining quota for new video..." >> "$LOG_FILE"
HAS_QUOTA=$("$PYTHON" -c "
from illustration_generator import _imagen_has_quota
print('yes' if _imagen_has_quota() else 'no')
" 2>/dev/null)

if [ "$HAS_QUOTA" = "yes" ]; then
    echo "Starting new books video..." >> "$LOG_FILE"
    MARKER_FILE="$LOG_DIR/.books_run_marker_$$"
    touch "$MARKER_FILE"

    "$PYTHON" "$PROJECT_DIR/generate_books.py" --auto >> "$LOG_FILE" 2>&1
    NEW_EXIT=$?
    echo "=== New video finished: $(date) | exit=$NEW_EXIT ===" >> "$LOG_FILE"

    if [ $NEW_EXIT -eq 0 ]; then
        LATEST_DIR=""
        for dir in "$PROJECT_DIR/output"/*books*/; do
            if [ -d "$dir" ] && [ "$dir" -nt "$MARKER_FILE" ]; then
                for vid in "$dir/final_zh_with_intro.mp4" "$dir/final_zh.mp4"; do
                    if [ -f "$vid" ]; then
                        LATEST_DIR="$dir"
                        /usr/bin/open "$vid"
                        break 2
                    fi
                done
            fi
        done
    fi
    rm -f "$MARKER_FILE"
else
    echo "No quota left after resume — skipping new video" >> "$LOG_FILE"
fi

echo "=== Books daily run finished: $(date) ===" >> "$LOG_FILE"

# Keep only last 60 days of logs
find "$LOG_DIR" -name "books_*.log" -mtime +60 -delete 2>/dev/null
