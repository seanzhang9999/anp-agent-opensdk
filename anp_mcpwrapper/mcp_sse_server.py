"""MCP Server for DID WBA Example using SSE transport.

This module implements a Model Context Protocol (MCP) server that exposes
the DID WBA client and server functionalities as MCP tools using Server-Sent Events (SSE).
"""
import os
import asyncio
import logging
import json
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from loguru import logger
from mcp.server.fastmcp import FastMCP, Context

# Import DID WBA server and client functions
from anp_core.server.server import (
    ANP_resp_start,
    ANP_resp_stop,
    server_status,
    # server_running,  # 不再直接使用全局变量
)

from anp_core.client.client import (
    ANP_connector_start,
    ANP_connector_stop,
    connector_running,
    client_chat_messages,
    client_new_message_event
)

from mcp.server.fastmcp import FastMCP
from mcp.server.sse import SseServerTransport
from mcp.server import Server
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.routing import Mount, Route
from starlette.responses import PlainTextResponse
import uvicorn

# Import server-side message handling
from api.anp_nlp_router import resp_handle_request_msgs, resp_handle_request_new_msg_event as server_new_message_event

# Store connection events for notification
connection_events = []
new_connection_event = asyncio.Event()
user_dir = os.path.dirname(os.path.abspath(__file__))
user_dir = os.path.join(user_dir, "logs")
# 设置日志
logger.add(f"{user_dir}/sse_server.log", rotation="1000 MB", retention="7 days", encoding="utf-8")

@dataclass
class AppContext:
    """Application context for MCP server."""
    server_status: Dict[str, Any] = None
    client_status: Dict[str, Any] = None
    connection_events: List[Dict[str, Any]] = None


@asynccontextmanager
async def app_lifespan(server: FastMCP) -> AsyncIterator[AppContext]:
    """Manage application lifecycle with type-safe context."""
    # Initialize on startup
    app_context = AppContext(
        server_status={"running": False, "port": None},
        client_status={"running": False, "port": None},
        connection_events=[]
    )

    # Start connection event listener
    asyncio.create_task(connection_event_listener(app_context))

    try:
        yield app_context
    finally:
        # Cleanup on shutdown
        if app_context.server_status.get("running"):
            ANP_resp_stop()
        if app_context.client_status.get("running"):
            ANP_connector_stop()


# Pass lifespan to server
mcp = FastMCP("DID WBA MCP Server", lifespan=app_lifespan, port=8080)


async def connection_event_listener(app_context: AppContext):
    """Listen for connection events from both DID WBA client and server."""
    global client_chat_messages, client_new_message_event, connection_events, new_connection_event
    global resp_handle_request_msgs, server_new_message_event

    # 创建两个任务，分别监听客户端和服务器端的消息
    while True:
        try:
            # 创建两个等待事件的任务
            client_task = asyncio.create_task(client_new_message_event.wait())
            server_task = asyncio.create_task(server_new_message_event.wait())

            # 等待任意一个任务完成
            done, pending = await asyncio.wait(
                [client_task, server_task],
                return_when=asyncio.FIRST_COMPLETED
            )

            # 取消未完成的任务
            for task in pending:
                task.cancel()

            # 处理客户端消息
            if client_task in done and client_new_message_event.is_set():
                if client_chat_messages:
                    # 获取最新消息
                    latest_message = client_chat_messages[-1]
                    latest_message['source'] = 'client'  # 添加来源标记

                    # 添加到连接事件
                    connection_events.append(latest_message)
                    if len(connection_events) > 50:
                        connection_events = connection_events[-50:]

                    # 更新应用上下文
                    app_context.connection_events = connection_events

                    # 设置事件通知订阅者
                    new_connection_event.set()

                    # 重置客户端事件
                    client_new_message_event.clear()
                    
                    logger.info(f"客户端消息事件: {latest_message}")

            # 处理服务器端消息
            if server_task in done and server_new_message_event.is_set():
                if resp_handle_request_msgs:
                    # 获取最新消息
                    latest_message = resp_handle_request_msgs[-1]
                    latest_message['source'] = 'server'  # 添加来源标记

                    # 添加到连接事件
                    connection_events.append(latest_message)
                    if len(connection_events) > 50:
                        connection_events = connection_events[-50:]

                    # 更新应用上下文
                    app_context.connection_events = connection_events

                    # 设置事件通知订阅者
                    new_connection_event.set()

                    # 重置服务器端事件
                    server_new_message_event.clear()
                    
                    logger.info(f"服务器消息事件: {latest_message}")

            # 小延迟防止CPU过载
            await asyncio.sleep(0.1)
        except Exception as e:
            logger.error(f"连接事件监听器错误: {e}")
            await asyncio.sleep(1)  # 出错时暂停一下


@mcp.tool()
async def start_did_server(ctx: Context, port: Optional[int] = None) -> Dict[str, Any]:
    """Start the DID WBA server.
    
    Args:
        port: Optional server port number (default: from settings)
        
    Returns:
        Dict with server status information
    """
    global server_status
    app_context = ctx.request_context.lifespan_context

    if server_status.is_running():
        return {"status": "already_running", "message": "服务器已经在运行中"}

    try:
        logger.info(f"Starting DID WBA server on port {port if port else 'default'}")
        
        # 直接调用start_server，它内部已经实现了子线程启动
        ANP_resp_start(port=port)

        max_retries = 10  # 增加重试次数
        for _ in range(max_retries):
            if server_status.is_running():
                break
            await asyncio.sleep(1)  # 增加等待间隔
        else:
            raise RuntimeError("Server did not start in time. Wait server_running event to check status.")

        app_context.server_status = {"running": True, "port": port or server_status.port}
        return {
            "status": "success",
            "message": f"服务器已在端口 {port if port else '默认端口'} 启动",
            "is_running": True
        }
    except Exception as e:
        logger.error(f"Server start failed: {e}")
        return {
            "status": "error",
            "message": str(e),
            "is_running": False
        }


@mcp.tool()
async def stop_did_server(ctx: Context) -> Dict[str, Any]:
    """Stop the DID WBA server.
    
    Returns:
        Dict with server status information
    """
    app_context = ctx.request_context.lifespan_context

    # Check if server is running
    if not server_status.is_running():
        return {"status": "not_running", "message": "服务器未运行"}

    # Stop the server
    ANP_resp_stop()

    # Update app context
    app_context.server_status = {"running": False, "port": None}

    return {
        "status": "success",
        "message": "服务器已关闭",
        "is_running": False
    }


@mcp.tool()
async def start_did_client(ctx: Context, port: Optional[int] = None, unique_id: Optional[str] = None,
                           message: Optional[str] = None) -> Dict[str, Any]:
    """Start the DID WBA client.
    
    Args:
        port: Optional target server port number
        unique_id: Optional unique identifier for the client
        message: Optional custom message to send
        
    Returns:
        Dict with client status information
    """
    global connector_running, client_chat_messages, client_new_message_event

    app_context = ctx.request_context.lifespan_context

    # Check if client is already running
    if connector_running:
        return {"status": "already_running", "message": "客户端已经在运行中"}
    
    # 在启动客户端前先清除事件和消息列表
    client_new_message_event.clear()
    
    # Start the client - 在单独的线程中运行run_client
    from anp_core.client.client import run_connector
    import threading
    client_thread = threading.Thread(target=run_connector, args=(unique_id, message))
    client_thread.daemon = True
    client_thread.start()

    # Update app context
    app_context.client_status = {"running": True, "port": port, "unique_id": unique_id}
    
    # 不再等待消息，立即返回
    logger.info(f"客户端已启动，目标端口: {port if port else '默认端口'}")
    logger.info("客户端消息将通过connection_event_listener处理并可通过get_connection_events获取")
    
    return {
        "status": "success",
        "message": f"客户端已启动，目标端口: {port if port else '默认端口'}",
        "is_running": True,
        "info": "客户端消息将通过connection_event_listener处理并可通过get_connection_events获取"
    }


@mcp.tool()
async def stop_did_client(ctx: Context) -> Dict[str, Any]:
    """Stop the DID WBA client.
    
    Returns:
        Dict with client status information
    """
    app_context = ctx.request_context.lifespan_context

    # Check if client is running
    if not connector_running:
        return {"status": "not_running", "message": "客户端未运行"}

    # Stop the client
    ANP_connector_stop()

    # Update app context
    app_context.client_status = {"running": False, "port": None, "unique_id": None}

    return {
        "status": "success",
        "message": "客户端已关闭",
        "is_running": False
    }


@mcp.tool()
async def get_connection_events(ctx: Context, wait_for_new: bool = False, timeout: int = 300) -> Dict[str, Any]:
    """Get connection events from the DID WBA server.
    
    Args:
        wait_for_new: Whether to wait for new events
        timeout: Timeout in seconds for waiting for new events

    Returns:
        Dict with connection events
    """
    global connection_events, new_connection_event

    try:
        if wait_for_new:
            # Wait for new connection event with timeout
            try:
                await asyncio.wait_for(new_connection_event.wait(), timeout=timeout)
                # Reset event for next notification
                new_connection_event.clear()
            except asyncio.TimeoutError:
                logger.warning("等待新连接事件超时")
                return {
                    "status": "timeout",
                    "message": "等待新连接事件超时",
                    "events": connection_events,
                    "error": None
                }

        return {
            "status": "success",
            "message": "获取连接事件成功",
            "events_number": len(connection_events),
            "events": connection_events,
            "error": None
        }
    except Exception as e:
        logger.error(f"获取连接事件时发生错误: {str(e)}", exc_info=True)
        return {
            "status": "error",
            "message": f"获取连接事件失败: {str(e)}",
            "events_number": 0,
            "events": [],
            "error": str(e)
        }


@mcp.tool()
async def clear_connection_events(ctx: Context) -> Dict[str, Any]:
    """清除所有连接事件"""
    global connection_events
    
    # 清除事件
    event_count = len(connection_events)
    connection_events.clear()
    
    return {
        "status": "success", 
        "message": f"已清除 {event_count} 个事件",
        "event_count": 0
    }


@mcp.resource("status://did-wba")
async def get_status() -> str:
    """获取DID WBA服务器和客户端状态"""
    global connection_events, server_status, connector_running
    
    # 创建状态信息
    status_info = {
        "server": {
            "running": server_status.is_running(),
            "status": {"running": server_status.is_running(), "port": server_status.port}
        },
        "client": {
            "running": connector_running,
            "status": {"running": connector_running}
        },
        "connection_events_count": len(connection_events)
    }
    
    # 返回JSON字符串
    return json.dumps(status_info)


def create_starlette_app(mcp_server: Server, *, debug: bool = False) -> Starlette:
    """创建支持SSE的Starlette应用"""
    sse = SseServerTransport("/messages/")

    async def handle_sse(request: Request) -> None:
        async with sse.connect_sse(
                request.scope,
                request.receive,
                request._send,
        ) as (read_stream, write_stream):
            await mcp_server.run(
                read_stream,
                write_stream,
                mcp_server.create_initialization_options(),
            )

    return Starlette(
        debug=debug,
        routes=[
            Route("/", endpoint=lambda request: PlainTextResponse("DID WBA MCP SSE Server")),
            Route("/sse", endpoint=handle_sse),
            Mount("/messages/", app=sse.handle_post_message),
        ],
    )


def main():
    """Run the MCP SSE server."""
    # 获取底层MCP服务器
    mcp_server = mcp._mcp_server

    # 创建支持SSE的Starlette应用
    starlette_app = create_starlette_app(mcp_server, debug=True)

    port = 8080
    logger.info(f"Starting MCP SSE server on port {port}...")
    logger.info(f"SSE endpoint available at: http://localhost:{port}/sse")
    # 使用uvicorn运行MCP SSE服务器
    uvicorn.run(starlette_app, host="0.0.0.0", port=8080)


if __name__ == "__main__":
    main()