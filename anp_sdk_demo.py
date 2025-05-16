#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ANP SDK 演示程序

这个程序演示了如何使用ANP SDK进行基本操作：
1. 初始化SDK
2. 启动服务器
3. 发送消息
4. 调用API
5. 注册API和消息处理器
6. 停止服务器
"""

import asyncio
from anp_sdk import ANPSDK
from utils.log_base import logger


# 创建一个简单的API处理函数
async def weather_api(city: str = "Beijing"):
    """一个简单的天气API示例"""
    return {
        "city": city,
        "temperature": "25°C",
        "condition": "晴天",
        "forecast": ["晴天", "多云", "小雨"]
    }


# 创建一个消息处理函数
def handle_message(message):
    """处理接收到的消息"""
    logger.info(f"收到消息: {message}")
    return {"status": "success", "message": "消息已处理"}


async def main():
    """主函数，演示ANP SDK的使用"""
    # 创建SDK实例
    anp = ANPSDK()
    
    # 注册API和消息处理器
    @anp.expose_api("api/weather")
    async def weather(city: str = "Beijing"):
        return await weather_api(city)
    
    @anp.register_message_handler("text")
    def text_handler(message):
        return handle_message(message)
    
    # 启动服务器
    logger.info("启动服务器...")
    server_result = anp.start_server()
    logger.info(f"服务器启动结果: {server_result}")
    
    # 等待服务器完全启动
    await asyncio.sleep(2)
    
    try:
        # 获取目标DID (这里使用示例DID，实际使用时需要替换为真实DID)
        target_did = "did:wba:localhost:9528:wba:user:7c15257e086afeba"
        
        # 发送消息
        logger.info(f"发送消息到 {target_did}")
        message = {
            "type": "text",
            "content": "Hello from ANP SDK Demo!",
            "data": {
                "key1": "value1",
                "key2": "value2"
            }
        }
        response = anp.send_message(target_did, message)
        logger.info(f"消息发送响应: {response}")
        
        # 调用API
        logger.info(f"调用API: {target_did}/api/test")
        api_response = anp.call_api(target_did, "api/test", {"param": "test_value"})
        logger.info(f"API调用响应: {api_response}")
        
        # 等待一段时间以便查看结果
        logger.info("等待5秒...")
        await asyncio.sleep(5)
        
        # 发送另一条消息
        logger.info(f"发送第二条消息到 {target_did}")
        response = anp.send_message(target_did, "这是第二条测试消息")
        logger.info(f"第二条消息发送响应: {response}")
        
        # 再次等待
        logger.info("再次等待5秒...")
        await asyncio.sleep(5)
    finally:
        # 停止服务器
        logger.info("停止服务器...")
        stop_result = anp.stop_server()
        logger.info(f"服务器停止结果: {stop_result}")


# 使用上下文管理器的示例
async def context_manager_example():
    """演示如何使用上下文管理器自动管理服务器生命周期"""
    logger.info("使用上下文管理器示例...")
    
    async with ANPSDK() as anp:
        # 服务器会自动启动
        logger.info("服务器已自动启动")
        
        # 发送消息
        target_did = "did:wba:localhost:9528:wba:user:7c15257e086afeba"
        response = anp.send_message(target_did, "使用上下文管理器发送的消息")
        logger.info(f"消息发送响应: {response}")
        
        # 等待一段时间
        await asyncio.sleep(3)
        
        # 退出上下文管理器时，服务器会自动停止
    
    logger.info("上下文管理器示例结束，服务器已自动停止")


if __name__ == "__main__":
    # 运行主函数
    asyncio.run(main())
    
    # 如果需要演示上下文管理器，取消下面的注释
    # asyncio.run(context_manager_example())