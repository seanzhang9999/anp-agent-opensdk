# Copyright 2024 ANP Open SDK Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import time
import logging
import threading
import asyncio
import json
import aiohttp
from datetime import datetime, timedelta
from typing import Dict, Any, Callable, Optional, Union, List, Type
from enum import Enum
from fastapi.middleware.cors import CORSMiddleware
import inspect

# 安全中间件
from anp_open_sdk.auth.auth_middleware import auth_middleware

# 两个历史遗留路由 用于认证 和 did发布 
from anp_open_sdk.service import router_auth, router_did


# 导入ANP核心组件

from anp_open_sdk.config.dynamic_config import dynamic_config
from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect, Response, FastAPI
from fastapi.responses import StreamingResponse



# 配置日志
from loguru import logger


class RemoteAgent:
    """远程智能体，代表其他DID身份"""
    
    def __init__(self, id: str):
        """初始化远程智能体
        
        Args:
            id: DID标识符
        """
        self.id = id

        host, port = ANPSDK.get_did_host_port_from_did(id)

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
        self.key_id = dynamic_config.get('anp_sdk.user_did_key_id')
        self.userdid_filepath = dynamic_config.get('anp_sdk.user_did_path')

        self.userdid_filepath = os.path.join(self.userdid_filepath, user_dir)

        self.did_document_path = f"{self.userdid_filepath}/did_document.json"

        self.private_key_path = f"{self.userdid_filepath}/{self.key_id}_private.pem"

        self.jwt_private_key_path = f"{self.userdid_filepath}/private_key.pem"

        self.jwt_public_key_path = f"{self.userdid_filepath}/public_key.pem"


        self.logger = logger
        self._ws_connections = {}
        self._sse_clients = set()
        self.token_to_remote_dict = {}  # 存储颁发的token信息
        self.token_from_remote_dict = {}  # 存储领取的token信息
        import requests
        self.requests = requests
        # 新增: API与消息handler注册表
        self.api_routes = {}  # path -> handler
        self.message_handlers = {}  # type -> handler
        # 新增: 群事件handler注册表
        # {(group_id, event_type): [handlers]}
        self._group_event_handlers = {}
        # [(event_type, handler)] 全局handler
        self._group_global_handlers = []

    
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
        # 保持原有实现
        if func is None:
            def decorator(f):
                self.message_handlers[msg_type] = f
                return f
            return decorator
        else:
            self.message_handlers[msg_type] = func
            return func

    def register_group_event_handler(self, handler: Callable, group_id: str = None, event_type: str = None):
        """
        注册群事件处理器
        - group_id=None 表示全局
        - event_type=None 表示所有类型
        handler: (group_id, event_type, event_data) -> None/awaitable
        """
        if group_id is None and event_type is None:
            self._group_global_handlers.append((None, handler))
        elif group_id is None:
            self._group_global_handlers.append((event_type, handler))
        else:
            key = (group_id, event_type)
            self._group_event_handlers.setdefault(key, []).append(handler)

    def _get_group_event_handlers(self, group_id: str, event_type: str):
        """
        获取所有应该处理该事件的handler，顺序为：
        1. 全局handler（event_type=None或匹配）
        2. 指定群/类型handler
        """
        handlers = []
        for et, h in self._group_global_handlers:
            if et is None or et == event_type:
                handlers.append(h)
        for (gid, et), hs in self._group_event_handlers.items():
            if gid == group_id and (et is None or et == event_type):
                handlers.extend(hs)
        return handlers

    async def _dispatch_group_event(self, group_id: str, event_type: str, event_data: dict):
        """
        分发群事件到所有已注册的handler，支持awaitable和普通函数
        """
        handlers = self._get_group_event_handlers(group_id, event_type)
        for handler in handlers:
            try:
                ret = handler(group_id, event_type, event_data)
                if inspect.isawaitable(ret):
                    await ret  # 处理异步任务
            except Exception as e:
                self.logger.error(f"群事件处理器出错: {e}")
                
    def __del__(self):
        """确保在对象销毁时释放资源"""
        try:
            # 清理WebSocket连接
            for ws in self._ws_connections.values():
                # 由于在析构函数中不能使用异步调用，记录日志提示可能的资源泄漏
                self.logger.debug(f"LocalAgent {self.id} 销毁时存在未关闭的WebSocket连接")
            
            # 清理其他资源
            self._ws_connections.clear()
            self._sse_clients.clear()
            self.token_to_remote_dict.clear()
            self.token_from_remote_dict.clear()
            
            self.logger.debug(f"LocalAgent {self.id} 资源已释放")
        except Exception:
            # 忽略错误，防止在解释器关闭时出现问题
            pass
                
    async def start_group_listening(self, sdk, group_url: str, group_id: str):
        """
        启动对指定群组的消息监听
        
        Args:
            sdk: ANPSDK 实例
            group_url: 群组URL
            group_id: 群组ID
            
        Returns:
            asyncio.Task: 监听任务对象，可用于后续取消
        """
        from anp_open_sdk.service.agent_message_group import listen_group_messages
        import asyncio
        
        # 创建监听任务
        task = asyncio.create_task(
            listen_group_messages(sdk, self.id, group_url, group_id)
        )
        
        self.logger.info(f"已启动群组 {group_id} 的消息监听")
        return task
       

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
    
    def store_token_to_remote(self, req_did: str, token: str, expires_delta: int):
        """存储颁发给其他方的token信息
        
        Args:
            req_did: 请求方DID
            token: 生成的token
            expires_delta: 过期时间（秒）
        """
        from datetime import datetime, timedelta, timezone
        now = datetime.now(timezone.utc)
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_delta)
        
        self.token_to_remote_dict[req_did] = {
            "token": token,
            "created_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
            "is_revoked": False,
            "req_did": req_did
        }
    
    def get_token_from_remote(self, req_did: str):
        """获取从其他方拿到存储在自己空间的token信息
        
        Args:
            req_did: 请求方DID
            
        Returns:
            token信息字典，如果不存在则返回None
        """
        return self.token_from_remote_dict.get(req_did)
    

    def store_token_from_remote(self, req_did: str, token: str):
        """存储从其他方拿到的token信息
        
        Args:
            req_did: 请求方DID
            token: 生成的token
            expires_delta: 过期时间（秒）
        """
        now = datetime.now()
        self.token_from_remote_dict[req_did] = {
            "token": token,
            "created_at": now.isoformat(),
            "req_did": req_did
        }
    
    def get_token_to_remote(self, req_did: str):
        """获取颁发给其他方的token信息
        
        Args:
            req_did: 请求方DID
            
        Returns:
            token信息字典，如果不存在则返回None
        """
        return self.token_to_remote_dict.get(req_did)
    
    def revoke_token_to_remote(self, req_did: str):
        """撤销颁发给其他方的token
        
        Args:
            req_did: 请求方DID
            
        Returns:
            是否成功撤销
        """
        if req_did in self.token_to_remote_dict:
            self.token_to_remote_dict[req_did]["is_revoked"] = True
            return True
        return False



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
        self.port = port or dynamic_config.get('anp_sdk.user_did_port_1')
        self.agent = None
        self.api_routes = {}
        self.message_handlers = {}
        self.ws_connections = {}
        self.sse_clients = set()
        
        debugmode = dynamic_config.get("anp_sdk.debugmode")

        if debugmode:
            self.app= FastAPI(
                title="ANP SDK Server in DebugMode", 
                description="ANP SDK Server in DebugMode",
                version="0.1.0",
                reload= True,
                docs_url="/docs" ,
                redoc_url="/redoc"
            )
        else:
            self.app= FastAPI(
                title="ANP SDK Server",
                description="ANP SDK Server",
                version="0.1.0",
                reload= False,
                docs_url=None,
                redoc_url=None
            )


            # Add CORS middleware
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],  # In production, specify exact origins
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )   

        # Add authentication middleware
        @self.app.middleware("http")
        async def auth_middleware_wrapper(request, call_next):
            return await auth_middleware(request, call_next, self)


        # 创建路由器实例
        from anp_open_sdk.service.router_agent import AgentRouter
        self.router = AgentRouter()
        
        # 初始化日志
        self.logger = logger
        
        # 公网代理客户端
        self.proxy_client = None
        self.proxy_mode = False
        self.proxy_task = None
        
        # 群组相关属性
        self.group_queues = {}  # 群组消息队列: {group_id: {client_id: Queue}}
        self.group_members = {}  # 群组成员列表: {group_id: set(did)}
        
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

           # Include routers

        self.app.include_router(router_auth.router)
        self.app.include_router(router_did.router)
        @self.app.get("/", tags=["status"])
        async def root():
            """
            Root endpoint for server status check.
            
            Returns:
                dict: Server status information
            """
            return {
                "status": "running",
                "service": "ANP SDK Server",
                "version": "0.1.0",
                "mode": "Server and client",
                "documentation": "/docs"
            }


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
        @self.app.post("/agent/message/post/{did}")
        async def message_entry_post(did: str, request: Request):
            data = await request.json()
            req_did = request.query_params.get("req_did", "demo_caller")
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
        
        # 群组消息队列
        self.group_queues = {}
        # 群组成员列表
        self.group_members = {}
        
        # 注册群聊消息发送路由
        @self.app.post("/group/{group_id}/message")
        async def group_message(group_id: str, request: Request):
            data = await request.json()
            req_did = request.query_params.get("req_did")
            if not req_did:
                return {"error": "未提供发送者 DID"}
            
            # 验证发送者权限
            if group_id not in self.group_members or req_did not in self.group_members[group_id]:
                return {"error": "无权在此群组发送消息"}
            
            time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # 构造消息
            message = {
                "sender": req_did,
                "content": data.get("content", ""),
                "timestamp": time,
                "type": "group_message"
            }
            
            # 将消息发送到群组队列
            if group_id in self.group_queues:
                for queue in self.group_queues[group_id].values():
                    await queue.put(message)
            
            return {"status": "success"}
        
        # 注册群聊SSE连接端点
        @self.app.get("/group/{group_id}/connect")
        async def group_connect(group_id: str, request: Request):
            req_did = request.query_params.get("req_did")
            if req_did.find("%3A") == -1:
                parts = req_did.split(":", 4)  # 分割 4 份 把第三个冒号替换成%3A 现在都上了urlencode 这个代码应该无用了
                req_did = ":".join(parts[:3]) + "%3A" + ":".join(parts[3:])
            if not req_did:
                return {"error": "未提供订阅者 DID"}

            # 验证订阅者权限
            if group_id not in self.group_members or req_did not in self.group_members[group_id]:
                return {"error": "无权订阅此群组消息"}
            
            async def event_generator():
                # 初始化群组
                if group_id not in self.group_queues:
                    self.group_queues[group_id] = {}
                
                # 为该客户端创建消息队列
                client_id = f"{group_id}_{req_did}_{id(request)}"
                self.group_queues[group_id][client_id] = asyncio.Queue()
                
                try:
                    # 发送初始连接成功消息
                    yield f"data: {json.dumps({'status': 'connected', 'group_id': group_id})}\n\n"
                    
                    # 保持连接打开并等待消息
                    while True:
                        try:
                            message = await asyncio.wait_for(
                                self.group_queues[group_id][client_id].get(),
                                timeout=30
                            )
                            yield f"data: {json.dumps(message)}\n\n"
                        except asyncio.TimeoutError:
                            # 发送心跳包
                            yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"
                except Exception as e:
                    self.logger.error(f"群组 {group_id} SSE连接错误: {e}")
                finally:
                    # 清理资源
                    if group_id in self.group_queues and client_id in self.group_queues[group_id]:
                        del self.group_queues[group_id][client_id]
                        if not self.group_queues[group_id]:
                            del self.group_queues[group_id]
            
            return StreamingResponse(event_generator(), media_type="text/event-stream")
        
        # 注册群组成员管理路由
        @self.app.post("/group/{group_id}/members")
        async def manage_group_members(group_id: str, request: Request):
            data = await request.json()
            action = data.get("action")
            target_did = data.get("did")
            req_did = request.query_params.get("req_did")
            if req_did.find("%3A") == -1:
                parts = req_did.split(":", 3)  # 只分割前 3 个
                req_did = ":".join(parts[:2]) + "%3A" + ":".join(parts[2:])
                
            
            if not all([action, target_did, req_did]):
                return {"error": "缺少必要参数"}
            
            # 初始化群组成员列表
            if group_id not in self.group_members:
                self.group_members[group_id] = set()
            
            # 如果是空群组，第一个加入的人自动成为成员
            if not self.group_members[group_id]:
                if action == "add":
                    self.group_members[group_id].add(req_did) # 添加请求者为首个成员
                    if target_did != req_did:  # 如果目标不是请求者自己，也添加目标
                        self.group_members[group_id].add(target_did)
                        return {"status": "success", "message": "成功创建群组并添加了创建者和创建者邀请的成员"}
                    return {"status": "success", "message": "成功创建群组并添加创建者为首个成员"}
                return {"error": "群组不存在"}
            
            # 验证请求者是否是群组成员
            if req_did not in self.group_members[group_id]:
                return {"error": "无权管理群组成员"}
            
            if action == "add":
                self.group_members[group_id].add(target_did)
                return {"status": "success", "message": "成功添加成员"}
            elif action == "remove":
                if target_did in self.group_members[group_id]:
                    self.group_members[group_id].remove(target_did)
                    return {"status": "success", "message": "成功移除成员"}
                return {"error": "成员不存在"}
            else:
                return {"error": "不支持的操作"}
            
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

        host, port = self.get_did_host_port_from_did(agent1.id)   

        def run_server():
            # 保存uvicorn服务器实例以便后续关闭
            config = uvicorn.Config(self.app, host=host, port=int(port))
            self.uvicorn_server = uvicorn.Server(config)
            self.uvicorn_server.run()
        
        # 在新线程中启动服务器
        self.server_thread = threading.Thread(target=run_server)
        self.server_thread.daemon = True  # 显式设置为守护线程
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
        
        # 优雅关闭uvicorn服务器
        if hasattr(self, 'uvicorn_server'):
            self.uvicorn_server.should_exit = True
            self.logger.info("已发送服务器关闭信号")
        
        self.server_running = False
        self.logger.info("服务器已停止")
        
        return True
        
    def __del__(self):
        """确保在对象销毁时释放资源"""
        try:
            if self.server_running:
                self.stop_server()
        except Exception as e:
            # 避免在解释器关闭时出现问题
            pass
     
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



# 其实应该转移到 anp_open_sdk  anp_sdk_utils
    @staticmethod
    def get_did_host_port_from_did(did: str) -> tuple[str, int]:
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
            return "localhost", 9527
        return host, int(port)

