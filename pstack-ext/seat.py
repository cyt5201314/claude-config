#!/usr/bin/env python3
"""Run one pstack panel seat on a non-Claude model through its local CLI.

Used by ~/.claude/rules/pstack-external.md. Binaries and logins are the ones
T3 Code installed under ~/.t3; nothing here stores credentials.

    seat.py gpt    --model gpt-6.2-astra   --effort max  --cwd DIR --brief FILE --out FILE [--write]
    seat.py gemini --model gemini-4-carbon --effort high --cwd DIR --brief FILE --out FILE

Exit codes: 0 ok, 2 usage or isolation guard, 3 T3 Code session, 4 CLI not
found, 5 the CLI failed (auth, quota, bad model), 6 timeout.
"""
import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
from pathlib import Path

T3_TOOLS = Path.home() / ".t3" / "tools"

EXIT_USAGE, EXIT_T3, EXIT_NO_CLI, EXIT_FAILED, EXIT_TIMEOUT = 2, 3, 4, 5, 6


def die(code, message):
    print(f"seat.py: {message}", file=sys.stderr)
    sys.exit(code)


def codex_bin():
    active = T3_TOOLS / "codex" / "active.json"
    if active.is_file():
        version = json.loads(active.read_text())["version"]
        candidate = T3_TOOLS / "codex" / version / "bin" / "codex"
        if candidate.is_file():
            return str(candidate)
    return shutil.which("codex")


def antigravity_bin():
    root = T3_TOOLS / "antigravity-acp" / "darwin-arm64"
    active = root / "active.json"
    if active.is_file():
        release = json.loads(active.read_text())["releaseId"]
        candidate = root / "versions" / release / "antigravity"
        if candidate.is_file():
            return str(candidate)
    return shutil.which("agy") or shutil.which("antigravity")


# Inherited from a git hook or a wrapper, these would make git describe some
# other repository than the one --cwd is in.
GIT_LOCATION_VARS = (
    "GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_NAMESPACE", "GIT_PREFIX",
)


def git(cwd, *args):
    env = {k: v for k, v in os.environ.items() if k not in GIT_LOCATION_VARS}
    return subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True, text=True, env={**env, "LC_ALL": "C"},
    )


MAX_SCAN = 20000


def holds_a_repo(cwd):
    """True when cwd, an ancestor, or anything beneath it has a .git entry."""
    if any((d / ".git").exists() for d in (cwd, *cwd.parents)):
        return True
    seen = 0
    for _, dirs, files in os.walk(cwd):
        if ".git" in dirs or ".git" in files:
            return True
        seen += len(dirs) + len(files)
        if seen > MAX_SCAN:
            return True
    return False


def isolation_problem(cwd):
    """Why a seat that can write must not run in cwd, or None when it may.

    Allowed: a linked git worktree, or a directory with no repo in, above or
    beneath it. Anything git cannot answer cleanly is refused.
    """
    git_dir = git(cwd, "rev-parse", "--path-format=absolute", "--git-dir")
    if git_dir.returncode == 0:
        common = git(cwd, "rev-parse", "--path-format=absolute", "--git-common-dir")
        if common.returncode != 0 or not git_dir.stdout.strip() or not common.stdout.strip():
            return f"git could not describe {cwd}: {common.stderr.strip()}"
        if git_dir.stdout.strip() == common.stdout.strip():
            return f"{cwd} is a repo's primary checkout"
        return None
    if "not a git repository" not in git_dir.stderr:
        return f"git could not describe {cwd}: {git_dir.stderr.strip()}"
    if holds_a_repo(cwd):
        return f"{cwd} is not a worktree but has a git repo in, above or beneath it (or is too large to scan)"
    return None


def kill_group(proc):
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(proc.pid, sig)
        except (ProcessLookupError, PermissionError):
            # macOS answers EPERM when only zombies are left in the group.
            return
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass


def run(cmd, cwd, stdin_text, timeout):
    # The CLI gets its own process group so that a timeout, or seat.py itself
    # being interrupted, stops the shells and tools it spawned along with it.
    proc = subprocess.Popen(
        cmd,
        cwd=cwd,
        stdin=subprocess.PIPE if stdin_text is not None else subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        stdout, stderr = proc.communicate(stdin_text, timeout=timeout)
    except subprocess.TimeoutExpired:
        kill_group(proc)
        die(EXIT_TIMEOUT, f"timed out after {timeout}s: {cmd[0]}")
    except BaseException:
        kill_group(proc)
        raise
    return subprocess.CompletedProcess(cmd, proc.returncode, stdout, stderr)


def run_gpt(args, brief):
    binary = codex_bin() or die(EXIT_NO_CLI, "codex CLI not found under ~/.t3/tools or on PATH")
    # --ignore-user-config: ~/.codex/config.toml sets max effort, a notify hook,
    # MCP servers and plugins; a panel seat wants none of them. Auth still loads.
    cmd = [
        binary, "exec", "--ignore-user-config", "--ephemeral",
        "-m", args.model,
        "-c", f"model_reasoning_effort={args.effort}",
        "-s", "workspace-write" if args.write else "read-only",
        "--skip-git-repo-check",
        "-C", str(args.cwd),
        "-o", str(args.out),
        "-",
    ]
    result = run(cmd, args.cwd, brief, args.timeout)
    if result.returncode != 0 or not args.out.is_file() or not args.out.read_text().strip():
        tail = "\n".join((result.stderr or result.stdout).strip().splitlines()[-5:])
        die(EXIT_FAILED, f"codex exit {result.returncode}\n{tail}")


def run_gemini(args, brief):
    binary = antigravity_bin() or die(EXIT_NO_CLI, "antigravity CLI not found under ~/.t3/tools or on PATH")
    cmd = [
        binary, "-p", brief,
        "--model", f"{args.model}-{args.effort}",
        "--sandbox",
        "--output-format", "json",
        "--print-timeout", f"{args.timeout}s",
    ]
    result = run(cmd, args.cwd, None, args.timeout + 30)
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        tail = "\n".join((result.stderr or result.stdout).strip().splitlines()[-5:])
        die(EXIT_FAILED, f"antigravity exit {result.returncode}, no JSON result\n{tail}")
    response = (payload.get("response") or "").strip()
    if result.returncode != 0 or payload.get("status") != "SUCCESS" or not response:
        die(EXIT_FAILED, f"antigravity exit {result.returncode}, status {payload.get('status')}: {str(payload)[:400]}")
    args.out.write_text(response + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("vendor", choices=["gpt", "gemini"])
    parser.add_argument("--model", required=True)
    parser.add_argument("--effort", required=True)
    parser.add_argument("--cwd", required=True, type=Path)
    parser.add_argument("--brief", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--write", action="store_true", help="gpt only: let the seat edit files and run commands in --cwd")
    parser.add_argument("--timeout", type=int, default=1500, help="seconds (default 1500)")
    args = parser.parse_args()

    if os.environ.get("CLAUDE_CODE_ENTRYPOINT") == "t3-code":
        die(EXIT_T3, "T3 Code session: dispatch through delegate_task per ~/.claude/pstack-t3/bridge.md")

    args.cwd, args.brief, args.out = args.cwd.resolve(), args.brief.resolve(), args.out.resolve()
    if not args.cwd.is_dir():
        die(EXIT_USAGE, f"--cwd is not a directory: {args.cwd}")
    if not args.brief.is_file() or not args.brief.read_text().strip():
        die(EXIT_USAGE, f"--brief is missing or empty: {args.brief}")
    if args.write and args.vendor == "gemini":
        die(EXIT_USAGE, "--write is gpt only; a gemini seat can always write, so isolation is enforced instead")

    if not args.out.parent.is_dir():
        die(EXIT_USAGE, f"--out parent directory does not exist: {args.out.parent}")
    if args.out.is_dir():
        die(EXIT_USAGE, f"--out is a directory: {args.out}")
    if args.out == args.brief:
        die(EXIT_USAGE, f"--out and --brief are the same file: {args.out}")
    if not os.access(args.out.parent, os.W_OK):
        die(EXIT_USAGE, f"--out parent directory is not writable: {args.out.parent}")

    # A gemini seat cannot be made read-only (2026-11-19: with --sandbox it still
    # created a file), and a gpt --write seat edits by design.
    if args.vendor == "gemini" or args.write:
        problem = isolation_problem(args.cwd)
        if problem:
            die(EXIT_USAGE, f"{problem}; give this seat its own git worktree, or a copy without .git outside any repo")

    brief = args.brief.read_text()
    try:
        args.out.unlink(missing_ok=True)
    except OSError as error:
        die(EXIT_USAGE, f"cannot replace --out: {error}")

    # A caller that stops seat.py (a Bash time limit, a closed terminal) must
    # not leave the CLI running; SIGINT already raises KeyboardInterrupt.
    for sig in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, lambda signum, _frame: sys.exit(128 + signum))
    (run_gpt if args.vendor == "gpt" else run_gemini)(args, brief)

    print(f"ok {args.vendor} {args.model} {args.effort} -> {args.out} ({args.out.stat().st_size} bytes)")
    status = git(args.cwd, "status", "--short")
    if status.returncode == 0:
        changed = status.stdout.strip()
        print(f"git status in {args.cwd}:\n{changed}" if changed else f"git status in {args.cwd}: clean")


if __name__ == "__main__":
    main()
