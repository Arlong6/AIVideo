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
export PATH="/Users/arlong/.pyenv/bin:$PATH"
eval "$(pyenv init -)"

for i in $(seq 1 $VIDEOS_PER_RUN); do
    LOG_FILE="$LOG_DIR/daily_$(date +%Y%m%d)_run${i}.log"
    echo "=== Run $i/$VIDEOS_PER_RUN started: $(date) ===" >> "$LOG_FILE"
    # Slot 1 → publish at 10:00 AM, Slot 2 → publish at 18:00 PM (Taiwan time)
    "$PYTHON" generate.py --auto --upload --slot $i >> "$LOG_FILE" 2>&1
    EXIT_CODE=$?
    echo "=== Run $i/$VIDEOS_PER_RUN finished: $(date) | exit=$EXIT_CODE ===" >> "$LOG_FILE"
    if [ $i -lt $VIDEOS_PER_RUN ]; then
        sleep 60  # brief pause between runs
    fi
done

# Keep only last 30 days of logs
find "$LOG_DIR" -name "daily_*.log" -mtime +30 -delete
