# claude-config

本机和 Claude Code 云端会话共用的 `CLAUDE.md`（用户级规则），只在这里维护。

## 本机

`~/.claude/CLAUDE.md` 是指向本仓库 `CLAUDE.md` 的软链接。改规则 = 编辑后 `git push`。

## 云端

claude.ai/code → 输入框上方云图标 → 环境齿轮 → Setup script：

```bash
#!/bin/bash
mkdir -p ~/.claude
curl -fsSL https://raw.githubusercontent.com/cyt5201314/claude-config/main/CLAUDE.md -o ~/.claude/CLAUDE.md || true
```

环境快照最多缓存约 7 天；push 后要立刻生效，就改一下 setup script 里的任意注释触发重建。
新会话里 `/context` 能看到 `/root/.claude/CLAUDE.md` 即生效。
