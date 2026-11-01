# claude-config

本机和 Claude Code 云端会话共用的 `CLAUDE.md`（用户级规则）和 commit 检查，只在这里维护。

## 本机

`~/.claude/CLAUDE.md` 是指向本仓库 `CLAUDE.md` 的软链接。改规则 = 编辑后 `git push`。

`~/.claude/hooks/require-commit-verify-rollback.py` 也是软链接，指向 `hooks/` 下的同名文件，在 `~/.claude/settings.json` 里注册成 PreToolUse Bash hook。

## 云端

claude.ai/code → 输入框上方云图标 → 环境齿轮 → Setup script：

```bash
#!/bin/bash
curl -fsSL https://raw.githubusercontent.com/cyt5201314/claude-config/main/cloud-setup.sh | bash || true
```

`cloud-setup.sh` 装 `CLAUDE.md`，并把 commit 检查装成 git `commit-msg` hook（全局 `core.hooksPath`）。不走 Claude Code 的 hook：Anthropic 托管环境不跑用户级 settings 里的 hook。

环境快照最多缓存约 7 天；push 后要立刻生效，就改一下 setup script 里的任意注释触发重建。
新会话里 `/context` 能看到 `/root/.claude/CLAUDE.md`，且 `git config --global core.hooksPath` 输出 `/root/.claude/git-hooks` 即生效。

## 验证

```bash
python3 tests/test_commit_check.py
```
