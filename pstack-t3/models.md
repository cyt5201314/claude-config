# pstack model configuration. One line per role. Delete a line to fall back to the skill default.
# `inherit-parent` or `auto` as a value: the role runs on the parent chat model (omit Task `model`). Alias entries in a panel list still count toward its fan-out.
# gpt-* / gemini-* values are dispatched through T3 Code `delegate_task`, not the Agent tool. Read ~/.claude/pstack-t3/bridge.md before any spawn. T3 Code only; replaces ~/.claude/rules/pstack-models.md there.
# budget: medium (high)
feature, refactoring: gpt-6.1-sol max
bug-fix: gpt-6.1-sol max
perf-issue: gpt-6.1-sol max
hillclimb: gpt-6.1-sol max
judgment and prose: fable high
hardest tasks: fable high
how explorer: gpt-6.1-sol xhigh
how explainer: fable high
why investigators: gpt-6.1-sol xhigh
why synthesizer: fable high
reflect tooling: gpt-6.1-sol xhigh
reflect judgment, divergent, synthesizer: fable high
arena runners: fable high, gpt-6-astra max
arena cross-judge pool: gemini-4-carbon high, gpt-6-astra max
swarm workers: gpt-6.1-sol xhigh
architect runners: fable high, gpt-6-astra max, gemini-4-carbon high
interrogate reviewers: fable high, gpt-6-astra max, gemini-4-carbon high
