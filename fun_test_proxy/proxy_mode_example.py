#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ANP SDK公网代理模式示例

这个示例演示了如何启动ANP SDK的公网代理模式，连接到公网WebSocket转发服务，
使内网的ANP SDK能够对外暴露API和聊天接口。
"""

import asyncio
import argparse
import logging
import sys
import os

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from anp_sdk import ANPSDK, MessageMode

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("proxy_example")


async def main():
    # 解析命令行参数
    parser = argparse.ArgumentParser(description="ANP SDK公网代理模式示例")
    parser.add_argument("--proxy-url", type=str, default="ws://localhost:8000/ws/proxy", 
                        help="公网WebSocket代理服务器URL")
    parser.add_argument("--did", type=str, help="指定使用的DID")
    parser.add_argument("--user-dir", type=str, help="指定用户目录")
    parser.add_argument("--port", type=int, default=8080, help="本地服务器端口")
    
    args = parser.parse_args()
    
    # 创建ANPSDK实例
    sdk = ANPSDK(did=args.did, user_dir=args.user_dir, port=args.port)
    
    # 注册消息处理器
    @sdk.register_message_handler("chat")
    async def handle_chat_message(message):
        logger.info(f"收到聊天消息: {message}")
        return {
            "status": "success",
            "message": "收到您的消息",
            "original_message": message
        }
    
    # 暴露API
    @sdk.expose_api("/api/echo", methods=["POST"])
    async def echo_api(req_did: str, text: str = ""):
        logger.info(f"收到API调用，来自: {req_did}, 文本: {text}")
        return {
            "status": "success",
            "message": "API调用成功",
            "echo": text,
            "from": req_did
        }
    
    try:
        # 启动本地服务器
        sdk.start_server()
        logger.info(f"本地服务器已启动，端口: {args.port}")
        
        # 启动公网代理模式
        await sdk.start_proxy_mode(args.proxy_url)
        logger.info(f"公网代理模式已启动，连接到: {args.proxy_url}")
        
        # 保持程序运行
        while True:
            await asyncio.sleep(1)
    
    except KeyboardInterrupt:
        logger.info("接收到退出信号，正在关闭...")
    
    except Exception as e:
        logger.error(f"运行时错误: {e}")
    
    finally:
        # 停止公网代理模式
        await sdk.stop_proxy_mode()
        logger.info("公网代理模式已停止")
        
        # 停止本地服务器
        sdk.stop_server()
        logger.info("本地服务器已停止")


if __name__ == "__main__":
    asyncio.run(main())