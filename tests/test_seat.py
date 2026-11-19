#!/usr/bin/env python3
"""Checks for pstack-ext/seat.py.

    python3 tests/test_seat.py          # guards and failure paths against stub CLIs, offline
    python3 tests/test_seat.py --live   # also sends a seeded-bug review to GPT and Gemini
"""
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

SEAT = Path(__file__).resolve().parent.parent / "pstack-ext" / "seat.py"
BUG = "def add(a, b):\n    return a - b\n"
BRIEF = (
    "Review calc.py in the current directory. Do not edit any file. "
    "If add() is wrong, reply with one line starting with FINDING: that names the wrong operator."
)
# STUB_MODE=hang: leave a grandchild running and record its pid in $STUB_PID.
# STUB_MODE=orphan: exit at once but leave a child holding stdout.
CODEX_STUB = """#!/bin/sh
touch "$STUB_CALLED"
if [ "$STUB_MODE" = hang ]; then sleep 60 & echo $! > "$STUB_PID"; wait; fi
if [ "$STUB_MODE" = orphan ]; then sleep 60 & echo $! > "$STUB_PID"; exit 0; fi
cat >/dev/null
while [ $# -gt 0 ]; do [ "$1" = -o ] && out=$2; shift; done
echo STUB_GPT > "$out"
"""
# Reads stdin to EOF first, so it only returns promptly when seat.py closes stdin.
ANTIGRAVITY_STUB = """#!/bin/sh
touch "$STUB_CALLED"
cat >/dev/null
echo '{"status":"SUCCESS","response":"STUB_GEMINI"}'
"""
failures = []


def git(cwd, *args):
    subprocess.run(
        ["git", "-C", str(cwd), "-c", "user.email=t@t", "-c", "user.name=t", *args],
        check=True, capture_output=True,
    )


def seat(*args, env=None):
    return subprocess.run(
        [sys.executable, str(SEAT), *map(str, args)],
        capture_output=True, text=True, stdin=subprocess.DEVNULL, env={**os.environ, **(env or {})},
    )


def check(name, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {name}")
    if not ok:
        failures.append(name)
        print(f"      {detail.strip()[:600]}")


def install_stubs(home):
    codex = home / ".t3/tools/codex"
    (codex / "0/bin").mkdir(parents=True)
    (codex / "active.json").write_text('{"version": "0"}')
    (codex / "0/bin/codex").write_text(CODEX_STUB)
    (codex / "0/bin/codex").chmod(0o755)
    agy = home / ".t3/tools/antigravity-acp/darwin-arm64"
    (agy / "versions/r").mkdir(parents=True)
    (agy / "active.json").write_text('{"releaseId": "r"}')
    (agy / "versions/r/antigravity").write_text(ANTIGRAVITY_STUB)
    (agy / "versions/r/antigravity").chmod(0o755)


def alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


def main():
    live = "--live" in sys.argv
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp).resolve()
        home, ws, plain = tmp / "home", tmp / "ws", tmp / "plain"
        repo, tree = ws / "repo", tmp / "tree"
        brief, out, called, pidfile = tmp / "brief.txt", tmp / "out.txt", tmp / "called", tmp / "pid"
        install_stubs(home)
        plain.mkdir()
        repo.mkdir(parents=True)
        git(repo, "init", "-q")
        (repo / "calc.py").write_text(BUG)
        git(repo, "add", "-A")
        git(repo, "commit", "-qm", "init")
        git(repo, "worktree", "add", "-q", str(tree))
        brief.write_text(BRIEF)
        base = ["--model", "m", "--effort", "low", "--brief", brief, "--out", out]
        stub = {"HOME": str(home), "STUB_CALLED": str(called), "STUB_PID": str(pidfile)}

        def refused(name, *args, needle, env=None):
            called.unlink(missing_ok=True)
            r = seat(*args, env={**stub, **(env or {})})
            check(name, r.returncode == 2 and needle in r.stderr and not called.exists(), r.stdout + r.stderr)

        def allowed(name, *args, expect):
            out.unlink(missing_ok=True)
            r = seat(*args, env=stub)
            text = out.read_text() if out.is_file() else ""
            check(name, r.returncode == 0 and expect in text, r.stdout + r.stderr)

        refused("gemini refuses a primary checkout", "gemini", "--cwd", repo, *base, needle="primary checkout")
        refused("gpt --write refuses a primary checkout", "gpt", "--cwd", repo, *base, "--write", needle="primary checkout")
        refused("gemini refuses a non-git folder that holds a repo", "gemini", "--cwd", ws, *base, needle="beneath it")
        refused("gemini refuses when git errors (unsafe owner)", "gemini", "--cwd", tree, *base,
                needle="git could not describe", env={"GIT_TEST_ASSUME_DIFFERENT_OWNER": "1"})
        refused("gemini rejects --write", "gemini", "--cwd", tree, *base, "--write", needle="gpt only")
        refused("missing brief", "gpt", "--cwd", repo, "--model", "m", "--effort", "low",
                "--brief", tmp / "none.txt", "--out", out, needle="--brief is missing")
        refused("--out parent missing, before any model call", "gpt", "--cwd", repo, "--model", "m", "--effort", "low",
                "--brief", brief, "--out", tmp / "nodir" / "o.txt", needle="parent directory does not exist")
        refused("--out is a directory", "gpt", "--cwd", repo, "--model", "m", "--effort", "low",
                "--brief", brief, "--out", plain, needle="is a directory")

        refused("gemini refuses a primary checkout despite an inherited GIT_DIR", "gemini", "--cwd", repo, *base,
                needle="primary checkout", env={"GIT_DIR": str(repo / ".git" / "worktrees" / "tree")})
        r = seat("gpt", "--cwd", repo, "--model", "m", "--effort", "low", "--brief", brief, "--out", brief, env=stub)
        check("--out equal to --brief is refused and the brief survives",
              r.returncode == 2 and "same file" in r.stderr and brief.read_text() == BRIEF, r.stderr)
        locked = tmp / "locked"
        locked.mkdir()
        locked.chmod(0o555)
        refused("--out parent not writable, before any model call", "gpt", "--cwd", repo, "--model", "m", "--effort", "low",
                "--brief", brief, "--out", locked / "o.txt", needle="not writable")
        locked.chmod(0o755)

        allowed("gemini runs in a linked worktree", "gemini", "--cwd", tree, *base, expect="STUB_GEMINI")
        allowed("gemini runs in a folder with no repo", "gemini", "--cwd", plain, *base, expect="STUB_GEMINI")
        allowed("gpt --write runs in a linked worktree", "gpt", "--cwd", tree, *base, "--write", expect="STUB_GPT")
        allowed("gpt read-only runs in a primary checkout", "gpt", "--cwd", repo, *base, expect="STUB_GPT")

        proc = subprocess.Popen(
            [sys.executable, str(SEAT), "gemini", "--cwd", str(tree), *map(str, base)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env={**os.environ, **stub},
        )
        try:
            proc.wait(timeout=15)
            check("gemini does not wait on the caller's open stdin", proc.returncode == 0)
        except subprocess.TimeoutExpired:
            proc.kill()
            check("gemini does not wait on the caller's open stdin", False, "still running after 15s")
        proc.communicate()

        pidfile.unlink(missing_ok=True)
        r = seat("gpt", "--cwd", repo, *base, "--timeout", "2", env={**stub, "STUB_MODE": "hang"})
        time.sleep(0.5)
        grandchild = int(pidfile.read_text()) if pidfile.is_file() else None
        check("timeout exits 6 and kills the CLI's child processes",
              r.returncode == 6 and grandchild is not None and not alive(grandchild),
              f"exit {r.returncode}, grandchild {grandchild}\n{r.stderr}")

        pidfile.unlink(missing_ok=True)
        r = seat("gpt", "--cwd", repo, *base, "--timeout", "2", env={**stub, "STUB_MODE": "orphan"})
        check("timeout still exits 6 when the CLI already exited but a child holds stdout",
              r.returncode == 6 and pidfile.is_file() and not alive(int(pidfile.read_text())), f"exit {r.returncode}\n{r.stderr}")

        for signum, label in ((signal.SIGTERM, "SIGTERM"), (signal.SIGHUP, "SIGHUP")):
            pidfile.unlink(missing_ok=True)
            proc = subprocess.Popen(
                [sys.executable, str(SEAT), "gpt", "--cwd", str(repo), *map(str, base)],
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                env={**os.environ, **stub, "STUB_MODE": "hang"},
            )
            deadline = time.time() + 10
            while not (pidfile.is_file() and pidfile.read_text().strip()) and time.time() < deadline:
                time.sleep(0.1)
            proc.send_signal(signum)
            try:
                proc.wait(timeout=20)
            except subprocess.TimeoutExpired:
                proc.kill()
            proc.communicate()
            time.sleep(0.5)
            grandchild = int(pidfile.read_text()) if pidfile.is_file() and pidfile.read_text().strip() else None
            check(f"{label} to seat.py also stops the CLI's child processes",
                  proc.returncode == 128 + signum and grandchild is not None and not alive(grandchild),
                  f"exit {proc.returncode}, grandchild {grandchild}")

        if live:
            r = seat("gpt", "--model", "no-such-model", "--cwd", repo, "--effort", "low", "--brief", brief, "--out", out)
            check("gpt bad model fails loudly (exit 5)", r.returncode == 5, r.stdout + r.stderr)

            for vendor, model, cwd in (("gpt", "gpt-6.2-astra", repo), ("gemini", "gemini-4-carbon", tree)):
                seat_out = tmp / f"{vendor}.txt"
                r = seat(vendor, "--model", model, "--cwd", cwd, "--effort", "low", "--brief", brief,
                         "--out", seat_out, "--timeout", "300")
                text = seat_out.read_text() if seat_out.is_file() else ""
                check(f"{vendor} seat returns the seeded finding", r.returncode == 0 and "FINDING:" in text, r.stdout + r.stderr + text)
                check(f"{vendor} seat left calc.py untouched", (cwd / "calc.py").read_text() == BUG)

    print(f"\n{'FAILED: ' + ', '.join(failures) if failures else 'all passed'}")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
