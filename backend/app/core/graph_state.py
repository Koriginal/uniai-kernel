"""
UniAI Kernel — 图状态定义

定义 LangGraph 状态图使用的全局状态类型与配置上下文类型。
状态在图节点之间流转，配置在整个图执行期间保持不变。
"""
from typing import TypedDict, Optional, Any
import operator
from typing_extensions import Annotated


class AgentGraphState(TypedDict):
    """
    对话图的可变状态，在节点之间流转。

    字段语义：
    - messages: 发送给 LLM 的完整消息列表（由每个 agent_node 更新）
    - iteration_count: 当前图循环次数（用于防无限递归）
    - pending_tool_calls: 上一次 LLM 响应中的 tool_calls 列表
    - has_pending_handoff: 是否存在待处理的专家移交
    - handoff_target_id: 移交目标的 agent_id
    - current_agent_id: 当前活跃的智能体 ID
    - current_agent_profile: 当前活跃智能体的 Profile 快照 (dict)
    - called_expert_ids: 已被调用过的专家 ID 列表（防重复）
    - wrapping_expert_id: 当前正在发送内容的专家 ID（用于 <collaboration> 标签管理）
    - total_assistant_content: 整个请求周期内累积的助手文本内容
    - current_msg_id: 当前正在更新的数据库消息 ID
    - total_tool_calls_list: 跨迭代累积的全部工具调用记录
    - global_tool_index_offset: 全局工具索引偏移器（防止前端 JSON 流粘连）
    - iter_text: 当前迭代产生的文本内容
    - interaction_mode: 当前交互形态（chat/workflow/delegated_app 等）
    - semantic_frame: 当前任务的语义框架摘要，供未来本体驱动调度使用
    - semantic_slots: 当前任务的结构化语义槽位
    - pending_delegate_type: 最近一次待处理移交类型（expert/orchestrator）
    """
    messages: list
    iteration_count: int
    pending_tool_calls: list
    has_pending_handoff: bool
    handoff_target_id: Optional[str]
    current_agent_id: str
    current_agent_profile: Optional[dict]
    called_expert_ids: list
    wrapping_expert_id: Optional[str]
    total_assistant_content: str
    current_msg_id: Optional[str]
    total_tool_calls_list: list
    global_tool_index_offset: int
    iter_text: str
    interaction_mode: str
    semantic_frame: Optional[dict]
    semantic_slots: dict
    pending_delegate_type: Optional[str]
    # --- [New: Phase 2] 自维护字段 ---
    recovery_count: int           # 本会话累计恢复次数
    last_healthy_node: Optional[str]        # 最后成功执行的节点名称
    execution_trace: list         # 执行节点路径追踪 [node_name, ...]


class GraphConfig(TypedDict, total=False):
    """
    图执行的不可变配置，通过 config["configurable"] 传递。

    这些字段在整个图执行期间保持不变。
    """
    # 会话上下文
    thread_id: str  # = session_id, 同时作为 checkpointer 的 key
    session_id: str
    user_id: str
    request_id: str
    model_name: str

    # 固定身份
    orchestrator_agent_id: str
    orchestrator_agent_profile: Optional[dict]

    # 功能开关
    enable_canvas: bool
    enable_swarm: bool
    enable_memory: bool
    max_iterations: int

    # 注入的上下文
    expert_prompt_catalog: str

    # 流式回调（节点通过此接口推送 SSE 事件到前端）
    stream_callback: Any  # StreamCallback 实例

    # 数据库会话
    db: Any  # AsyncSession 实例
