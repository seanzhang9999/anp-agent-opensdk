# -*- coding: utf-8 -*-
# @Time    : 2025/4/30 20:12
# mcp_stdio_client.py
import asyncio
import json
import os
import argparse
from typing import List

from fastapi import status
from loguru import logger
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.sse import sse_client
from mcp.types import TextResourceContents, TextContent

user_dir = os.path.dirname(os.path.abspath(__file__))
user_dir = os.path.join(user_dir, "logs")
# 设置日志
logger.add(f"{user_dir}/stdio_client.log", rotation="1000 MB", retention="7 days", encoding="utf-8")

def get_status_data(status_contents: List[TextContent]):
    assert len(status_contents) != 0, "状态返回数据为空"
    status_content = status_contents[0]
    status_data = {}
    try:
        status_data = json.loads(status_content.text)
    except json.JSONDecodeError:
        logger.warning("错误：服务器状态数据格式错误")

    return status_data


def get_text_content_data(text_contents: List[TextContent]):
    assert len(text_contents) == 1, "MCPserver返回数据为空"
    text_content = text_contents[0]
    content_data = {}
    try:
        content_data = json.loads(text_content.text)
    except json.JSONDecodeError:
        logger.warning("错误：MCPserver返回的文本数据格式错误")
        ValueError("MCPserver返回的文本数据格式错误")
    return content_data


async def main():
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='启动 MCP 客户端')
    parser.add_argument('--transport', '-t', type=str, choices=['stdio', 'sse'], default='stdio',
                        help='选择传输模式: stdio (默认) 或 sse')
    parser.add_argument('--server-url', type=str, default='http://localhost:8080/sse',
                        help='SSE 服务器 URL (仅在 sse 模式下使用)')
    args = parser.parse_args()
    
    # 获取传输模式
    transport = args.transport
    logger.info(f"使用 {transport} 模式连接服务器")
    
    if transport == 'stdio':
        # 获取服务器脚本路径
        current_dir = os.path.dirname(os.path.abspath(__file__))
        server_path = os.path.join(current_dir, "mcp_stdio_server.py")

        # 创建服务器参数
        server_params = StdioServerParameters(
            command="python",
            args=[server_path, "--transport", "stdio"]
        )

        logger.info("1. 正在通过stdio建立与MCP服务器的连接...")
        async with stdio_client(server_params) as streams:
            await run_client_session(streams)
    else:  # sse 模式
        server_url = args.server_url
        logger.info(f"1. 正在通过SSE连接到服务器 {server_url}...")
        async with sse_client(url=server_url) as streams:
            await run_client_session(streams)


async def run_client_session(streams):
    # 创建客户端会话
    async with ClientSession(*streams) as session:
        logger.info("2. 会话已建立，正在初始化...")
        await session.initialize()

        # 列出可用工具
        logger.info("3. 获取服务器可用工具列表...")
        response = await session.list_tools()
        logger.info(f"4. 可用工具: {[tool.name for tool in response.tools]}")
        # logger.info(f"4. 可用工具 - 详细信息: {[tool.to for tool in response.tools]}")

        logger.info("5. 启动 DID WBA 服务器...")
        result = await session.call_tool("start_did_server")
        logger.info(f"6. 服务器启动结果: {get_text_content_data(result.content)}", )

        await asyncio.sleep(2)

        # todo stdio 启动服务 的进程是临时的，全局变量的方式获取状态 可能无法实现；需要redis或者kafuka之类的中间件
        logger.info("\n7. 检查服务器状态...")
        server_status = await session.read_resource("status://did-wba")
        logger.info(f"8. 服务器状态: {server_status.contents}")
        status_data = get_status_data(server_status.contents)
        if not status_data["server"]["running"]:
            logger.error("错误：服务器启动失败 - 全局变量的方式获取状态不可靠")
            # return

        logger.info("9. 启动 DID WBA 客户端并发送测试消息...")
        client_result = await session.call_tool(
            "start_did_client",
            {"message": "你好，这是通过 MCP 客户端发送的测试消息"}
        )
        # logger.info(f"10. 客户端启动结果: {get_text_content_data(client_result.content)}")
        logger.info(f"10. 客户端启动结果: {client_result.content}")

        # 等待1秒确保客户端初始化完成
        await asyncio.sleep(1)

        # 测试chat_to_ANP功能
        logger.info("10. 测试chat_to_ANP功能...")
        try:
            chat_result = await session.call_tool(
                "chat_to_ANP",
                {"custom_msg": "这是通过chat_to_ANP工具发送的测试消息"}
            )
            logger.info(f"10. 消息发送结果: {get_text_content_data(chat_result.content)}")
        except Exception as e:
            logger.error(f"10. 消息发送失败: {e}")

        # 确认客户端状态
        client_status = await session.read_resource("status://did-wba")
        logger.info(f"客户端状态: {client_status.contents}")
        status_data = get_status_data(server_status.contents)
        if not status_data["server"]["running"]:
            logger.error("错误：客户端启动失败 - 全局变量的方式获取状态不可靠")
            # return

        logger.info("11. 等待并获取连接事件...")
        for i in range(5):  # 尝试获取3次事件
            logger.info(f"12. 第{i + 1}次尝试获取事件...")
            try:
                events = await session.call_tool(
                    "get_connection_events",
                    {"wait_for_new": True, "timeout": 5}  # 缩短超时时间
                )
                events_data = get_text_content_data(events.content)

                logger.info(f"13. 获取到的事件: {events_data}")
                if events_data["events"]:
                    logger.info(f"14. 最新消息内容: {events_data['events'][-1]}")
                    break

            except Exception as e:
                logger.info(f"获取事件时出错: {e}")
                continue

        logger.info("15. 停止 DID WBA 客户端...")
        stop_client = await session.call_tool("stop_did_client")
        logger.info(f"16. 客户端停止结果: {get_text_content_data(stop_client.content)}")

        logger.info("17. 停止 DID WBA 服务器...")
        stop_server = await session.call_tool("stop_did_server")
        logger.info(f"18. 服务器停止结果: {get_text_content_data(stop_server.content)}")

        logger.info("19. 最终状态检查...")
        final_status = await session.read_resource("status://did-wba")
        logger.info(f"20. 最终状态: {get_text_content_data(final_status.contents)}")

        logger.info("21. 全流程模拟完成!")


if __name__ == "__main__":
    asyncio.run(main())
