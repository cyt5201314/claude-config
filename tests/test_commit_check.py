#!/usr/bin/env python3
"""验证 commit 检查的两个入口和 cloud-setup.sh。跑法：python3 tests/test_commit_check.py"""
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOOK = ROOT / "hooks" / "require-commit-verify-rollback.py"
GOOD = "subject\n\nVerified: ran tests\nRollback: git revert it\n"
failed = 0


def report(ok, label):
    global failed
    failed += not ok
    print(f"{'ok  ' if ok else 'FAIL'} {label}")


def bash_entry_cases(tmp):
    """本机入口：stdin 收到将要跑的命令。"""
    (tmp / "good.txt").write_text(GOOD)
    (tmp / "bad.txt").write_text("subject only\n")
    cases = [
        (2, 'git commit -m "fix bug"'),
        (2, 'git add . && git commit -m "fix"'),
        (2, 'cd /tmp\ngit commit -m "fix"'),
        (2, 'git -C /some/repo commit -m "fix"'),
        (2, 'git -c user.name=t -C "/a b" commit -m "fix"'),
        (2, 'GIT_AUTHOR_NAME=x git commit -m "fix"'),
        (2, 'git commit -m "fix" -m "Verified: ok"'),
        (2, 'git commit -m "fix" -m "Rollback: revert"'),
        (2, 'git commit -m "提到已验证和回滚但不在行首"'),
        (2, './verify.sh && git commit -m "fix"'),
        (2, "git commit -F - <<'EOF'\nsubject\n\nbody\nEOF"),
        (2, f"git commit -F {tmp}/bad.txt"),
        (2, f"git commit --file={tmp}/bad.txt"),
        (2, 'git commit --amend -m "fix"'),
        (0, "git commit -F - <<'EOF'\nsubject\n\nVerified: ok\nRollback: revert\nEOF"),
        (0, "git commit -m \"$(cat <<'EOF'\nsubject\n\nVerified: ok\nRollback: revert\nEOF\n)\""),
        (0, 'git commit -m "fix" -m "Verified: ok" -m "Rollback: revert"'),
        (0, 'git commit -m "修复" -m "验证：跑了测试" -m "回滚：git revert"'),
        (0, 'git commit -m "fix\n\n- Verified by tests\n- Roll back with git revert"'),
        (0, f"git commit -F {tmp}/good.txt"),
        (0, f"git commit -F {tmp}/generated-later.txt"),
        (0, "git commit --amend --no-edit"),
        (0, "git commit --no-edit"),
        (0, "git commit --fixup abc123"),
        (0, "git commit --dry-run"),
        (0, "git commit -C HEAD"),
        (0, 'grep -n "git commit" README.md'),
        (0, "git commit-tree HEAD^{tree} -m x"),
        (0, "git log --oneline"),
        (0, "ls"),
    ]
    for expected, command in cases:
        result = subprocess.run(
            [sys.executable, str(HOOK)],
            input=json.dumps({"tool_input": {"command": command}, "cwd": str(tmp)}),
            capture_output=True,
            text=True,
        )
        report(result.returncode == expected, f"bash expected={expected} got={result.returncode} {command!r}")


def git(repo, *args, env=None):
    return subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.test", *args],
        capture_output=True,
        text=True,
        env=env,
    )


def commit_flow_cases(repo, env=None):
    """真实 git 流程：commit-msg 入口要拦住缺说明的提交，放过自动生成的 message。"""
    git(repo, "init", "-q", "-b", "main", env=env)
    report(git(repo, "commit", "--allow-empty", "-m", "no labels", env=env).returncode != 0, "git rejects no labels")
    report(git(repo, "rev-list", "--all", "--count", env=env).stdout.strip() == "0", "rejected commit left no history")
    report(
        git(repo, "commit", "--allow-empty", "-m", "only", "-m", "Verified: ok", env=env).returncode != 0,
        "git rejects missing rollback",
    )
    report(git(repo, "commit", "--allow-empty", "-m", GOOD, env=env).returncode == 0, "git accepts labels")

    (repo / "a.txt").write_text("a\n")
    git(repo, "add", "a.txt", env=env)
    report(git(repo, "commit", "-m", "add a", "-m", "验证：看过", "-m", "回滚：git revert", env=env).returncode == 0, "git accepts chinese labels")
    report(git(repo, "revert", "--no-edit", "HEAD", env=env).returncode == 0, "git revert passes")

    git(repo, "switch", "-q", "-c", "side", "HEAD~1", env=env)
    git(repo, "commit", "--allow-empty", "-m", GOOD, env=env)
    git(repo, "switch", "-q", "main", env=env)
    report(git(repo, "merge", "--no-ff", "--no-edit", "side", env=env).returncode == 0, "git merge passes")
    report(git(repo, "commit", "--allow-empty", "--fixup", "HEAD", env=env).returncode == 0, "git commit --fixup passes")


def commit_msg_entry_cases(tmp):
    hooks = tmp / "git-hooks"
    hooks.mkdir()
    shutil.copy(HOOK, hooks / "commit-msg")
    repo = tmp / "direct"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "core.hooksPath", str(hooks))
    commit_flow_cases(repo)


def tree_diff(a, b):
    """递归比较两个目录：多出或缺少的文件、内容不同或可执行位不同的文件。"""
    files = lambda root: {p.relative_to(root) for p in root.rglob("*") if p.is_file()} if root.is_dir() else set()
    fa, fb = files(a), files(b)
    if fa != fb or not fa:
        return [str(p) for p in sorted(fa ^ fb)] or ["(empty)"]
    return [
        str(p)
        for p in sorted(fa)
        if (a / p).read_bytes() != (b / p).read_bytes() or os.access(a / p, os.X_OK) != os.access(b / p, os.X_OK)
    ]


def cloud_setup_cases(tmp):
    """用临时 HOME 和 file:// 地址模拟 setup script，跑两遍确认可重复。"""
    home = tmp / "home"
    home.mkdir()
    tarball = tmp / "claude-config.tar.gz"
    with tarfile.open(tarball, "w:gz") as tar:   # 和 codeload 一样：最外层一个「仓库名-分支」目录
        tar.add(ROOT / "skills", arcname="claude-config-main/skills")
    env = {
        **os.environ,
        "HOME": str(home),
        "CLAUDE_CONFIG_RAW": ROOT.as_uri(),
        "CLAUDE_CONFIG_TARBALL": tarball.as_uri(),
    }
    env.pop("GIT_CONFIG_GLOBAL", None)
    script = (ROOT / "cloud-setup.sh").read_text()
    for attempt in (1, 2):
        result = subprocess.run(["bash"], input=script, capture_output=True, text=True, env=env)
        report(result.returncode == 0, f"cloud-setup run {attempt} exit 0 {result.stderr.strip()}")
    report((home / ".claude/CLAUDE.md").read_text() == (ROOT / "CLAUDE.md").read_text(), "cloud-setup installs CLAUDE.md")
    installed = home / ".claude/git-hooks/commit-msg"
    report(os.access(installed, os.X_OK), "cloud-setup installs executable commit-msg")
    configured = subprocess.run(
        ["git", "config", "--global", "--get-all", "core.hooksPath"], capture_output=True, text=True, env=env
    )
    report(configured.stdout.strip() == str(home / ".claude/git-hooks"), "cloud-setup sets one absolute hooksPath")
    for skill in sorted(p for p in (ROOT / "skills").iterdir() if p.is_dir()):
        diff = tree_diff(skill, home / ".claude/skills" / skill.name)
        report(not diff, f"cloud-setup installs skill {skill.name} {diff[:3]}")
    sample = tmp / "sample.md"
    sample.write_text("この説明は、テストです。\n")
    lint = subprocess.run(
        [sys.executable, str(home / ".claude/skills/yomiyasu/scripts/yomiyasu_lint.py"), "-"],
        input=sample.read_text(),
        capture_output=True,
        text=True,
    )
    report(lint.returncode == 0 and "見直し候補" in lint.stdout, f"installed yomiyasu lint runs {lint.stderr.strip()}")
    repo = tmp / "cloud"
    repo.mkdir()
    commit_flow_cases(repo, env=env)


with tempfile.TemporaryDirectory() as name:
    tmp = Path(name).resolve()
    bash_entry_cases(tmp)
    commit_msg_entry_cases(tmp)
    cloud_setup_cases(tmp)

print(f"\n{'all passed' if not failed else f'{failed} FAILED'}")
sys.exit(1 if failed else 0)
