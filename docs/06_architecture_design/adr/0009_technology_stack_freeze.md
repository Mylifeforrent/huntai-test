# ADR 0009: Technology Stack Freeze and Phased Infrastructure Adoption

- **Status: Accepted**
- **Date: 2026-08-29**

## Context

Stage 6 的架构结论已定稿，但 [architecture.md](../architecture.md) §2.3 明确把「依赖、部署清单、环境变量」列为非目标，ADR 目录此前也声明不承载依赖与部署配置。结果是：模块边界、状态机、审批与恢复协议都已收口，具体用什么框架、什么 ORM、什么版本落地却没有任何一份文档承接——Stage 7 的 API 契约与 Stage 11/12 的实施都缺少这层输入。

同时存在两处已知的悬空项：[frontend_design_spec](../frontend_design_spec-v1.0.md) §1.3 把路由库留给「Stage 11 按红线 R4 确定」；`project_rules.md` §5 的验证命令引用了尚不存在的 uv 项目与 npm scripts。

还有一处实质冲突需要裁决。用户对本次冻结提出两条约束：「只确定实现所必需的技术」与「每个选型是我能独立运维的」。但 [ADR 0001](0001_modular_monolith_control_plane.md) 与 [ADR 0002](0002_durable_workflow_runtime.md) 要求的目标运行形态包含 Temporal Server、Vault、Redis 与 S3/MinIO——单人独立运维 Temporal（自身数据库、history 保留、Worker Versioning、在途 workflow 兼容）与 Vault（unseal、租约轮换、灾备）并不现实。「按目标架构一次装齐」与「能独立运维」无法同时成立。

## Decision

1. **冻结八类技术栈**：前端框架、UI 组件方案、状态管理、后端框架、ORM、API 风格、测试框架、构建部署方式。逐项理由、锁定版本、License、维护活跃度与 CVE 结论见 [tech_stack_decision-v1.0.md](../tech_stack_decision-v1.0.md)。本 ADR 只承载决策本身，版本表不在此重复维护。

2. **Starlette 提升为直接依赖并显式锁定。** FastAPI 只声明 `starlette>=0.46.0` 且无上界，把 Starlette 当作纯传递依赖会使锁文件可能落在含未修复 CVE 的版本（实测 0.51.x 命中 6 条通告）。因此 Starlette 必须作为直接依赖锁定，且与 FastAPI 同批次升级、同批次复验；升级 FastAPI 时不得移除该显式声明。

3. **PostgreSQL 驱动选 asyncpg（Apache-2.0）而非 psycopg3（LGPL-3.0-only）。** [architecture.md](../architecture.md) §18 风险表已登记「GPL 源码污染」风险项。LGPL 动态链接通常可用，但选 Apache-2.0 直接消除了这个需要法务判断的问题。若 asyncpg 停维，切换 psycopg3 属 License 变更，须重新登记。

4. **M0/M1 采用单 PostgreSQL 数据面；Temporal、Redis、S3/MinIO、Vault 推迟至 M2+ 启用。** 本条**不推翻** ADR 0002——Temporal 仍是目标持久工作流运行时，本条只决定启用节奏。M0/M1 期间：Outbox 落 PostgreSQL 表、轮询由后端定时任务驱动、秘密经 `.env` + Docker secret、制品存本地卷。

5. **M0/M1 必须照常实现幂等键、CAS 与数据库行锁。** 这三项在 M0/M1 是「重启不重复副作用」的唯一保障（因为没有 workflow history 可重放），不得以「M2 要上 Temporal」为由推迟。

6. **构建产物是容器镜像，部署路径为 docker compose → Kubernetes，且镜像不变只换编排层。** 由此产生三条硬约束：配置全部经环境变量注入、进程无本地状态（M0/M1 制品卷是唯一例外且须在启用 MinIO 前迁移）、日志写 stdout 不写文件。

7. **前端路由库定为 React Router，且不启用其 loader/action 数据层。** 服务端状态统一由 TanStack Query 承担。理由是避免两套并行的数据获取与失效机制对同一份领域数据各自缓存——那会直接制造 [frontend_backend_boundary_spec](../frontend_backend_boundary_spec-v1.0.md) §1 原则 1 与 §3.3 红线 1 所禁止的「前端自行推演状态」。

8. **本 ADR 不批准 M2+ 组件的启用。** Temporal 启用仍受 [architecture.md](../architecture.md) §15.1 八项生产 Gate 约束；Temporal 与 Vault 启用前必须先补运维方案，该前置条件为硬性。

## Alternatives

1. **按目标架构一次装齐（Temporal + Vault + Redis + MinIO 全部进 M0）**：与已定稿架构形态完全一致，无迁移债务。未采纳的原因是它使「能独立运维」自检项直接失败——M0 就要同时运维四个各有独立故障模式与升级路径的有状态组件，而 M0 的业务目标只是多租户 + SSO + AI 日志 + 执行环境注册中心。

2. **彻底放弃 Temporal，改用 PostgreSQL + 应用内状态机 + 幂等键**（决策总纲 §7.13 的「保底方案」）：运维面最小，但会推翻已 Accepted 的 ADR 0002，且长等待、Signal 与崩溃恢复需要自行实现持久 Timer 与历史重放。未采纳，保留为 Temporal 无法通过生产 Gate 时的替代候选。

3. **psycopg3 作为驱动**：官方维护、发布节奏更稳、功能更全（含服务端游标与 pipeline 模式）。未采纳仅因 LGPL-3.0-only 与 §18 已登记的 GPL 风险项相邻，属主动规避而非技术劣势。asyncpg 发布节奏偏慢已作为观察项登记。

4. **前端只用 Zustand + React Router，不引入 TanStack Query**：少一个依赖。未采纳的原因是 boundary spec §7.2 已明文把自动重试归给 TanStack Query，另有三项上游要求（`architecture.md` §9.3 的重连后 GET 对账、boundary spec §9-G3 的降级轮询、`frontend_design_spec` §6.14 的缓存失效）需要等价能力；自行在 Zustand 上实现等于重建一个缓存库，且 store 语义会诱导把领域数据当作本地事实源。

5. **成品组件库（Ant Design / MUI）**：开箱即用。未采纳因 05 §4.3 冻结了审批卡片、TestRun 详情、执行发起页三者的分区顺序，成品库意味着持续与其默认布局对抗。

## Consequences

- 优点：Stage 7/11/12 获得明确的实现约束；M0/M1 的运维面收敛到「1 个有状态组件 + 1 个无状态进程 + 静态产物」，单人可控；全部依赖为 MIT / BSD-3-Clause / Apache-2.0 / ISC，无 GPL 与 LGPL。
- 代价：M0/M1 的恢复保证**弱于**目标架构——进程重启后靠数据库状态重建而非 workflow 重放。这是明确接受的债务，不是疏漏。
- 代价：M2 启用 Temporal 时存在调度 Owner 切换窗口，必须保证同一业务步骤不被后端定时任务与 Temporal 同时调度（[architecture.md](../architecture.md) §11.2 原文约束）。
- 代价：M0/M1 制品存本地卷违反「进程无本地状态」，构成 Kubernetes 迁移的前置阻塞项，必须在迁移前完成对象存储切换。
- 版本冻结意味着日常「跟新版本」不再是可自由执行的操作；只有安全通告、上游不兼容或已登记的架构变更才构成升级理由。

## Security and Operations

- 高危/严重 CVE 未处置数必须保持为 0。锁文件（`uv.lock` / `package-lock.json`）每次变更后必须按锁定版本逐个复扫，不得沿用旧扫描结论。
- 秘密在 M0/M1 只经 `.env` 注入且不入库（`AGENTS.md` §2）；`.env.example` 只含键名。数据库中保存的必须已经是凭证**引用**而非明文，否则 M2 迁移 Vault 会退化为改数据。
- ApiToken 使用 argon2 哈希（决策总纲 §6 裁定「bcrypt/argon2」），明文只显示一次。
- 日志写 stdout 且不得承载秘密或敏感正文；M0/M1 用标准库 logging + JSON formatter 满足「结构化日志」，OpenTelemetry Trace 推迟至 Worker 拆出后评估。
- 四项维护活跃度观察项（class-variance-authority、clsx、argon2-cffi、asyncpg）每次发布前复查发布日期；连续 18 个月无发布且出现未修复通告即启动退出方案。

## Migration or Follow-up

1. Stage 11/12 初始化 `frontend/` 与 `backend/` 时按本冻结落锁；子目录结构由 Stage 6/7 设计文档定稿后才建（`project_rules.md` §2.5）。
2. 启用 Temporal 前完成 [architecture.md](../architecture.md) §15.1 八项生产 Gate，并补运维方案（history 保留、Worker Versioning、备份恢复、值班）。
3. 启用 MinIO 前完成本地卷制品迁移与摘要复核；此前应用不得假设 S3 专有语义（如预签名 URL）。
4. 启用 Vault 前确认业务库中已只保存凭证引用。
5. 上述任一组件启用均属「变更依赖或配置」，须按 `AGENTS.md` §5 先出 Plan 并在 `change_log` 登记。
6. G1–G5 缺口（M0/M1 调度形态、JSON Schema 校验器、前后端类型同步、K8s 清单形态、PostgreSQL 高可用拓扑）见 [tech_stack_decision-v1.0.md](../tech_stack_decision-v1.0.md) §10。

## Verification

- 依赖审计可复现：按锁定版本查询 PyPI 逐版本 `vulnerabilities` 字段与 npm registry advisory bulk 接口，结果应与 [tech_stack_decision-v1.0.md](../tech_stack_decision-v1.0.md) §4 一致；Starlette 1.6.0 必须为 CLEAN。
- 锁文件中 Starlette 为直接依赖且版本 ≥ 1.3.1；FastAPI 升级后复验该约束仍成立。
- License 扫描结果中不出现 GPL / LGPL 依赖。
- M0/M1 的幂等与恢复测试照常执行：Outbox 重发、重复受理、API 与数据库重启、外部调用成功但响应丢失，均不产生重复副作用（对应 [architecture.md](../architecture.md) §20 验证计划第 6 项）。
- M2 启用 Temporal 后，验证同一业务步骤不存在两个调度 Owner。

## Open Questions

1. M0/M1 定时任务的调度形态（进程内调度器 / 独立进程 / 数据库 advisory lock 选主）未定。
2. Temporal 启用的具体里程碑时点与托管方式（自托管 / 托管服务）未定，沿用 [architecture.md](../architecture.md) 开放问题 Q1。
3. Kubernetes 迁移时点、清单形态与 Ingress/网关选型未定。
4. 前后端类型同步是否引入 OpenAPI 代码生成器未定；若引入属新增开发依赖，须走红线 R4。
5. asyncpg 若停维，切换 psycopg3 涉及 License 由 Apache-2.0 变为 LGPL-3.0-only，须重新评估 §18 GPL 风险项。

## References

- [tech_stack_decision-v1.0.md](../tech_stack_decision-v1.0.md)
- [architecture.md](../architecture.md) §2.3、§9.3、§11.2、§11.3、§12、§15.1、§18
- [frontend_backend_boundary_spec-v1.0.md](../frontend_backend_boundary_spec-v1.0.md) §3.2、§3.3、§5.1、§7.2
- [frontend_design_spec-v1.0.md](../frontend_design_spec-v1.0.md) §1.3、§6.14
- [0001_modular_monolith_control_plane.md](0001_modular_monolith_control_plane.md)、[0002_durable_workflow_runtime.md](0002_durable_workflow_runtime.md)
- `../../00_setup/project_rules.md` §1.1、§1.2、§2.5、§5
- `../../README.md` §4.2、§6、§7.13
