# 截图清单与命名规范

状态：⬜ 待采集。采集时用 Chrome 实截（1600×950），深浅主题各一套；文件名小写连字符，带主题后缀。截图不得包含真实 AK/Secret、个人账号或无关浏览器标签。

| 文件名 | 内容 | 对应演示步骤 | 状态 |
| --- | --- | --- | --- |
| `01-workspace-dark.png` / `01-workspace-light.png` | 工作台全貌：七类开关、图例、顶栏数据来源状态 | A1/B1 | ⬜ |
| `02-isochrone-grid-dark.png` / `02-isochrone-grid-light.png` | 等时圈 + 服务区域网格色块 + 设施点 | A3/B3 | ⬜ |
| `03-blindspot-evidence.png` | 重点盲区格展开：最近设施、步行时间、依据、置信度、来源 | A4/B4 | ⬜ |
| `04-score-breakdown.png` | 类别评分三子项与权重、计分理由 | A5 | ⬜ |
| `05-bar-tooltip.png` | 覆盖评分柱状图悬浮提示 | A5 | ⬜ |
| `06-radar-dark.png` / `06-radar-light.png` | 七维类别得分雷达图 | A5 | ⬜ |
| `07-walking-route.png` | 悬浮卡步行路线折线（真实模式） | B5 | ⬜ |
| `08-ai-interpretation.png` | AI 解读面板：摘要/解释/汇报 + 证据引用 | A6 | ⬜ |
| `09-simulation.png` | 候选设施模拟前后对比 | A7 | ⬜ |
| `10-export-menu.png` | 四种导出菜单 | A8 | ⬜ |
| `11-execution-metrics.png` | 执行指标区：总耗时、API 调用、缓存命中、阶段耗时 | B3/B7 | ⬜ |
| `12-data-quality.png` | 数据质量披露区 | B6 | ⬜ |

## 采集与更新规则

- 每张截图在 [../demo-script.md](../demo-script.md) 中有对应步骤；新增功能时同步补行。
- 真实模式截图须顶栏显示"真实百度服务已连接"；离线截图须可见快照/非实时提示，二者不可混用。
- 采集完成后把状态改为 ✅ 并在 [../evidence-index.md](../evidence-index.md) E-19 更新。
