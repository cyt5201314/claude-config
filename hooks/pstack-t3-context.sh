#!/bin/sh
# T3 Code 会话才有 GPT / Gemini 可派，pstack 的多家族配置只在这里生效；
# Claude app 等其他入口不输出任何东西，pstack 用 ~/.claude/rules/pstack-models.md（纯 Claude）。
[ "$CLAUDE_CODE_ENTRYPOINT" = "t3-code" ] || exit 0
[ -f "$HOME/.claude/pstack-t3/bridge.md" ] || exit 0
echo "[pstack-t3] 本会话在 T3 Code。跑 /pstack:* 时，派任何子代理之前先读 ~/.claude/pstack-t3/bridge.md：它让 ~/.claude/pstack-t3/models.md 整份替换 ~/.claude/rules/pstack-models.md，gpt-* / gemini-* 席位走 T3 delegate_task。"
