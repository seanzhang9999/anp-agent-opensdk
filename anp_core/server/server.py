"""DID WBA Server implementation.

This module provides the server functionality for the DID WBA system.
"""
import os
import logging
import uvicorn
import asyncio
import signal
import threading
import time

from loguru import logger
from fastapi import FastAPI

from core.config import settings
from core.app import create_app

# 服务器状态管理类
class ServerStatus:
    """封装服务器状态的类，确保所有模块引用同一个状态对象"""
    def __init__(self):
        self.running = False
        self.port = None
        self.thread = None
        self.instance = None
    
    def set_running(self, status, port=None):
        """设置服务器运行状态
        
        Args:
            status: 运行状态（True/False）
            port: 服务器端口
        """
        self.running = status
        if port:
            self.port = port
    
    def is_running(self):
        """获取服务器运行状态
        
        Returns:
            bool: 服务器是否正在运行
        """
        return self.running

# 创建全局单例
server_status = ServerStatus()

user_dir = os.path.dirname(os.path.abspath(__file__))
user_dir = os.path.join(user_dir, "logs")
# 设置日志
logger.add(f"{user_dir}/anpcore_server.log", rotation="1000 MB", retention="7 days", encoding="utf-8")

# 创建FastAPI应用
app = create_app()


@app.get("/", tags=["status"])
async def root():
    """
    Root endpoint for server status check.
    
    Returns:
        dict: Server status information
    """
    return {
        "status": "running",
        "service": "DID WBA Example",
        "version": "0.1.0",
        "mode": "Server",
        "documentation": "/docs"
    }


def ANP_resp_start(port=None):
    """启动DID WBA服务器
    
    Args:
        port: 可选的服务器端口号
        
    Returns:
        bool: 服务器是否成功启动
    """
    global server_status
    
    # 检查服务器是否已经在运行
    if server_status.is_running():
        logger.warning("服务器已经在运行中")
        return True
    
    # 如果指定了端口，更新设置
    if port:
        settings.PORT = port
        server_status.port = port
    
    try:
        # 创建uvicorn配置
        config = uvicorn.Config(
            "anp_core.server.server:app",
            host=settings.HOST,
            port=settings.PORT,
            reload=settings.DEBUG,
            use_colors=True,
            log_level="error"
        )
        
        # 创建服务器实例
        server_status.instance = uvicorn.Server(config)
        server_status.instance.should_exit = False
        
        # 设置服务器状态
        server_status.set_running(True, settings.PORT)
        
        # 创建并启动服务器线程，使用自定义的非阻塞运行方法
        def run_server_nonblocking():
            # 使用底层的serve方法而不是run方法
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(server_status.instance.serve())
            except Exception as e:
                logger.error(f"服务器运行出错: {e}")
                server_status.set_running(False)
            finally:
                loop.close()
        
        server_status.thread = threading.Thread(target=run_server_nonblocking)
        server_status.thread.daemon = True
        server_status.thread.start()
        
        # 等待服务器启动
        for _ in range(10):
            if server_status.is_running():
                logger.info(f"服务器已在端口 {settings.PORT} 启动")
                return True
            time.sleep(0.5)
        
        logger.error("服务器启动超时")
        return False
    except Exception as e:
        logger.error(f"启动服务器时出错: {e}")
        server_status.set_running(False)
        return False


def ANP_resp_stop():
    """停止DID WBA服务器
    
    Returns:
        bool: 服务器是否成功停止
    """
    global server_status
    
    if not server_status.is_running():
        logger.warning("服务器未运行")
        return True
    
    try:
        # 发送停止信号给服务器
        if server_status.instance:
            server_status.instance.should_exit = True
            # 确保信号被处理
            time.sleep(0.5)
        
        # 标记服务器状态为已停止
        server_status.set_running(False)
        
        # 等待服务器线程结束
        if server_status.thread and server_status.thread.is_alive():
            server_status.thread.join(timeout=10.0)  # 设置超时时间，避免无限等待
            
        logger.info("服务器已停止")
        return True
    except Exception as e:
        logger.error(f"停止服务器时出错: {e}")
        return False