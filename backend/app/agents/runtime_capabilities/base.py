"""Shared runtime capability provider contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class RuntimeCapabilityContext:
    query: str = ""
    semantic_frame: dict[str, Any] = field(default_factory=dict)
    semantic_slots: dict[str, Any] = field(default_factory=dict)
    agent_profile: dict[str, Any] = field(default_factory=dict)
    allowed_provider_names: list[str] | None = None
    available_tools: list[str] = field(default_factory=list)
    enable_swarm: bool = False
    task_frame: dict[str, Any] = field(default_factory=dict)
    execution_plan: dict[str, Any] = field(default_factory=dict)
    execution_artifacts: list[dict[str, Any]] = field(default_factory=list)
    messages: list[dict[str, Any]] = field(default_factory=list)
    assistant_text: str = ""


@runtime_checkable
class RuntimeCapabilityProvider(Protocol):
    name: str
    version: str
    task_kinds: list[str]
    priority: int

    def catalog(self) -> dict[str, Any]:
        ...

    def match(self, context: RuntimeCapabilityContext) -> float:
        ...

    def classify_task(self, context: RuntimeCapabilityContext) -> str:
        ...

    def build_frame(self, context: RuntimeCapabilityContext) -> dict[str, Any]:
        ...

    def build_plan(self, context: RuntimeCapabilityContext) -> dict[str, Any]:
        ...

    def evaluate(self, context: RuntimeCapabilityContext) -> dict[str, Any]:
        ...
