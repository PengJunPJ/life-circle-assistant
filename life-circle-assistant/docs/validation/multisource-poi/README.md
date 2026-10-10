# 多源 POI 验证材料

本目录只用于经许可的、数据最小化的百度/高德交叉验证。

- [`source-registry.yaml`](source-registry.yaml)：来源角色、坐标系、优先级和运行时开关；当前 `runtime_enabled: false`。
- [`fixture.json`](fixture.json)：审计 fixture manifest；当前等待真实采集，`pairs` 为空，不代表验证已完成。
- [`../../architecture/multi-source-poi-reconciliation.md`](../../architecture/multi-source-poi-reconciliation.md)：实体匹配规则、冲突/时效策略和启用门槛。

## Fixture 样本字段

取得书面许可并完成 50–100 对人工标签后，`pairs` 使用最小特征格式，不保存第三方原始 POI 字段：

```json
{
  "pair_id": "sha256:截断后的非可逆样本编号",
  "features": {
    "distance_m": 18.5,
    "name_score": 0.91,
    "address_score": 0.88,
    "category_match": true,
    "coordinate_system_compatible": true
  },
  "label": "match",
  "reviewer": "reviewer-a",
  "reviewed_at": "2026-10-10"
}
```

`label` 只能为 `match`、`non_match`、`conflict`。fixture manifest 需设置 `status: ready`、`permission_status: written_permission_received`，记录采集时间、查询指纹和许可工单引用（不记录 Key）。每一对记录都需人工复核者与复核时间。

在 manifest 条件和 50–100 对样本满足前，评估脚本会拒绝运行。不要把测试代码中的人工构造样例拷贝进真实 fixture。
