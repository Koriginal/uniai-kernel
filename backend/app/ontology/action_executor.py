from __future__ import annotations

import asyncio
import ipaddress
import re
import socket
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional, Sequence
from urllib.parse import urljoin, urlparse

import httpx

from app.core.config import settings
from app.ontology.domain_models import InstanceGraph, OntologyDataSourceRecord

SecretResolver = Callable[[Optional[str], str], Awaitable[Optional[str]]]
AuditLogger = Callable[[str, str, Dict[str, Any]], Awaitable[None]]


@dataclass
class OntologyExecutionResult:
    mode: str = "safe_plan"
    status: str = "skipped"
    applied_patch_count: int = 0
    executions: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    graph: Optional[InstanceGraph] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mode": self.mode,
            "status": self.status,
            "applied_patch_count": self.applied_patch_count,
            "executions": self.executions,
            "warnings": self.warnings,
        }


class OntologyActionExecutor:
    """Executes the safe subset of ontology action plans.

    V1 intentionally supports only deterministic fixture-backed data enrichment.
    Live DB/API execution should be added behind explicit approvals and network policy.
    """

    def execute_safe(
        self,
        *,
        graph: InstanceGraph,
        action_plan: Dict[str, Any],
        data_sources: Sequence[OntologyDataSourceRecord],
    ) -> OntologyExecutionResult:
        result = OntologyExecutionResult(mode="safe_plan", status="skipped", graph=graph.model_copy(deep=True))
        missing_fields = action_plan.get("missing_fields") or []
        if not missing_fields:
            result.status = "no_missing_fields"
            return result

        data_source_by_id = {item.id: item for item in data_sources}
        steps = action_plan.get("steps") or []
        data_steps = [step for step in steps if step.get("kind") == "data_source"]
        if not data_steps:
            result.warnings.append("action plan has missing fields but no data_source step")
            return result

        for step in data_steps:
            source_id = step.get("data_source_id")
            if not source_id:
                result.executions.append({
                    "step_id": step.get("step_id"),
                    "status": "skipped",
                    "reason": "no data_source_id selected by planner",
                })
                continue
            source = data_source_by_id.get(source_id)
            if not source:
                result.executions.append({
                    "step_id": step.get("step_id"),
                    "data_source_id": source_id,
                    "status": "skipped",
                    "reason": "data source not available or not accessible",
                })
                continue
            execution = self._execute_fixture_source(result.graph, source, missing_fields, step.get("step_id") or "data_source")
            result.executions.append(execution)
            result.applied_patch_count += int(execution.get("applied_patch_count") or 0)

        result.status = "applied" if result.applied_patch_count > 0 else "skipped"
        if result.applied_patch_count == 0 and not result.warnings:
            result.warnings.append("no safe executable data source produced patches")
        return result

    async def execute(
        self,
        *,
        graph: InstanceGraph,
        action_plan: Dict[str, Any],
        data_sources: Sequence[OntologyDataSourceRecord],
        secret_resolver: Optional[SecretResolver] = None,
        audit_logger: Optional[AuditLogger] = None,
    ) -> OntologyExecutionResult:
        """Execute fixture and explicitly approved live data-source enrichments.

        Live execution is intentionally gated by multiple controls:
        global feature flag, active data source, runtime.live_approved, read-only
        adapter policy, timeout, SSRF validation for HTTP, SQL whitelist for DB,
        audit event and field-level redaction in returned execution details.
        """
        if not settings.ONTOLOGY_ENABLE_LIVE_DATA_SOURCE_EXECUTION:
            return self.execute_safe(graph=graph, action_plan=action_plan, data_sources=data_sources)

        result = OntologyExecutionResult(mode="governed_runtime", status="skipped", graph=graph.model_copy(deep=True))
        missing_fields = action_plan.get("missing_fields") or []
        if not missing_fields:
            result.status = "no_missing_fields"
            return result

        data_source_by_id = {item.id: item for item in data_sources}
        steps = [step for step in (action_plan.get("steps") or []) if step.get("kind") == "data_source"]
        if not steps:
            result.warnings.append("action plan has missing fields but no data_source step")
            return result

        for step in steps:
            source_id = step.get("data_source_id")
            source = data_source_by_id.get(source_id) if source_id else None
            if not source:
                execution = {
                    "step_id": step.get("step_id"),
                    "data_source_id": source_id,
                    "status": "skipped",
                    "reason": "data source not available or not accessible",
                    "applied_patch_count": 0,
                }
            else:
                execution = await self._execute_source(
                    result.graph,
                    source,
                    missing_fields,
                    step.get("step_id") or "data_source",
                    secret_resolver=secret_resolver,
                )
            result.executions.append(execution)
            result.applied_patch_count += int(execution.get("applied_patch_count") or 0)
            if audit_logger and source:
                await audit_logger(
                    "ontology.datasource.runtime_execute",
                    execution.get("status") or "unknown",
                    self._audit_payload(source, execution),
                )

        result.status = "applied" if result.applied_patch_count > 0 else "skipped"
        if result.applied_patch_count == 0 and not result.warnings:
            result.warnings.append("no governed data source produced patches")
        return result

    async def _execute_source(
        self,
        graph: Optional[InstanceGraph],
        source: OntologyDataSourceRecord,
        missing_fields: Sequence[Dict[str, Any]],
        step_id: str,
        *,
        secret_resolver: Optional[SecretResolver],
    ) -> Dict[str, Any]:
        runtime = source.config.get("runtime") if isinstance((source.config or {}).get("runtime"), dict) else {}
        mode = str(runtime.get("mode") or "disabled").lower()
        if mode == "fixture":
            return self._execute_fixture_source(graph, source, missing_fields, step_id)
        gate = self._validate_live_gate(source, runtime)
        if gate:
            return self._skipped(step_id, source, gate)
        kind = source.kind.value if hasattr(source.kind, "value") else str(source.kind)
        if kind == "database":
            return await self._execute_live_db(graph, source, missing_fields, step_id, secret_resolver=secret_resolver)
        if kind == "api":
            return await self._execute_live_api(graph, source, missing_fields, step_id, secret_resolver=secret_resolver)
        return self._skipped(step_id, source, f"live execution adapter is not supported for {kind}")

    def _validate_live_gate(self, source: OntologyDataSourceRecord, runtime: Dict[str, Any]) -> Optional[str]:
        status = source.status.value if hasattr(source.status, "value") else str(source.status)
        if status != "active":
            return "data source must be active before live execution"
        if not runtime.get("live_approved"):
            return "live execution requires governance approval"
        mode = str(runtime.get("mode") or "").lower()
        if mode not in {"live_api", "live_db"}:
            return "runtime.mode must be live_api or live_db for governed live execution"
        return None

    async def _execute_live_db(
        self,
        graph: Optional[InstanceGraph],
        source: OntologyDataSourceRecord,
        missing_fields: Sequence[Dict[str, Any]],
        step_id: str,
        *,
        secret_resolver: Optional[SecretResolver],
    ) -> Dict[str, Any]:
        if not graph:
            return self._skipped(step_id, source, "graph is empty")
        if (source.protocol or "").lower() != "postgresql":
            return self._skipped(step_id, source, "only PostgreSQL live DB runtime is currently enabled")
        config = source.config or {}
        runtime = config.get("runtime") if isinstance(config.get("runtime"), dict) else {}
        sql = str(runtime.get("sql") or "").strip()
        sql_error = self._validate_readonly_sql(sql)
        if sql_error:
            return self._skipped(step_id, source, sql_error)

        try:
            import asyncpg
        except Exception as exc:  # pragma: no cover
            return self._skipped(step_id, source, f"asyncpg is not available: {exc}")

        password = await secret_resolver(source.secret_ref, source.space_id) if secret_resolver else None
        timeout = self._bounded_timeout(runtime.get("timeout_seconds"))
        max_rows = self._bounded_max_rows(runtime.get("max_rows"))
        patches: List[Dict[str, Any]] = []
        started = time.perf_counter()
        conn = None
        try:
            conn = await asyncpg.connect(
                host=str(config.get("host") or "127.0.0.1"),
                port=int(config.get("port") or 5432),
                user=str(config.get("user") or config.get("username") or "postgres"),
                password=password,
                database=str(config.get("database")),
                timeout=timeout,
                ssl=config.get("ssl") if isinstance(config.get("ssl"), bool) else None,
            )
            try:
                await conn.execute(f"SET statement_timeout = {max(int(timeout * 1000), 1000)}")
            except Exception:
                pass
            async with conn.transaction(readonly=True):
                for entity, missing in self._iter_missing_entities(graph, missing_fields):
                    params = self._build_query_params(entity.attributes or {}, runtime)
                    rows = await asyncio.wait_for(conn.fetch(sql, *params), timeout=timeout)
                    for row in list(rows)[:max_rows]:
                        patches.extend(self._apply_record_to_entity(entity, dict(row), [missing], runtime))
        except Exception as exc:
            return self._failed(step_id, source, f"live DB query failed: {exc}", started)
        finally:
            if conn:
                await conn.close()

        return self._execution_response(step_id, source, patches, "live DB query completed", started, runtime)

    async def _execute_live_api(
        self,
        graph: Optional[InstanceGraph],
        source: OntologyDataSourceRecord,
        missing_fields: Sequence[Dict[str, Any]],
        step_id: str,
        *,
        secret_resolver: Optional[SecretResolver],
    ) -> Dict[str, Any]:
        if not graph:
            return self._skipped(step_id, source, "graph is empty")
        config = source.config or {}
        runtime = config.get("runtime") if isinstance(config.get("runtime"), dict) else {}
        method = str(runtime.get("method") or "GET").upper()
        if method != "GET":
            return self._skipped(step_id, source, "live API runtime only permits GET requests")
        base_url = str(config.get("base_url") or "").rstrip("/")
        path_template = str(runtime.get("path") or runtime.get("url_path") or "").strip()
        allowed_hosts = runtime.get("allowed_hosts") or config.get("allowed_hosts") or []
        if not isinstance(allowed_hosts, list) or not allowed_hosts:
            return self._skipped(step_id, source, "live API runtime requires allowed_hosts")
        timeout = self._bounded_timeout(runtime.get("timeout_seconds"))
        token = await secret_resolver(source.secret_ref, source.space_id) if secret_resolver else None
        headers = dict(runtime.get("headers") or {}) if isinstance(runtime.get("headers"), dict) else {}
        if token:
            headers[str(runtime.get("auth_header") or "Authorization")] = f"Bearer {token}"

        patches: List[Dict[str, Any]] = []
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
                for entity, missing in self._iter_missing_entities(graph, missing_fields):
                    path = self._render_template(path_template, entity.attributes or {})
                    url = urljoin(f"{base_url}/", path.lstrip("/"))
                    self._assert_safe_url(url, [str(item) for item in allowed_hosts])
                    params = self._build_http_params(entity.attributes or {}, runtime)
                    response = await client.get(url, params=params, headers=headers)
                    raw = await response.aread()
                    if len(raw) > settings.ONTOLOGY_LIVE_EXECUTION_MAX_RESPONSE_BYTES:
                        raise ValueError("live API response exceeds max response bytes")
                    response.raise_for_status()
                    data = response.json() if raw else {}
                    record = self._extract_api_record(data, runtime)
                    patches.extend(self._apply_record_to_entity(entity, record, [missing], runtime))
        except Exception as exc:
            return self._failed(step_id, source, f"live API query failed: {exc}", started)

        return self._execution_response(step_id, source, patches, "live API query completed", started, runtime)

    def _iter_missing_entities(self, graph: InstanceGraph, missing_fields: Sequence[Dict[str, Any]]):
        for missing in missing_fields:
            entity_id = missing.get("entity_id")
            entity_type = missing.get("entity_type")
            for entity in graph.entities:
                if entity_id and entity.id != entity_id:
                    continue
                if entity_type and entity.entity_type != entity_type:
                    continue
                yield entity, missing

    def _apply_record_to_entity(
        self,
        entity,
        record: Dict[str, Any],
        missing_fields: Sequence[Dict[str, Any]],
        runtime: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        if not isinstance(record, dict):
            return []
        field_map = runtime.get("field_map") if isinstance(runtime.get("field_map"), dict) else {}
        sensitive_fields = {str(item) for item in (runtime.get("sensitive_fields") or runtime.get("redact_fields") or [])}
        allow_sensitive_runtime_values = bool(runtime.get("allow_sensitive_runtime_values"))
        patches: List[Dict[str, Any]] = []
        for missing in missing_fields:
            field_name = str(missing.get("field") or "")
            if not field_name:
                continue
            current = (entity.attributes or {}).get(field_name)
            if current not in (None, "", []):
                continue
            source_field = str(field_map.get(field_name) or field_name)
            if source_field not in record:
                continue
            raw_value = record.get(source_field)
            is_sensitive = field_name in sensitive_fields or source_field in sensitive_fields
            stored_value = raw_value if not is_sensitive or allow_sensitive_runtime_values else self._mask_value(raw_value)
            entity.attributes[field_name] = stored_value
            patches.append(
                {
                    "entity_id": entity.id,
                    "entity_type": entity.entity_type,
                    "field": field_name,
                    "value": self._mask_value(raw_value) if is_sensitive else raw_value,
                    "redacted": is_sensitive,
                }
            )
        return patches

    @staticmethod
    def _build_query_params(attributes: Dict[str, Any], runtime: Dict[str, Any]) -> List[Any]:
        param_fields = runtime.get("parameter_fields")
        if not isinstance(param_fields, list) or not param_fields:
            param_fields = [runtime.get("key_field") or "id"]
        return [attributes.get(str(field)) for field in param_fields]

    @staticmethod
    def _build_http_params(attributes: Dict[str, Any], runtime: Dict[str, Any]) -> Dict[str, Any]:
        param_map = runtime.get("query_params") if isinstance(runtime.get("query_params"), dict) else {}
        if not param_map:
            key_field = str(runtime.get("key_field") or "id")
            return {key_field: attributes.get(key_field)}
        return {str(target): attributes.get(str(source)) for target, source in param_map.items()}

    @staticmethod
    def _render_template(template: str, attributes: Dict[str, Any]) -> str:
        def replace(match: re.Match[str]) -> str:
            key = match.group(1).strip()
            value = attributes.get(key)
            return "" if value is None else str(value)

        return re.sub(r"\{\{\s*([A-Za-z0-9_.-]+)\s*\}\}", replace, template or "")

    @staticmethod
    def _extract_api_record(data: Any, runtime: Dict[str, Any]) -> Dict[str, Any]:
        path = str(runtime.get("response_path") or "").strip()
        current = data
        if path:
            for part in path.split("."):
                if isinstance(current, dict):
                    current = current.get(part)
                elif isinstance(current, list) and part.isdigit():
                    current = current[int(part)]
                else:
                    return {}
        if isinstance(current, list):
            current = current[0] if current else {}
        return current if isinstance(current, dict) else {}

    def _assert_safe_url(self, url: str, allowed_hosts: Sequence[str]) -> None:
        parsed = urlparse(url)
        if parsed.scheme not in {"https", "http"}:
            raise ValueError("only http/https URLs are allowed")
        host = (parsed.hostname or "").lower()
        if not host:
            raise ValueError("URL host is required")
        normalized_allowed = {item.lower() for item in allowed_hosts}
        if host not in normalized_allowed:
            raise ValueError("URL host is not in allowed_hosts")
        for info in socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM):
            address = info[4][0]
            ip = ipaddress.ip_address(address)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved:
                raise ValueError("URL resolves to a blocked private or reserved address")

    @staticmethod
    def _validate_readonly_sql(sql: str) -> Optional[str]:
        if not sql:
            return "live DB runtime requires runtime.sql"
        normalized = re.sub(r"/\*.*?\*/", " ", sql, flags=re.S)
        normalized = re.sub(r"--.*?$", " ", normalized, flags=re.M).strip()
        if ";" in normalized.rstrip(";"):
            return "only one SQL statement is allowed"
        lowered = normalized.lower().rstrip(";").strip()
        if not (lowered.startswith("select ") or lowered.startswith("with ")):
            return "only SELECT/WITH read-only SQL is allowed"
        forbidden = r"\b(insert|update|delete|drop|alter|truncate|create|grant|revoke|copy|call|execute|merge|vacuum|analyze|lock)\b"
        if re.search(forbidden, lowered):
            return "SQL contains forbidden write/admin keyword"
        return None

    @staticmethod
    def _bounded_timeout(value: Any) -> float:
        try:
            raw = float(value)
        except (TypeError, ValueError):
            raw = settings.ONTOLOGY_LIVE_EXECUTION_TIMEOUT_SECONDS
        return min(max(raw, 0.5), settings.ONTOLOGY_LIVE_EXECUTION_TIMEOUT_SECONDS)

    @staticmethod
    def _bounded_max_rows(value: Any) -> int:
        try:
            raw = int(value)
        except (TypeError, ValueError):
            raw = settings.ONTOLOGY_LIVE_EXECUTION_MAX_ROWS
        return min(max(raw, 1), settings.ONTOLOGY_LIVE_EXECUTION_MAX_ROWS)

    @staticmethod
    def _mask_value(value: Any) -> str:
        text = str(value)
        if len(text) <= 4:
            return "****"
        return f"{text[:2]}****{text[-2:]}"

    def _execution_response(
        self,
        step_id: str,
        source: OntologyDataSourceRecord,
        patches: List[Dict[str, Any]],
        reason: str,
        started: float,
        runtime: Dict[str, Any],
    ) -> Dict[str, Any]:
        return {
            "step_id": step_id,
            "data_source_id": source.id,
            "data_source_name": source.name,
            "status": "applied" if patches else "skipped",
            "reason": reason if patches else "live source returned no applicable fields",
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            "applied_patch_count": len(patches),
            "patches": patches[:50],
            "redaction": {
                "enabled": True,
                "sensitive_fields": [str(item) for item in (runtime.get("sensitive_fields") or runtime.get("redact_fields") or [])],
            },
        }

    def _failed(self, step_id: str, source: OntologyDataSourceRecord, reason: str, started: float) -> Dict[str, Any]:
        return {
            "step_id": step_id,
            "data_source_id": source.id,
            "data_source_name": source.name,
            "status": "failed",
            "reason": reason,
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            "applied_patch_count": 0,
        }

    @staticmethod
    def _skipped(step_id: str, source: OntologyDataSourceRecord, reason: str) -> Dict[str, Any]:
        return {
            "step_id": step_id,
            "data_source_id": source.id,
            "data_source_name": source.name,
            "status": "skipped",
            "reason": reason,
            "applied_patch_count": 0,
        }

    @staticmethod
    def _audit_payload(source: OntologyDataSourceRecord, execution: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "data_source_id": source.id,
            "data_source_name": source.name,
            "kind": source.kind.value if hasattr(source.kind, "value") else str(source.kind),
            "protocol": source.protocol,
            "status": execution.get("status"),
            "reason": execution.get("reason"),
            "applied_patch_count": execution.get("applied_patch_count", 0),
            "duration_ms": execution.get("duration_ms"),
        }

    def _execute_fixture_source(
        self,
        graph: Optional[InstanceGraph],
        source: OntologyDataSourceRecord,
        missing_fields: Sequence[Dict[str, Any]],
        step_id: str,
    ) -> Dict[str, Any]:
        config = source.config or {}
        runtime = config.get("runtime") if isinstance(config.get("runtime"), dict) else {}
        mode = str(runtime.get("mode") or "disabled").lower()
        if mode != "fixture":
            return {
                "step_id": step_id,
                "data_source_id": source.id,
                "data_source_name": source.name,
                "status": "skipped",
                "reason": "data source runtime.mode is not fixture; live execution is disabled by default",
                "applied_patch_count": 0,
            }

        records = runtime.get("records") or config.get("sample_records") or []
        if not isinstance(records, list):
            records = []
        key_field = str(runtime.get("key_field") or "id")
        entity_type_filter = runtime.get("entity_type")
        patches: List[Dict[str, Any]] = []

        if not graph:
            return {
                "step_id": step_id,
                "data_source_id": source.id,
                "data_source_name": source.name,
                "status": "skipped",
                "reason": "graph is empty",
                "applied_patch_count": 0,
            }

        for missing in missing_fields:
            entity_id = missing.get("entity_id")
            entity_type = missing.get("entity_type")
            field_name = missing.get("field")
            if not field_name:
                continue
            for entity in graph.entities:
                if entity_id and entity.id != entity_id:
                    continue
                if entity_type and entity.entity_type != entity_type:
                    continue
                if entity_type_filter and entity.entity_type != entity_type_filter:
                    continue
                current = (entity.attributes or {}).get(field_name)
                if current not in (None, "", []):
                    continue
                record = self._match_record(entity, records, key_field)
                if not record or field_name not in record:
                    continue
                value = record.get(field_name)
                entity.attributes[field_name] = value
                patches.append({
                    "entity_id": entity.id,
                    "entity_type": entity.entity_type,
                    "field": field_name,
                    "value": value,
                    "source_record_key": record.get(key_field),
                })

        return {
            "step_id": step_id,
            "data_source_id": source.id,
            "data_source_name": source.name,
            "status": "applied" if patches else "skipped",
            "reason": "fixture records applied to missing fields" if patches else "fixture records did not match missing fields",
            "applied_patch_count": len(patches),
            "patches": patches[:50],
        }

    @staticmethod
    def _match_record(entity, records: Sequence[Dict[str, Any]], key_field: str) -> Optional[Dict[str, Any]]:
        attrs = entity.attributes or {}
        candidates = [attrs.get(key_field), attrs.get("id"), entity.id.split(":")[-1]]
        normalized = {str(item) for item in candidates if item not in (None, "")}
        for record in records:
            if not isinstance(record, dict):
                continue
            record_key = record.get(key_field)
            if record_key is not None and str(record_key) in normalized:
                return record
        if len(records) == 1:
            return records[0] if isinstance(records[0], dict) else None
        return None


ontology_action_executor = OntologyActionExecutor()
