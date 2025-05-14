"""MCP Server for DID WBA Example.

This module implements a Model Context Protocol (MCP) server that exposes
the DID WBA client and server functionalities as MCP tools.
"""
import os
import sys
import asyncio
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from mcp.server.sse import SseServerTransport
from mcp.server import Server
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.routing import Mount, Route
import uvicorn

# 添加项目根目录到 Python 路径
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)  # 获取上级目录
if project_root not in sys.path:
    sys.path.insert(0, project_root)
    # 这里不能直接使用printmute，因为函数还未定义
    # 我们将在run_mcp_server函数中处理这个打印
    _print_path_added = True
else:
    _print_path_added = False

from loguru import logger
# 导入 FastMCP
from mcp.server.fastmcp import FastMCP, Context

# Import DID WBA server and client functions
from anp_core.server.server import ANP_resp_start, ANP_resp_stop, server_status
from anp_core.client.client import ANP_connector_start, ANP_connector_stop, connector_running, client_chat_messages, client_new_message_event, ANP_req_auth, ANP_req_chat

# Import settings for server configuration
from core.config import settings
# Import server-side message handling
from api.anp_nlp_router import resp_handle_request_msgs, resp_handle_request_new_msg_event as server_new_message_event

# Store connection events for notification
connection_events = []
new_connection_event = asyncio.Event()

user_dir = os.path.dirname(os.path.abspath(__file__))
user_dir = os.path.join(user_dir, "logs")
# 设置日志
logger.add(f"{user_dir}/stdio_server.log", rotation="1000 MB", retention="7 days", encoding="utf-8")

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
mcp = FastMCP("DID WBA MCP Server", lifespan=app_lifespan)

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
            
            # 小延迟防止CPU过载
            await asyncio.sleep(0.1)
        except Exception as e:
            logging.error(f"Error in connection event listener: {e}")
            await asyncio.sleep(1)  # 出错后等待一段时间再重试

@mcp.tool()
def start_did_server(ctx: Context, port: Optional[int] = None) -> Dict[str, Any]:
    """Start the DID WBA server.
    
    Args:
        port: Optional server port number (default: from settings)
        
    Returns:
        Dict with server status information
    """
    global server_status
    app_context = ctx.request_context.lifespan_context
    
    # Check if server is already running
    if server_status.is_running():
        return {"status": "already_running", "message": "服务器已经在运行中"}

    try:
        logger.info(f"Starting DID WBA server on port {port if port else 'default'}")
        if not ANP_resp_start(port=port):  # 检查启动返回值
            raise RuntimeError("服务器启动失败")

        # 服务器已经启动，不需要等待状态更新
        # server_status对象会在start_server函数中自动更新状态

        app_context.server_status = {"running": True, "port": port}
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
    global connector_running

    app_context = ctx.request_context.lifespan_context
    
    # Check if client is already running
    if connector_running:
        return {"status": "already_running", "message": "客户端已经在运行中"}
    
    # Start the client
    ANP_connector_start(port=port, unique_id=unique_id,message=message)
    
    # Update app context
    app_context.client_status = {"running": True, "port": port, "unique_id": unique_id}
    
    return {
        "status": "success",
        "message": f"客户端已启动，目标端口: {port if port else '默认端口'}",
        "is_running": True
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
                logging.warning("等待新连接事件超时")
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
        logging.error(f"获取连接事件时发生错误: {str(e)}", exc_info=True)
        return {
            "status": "error",
            "message": f"获取连接事件失败: {str(e)}",
            "events_number": 0,
            "events": [],
            "error": str(e)
        }


@mcp.tool()
async def clear_connection_events(ctx: Context) -> Dict[str, Any]:
    """清除DID WBA服务器的连接事件列表。
    
    Returns:
        Dict with operation status information
    """
    global connection_events

    try:
        # 清空连接事件列表
        connection_events.clear()
        
        # 更新应用上下文
        app_context = ctx.request_context.lifespan_context
        app_context.connection_events = connection_events
        
        return {
            "status": "success",
            "message": "连接事件已清除",
            "events_number": 0,
            "error": None
        }
    except Exception as e:
        logger.error(f"清除连接事件时发生错误: {str(e)}", exc_info=True)
        return {
            "status": "error",
            "message": f"清除连接事件失败: {str(e)}",
            "events_number": len(connection_events),
            "error": str(e)
        }


@mcp.resource("status://did-wba")
async def get_status() -> Dict[str, Any]:
    """Get the current status of the DID WBA server and client.
    
    Returns:
        Dict with status information
    """
    global server_status, connector_running, connection_events
    return {
        "server": {
            "running": server_status.is_running(),
            "status": {"running": server_status.is_running()}
        },
        "client": {
            "running": connector_running,
            "status": {"running": connector_running}
        },
        "connection_events_count": len(connection_events)
    }


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
            Route("/sse", endpoint=handle_sse),
            Mount("/messages/", app=sse.handle_post_message),
        ],
    )


# 添加printmute函数在文件开头部分
def printmute(message, enable_print = False):
    """打印函数，当enable_print为False时不打印任何内容。
    
    Args:
        message: 要打印的消息
        enable_print: 是否启用打印，默认为True
    """
    if enable_print:
        print(message)

def run_mcp_server():
    """Run the MCP server."""
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='启动 MCP 服务器')
    parser.add_argument('--transport', '-t', type=str, choices=['stdio', 'sse'], default='stdio',
                        help='选择传输模式: stdio (默认) 或 sse')
    parser.add_argument('--print', action='store_true', default=False,
                        help='启用打印输出，默认为False')
    args = parser.parse_args()
    # 从args对象中正确获取参数值
    transport = args.transport
    enable_print = args.print
    
    # 处理之前添加项目根目录到Python路径时的打印
    global _print_path_added
    if _print_path_added:
        printmute(f"已添加项目根目录到 Python 路径: {project_root}", enable_print)
        _print_path_added = False
    
    # Install the MCP server for development
    import sys
    
    # 检查是否需要启用调试
    enable_debug = os.environ.get("ENABLE_DEBUGPY", "False").lower() == "true"
    
    if enable_debug:
        try:
            import debugpy
            # 允许其他客户端连接到调试器
            debugpy.listen(("0.0.0.0", 5678))
            printmute("调试器已启动，监听端口5678。您可以在VSCode中使用'Attach to Running MCP Server'配置连接到此进程。", enable_print)
            # 如果需要等待调试器连接，取消下面这行的注释
            # debugpy.wait_for_client()
        except ImportError:
            printmute("警告: 无法导入debugpy模块，调试功能将被禁用", enable_print)
            printmute("如需启用调试，请运行: pip install debugpy", enable_print)
    
    try:
        # 尝试直接启动MCP服务器，而不是使用MCP CLI
        # printmute(f"正在直接启动MCP服务器 (传输模式: {transport})...", enable_print)
    
        # 使用FastMCP的run方法启动服务器
        if args.transport == 'stdio':
            # printmute("使用 stdio 传输模式启动服务器", enable_print)
            mcp.run(transport='stdio')
        else:
            # 设置HTTP服务器端口 - 仅在sse模式下需要
            # 获取底层MCP服务器
            mcp_server = mcp._mcp_server

            # 创建支持SSE的Starlette应用
            starlette_app = create_starlette_app(mcp_server, debug=True)
            port = 8080
            printmute(f"Starting MCP server with SSE transport on port {port}...", enable_print)
            printmute(f"SSE endpoint available at: http://localhost:{port}/sse", enable_print)

            # 使用uvicorn运行服务器
            uvicorn.run(starlette_app, host="0.0.0.0", port=port)

    except ImportError as e:
        printmute(f"错误: 导入MCP模块失败: {e}", enable_print)
        printmute("请运行以下命令安装必要的依赖:", enable_print)
        printmute("python -m pip install --upgrade mcp", enable_print)
        printmute("\n安装完成后，再次运行此脚本", enable_print)
        sys.exit(1)

@mcp.tool()
async def chat_to_ANP(ctx: Context, custom_msg: str, token: Optional[str] = None, unique_id_arg: Optional[str] = None) -> Dict[str, Any]:
    """发送消息到目标服务器
    
    Args:
        custom_msg: 要发送的消息
        token: 认证令牌，如果为None则会启动客户端认证获取token
        unique_id_arg: 可选的唯一ID，用于客户端认证
        
    Returns:
        Dict with message sending status information
    """
    app_context = ctx.request_context.lifespan_context
    
    try:
        # 创建一个后台任务来处理消息发送
        asyncio.create_task(_chat_to_ANP_impl(custom_msg, token, unique_id_arg))
        
        return {
            "status": "success",
            "message": f"消息 '{custom_msg}' 发送请求已提交",
            "error": None
        }
    except Exception as e:
        logger.error(f"发送消息时出错: {e}")
        return {
            "status": "error",
            "message": "发送消息失败",
            "error": str(e)
        }

async def _chat_to_ANP_impl(custom_msg: str, token: Optional[str] = None, unique_id_arg: Optional[str] = None):
    """发送消息的实际实现（内部函数）
    """
    try:
        if not token:
            logger.info(f"无token，正在启动客户端认证获取token...并发送消息: {custom_msg}")
            await ANP_req_auth(unique_id=unique_id_arg, msg=custom_msg)
            target_host = settings.TARGET_SERVER_HOST
            target_port = settings.TARGET_SERVER_PORT
            base_url = f"http://{target_host}:{target_port}"
            await ANP_req_chat(base_url=base_url, silent=True, from_chat=True, msg=custom_msg, token=token)
        else:
            logger.info(f"使用token...发送消息: {custom_msg}")
            target_host = settings.TARGET_SERVER_HOST
            target_port = settings.TARGET_SERVER_PORT
            base_url = f"http://{target_host}:{target_port}"
            # 调用did_core中的send_message_to_chat函数
            await ANP_req_chat(base_url=base_url, silent=True, from_chat=True, msg=custom_msg, token=token)
    except Exception as e:
        logger.error(f"发送消息时出错: {e}")
        return {
            "status": "error",
            "message": "发送消息失败",
            "error": str(e)
        }


import argparse

def run_mcp_server():
    """Run the MCP server."""
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='启动 MCP 服务器')
    parser.add_argument('--transport', '-t', type=str, choices=['stdio', 'sse'], default='stdio',
                        help='选择传输模式: stdio (默认) 或 sse')
    args = parser.parse_args()
    # 从args对象中正确获取transport参数值
    transport = args.transport
    
    # Install the MCP server for development
    import sys
    
    # 检查是否需要启用调试
    enable_debug = os.environ.get("ENABLE_DEBUGPY", "False").lower() == "true"
    
    if enable_debug:
        try:
            import debugpy
            # 允许其他客户端连接到调试器
            debugpy.listen(("0.0.0.0", 5678))
            printmute("调试器已启动，监听端口5678。您可以在VSCode中使用'Attach to Running MCP Server'配置连接到此进程。")
            # 如果需要等待调试器连接，取消下面这行的注释
            # debugpy.wait_for_client()
        except ImportError:
            printmute("警告: 无法导入debugpy模块，调试功能将被禁用")
            printmute("如需启用调试，请运行: pip install debugpy")
    
    try:
        # 尝试直接启动MCP服务器，而不是使用MCP CLI
        printmute(f"正在直接启动MCP服务器 (传输模式: {transport})...")
    
        # 使用FastMCP的run方法启动服务器
        if args.transport == 'stdio':
            printmute("使用 stdio 传输模式启动服务器")
            mcp.run(transport='stdio')
        else:
            # 设置HTTP服务器端口 - 仅在sse模式下需要
            # 获取底层MCP服务器
            mcp_server = mcp._mcp_server

            # 创建支持SSE的Starlette应用
            starlette_app = create_starlette_app(mcp_server, debug=True)
            port = 8080
            printmute(f"Starting MCP server with SSE transport on port {port}...")
            printmute(f"SSE endpoint available at: http://localhost:{port}/sse")

            # 使用uvicorn运行服务器
            uvicorn.run(starlette_app, host="0.0.0.0", port=port)

    except ImportError as e:
        printmute(f"错误: 导入MCP模块失败: {e}")
        printmute("请运行以下命令安装必要的依赖:")
        printmute("python -m pip install --upgrade mcp")
        printmute("\n安装完成后，再次运行此脚本")
        sys.exit(1)

if __name__ == "__main__":
    run_mcp_server()