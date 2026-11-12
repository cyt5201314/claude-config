# pstack 的 Claude 档位上限

跑 `/pstack:*` 时，poteto-mode「按任务升降档」的结果受下面上限约束（成本是用户实测的相对值）：

- Fable 5.2：常用 `medium` / `high`，按需切换（两者差距不大）。`xhigh` 成本约 2.5 倍，只给极难任务（跨模块设计、迁移 / RLS / 权限、并发、原因不明的 bug），并在汇报里写明理由。`max` 约 8 倍，不用，除非用户点名。poteto-mode「最难的改动升一档」对 Fable 也受此限。
- Opus 5.5：`high`。`xhigh` 成本翻倍以上，只在任务特别难时由用户把线程切过去，不自己升。
