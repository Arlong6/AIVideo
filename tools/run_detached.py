"""Run a long command fully detached, so nothing kills it when the caller goes away.

A full batch render is 40+ minutes. Backgrounding it from an agent shell with
`&` or `nohup` is not enough — the whole process group gets torn down when the
caller's shell does, and what that leaves behind is worse than no render at all:
a truncated mp4 whose header still parses, whose duration still looks right, and
which only fails once something decodes past the cut. Three of those had to be
found and re-rendered before this existed.

macOS has no `setsid`, so this does the classic double fork: the first child
calls `os.setsid()` to become a new session leader with no controlling terminal,
the second detaches from that leader so the process can never reacquire one.

Usage:
  python3 tools/run_detached.py LOGFILE CMD [ARGS...]

Prints the detached PID. Poll the logfile, or `kill PID` to stop it.
"""
from __future__ import annotations

import os
import sys


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    log_path, cmd = sys.argv[1], sys.argv[2:]

    read_fd, write_fd = os.pipe()          # so the caller can learn the real PID

    if os.fork() > 0:                      # original caller
        os.close(write_fd)
        pid = os.read(read_fd, 32).decode().strip()
        os.close(read_fd)
        os.wait()                          # reap the intermediate child at once
        print(pid)
        return 0

    # First child: new session, no controlling terminal.
    os.close(read_fd)
    os.setsid()
    if os.fork() > 0:
        os._exit(0)                        # leave the session leader behind

    # Second child: the one that actually runs, and cannot reacquire a terminal.
    os.write(write_fd, f"{os.getpid()}\n".encode())
    os.close(write_fd)

    fd = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
    os.dup2(fd, 1)
    os.dup2(fd, 2)
    devnull = os.open(os.devnull, os.O_RDONLY)
    os.dup2(devnull, 0)
    os.execvp(cmd[0], cmd)                 # replaces this process; never returns
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
