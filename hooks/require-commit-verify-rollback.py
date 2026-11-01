#!/usr/bin/env python3
"""git commit 的 message 必须写明怎么验证、怎么回滚。同一份规则有两个入口：

- 本机：PreToolUse(Bash) hook，注册在 ~/.claude/settings.json，从 stdin 读将要跑的命令。
- 云端：git commit-msg hook，由 cloud-setup.sh 安装，argv[1] 是 message 文件。
  Anthropic 托管环境不跑用户级 settings 里的 hook，所以走 git 这一层。

来由：2026-11 CLAUDE.md「review 与提交」的 commit 规则只靠文字守不住，落到 hook。
判定：message 里要有以验证、回滚关键词开头的行（或 -m 参数）。缺了就 exit 2，stderr 回给模型。
不查：沿用已有 message 的提交（--no-edit、--fixup 等）、merge / revert 自动生成的 message；
本机入口下 -F 指向的文件读不到时放行（可能是同一条命令里才生成的）。
"""
import json
import re
import sys
from pathlib import Path

ARG = r"""(?:"[^"]*"|'[^']*'|\S+)"""
# git 要在命令位置，避免 grep "git commit" 这类字符串误中；(?!-) 排除 commit-tree / commit-graph
PATTERN = re.compile(
    rf"(?:^|[;&|(\n])\s*(?:\w+=\S*\s+)*git(?:\s+(?:-C\s+{ARG}|-c\s+{ARG}|--[\w-]+(?:={ARG})?))*\s+commit\b(?!-)"
)
EXEMPT = re.compile(r"(?:^|\s)(?:--no-edit|--fixup\b|--squash\b|--dry-run|-C\s|--reuse-message\b|-h|--help)")
FILE_ARG = re.compile(rf"(?:^|\s)(?:-F\s*|--file[=\s])({ARG})")
AUTO_GENERATED = re.compile(r'(?:Merge |Revert "|fixup! |squash! |amend! )')

LINE_START = r"""(?:^|["']|\\n)[\s\-*]*"""
REQUIRED = {
    "验证": re.compile(LINE_START + r"(?:验证|驗證|検証|verif(?:y|ied|ication))", re.I | re.M),
    "回滚": re.compile(LINE_START + r"(?:回滚|回滾|ロールバック|roll\s*back|revert)", re.I | re.M),
}


def require_labels(message):
    missing = [name for name, pattern in REQUIRED.items() if not pattern.search(message)]
    if missing:
        print(
            f"已拦截：commit message 缺少{'、'.join(missing)}说明（CLAUDE.md「review 与提交」）。"
            "请在正文加独立的行再提交：\n"
            "Verified: <跑了什么、结果如何>\n"
            "Rollback: <怎么撤销，如 git revert 这个提交>",
            file=sys.stderr,
        )
        sys.exit(2)


def read_message_file(flags, tail, cwd):
    """-F <文件> 返回文件内容；-F - 的 message 在命令里，返回 tail；读不到返回 None。"""
    match = FILE_ARG.search(flags)
    if not match:
        return tail
    name = match.group(1).strip("\"'")
    if name == "-":
        return tail
    try:
        return (Path(cwd).expanduser() / Path(name).expanduser()).read_text()
    except (OSError, UnicodeDecodeError):
        return None


def check_bash_command(data):
    command = (data.get("tool_input") or {}).get("command") or ""
    for match in PATTERN.finditer(command):
        tail = command[match.end():]
        flags = tail.split("\n", 1)[0]
        if EXEMPT.search(flags):
            continue
        message = read_message_file(flags, tail, data.get("cwd") or ".")
        if message is not None:
            require_labels(message)


def check_commit_msg_file(path):
    message = Path(path).read_text(encoding="utf-8", errors="replace")
    if not AUTO_GENERATED.match(message):
        require_labels(message)


if len(sys.argv) > 1:
    check_commit_msg_file(sys.argv[1])
else:
    check_bash_command(json.load(sys.stdin))
