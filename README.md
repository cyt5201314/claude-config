# claude-config

本机和 Claude Code 云端会话共用的 `CLAUDE.md`（用户级规则）和 commit 检查，只在这里维护。

## 本机

`~/.claude/CLAUDE.md` 是指向本仓库 `CLAUDE.md` 的软链接。改规则 = 编辑后 `git push`。

`~/.claude/hooks/require-commit-verify-rollback.py` 也是软链接，指向 `hooks/` 下的同名文件，在 `~/.claude/settings.json` 里注册成 PreToolUse Bash hook。

### pstack

- `~/.claude/rules` → `rules/`（整个目录软链接，`/pstack:setup-pstack` 整份重写 `pstack-models.md` 时也写进仓库）。
  - `pstack-models.md`：纯 Claude 的角色模型表，Claude app 等所有入口都用。
  - `pstack-effort.md`：Fable / Opus 的档位上限。
- `~/.claude/pstack-t3` → `pstack-t3/`：只在 T3 Code 里生效的多家族配置。`models.md` 替换上面的模型表，`bridge.md` 写 GPT / Gemini 怎么经 T3 `delegate_task` 派发。
- `~/.claude/hooks/pstack-t3-context.sh` → `hooks/` 同名文件，在 `settings.json` 里注册成 SessionStart hook：
  `CLAUDE_CODE_ENTRYPOINT=t3-code` 时输出一行 `[pstack-t3]` 提示去读 `bridge.md`，其他入口不输出。

新机器：

```bash
R=~/Documents/workspace/claude-config
ln -s $R/rules ~/.claude/rules
ln -s $R/pstack-t3 ~/.claude/pstack-t3
ln -s $R/hooks/pstack-t3-context.sh ~/.claude/hooks/pstack-t3-context.sh
# settings.json 的 hooks.SessionStart 加：{"hooks":[{"type":"command","command":"sh ~/.claude/hooks/pstack-t3-context.sh"}]}
```

## 云端

claude.ai/code → 输入框上方云图标 → 环境齿轮 → Setup script：

```bash
#!/bin/bash
curl -fsSL https://raw.githubusercontent.com/cyt5201314/claude-config/main/cloud-setup.sh | bash || true
```

`cloud-setup.sh` 装 `CLAUDE.md`，并把 commit 检查装成 git `commit-msg` hook（全局 `core.hooksPath`）。不走 Claude Code 的 hook：Anthropic 托管环境不跑用户级 settings 里的 hook。

`skills/` 下每个目录整包装到云端的 `~/.claude/skills/<名字>`（下载仓库 tarball，同名目录先删再放）。现有：`yomiyasu`（日语推敲，上游 nanaism，MIT）。本机 `~/.claude/skills/yomiyasu` 目前是另一份拷贝，改 skill 要两边一起改。

环境快照最多缓存约 7 天；push 后要立刻生效，就改一下 setup script 里的任意注释触发重建。
新会话里 `/context` 能看到 `/root/.claude/CLAUDE.md`，`git config --global core.hooksPath` 输出 `/root/.claude/git-hooks`，且 `ls ~/.claude/skills` 列出 `yomiyasu` 即生效。

## 验证

```bash
python3 tests/test_commit_check.py
```
