# pstack model configuration. One line per role. Delete a line to fall back to the skill default.
# `inherit-parent` or `auto` as a value: the role runs on the parent chat model (omit Task `model`). Alias entries in a panel list still count toward its fan-out.
# gpt-* / gemini-* values are dispatched through T3 Code `delegate_task`, not the Agent tool. Read ~/.claude/pstack-t3/bridge.md before any spawn. T3 Code only; replaces ~/.claude/rules/pstack-models.md there.
# defaults: 3
# budget: medium (high)
feature, refactoring: opus xhigh
bug-fix: opus xhigh
perf-issue: opus xhigh
hillclimb: opus xhigh
judgment and prose: fable high
arena runners: fable high, gpt-6.2-astra max, gemini-4-carbon high
arena cross-judge pool: gemini-4-carbon high, gpt-6.2-astra max
swarm workers: gpt-6.2-sol xhigh
interrogate reviewers: fable high, gpt-6.2-astra max, gemini-4-carbon high
