# Contributing to UniAI Kernel

Thank you for contributing to UniAI Kernel! This project has evolved into a **Dynamic Agentic OS** powered by LangGraph. This guide outlines how to contribute to our new orchestration-centric architecture.

## 🏗️ Core Architecture (v2.1+)

UniAI Kernel is built on three pillars:
1.  **LangGraph State Machine**: Orchestrates complex workflows through directed graphs.
2.  **Plugin Registry**: Manages tools and expert agent profiles.
3.  **Real-Time Telemetry**: Bridges internal graph execution with SSE streaming to the frontend.

### The Execution State
All nodes operate on the `AgentGraphState`. When adding new features, you may need to update this state in `backend/app/core/graph_state.py`.

---

## 🛠️ How to Extend

### 1. Adding a New Graph Node
Nodes are atomic logic units. To add one:
1.  Create a function in `backend/app/agents/nodes/`:
    ```python
    async def my_custom_node(state: AgentGraphState, config: RunnableConfig) -> dict:
        # 1. Access configurable parameters
        callback = config["configurable"]["stream_callback"]
        
        # 2. Perform logic
        await callback.emit_node_event("start", "my_custom_node")
        # ... logic ...
        
        # 3. Return updated state fields
        return {"messages": state["messages"] + [...]}
    ```
2.  **Important**: Nodes should be idempotent and handle errors gracefully.

### 2. Defining Custom Topologies (Workflows)
You can define new workflows without changing the core Python logic:
1.  Define a **Topology JSON** (refer to `GraphRegistry` for schema).
2.  Register your template in `backend/app/agents/graph_registry.py` or via the database `graph_templates` table.
3.  Specify the `graph_template_id` in your chat request to trigger the custom flow.

### 3. Implementing Self-Healing Logic
If your node is prone to failure, register its healing strategy in `backend/app/agents/auto_heal.py`. This ensures the system can automatically retry or fallback to a healthy node.

---

## 🎨 Frontend Contributions
The UI is built with **React + Ant Design**.
- **Execution Visualization**: Managed in `frontend/src/components/GraphTracePanel.tsx`. 
- **Artifacts**: New canvas types should be added to `frontend/src/components/ArtifactCanvas.tsx`.

---

## 🚀 Development Workflow

1.  **Setup**: Use `uv sync` to install dependencies.
2.  **Environment**: Copy `.env.example` to `.env` and configure your API keys.
3.  **Trace**: Use the **Graph Trace** panel in the UI to debug your node transitions in real-time.
4.  **Backend Testing**: Run `pytest` or use the provided scripts in `backend/scripts/`.

### Commit Guidelines
We use [Conventional Commits](https://www.conventionalcommits.org/):
- `feat(agent)`: A new agent capability.
- `feat(graph)`: Changes to graph logic or registry.
- `fix(node)`: Bug fix in a specific node.
- `refactor(core)`: Internal architecture improvements.

---

Thank you for helping build the future of AI orchestration! 🚀
