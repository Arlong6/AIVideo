#!/bin/bash
# Daily auto-run: generate + upload true crime video(s)
# Runs via macOS launchd — see com.aivideo.daily*.plist
# Also runs via GH Actions daily.yml (VIDEO_ENGINE=remotion on GH)

PROJECT_DIR="/Users/arlong/Projects/AIvideo"
PYTHON="/Users/arlong/.pyenv/versions/3.10.11/bin/python3"
LOG_DIR="$PROJECT_DIR/logs"

mkdir -p "$LOG_DIR"

VIDEOS_PER_RUN=2

cd "$PROJECT_DIR" || exit 1

# ── Bug #2 fix: ffmpeg PATH detection (Homebrew arm64 / intel / system) ──
if [ -x "/opt/homebrew/bin/ffmpeg" ]; then
    FFMPEG_DIR="/opt/homebrew/bin"          # Apple Silicon
elif [ -x "/usr/local/bin/ffmpeg" ]; then
    FFMPEG_DIR="/usr/local/bin"             # Intel Homebrew
elif command -v ffmpeg >/dev/null 2>&1; then
    FFMPEG_DIR="$(dirname "$(command -v ffmpeg)")"  # System
else
    echo "FATAL: ffmpeg not found anywhere" | tee -a "$LOG_DIR/daily_$(date +%Y%m%d)_health.log"
    exit 1
fi
export PATH="$FFMPEG_DIR:/Users/arlong/.pyenv/bin:$PATH"
# MoviePy needs this for books/long-form (Remotion uses its own ffmpeg)
export IMAGEIO_FFMPEG_EXE="$FFMPEG_DIR/ffmpeg"
eval "$(pyenv init -)" 2>/dev/null || true

# ── Pre-flight health check ──
HEALTH_LOG="$LOG_DIR/daily_$(date +%Y%m%d_%H%M)_health.log"
"$PYTHON" "$PROJECT_DIR/health_check.py" --verbose > "$HEALTH_LOG" 2>&1
if [ $? -ne 0 ]; then
    echo "=== Pre-flight health check FAILED: $(date) ===" >> "$HEALTH_LOG"
    echo "Aborting daily run — see Telegram alert." >> "$HEALTH_LOG"
    exit 1
fi

# ── Bug #1 + #6 fix: slots run independently, failures don't block next ──
# Each slot runs in its own subshell. A single slot failure sends Telegram
# (generate.py handles that) but does NOT abort the other slot.
# Two consecutive failures → abort remaining slots (environment is broken).
CONSECUTIVE_FAILS=0

for i in $(seq 1 $VIDEOS_PER_RUN); do
    LOG_FILE="$LOG_DIR/daily_$(date +%Y%m%d)_run${i}.log"
    echo "=== Run $i/$VIDEOS_PER_RUN started: $(date) ===" >> "$LOG_FILE"

    # Bug #4 fix: wrap generate.py with a timeout (10 min per slot).
    # If Gemini hangs or any API stalls, the slot dies cleanly instead of
    # blocking the whole pipeline forever.
    timeout 600 "$PYTHON" generate.py --auto --upload --slot $i >> "$LOG_FILE" 2>&1
    EXIT_CODE=$?

    if [ $EXIT_CODE -eq 124 ]; then
        echo "=== Run $i TIMED OUT after 600s: $(date) ===" >> "$LOG_FILE"
        "$PYTHON" -c "
from telegram_notify import _send_raw
_send_raw('⏰ [AIvideo] Slot $i 超時 (600s)，可能 API 卡住')
" 2>/dev/null
    fi

    echo "=== Run $i/$VIDEOS_PER_RUN finished: $(date) | exit=$EXIT_CODE ===" >> "$LOG_FILE"

    # Bug #6 fix: unified failure strategy
    if [ $EXIT_CODE -ne 0 ]; then
        CONSECUTIVE_FAILS=$((CONSECUTIVE_FAILS + 1))
        echo "  Consecutive failures: $CONSECUTIVE_FAILS" >> "$LOG_FILE"
        if [ $CONSECUTIVE_FAILS -ge 2 ]; then
            echo "=== 2 consecutive failures — aborting remaining slots ===" >> "$LOG_FILE"
            "$PYTHON" -c "
from telegram_notify import _send_raw
_send_raw('🛑 [AIvideo] 連續 $CONSECUTIVE_FAILS 次失敗，中止後續 slot')
" 2>/dev/null
            break
        fi
    else
        CONSECUTIVE_FAILS=0
    fi
done

# Keep only last 30 days of logs
find "$LOG_DIR" -name "daily_*.log" -mtime +30 -delete 2>/dev/null
