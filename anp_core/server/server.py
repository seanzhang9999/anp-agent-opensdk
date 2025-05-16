"""DID WBA Server implementation.

This module provides the server functionality for the DID WBA system.
"""
import os
import logging
from config import dynamic_config
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
    """封装服务器状态的类，支持多个服务器实例的管理"""
    def __init__(self):
        self.servers = {}  # 使用字典存储不同端口的服务器状态
    
    def set_running(self, status, port=None):
        """设置服务器运行状态
        
        Args:
            status: 运行状态（True/False）
            port: 服务器端口
        """
        if port is None:
            return
            
        if port not in self.servers:
            self.servers[port] = {"running": False, "thread": None, "instance": None}
        
        self.servers[port]["running"] = status
    
    def is_running(self, port=None):
        """获取服务器运行状态
        
        Args:
            port: 服务器端口，如果为None则检查是否有任何服务器在运行
            
        Returns:
            bool: 服务器是否正在运行
        """
        if port is None:
            # 如果没有指定端口，检查是否有任何服务器在运行
            return any(server["running"] for server in self.servers.values()) if self.servers else False
        
        if port in self.servers:
            return self.servers[port]["running"]
        return False
        
    def get_instance(self, port):
        """获取指定端口的服务器实例
        
        Args:
            port: 服务器端口
            
        Returns:
            object: 服务器实例
        """
        if port in self.servers:
            return self.servers[port]["instance"]
        return None
        
    def set_instance(self, port, instance):
        """设置指定端口的服务器实例
        
        Args:
            port: 服务器端口
            instance: 服务器实例
        """
        if port not in self.servers:
            self.servers[port] = {"running": False, "thread": None, "instance": None}
        
        self.servers[port]["instance"] = instance
        
    def get_thread(self, port):
        """获取指定端口的服务器线程
        
        Args:
            port: 服务器端口
            
        Returns:
            Thread: 服务器线程
        """
        if port in self.servers:
            return self.servers[port]["thread"]
        return None
        
    def set_thread(self, port, thread):
        """设置指定端口的服务器线程
        
        Args:
            port: 服务器端口
            thread: 服务器线程
        """
        if port not in self.servers:
            self.servers[port] = {"running": False, "thread": None, "instance": None}
        
        self.servers[port]["thread"] = thread

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
    
    # 如果指定了端口，更新设置
    if port:
        current_port = port
    else:
        current_port = dynamic_config.get("demo_autorun.user_did_port_1")
    
    # 检查该端口的服务器是否已经在运行
    if server_status.is_running(current_port):
        logger.warning(f"端口 {current_port} 的服务器已经在运行中")
        return True
    
    try:
        # 创建uvicorn配置
        config = uvicorn.Config(
            "anp_core.server.server:app",
            host=dynamic_config.get("demo_autorun.user_did_hostname"),
            port=current_port,
            reload=settings.DEBUG,
            use_colors=True,
            log_level="error"
        )
        
        # 创建服务器实例
        server_instance = uvicorn.Server(config)
        server_instance.should_exit = False
        
        # 设置服务器状态
        server_status.set_running(True, current_port)
        server_status.set_instance(current_port, server_instance)
        
        # 创建并启动服务器线程，使用自定义的非阻塞运行方法
        def run_server_nonblocking():
            import sys
            # 在Mac环境下使用不同的事件循环策略
            # if sys.platform == 'darwin':  # 检测是否为Mac
            # 使用uvloop或其他更适合Mac的事件循环实现
            #     import uvloop
            #    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
            #     # 使用底层的serve方法而不是run方法
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(server_status.get_instance(current_port).serve())
            except Exception as e:
                logger.error(f"服务器运行出错: {e}")
                server_status.set_running(False, current_port)
            finally:
                loop.close()
        
        server_thread = threading.Thread(target=run_server_nonblocking)
        server_thread.daemon = True
        server_thread.start()
        
        # 设置线程
        server_status.set_thread(current_port, server_thread)
        
        # 等待服务器启动
        for _ in range(10):
            if server_status.is_running(current_port):
                logger.info(f"服务器已在端口 {current_port} 启动")
                return True
            time.sleep(0.5)
        
        logger.error("服务器启动超时")
        return False
    except Exception as e:
        logger.error(f"启动服务器时出错: {e}")
        server_status.set_running(False, current_port)
        return False


def ANP_resp_stop(port=None):
    """停止DID WBA服务器
    
    Args:
        port: 可选的服务器端口号，如果不提供则停止所有服务器
        
    Returns:
        bool: 服务器是否成功停止
    """
    global server_status
    
    # 如果指定了端口，只停止该端口的服务器
    if port:
        if not server_status.is_running(port):
            logger.warning(f"端口 {port} 的服务器未运行")
            return True
        
        try:
            # 发送停止信号给服务器
            server_instance = server_status.get_instance(port)
            if server_instance:
                server_instance.should_exit = True
                # 确保信号被处理
                time.sleep(0.5)
            
            # 标记服务器状态为已停止
            server_status.set_running(False, port)
            
            logger.info(f"端口 {port} 的服务器已停止")
            return True
        except Exception as e:
            logger.error(f"停止端口 {port} 的服务器时出错: {e}")
            return False
    else:
        # 停止所有服务器
        success = True
        for port in list(server_status.servers.keys()):
            try:
                # 发送停止信号给服务器
                server_instance = server_status.get_instance(port)
                if server_instance:
                    server_instance.should_exit = True
                    # 确保信号被处理
                    time.sleep(0.5)
                
                # 标记服务器状态为已停止
                server_status.set_running(False, port)
                
                logger.info(f"端口 {port} 的服务器已停止")
            except Exception as e:
                logger.error(f"停止端口 {port} 的服务器时出错: {e}")
                success = False
        logger.info("全部服务器已停止")
        return success
