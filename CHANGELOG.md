# Changelog

All notable changes to this project will be documented in this file.

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
