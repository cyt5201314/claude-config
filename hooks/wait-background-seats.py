#!/usr/bin/env python3
"""Keep a session visibly busy while its pstack seats still run.

A seat (~/.claude/pstack-ext/seat.py) runs as a background Bash task. The
desktop app marks the session idle as soon as the turn reaches Stop, even
while a Stop hook is still running, so holding the turn inside this hook
leaves the sidebar showing idle. Instead:

- As the Stop hook (no arguments): if this session's seats still run, block
  the stop at once and tell Claude to wait in the foreground with --wait.
- With --wait (run by Claude as a foreground Bash call): wait up to
  WAIT_SECONDS for the seats to exit, then report what is left. A tool call
  in progress keeps the session shown as running.
"""
import json
import os
import subprocess
import sys
import time

SEAT_SCRIPT = "seat.py"
POLL_SECONDS = 5
WAIT_SECONDS = 570
MAX_SEAT_SECONDS = 1800
SHELLS = {"sh", "bash", "zsh", "dash", "fish", "python", "python3", "env"}
WAIT_COMMAND = "python3 ~/.claude/hooks/wait-background-seats.py --wait"


def elapsed_seconds(etime):
    days, _, clock = etime.rpartition("-")
    seconds = 0
    for part in clock.split(":"):
        seconds = seconds * 60 + int(part)
    return seconds + int(days or 0) * 86400


def process_table():
    out = subprocess.run(
        ["ps", "-axo", "pid=,ppid=,etime=,command="], capture_output=True, text=True
    ).stdout
    table = {}
    for line in out.splitlines():
        parts = line.split(None, 3)
        if len(parts) == 4:
            table[int(parts[0])] = (int(parts[1]), elapsed_seconds(parts[2]), parts[3])
    return table


def executable_name(command):
    return os.path.basename(command.split()[0]) if command else ""


def session_pid(table):
    pid = os.getppid()
    while pid in table:
        ppid, _, command = table[pid]
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
        pid for pid, (_, elapsed, command) in table.items()
        if pid != os.getpid()
        and elapsed < MAX_SEAT_SECONDS
        and any(os.path.basename(arg) == SEAT_SCRIPT for arg in command.split()[1:3])
        and descends_from(pid, root, table)
    ]


def stop_hook():
    try:
        json.load(sys.stdin)
    except ValueError:
        pass
    root = session_pid(process_table())
    seats = running_seats(root) if root else []
    if seats:
        print(json.dumps({
            "decision": "block",
            "reason": (
                f"本会话还有 {len(seats)} 个 pstack 席位（seat.py）在跑，直接结束这一轮侧栏会显示空闲。"
                f"用 Bash 前台跑 `{WAIT_COMMAND}`（timeout 600000），不要 run_in_background；"
                "它说还有席位在跑就再跑一次，都退出后读各席位的 --out 文件和退出码，接着完成原来的任务。"
            ),
        }, ensure_ascii=False))
    return 0


def wait():
    root = session_pid(process_table())
    if root is None:
        print("找不到本会话的 Claude 进程，没法判断席位。")
        return 1
    deadline = time.monotonic() + WAIT_SECONDS
    while (seats := running_seats(root)) and time.monotonic() < deadline:
        time.sleep(POLL_SECONDS)
    if seats:
        print(f"还有 {len(seats)} 个席位在跑（pid {' '.join(map(str, seats))}），再跑一次本命令接着等。")
    else:
        print("本会话的席位都已退出，读各席位的 --out 文件和退出码。")
    return 0


if __name__ == "__main__":
    sys.exit(wait() if sys.argv[1:] == ["--wait"] else stop_hook())
