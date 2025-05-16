#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ANP SDK 示例程序

这个程序演示了如何使用ANP SDK的三种消息收发模式和API装饰器功能：
1. HTTP POST 消息收发
2. WebSocket 消息收发
3. HTTP SSE 消息收发
4. 使用装饰器发布API
"""

import asyncio
import json
from anp_sdk import ANPSDK, MessageMode
from loguru import logger
from fastapi import Request, Depends, Body
from typing import Dict, Any, Optional, List


# 创建一个简单的API处理函数
async def get_weather_data(city: str = "Beijing"):
    """一个简单的天气API示例"""
    return {
        "city": city,
        "temperature": "25°C",
        "condition": "晴天",
        "forecast": ["晴天", "多云", "小雨"]
    }


# 创建一个消息处理函数
def handle_text_message(message):
    """处理接收到的文本消息"""
    logger.info(f"收到文本消息: {message}")
    content = message.get("content", "")
    logger.info(f"消息内容: {content}")
    return {"status": "success", "message": "文本消息已处理"}


# 创建一个处理图片消息的函数
def handle_image_message(message):
    """处理接收到的图片消息"""
    logger.info(f"收到图片消息: {message}")
    image_url = message.get("url", "")
    logger.info(f"图片URL: {image_url}")
    return {"status": "success", "message": "图片消息已处理"}


# 创建一个处理所有类型消息的函数
def handle_all_messages(message):
    """处理所有类型的消息"""
    logger.info(f"收到未知类型消息: {message}")
    return {"status": "success", "message": "未知类型消息已处理"}


async def http_post_example(anp: ANPSDK, target_did: str):
    """HTTP POST 消息发送示例"""
    logger.info("=== HTTP POST 消息发送示例 ===")
    
    # 发送文本消息
    text_message = "这是通过HTTP POST发送的文本消息"
    response = anp.send_message(target_did, text_message, "text", MessageMode.HTTP_POST)
    logger.info(f"文本消息发送响应: {response}")
    
    # 发送结构化消息
    structured_message = {
        "type": "structured",
        "content": "这是结构化消息",
        "data": {
            "key1": "value1",
            "key2": "value2",
            "nested": {
                "key3": "value3"
            }
        }
    }
    response = anp.send_message(target_did, structured_message, mode=MessageMode.HTTP_POST)
    logger.info(f"结构化消息发送响应: {response}")
    
    await asyncio.sleep(1)  # 等待一秒


async def websocket_example(anp: ANPSDK, target_did: str):
    """WebSocket 消息发送示例"""
    logger.info("=== WebSocket 消息发送示例 ===")
    
    # 发送文本消息
    text_message = "这是通过WebSocket发送的文本消息"
    response = anp.send_message(target_did, text_message, "text", MessageMode.WEBSOCKET)
    logger.info(f"WebSocket文本消息发送响应: {response}")
    
    # 发送图片消息
    image_message = {
        "type": "image",
        "url": "https://example.com/image.jpg",
        "description": "这是一张示例图片"
    }
    response = anp.send_message(target_did, image_message, mode=MessageMode.WEBSOCKET)
    logger.info(f"WebSocket图片消息发送响应: {response}")
    
    await asyncio.sleep(1)  # 等待一秒


async def sse_example(anp: ANPSDK, target_did: str):
    """HTTP SSE 消息发送示例"""
    logger.info("=== HTTP SSE 消息发送示例 ===")
    
    # 发送通知消息
    notification = {
        "type": "notification",
        "title": "系统通知",
        "content": "这是通过SSE发送的系统通知",
        "level": "info"
    }
    response = anp.send_message(target_did, notification, mode=MessageMode.HTTP_SSE)
    logger.info(f"SSE通知消息发送响应: {response}")
    
    await asyncio.sleep(1)  # 等待一秒


async def broadcast_example(anp: ANPSDK):
    """广播消息示例"""
    logger.info("=== 广播消息示例 ===")
    
    # 广播一条消息给所有连接的客户端
    broadcast_message = {
        "type": "broadcast",
        "content": "这是一条广播消息",
        "timestamp": "2023-06-01T12:00:00Z"
    }
    await anp.broadcast_message(broadcast_message)
    logger.info("广播消息已发送")
    
    await asyncio.sleep(1)  # 等待一秒


async def main():
    """主函数，演示ANP SDK的三种消息收发模式和API装饰器功能"""
    # 创建SDK实例
    anp = ANPSDK()
    
    # 注册消息处理器
    @anp.register_message_handler("text")
    def text_handler(message):
        return handle_text_message(message)
    
    @anp.register_message_handler("image")
    def image_handler(message):
        return handle_image_message(message)
    
    @anp.register_message_handler()
    def default_handler(message):
        return handle_all_messages(message)
    
    # 注册API
    @anp.expose_api("api/weather", methods=["GET"])
    async def weather(city: str = "Beijing"):
        return await get_weather_data(city)
    
    @anp.expose_api("api/echo", methods=["POST"])
    async def echo(request: Request):
        data = await request.json()
        return {"echo": data}
    
    @anp.expose_api("api/users/{user_id}", methods=["GET"])
    async def get_user(user_id: str):
        return {"user_id": user_id, "name": f"User {user_id}"}
    
    @anp.expose_api("api/items", methods=["GET", "POST"])
    async def items(request: Request):
        if request.method == "GET":
            return {"items": ["item1", "item2", "item3"]}
        else:  # POST
            data = await request.json()
            return {"added": data}
    
    # 启动服务器
    logger.info("启动服务器...")
    server_result = anp.start_server()
    logger.info(f"服务器启动结果: {server_result}")
    
    # 等待服务器完全启动
    await asyncio.sleep(2)
    
    try:
        # 获取目标DID (这里使用示例DID，实际使用时需要替换为真实DID)
        target_did = "did:wba:localhost:9527:wba:user:7c15257e086afeba"
        
        # 演示HTTP POST消息发送
        await http_post_example(anp, target_did)
        
        # 演示WebSocket消息发送
        await websocket_example(anp, target_did)
        
        # 演示HTTP SSE消息发送
        await sse_example(anp, target_did)
        
        # 演示广播消息
        await broadcast_example(anp)
        
        # 等待一段时间以便查看结果
        logger.info("等待5秒...")
        await asyncio.sleep(5)
        
    finally:
        # 停止服务器
        logger.info("停止服务器...")
        stop_result = anp.stop_server()
        logger.info(f"服务器停止结果: {stop_result}")


# 使用异步上下文管理器的示例
async def async_context_manager_example():
    """演示如何使用异步上下文管理器自动管理服务器生命周期"""
    logger.info("使用异步上下文管理器示例...")
    
    async with ANPSDK() as anp:
        # 服务器会自动启动
        logger.info("服务器已自动启动")
        
        # 注册API
        @anp.expose_api("api/async_test")
        async def async_test():
            return {"message": "这是一个异步API"}
        
        # 发送消息
        target_did = "did:wba:localhost:9527:wba:user:7c15257e086afeba"
        response = anp.send_message(target_did, "使用异步上下文管理器发送的消息")
        logger.info(f"消息发送响应: {response}")
        
        # 等待一段时间
        await asyncio.sleep(3)
        
        # 退出上下文管理器时，服务器会自动停止
    
    logger.info("异步上下文管理器示例结束，服务器已自动停止")


if __name__ == "__main__":
    # 运行主函数
    asyncio.run(main())
    
    # 如果需要演示异步上下文管理器，取消下面的注释
    # asyncio.run(async_context_manager_example())