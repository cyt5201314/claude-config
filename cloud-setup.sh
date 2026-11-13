#!/bin/bash
# 云端环境 setup script 的入口：装用户级 CLAUDE.md、commit 检查和 skills/ 下的 skill。本机不用跑。
set -euo pipefail

RAW="${CLAUDE_CONFIG_RAW:-https://raw.githubusercontent.com/cyt5201314/claude-config/main}"
TARBALL="${CLAUDE_CONFIG_TARBALL:-https://codeload.github.com/cyt5201314/claude-config/tar.gz/main}"

mkdir -p ~/.claude/git-hooks
curl -fsSL "$RAW/CLAUDE.md" -o ~/.claude/CLAUDE.md
curl -fsSL "$RAW/hooks/require-commit-verify-rollback.py" -o ~/.claude/git-hooks/commit-msg
chmod +x ~/.claude/git-hooks/commit-msg
git config --global core.hooksPath ~/.claude/git-hooks

# skill 是多文件目录，raw 地址一个个拉不现实，整包下载后只取 skills/ 这一层
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
curl -fsSL "$TARBALL" | tar -xzf - -C "$tmp"
mkdir -p ~/.claude/skills
for src in "$tmp"/*/skills/*/; do
  [ -d "$src" ] || continue
  name="$(basename "$src")"
  rm -rf ~/.claude/skills/"$name"
  cp -R "$src" ~/.claude/skills/"$name"
done
