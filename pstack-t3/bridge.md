# pstack × T3 Code 桥接

仅在 T3 Code 会话里跑 `/pstack:*`（含它派出的子代理）时适用；SessionStart hook `~/.claude/hooks/pstack-t3-context.sh` 只在 T3 会话里提示读本文件。与 pstack 自带的 Claude Code 适配文档冲突时以本文件为准。

## 模型表

本目录的 `models.md` 整份替换 `~/.claude/rules/pstack-models.md`（后者是 Claude app 用的纯 Claude 版）。pstack 让你读模型规则时，读 `models.md`。

## 派发

`models.md` 里的非 Claude 值不走 `Agent` 工具（适配文档会把它们降成会话模型，等于没换家），改走 T3 的 `delegate_task`：

| 值的前缀 | 派发方式 | 限制 |
| --- | --- | --- |
| `gpt-*` | `target.providerInstanceId` = displayName「ChatGPT - Personal」的 codex 实例（id 用 `orchestrator_capabilities` 查，别写死），`model` = slug，`options.reasoningEffort` = 档位 | 会改代码的任务用 `isolation: "worktree"` |
| `gemini-*` | `providerInstanceId: "antigravity"`，`options.thinking_level` = 档位（只有 low / medium / high） | 不跑 shell：Antigravity 每条 shell 命令都要人工批准，会卡住。审查、裁判只读文件给结论；arena / architect 的 runner 只写自己那一份输出文件（改文件不用批准） |

Gemini 不能跑 `git diff`：派它审查或当裁判前，总指挥先把 diff、候选方案写成文件（放 scratchpad），brief 里给绝对路径。

## 回交

`gpt-*` 的写代码任务在自己的 worktree 里：做完在该 worktree 的分支上 commit，最后一行报 `worktree <路径>, branch <名>, HEAD <SHA>`。总指挥在自己的 checkout 里 `git merge` / `cherry-pick` 那个分支再验证、审查；不信它的「done」，自己看 diff。

Claude 值（`fable` / `opus` / `sonnet` / `haiku`）照旧用 `Agent`，`subagent_type: "pstack:poteto-agent"` 或 skill 指定的类型。

## brief

非 Claude 的子代理读不到 `~/.claude`，也没有 skill 机制，brief 必须自带：

- 开头：先完整读 poteto-mode 的 SKILL.md（含 Principles 索引），再读 `agents/poteto-agent.md`，以 poteto-agent 身份工作；用到某条原则时读对应 `skills/principle-*/SKILL.md`。给绝对路径，用 `~/.claude/plugins/cache/cursor-plugins/pstack/*/` 下当前版本解析。
- `~/.claude/CLAUDE.md`「pstack poteto-mode」一节的口径（注释、review 处理、计划落盘位置）。
- 不派子任务、不 push、不合 main、不改 `~/.claude`；写代码的任务 commit 在自己分支上（见「回交」）。

## 家族

`claude-*` 与 `opus` / `sonnet` / `haiku` / `fable` 是 Claude；`gpt-*` 是 GPT；`gemini-*` 是 Gemini；`grok-*` / `composer-*` 是 Grok。arena 裁判「不同家族」、面板多样性都按这个判。审查一段代码时，去掉写它的那一家的席位。

## 档位

- 非 Claude 的行写的是最终档位，不套 poteto-mode「判断降一档、例行降两档」的调整。唯一例外：极难任务可升一档（GPT `max` → `ultra`）。
- GPT 与 Claude 档位不等价：GPT `max` ≈ Claude high～xhigh，GPT `xhigh` ≈ Claude medium。
- Claude（Fable / Opus）的档位上限照 `~/.claude/rules/pstack-effort.md`。

## 不可用时

`delegate_task` 报模型或额度错误：先换同家族备选（Astra ↔ Sol），再不行按 pstack 的回退走并在汇报里写明。不擅自换到别的家族。
