# 黄埔区红山街道海韵东路人工核查说明

## 核查对象

- 基准编号：`hongshan-haiyundonglu-20260921`
- 中心坐标：BD-09 `113.4872, 23.1068`
- 中心地址：广东省广州市黄埔区红山街道海韵东路
- 步行阈值：15 分钟
- 网格：4 × 4，共 16 个空间网格；菜市场、药店、小学、医疗服务各核查一次，共 64 个类别网格
- 真实报告：[`../reports/hongshan-haiyundonglu-20260921.json`](../reports/hongshan-haiyundonglu-20260921.json)
- 待标注文件：[`hongshan-haiyundonglu-20260921.json`](hongshan-haiyundonglu-20260921.json)
- 盲审图层：[`hongshan-haiyundonglu-20260921-review-grid.geojson`](hongshan-haiyundonglu-20260921-review-grid.geojson)

## 核查原则

先使用盲审图层和独立地图来源核查，不查看真实报告中的系统 `kind`、最近设施和判定依据，避免系统结果影响人工判断。

每个类别网格按以下规则填写：

- `normal`：存在 1 公里内同类设施，且最近有效步行路线不超过 15 分钟。
- `sparse`：仅满足“1 公里内有设施”或“15 分钟内可步行到达”其中一项。
- `critical`：1 公里内无同类设施，且最近有效步行路线超过 15 分钟。

核查时应记录小区出入口、围墙、铁路、厂区、河道和过街点等会造成步行绕行的现场条件。不要用直线距离直接代替步行路线。

## 填写方式

推荐从仓库根目录运行人工核查向导：

```bash
./.scratch/v2.1-hongshan-benchmark/review-wizard.sh
```

向导会按菜市场、药店、小学和医疗服务依次打开独立地图核查入口，每完成一格立即保存。可输入 `q` 中途退出，重新运行后会跳过已完成网格。64 项全部完成并经确认后，向导才会将基准改为 `verified` 并生成评估结果。

也可直接在待标注 JSON 中逐项填写：

```json
{
  "grid_id": "market-r1c1",
  "category": "market",
  "expected_kind": "normal",
  "evidence": {
    "source": "独立地图名称或现场核查",
    "checked_at": "2026-09-21",
    "reviewer": "核查人",
    "notes": "最近设施、实际步行时间及道路条件"
  }
}
```

64 项完成后，将顶层 `status` 从 `draft` 改为 `verified`。在完成全部标注前，不得把草稿评估结果描述为全网格准确率。

## 完成后评估

```bash
cd life-circle-assistant
python3 backend/scripts/evaluate_benchmark.py evaluate \
  --report docs/validation/reports/hongshan-haiyundonglu-20260921.json \
  --benchmark docs/validation/benchmarks/hongshan-haiyundonglu-20260921.json \
  --json-output docs/validation/results/hongshan-haiyundonglu-20260921.json \
  --markdown-output docs/validation/results/hongshan-haiyundonglu-20260921.md
```

## 本次运行记录

- 数据来源：百度地图 Web 服务真实模式
- 原始设施：75 条
- 归一化设施：71 条，其中医疗同址记录合并 4 条
- 服务区域：64 个，全部计算完成
- 综合生活圈指数：68
- 重点服务盲区：9 个
- 设施稀疏区：17 个
- 路线缓存命中：1002，新增真实步行调用：150
- 完整性：`complete`，无部分失败
- 凭证检查：报告与盲审材料不包含百度 AK、Secret 或浏览器 AK
