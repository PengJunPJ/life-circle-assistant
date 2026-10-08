# 现场演示脚本

每步三段：**操作** / **预期观察** / **证据指针**。路径 A 无需任何凭证，评审可当场复现；路径 B 需要有效百度 AK，用于证明真实地图能力。两条路径都不要手工解释隐含前提。

演示前统一确认：浏览器打开 `http://localhost:5173`，顶栏右侧状态灯与文字说明当前数据来源（真实百度服务 / 本地快照）。

## 路径 A：无凭证离线演示（约 3 分钟）

| # | 操作 | 预期观察 | 证据指针 |
| --- | --- | --- | --- |
| A1 | `cp .env.example .env`（AK 留空）后 `docker compose up --build`，打开 `:5173` | 容器健康、页面加载；顶栏提示地图服务未连接或本地快照 | [../../README.md](../../README.md) 快速运行 |
| A2 | 完成首次使用引导，确认默认中心点（黄埔区红山街道海韵东路样例） | 引导只要求确认中心，不要求凭证 | 用户故事：无凭证可完成闭环 |
| A3 | 保持默认七类设施，点击分析 | 生成等时圈、服务区域网格、评分与雷达图；界面与报告带"非实时数据/本地快照"提示 | [../releases/v2.2.0.md](../releases/v2.2.0.md)；[limitations.md](limitations.md) |
| A4 | 点击任一网格色块 | 展开最近同类设施、步行时间、分类依据、置信度与数据来源（snapshot） | [../../../docs/adr/0006-mvp设施类别与盲区判定标准.md](../../../docs/adr/0006-mvp设施类别与盲区判定标准.md) |
| A5 | 展开"设施覆盖评分"任一类别 | 数量/最近步行/空间分布三子项及权重、计分理由可见 | [../../../docs/adr/0011-可解释规则评分与数据质量提示.md](../../../docs/adr/0011-可解释规则评分与数据质量提示.md) |
| A6 | 打开 AI 规划助手，依次运行体检摘要、服务区域解释、汇报摘要 | 无模型密钥时输出规则模板结果，且引用报告内真实存在的网格/设施/分数 | [../../backend/app/ai_assistant.py](../../backend/app/ai_assistant.py) |
| A7 | 在规划建议中选择一个候选点运行模拟 | 展示模拟前后覆盖与评分变化，建议引用具体类别与网格 | [../architecture/v2-trustworthy-analysis.md](../architecture/v2-trustworthy-analysis.md) |
| A8 | 导出 JSON / CSV / GeoJSON / PDF | 四种导出均保留分析参数与数据质量说明 | [../releases/v2.0.0.md](../releases/v2.0.0.md) |

## 路径 B：真实百度模式演示（约 5 分钟）

| # | 操作 | 预期观察 | 证据指针 |
| --- | --- | --- | --- |
| B1 | 在 `.env` 填 `BAIDU_MAP_AK` 与 `VITE_BAIDU_MAP_AK`，`BAIDU_MAP_MODE=real`，`docker compose up --build`；在分析面板点击“验证 Web API” | `/api/health` 仅返回 `real_api_configured: true`，不会消耗配额；显式探活成功后界面显示地理编码接口已验证，浏览器底图状态单独展示 | [../../README.md](../../README.md) 模式说明 |
| B2 | 用地址搜索、地图点选、坐标输入三种方式各选一次中心 | 三种选点结果一致地驱动分析中心 | 用户故事 5 |
| B3 | 运行"正式分析"（24 方向等时圈） | 等时圈为真实路网步行边界而非圆形缓冲；执行指标区显示 API 调用、缓存命中、阶段耗时 | [../performance/v2-baseline.md](../performance/v2-baseline.md) |
| B4 | 查看重点盲区格证据 | 依据文案给出"步行超过阈值且 1 公里内无同类设施"，数据来源为 real_api | [algorithm-overview.md](algorithm-overview.md) 盲区规则 |
| B5 | 悬浮任一设施点，点击"显示步行路线" | 卡片锚定设施点并绘制真实步行折线（非直线） | [../releases/v2.1.0.md](../releases/v2.1.0.md) |
| B6 | 观察报告"数据质量"区 | 披露缓存命中、限流/超时/重试、降级估算与部分失败；无隐藏结论 | [../architecture/v2-trustworthy-analysis.md](../architecture/v2-trustworthy-analysis.md) |
| B7 | 运行一次定稿真实跑并归档 | 报告 JSON 存入 `docs/validation/reports/`，作为真实能力与执行指标证据 | [evidence-index.md](evidence-index.md) E-05 |

## 演示收尾话术（照读即可）

- 离线演示展示的是**合成样例**，用于验证完整交互闭环，不代表任何真实社区结论。
- 真实模式展示的步行等时圈与盲区判定来自百度 Web 服务实时测算；若命中缓存或种子，报告已显式披露。
- 沙涌长盛花园 64/64 核查仅为百度同源一致性证据；盲区识别的跨来源准确率与多社区泛化**尚未验证**，见 [limitations.md](limitations.md)。

## 截图与录屏

演示过程按 [screenshots/README.md](screenshots/README.md) 的清单与命名规范采集；录屏建议 3~5 分钟，覆盖 A3→A6 与 B3→B5。
