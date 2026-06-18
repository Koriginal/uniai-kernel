# UniAI Kernel 平台方向与当前差距

UniAI Kernel 的定位不是单个聊天机器人，也不是一组 system prompt。它应该是一个智能体开发平台和运行框架：平台先定义业务智能体应用，再把 Agent、工具、本体、运行图、任务状态、权限和审计挂到应用上；运行框架负责把用户请求转成可执行状态，并在图节点之间推进。

这份文档按当前代码来写，不按口号写。这里的每一项都应该能落到模块、字段、接口或下一步开发动作。

## 平台边界

当前平台至少要分成九层：

1. 业务应用层：`AgentApplication`，绑定业务域、场景、主控 Agent、provider、工具、本体空间、运行策略和验收策略。
2. 规则库层：独立维护规则来源、规则提取、规则条目、规则审核和规则包；本体、评审应用和其他工程都只能消费规则库产物，不在这里混管本体或评审运行。
3. 评审应用层：消费已发布规则包，组织合同/招标/制度评审运行，记录评审结果和引用依据。
4. Agent 定义层：`backend/app/models/agent.py`、Agent Profile、runtime policy、专家角色和 handoff 策略。
5. 运行图层：`backend/app/agents/graph_builder.py`、`graph_registry.py`、拓扑版本和节点编译。
6. 任务运行时层：`backend/app/agents/task_runtime.py`、`task_planner`、`task_evaluator`。
7. 工具层：动态工具、MCP 工具、工具执行器、工具审计和 tool runtime events。
8. 本体资产层：实体、字段、关系、枚举、映射、schema package 和本体治理。
9. 观测层和控制台层：SSE runtime events、审计、ChatView、GraphTracePanel、RuleLibraryWorkbench、ApplicationManager、AgentManager、ToolRegistry、OntologyWorkbench。

这几个层之间不能继续靠提示词传隐式状态。业务应用、任务目标、执行计划、工具产物、验收结果要进入状态字段和事件流。

## 当前成熟度

后端内核已经从“提示词驱动”进入“运行时驱动”的早期阶段。

已落地的部分：

- 标准图里已有 `context -> task_planner -> agent -> tool_executor / handoff / orchestrator_invoke / synthesize -> task_evaluator`。
- `task_frame` 记录任务类型、用户目标、约束、风险标记和验收条件。
- `AgentApplication` 已作为业务场景入口，收拢主控 Agent、runtime provider、工具白名单、本体空间和验收策略。
- 现有本体模块已经有 package 存储、审批、发布、rollback、映射执行、规则评估和解释。
- `execution_plan` 记录步骤、责任方、工具候选、当前步骤和完成标准。
- `execution_artifacts` 记录工具、专家和回答阶段留下的可回放产物。
- `task_evaluator` 会在结束前检查任务完成度，并在失败时按 `max_task_repairs` 重新打开计划。
- 已有 `runtime_capabilities` 扩展契约，默认 provider 承接当前任务分类、计划和验收逻辑。
- 旧拓扑通过 `graph_registry._normalize_runtime_topology()` 自动补齐 `task_planner` 和 `task_evaluator`，避免历史模板直接崩。
- `/api/v1/graph/runtime/capabilities` 已暴露运行时能力目录、provider、状态字段、事件类型和请求配置。
- `/api/v1/applications` 已提供业务应用管理接口，`/runtime-contract` 可查看应用实际启用的主控、provider、工具、本体和策略。

还没有完成的部分：

- 任务分类仍是默认 provider 的规则优先，应用级 provider 白名单已接入，但还没有模型分类回退。
- 计划步骤已有工具准入约束，但工具注册表的 category、effect 和风险等级还不够细。
- 完整工具结果已有 `tool_artifacts` 表承载；专家输出、文件产物还没有统一进入 artifact 表。
- 修复循环是一次性图内重试，不是完整的子任务队列，也没有人工确认点。
- 前端已有业务应用入口，但规则、本体和映射还停留在 package/JSON 维护方式，没有条目级生产线。
- 合同和招标文件评审已有评审知识库第一版，但抽取逻辑还是候选生成，后续要接入更稳定的结构化抽取 provider 和人工校对页面。
- E2E 测试还没覆盖 SSE 全链路、历史消息回放和旧拓扑迁移。

## 已修掉的问题

### task_evaluator 节点缺失

现象：运行时报 `内核严重故障: 'task_evaluator'`。

原因：标准拓扑和编译器没有同时注册新节点。图模板里出现了 `task_evaluator`，但 `graph_registry` 的 node factory 不认识它。

处理：

- `backend/app/agents/graph_registry.py` 增加 `task_evaluator_node` factory。
- 标准拓扑补齐 `task_evaluator`。
- 旧模板 normalize 时自动插入 evaluator 节点和条件边。

### END 局部变量错误

现象：运行时报 `cannot access local variable 'END' where it is not associated with a value`。

原因：`graph_registry.py` 内部局部 import `END`，让 Python 把 `END` 判定成局部变量，前面的引用反而读不到模块级 `END`。

处理：

- 移除函数内 `from langgraph.graph import END`。
- 统一使用模块级导入。

### 数据库 checkpointer 不可用时图不可编译

现象：本地没有数据库连接池时，旧拓扑编译验证会失败。

处理：

- `graph_registry` 在没有 DB pool 时回退到 `MemorySaver`。
- 这只解决本地编译和开发体验，生产环境仍应使用持久化 checkpointer。

## 现在最该补的能力

### 0. 评审知识库和规则包

合同审核、招标文件审核这类应用不能直接读取 Word 后让模型自由发挥。平台需要先把审查口径做成固定版本的 `ReviewPack`，运行时只读取已发布规则包。

已落地动作：

- 新增独立 `rule_extraction` 模块，输入非结构化文本或上传文件，输出标准规则候选；接口为 `/api/v1/rule-extraction/extract` 和 `/api/v1/rule-extraction/upload`。这块后续可以单独抽成规则提取应用，不依赖评审知识库页面。
- 新增 `policy_documents`：记录合同/招标评审规则来源文档、版本、来源文件和状态。
- 新增 `policy_articles`：按章、条、段落切分原文，保留 locator、quote 和 hash。
- 新增 `norm_clauses`：把原文条款抽取成规范语义，记录义务、禁止、审批要求、材料要求、评分标准、责任等类型。
- 新增 `review_checks`：把规范语义转成可执行审查点，记录场景、严重度、证据字段、输出模板和绑定的规范条款。
- 新增 `review_packs`：把 approved 规范和审查点发布成固定版本规则包。
- 新增 `review_runs`：记录一次评审使用的应用、规则包、目标文件快照、命中结果、引用依据和摘要。
- 新增 `/api/v1/review/*` 接口，支持上传规则文档、分条、抽规范、确认、创建规则包、发布规则包和运行评审。
- 新增 `/api/v1/review/target-documents/extract`，待审 DOCX/TXT/MD 可以先解析成正文再进入 `ReviewRun`。
- `AgentApplication` 增加 `review_pack_id`、`review_pack_version`，`runtime-contract` 返回固定规则包摘要。
- 前端新增“评审知识库”，包含规则文档、原文条款、规范条款、审查点、规则包和评审工作台；规范条款和审查点支持字段级编辑，评审工作台支持待审文件上传解析。

边界：

- 当前抽取是 v1 候选生成，不直接代表可上线规则。
- 只有 `approved` 的 `NormClause` 和 `ReviewCheck` 可以进入 `ReviewPack`。
- 只有 `released` 的 `ReviewPack` 可以进入评审运行时。
- 评审输出固定为问题清单、目标文件证据、规则原文引用和修改建议。

下一步动作：

- 把结构化抽取接入独立 runtime provider，输出必须符合 `NormClause` 和 `ReviewCheck` schema。
- 待审文件后续要落正式表，记录上传文件、解析文本、版面 locator 和评审运行引用关系。
- 合同和招标各补一份样板规则包，作为应用模板引用。

### 1. 规则与本体资产生产线

这一步应该排在业务应用继续增强之前。合同审核、风控审核、授信评估这类应用要稳定运行，不能让模型每次临时解释制度文件，也不能把规则藏在 prompt 里。平台需要先把规则和本体做成可管理资产。

已确认方向：

- 新增“规则与本体资产台”，作为独立控制台入口。
- 来源文档进入 `RuleSourceDocument`，记录文件、来源类型、hash、解析状态和原文引用。
- 业务规则进入 `RuleEntry`，记录 `rule_code`、目标实体、结构化条件、严重度、动作、证据引用、测试用例和审核状态。
- 本体定义进入 `OntologyTerm`，记录实体、字段、关系、枚举、字段类型、别名、证据引用和审核状态。
- 字段映射进入 `MappingEntry`，记录来源路径、本体目标字段、必填、默认值和 transform。
- 只允许 `approved` 条目编译成现有 `schema`、`mapping`、`rule` package。
- package 继续走现有审批、发布和 rollback。

已落地动作：

- 新增 `rule_source_documents`、`rule_entries`、`ontology_terms` 三张 authoring 表。
- 新增 `/api/v1/ontology/asset-sources`、`/rule-entries`、`/terms` 管理接口。
- 新增 `/api/v1/ontology/asset-sources/upload`，支持上传 TXT、MD、JSON、CSV、TSV、DOCX 并抽取 `raw_text`。
- 新增 `/api/v1/ontology/asset-sources/{source_id}/parse`，从来源文档 `raw_text` 抽取候选规则条目，并保留原文依据。
- 新增 `/api/v1/ontology/assets/compile-rules`，从 approved `RuleEntry` 编译 draft rule package。
- 新增 `/api/v1/ontology/assets/compile-schema`，从 approved `OntologyTerm` 编译 draft schema package。
- 前端新增“规则与本体资产”入口，支持文档上传、来源文档、原文查看、来源解析、规则条目、本体条目和两个编译动作。

文档：

- `docs/rule_ontology_asset_sop.md` 记录完整 SOP、状态流转、数据模型、接口、控制台页面和 MVP 顺序。

下一步动作：

- 第三阶段做 `MappingEntry` 和 `compile-mapping`。
- 规则和本体条目补编辑、废弃、批量导入和样例回放。
- 让 `AgentApplication` 绑定明确的 `schema_version`、`mapping_version`、`rule_version`。

### 2. 业务智能体应用层

现在已经新增 `backend/app/models/application.py`，应用是业务场景入口，Agent Profile 是执行角色。业务用户不应该先选“专家、工具、本体、审计”，而应该先进入一个业务应用，例如风控审核、合同审查、客户支持或研究流程。

已落地动作：

- `AgentApplication` 表记录业务域、场景类型、主控 Agent、runtime provider、工具白名单、本体空间、运行策略和验收策略。
- `AgentApplication` 已增加 `review_pack_id`、`review_pack_version`，合同/招标应用可以绑定固定规则包。
- `GET/POST/PATCH /api/v1/applications` 管理应用。
- `GET /api/v1/applications/{id}/runtime-contract` 展示实际启用的主控、provider、工具、本体、评审规则包和策略。
- Chat 请求支持 `application_id`，运行时从应用解析主控 Agent、工具白名单、provider 白名单、本体空间和验收策略。
- `task_frame` 写入 `application_id`、`business_domain`、`scenario_type`。
- 前端新增 ApplicationManager，侧边栏把“业务应用”放到“管理专家”之前。

下一步动作：

- 应用先绑定已发布的规则、本体和映射版本，再谈模板和搭建体验。
- 给常见业务场景补模板时，模板应该包含规则条目、本体条目和映射条目的草稿，不只是应用配置。
- 把应用运行报表接到审计面板，按应用聚合会话、工具调用、命中规则、产物和失败原因。

### 3. 运行时扩展契约

现在已经新增 `backend/app/agents/runtime_capabilities/`，用于注册任务运行时 provider。旧的 `build_task_frame()`、`build_execution_plan()`、`evaluate_task_completion()` 入口没有改，内部会先选择 provider，再调用 provider 的分类、计划和验收逻辑。

当前接口：

```python
class RuntimeCapabilityProvider(Protocol):
    name: str
    version: str
    task_kinds: list[str]
    priority: int

    def catalog(self) -> dict: ...
    def match(self, context: RuntimeCapabilityContext) -> float: ...
    def classify_task(self, context: RuntimeCapabilityContext) -> str: ...
    def build_frame(self, context: RuntimeCapabilityContext) -> dict: ...
    def build_plan(self, context: RuntimeCapabilityContext) -> dict: ...
    def evaluate(self, context: RuntimeCapabilityContext) -> dict: ...
```

已落地动作：

- `DefaultRuntimeCapabilityProvider` 承接当前 `general`、`realtime_research`、`engineering`、`business_review`。
- `register_runtime_capability_provider()` 支持业务模块注册 provider。
- `RuntimeCapabilityContext` 固定传入 query、semantic frame、agent profile、available tools、plan、artifacts、messages 和 final text。
- `task_frame`、`execution_plan`、`task_evaluation` 写入 `runtime_provider`，前端和历史回放可以知道本次由哪个 provider 接管。
- `/graph/runtime/capabilities` 返回 `providers[]`，GraphTracePanel 展示 provider 和 task kinds。

下一步动作：

- Agent Profile 可配置允许哪些 provider。
- 模型分类回退只能作为 provider 内部策略，输出仍必须落到固定字段。

### 4. Plan-aware Tool Policy

工具执行器不能只看 `pending_tool_calls` 和 Agent runtime policy。现在已经新增 `validate_tool_against_plan()`，工具执行前会读取 `execution_plan.current_step`、步骤候选工具和任务约束，给出准入决策。

当前规则：

- 当前 step 有 `tool_candidates` 时，工具名、类别或通配候选必须命中。
- 工具命中后续未完成步骤时允许执行，并把 `plan_step_id` 写回事件。
- 任务要求外部事实时，`web_search` 可以作为检索证据工具放行。
- 已存在明确候选工具但本次工具完全不匹配时，直接拦截。
- 没有任何步骤声明候选工具时，先放行并标记 `policy_decision=warn`，避免早期阶段误伤正常工具。

已落地字段：

- `tool_runtime.plan_step_id`
- `tool_runtime.policy_decision`: `allow | warn | deny`
- `tool_runtime.policy_reason`
- `execution_artifacts[].metadata.plan_step_id`
- `execution_artifacts[].metadata.policy_decision`
- `execution_artifacts[].metadata.policy_reason`

下一步动作：

- 把工具注册表的 `metadata.category` 和能力标签规范化。
- 给文件、终端、HTTP、数据库类工具增加更细的 effect 分类。
- 高风险工具在 `policy_decision=warn` 时改为要求确认，而不是直接执行。

### 5. 工具结果外置

现在工具结果不再只回填到消息和 runtime events。短摘要仍留在 `tool_runtime_events`，完整结果写入 `tool_artifacts`，前端通过 `artifact_id` 按需展开。

已新增表 `tool_artifacts`：

```text
id
session_id
message_id
user_id
agent_id
request_id
tool_call_id
tool_name
content_type
preview
content
artifact_metadata
size_bytes
created_at
```

已落地动作：

- `tool_executor_node` 在工具成功、拦截、异常时尝试写入产物。
- `tool_runtime` 事件带 `artifact_id`。
- `execution_artifacts[].metadata.artifact_id` 保留索引。
- `GET /api/v1/messages/{message_id}/artifacts` 返回消息级产物列表。
- `GET /api/v1/messages/artifacts/{artifact_id}` 返回完整产物。
- ChatView 工具卡片出现“查看产物”按钮，按需加载完整内容。

当前取舍：

- 工具消息仍保留 `str(res)`，是为了不一次性改动模型续写链路。下一步再把 tool message 改成 `preview + artifact_id`。
- artifact 写入失败不会中断对话，只会让本次工具事件没有 `artifact_id`。

### 5. Runtime Console

前端不能只显示聊天内容。平台用户需要看到一次运行为什么这样执行。

当前已经接入：

- ChatView 消息内展示 `task_runtime`、本体运行态、工具运行态。
- GraphTracePanel 展示运行图节点，并读取 `/graph/runtime/capabilities`。
- GraphTracePanel 已接入本轮 `runtimeEvents`，按时间线混排 `node_event`、`task_runtime`、`tool_runtime`、`ontology_runtime`、`task_evaluation`。
- GraphTracePanel 顶部展示本轮任务类型、计划状态、验收状态、工具数、拦截数和产物数。
- `node_event` 已带 `input_summary`、`output_summary`、`duration_ms`，用于定位节点进入时状态、退出时改动和耗时。
- GraphTracePanel 已按 `execution_plan.steps[]` 聚合工具调用、策略结果、产物数量和验收检查缺口。
- 会话运行轨迹 drawer 已展示任务验收检查、计划步骤、修复次数、缺口和工具产物统计。
- 会话运行轨迹 drawer 已支持按计划步骤展开关联工具的 `artifact_id`，复用 `GET /api/v1/messages/artifacts/{artifact_id}` 按需读取完整产物。

下一步：

- 会话运行轨迹 drawer 后续可补按步骤、工具名、产物状态过滤，方便长会话里定位一次具体工具调用。

### 6. E2E 验证

现在单元测试覆盖了任务分类、计划生成、计划推进、产物记录、验收和修复。还缺整链路。

建议新增用例：

- 旧拓扑模板编译后能自动补齐 task nodes。
- SSE 中按顺序出现 `task_runtime -> node_event -> tool_runtime -> task_evaluation`。
- 历史消息能从 `runtime_events.task_runtime` 恢复。
- `max_task_repairs=0` 时失败不修复，`max_task_repairs=1` 时只修一次。
- 前端 build 不因新增 runtime 字段失败。

## 近期开发顺序

建议按下面顺序推进，不要同时铺太多面：

1. 映射条目生产线：补来源字段到本体字段的结构化映射和 `compile-mapping`。
2. 规则和本体资产台补编辑、批量导入、废弃和样例回放。
3. 应用绑定固定版本：`AgentApplication` 支持 `schema_version`、`mapping_version`、`rule_version`。
4. 运行报表：按应用聚合会话、工具调用、命中规则、产物和失败原因。

## 取舍

短期不建议先做复杂多智能体市场、角色模板市场或大而全工作流编辑器。现在真正影响框架成型的是运行时状态和执行约束。

短期也不建议把所有判断都交给模型。分类、计划、验收可以逐步引入模型，但输出字段要固定，调用点要可测试。否则系统会回到“几段提示词解释一切”的状态。
