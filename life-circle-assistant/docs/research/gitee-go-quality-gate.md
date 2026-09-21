# Gitee Go 质量门禁落地调研

> 调研日期：2026-09-21  
> 范围：Gitee 社区版私有仓库 `pengjiejun/life-circle-assistant-project`  
> 资料原则：仅使用 Gitee 官方帮助中心、Gitee 官方示例仓库和官方 API 文档。

## 结论摘要

Gitee Go 可以在当前 Gitee 仓库中承担 PR 和 `master` 分支的 CI 触发器，其流水线以仓库根目录下 `.workflow/*.yml` 保存。官方文档明确支持 Push、Pull Request 和定时触发；PR 触发会先将目标分支与源分支自动预合并，再构建预合并结果。[1][3]

但当前项目不宜直接使用 Gitee Go 的 Node.js/Python 官方语言插件复刻现有质量脚本：官方 Node.js 构建插件列出的最新版本为 15.12.0，Python 构建插件列出的最新版本为 3.9，而本项目容器分别使用 Node 22 和 Python 3.12。[4] Gitee Go 官方确实提供 Docker 镜像构建插件，但该插件的公开契约是“指定单个 Dockerfile 构建并推送镜像”，官方资料没有承诺托管构建任务可以直接访问 Docker daemon，也没有给出 `docker compose` 或服务容器的配置语法。[5] 因此，不应把 `make container-check` 直接放进 Gitee 托管语言插件并预期它可用。

建议采用两阶段方案：

1. 立即在 Gitee Go 中落地“不依赖 Docker Compose”的 PR 质量流水线，并通过 PR 页面验证它是否自动登记为可选门禁检查项。
2. 对完整 `make quality` 使用自有执行资源，或用其他能明确提供 Docker daemon/Compose 的 CI 执行器；不在没有实跑证据前将 Docker 冒烟标记为 Gitee Go 已支持。

## 1. 配置文件路径与格式

Gitee Go 通过 YAML 描述流水线。官方的“三步开启流水线”说明，使用模板开通后，Gitee 会向代码库提交 `.workflow` 目录，默认生成 `MasterPipeline.yml`、`BranchPipeline.yml` 和 `PRPipeline.yml`。[1] 编辑器同时提供图形视图和代码视图，保存时会将 YAML 提交回仓库。[2]

YAML 的基本顶层字段包括：

```yaml
version: '1.0'
name: quality-pr
displayName: PR 质量门禁
triggers: {}
stages: []
```

- `version`：当前 YAML 版本，官方示例为 `'1.0'`。
- `name`：仓库内唯一的流水线标识。
- `displayName`：展示名称。
- `triggers`：自动触发规则。
- `stages`：按顺序执行的阶段；阶段内以 `steps` 配置任务。[6][7]

Gitee 官方 `gitee-go/node-js` 示例仓库可以作为实际格式参照；其 `.workflow/pipeline-20230413.yml` 包含 `version`、`name`、`displayName`、`triggers`、`stages`、`steps`、`artifacts` 和 `caches` 等字段。[8]

## 2. 触发条件

### Push

Push 触发包括本地推送、分支合并和 PR 合并。分支、Tag 和提交注释条件是交集，同时配置时必须全部匹配才会触发。分支和 Tag 支持前缀、精确、正则包含和精确排除。[3]

### Pull Request

PR 页面创建 PR 或更新 PR 会产生 PR 触发。规则可匹配分支、PR 标题和 PR 评论。需要注意，官方页面在这一节有两处明显的文案误写，把 PR 事件写成了 Push 事件；但同页 YAML 和后续执行逻辑明确使用 `triggers.pr`，实施时应以 YAML 示例和实跑为准。[3]

PR 构建的重要语义是：

- 从源分支最新 commit 读取 YAML。
- 拉取代码时自动预合并，构建内容是“目标分支 + 源分支增量”。
- PR 创建后，源分支新提交会重新触发；目标分支单独更新不会改变已建 PR 的本次触发。[3]

面向当前仓库，PR 流水线应精确匹配目标分支 `master`：

```yaml
triggers:
  trigger: auto
  pr:
    branches:
      precise:
        - master
```

`master` 流水线则使用 `push.branches.precise: [master]`。这样 PR 上先验证预合并结果，合并后再对主分支产物进行一次确认。

## 3. Docker、服务容器与 `docker compose`

### 官方明确支持的能力

Gitee Go 提供 `build@docker` 镜像构建插件：以代码库根目录为工作空间，指定 Dockerfile，构建一个镜像并推送到远程镜像仓库；成功后输出 `GITEE_DOCKER_IMAGE` 供下游步骤使用。[5] 官方还提供 K8s 和 Helm 部署插件，但它们针对外部集群部署，不等于流水线任务内有 Docker daemon。[5]

### 官方未证实的能力

截至调研日期，Gitee Go 公开帮助中心和官方示例没有给出以下承诺或配置方法：

- 托管的 Node.js/Python/其他构建任务可以直接调用 Docker daemon。
- 流水线 YAML 支持类似 GitHub Actions `services` 的伴生服务容器语法。
- 可在托管任务中执行 `docker compose up` 或 Docker-in-Docker。

因此对“是否能直接运行 `docker compose`”的严谨结论是：**官方资料不足以证明可以，不应作为默认能力依赖。** 可以在开通后做最小探测（`docker version` 和 `docker compose version`），但探测结果只代表当时执行环境，不代表官方稳定契约。

### 对本项目的影响

`make container-check` 调用 `docker compose`。在未获得 Gitee 官方确认或实际执行资源证据前，它不应被放到 Gitee Go 托管插件中作为 PR 必过门禁。更可靠的做法是：

- Gitee Go PR 门禁先执行后端测试、前端类型检查/测试/构建。
- Docker 冒烟保留在能明确提供 Docker Compose 的执行器上。
- 如果只需验证 Dockerfile 可构建，可分别为 `backend/Dockerfile` 和 `frontend/Dockerfile` 配置两个 `build@docker` 任务，但该插件要求镜像仓库地址和凭据，且它仍不会验证多容器联调。[5]

## 4. Node.js/Python 镜像和缓存

### Node.js

官方 `build@nodejs` 文档列出 Node.js 8.16.2、10.17.0、12.16.1、14.16.0 和 15.12.0，基础镜像为 CentOS 7.6，内含 git、wget 和 Python 3 等工具。[4] Gitee 官方 Node.js 示例在任务中使用：

```yaml
caches:
  - ~/.npm
  - ~/.yarn
```

这证明任务级 `caches` 至少在官方 Node.js 示例中用于 npm/yarn 缓存。[8]

本项目 `frontend/Dockerfile` 使用 Node 22，且 Vite 6 项目不应降级到官方插件列出的 Node 15。只有在 Gitee Go 实际可视化编辑器显示了更新的 Node 版本并实跑通过后，才应更新此结论。

### Python

官方 `build@python` 文档列出 Python 2.7、3.6、3.7、3.8 和 3.9，支持在 `commands` 内自定义 pip 安装和执行命令。[4] 本项目 `backend/Dockerfile` 使用 Python 3.12；即使现有依赖可能在 3.9 安装，用 3.9 作为唯一 CI 也不能代表生产镜像的 3.12 运行时。

公开帮助中心没有给出 Python `caches` 的官方示例，因此可以在试验流水线中尝试 `~/.cache/pip`，但在保存并实跑通过前不应将其记录为已验证能力。

Gitee 企业版的新流水线文档另行记录了 Node.js 和 Python 插件的缓存路径配置，并说明成功时上传缓存、默认 30 天失效。[13][14] 这可用来理解 Gitee 新一代企业流水线的能力，但不能单凭企业版文档推导社区版 Gitee Go 一定接受相同字段；社区版仍应以可视化编辑器保存结果和实跑为准。

## 5. PR 门禁与保护分支

Gitee 的“Pull Request 门禁检查”支持将 CI/扫描结果以 Check Run 展示在 PR 上，并可在保护分支策略中开启“要求门禁状态成功才能合并”。未成功的被选检查项会阻止 PR 合并；只有最近一周执行过的检查项才能被筛选；仓库管理员仍可强制跳过。[9]

但公开文档没有明确说明“一条 Gitee Go PR 流水线会以什么检查项名称自动出现在保护分支的门禁选择器中”。因此，实际关联步骤必须以 UI 实跑完成：

1. 开通 Gitee Go，提交 PR 流水线 YAML。
2. 创建或更新一个目标为 `master` 的 PR，确认流水线自动运行且 PR 页面显示状态。
3. 进入仓库的保护分支设置，为 `master` 开启“要求门禁状态成功才能合并”，选择刚刚实际运行过的检查项。[9]
4. 用一个故意失败的测试 PR 验证合并被阻止，再修复代码验证恢复可合并。

如果第 2 步的 Gitee Go 流水线状态没有出现为保护分支可选检查项，就不能只靠 PR 触发 YAML 宣称门禁已成立。备选是使用 PR WebHook 触发 CI，再按官方 Check Runs API 为对应 `head_sha`/`pull_request_id` 创建和更新检查任务，最后把该检查名称加入保护分支必过列表。[9]

官方保护分支文档还说明，保护分支可设为标准模式或评审模式；评审模式下，无推送权限的推送会自动创建或更新 PR。[10] 对本项目，可以将 `master` 设为禁止普通成员直推的保护分支，强制改动经过 PR。

## 6. 社区版私有仓库的可用性与额度

Gitee 官方当前文档称 Gitee Go 已对企业版和社区版开放，“单个代码仓库”获得 200 分钟永久有效的免费构建时长，企业/组织/个人每月还有 500 分钟免费时长可供所有仓库使用。[1][11]

文档没有在这一开放说明中对社区版私有仓库作出排除；但开通按钮、账号手机绑定和当前账号的实际额度仍应在仓库页面确认。官方特别提醒，无法开通时需先检查账号是否绑定手机号。[1]

## 7. 建议的实施顺序

### 第一阶段：建立可观测的 PR 流水线

1. 在当前私有仓库开通 Gitee Go。
2. 由 Gitee UI 生成一条 PR 模板，使其提交到 `.workflow/PRPipeline.yml`；不手写未经 UI 验证的插件契约。
3. 将触发条件收紧为目标分支 `master`。
4. 用最小命令确认执行环境实际版本：`node --version`、`python3 --version`、`docker version`、`docker compose version`。
5. 只将实际成功的检查纳入必过门禁。

### 第二阶段：匹配项目运行时

如果 Gitee Go UI 仍只提供文档中的旧 Node/Python 版本，不要降级项目；应改用能保证 Node 22 + Python 3.12 的执行资源。Gitee Go 的官方概念文档说明，用户自定义插件可选择在自有资源上运行，以兼容无法与环境解耦的任务；但公开的 Gitee Go 社区版帮助中未提供详细的自有执行资源接入教程，需在产品界面或向 Gitee 官方进一步确认。[12]

### 第三阶段：启用强制门禁

先让检查项成功运行一次，再在 `master` 保护分支中选中它。然后完成一次“失败时禁止合并、修复后允许合并”的反向测试，再将该门禁记录为已落地。

## 8. 风险与待实跑确认项

| 项目 | 官方证据状态 | 落地决策 |
| --- | --- | --- |
| `.workflow/*.yml` | 明确支持 | 可直接采用 |
| Push/PR/定时触发 | 明确支持 | PR 匹配 `master`，主分支单独 Push 触发 |
| PR 预合并构建 | 明确支持 | 作为 PR CI 的核心语义 |
| Node 缓存 `~/.npm`/`~/.yarn` | 官方示例已使用 | 可按相同插件格式试用 |
| Python pip 缓存 | 未找到官方示例 | 仅做试验，不先写入强制方案 |
| Node 22 / Python 3.12 托管插件 | 公开文档未支持 | 不降级项目，改用匹配运行时的资源 |
| `build@docker` 构建单镜像 | 明确支持 | 可用于 Dockerfile 构建验证，需镜像仓库凭据 |
| 托管任务直接运行 `docker compose` | 未找到官方承诺 | 不设为必过门禁，先探测或改用自有资源 |
| Gitee Go 自动出现为保护分支检查项 | 公开文档未给出精确映射 | 先运行 PR 流水线，再从保护分支 UI 选择实际检查项 |

## 官方资料

1. [Gitee 帮助中心：三步开启流水线](https://help.gitee.com/gitee-go/get-started-in-3-steps)
2. [Gitee 帮助中心：三分钟快速入门](https://help.gitee.com/gitee-go/quick-start)
3. [Gitee 帮助中心：触发事件](https://help.gitee.com/gitee-go/pipeline/trigger)
4. [Gitee 帮助中心：云端编译插件](https://help.gitee.com/gitee-go/plugin/ci-build)
5. [Gitee 帮助中心：镜像构建与部署](https://help.gitee.com/gitee-go/plugin/image-build-and-deployment)
6. [Gitee 帮助中心：流水线基本概念](https://help.gitee.com/gitee-go/pipeline/basic-config)
7. [Gitee 帮助中心：任务编排](https://help.gitee.com/gitee-go/pipeline/scheduling)
8. [Gitee 官方示例仓库：`gitee-go/node-js` 流水线 YAML](https://gitee.com/gitee-go/node-js/blob/master/.workflow/pipeline-20230413.yml)
9. [Gitee 帮助中心：Pull Request 门禁检查](https://help.gitee.com/base/pullrequest/ci-check)
10. [Gitee 帮助中心：保护分支和保护分支的评审模式](https://help.gitee.com/repository/branch/protected-branches)
11. [Gitee 帮助中心：Gitee Go 产品定价与计费](https://help.gitee.com/gitee-go/price)
12. [Gitee 帮助中心：初识 Gitee Go](https://help.gitee.com/gitee-go/intro)
13. [Gitee 帮助中心（企业版）：Node.js 构建](https://help.gitee.com/enterprise/pipeline/plugin/nodejs-compile)
14. [Gitee 帮助中心（企业版）：Python 单元测试](https://help.gitee.com/enterprise/pipeline/plugin/python-unit-test)
