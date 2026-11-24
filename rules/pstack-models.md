# pstack model configuration. One line per role. Delete a line to fall back to the skill default.
# `inherit-parent` or `auto` as a value: the role runs on the parent chat model (omit Task `model`). Alias entries in a panel list still count toward its fan-out.
# defaults: 3
# budget: medium (high)
feature, refactoring: inherit-parent
bug-fix: inherit-parent
perf-issue: inherit-parent
hillclimb: inherit-parent
judgment and prose: fable high
arena runners: fable high, opus high
arena cross-judge pool: opus high, fable high
swarm workers: inherit-parent
interrogate reviewers: fable high, opus high
