#!/usr/bin/env python3
"""验证记忆写入闸门。跑法：python3 tests/test_memory_gate.py"""
import json
import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOOK = ROOT / "hooks" / "memory-gate.py"
failed = 0


def report(ok, label):
    global failed
    failed += not ok
    print(f"{'ok  ' if ok else 'FAIL'} {label}")


def run(home, payload):
    env = {**os.environ, "HOME": str(home)}
    return subprocess.run(
        ["/usr/bin/python3", str(HOOK)], input=json.dumps(payload), text=True, capture_output=True, env=env
    )


def prompt(home, text, session="s1"):
    run(home, {"hook_event_name": "UserPromptSubmit", "session_id": session, "prompt": text})


def tool(home, event, name, tool_input, session="s1"):
    return run(home, {"hook_event_name": event, "session_id": session, "cwd": "/x", "tool_name": name, "tool_input": tool_input})


def approval_cases(home):
    cases = [
        (True, "记住：shift 的 land 只合本地 main"),
        (True, "记 1、3"),
        (True, "记1"),
        (True, "这条记下来"),
        (True, "批准记忆 2"),
        (True, "把第 2 条记忆删掉"),
        (True, "忘掉那条关于端口的"),
        (False, "不要记这个"),
        (False, "别记住这件事"),
        (False, "帮我修一下登录页"),
        (False, "这个记录有问题"),
        (False, "日记 1 篇"),
    ]
    for expected, text in cases:
        prompt(home, text)
        code = tool(home, "PreToolUse", "Write", {"file_path": str(home / ".claude/projects/p/memory/a.md")}).returncode
        report((code == 0) == expected, f"{'批准' if expected else '不批准'}: {text!r} -> exit {code}")


def pre_tool_cases(home):
    mem = home / ".claude/projects/-Users-l-shift/memory"
    prompt(home, "帮我看下日志")
    cases = [
        (2, "Write", {"file_path": str(mem / "feedback.md")}),
        (2, "Edit", {"file_path": str(mem / "MEMORY.md")}),
        (2, "Write", {"file_path": "~/.claude/projects/-Users-l-shift/memory/x.md"}),
        (0, "Write", {"file_path": str(home / ".claude/projects/-Users-l-shift/abc.jsonl")}),
        (0, "Write", {"file_path": "/tmp/memory/x.md"}),
        (0, "Edit", {"file_path": str(home / "repo/CLAUDE.md")}),
        (2, "Bash", {"command": f"echo hi > {mem}/a.md"}),
        (2, "Bash", {"command": f"sed -i '' 's/a/b/' ~/.claude/projects/p/memory/a.md"}),
        (2, "Bash", {"command": f"rm {mem}/a.md"}),
        (2, "Bash", {"command": f"cat > {mem}/a.md <<'EOF'\nx\nEOF"}),
        (2, "Bash", {"command": f"git -C {home}/.claude/projects checkout -- p/memory"}),
        (2, "Bash", {"command": "cd ~/.claude/projects && rm p/memory/a.md"}),
        (0, "Bash", {"command": f"cat {mem}/MEMORY.md"}),
        (0, "Bash", {"command": f"ls {mem} 2>/dev/null"}),
        (0, "Bash", {"command": f"grep -r port ~/.claude/projects/*/memory/ 2>&1 | head"}),
        (0, "Bash", {"command": f"git -C {home}/.claude/projects log --oneline -- p/memory"}),
        (0, "Bash", {"command": "echo hi > /tmp/a.txt"}),
        (0, "Bash", {"command": f"for t in tests/*.py; do python3 \"$t\"; done; ls {mem} 2>&1 | head -3"}),
        (2, "Bash", {"command": f"python3 - <<'EOF'\nopen('{mem}/a.md', 'w').write('x')\nEOF"}),
        (2, "Bash", {"command": f"echo x | tee {mem}/a.md"}),
        (0, "Bash", {"command": "git commit -F - <<'EOF'\nmemory-gate: 改动进 ~/.claude/projects 的仓库\nEOF"}),
        (0, "Bash", {"command": "python3 - <<'EOF'\ns = 'r\"\\.claude/projects\\b.*\\bmemory\\b\"'\nEOF"}),
        (0, "Read", {"file_path": str(mem / "a.md")}),
    ]
    for expected, name, tool_input in cases:
        result = tool(home, "PreToolUse", name, tool_input)
        label = tool_input.get("command") or tool_input.get("file_path")
        report(result.returncode == expected, f"{name} {label!r} -> exit {result.returncode}")
    blocked = tool(home, "PreToolUse", "Write", {"file_path": str(mem / "a.md")})
    report("需要你决定" in blocked.stderr, "拦截提示里告诉模型把候选写进汇报")


def lifecycle_cases(home):
    mem = home / ".claude/projects/p/memory/a.md"
    prompt(home, "记住 a", session="s2")
    report(tool(home, "PreToolUse", "Write", {"file_path": str(mem)}, session="s2").returncode == 0, "批准后同会话放行")
    report(tool(home, "PreToolUse", "Write", {"file_path": str(mem)}, session="s3").returncode == 2, "别的会话不沾光")
    prompt(home, "继续", session="s2")
    report(tool(home, "PreToolUse", "Write", {"file_path": str(mem)}, session="s2").returncode == 2, "下一条消息后通行证失效")


def commit_cases(home, workdir):
    projects = home / ".claude/projects"
    gitdir = workdir / "claude-memory.git"
    subprocess.run(["git", "init", "-q", "--separate-git-dir", str(gitdir), str(projects)], check=True)
    (projects / ".gitignore").write_text("/*\n!/.gitignore\n!/*/\n/*/*\n!/*/memory/\n")
    (projects / "p/abc.jsonl").write_text("transcript\n")
    mem = projects / "p/memory/a.md"
    mem.write_text("---\nname: a\n---\nx\n")

    prompt(home, "记住 a 规则", session="s4")
    tool(home, "PostToolUse", "Write", {"file_path": str(mem)}, session="s4")
    git = ["git", "-C", str(projects)]
    log = subprocess.run(git + ["log", "-1", "--format=%B"], capture_output=True, text=True).stdout
    files = subprocess.run(git + ["ls-files"], capture_output=True, text=True).stdout.split()
    report("session: s4" in log and "记住 a 规则" in log, "commit 带会话 id 和批准原话")
    report("p/memory/a.md" in files and "p/abc.jsonl" not in files, "只收记忆文件，不收会话记录")

    head = subprocess.run(git + ["rev-parse", "HEAD"], capture_output=True, text=True).stdout
    tool(home, "PostToolUse", "Edit", {"file_path": str(home / "repo/x.md")}, session="s4")
    after = subprocess.run(git + ["rev-parse", "HEAD"], capture_output=True, text=True).stdout
    report(head == after, "改别的文件不产生 commit")


with tempfile.TemporaryDirectory() as tmp:
    home = Path(tmp) / "home"
    (home / ".claude/projects/p/memory").mkdir(parents=True)
    approval_cases(home)
    pre_tool_cases(home)
    lifecycle_cases(home)
    commit_cases(home, Path(tmp))

print(f"\n{'全部通过' if not failed else f'{failed} 项失败'}")
raise SystemExit(1 if failed else 0)
