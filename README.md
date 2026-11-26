# claude-config

本机和 Claude Code 云端会话共用的 `CLAUDE.md`（用户级规则）和 commit 检查，只在这里维护。

## 本机

`~/.claude/CLAUDE.md` 是指向本仓库 `CLAUDE.md` 的软链接。改规则 = 编辑后 `git push`。

`~/.claude/hooks/require-commit-verify-rollback.py` 也是软链接，指向 `hooks/` 下的同名文件，在 `~/.claude/settings.json` 里注册成 PreToolUse Bash hook。

### 记忆闸门

`hooks/memory-gate.py`：用户在当前这条消息里批准（「记住」「记 1、3」「把第 2 条记忆删掉」等），才能改 `~/.claude/projects/*/memory/`；否则拦下，让模型把候选写进汇报。批准过的改动自动 commit 到本地记忆仓库，message 里带会话 id 和用户批准时的原话。规则写在 `CLAUDE.md`「记忆」。

- `~/.claude/hooks/memory-gate.py` 软链接到这里，在 `~/.claude/settings.json` 的 `UserPromptSubmit`、`PreToolUse`、`PostToolUse` 各注册一次（后两个 matcher：`Write|Edit|MultiEdit|NotebookEdit|Bash`）。
- 记忆仓库的工作区是 `~/.claude/projects`，`.gitignore` 只放行 `*/memory/`；git 目录在 `~/Documents/workspace/claude-memory.git`，不设 remote（记忆里有公司信息，本仓库是公开的）。看记录：`git -C ~/.claude/projects log -p`；撤销一次改动：`git -C ~/.claude/projects revert <commit>`。
- 测试：`python3 tests/test_memory_gate.py`。

新机器：

```bash
ln -s ~/Documents/workspace/claude-config/hooks/memory-gate.py ~/.claude/hooks/memory-gate.py
git init --separate-git-dir ~/Documents/workspace/claude-memory.git ~/.claude/projects
printf '/*\n!/.gitignore\n!/*/\n/*/*\n!/*/memory/\n' > ~/.claude/projects/.gitignore
```

### pstack

- `~/.claude/rules` → `rules/`（整个目录软链接，`/pstack:setup-pstack` 整份重写 `pstack-models.md` 时也写进仓库）。
  - `pstack-models.md`：纯 Claude 的角色模型表，Claude app 等所有入口都用。
  - `pstack-effort.md`：Fable / Opus 的档位上限。
  - `pstack-external.md`：本机会话里给方案 / review 面板加 GPT、Gemini 席位，经 `pstack-ext/seat.py` 调本机 CLI。
  - `skills/sharpen`、`skills/reframe`：pstack 同名 skill 的中文版（原版写的是英文，跑出来的改写提示词也是英文）。敲 `/sharpen`、`/reframe` 走中文版，`/pstack:sharpen`、`/pstack:reframe` 仍是原版。pstack 升级后 `tests/test_pstack_zh.py` 报原文变了，就对照新原文重译，再更新测试里的版本和 hash。
  - `pstack-web.md`：跑 pstack 改前端 / UI 前先用 modern-web-guidance 查现代原生 API（本机 skill 在 `~/.agents/skills/modern-web-guidance`，不在本仓库）。
- `~/.claude/pstack-ext` → `pstack-ext/`：`seat.py` 用 T3 Code 装在 `~/.t3/tools` 下的 Codex / Antigravity CLI 跑一个外部席位，复用它们的登录；Gemini 席位和带 `--write` 的 GPT 席位拒绝在仓库主 checkout 里跑。

新机器：

```bash
R=~/Documents/workspace/claude-config
ln -s $R/rules ~/.claude/rules
ln -s $R/pstack-ext ~/.claude/pstack-ext
ln -s $R/skills/yomiyasu ~/.claude/skills/yomiyasu
ln -s $R/skills/lark-task-board ~/.claude/skills/lark-task-board
ln -s $R/skills/kien-mode ~/.claude/skills/kien-mode
ln -s $R/skills/sharpen ~/.claude/skills/sharpen
ln -s $R/skills/reframe ~/.claude/skills/reframe
```

`lark-task-board` 还要 `lark-cli`（已用本人身份登录，有 task 读写权限）和本机配置 `~/.claude/lark-task-board.json`，格式见 `skills/lark-task-board/SKILL.md` 的「配置」。配置里是清单 ID 和项目名，不进本仓库（本仓库是公开的）。

## 云端

claude.ai/code → 输入框上方云图标 → 环境齿轮 → Setup script：

```bash
#!/bin/bash
curl -fsSL https://raw.githubusercontent.com/cyt5201314/claude-config/main/cloud-setup.sh | bash || true
```

`cloud-setup.sh` 装 `CLAUDE.md`，并把 commit 检查装成 git `commit-msg` hook（全局 `core.hooksPath`）。不走 Claude Code 的 hook：Anthropic 托管环境不跑用户级 settings 里的 hook。

`skills/` 下每个目录整包装到云端的 `~/.claude/skills/<名字>`（下载仓库 tarball，同名目录先删再放）。现有：`yomiyasu`（日语推敲，上游 nanaism，MIT）、`lark-task-board`（个人 Lark 任务面板：加任务前判重、判父子和关联；云端没有 `lark-cli` 和配置，装过去也只会报「不能用」）、`kien-mode`（本人的工作方式，只在敲 `/kien-mode` 时加载）、`sharpen` / `reframe`（pstack 同名 skill 的中文版）。本机 `~/.claude/skills/yomiyasu` 是指向 `skills/yomiyasu` 的软链接，改 skill = 改这里再 `git push`。

环境快照最多缓存约 7 天；push 后要立刻生效，就改一下 setup script 里的任意注释触发重建。
新会话里 `/context` 能看到 `/root/.claude/CLAUDE.md`，`git config --global core.hooksPath` 输出 `/root/.claude/git-hooks`，且 `ls ~/.claude/skills` 列出 `yomiyasu` 即生效。

## 验证

```bash
python3 tests/test_commit_check.py
python3 tests/test_seat.py          # 外部席位脚本的参数和隔离检查，不联网
python3 tests/test_seat.py --live   # 另外真的让 GPT、Gemini 各审一段埋了 bug 的代码（花额度）
python3 tests/test_lark_task_board.py   # 任务面板脚本的 plan 校验和写入内容，假 lark-cli，不联网
python3 tests/test_pstack_zh.py         # 中文版 sharpen / reframe 的原文有没有随 pstack 升级变掉
```
