#!/usr/bin/env python3
"""Stop hook: hold the turn open while this session's pstack seats still run.

A seat (~/.claude/pstack-ext/seat.py) runs as a background Bash task. Without
this hook the turn ends while it runs and the app shows the session as idle.
Here the hook waits until the session's own seats exit, then blocks the stop
so Claude carries on in the same turn and reads the --out files.
"""
import json
import os
import subprocess
import sys
import time

SEAT_SCRIPT = "seat.py"
POLL_SECONDS = 5
MAX_WAIT_SECONDS = 1750
SHELLS = {"sh", "bash", "zsh", "dash", "fish", "python", "python3", "env"}


def process_table():
    out = subprocess.run(
        ["ps", "-axo", "pid=,ppid=,command="], capture_output=True, text=True
    ).stdout
    table = {}
    for line in out.splitlines():
        parts = line.split(None, 2)
        if len(parts) == 3:
            table[int(parts[0])] = (int(parts[1]), parts[2])
    return table


def executable_name(command):
    return os.path.basename(command.split()[0]) if command else ""


def session_pid(table):
    pid = os.getppid()
    while pid in table:
        ppid, command = table[pid]
        if executable_name(command) not in SHELLS:
            return pid
        pid = ppid
    return None


def descends_from(pid, ancestor, table):
    while pid in table and pid > 1:
        if pid == ancestor:
            return True
        pid = table[pid][0]
    return False


def running_seats(root):
    table = process_table()
    return [
        pid for pid, (_, command) in table.items()
        if pid != os.getpid()
        and any(os.path.basename(arg) == SEAT_SCRIPT for arg in command.split()[1:3])
        and descends_from(pid, root, table)
    ]


def main():
    try:
        json.load(sys.stdin)
    except ValueError:
        pass

    root = session_pid(process_table())
    if root is None or not running_seats(root):
        return 0

    deadline = time.monotonic() + MAX_WAIT_SECONDS
    while running_seats(root):
        if time.monotonic() > deadline:
            return 0
        time.sleep(POLL_SECONDS)

    print(json.dumps({
        "decision": "block",
        "reason": "后台的 pstack 席位（seat.py）都已退出。读各席位的 --out 文件和退出码，接着完成原来的任务。",
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
