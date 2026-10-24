"""Work with both MCP Python SDK lines.

* mcp 2.x  -> ``mcp.server.mcpserver.MCPServer``
* mcp 1.x  -> ``mcp.server.fastmcp.FastMCP``

The two expose the same decorator API for tools, prompts and resources; they
differ in how host/port are passed when running over HTTP.
"""

from __future__ import annotations

from typing import Any

try:  # mcp >= 2.0
    from mcp.server.mcpserver import Context, MCPServer as _Server  # type: ignore  # noqa: F401

    SDK_MAJOR = 2
except ImportError:  # mcp 1.x
    from mcp.server.fastmcp import Context, FastMCP as _Server  # type: ignore  # noqa: F401

    SDK_MAJOR = 1

from mcp.types import ToolAnnotations


def make_server(name: str, version: str, instructions: str, website_url: str):
    kwargs: dict[str, Any] = {"instructions": instructions}
    if SDK_MAJOR >= 2:
        kwargs["version"] = version
    try:
        server = _Server(name, website_url=website_url, **kwargs)
    except TypeError:  # very old 1.x without website_url
        server = _Server(name, **kwargs)
    if SDK_MAJOR < 2:
        # FastMCP 1.x reports the SDK version by default; report ours instead.
        low = getattr(server, "_mcp_server", None)
        if low is not None and hasattr(low, "version"):
            low.version = version
    return server


def annotations(*, title: str, read_only: bool, destructive: bool = False, idempotent: bool = True, open_world: bool = True) -> ToolAnnotations:
    # camelCase works on both SDK lines (v2 accepts the aliases).
    return ToolAnnotations(
        title=title,
        readOnlyHint=read_only,
        destructiveHint=destructive,
        idempotentHint=idempotent,
        openWorldHint=open_world,
    )


def run(server, transport: str, host: str, port: int, path: str = "/mcp") -> None:
    if transport == "stdio":
        server.run(transport="stdio")
        return

    security = None
    if host not in ("127.0.0.1", "localhost", "::1"):
        # Remote/Docker binding was opted into explicitly via MCP_HOST, so the
        # localhost-only Host allowlist would reject every request (HTTP 421).
        try:
            from mcp.server.transport_security import TransportSecuritySettings

            security = TransportSecuritySettings(enable_dns_rebinding_protection=False)
        except Exception:
            security = None

    if SDK_MAJOR >= 2:
        kwargs: dict[str, Any] = {"host": host, "port": port}
        if transport == "streamable-http":
            kwargs["streamable_http_path"] = path
        if security is not None:
            kwargs["transport_security"] = security
        server.run(transport=transport, **kwargs)
    else:
        server.settings.host = host
        server.settings.port = port
        if transport == "streamable-http":
            server.settings.streamable_http_path = path
        if security is not None:
            try:
                server.settings.transport_security = security
            except Exception:
                pass
        server.run(transport=transport)


async def try_elicit(ctx: Any, message: str, schema: type) -> tuple[str, Any]:
    """Ask the user through the client. Returns (action, data).

    action is 'accept', 'decline', 'cancel' or 'unsupported'.
    """
    if ctx is None:
        return "unsupported", None
    try:
        caps = ctx.session.client_params.capabilities  # type: ignore[attr-defined]
        if getattr(caps, "elicitation", None) is None:
            return "unsupported", None
    except Exception:
        pass  # can't tell; just try
    try:
        result = await ctx.elicit(message, schema)
    except Exception:
        return "unsupported", None
    action = getattr(result, "action", "cancel")
    return str(action), getattr(result, "data", None)
