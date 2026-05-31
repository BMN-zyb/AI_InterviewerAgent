"""
MCP Client 实现：通过 Model Context Protocol 标准协议接入外部工具
支持连接本地 stdio 服务或 HTTP 服务。
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Dict, List

from loguru import logger

try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
except ImportError:
    ClientSession = None  # type: ignore
    StdioServerParameters = None  # type: ignore
    stdio_client = None  # type: ignore


class MCPClient:
    """MCP 客户端封装"""

    def __init__(self) -> None:
        self.session: ClientSession | None = None  # type: ignore
        self._ctx = None

    @asynccontextmanager
    async def connect_stdio(
        self, command: str, args: List[str], env: Dict[str, str] | None = None
    ) -> AsyncGenerator[ClientSession, None]:  # type: ignore
        """连接本地 stdio MCP 服务"""
        if StdioServerParameters is None:
            raise RuntimeError("mcp SDK 未安装")
        params = StdioServerParameters(command=command, args=args, env=env)
        async with stdio_client(params) as (read, write):  # type: ignore
            async with ClientSession(read, write) as session:  # type: ignore
                await session.initialize()
                logger.info("MCP stdio 会话已建立")
                yield session

    async def list_tools(self, session: ClientSession) -> List[Dict[str, Any]]:  # type: ignore
        """列出可用工具"""
        result = await session.list_tools()  # type: ignore
        return [{"name": t.name, "description": t.description} for t in result.tools]

    async def call_tool(
        self, session: ClientSession, tool_name: str, arguments: Dict[str, Any]  # type: ignore
    ) -> Any:
        """调用工具"""
        result = await session.call_tool(tool_name, arguments)  # type: ignore
        return result.content


# 全局便捷函数
def run_async(coro):
    """同步包装器：在已有 event loop 下创建新 loop 运行"""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(1) as pool:
            return pool.submit(asyncio.run, coro).result()
    return asyncio.run(coro)
