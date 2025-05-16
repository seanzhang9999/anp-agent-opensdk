#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
ANP SDK 可视化服务器示例

这个示例展示了如何在实际应用中使用ANPSDK的visualize_handlers方法，
并提供一个简单的Web界面来查看API路由和消息处理器的注册顺序。
"""

import os
import asyncio
from anp_sdk import ANPSDK, MessageMode
from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse

# 创建ANPSDK实例
sdk = ANPSDK(port=9528)

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

# 添加可视化相关的API路由
@sdk.expose_api("visualize", methods=["GET"])
def visualize_handlers_html(request: Request):
    """以HTML格式可视化当前注册的API路由和消息处理器"""
    html_result = sdk.visualize_handlers(output_format="html")
    return HTMLResponse(content=html_result)

@sdk.expose_api("visualize/json", methods=["GET"])
def visualize_handlers_json(request: Request):
    """以JSON格式可视化当前注册的API路由和消息处理器"""
    json_result = sdk.visualize_handlers(output_format="json")
    return JSONResponse(content=json.loads(json_result))

@sdk.expose_api("visualize/text", methods=["GET"])
def visualize_handlers_text(request: Request):
    """以文本格式可视化当前注册的API路由和消息处理器"""
    text_result = sdk.visualize_handlers(output_format="text")
    return PlainTextResponse(content=text_result)

# 添加一个主页路由
@sdk.expose_api("", methods=["GET"])
def home(request: Request):
    """主页"""
    return HTMLResponse(content="""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>ANP SDK 可视化服务器</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; line-height: 1.6; }
            h1 { color: #333; }
            .container { max-width: 800px; margin: 0 auto; }
            .card { border: 1px solid #ddd; border-radius: 5px; padding: 20px; margin-bottom: 20px; }
            .btn { display: inline-block; padding: 10px 15px; background-color: #4CAF50; color: white; 
                  text-decoration: none; border-radius: 4px; margin-right: 10px; }
            .btn:hover { background-color: #45a049; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>ANP SDK 可视化服务器</h1>
            
            <div class="card">
                <h2>可视化选项</h2>
                <p>选择以下选项之一来查看API路由和消息处理器的注册顺序：</p>
                <a href="/visualize" class="btn">HTML格式</a>
                <a href="/visualize/json" class="btn">JSON格式</a>
                <a href="/visualize/text" class="btn">文本格式</a>
            </div>
            
            <div class="card">
                <h2>API示例</h2>
                <p>以下是一些可以测试的API端点：</p>
                <ul>
                    <li><a href="/weather/current?city=上海">获取上海当前天气</a></li>
                    <li><a href="/weather/forecast?city=广州&days=5">获取广州5天天气预报</a></li>
                    <li><a href="/user/profile?user_id=12345">获取用户资料</a></li>
                </ul>
            </div>
        </div>
    </body>
    </html>
    """)


def main():
    """主函数"""
    print("启动ANP SDK可视化服务器...")
    print("服务器启动后，可以通过浏览器访问 http://localhost:9528 查看可视化界面")
    
    # 启动服务器
    with sdk:
        try:
            # 保持主线程运行
            import time
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("服务器已停止")


if __name__ == "__main__":
    import json  # 导入json模块，用于JSON格式化
    main()