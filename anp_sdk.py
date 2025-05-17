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
from config.dynamic_config import dynamic_config
from anp_core.client.client import ANP_req_auth
from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect, Response, FastAPI
from fastapi.responses import StreamingResponse

# 导入代理组件
from anp_core.proxy.ws_proxy_client import WSProxyClient

# 配置日志
from loguru import logger


# 定义消息传输模式枚举
class MessageMode(Enum):
    HTTP_POST = "http_post"  # 传统HTTP POST请求
    WEBSOCKET = "websocket"  # WebSocket长连接
    HTTP_SSE = "http_sse"    # HTTP Server-Sent Events


class RemoteAgent:
    """远程智能体，代表其他DID身份"""
    
    def __init__(self, id: str):
        """初始化远程智能体
        
        Args:
            id: DID标识符
        """
        self.id = id

        host, port = get_did_host_port_from_did(id)

        self.host = host
        self.port = port


 
   



class LocalAgent:
    """本地智能体，代表当前用户的DID身份"""
    
    def __init__(self, id: str, user_dir: str, name:str = "未命名", agent_type: str = "personal"):
        """初始化本地智能体
        
        Args:
            id: DID标识符
            user_dir: 用户目录
            agent_type: 智能体类型，"personal"或"service"
        """
        if name == "未命名":
            self.name = f"未命名智能体{id}"
        self.id = id
        self.name = name
        self.user_dir = user_dir
        self.agent_type = agent_type
        self.logger = logger
        self._ws_connections = {}
        self._sse_clients = set()
        self.token_info_dict = {}  # 存储token信息
        import requests
        self.requests = requests
        # 新增: API与消息handler注册表
        self.api_routes = {}  # path -> handler
        self.message_handlers = {}  # type -> handler
    
    # 支持装饰器和函数式注册API
    def expose_api(self, path: str, func: Callable = None):
        if func is None:
            def decorator(f):
                self.api_routes[path] = f
                return f
            return decorator
        else:
            self.api_routes[path] = func
            return func
    
    # 支持装饰器和函数式注册消息handler
    def register_message_handler(self, msg_type: str, func: Callable = None):
        if func is None:
            def decorator(f):
                self.message_handlers[msg_type] = f
                return f
            return decorator
        else:
            self.message_handlers[msg_type] = func
            return func

    def handle_request(self, req_did: str, request_data: Dict[str, Any]):
        """处理来自req_did的请求
        
        Args:
            req_did: 请求方DID
            request_data: 请求数据
            
        Returns:
            处理结果
        """
        req_type = request_data.get("type")
        if req_type == "api_call":
            api_path = request_data.get("path")
            handler = self.api_routes.get(api_path)
            if handler:
                try:
                    result = handler(request_data)
                    if isinstance(result, dict) and "anp_result" in result:
                        return result
                    return {"anp_result": result}
                except Exception as e:
                    self.logger.error(f"API调用错误: {e}")
                    return {"anp_result": {"status": "error", "message": str(e)}}
            else:
                return {"anp_result": {"status": "error", "message": f"未找到API: {api_path}"}}
        elif req_type == "message":
            msg_type = request_data.get("message_type", "*")
            handler = self.message_handlers.get(msg_type) or self.message_handlers.get("*")
            if handler:
                try:
                    result = handler(request_data)
                    if isinstance(result, dict) and "anp_result" in result:
                        return result
                    return {"anp_result": result}
                except Exception as e:
                    self.logger.error(f"消息处理错误: {e}")
                    return {"anp_result": {"status": "error", "message": str(e)}}
            else:
                return {"anp_result": {"status": "error", "message": f"未找到消息处理器: {msg_type}"}}
        else:
            return {"anp_result": {"status": "error", "message": "未知的请求类型"}}
    
    def store_token_info(self, req_did: str, token: str, expires_delta: int):
        """存储token信息
        
        Args:
            req_did: 请求方DID
            token: 生成的token
            expires_delta: 过期时间（秒）
        """
        now = datetime.now()
        expires_at = now + timedelta(seconds=expires_delta)
        
        self.token_info_dict[req_did] = {
            "token": token,
            "created_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
            "is_revoked": False,
            "req_did": req_did
        }
    
    def get_token_info(self, req_did: str):
        """获取token信息
        
        Args:
            req_did: 请求方DID
            
        Returns:
            token信息字典，如果不存在则返回None
        """
        return self.token_info_dict.get(req_did)
    
    def revoke_token(self, req_did: str):
        """撤销token
        
        Args:
            req_did: 请求方DID
            
        Returns:
            是否成功撤销
        """
        if req_did in self.token_info_dict:
            self.token_info_dict[req_did]["is_revoked"] = True
            return True
        return False

    def call_api(self, url: str, params: dict = None, method: str = "GET"):
        """
        调用远程API
        Args:
            url: 目标API完整URL
            params: 请求参数
            method: 请求方法，默认为GET
        Returns:
            响应内容
        """
        import requests
        try:
            if method.upper() == "GET":
                resp = requests.get(url, params=params, timeout=10)
            else:
                resp = requests.post(url, json=params, timeout=10)
            if resp.status_code == 200:
                return resp.json()
            else:
                self.logger.error(f"API调用失败，状态码: {resp.status_code}")
                return {"status": "error", "message": f"API调用失败，状态码: {resp.status_code}"}
        except Exception as e:
            self.logger.error(f"API调用异常: {e}")
            return {"status": "error", "message": str(e)}

    async def _send_http_post(self, target_did: str, target_url: str, message: Dict[str, Any]):
        """通过HTTP POST发送消息
        
        Args:
            target_did: 目标DID
            target_url: 目标URL
            message: 消息内容
            
        Returns:
            响应结果
        """
        try:
            # 构建POST消息URL
            post_url = f"http://{target_url}/api/message"
            
            # 构建请求数据
            request_data = {
                "req_did": self.id,
                "resp_did": target_did,
                "message": message
            }
            
            # 发送POST请求到消息端点
            async with aiohttp.ClientSession() as session:
                async with session.post(post_url, json=request_data) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        self.logger.error(f"HTTP POST请求失败，状态码: {response.status}")
                        return {"status": "error", "message": f"HTTP POST请求失败，状态码: {response.status}"}
                        
        except Exception as e:
            self.logger.error(f"发送HTTP POST消息时出错: {e}")
            return {"status": "error", "message": str(e)}

    async def _send_http_sse(self, target_did: str, target_url: str, message: Dict[str, Any]):
        """通过HTTP SSE发送消息
        
        Args:
            target_did: 目标DID
            target_url: 目标URL
            message: 消息内容
            
        Returns:
            响应结果
        """
        try:
            # 构建SSE消息URL
            sse_url = f"http://{target_url}/sse/message"
            
            # 构建请求数据
            request_data = {
                "req_did": self.id,
                "resp_did": target_did,
                "message": message
            }
            
            # 发送SSE请求到消息端点
            async with aiohttp.ClientSession() as session:
                async with session.post(sse_url, json=request_data) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        self.logger.error(f"HTTP SSE请求失败，状态码: {response.status}")
                        return {"status": "error", "message": f"HTTP SSE请求失败，状态码: {response.status}"}
                        
        except Exception as e:
            self.logger.error(f"发送HTTP SSE消息时出错: {e}")
            return {"status": "error", "message": str(e)}


    def header_req_auth(Request):
        """
        验证请求头是否包含Authorization
        DID请求头，走DID验证
        Token请求头，走Token验证
        函数返回
            req_did和resp_did  方便路由使用
            检验结果 确认放行
            返回头 方便后续加入header
                返回认证头时一律走 "access_token","token_type","req_did","resp_did"方式返回
                因为请求方无法解析bearer token,所以后两个明文返回，未来可以考虑did公钥加密
                在有双向认证请求时，附加DID认证头，resp_did_auth_header
        """
        auth_header = Request.headers.get("Authorization")
        if auth_header and auth_header.startswith("ANP "):
            return auth_header.split(" ")[1]
        return None

    def header_resp_auth(Response):
        """
        验证响应头是否包含Authorization
        校验DID响应头，完成双向认证后，存储Token和双向认证结果
        返回req_did和resp_did 检验结果
        """
        auth_header = Request.headers.get("Authorization")
        if auth_header and auth_header.startswith("ANP "):
            return auth_header.split(" ")[1]
        return None
    
    def header_req_generate(req_did: str, resp_did: str):
        """
        生成请求头，
        如果有Token，直接用Token请求头
        如果本地Agent没有远方Agent的Token，生成DID请求头
        如果本地Agent没有远方Agent的双向认证结果或双向认证结果过期，附加双向认证请求
        """
        req_did = LocalAgent(req_did)
        resp_did = RemoteAgent(resp_did)
        token = req_did.get_token(resp_did)
        if token:
            return f"ANP {token}"


        return f"ANP {req_did}"




class ANPSDK:
    """ANP SDK主类，提供简单易用的接口"""
    
    def __init__(self,  port: int = None):
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
        
        # 创建FastAPI应用实例
        self.app = FastAPI(title="ANP SDK API", description="ANP SDK API服务")
        
        # 创建路由器实例
        from anp_core.agent.agent_router import AgentRouter
        self.router = AgentRouter()
        
        # 初始化日志
        self.logger = logger
        
        # 公网代理客户端
        self.proxy_client = None
        self.proxy_mode = False
        self.proxy_task = None
        
            
    def register_agent(self, agent: LocalAgent):
        """注册智能体到路由器
        
        Args:
            agent: LocalAgent实例
        """
        self.router.register_agent(agent)
        self.logger.info(f"已注册智能体到路由器: {agent.id}")
            
        # 注册默认路由
        self._register_default_routes()
    
    def get_agents(self):
        """获取所有已注册的智能体

        Returns:
            智能体列表
        """
        return self.router.local_agents.values()

    def get_agent(self, did: str):
        """获取指定DID的智能体

        Args:
            did: DID字符串

        Returns:
            LocalAgent实例，如果未找到则返回None
        """
        return self.router.get_agent(did)
    
    def _register_default_routes(self):
        """注册默认路由"""
        # 注册智能体 API 路由
        @self.app.get("/agent/api/{did}/{subpath:path}")
        async def api_entry_get(did: str, subpath:str, request: Request):
            data =dict(request.query_params)
            req_did = request.query_params.get("req_did", "demo_caller")
            resp_did = did
            data["type"] = "api_call"
            data["path"] = f"/{subpath}"
            result = self.router.route_request(req_did, resp_did, data)
            return result

        @self.app.post("/agent/api/{did}/{subpath:path}")
        async def api_entry_post(did: str, subpath:str, request: Request):
            data = await request.json()
            req_did = request.query_params.get("req_did", "demo_caller")
            resp_did = did
            data["type"] = "api_call"
            data["path"] = f"/{subpath}"
            result = self.router.route_request(req_did, resp_did, data)
            return result

        # 注册智能体消息路由
        @self.app.post("/agent/message/{did}")
        async def message_entry(did: str, request: Request):
            data = await request.json()
            req_did = data.get("req_did", "demo_caller")
            resp_did = did
            data["type"] = "message"
            result = self.router.route_request(req_did, resp_did, data)
            return result

        # 注册HTTP POST消息接收路由
        @self.app.post("/api/message")
        async def receive_message(request: Request):
            data = await request.json()
            return await self._handle_message(data)
        
        # 注册WebSocket消息接收路由
        @self.app.websocket("/ws/message")
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
        @self.app.post("/sse/message")
        async def sse_message(request: Request):
            data = await request.json()
            response = await self._handle_message(data)
            return response
        
        # 注册SSE连接端点
        @self.app.get("/sse/connect")
        async def sse_connect(request: Request):
            async def event_generator():
                client_id = id(request)
                self.sse_clients.add(client_id)
                try:
                    # 发送初始连接成功消息
                    yield f"data: {json.dumps({'status': 'connected'})}\n\n"
                    
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
        logger.info(f"准备处理接收到的消息内容: {message}")

        # 如果收到的是带有 message 字段的包裹，自动解包
        if "message" in message:
            message = message["message"]

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
        
        # 注册通过 expose_api 装饰器收集的API路由
        for route_path, route_info in self.api_routes.items():
            func = route_info['func']
            methods = route_info['methods']
            self.app.add_api_route(f"/{route_path}", func, methods=methods)
        
        # 启动服务器
        import uvicorn
        import threading

        agent1 = list(self.get_agents())[0]

        host, port = get_did_host_port_from_did(agent1.id)   

        def run_server():
            uvicorn.run(self.app, host=host, port=int(port))
        
        # 在新线程中启动服务器
        self.server_thread = threading.Thread(target=run_server, daemon=True)
        self.server_thread.start()
        
        self.server_running = True
        self.logger.info(f"服务器已在端口 {self.port} 启动")
        
        return True
    
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
        
        # 由于服务器在独立线程中运行，这里我们不需要显式停止它
        # 线程会在主程序退出时自动终止（因为是daemon线程）
        
        self.server_running = False
        self.logger.info("服务器已停止")
        
        return True
    
    async def send_message(self, target_did: str, message: Union[str, Dict], message_type: str = "text", mode: MessageMode = MessageMode.HTTP_POST):
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
        response = await self.agent.send_message(target_agent, msg, mode)
        return response
    
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
            self.api_routes[route_path] = {'func': func, 'methods': methods}
            
            # 如果服务器已经运行，直接注册到FastAPI应用
            if self.server_running:
                self.app.add_api_route(f"/{route_path}", func, methods=methods)
            
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
            from templates.template_generator import generate_visualization_html
            result = generate_visualization_html(api_routes_info, message_handlers_info, default_routes_info)
        
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

    async def start_proxy_mode(self, proxy_url: str):
        """启动公网代理模式
        
        Args:
            proxy_url: 公网WebSocket代理服务器URL
            
        Returns:
            是否成功启动代理模式
        """
        if not self.agent:
            self.logger.error("未初始化智能体，无法启动代理模式")
            return False
        
        if self.proxy_mode:
            self.logger.warning("代理模式已经启动")
            return True
        
        try:
            # 创建代理客户端
            self.proxy_client = WSProxyClient(self, proxy_url, self.agent.id)
            
            # 启动代理客户端
            self.proxy_task = asyncio.create_task(self.proxy_client.start())
            self.proxy_mode = True
            
            self.logger.info(f"已启动公网代理模式，连接到: {proxy_url}")
            return True
        
        except Exception as e:
            self.logger.error(f"启动代理模式时出错: {e}")
            return False
    
    async def stop_proxy_mode(self):
        """停止公网代理模式
        
        Returns:
            是否成功停止代理模式
        """
        if not self.proxy_mode or not self.proxy_client:
            return True
        
        try:
            # 断开代理客户端连接
            await self.proxy_client.disconnect()
            
            # 取消代理任务
            if self.proxy_task and not self.proxy_task.done():
                self.proxy_task.cancel()
                try:
                    await self.proxy_task
                except asyncio.CancelledError:
                    pass
            
            self.proxy_client = None
            self.proxy_mode = False
            self.proxy_task = None
            
            self.logger.info("已停止公网代理模式")
            return True
        
        except Exception as e:
            self.logger.error(f"停止代理模式时出错: {e}")
            return False
    
    async def _handle_api_call(self, req_did: str, resp_did: str, api_path: str, method: str, params: Dict[str, Any]):
        """处理API调用请求
        
        Args:
            req_did: 请求方DID
            resp_did: 响应方DID
            api_path: API路径
            method: 请求方法
            params: 请求参数
            
        Returns:
            API调用结果
        """
        # 检查是否是本地智能体
        if resp_did != self.agent.id:
            return {"status": "error", "message": f"未找到智能体: {resp_did}"}
        
        # 查找对应的API处理器
        api_key = f"{method.lower()}:{api_path}"
        if api_key in self.api_routes:
            handler = self.api_routes[api_key]
            try:
                # 调用API处理器
                result = await handler(req_did=req_did, **params)
                return result
            except Exception as e:
                self.logger.error(f"API调用错误: {e}")
                return {"status": "error", "message": str(e)}
        else:
            return {"status": "error", "message": f"未找到API: {api_path} [{method}]"}

    def get_did_url_from_did(did):
        """根据DID返回 http://host:port 形式的URL"""
        host , port = get_did_host_port_from_did(did)
        return f"{host}:{port}"

    def get_did_host_port_from_did(did):

        """从DID中解析出主机和端口"""

        host, port = None, None

        if did.startswith('did:wba:'):

            try:

                # 例：did:wba:localhost%3A9527:wba:user:7c15257e086afeba

                did_parts = did.split(':')

                if len(did_parts) > 2:

                    host_port = did_parts[2]

                    if '%3A' in host_port:

                        host, port = host_port.split('%3A')
                    else:
                        host = did_parts[2]
                        port = did_parts[3]

            except Exception as e:

                print(f"解析did失败: {did}, 错误: {e}")

        if not host or not port:

            raise ValueError(f"未能从did解析出host和port，did: {did}")

        return host, port

