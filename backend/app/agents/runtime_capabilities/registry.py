"""In-process registry for task runtime capability providers."""

from __future__ import annotations

from typing import Any

from app.agents.runtime_capabilities.base import RuntimeCapabilityContext, RuntimeCapabilityProvider

_PROVIDERS: dict[str, RuntimeCapabilityProvider] = {}


def register_runtime_capability_provider(provider: RuntimeCapabilityProvider) -> None:
    if not provider.name:
        raise ValueError("runtime capability provider requires a name")
    _PROVIDERS[provider.name] = provider


def unregister_runtime_capability_provider(name: str) -> None:
    _PROVIDERS.pop(name, None)


def list_runtime_capability_providers() -> list[RuntimeCapabilityProvider]:
    return sorted(
        _PROVIDERS.values(),
        key=lambda item: (getattr(item, "priority", 0), item.name),
        reverse=True,
    )


def select_runtime_capability_provider(context: RuntimeCapabilityContext) -> RuntimeCapabilityProvider:
    providers = list_runtime_capability_providers()
    if not providers:
        raise RuntimeError("no runtime capability provider registered")

    scored = [(provider.match(context), getattr(provider, "priority", 0), provider.name, provider) for provider in providers]
    scored.sort(reverse=True, key=lambda item: (item[0], item[1], item[2]))
    return scored[0][3]


def get_runtime_provider_catalog() -> list[dict[str, Any]]:
    catalog: list[dict[str, Any]] = []
    for provider in list_runtime_capability_providers():
        item = provider.catalog()
        item.setdefault("name", provider.name)
        item.setdefault("version", getattr(provider, "version", "unknown"))
        item.setdefault("task_kinds", getattr(provider, "task_kinds", []))
        item.setdefault("priority", getattr(provider, "priority", 0))
        catalog.append(item)
    return catalog
