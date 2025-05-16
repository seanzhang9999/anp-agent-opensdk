import os
import time
import logging
import threading
import asyncio
import json
import aiohttp
from datetime import datetime
from typing import Dict, Any, Callable, Optional, Union, List, Type
from enum import Enum

# 导入ANP核心组件
from anp_core.server.server import ANP_resp_start, ANP_resp_stop
from anp_core.auth.did_auth import get_did_url_from_did
from config.dynamic_config import dynamic_config
from anp_core.client.client import ANP_req_auth
from core.app import app
from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect, Response
from fastapi.responses import StreamingResponse

# 配置日志
from utils.log_base import logger


# 定义消息传输模式枚举
class MessageMode(Enum):
    HTTP_POST = "http_post"  # 传统HTTP POST请求
    WEBSOCKET = "websocket"  # WebSocket长连接
    HTTP_SSE = "http_sse"    # HTTP Server-Sent Events


class LocalAgent:
    """本地智能体，代表当前用户的DID身份"""
    
    def __init__(self, id: str, user_dir: str):
        """初始化本地智能体
        
        Args:
            id: DID标识符
            user_dir: 用户目录
        """
        self.id = id
        self.user_dir = user_dir
        self.logger = logger
        self._ws_connections = {}
        self._sse_clients = set()
        
    def send_message(self, target_agent, message: Dict[str, Any], mode: MessageMode = MessageMode.HTTP_POST):
        """向目标智能体发送消息
        
        Args:
            target_agent: 目标智能体对象
            message: 消息内容
            mode: 消息传输模式，默认为HTTP_POST
            
        Returns:
            响应结果
        """
        try:
            # 构建基础URL
            target_url = get_did_url_from_did(target_agent.id)
            
            # 根据不同的传输模式选择不同的发送方法
            if mode == MessageMode.HTTP_POST:
                return self._send_http_post(target_agent.id, target_url, message)
            elif mode == MessageMode.WEBSOCKET:
                return asyncio.run(self._send_websocket(target_agent.id, target_url, message))
            elif mode == MessageMode.HTTP_SSE:
                return asyncio.run(self._send_http_sse(target_agent.id, target_url, message))
            else:
                raise ValueError(f"不支持的消息传输模式: {mode}")
                
        except Exception as e:
            self.logger.error(f"发送消息时出错: {e}")
            return None
    
    def _send_http_post(self, target_did: str, target_url: str, message: Dict[str, Any]):
        """通过HTTP POST发送消息"""
        url = f"http://{target_url}/api/message"
        
        # 发送认证请求
        response = ANP_req_auth(
            self.id,
            target_did,
            url,
            self.user_dir,
            dynamic_config.get("demo_autorun.user_did_key_id"),
            message
        )
        
        return response
    
    async def _send_websocket(self, target_did: str, target_url: str, message: Dict[str, Any]):
        """通过WebSocket发送消息"""
        ws_url = f"ws://{target_url}/ws/message"
        
        try:
            # 创建WebSocket连接
            async with aiohttp.ClientSession() as session:
                # 添加认证头
                headers = await self._get_auth_headers(target_did, ws_url)
                
                async with session.ws_connect(ws_url, headers=headers) as ws:
                    # 发送消息
                    await ws.send_json(message)
                    
                    # 接收响应
                    response = await ws.receive_json()
                    return response
        except Exception as e:
            self.logger.error(f"WebSocket消息发送失败: {e}")
            return {"status": "error", "message": str(e)}
    
    async def _send_http_sse(self, target_did: str, target_url: str, message: Dict[str, Any]):
        """通过HTTP SSE发送消息"""
        sse_url = f"http://{target_url}/sse/message"
        
        try:
            # 创建HTTP会话
            async with aiohttp.ClientSession() as session:
                # 添加认证头
                headers = await self._get_auth_headers(target_did, sse_url)
                
                # 发送POST请求到SSE端点
                async with session.post(sse_url, json=message, headers=headers) as response:
                    return await response.json()
        except Exception as e:
            self.logger.error(f"SSE消息发送失败: {e}")
            return {"status": "error", "message": str(e)}
    
    async def _get_auth_headers(self, target_did: str, url: str):
        """获取认证头信息"""
        # 这里简化处理，实际应该调用ANP_req_auth的底层方法获取认证头
        # 返回一个示例头信息
        return {
            "Authorization": f"Bearer {self.id}_{target_did}",
            "Content-Type": "application/json"
        }
    
    def call_api(self, url: str, params: Dict[str, Any] = None, method: str = "GET"):
        """调用API
        
        Args:
            url: API URL
            params: 请求参数
            method: 请求方法
            
        Returns:
            API响应
        """
        try:
            # 从URL中提取目标DID
            target_url = url.split("//")[1].split("/")[0]
            target_did = f"did:wba:{target_url}"
            
            # 发送认证请求
            response = ANP_req_auth(
                self.id,
                target_did,
                url,
                self.user_dir,
                dynamic_config.get("demo_autorun.user_did_key_id"),
                params or {},
                method=method
            )
            
            return response
        except Exception as e:
            self.logger.error(f"调用API时出错: {e}")
            return None


class RemoteAgent:
    """远程智能体，代表其他DID身份"""
    
    def __init__(self, id: str):
        """初始化远程智能体
        
        Args:
            id: DID标识符
        """
        self.id = id


class ANPSDK:
    """ANP SDK主类，提供简单易用的接口"""
    
    def __init__(self, did: str = None, user_dir: str = None, port: int = None):
        """初始化ANP SDK
        
        Args:
            did: 可选，指定使用的DID，如果不指定则提供选择或创建新DID的功能
            user_dir: 可选，指定用户目录，默认使用配置中的目录
            port: 可选，指定服务器端口，默认使用配置中的端口
        """
        self.server_running = False
        self.port = port or dynamic_config.get('demo_autorun.user_did_port_1')
        self.agent = None
        self.api_routes = {}
        self.message_handlers = {}
        self.ws_connections = {}
        self.sse_clients = set()
        
        # 初始化路由器
        self.router = APIRouter()
        
        # 初始化日志
        self.logger = logger
        
        # 如果指定了DID，直接使用
        if did and user_dir:
            self.agent = LocalAgent(id=did, user_dir=user_dir)
            self.logger.info(f"已初始化智能体 DID: {did}")
        else:
            # 否则提供选择功能
            self._initialize_agent()
            
        # 注册默认路由
        self._register_default_routes()
    
    def _initialize_agent(self):
        """初始化智能体，提供DID选择或创建功能"""
        from demo_autorun import get_user_cfg_list, get_user_cfg
        
        user_list, name_to_dir = get_user_cfg_list()
        
        if not user_list:
            self.logger.error("未找到可用的DID配置")
            return
        
        # 提供选择界面或自动选择第一个
        status, did_dict, selected_name = get_user_cfg(1, user_list, name_to_dir)
        
        if status:
            self.agent = LocalAgent(
                id=did_dict['id'],
                user_dir=name_to_dir[selected_name]
            )
            self.logger.info(f"已选择智能体: {selected_name} DID: {did_dict['id']}")
        else:
            self.logger.error("初始化智能体失败")
    
    def _register_default_routes(self):
        """注册默认路由"""
        # 注册HTTP POST消息接收路由
        @app.post("/api/message")
        async def receive_message(request: Request):
            data = await request.json()
            return await self._handle_message(data)
        
        # 注册WebSocket消息接收路由
        @app.websocket("/ws/message")
        async def websocket_endpoint(websocket: WebSocket):
            await websocket.accept()
            client_id = id(websocket)
            self.ws_connections[client_id] = websocket
            
            try:
                while True:
                    data = await websocket.receive_json()
                    response = await self._handle_message(data)
                    await websocket.send_json(response)
            except WebSocketDisconnect:
                self.logger.info(f"WebSocket客户端断开连接: {client_id}")
                if client_id in self.ws_connections:
                    del self.ws_connections[client_id]
            except Exception as e:
                self.logger.error(f"WebSocket处理错误: {e}")
                if client_id in self.ws_connections:
                    del self.ws_connections[client_id]
        
        # 注册SSE消息接收路由
        @app.post("/sse/message")
        async def sse_message(request: Request):
            data = await request.json()
            response = await self._handle_message(data)
            return response
        
        # 注册SSE连接端点
        @app.get("/sse/connect")
        async def sse_connect(request: Request):
            async def event_generator():
                client_id = id(request)
                self.sse_clients.add(client_id)
                
                try:
                    # 发送初始连接成功消息
                    yield f"data: {json.dumps({'status': 'connected'})\n\n"
                    
                    # 保持连接打开
                    while True:
                        await asyncio.sleep(1)
                        # 实际应用中，这里会有一个消息队列，当有新消息时发送给客户端
                except Exception as e:
                    self.logger.error(f"SSE连接错误: {e}")
                finally:
                    if client_id in self.sse_clients:
                        self.sse_clients.remove(client_id)
            
            return StreamingResponse(event_generator(), media_type="text/event-stream")
    
    async def _handle_message(self, message: Dict[str, Any]):
        """处理接收到的消息"""
        message_type = message.get("type", "*")
        
        # 查找对应的消息处理器
        handler = self.message_handlers.get(message_type) or self.message_handlers.get("*")
        
        if handler:
            try:
                result = handler(message)
                # 如果处理器返回协程，等待其完成
                if asyncio.iscoroutine(result):
                    result = await result
                return result
            except Exception as e:
                self.logger.error(f"消息处理器执行错误: {e}")
                return {"status": "error", "message": str(e)}
        else:
            return {"status": "error", "message": f"未找到处理{message_type}类型消息的处理器"}
    
    def start_server(self):
        """启动服务器
        
        Returns:
            bool: 服务器是否成功启动
        """
        if self.server_running:
            self.logger.warning("服务器已经在运行")
            return True
        
        # 在Mac环境下添加延迟，避免多线程问题
        if os.name == 'posix' and 'darwin' in os.uname().sysname.lower():
            self.logger.info("检测到Mac环境，使用特殊启动方式")
        
        result = ANP_resp_start(port=self.port)
        
        if result:
            self.server_running = True
            self.logger.info(f"服务器已在端口 {self.port} 启动")
        else:
            self.logger.error(f"服务器启动失败，端口: {self.port}")
        
        return result
    
    def stop_server(self):
        """停止服务器
        
        Returns:
            bool: 服务器是否成功停止
        """
        if not self.server_running:
            return True
        
        # 关闭所有WebSocket连接
        for ws in self.ws_connections.values():
            asyncio.create_task(ws.close())
        self.ws_connections.clear()
        
        # 清空SSE客户端
        self.sse_clients.clear()
        
        result = ANP_resp_stop(port=self.port)
        
        if result:
            self.server_running = False
            self.logger.info("服务器已停止")
        else:
            self.logger.error("服务器停止失败")
        
        return result
    
    def send_message(self, target_did: str, message: Union[str, Dict], message_type: str = "text", mode: MessageMode = MessageMode.HTTP_POST):
        """向目标DID发送消息
        
        Args:
            target_did: 目标DID
            message: 消息内容，可以是字符串或字典
            message_type: 消息类型，默认为text
            mode: 消息传输模式，默认为HTTP_POST
        
        Returns:
            响应结果
        """
        if not self.agent:
            self.logger.error("智能体未初始化")
            return None
        
        # 创建远程智能体对象
        target_agent = RemoteAgent(id=target_did)
        
        # 构建消息
        if isinstance(message, str):
            msg = {
                "type": message_type,
                "content": message,
                "timestamp": datetime.now().isoformat()
            }
        else:
            msg = message
            if "timestamp" not in msg:
                msg["timestamp"] = datetime.now().isoformat()
            if "type" not in msg:
                msg["type"] = message_type
        
        # 发送消息
        return self.agent.send_message(target_agent, msg, mode)
    
    def call_api(self, target_did: str, api_path: str, params: Dict[str, Any] = None, method: str = "GET"):
        """调用目标DID的API
        
        Args:
            target_did: 目标DID
            api_path: API路径
            params: 参数，可选
            method: 请求方法，默认为GET
        
        Returns:
            API调用结果
        """
        if not self.agent:
            self.logger.error("智能体未初始化")
            return None
        
        # 构建API请求URL
        target_url = get_did_url_from_did(target_did)
        url = f"http://{target_url}/{api_path}"
        
        # 调用API
        return self.agent.call_api(url, params, method)
    
    def expose_api(self, route_path: str, methods: List[str] = None):
        """装饰器，用于暴露API到FastAPI
        
        Args:
            route_path: API路径
            methods: HTTP方法列表，默认为["GET"]
        
        Returns:
            装饰器函数
        """
        if methods is None:
            methods = ["GET"]
            
        def decorator(func):
            # 注册API路由
            self.api_routes[route_path] = func
            
            # 将函数注册到FastAPI
            for method in methods:
                if method.upper() == "GET":
                    app.get(f"/{route_path}", response_model=None)(func)
                elif method.upper() == "POST":
                    app.post(f"/{route_path}", response_model=None)(func)
                elif method.upper() == "PUT":
                    app.put(f"/{route_path}", response_model=None)(func)
                elif method.upper() == "DELETE":
                    app.delete(f"/{route_path}", response_model=None)(func)
            
            return func
        return decorator
    
    def register_message_handler(self, message_type: str = None):
        """注册消息处理器
        
        Args:
            message_type: 消息类型，如果为None则处理所有类型
        
        Returns:
            装饰器函数
        """
        def decorator(func):
            # 注册消息处理器
            self.message_handlers[message_type or "*"] = func
            return func
        return decorator
    
    async def broadcast_message(self, message: Dict[str, Any]):
        """向所有连接的客户端广播消息
        
        Args:
            message: 要广播的消息
        """
        # 向所有WebSocket连接广播
        for ws in self.ws_connections.values():
            try:
                await ws.send_json(message)
            except Exception as e:
                self.logger.error(f"WebSocket广播失败: {e}")
        
        # 实际应用中，这里会将消息放入SSE客户端的消息队列
        self.logger.info(f"向{len(self.sse_clients)}个SSE客户端广播消息")
    
    def visualize_handlers(self, output_format: str = "html", output_path: Optional[str] = None):
        """可视化当前注册的API路由和消息处理器
        
        Args:
            output_format: 输出格式，支持 "html"、"text" 或 "json"
            output_path: 输出文件路径，如果为None则返回字符串
            
        Returns:
            如果output_path为None，则返回可视化结果字符串；否则将结果写入文件并返回True
        """
        # 收集API路由信息
        api_routes_info = []
        for route_path, func in self.api_routes.items():
            api_routes_info.append({
                "path": f"/{route_path}",
                "name": func.__name__,
                "module": func.__module__,
                "doc": func.__doc__ or "",
                "is_async": asyncio.iscoroutinefunction(func)
            })
        
        # 收集消息处理器信息
        message_handlers_info = []
        for message_type, handler in self.message_handlers.items():
            message_handlers_info.append({
                "type": message_type,
                "name": handler.__name__,
                "module": handler.__module__,
                "doc": handler.__doc__ or "",
                "is_async": asyncio.iscoroutinefunction(handler)
            })
        
        # 收集默认路由信息
        default_routes_info = [
            {"path": "/api/message", "method": "POST", "description": "HTTP POST消息接收路由"},
            {"path": "/ws/message", "method": "WebSocket", "description": "WebSocket消息接收路由"},
            {"path": "/sse/message", "method": "POST", "description": "SSE消息接收路由"},
            {"path": "/sse/connect", "method": "GET", "description": "SSE连接端点"}
        ]
        
        # 根据输出格式生成结果
        if output_format.lower() == "json":
            result = json.dumps({
                "api_routes": api_routes_info,
                "message_handlers": message_handlers_info,
                "default_routes": default_routes_info
            }, indent=2, ensure_ascii=False)
        
        elif output_format.lower() == "text":
            result = "ANP SDK 路由和处理器注册顺序\n"
            result += "=========================\n\n"
            
            result += "API路由:\n"
            for i, route in enumerate(api_routes_info, 1):
                result += f"{i}. {route['path']} -> {route['name']}() {'[异步]' if route['is_async'] else ''}\n"
                if route['doc']:
                    result += f"   描述: {route['doc'].strip()}\n"
            
            result += "\n消息处理器:\n"
            for i, handler in enumerate(message_handlers_info, 1):
                result += f"{i}. 类型: {handler['type']} -> {handler['name']}() {'[异步]' if handler['is_async'] else ''}\n"
                if handler['doc']:
                    result += f"   描述: {handler['doc'].strip()}\n"
            
            result += "\n默认路由:\n"
            for i, route in enumerate(default_routes_info, 1):
                result += f"{i}. {route['path']} [{route['method']}] - {route['description']}\n"
        
        else:  # HTML格式
            result = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>ANP SDK 路由和处理器可视化</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        h1 {{ color: #333; }}
        h2 {{ color: #555; margin-top: 30px; }}
        .container {{ display: flex; flex-wrap: wrap; }}
        .section {{ flex: 1; min-width: 300px; margin-right: 20px; }}
        .card {{ border: 1px solid #ddd; border-radius: 5px; padding: 15px; margin-bottom: 15px; background-color: #f9f9f9; }}
        .card h3 {{ margin-top: 0; color: #333; }}
        .card p {{ margin: 5px 0; color: #666; }}
        .card .path {{ font-weight: bold; color: #0066cc; }}
        .card .method {{ display: inline-block; padding: 2px 6px; border-radius: 3px; font-size: 12px; margin-right: 5px; }}
        .card .get {{ background-color: #61affe; color: white; }}
        .card .post {{ background-color: #49cc90; color: white; }}
        .card .put {{ background-color: #fca130; color: white; }}
        .card .delete {{ background-color: #f93e3e; color: white; }}
        .card .ws {{ background-color: #9012fe; color: white; }}
        .card .async {{ font-style: italic; color: #0066cc; }}
        .card .doc {{ font-style: italic; color: #666; margin-top: 5px; }}
        .flow-diagram {{ margin-top: 30px; padding: 20px; border: 1px solid #ddd; border-radius: 5px; }}
        .flow-diagram svg {{ width: 100%; height: auto; }}
    </style>
</head>
<body>
    <h1>ANP SDK 路由和处理器可视化</h1>
    
    <div class="container">
        <div class="section">
            <h2>API路由</h2>
            {''.join([f'''
            <div class="card">
                <h3 class="path">{route['path']}</h3>
                <p><span class="method get">GET</span> <span class="method post">POST</span> {route['name']}() {'<span class="async">[异步]</span>' if route['is_async'] else ''}</p>
                {f'<p class="doc">{route["doc"]}</p>' if route['doc'] else ''}
            </div>''' for route in api_routes_info])}
        </div>
        
        <div class="section">
            <h2>消息处理器</h2>
            {''.join([f'''
            <div class="card">
                <h3>类型: {handler['type']}</h3>
                <p>{handler['name']}() {'<span class="async">[异步]</span>' if handler['is_async'] else ''}</p>
                {f'<p class="doc">{handler["doc"]}</p>' if handler['doc'] else ''}
            </div>''' for handler in message_handlers_info])}
        </div>
        
        <div class="section">
            <h2>默认路由</h2>
            {''.join([f'''
            <div class="card">
                <h3 class="path">{route['path']}</h3>
                <p><span class="method {'get' if route['method'] == 'GET' else 'post' if route['method'] == 'POST' else 'ws'}">{route['method']}</span> {route['description']}</p>
            </div>''' for route in default_routes_info])}
        </div>
    </div>
    
    <div class="flow-diagram">
        <h2>消息流程图</h2>
        <svg viewBox="0 0 800 400" xmlns="http://www.w3.org/2000/svg">
            <!-- 简单的流程图 -->
            <defs>
                <marker id="arrowhead" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
                    <polygon points="0 0, 10 3.5, 0 7" fill="#333" />
                </marker>
            </defs>
            
            <!-- 客户端 -->
            <rect x="50" y="50" width="120" height="60" rx="5" fill="#f5f5f5" stroke="#333" />
            <text x="110" y="85" text-anchor="middle">客户端</text>
            
            <!-- 服务器 -->
            <rect x="350" y="50" width="120" height="60" rx="5" fill="#f5f5f5" stroke="#333" />
            <text x="410" y="85" text-anchor="middle">服务器</text>
            
            <!-- 消息处理器 -->
            <rect x="650" y="50" width="120" height="60" rx="5" fill="#f5f5f5" stroke="#333" />
            <text x="710" y="85" text-anchor="middle">消息处理器</text>
            
            <!-- HTTP路径 -->
            <rect x="350" y="170" width="120" height="40" rx="5" fill="#61affe" stroke="#333" />
            <text x="410" y="195" text-anchor="middle" fill="white">/api/message</text>
            
            <!-- WebSocket路径 -->
            <rect x="350" y="230" width="120" height="40" rx="5" fill="#9012fe" stroke="#333" />
            <text x="410" y="255" text-anchor="middle" fill="white">/ws/message</text>
            
            <!-- SSE路径 -->
            <rect x="350" y="290" width="120" height="40" rx="5" fill="#49cc90" stroke="#333" />
            <text x="410" y="315" text-anchor="middle" fill="white">/sse/message</text>
            
            <!-- 连接线 -->
            <line x1="170" y1="80" x2="350" y2="80" stroke="#333" stroke-width="2" marker-end="url(#arrowhead)" />
            <line x1="470" y1="80" x2="650" y2="80" stroke="#333" stroke-width="2" marker-end="url(#arrowhead)" />
            
            <line x1="410" y1="110" x2="410" y2="170" stroke="#333" stroke-width="2" marker-end="url(#arrowhead)" />
            <line x1="410" y1="210" x2="410" y2="230" stroke="#333" stroke-width="2" marker-end="url(#arrowhead)" />
            <line x1="410" y1="270" x2="410" y2="290" stroke="#333" stroke-width="2" marker-end="url(#arrowhead)" />
            
            <line x1="470" y1="190" x2="650" y2="90" stroke="#333" stroke-width="2" marker-end="url(#arrowhead)" />
            <line x1="470" y1="250" x2="650" y2="90" stroke="#333" stroke-width="2" marker-end="url(#arrowhead)" />
            <line x1="470" y1="310" x2="650" y2="90" stroke="#333" stroke-width="2" marker-end="url(#arrowhead)" />
            
            <!-- 文本标签 -->
            <text x="260" y="65" text-anchor="middle">发送消息</text>
            <text x="560" y="65" text-anchor="middle">处理消息</text>
        </svg>
    </div>
</body>
</html>
"""
        
        # 如果指定了输出路径，则写入文件
        if output_path:
            try:
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(result)
                self.logger.info(f"已将可视化结果写入文件: {output_path}")
                return True
            except Exception as e:
                self.logger.error(f"写入文件时出错: {e}")
                return False
        
        # 否则返回结果字符串
        return result

    def __enter__(self):
        """上下文管理器入口，自动启动服务器"""
        self.start_server()
        return self
    
    async def __aenter__(self):
        """异步上下文管理器入口"""
        self.start_server()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器退出，自动停止服务器"""
        self.stop_server()
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器退出"""
        self.stop_server()