# 统一账本区域折叠入口

Status: resolved

## 复现

使用本地 Vite 服务加载真实 `ReportPanel` 组件和报告样例，在 Chromium 测量三个折叠标题。

| 入口 | 左边缘 | 字号 | 行高 |
| --- | --- | --- | --- |
| 调用预算和版本 | 35px | 16px | normal |
| 人工账单结算与历史 | 35px | 11px | 18.15px |
| 未决调用与计费核对 | 47px | 10px | 16.5px |

浏览器断言失败：三个折叠入口的左边缘、字号或行高不一致。

## 原因

预算入口未定义文字样式；结算与未决调用组件分别使用不同字号；未决调用组件默认左右外边距为 12px，且位于账本区域外。该组件也用于对话工作区，修正应限定在报告账本内。

## Comments

- 2026-10-15：完成浏览器复现及独立字号、外边距探针，开始修正报告账本的展示容器。

## Answer

报告账本内的三个入口统一放在同一容器，使用一致的 12px 字号、行高、箭头、标题高度、分隔线和键盘焦点。移除该区域的额外缩进；执行编号单独展示并支持换行，预算和版本按两列对齐，结算状态占满整行。样式限定在报告账本容器。

验证通过：

- Chromium 在 1440px、390px、320px 下分别验证深浅主题：左边缘、文本起点、字号、行高、箭头及标题高度一致。
- 使用 Enter 和空格展开、收起，检查箭头方向；展开预算、结算表单、长账单引用及 64 位用量指纹后没有横向溢出。
- 使用浏览器拦截提供的模拟响应，验证账本与结算历史读取、未决调用检查。
- `npm test -- src/components/ReportPanel.test.ts src/components/ExecutionSettlementReview.test.ts src/components/ExecutionCheckpointReview.test.ts`：38 项测试通过。
- `npm run typecheck`、`npm run lint`、`npm run build` 通过。

效果：[深色](../artifacts/ledger-dark.png)、[浅色](../artifacts/ledger-light.png)。
