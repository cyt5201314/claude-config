# pstack 的外部席位（GPT / Gemini，经本机 CLI）

跑 `/pstack:*` 的方案和 review 面板时适用，T3 Code 会话除外：那里照 `~/.claude/pstack-t3/bridge.md` 走 `delegate_task`（会话开头有 `[pstack-t3]` 提示的就是）。云端会话没有这些 CLI，也不适用。

pstack 的 Claude Code 适配文档把非 Claude 的值降成会话模型，等于没换家。下面的席位不走那条，改用 `~/.claude/pstack-ext/seat.py` 调本机 CLI（T3 Code 装在 `~/.t3/tools` 下的 Codex 和 Antigravity，复用它们的登录）。

## 席位

加在 `pstack-models.md` 对应行之后，不替换那一行的 Claude 席位：

- `arena runners`：加 `gpt-6.2-astra max`、`gemini-4-carbon high`
- `arena cross-judge pool`：`gemini-4-carbon high`、`gpt-6.2-astra max`。两个都派，各出一份打分，照 `bridge.md`「arena 裁判」一节
- `interrogate reviewers`：加 `gpt-6.2-astra max`、`gemini-4-carbon high`
- poteto-mode 的「Diverse review and design panels」：同 `arena runners`

写代码的角色（feature、bug-fix、swarm workers 等）不加外部席位。

家族、档位、brief 自带内容、不可用时的回退，照 `bridge.md` 的「家族」「档位」「brief」「不可用时」各节，只有派发方式换成下面这套。

## 派发

brief 写成文件（放 scratchpad），再用 Bash 跑，`run_in_background: true`，多个席位同一条消息发出：

```bash
python3 ~/.claude/pstack-ext/seat.py gpt    --model gpt-6.2-astra   --effort max  --cwd <目录> --brief <brief 文件> --out <结果文件>
python3 ~/.claude/pstack-ext/seat.py gemini --model gemini-4-carbon --effort high --cwd <目录> --brief <brief 文件> --out <结果文件>
```

跑完读 `--out` 的文件，它就是这个席位的交付。脚本最后会打印 `--cwd` 的 `git status`。

- **GPT 默认只读**：能读文件、跑命令，写不了（Codex `read-only` 沙箱，2026-11-19 实测拦住了写文件）。裁判和只看代码的审查用默认；要自己写产物或复现脚本的席位（arena runner、interrogate adversary）加 `--write`，这时 `--cwd` 必须是它自己的 worktree。
- **Gemini 关不掉写权限**：带 `--sandbox` 照样写文件、跑命令（同日实测）。`--cwd` 必须是它自己的 git worktree，或一个上下都没有 `.git` 的目录（不带 `.git` 的副本）；主 checkout、装着仓库的父目录、git 报错的目录，脚本都拒绝（退出码 2）。带 `--write` 的 GPT 席位同样受这条检查。brief 里写明「只在当前目录内读写」；跑完看脚本打印的 `git status`，出现 brief 没要求的改动就在汇报里写明。
- **Gemini 不能用 `--mode plan`**：它不给结论，只写一份计划文件等批准。
- interrogate 的发现照旧要在 Verify 阶段由总指挥重跑命令确认，外部席位自称跑过也一样。

## 退出码

`0` 成功；`2` 参数或隔离检查不过；`3` 在 T3 Code 里；`4` 找不到 CLI；`5` CLI 报错（登录、额度、模型名）；`6` 超时（默认 1500 秒，`--timeout` 改）。

`4` / `5` / `6`：这个席位算掉线，照 pstack 的掉线规则继续（arena 至少留两个 runner），并在汇报里写明哪一家没出结果和退出码。不擅自换到别的家族，不用 Claude 顶替后说成外部席位。
