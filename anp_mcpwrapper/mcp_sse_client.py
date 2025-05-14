# -*- coding: utf-8 -*-
# mcp_sse_client.py - SSE版本的MCP客户端

import asyncio
import json
import os
from typing import List

from fastapi import status
from loguru import logger
from mcp import ClientSession, StdioServerParameters
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client
from mcp.types import TextResourceContents, TextContent
user_dir = os.path.dirname(os.path.abspath(__file__))
user_dir = os.path.join(user_dir, "logs")
# 设置日志
logger.add(f"{user_dir}/sse_client.log", rotation="1000 MB", retention="7 days", encoding="utf-8")


def get_status_data(status_contents: List[TextContent]):
    """解析状态数据"""
    assert len(status_contents) != 0, "状态返回数据为空"
    status_content = status_contents[0]
    status_data = {}
    try:
        status_data = json.loads(status_content.text)
    except json.JSONDecodeError:
        logger.warning("错误：服务器状态数据格式错误")

    return status_data


def get_text_content_data(text_contents: List[TextContent]):
    """解析文本内容数据"""
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
    """主函数，连接到SSE服务器并执行操作"""
    server_url = "http://localhost:8080/sse"

    logger.info(f"1. Connecting to SSE server at {server_url}...")

    # 通过SSE建立连接
    async with sse_client(url=server_url) as streams:
        # 创建客户端会话
        async with ClientSession(*streams) as session:
            # 初始化会话
            logger.info("2. 初始化会话...")
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
            logger.info(f"10. 客户端启动结果: {get_text_content_data(client_result.content)}")

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
            for i in range(5):  # 尝试获取5次事件
                logger.info(f"12. 第{i + 1}次尝试获取事件...")
                try:
                    events = await session.call_tool(
                        "get_connection_events",
                        {"wait_for_new": True, "timeout": 10}  # 增加超时时间到10秒
                    )
                    events_data = get_text_content_data(events.content)
                    logger.info(f"13. 事件结果: {events_data}")

                    if events_data["status"] == "success" and events_data["events"]:
                        logger.info(f"14. 收到 {len(events_data['events'])} 个事件")
                        for event in events_data["events"]:
                            logger.info(f"15. 事件: {event}")
                        break
                    else:
                        logger.info("16. 未收到事件，继续等待...")
                except Exception as e:
                    logger.error(f"17. 获取事件出错: {e}")

                await asyncio.sleep(3)  # 增加循环间隔等待时间

            # 清除事件
            logger.info("18. 清除连接事件...")
            clear_result = await session.call_tool("clear_connection_events")
            logger.info(f"19. 清除结果: {get_text_content_data(clear_result.content)}")

            # 停止客户端
            logger.info("20. 停止 DID WBA 客户端...")
            stop_client_result = await session.call_tool("stop_did_client")
            logger.info(f"21. 客户端停止结果: {get_text_content_data(stop_client_result.content)}")

            # 停止服务器
            logger.info("22. 停止 DID WBA 服务器...")
            stop_server_result = await session.call_tool("stop_did_server")
            logger.info(f"23. 服务器停止结果: {get_text_content_data(stop_server_result.content)}")

            logger.info("24. MCP SSE 客户端示例完成")


if __name__ == "__main__":
    asyncio.run(main())