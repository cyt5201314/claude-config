#!/bin/bash
# 云端环境 setup script 的入口：装用户级 CLAUDE.md 和 commit 检查。本机不用跑。
set -eu

RAW="${CLAUDE_CONFIG_RAW:-https://raw.githubusercontent.com/cyt5201314/claude-config/main}"

mkdir -p ~/.claude/git-hooks
curl -fsSL "$RAW/CLAUDE.md" -o ~/.claude/CLAUDE.md
curl -fsSL "$RAW/hooks/require-commit-verify-rollback.py" -o ~/.claude/git-hooks/commit-msg
chmod +x ~/.claude/git-hooks/commit-msg
git config --global core.hooksPath ~/.claude/git-hooks
