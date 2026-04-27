import asyncio

from app.core.config import settings
from app.services.ext_tools import CliTool


def test_cli_tool_disabled_by_default():
    tool = CliTool(name="cli_demo", label="demo", description="demo", script="echo hello")
    original = settings.ENABLE_DYNAMIC_CLI_TOOLS
    try:
        settings.ENABLE_DYNAMIC_CLI_TOOLS = False

        async def _run():
            out = await tool.execute()
            assert "disabled" in out

        asyncio.run(_run())
    finally:
        settings.ENABLE_DYNAMIC_CLI_TOOLS = original


def test_cli_tool_requires_allowlist():
    tool = CliTool(name="cli_demo", label="demo", description="demo", script="echo hello")
    original_enable = settings.ENABLE_DYNAMIC_CLI_TOOLS
    original_allowlist = settings.DYNAMIC_CLI_ALLOWED_COMMANDS
    try:
        settings.ENABLE_DYNAMIC_CLI_TOOLS = True
        settings.DYNAMIC_CLI_ALLOWED_COMMANDS = ""

        async def _run():
            out = await tool.execute()
            assert "allowlist is empty" in out

        asyncio.run(_run())
    finally:
        settings.ENABLE_DYNAMIC_CLI_TOOLS = original_enable
        settings.DYNAMIC_CLI_ALLOWED_COMMANDS = original_allowlist


def test_cli_tool_blocks_command_not_in_allowlist():
    tool = CliTool(name="cli_demo", label="demo", description="demo", script="echo hello")
    original_enable = settings.ENABLE_DYNAMIC_CLI_TOOLS
    original_allowlist = settings.DYNAMIC_CLI_ALLOWED_COMMANDS
    try:
        settings.ENABLE_DYNAMIC_CLI_TOOLS = True
        settings.DYNAMIC_CLI_ALLOWED_COMMANDS = "python3,jq"

        async def _run():
            out = await tool.execute()
            assert "not in allowlist" in out

        asyncio.run(_run())
    finally:
        settings.ENABLE_DYNAMIC_CLI_TOOLS = original_enable
        settings.DYNAMIC_CLI_ALLOWED_COMMANDS = original_allowlist
