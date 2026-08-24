# 04 · 竞品功能拆解 → 源码实现索引（按 PRD 模块组织 · Stage 4）

> - **日期**：2026-08-23
> - **流程定位**：开发流程图 Stage 4「竞品功能拆解」产出——`competitors/` 下产品级（modules/）与源码级（code/）拆解为本阶段主体产出，本文档是按我方 PRD 模块组织的实现索引
> - **目的**：把 [12-PRD](../08_prd/prd.md)（Stage 12 槽位，FR 编号稳定）所需的每个模块，映射到三个竞品仓库的**具体代码实现**（`文件:行号` 级证据），作为开发期的参考借鉴与反向验收清单。
> - **方法**：howPrompt 提示词分析纪律（提示词识别四方法 + 上下文工程/Agent 循环拆解 + 工具 Schema）+ 工程实现拆解（数据模型/调用链/错误处理），三个分析代理并行完成。
> - **源码快照**（本地克隆于 `/Users/macbookair/vscode-workspace/competitor-src/`，仓库外，不入库）：
>   - WHartTest `f96be5d`（2026-08-21）· Django 5.2 + DRF + Celery + LangChain/LangGraph + Qdrant
>   - TestHub `26c24a0`（2026-08-22）· Django + Vue · **GPL-3.0：只借机制，严禁复制代码**
>   - FullScopeTest `8e3ec79`（2026-08-02）· Flask + Celery + Locust

---

## 1. 拆解成果总览

| 竞品 | 拆解文档 | 风格与定位 |
| --- | --- | --- |
| WHartTest | competitors/wharttest/code/（源仓库 opensource-product-analysis：competitors/wharttest/code/）（README + 9 篇模块） | AI 链路最深：LangGraph Agent + 四中间件 + HITL 中断恢复、RAG 三段管线、slot 租约执行器、Token 计量主链路 |
| FullScopeTest | competitors/fullscopetest/code/（源仓库 opensource-product-analysis：competitors/fullscopetest/code/）（README + 9 篇模块） | AI 工程化与门禁设计最全，但断点多：五项取证全部证实（见 §4），是最好的**反面验收清单** |
| TestHub | competitors/testhub/code/（源仓库 opensource-product-analysis：competitors/testhub/code/）（README + 8 篇模块） | 安全执行范式与数据建模最强：MCP 两段式审批、LLM Judge、BrowserUse 执行纪律、性能 8 态模型（GPL 纪律） |

每份 README 含：Mermaid LLM 数据流时序图、提示词分类统计与逐条登记（原文 + `path:line` + 上下文）、应用场景清单、Agent 循环拆解与工具 Schema、对我方 PRD 的总体借鉴结论。

---

## 2. FR → 竞品实现索引（开发期按此查参考）

### 2.1 平台基座（M0）

| 我方 FR | 首选参考 | 关键实现要点 | 必须反向做对 |
| --- | --- | --- | --- |
| FR-01 多租户/RBAC/SSO | FullScopeTest 01-多租户与RBAC隔离（源仓库 opensource-product-analysis：competitors/fullscopetest/code/modules/01-多租户与RBAC隔离.md）、WHartTest 09-平台底座（源仓库 opensource-product-analysis：competitors/wharttest/code/modules/09-平台底座认证权限与编排模型.md） | FST：中间件解析 `X-Organization-ID` + 15 处手工 `filter_by_org*`；WHT：组织-项目-角色 + JWT/API Key 双认证 | FST 取证 G1–G8：**无组织上下文 = 不过滤**（越权缺口）、Mock 公开端点无认证、环境变量无归属校验——我方 ORM 强制隔离 + 越权回归集 |
| FR-02/03 AI 日志与计量 | WHartTest 03-Token计量与审计日志（源仓库 opensource-product-analysis：competitors/wharttest/code/modules/03-Token计量与审计日志.md）、FullScopeTest 02-AI调用日志（源仓库 opensource-product-analysis：competitors/fullscopetest/code/modules/02-AI调用日志与Token计量.md） | WHT：TokenUsageRecord 优先 `usage_metadata`、工具+提示词 overhead 单列、cache_read 独立、明细/累计双写 | **两家都有旁路**：WHT 的需求评审/知识库 LLM 调用不计账；FST `utils/` 下 8 模块 10 处裸 `requests.post` 零日志——我方必须在 **LLM 工厂唯一出口**埋点（FR-02 验收加此条） |
| FR-04 审批中心 | TestHub 01-mcp-approval（源仓库 opensource-product-analysis：competitors/testhub/code/modules/01-mcp-approval.md）、WHartTest 02-Agent循环与HITL审批（源仓库 opensource-product-analysis：competitors/wharttest/code/modules/02-Agent循环与HITL审批.md） | TH：preview→confirm + TimestampSigner（5min TTL、单次消费）+ DB 五态双验；WHT：LangGraph `__interrupt__`→SSE→`Command(resume)`，默认 reject + 白名单放行 | TH 三缺口行号取证：发起人可自批（views.py:276）、consume 无行锁（confirm.py:118-144）、TTL 覆盖人审窗口（models.py:112）；WHT resume 不带参数哈希——我方 FR-4.12 参数哈希绑定 + 四眼原则缺一不可 |
| FR-17 Policy Gate | TestHub 01（源仓库 opensource-product-analysis：competitors/testhub/code/modules/01-mcp-approval.md）（annotations readOnly/destructive 声明） | 工具级风险注解 + DB 状态机双验 | 我方升级为 L0–L4 分级 + 路由级裁决 |

### 2.2 接口自动化（M1）

| 我方 FR | 首选参考 | 关键实现要点 | 必须反向做对 |
| --- | --- | --- | --- |
| FR-05 Swagger→生成 | FullScopeTest 03-Swagger生成（源仓库 opensource-product-analysis：competitors/fullscopetest/code/modules/03-Swagger生成与AI用例服务.md）、WHartTest 01-AI用例生成链路（源仓库 opensource-product-analysis：competitors/wharttest/code/modules/01-AI用例生成链路.md） | FST：JSON/YAML+$ref 解析、每端点 2 正常+2 边界+2 异常、分批 10 个/次、两步式 save；WHT：权限上下文注入 + Prompt 模板可选 + 生成策略组合 | FST：整批 JSON 解析失败**静默返回空**、断言仅 2 类、save=true 可绕审阅——我方 partial 可见 + 六类断言 + 无直写路径 |
| FR-06/A4 失败自愈 | FullScopeTest 04-失败自愈三段式（源仓库 opensource-product-analysis：competitors/fullscopetest/code/modules/04-失败自愈三段式.md） | 8 类原因枚举 + fixes{field,current,suggested} + temperature 0.2 严格 JSON + confidence≥0.7 + 快照 | 取证：apply-heal 不复核 confidence、快照 `except: pass` fail-open、`setattr` 可改任意列（healing_service.py:76-83）——我方服务端复核 + fail-close + 字段白名单 + 回滚端点 |
| FR-07 失败聚类 | WHartTest 01（源仓库 opensource-product-analysis：competitors/wharttest/code/modules/01-AI用例生成链路.md）（结构化输出契约） | WHT 四件套输出契约（步骤+断言+变量提取+前后置） | 我方升级为 run 级聚类（A2）+ evidence_refs 服务端校验 |
| FR-08 执行引擎 | FullScopeTest 05-接口执行引擎（源仓库 opensource-product-analysis：competitors/fullscopetest/code/modules/05-接口执行引擎.md）、TestHub 05-api-testing（源仓库 opensource-product-analysis：competitors/testhub/code/modules/05-api-testing.md）、WHartTest 05-HttpRunner（源仓库 opensource-product-analysis：competitors/wharttest/code/modules/05-接口执行引擎HttpRunner.md） | FST 管线顺序：前置脚本→`{{}}` 变量替换（3 轮嵌套）→环境 headers→Mock 短路→SSRF→请求→后置→断言；TH 双层变量 `{{env}}`+`${func}`（约 100 函数别名）+ 六类断言 + Allure 降级链 | FST 取证：假异步 `threading.Thread(daemon)`（api_test.py:626）任务永久 running；TH：同步 requests 伪装 httpx、`{{var}}` 未定义静默保留——我方真队列 + 解析失败必报错 |

### 2.3 Web 自动化与 Agent Mode（M2）

| 我方 FR | 首选参考 | 关键实现要点 | 必须反向做对 |
| --- | --- | --- | --- |
| FR-09 Playwright 执行器 | WHartTest 06-UI执行器Actuator（源仓库 opensource-product-analysis：competitors/wharttest/code/modules/06-UI执行器Actuator与用例执行.md） | 独立执行器进程 + 能力上报 + **Redis slot 租约（原子预占 + TTL 自愈）** + 浏览器安装检测 + Trace 采集 + 进程终止治理 | 我方容器化 + 心跳/僵尸回收（WHT 亦缺排队上限） |
| FR-10 定位器自愈 | TestHub 06-ui-automation（源仓库 opensource-product-analysis：competitors/testhub/code/modules/06-ui-automation.md） | 12 种定位策略 DB 表 + 主备定位器 + 健康度四态 + 使用统计（24 张表建模） | 我方 AI 只做建议 + diff 确认 + 回滚（TH 无 AI 接点，机制层借鉴） |
| FR-19 Agent Mode | TestHub 04-browser-use-agent（源仓库 opensource-product-analysis：competitors/testhub/code/modules/04-browser-use-agent.md）、WHartTest 02/07（源仓库 opensource-product-analysis：competitors/wharttest/code/modules/07-Skills与MCP工具体系.md） | TH：两阶段编排（analyze_task→run_full_process）+ planned_tasks 落库 + **12 条执行纪律 Prompt + 服务端强制（步数裁剪/漏标补齐/登录 3 次熔断）双层防御** + 三级拆解兜底（正则→LLM→规范化）+ GIF 报告 | TH 取证：daemon 线程 + 内存 STOP_SIGNALS（views.py:3153）多 worker 失效；WHT Skills：`subprocess.run(shell=True)`（skill_tools.py:712）、无 allowedTools/max_steps、全局共享跨项目、凭据明文进提示词——我方 manifest 声明 + 容器沙箱 + 工具层租户校验（FR-19 全部命中） |
| A3 多模态归因 | WHartTest 01/06（源仓库 opensource-product-analysis：competitors/wharttest/code/modules/06-UI执行器Actuator与用例执行.md） | 日志+截图+Trace → 四类修复建议（失效定位器/不稳定等待/异常页面/断言失败） | 无量化数据（[待确认]），我方建评测集 |

### 2.4 CI 集成与门禁（M2）

| 我方 FR | 首选参考 | 关键实现要点 | 必须反向做对 |
| --- | --- | --- | --- |
| FR-13 Check Run 门禁 | FullScopeTest 07-GitHub集成与CI（源仓库 opensource-product-analysis：competitors/fullscopetest/code/modules/07-GitHub集成与CI.md） | OAuth 授权码流（state 防 CSRF）、Check Run 三段式 create→update→complete、触发规则 fnmatch include/exclude、三阈值门禁模型 | 取证 D1–D11：门禁 FAIL **不影响 exit code**（cli/main.py:103-116，官方模板 `curl|jq` 恒 0）、PR 事件 changed_files 传空、HMAC 在 SECRET 空时整段跳过（webhooks/github.py:35-36，默认空串）——我方门禁写 exit code + 强制验签无例外 + 仓库归属校验 |
| FR-18 执行环境/引用型用例 | FullScopeTest 07（源仓库 opensource-product-analysis：competitors/fullscopetest/code/modules/07-GitHub集成与CI.md）（连接器形态参考） | FST 定时回归 APScheduler + notify_webhook + 通用触发端点 | **新发现**：FST 的 CI ApiToken 模型/校验齐全但**全后端无中间件消费 `X-API-Key`**（CLI 发的 key 无人认）——我方 API Token 必须进认证链且有消费闭环测试 |

### 2.5 性能自动化（M3）

| 我方 FR | 首选参考 | 关键实现要点 | 必须反向做对 |
| --- | --- | --- | --- |
| FR-11 压测编排 | TestHub 07-perf-testing（源仓库 opensource-product-analysis：competitors/testhub/code/modules/07-perf-testing.md）（数据模型首选）、FullScopeTest 06-性能压测（源仓库 opensource-product-analysis：competitors/fullscopetest/code/modules/06-性能压测.md）（执行实现参考） | TH 模型：三引擎、8 态 + ACTIVE/FINAL 集合、`has_active_execution` 互斥、heartbeat_at 僵尸检测、快照冻结、压力机自监控、SLA abort_on_breach、验收/过程分离；FST 执行：subprocess Locust + CSV 2s 轮询 + 四件套护栏（SSRF+参数上限+AST+硬超时） | FST 缺：目标环境白名单、启动审批、全局并发预算、压测误用功能重试 max_retries=3；TH 未发版仅模型——我方两道闸先行 |
| FR-12 性能门禁 | FST 06/07 | p95/错误率阈值复用门禁模型 | 同 FR-13 |

### 2.6 Copilot / Skills / 模型路由（M3–M4）

| 我方 FR/A | 首选参考 | 关键实现要点 | 必须反向做对 |
| --- | --- | --- | --- |
| FR-16 Copilot | FullScopeTest README §Copilot（源仓库 opensource-product-analysis：competitors/fullscopetest/code/README.md）（反面教材）、WHartTest 02（源仓库 opensource-product-analysis：competitors/wharttest/code/modules/02-Agent循环与HITL审批.md）（正面架构） | WHT：SSE 流式 + 中间件链 + Agent Loop 可视化 | FST 取证：裸 requests.post 绕日志（ai_copilot.py:274,309）、`AI_ASSISTANT_ENABLED` 读而不判、BYOK 明文 localStorage、前端内存会话——FR-16 六件事全部命中，作为验收清单用 |
| Skills 体系 | WHartTest 07-Skills与MCP（源仓库 opensource-product-analysis：competitors/wharttest/code/modules/07-Skills与MCP工具体系.md） | SKILL.md frontmatter + ZIP 分发 + 技能商店源；MCP 双向（FastMCP 三传输 + GlobalMCPSessionManager 会话治理） | WHT 安全缺口即我方差异化：manifest 增 allowedTools/max_steps/副作用上限/数据分级；沙箱替代 shell=True |
| 模型路由/多模型配置 | TestHub 02-model-config（源仓库 opensource-product-analysis：competitors/testhub/code/modules/02-model-config.md） | 单表多角色（writer/reviewer/browser_use_text）+ max_tokens=1 测试连接 + 智能模式服务端强制单活 | TH 取证：API Key 明文 CharField（requirement_analysis/models.py:214）且日志打印前 10 位、取配置不过滤 created_by 跨用户消耗 Key——我方 Vault + 加密 + 归属校验 |
| A7 LLM Judge | TestHub 03-llm-judge（源仓库 opensource-product-analysis：competitors/testhub/code/modules/03-llm-judge.md） | 规则 0.4+LLM 0.6（规则可一票否决）、CoT 先理由后打分、temperature=0、n_runs×多裁判中位数/众数、rubric DB+YAML 双源、五因子缓存键、红黄绿分区、MockJudge 联调 | TH 局限：评测对象是 QA 对而非测试资产、should_block 无调用方——我方接平台资产 + 门禁挂钩 |
| M4 RAG | WHartTest 04-RAG混合检索（源仓库 opensource-product-analysis：competitors/wharttest/code/modules/04-RAG混合检索与知识库.md） | 三段管线：混合检索 RRF 融合 → Reranker 复合评分（0.6/0.3/0.1）→ MMR+降级；embedding OpenAI 兼容 | 分块策略/参数未公开 [待确认]；我方 MVP 用 pgvector 起步 |
| M4 Prompt 版本化/A-B | FullScopeTest 08-Prompt版本化与A-B测试（源仓库 opensource-product-analysis：competitors/fullscopetest/code/modules/08-Prompt版本化与A-B测试.md） | feature 版本自增 + traffic_weight 加权 + 从日志回算统计 | FST 仅 3 端点接入、16 处提示词仅 2 个 feature 版本化——我方「未版本化不进生产」CI 强制 |
| A5/A6 Release notes/Copilot 查询 | WHartTest 08-需求分析评审引擎（源仓库 opensource-product-analysis：competitors/wharttest/code/modules/08-需求分析与评审引擎.md）（文档解析与结构化输出参考） | 多源解析 + 六维评分框架（维度黑盒 [待确认]） | 我方接 Jira/Confluence 连接器 + Evidence 绑定 |

### 2.7 通知与认证（横切）

| 主题 | 首选参考 | 要点 |
| --- | --- | --- |
| 通知子系统 | TestHub 08-notification（源仓库 opensource-product-analysis：competitors/testhub/code/modules/08-notification-testmgmt-jwt.md） | Fernet 加密 + 密钥失效自检、主备渠道容灾、告警 episode 状态机、企微/钉钉/飞书多机器人——其全平台工程质量最高的部分 |
| JWT 双 Token | TestHub 08（源仓库 opensource-product-analysis：competitors/testhub/code/modules/08-notification-testmgmt-jwt.md） | 刷新排队 + 防循环；WHT 09 提供 JWT+API Key 双通道参考 |

---

## 3. AI 能力 → 提示词与上下文工程参考

| 我方能力 | 提示词参考（原文登记于各家 README/code 模块） | 上下文工程参考 |
| --- | --- | --- |
| A1 用例生成 | WHT：生成策略×用例类型组合模板；FST：Swagger 端点分批提示词（≥2 正常+2 边界+2 异常） | WHT：权限上下文注入（project auth/role 进链路）——我方 Copilot/生成共用 |
| A2 聚类归因 | FST：8 类原因枚举 + 严格 JSON + confidence | 我方 Prompt Contract（PRD 3.2）补 evidence_refs 校验 |
| A7 Judge | TH：rubric 模板 + CoT 指令（「直接打分一致性低 25–40%」的注释值得照抄思路） | TH：五因子缓存键设计 |
| A8 Agent Mode | TH：**12 条执行纪律 Prompt**（凭据规则/步数纪律/漏标补齐）+ 任务拆解三级兜底 | TH：两阶段编排 planned_tasks 落库可审计；WHT：Agent 循环（LLM makes/in/ends the loop）+ Summarization 扣 overhead 预算 |
| A5 Release notes | WHT：需求评审专项分析提示词 | 结构化输出优先（研究包 3.10） |

---

## 4. 源码级新发现对 PRD 的验证与修订建议

三家拆解共 30 份文档，除证实既有决策外，有 6 项**新证据**建议回写 PRD/README（暂记录于此，待你确认后应用）：

1. **LLM 出口收口**（验证 FR-02）：WHT 与 FST 用两种方式证明了「逐调用点埋点」必然有旁路（WHT 漏需求评审/知识库，FST `utils/` 10 处裸调用）。→ 建议把「LLM 工厂唯一出口 + 出口埋点 + 无直连 SDK 的架构约束测试」写入 FR-02 验收。
2. **CI Token 消费闭环**（新发现，FR-18）：FST 的 ApiToken 有模型无消费者。→ 建议 FR-18 验收加「Token 进认证链 + 端到端消费测试（发 key→触发→审计可见）」。
3. **审批四眼 + 行锁 + 独立 TTL**（验证 FR-4.12）：TH 三处缺口给了精确行号级反例。→ FR-04 验收已覆盖，可补充自动化测试用例描述。
4. **Agent Mode 服务端强制层**（强化 FR-19）：TH 的「Prompt 纪律 + 服务端强制（步裁剪/漏标补齐/登录熔断）」双层防御是比我方文档更具体的设计。→ 建议写入 FR-19 实现说明。
5. **门禁 exit code 与验签强制**（验证 FR-13）：FST 给出行号级失败模式（curl|jq 恒 0、SECRET 空跳过）。→ FR-13 验收已有「CI 变红 E2E」，补「验签无例外分支的代码审查检查项」。
6. **幽灵模块纪律**（新发现）：TH 两个模块被引用但不存在（`suite_runner.py`、`scene_binding.py`），运行即 ImportError。→ 建议我方 CI 加 import 完整性检查（ruff/pytest --collect-only）作为门禁项。

---

## 5. 证据纪律

- 全部结论以静态分析为据，`文件:行号` 均对应 §头部三个 commit 快照；竞品后续提交可能使行号漂移，引用时注明快照号；
- TestHub 文档头部均带 GPL-3.0 警示：**机制可借鉴、源码不可复制**，摘录≤10 行最小引文；
- 标注 [待确认] 的点（如 WHT 评分维度、RAG 分块参数）不得用推测填充；
- 本索引不替代各模块文档，开发期以模块文档的完整上下文为准。

## 6. 变更日志

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| v1.0 | 2026-08-23 | 基于三家源码快照（f96be5d / 26c24a0 / 8e3ec79）生成；30 份拆解文档索引化；6 项 PRD 修订建议 |
