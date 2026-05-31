# UniAI Kernel 平台方向与当前差距

UniAI Kernel 的定位不是单个聊天机器人，也不是一组 system prompt。它应该是一个智能体开发平台和运行框架：平台负责定义 Agent、工具、运行图、任务状态、权限和审计；运行框架负责把用户请求转成可执行状态，并在图节点之间推进。

这份文档按当前代码来写，不按口号写。这里的每一项都应该能落到模块、字段、接口或下一步开发动作。

## 平台边界

当前平台至少要分成七层：

1. Agent 定义层：`backend/app/models/agent.py`、Agent Profile、runtime policy、专家角色和 handoff 策略。
2. 运行图层：`backend/app/agents/graph_builder.py`、`graph_registry.py`、拓扑版本和节点编译。
3. 任务运行时层：`backend/app/agents/task_runtime.py`、`task_planner`、`task_evaluator`。
4. 工具层：动态工具、MCP 工具、工具执行器、工具审计和 tool runtime events。
5. 语义与本体层：semantic frame、ontology runtime、本体空间、规则检查和补数字段。
6. 观测层：SSE `node_event`、`task_runtime`、`tool_runtime`、`task_evaluation`，以及消息上的 `runtime_events`。
7. 控制台层：ChatView、GraphTracePanel、AgentManager、ToolRegistry、OntologyWorkbench。

这几个层之间不能继续靠提示词传隐式状态。任务目标、执行计划、工具产物、验收结果要进入状态字段和事件流。

## 当前成熟度

后端内核已经从“提示词驱动”进入“运行时驱动”的早期阶段。

已落地的部分：

- 标准图里已有 `context -> task_planner -> agent -> tool_executor / handoff / orchestrator_invoke / synthesize -> task_evaluator`。
- `task_frame` 记录任务类型、用户目标、约束、风险标记和验收条件。
- `execution_plan` 记录步骤、责任方、工具候选、当前步骤和完成标准。
- `execution_artifacts` 记录工具、专家和回答阶段留下的可回放产物。
- `task_evaluator` 会在结束前检查任务完成度，并在失败时按 `max_task_repairs` 重新打开计划。
- 旧拓扑通过 `graph_registry._normalize_runtime_topology()` 自动补齐 `task_planner` 和 `task_evaluator`，避免历史模板直接崩。
- `/api/v1/graph/runtime/capabilities` 已暴露运行时能力目录、状态字段、事件类型和请求配置。

还没有完成的部分：

- 任务分类仍是规则优先，不是可配置策略，也没有模型分类回退。
- 计划步骤只做到节点级推进，还没有强约束工具调用必须匹配当前步骤。
- `execution_artifacts` 目前存在状态和消息 runtime events 里，还没有独立表承载大结果。
- 修复循环是一次性图内重试，不是完整的子任务队列，也没有人工确认点。
- 前端控制台刚开始接入任务运行态，还没有形成专门的运行图调试台。
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

### 1. 运行时扩展契约

现在 `task_runtime.py` 已经有能力目录，但插件或业务模块还不能注册自己的任务类型。

建议新增接口：

```python
class RuntimeCapabilityProvider(Protocol):
    name: str
    task_kinds: list[str]

    def match(self, state: GraphState) -> float: ...
    def build_frame(self, state: GraphState) -> dict: ...
    def build_plan(self, task_frame: dict, state: GraphState) -> dict: ...
    def evaluate(self, state: GraphState) -> dict: ...
```

落地动作：

- 在 `backend/app/agents/runtime_capabilities/` 下放 provider。
- `task_runtime.py` 保留默认 provider。
- `/graph/runtime/capabilities` 返回 provider 名称、版本、任务类型和事件。
- Agent Profile 可配置允许哪些 provider。

### 2. Plan-aware Tool Policy

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

### 3. 工具结果外置

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

### 4. Runtime Console

前端不能只显示聊天内容。平台用户需要看到一次运行为什么这样执行。

当前已经接入：

- ChatView 消息内展示 `task_runtime`、本体运行态、工具运行态。
- GraphTracePanel 展示运行图节点，并读取 `/graph/runtime/capabilities`。
- GraphTracePanel 已接入本轮 `runtimeEvents`，按时间线混排 `node_event`、`task_runtime`、`tool_runtime`、`ontology_runtime`、`task_evaluation`。
- GraphTracePanel 顶部展示本轮任务类型、计划状态、验收状态、工具数、拦截数和产物数。
- `node_event` 已带 `input_summary`、`output_summary`、`duration_ms`，用于定位节点进入时状态、退出时改动和耗时。
- GraphTracePanel 已按 `execution_plan.steps[]` 聚合工具调用、策略结果、产物数量和验收检查缺口。

下一步：

- 会话运行轨迹 drawer 中补 `task_evaluation.checks` 和 repair 记录。

### 5. E2E 验证

现在单元测试覆盖了任务分类、计划生成、计划推进、产物记录、验收和修复。还缺整链路。

建议新增用例：

- 旧拓扑模板编译后能自动补齐 task nodes。
- SSE 中按顺序出现 `task_runtime -> node_event -> tool_runtime -> task_evaluation`。
- 历史消息能从 `runtime_events.task_runtime` 恢复。
- `max_task_repairs=0` 时失败不修复，`max_task_repairs=1` 时只修一次。
- 前端 build 不因新增 runtime 字段失败。

## 近期开发顺序

建议按下面顺序推进，不要同时铺太多面：

1. 稳定当前主链路：后端测试、前端 build、旧拓扑迁移验证。
2. 补工具计划约束：先做 `validate_tool_against_plan`，再扩展审计字段。
3. 补 runtime console：先让一次运行的计划、节点、工具、验收在 UI 上串起来。
4. 补 artifact 表：先支持工具结果，再支持专家输出和文件产物。
5. 做 runtime capability provider：把默认规则从 `task_runtime.py` 里拆出来，形成可扩展接口。

## 取舍

短期不建议先做复杂多智能体市场、角色模板市场或大而全工作流编辑器。现在真正影响框架成型的是运行时状态和执行约束。

短期也不建议把所有判断都交给模型。分类、计划、验收可以逐步引入模型，但输出字段要固定，调用点要可测试。否则系统会回到“几段提示词解释一切”的状态。
