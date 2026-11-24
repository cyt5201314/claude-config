# pstack 改 UI 时的原生 API 优先

跑 `/pstack:*`（含它派出的子代理）改前端 / UI 时，写代码前先用 modern-web-guidance 查现代原生 API，不凭记忆写老方案：

- `npx modern-web-guidance@latest search "<需求>"` 拿候选，再 `retrieve "<id>"` 读一篇；一次只取需要的那篇。
- Baseline 目标用默认的 Widely available，不在这里写年份；`set-allow-volatile-features` / `set-allow-origin-trials` 不开。想用更新的特性时，在该项目单独放行并在汇报里写明。
- 原生 API 不一定优于项目已有的库；项目已有同类封装时复用现有的，不为「原生」另起一套。
- iOS Safari 是兼容性重点，涉及新特性要在汇报里写「没在真机 / Safari 验证」或附验证结果。
