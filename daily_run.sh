#!/bin/bash
# Daily auto-run: generate + upload true crime video(s)
# Runs via macOS launchd — see com.aivideo.daily*.plist

PROJECT_DIR="/Users/arlong/Projects/AIvideo"
PYTHON="/Users/arlong/.pyenv/versions/3.10.11/bin/python3"
LOG_DIR="$PROJECT_DIR/logs"

mkdir -p "$LOG_DIR"

# How many videos to generate this run (edit to change)
VIDEOS_PER_RUN=2

cd "$PROJECT_DIR" || exit 1
# Homebrew ffmpeg must be on PATH when run under launchd (no login shell)
export PATH="/opt/homebrew/bin:/Users/arlong/.pyenv/bin:$PATH"
# imageio_ffmpeg's bundled binary is missing on this machine — point moviepy at system ffmpeg
export IMAGEIO_FFMPEG_EXE="/opt/homebrew/bin/ffmpeg"
eval "$(pyenv init -)"

# Pre-flight health check — bail out early if environment is broken.
# On failure health_check.py sends a Telegram alert itself.
HEALTH_LOG="$LOG_DIR/daily_$(date +%Y%m%d)_health.log"
"$PYTHON" "$PROJECT_DIR/health_check.py" --verbose > "$HEALTH_LOG" 2>&1
if [ $? -ne 0 ]; then
    echo "=== Pre-flight health check FAILED: $(date) ===" >> "$HEALTH_LOG"
    echo "Aborting daily run — see Telegram alert." >> "$HEALTH_LOG"
    exit 1
fi

for i in $(seq 1 $VIDEOS_PER_RUN); do
    LOG_FILE="$LOG_DIR/daily_$(date +%Y%m%d)_run${i}.log"
    echo "=== Run $i/$VIDEOS_PER_RUN started: $(date) ===" >> "$LOG_FILE"
    # Slot 1 → publish at 10:00 AM, Slot 2 → publish at 18:00 PM (Taiwan time)
    "$PYTHON" generate.py --auto --upload --slot $i >> "$LOG_FILE" 2>&1
    EXIT_CODE=$?
    echo "=== Run $i/$VIDEOS_PER_RUN finished: $(date) | exit=$EXIT_CODE ===" >> "$LOG_FILE"
    # No sleep between slots — slot N+1 starts only after slot N fully completes
    # (sequential execution in for loop, no background &)
done

# Keep only last 30 days of logs
find "$LOG_DIR" -name "daily_*.log" -mtime +30 -delete
