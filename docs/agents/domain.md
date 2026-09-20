# 领域文档

本文件说明各项工程技能在探索代码库时应如何使用本项目的领域文档。

## 开始探索前，请阅读以下文件

- 根目录下的 **`CONTEXT.md`**；或者
- 如果根目录存在 **`CONTEXT-MAP.md`**，阅读其中指向的、与当前主题相关的各个 `CONTEXT.md` 文件。
- **`docs/adr/`**：阅读涉及当前工作范围的 ADR。在多上下文项目中，还要检查 `src/<context>/docs/adr/` 下的上下文级决策。

如果这些文件不存在，**直接继续工作即可**。不要专门提示文件缺失，也不要建议提前创建。`/domain-modeling` 技能会在领域术语或架构决策真正确定时按需创建这些文件。

## 文件结构

单上下文项目（大多数项目）：

```
/
├── CONTEXT.md
├── docs/adr/
│   ├── 0001-event-sourced-orders.md
│   └── 0002-postgres-for-write-model.md
└── src/
```

多上下文项目（根目录存在 `CONTEXT-MAP.md`）：

```
/
├── CONTEXT-MAP.md
├── docs/adr/                          ← system-wide decisions
└── src/
    ├── ordering/
    │   ├── CONTEXT.md
    │   └── docs/adr/                  ← context-specific decisions
    └── billing/
        ├── CONTEXT.md
        └── docs/adr/
```

## 使用术语表中的词汇

当输出中出现领域概念时，例如问题标题、重构建议、假设或测试名称，应使用 `CONTEXT.md` 中定义的术语。不要随意使用术语表明确避免的同义词。

如果所需概念尚未出现在术语表中，这意味着：要么正在创造项目并未使用的说法，需要重新考虑；要么确实存在领域文档缺口，应记录下来并交给 `/domain-modeling` 处理。

## 标记 ADR 冲突

如果输出内容与已有 ADR 冲突，应明确指出，不要静默覆盖：

> _Contradicts ADR-0007 (event-sourced orders), but worth reopening because…_
