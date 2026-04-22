# Changelog

All notable changes to this project will be documented in this file.

## [2.3.0] - 2026-04-22
### Added
- **UI/UX Overhaul**: Reimagined sidebar with collapsible state, improved navigation hierarchy, and new "BrandCat" logo across Login and main Layout.
- **Advanced Agent Topology Editor**: Empowered orchestration with Undo/Redo support, automatic layouting (Dagre-based), node alignment tools, and multi-selection capabilities.
- **Sub-App Delegation (Invoke)**: Introduced application-level delegation between orchestrators via "Invoke Edges" and a dedicated backend `orchestrator_invoke_node`.
- **Agent Governance Center**: Added "Operations View" in `AgentManager` for high-density batch management, real-time health monitoring, and routing observability insights.
- **Semantic Ontology Layer**: Launched a new ontology package for managing structured delegation policies and semantic context across the agent graph.
- **Wildcard Tool Support**: Agents can now be configured with `*` to automatically inherit all registered tools.

### Improved
- **Graph Execution Streaming**: Refined `handoff_node` and `synthesize_node` for more consistent status updates and chunk ID handling during streaming.
- **Responsive Layout**: Enhanced `index.css` with specialized styles for collapsed navigation and glassmorphism-inspired card transitions.

## [2.2.1] - 2026-04-09
### Added
- **Concurrent Initialization Safety**: Implemented `_init_lock` and 30s timeout protection for `AsyncPostgresSaver` in `pg_checkpointer.py` to prevent DDL deadlocks during high-concurrency boot.
- **Smart Expert Ranking**: Integrated performance scoring into the `EXPERT_DIRECTORY`. Highly successful agents are now automatically prioritized in the system prompt for better orchestrator decision-making.
- **Improved Handoff Context**: Captured and propagated handoff reasons and agent transfer histories to ensure intent continuity.
- **Database Fallback Engine**: Enhanced `GraphRegistry` with graceful degradation logic; if the DB is unavailable, the kernel now automatically falls back to the hardcoded default graph.

### Fixed
- Resolved potential race conditions during graph compilation.
- Fixed UI inconsistencies in the `AgentManager` after bulk deletion or activation toggles.

## [2.2.0] - 2026-04-09
### Added
- **Advanced Agent Governance**: Introduced explicit roles (`orchestrator`/`expert`), dynamic routing keywords, and a "Silent Validation" API for pre-deployment checks.
- **Topology Version Control**: Full support for snapshotting graph topologies. Users can now edit workflows, save versions, and switch between active snapshots in real-time.
- **Dynamic Tools V2**: Added real-time validation and a "Test" execution engine for API, MCP, and CLI tools.
- **Enhanced Audit Dashboard**: Aggregated summary statistics for agents, including success rate heatmaps and performance trend analysis.
- **Multimodal Chat Support**: Updated the agent-specific chat API to support multimodal content (images/text arrays).

### Changed
- Replaced `AgentTopologyGraph` with the interactive `AgentTopologyEditor`.
- Refactored `PluginRegistry` to support lazy-loading and hot-swapping of dynamic tools via database triggers.

## [2.1.0] - 2026-04-09
### Added
- **Dynamic Graph Registry**: Support for loading graph topologies from the database via JSON definitions.
- **Adaptive Self-Healing Engine**: Implemented pre-node checks and error recovery mechanisms in the orchestration layer.
- **Agent Performance Scorecards**: Detailed KPIs (success rate, latency, quality) for each expert agent in the UI.
- **Node-level Execution Tracing**: Real-time event streaming for graph node transitions (Start/End events).
- **PostgreSQL Persistence**: Replaced MemorySaver with an industrial-grade checkpointer for cross-session state recovery.

### Fixed
- Improved SSE streaming reliability with unified `[DONE]` signal sent directly from the graph execution task.
- Fixed UI message bubble alignment and horizontal scroll issues for long code blocks.

## [2.0.0] - 2026-04-08
### Added
- **LangGraph Integration**: Fully replaced the sequences chat loop with a StateGraph-based orchestration engine.
- **Swarm Intelligence**: Implemented multi-agent collaboration with dynamic handoffs (transfer_to_agent).
- **Artifacts Canvas**: Real-time side panel for rendering code, React components, and rich media.
- **Graph Trace Panel**: Visual execution path monitoring in the frontend.
- **Microkernel Architecture**: Decoupled core modules for faster startup and lazy dependency loading.

### Changed
- Refactored `AgentService` to act as a pure scheduler for the graph engine.
- Modernized frontend with Ant Design and enhanced Markdown rendering capabilities.

## [1.1.0] - 2026-04-03
### Added
- Stable multi-agent framework core.
- Modern settings center with user profile and security management.
- Multi-tenant model gateway supporting 100+ models via LiteLLM.

## [1.0.0] - 2026-03-30
### Added
- Initial release of UniAI Kernel.
- Basic streaming chat and model management.
- Apache 2.0 Licensing.

---
*Generated based on git history and architecture milestones.*
