# Agent Runtime 机制设计

本文档记录 UniAI Kernel 从“提示词驱动的 Agent”升级到“运行时驱动的 Agent”的落地方案。

当前主链路已经有 LangGraph、动态工具、本体运行时、专家 handoff、审计和 SSE 事件。问题不在于缺少提示词，而在于任务理解、拆解、执行和验收还没有独立状态。LLM 每轮根据 system prompt 自己决定是否调用工具、是否找专家、是否结束，路由器只在 tool_calls 出来之后做分流。

新的方向是：先把任务转成结构化状态，再让 LLM、工具执行器、专家路由、审计和前端都读取同一份状态。

## 当前边界

现有标准图：

```text
context -> agent -> tool_executor / handoff / orchestrator_invoke / synthesize
```

已经具备的能力：

- `context_node`：加载会话历史、长期记忆、语义解析、本体运行时预执行结果。
- `agent_node`：拼接 system prompt，暴露工具，流式调用模型，解析 tool_calls。
- `adaptive_router`：根据 pending tool_calls 决定进入工具、专家、子主控或结束。
- `tool_executor_node`：执行工具，写入 runtime_events 和审计。
- `synthesize_node`：专家结果归还主控。

主要缺口：

- 没有独立的任务框架，用户目标、约束、风险、验收条件都散在 prompt 和启发式判断里。
- 没有独立的执行计划，工具调用和专家派发依赖模型即时生成。
- 工具执行器无法知道当前任务步骤，只能执行 pending tool_calls。
- 前端和审计只能看到节点事件、工具事件，看不到“为什么这么执行”。

## 已落地改动

标准图新增 `task_planner` 和 `task_evaluator` 节点：

```text
context -> task_planner -> agent -> tool_executor / handoff / orchestrator_invoke / synthesize -> task_evaluator
```

新增模块：

- `backend/app/agents/task_runtime.py`
- `backend/app/agents/nodes/task_planner.py`
- `backend/app/agents/nodes/task_evaluator.py`

新增状态字段：

- `application_id`
- `application_context`
- `task_frame`
- `execution_plan`
- `execution_artifacts`
- `task_evaluation`
- `task_repair_count`
- `pending_repair`

`task_planner_node` 的职责：

1. 读取当前用户请求、`semantic_frame`、`semantic_slots`、Agent Profile、业务应用 runtime contract、可用工具目录。
2. 生成 `task_frame`，记录任务类型、用户目标、约束、风险和验收条件。
3. 生成 `execution_plan`，记录步骤、责任方、工具候选和完成标准。
4. 通过 SSE 发出 `task_runtime` 事件。
5. 写入当前 assistant message 的 `runtime_events.task_runtime`，方便历史回放和审计。

`agent_node` 现在会把结构化计划转成 `[TASK RUNTIME CONTRACT]` 注入本轮模型上下文。这里不是把所有机制继续塞进提示词，而是让 prompt 成为运行时状态的一种投影。后续路由器、工具执行器和前端可以直接读 `state["execution_plan"]`。

`task_evaluator_node` 在一次回答结束前读取 `task_frame`、`execution_plan`、`execution_artifacts` 和最终消息，生成 `task_evaluation`。如果验收失败且 `max_task_repairs` 没耗尽，会把计划重新打开，并把修复要求写回下一轮 `agent_node`。

## task_frame 字段

当前字段：

```json
{
  "task_id": "task_xxx",
  "application_id": "app_xxx",
  "business_domain": "risk",
  "scenario_type": "risk_review",
  "kind": "general | realtime_research | business_review | engineering | workflow | builder | analysis",
  "user_goal": "...",
  "semantic_frame": {},
  "semantic_slots": {},
  "constraints": {
    "allow_tools": true,
    "allow_web_search": true,
    "requires_external_facts": false,
    "requires_code_workspace": false,
    "requires_governance": false
  },
  "acceptance": [],
  "acceptance_policy": {},
  "risk_flags": []
}
```

如果请求带 `application_id`，`AgentService` 会先读取业务应用：

- `primary_agent_id` 决定本轮主控 Agent。
- `runtime_provider_names` 限制 provider 选择；留空只使用 `default_task_runtime`。
- `tool_names` 先限制可暴露和可执行工具，再进入 plan-aware policy。
- `ontology_space_id` 写入本体运行配置。
- `acceptance_policy` 进入 `task_frame`，后续验收策略可读取。

当前分类是规则优先：

- `realtime_research`：今日、最新、当前、实时、价格、新闻、汇率等请求。
- `business_review`：合同、协议、风控、合规、审查、责任上限等业务审核请求。
- `engineering`：代码、修复、测试、接口、重构、仓库等工程请求。
- `general`：默认问答或轻量任务。

后续可以把 `classify_task` 换成模型或小模型分类，但输出结构不要变。

## execution_plan 字段

当前字段：

```json
{
  "plan_id": "plan_xxx",
  "task_id": "task_xxx",
  "status": "planned",
  "steps": [
    {
      "id": "understand",
      "title": "确认用户要查的对象、时间范围和口径",
      "owner": "orchestrator | expert | tool",
      "status": "pending",
      "tool_candidates": [],
      "depends_on": []
    }
  ],
  "current_step": "understand",
  "done_criteria": []
}
```

不同任务类型的默认计划：

- `realtime_research`：understand -> retrieve -> synthesize。
- `business_review`：extract -> evaluate -> explain。
- `engineering`：inspect -> delegate 可选 -> change -> verify。
- `general`：understand -> solve -> respond。

## 已接入的推进机制

### 1. 计划执行状态推进

当前已提供统一函数：

```python
advance_execution_plan(state, event_type, payload) -> dict
```

节点不直接拼状态结构，而是按事件推进计划：

- `agent`：记录模型动作和回答阶段。
- `tool_executor`：记录工具调用和工具结果产物。
- `handoff`：记录专家移交。
- `orchestrator_invoke`：记录子主控调用。
- `synthesize`：记录汇总归还。
- `task_evaluator`：记录验收结果，并决定是否进入修复。

### 2. 计划约束工具执行

当前已提供统一函数：

```python
validate_tool_against_plan(tool_name, tool_metadata, task_frame, execution_plan) -> dict
```

工具执行器在真正调用工具前执行这层检查。它不会替代 Agent runtime policy，而是补一个计划约束：

- 当前步骤有 `tool_candidates` 时，工具名、类别或通配候选必须命中。
- 工具命中后续未完成步骤时，允许执行，并把命中的 `plan_step_id` 写入事件。
- `requires_external_facts=true` 时，`web_search` 作为证据检索工具放行。
- 已存在明确候选工具但本次工具完全不匹配时，工具事件标记 `blocked`。
- 没有步骤声明候选工具时，先放行并标记 `policy_decision=warn`。

工具运行事件新增字段：

```json
{
  "plan_step_id": "retrieve",
  "policy_decision": "allow | warn | deny",
  "policy_reason": "tool matches current plan step candidates"
}
```

这些字段会进入 SSE、消息 `runtime_events.tool_runtime_events`、审计输入和 `execution_artifacts[].metadata`。

### 3. 工具产物外置

当前已新增 `tool_artifacts` 表，工具事件保留短摘要，完整结果落库：

```text
tool_runtime.result.preview          # 前端列表和消息回放使用
tool_runtime.artifact_id             # 完整产物索引
tool_artifacts.content               # 完整工具输出
tool_artifacts.artifact_metadata     # 策略、步骤、耗时等运行信息
```

读取接口：

```text
GET /api/v1/messages/{message_id}/artifacts
GET /api/v1/messages/artifacts/{artifact_id}
```

当前阶段仍保留 tool message 的 `str(res)`，避免影响模型拿工具结果继续生成。下一步要把 tool message 缩成 `preview + artifact_id`，并由 context builder 在需要时按 artifact id 取回。

### 4. 运行时能力接口

当前已提供接口：

```text
GET /api/v1/graph/runtime/capabilities
```

返回内容包括：

- `capabilities`：当前内核能力目录。
- `state_fields`：运行图会使用的状态字段。
- `events`：前端和 SDK 需要监听的事件类型。
- `request_config`：调用方可传的运行时参数。

### 5. 节点遥测摘要

`wrap_telemetry()` 现在会在 `node_event` 中输出轻量摘要：

```json
{
  "type": "node_event",
  "event": "end",
  "node": "tool_executor",
  "payload": {
    "status": "success",
    "duration_ms": 42.3,
    "input_summary": {},
    "output_summary": {}
  }
}
```

`input_summary` 只包含计数和状态字段：

- `message_count`
- `pending_tool_calls`
- `current_agent_id`
- `iteration_count`
- `task_kind`
- `plan.status`
- `plan.current_step`
- `artifact_count`
- `repair_count`
- `pending_repair`

`output_summary` 记录本节点改变了哪些运行状态：

- `updated_keys`
- `message_delta`
- `pending_tool_calls`
- `iter_text_chars`
- `plan.status`
- `plan.current_step`
- `artifact_count`
- `task_evaluation_status`
- `pending_repair`

这里不输出消息正文、工具参数正文或工具完整结果。完整工具结果走 `tool_artifacts`，消息正文仍由 ChatMessage 保存。

## 后续要接的机制

### 1. Runtime capability provider

当前已经有 `backend/app/agents/runtime_capabilities/`：

- `RuntimeCapabilityContext`：统一传 query、semantic frame、Agent Profile、可用工具、计划、产物、消息和最终回答。
- `RuntimeCapabilityProvider`：提供 `match()`、`classify_task()`、`build_frame()`、`build_plan()`、`evaluate()`。
- `register_runtime_capability_provider()`：业务模块注册自己的任务类型和验收逻辑。
- `DefaultRuntimeCapabilityProvider`：保留当前默认规则，避免老入口改动。

后续每加一类任务，不应该先改 system prompt，也不应该直接改全局 `classify_task`。先新增 provider，再决定是否让某个 Agent Profile 启用它。

### 2. Tool policy 表

建议新增 `tool_policy_rules`：

- `id`
- `org_id`
- `user_id`
- `agent_id`
- `tool_name`
- `effect`: `allow | deny | approval_required`
- `resource_pattern`
- `operation`
- `priority`
- `is_active`
- `created_at`

执行顺序：

1. Agent Profile 的 `runtime_policy`。
2. 组织/用户/Agent 的 `tool_policy_rules`。
3. 工具自己的 `validateInput`。
4. 动态工具类型策略，例如 CLI allowlist、MCP server allowlist、HTTP host allowlist。

### 3. Skill 层

动态工具解决“能执行什么”，Skill 解决“某类任务怎么做”。建议新增 `agent_skills`：

- `name`
- `description`
- `when_to_use`
- `prompt`
- `allowed_task_kinds`
- `allowed_agent_types`
- `org_id`
- `version`
- `is_active`

`task_planner_node` 根据 `task_frame.kind` 和 `semantic_slots` 选择 Skill，把 Skill 作为 `task_frame.skills` 注入，而不是把所有技能都塞给模型。

## 验收口径

这一轮改动的验收不是“模型回答更聪明”，而是运行时出现了可观测的结构：

- SSE 中能看到 `task_runtime` 事件。
- SSE 中能看到 `task_runtime_update` 和 `task_evaluation` 事件。
- `ChatMessage.runtime_events.task_runtime` 能回放任务框架和计划。
- `agent_node` 的 prompt 中有来自状态的 `[TASK RUNTIME CONTRACT]`。
- 单元测试覆盖任务分类、计划生成、prompt 投影、计划推进、产物记录、验收和修复。

后续每加一类任务，不应该先改 system prompt，而应该先补 provider：

1. `match`
2. `classify_task`
3. `build_frame`
4. `build_plan`
5. 计划状态推进
6. 工具/专家/验收策略
