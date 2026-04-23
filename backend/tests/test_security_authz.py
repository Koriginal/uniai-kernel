import ast
import asyncio
from pathlib import Path

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.api import deps
from app.core.auth import get_current_user_id
from app.core.config import settings


def _dummy_receive():
    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    return receive


def _make_request(path: str = "/api/v1/chat/completions", headers: list[tuple[bytes, bytes]] | None = None) -> Request:
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": headers or [],
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
        "state": {},
    }
    return Request(scope, _dummy_receive())


class _DummyDB:
    async def execute(self, *_args, **_kwargs):
        raise AssertionError("execute should not be called for unauthenticated request without X-API-Key")

    async def get(self, *_args, **_kwargs):
        raise AssertionError("get should not be called for unauthenticated request without Authorization")

    async def commit(self):
        raise AssertionError("commit should not be called for unauthenticated request")


def test_identity_requires_auth_when_fallback_disabled(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "ALLOW_ANONYMOUS_ADMIN_FALLBACK", False, raising=False)
    request = _make_request()
    db = _DummyDB()

    async def _run():
        with pytest.raises(HTTPException) as exc:
            await deps.get_identity(request=request, db=db)
        assert exc.value.status_code == 401

    asyncio.run(_run())


def test_legacy_get_current_user_id_requires_header():
    async def _run():
        with pytest.raises(HTTPException) as exc:
            await get_current_user_id(x_user_id=None)
        assert exc.value.status_code == 401

    asyncio.run(_run())


def test_unprotected_endpoints_allowlist():
    """
    防回归：除登录端点外，不应存在匿名暴露的管理 API。
    """
    root = Path(__file__).resolve().parents[1] / "app" / "api" / "endpoints"
    http_decorators = {"get", "post", "put", "patch", "delete"}
    secure_markers = {"get_current_active_user", "get_current_admin", "get_identity"}
    allowlist = {("auth.py", "login")}
    unprotected = []

    for file in sorted(root.glob("*.py")):
        src = file.read_text()
        tree = ast.parse(src, filename=str(file))
        router_has_global_dep = False

        for node in tree.body:
            if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "router" for t in node.targets):
                if isinstance(node.value, ast.Call) and getattr(node.value.func, "id", "") == "APIRouter":
                    for kw in node.value.keywords:
                        if kw.arg == "dependencies":
                            txt = ast.get_source_segment(src, kw.value) or ""
                            if any(m in txt for m in secure_markers):
                                router_has_global_dep = True

        for node in tree.body:
            if not isinstance(node, ast.AsyncFunctionDef):
                continue
            is_route = False
            for dec in node.decorator_list:
                if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute) and dec.func.attr in http_decorators:
                    is_route = True
                    break
            if not is_route:
                continue

            has_secure_dep = False
            defaults = list(node.args.defaults) + [d for d in node.args.kw_defaults if d is not None]
            for default in defaults:
                txt = ast.get_source_segment(src, default) or ""
                if any(m in txt for m in secure_markers):
                    has_secure_dep = True
                    break

            if not router_has_global_dep and not has_secure_dep:
                key = (file.name, node.name)
                if key not in allowlist:
                    unprotected.append(f"{file.name}:{node.name}")

    assert not unprotected, f"Found unprotected endpoints: {unprotected}"
