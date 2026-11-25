# pstack 的外部席位（GPT / Gemini，经本机 CLI）

跑 `/pstack:*` 的方案和 review 面板时适用。云端会话没有这些 CLI，也不适用。

pstack 的 Claude Code 适配文档把非 Claude 的值降成会话模型，等于没换家。下面的席位不走那条，改用 `~/.claude/pstack-ext/seat.py` 调本机 CLI（T3 Code 装在 `~/.t3/tools` 下的 Codex 和 Antigravity，复用它们的登录）。

## 席位

加在 `pstack-models.md` 对应行之后，不替换那一行的 Claude 席位：

- `arena runners`：加 `gpt-6.2-astra max`、`gemini-4-carbon high`
- `arena cross-judge pool`：`gpt-6.2-astra max`、`gemini-4-carbon high`。只派一个，照下面「arena 裁判」
- `interrogate reviewers`：不加外部席位，只派 `pstack-models.md` 那一行的 Claude 席位，也不套下面「去掉写它的那一家」（不然审 Claude 写的代码一个席位都不剩）
- poteto-mode 的「Diverse review and design panels」：同 `arena runners`

写代码的角色（feature、bug-fix、swarm workers 等）不加外部席位。Feature 第 4 步用 arena 写实现时同样不加：arena runners 只派 Claude 席位；外部席位只进出方案 / 设计 / 审查的面板。

## 家族

`claude-*` 与 `opus` / `sonnet` / `haiku` / `fable` 是 Claude；`gpt-*` 是 GPT；`gemini-*` 是 Gemini；`grok-*` / `composer-*` 是 Grok。arena 裁判「不同家族」、面板多样性都按这个判。审查一段代码时，去掉写它的那一家的席位。

## 档位

- 非 Claude 的行写的是最终档位，不套 poteto-mode「判断降一档、例行降两档」的调整。唯一例外：极难任务可升一档（GPT `max` → `ultra`）。
- GPT 与 Claude 档位不等价：GPT `max` ≈ Claude high～xhigh，GPT `xhigh` ≈ Claude medium。
- Claude（Fable / Opus）的档位上限照 `~/.claude/rules/pstack-effort.md`。

## arena 裁判

照 arena Phase C 只派一个只读裁判：`gpt-6.2-astra max`（默认只读，不用隔离目录）。它照「退出码」算掉线后才换池里的下一个 `gemini-4-carbon high`，这是裁判池的顺位，不算擅自换家族；两个都掉线就照 Phase C 跳过裁判，并在汇报里写明。

## brief

非 Claude 的席位读不到 `~/.claude`，也没有 skill 机制，brief 必须自带：

- 开头：先完整读 poteto-mode 的 SKILL.md（含 Principles 索引），再读 `agents/poteto-agent.md`，以 poteto-agent 身份工作；用到某条原则时读对应 `skills/principle-*/SKILL.md`。给绝对路径，用 `~/.claude/plugins/cache/cursor-plugins/pstack/*/` 下当前版本解析。
- `~/.claude/CLAUDE.md`「pstack poteto-mode」一节的口径（注释、计划落盘位置）。
- 本任务的判据表（CLAUDE.md「开发流程」），它就是交付的 bar；不向用户提问，判据定不了的写进交付里。
- 不派子任务、不 push、不合 main、不改 `~/.claude`；写代码的任务 commit 在自己分支上。

## 派发

brief 写成文件（放 scratchpad），再用 Bash 跑，`run_in_background: true`，多个席位同一条消息发出：

```bash
python3 ~/.claude/pstack-ext/seat.py gpt    --model gpt-6.2-astra   --effort max  --cwd <目录> --brief <brief 文件> --out <结果文件>
python3 ~/.claude/pstack-ext/seat.py gemini --model gemini-4-carbon --effort high --cwd <目录> --brief <brief 文件> --out <结果文件>
```

跑完读 `--out` 的文件，它就是这个席位的交付。脚本最后会打印 `--cwd` 的 `git status`。

- **GPT 默认只读**：能读文件、跑命令，写不了（Codex `read-only` 沙箱，2026-11-19 实测拦住了写文件）。裁判和只看代码的审查用默认；要自己写产物的席位（如 arena runner）加 `--write`，这时 `--cwd` 必须是它自己的 worktree。
- **Gemini 关不掉写权限**：带 `--sandbox` 照样写文件、跑命令（同日实测）。`--cwd` 必须是它自己的 git worktree，或一个上下都没有 `.git` 的目录（不带 `.git` 的副本）；主 checkout、装着仓库的父目录、git 报错的目录，脚本都拒绝（退出码 2）。带 `--write` 的 GPT 席位同样受这条检查。brief 里写明「只在当前目录内读写」；跑完看脚本打印的 `git status`，出现 brief 没要求的改动就在汇报里写明。
- **Gemini 不能用 `--mode plan`**：它不给结论，只写一份计划文件等批准。

## 退出码

`0` 成功；`2` 参数或隔离检查不过；`4` 找不到 CLI；`5` CLI 报错（登录、额度、模型名）；`6` 超时（默认 1500 秒，`--timeout` 改）。

`5` 且 stderr 显示是模型或额度错误：先换同家族备选重跑（`gpt-6.2-astra` ↔ `gpt-6.2-sol`）。`4`、`6`、其他原因的 `5`，或换了还失败：这个席位算掉线，照 pstack 的掉线规则继续（arena 至少留两个 runner），并在汇报里写明哪一家没出结果和退出码。不擅自换到别的家族，不用 Claude 顶替后说成外部席位。
