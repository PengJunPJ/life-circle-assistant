# 问题追踪：本地 Markdown

本项目的需求和问题以 Markdown 文件形式保存在 `.scratch/` 目录中。

## 文件约定

- 每个功能使用一个独立目录：`.scratch/<feature-slug>/`
- 需求规格文件为 `.scratch/<feature-slug>/spec.md`
- 实现问题按照一票一文件的方式保存在 `.scratch/<feature-slug>/issues/<NN>-<slug>.md`，从 `01` 开始编号，不使用合并后的总问题文件
- 每个问题文件顶部附近使用 `Status:` 行记录分流状态，具体标签见 `triage-labels.md`
- 评论和沟通历史追加到文件末尾的 `## Comments` 标题下

## 技能要求“发布到问题追踪系统”时

在 `.scratch/<feature-slug>/` 下创建新文件；如果目录不存在则一并创建。

## 技能要求“获取相关问题单”时

读取指定路径的文件。通常由用户直接提供文件路径或问题编号。

## Wayfinding 操作

以下约定供 `/wayfinder` 使用。**地图文件**为每个问题单维护一个对应的**子文件**。

- **地图文件**：`.scratch/<effort>/map.md`，正文包含 Notes、Decisions-so-far 和 Fog 部分。
- **子问题单**：`.scratch/<effort>/issues/NN-<slug>.md`，从 `01` 开始编号，正文记录待解决问题。使用 `Type:` 行记录问题类型（`research`/`prototype`/`grilling`/`task`），使用 `Status:` 行记录状态（`claimed`/`resolved`）。
- **阻塞关系**：在文件顶部附近使用 `Blocked by: NN, NN` 行记录前置问题。当列出的所有文件都为 `resolved` 时，该问题单解除阻塞。
- **前沿问题**：扫描 `.scratch/<effort>/issues/`，查找处于开放状态、未被阻塞且未被认领的问题单，优先处理编号最小的问题。
- **认领**：开始工作前，将 `Status:` 设置为 `claimed` 并保存。
- **解决**：在 `## Answer` 标题下追加答案，将 `Status:` 设置为 `resolved`，然后在 `map.md` 的 Decisions-so-far 中追加上下文指针（摘要和链接）。
