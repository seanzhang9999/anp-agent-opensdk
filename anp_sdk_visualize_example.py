#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
ANP SDK 可视化示例

这个示例展示了如何使用ANPSDK的visualize_handlers方法来可视化API路由和消息处理器的注册顺序。
"""

import os
import asyncio
from anp_sdk import ANPSDK, MessageMode

# 创建ANPSDK实例
sdk = ANPSDK(port=9527)

# 注册一些API路由
@sdk.expose_api("weather/current", methods=["GET"])
def get_current_weather(city: str = "北京"):
    """获取当前天气信息"""
    return {"city": city, "temperature": 25, "condition": "晴朗"}

@sdk.expose_api("weather/forecast", methods=["GET"])
def get_weather_forecast(city: str = "北京", days: int = 3):
    """获取天气预报"""
    return {"city": city, "forecast": [{"day": i, "temperature": 20 + i, "condition": "晴朗"} for i in range(1, days + 1)]}

@sdk.expose_api("user/profile", methods=["GET", "POST"])
async def user_profile(user_id: str = None):
    """获取或更新用户资料"""
    await asyncio.sleep(0.1)  # 模拟异步操作
    return {"user_id": user_id or "default", "name": "测试用户", "age": 30}

# 注册一些消息处理器
@sdk.register_message_handler("text")
def handle_text_message(message):
    """处理文本消息"""
    print(f"收到文本消息: {message.get('content')}")
    return {"status": "success", "message": "文本消息已处理"}

@sdk.register_message_handler("image")
async def handle_image_message(message):
    """处理图片消息"""
    await asyncio.sleep(0.1)  # 模拟异步处理
    print(f"收到图片消息: {message.get('url')}")
    return {"status": "success", "message": "图片消息已处理"}

@sdk.register_message_handler()
def handle_default_message(message):
    """处理默认消息（未指定类型的消息处理器会处理所有类型）"""
    print(f"收到未知类型消息: {message}")
    return {"status": "success", "message": "未知类型消息已处理"}


def main():
    """主函数"""
    # 创建输出目录
    os.makedirs("output", exist_ok=True)
    
    # 生成HTML格式的可视化结果并保存到文件
    html_result = sdk.visualize_handlers(output_format="html", output_path="output/handlers_visualization.html")
    if html_result:
        print("HTML格式的可视化结果已保存到 output/handlers_visualization.html")
    
    # 生成文本格式的可视化结果
    text_result = sdk.visualize_handlers(output_format="text")
    print("\n文本格式的可视化结果:")
    print(text_result)
    
    # 生成JSON格式的可视化结果
    json_result = sdk.visualize_handlers(output_format="json")
    print("\nJSON格式的可视化结果已生成，长度:", len(json_result))
    
    print("\n可以通过浏览器打开 output/handlers_visualization.html 查看可视化结果")


if __name__ == "__main__":
    main()