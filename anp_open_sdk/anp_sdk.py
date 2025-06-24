# Copyright 2024 ANP Open SDK Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from anp_open_sdk.anp_sdk_user_data import LocalUserDataManager
import urllib.parse
import os
import time
import asyncio
import json
from datetime import datetime
from typing import Dict, Any, Optional, List
from fastapi.middleware.cors import CORSMiddleware
from anp_open_sdk.auth.auth_server import auth_middleware
from anp_open_sdk.service.router import router_did, router_publisher, router_auth
from anp_open_sdk.config import get_global_config
from fastapi import Request, WebSocket, WebSocketDisconnect, FastAPI
from fastapi.responses import StreamingResponse
from anp_open_sdk.anp_sdk_agent import LocalAgent
from anp_open_sdk.service.interaction.anp_sdk_group_runner import GroupManager, GroupRunner, Message, MessageType, Agent
from anp_open_sdk.sdk_mode import SdkMode

# 在模块顶部获取 logger，这是标准做法
import logging
logger = logging.getLogger(__name__)

class ANPSDK:
    """ANP SDK主类，支持多种运行模式"""
    
    instance = None
    _instances = {}

    @classmethod
    def get_instance(cls, port):
        if port not in cls._instances:
            cls._instances[port] = cls(SdkMode.MULTI_AGENT_ROUTER, ws_port=port)
        return cls._instances[port]
    
    def __new__(cls, *args, **kwargs):
        if cls.instance is None:
            cls.instance = super().__new__(cls)
        return cls.instance
    
    def __init__(self, mode = SdkMode.MULTI_AGENT_ROUTER, agents=None, ws_host="0.0.0.0", ws_port=9527, **kwargs):
        if hasattr(self, 'initialized'):
            return
        self.mode = mode
        self.agents = agents or []
        self.port = ws_port
        self.server_running = False
        self.api_routes = {}
        self.api_registry = {}
        self.message_handlers = {}
        self.ws_connections = {}
        self.sse_clients = set()
        self.logger = logger
        self.proxy_client = None
        self.proxy_mode = False
        self.proxy_task = None
        self.group_manager = GroupManager(self)
        self.user_data_manager = LocalUserDataManager()
        self.agent = None
        self.initialized = True
        config = get_global_config()
        self.debug_mode = config.anp_sdk.debug_mode

        if self.debug_mode:
            self.app = FastAPI(
                title="ANP SDK Server in DebugMode",
                description="ANP SDK Server in DebugMode",
                version="0.1.0",
                reload=False,
                docs_url="/docs",
                redoc_url="/redoc"
                    )
        else:
            self.app = FastAPI(
                title="ANP SDK Server",
                description="ANP SDK Server",
                version="0.1.0",
                reload=True,
                docs_url=None,
                redoc_url=None
                    )
        self.app.state.sdk = self

        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        @self.app.middleware("http")
        async def auth_middleware_wrapper(request, call_next):
            return await auth_middleware(request, call_next)

        from anp_open_sdk.service.router.router_agent import AgentRouter
        self.router = AgentRouter()
        if mode == SdkMode.MULTI_AGENT_ROUTER:
            for agent in self.agents:
                self.register_agent(agent)
            self._register_default_routes()
        elif mode == SdkMode.DID_REG_PUB_SERVER:
            self._register_default_routes()
        elif mode == SdkMode.SDK_WS_PROXY_SERVER:
            self._register_default_routes()
            self._register_ws_proxy_server(ws_host, ws_port)
        # 其他模式由LocalAgent主导

        @self.app.on_event("startup")
        async def generate_openapi_yaml():
            self.save_openapi_yaml()


    def _register_ws_proxy_server(self, ws_host, ws_port):
        self.ws_clients = {}

        @self.app.websocket("/ws/agent")
        async def ws_agent_endpoint(websocket: WebSocket):
            await websocket.accept()
            client_id = id(websocket)
            self.ws_clients[client_id] = websocket
            try:
                while True:
                    msg = await websocket.receive_text()
                    data = json.loads(msg)
                    # 处理代理注册、DID发布、API代理等
            except Exception as e:
                    self.logger.error(f"WebSocket客户端断开: {e}")
            finally:
                    self.ws_clients.pop(client_id, None)

    def register_group_runner(self, group_id: str, runner_class: type[GroupRunner],
                             url_pattern: Optional[str] = None):
        self.group_manager.register_runner(group_id, runner_class, url_pattern)

    def unregister_group_runner(self, group_id: str):
        self.group_manager.unregister_runner(group_id)

    def get_group_runner(self, group_id: str) -> Optional[GroupRunner]:
        return self.group_manager.get_runner(group_id)

    def list_groups(self) -> List[str]:
        return self.group_manager.list_groups()

    async def check_did_host_request(self):
        from anp_open_sdk.service.publisher.anp_sdk_publisher_mail_backend import EnhancedMailManager
        from anp_open_sdk.service.publisher.anp_sdk_publisher import DIDManager
        try:
            config = get_global_config()
            use_local = config.mail.use_local_backend
            logger.debug(f"管理邮箱检查前初始化，使用本地文件邮件后端参数设置:{use_local}")
            mail_manager = EnhancedMailManager(use_local_backend=use_local)
            did_manager = DIDManager()
            
            did_requests = mail_manager.get_unread_did_requests()
            if not did_requests:
                return "没有新的DID托管请求"
            
            result = "开始处理DID托管请求\n"
            for request in did_requests:
                did_document = request['content']
                from_address = request['from_address']
                message_id = request['message_id']
                
                parsed_json = json.loads(did_document)
                did_document_dict = dict(parsed_json)

                if did_manager.is_duplicate_did(did_document):
                    mail_manager.send_reply_email(
                        from_address,
                        "DID已申请",
                        "重复的DID申请，请联系管理员"
                    )
                    mail_manager.mark_message_as_read(message_id)
                    result += f"{from_address}的DID {did_document_dict.get('id')} 已申请，退回\n"
                    continue
                
                success, new_did_doc, error = did_manager.store_did_document(did_document_dict)
                if success:
                    mail_manager.send_reply_email(
                        from_address,
                        "ANP HOSTED DID RESPONSED",
                        new_did_doc)
                    
                    result += f"{from_address}的DID {new_did_doc['id']} 已保存\n"
                else:
                    mail_manager.send_reply_email(
                        from_address,
                        "DID托管申请失败",
                        f"处理DID文档时发生错误: {error}"
                    )
                    result += f"{from_address}的DID处理失败: {error}\n"
                
                mail_manager.mark_message_as_read(message_id)
            
            return result
        except Exception as e:
            error_msg = f"处理DID托管请求时发生错误: {e}"
            logger.error(error_msg)
            return error_msg

    def register_agent(self, agent: LocalAgent):
        self.router.register_agent(agent)
        self.logger.debug(f"已注册智能体到SDK: {agent.id}")


    
    def save_openapi_yaml(self):
        import yaml
        import os
        
        docs_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'anp_open_sdk', 'anp_users')
        os.makedirs(docs_dir, exist_ok=True)
        
        for agent_id, agent in self.router.local_agents.items():
            if agent.is_hosted_did:
                continue
            openapi_spec = {
                "openapi": "3.0.0",
                "info": {
                    "title": f"Agent {agent_id} API Documentation",
                    "version": "1.0.0"
                },
                "paths": {}
            }
            if hasattr(self, 'api_registry') and self.api_registry:
                for agent_api_id, apis in self.api_registry.items():
                    if agent_api_id != agent_id:
                        continue
                    for api in apis:
                        api_path = api.get('path')
                        api_methods = api.get('methods', ['GET'])
                        api_summary = api.get('summary', '')
                        for method in api_methods:
                            method_lower = method.lower()
                            if method_lower == "head":
                                continue
                            if api_path.startswith(f"/agent/api/{agent_id}"):
                                openapi_path = api_path
                            else:
                                openapi_path = f"/agent/api/{agent_id}{api_path if api_path.startswith('/') else '/' + api_path}"
                            if openapi_path not in openapi_spec["paths"]:
                                openapi_spec["paths"][openapi_path] = {}
                            parameters = [
                                {
                                    "name": "req_did",
                                    "in": "query",
                                    "required": False,
                                    "schema": {"type": "string"},
                                    "default": "demo_caller"
                                }
                            ]
                            operation_id = f"{method_lower}_{openapi_path.replace('/', '_').replace('{', '').replace('}', '')}"
                            responses = {
                                "200": {
                                    "description": "成功响应",
                                    "content": {
                                        "application/json": {
                                            "schema": {"type": "object"}
                                        }
                                    }
                                }
                            }
                            request_body = None
                            if method_lower == "post":
                                request_body = {
                                    "required": True,
                                    "content": {
                                        "application/json": {
                                            "schema": {"type": "object"}
                                        }
                                    }
                                }
                            openapi_spec["paths"][openapi_path][method_lower] = {
                                "summary": api_summary,
                                "operationId": operation_id,
                                "parameters": parameters,
                                "responses": responses
                            }
                            if request_body:
                                openapi_spec["paths"][openapi_path][method_lower]["requestBody"] = request_body

            for route in self.app.routes:
                if hasattr(route, "methods") and hasattr(route, "path"):
                    methods = route.methods
                    path = route.path
                    if path.startswith("/agent/api/"):
                        continue
                    if not (path.startswith("/agent/message/") or path.startswith("/agent/group/") or path.startswith("/wba/")):
                        continue
                    for method in methods:
                        method_lower = method.lower()
                        if method_lower == "head":
                            continue
                        if path not in openapi_spec["paths"]:
                            openapi_spec["paths"][path] = {}
                        parameters = []
                        if "{group_id}" in path:
                            parameters.append({
                                "name": "group_id",
                                "in": "path",
                                "required": True,
                                "schema": {"type": "string"}
                            })
                        parameters.append({
                            "name": "req_did",
                            "in": "query",
                            "required": False,
                            "schema": {"type": "string"},
                            "default": "demo_caller"
                        })
                        summary = getattr(route, "summary", None) or getattr(route, "name", "")
                        operation_id = f"{method_lower}_{path.replace('/', '_').replace('{', '').replace('}', '')}"
                        responses = {
                            "200": {
                                "description": "成功响应",
                                "content": {
                                    "application/json": {
                                        "schema": {"type": "object"}
                                    }
                                }
                            }
                        }
                        if path.endswith("/connect") and method_lower == "get":
                            responses["200"]["content"] = {
                                "text/event-stream": {
                                    "schema": {"type": "string"}
                                }
                            }
                        request_body = None
                        if method_lower == "post":
                            request_body = {
                                "required": True,
                                "content": {
                                    "application/json": {
                                        "schema": {"type": "object"}
                                    }
                                }
                            }
                        openapi_spec["paths"][path][method_lower] = {
                            "summary": summary,
                            "operationId": operation_id,
                            "parameters": parameters,
                            "responses": responses
                        }
                        if request_body:
                            openapi_spec["paths"][path][method_lower]["requestBody"] = request_body

            user_id = agent_id.split(':')[-1]
            user_dir = f"user_{user_id}"
            config = get_global_config()

            user_path = os.path.join(config.anp_sdk.user_did_path, user_dir)
            safe_agent_id = urllib.parse.quote(agent_id, safe="")

            if os.path.exists(user_path):
                yaml_path = os.path.join(user_path, f"openapi_{safe_agent_id}.yaml")
                with open(yaml_path, 'w', encoding='utf-8') as f:
                    yaml.dump(openapi_spec, f, allow_unicode=True, sort_keys=False)
            else:
                yaml_path = os.path.join(docs_dir, f"openapi_{safe_agent_id}.yaml")
                with open(yaml_path, 'w', encoding='utf-8') as f:
                    yaml.dump(openapi_spec, f, allow_unicode=True, sort_keys=False)

    def get_agents(self):
        return self.router.local_agents.values()

    def get_agent(self, did: str):
        return self.router.get_agent(did)

    def _register_default_routes(self):
        self.app.include_router(router_auth.router)
        self.app.include_router(router_did.router)
        self.app.include_router(router_publisher.router)
        @self.app.get("/", tags=["status"])
        async def root():
            return {
                "status": "running",
                "service": "ANP SDK Server",
                "version": "0.1.0",
                "mode": "Server and client",
                "documentation": "/docs"
            }

        @self.app.get("/agent/api/{did}/{subpath:path}")
        async def api_entry_get(did: str, subpath: str, request: Request):
            data = dict(request.query_params)
            req_did = request.query_params.get("req_did", "demo_caller")
            resp_did = did
            data["type"] = "api_call"
            data["path"] = f"/{subpath}"
            result = self.router.route_request(req_did, resp_did, data, request)
            if asyncio.iscoroutine(result):
                result = await result
            return result

        @self.app.post("/agent/api/{did}/{subpath:path}")
        async def api_entry_post(did: str, subpath: str, request: Request):
            try:
                data = await request.json()
                if not data:
                    data = {}
            except Exception:
                data = {}
            req_did = request.query_params.get("req_did", "demo_caller")
            resp_did = did
            data["type"] = "api_call"
            data["path"] = f"/{subpath}"
            result = await self.router.route_request(req_did, resp_did, data, request)
            if asyncio.iscoroutine(result):
                result = await result
            return result

        @self.app.post("/agent/message/{did}/post")
        async def message_entry_post(did: str, request: Request):
            data = await request.json()
            req_did = request.query_params.get("req_did", "demo_caller")
            resp_did = did
            data["type"] = "message"
            result = await self.router.route_request(req_did, resp_did, data, request)
            if asyncio.iscoroutine(result):
                result = await result
            return result

        self.group_queues = {}
        self.group_members = {}
        
        @self.app.post("/agent/group/{did}/{group_id}/join")
        async def join_group(did: str, group_id: str, request: Request):
            data = await request.json()
            req_did = request.query_params.get("req_did", "demo_caller")
            runner = self.group_manager.get_runner(group_id)
            if runner:
                agent = Agent(
                    id=req_did,
                    name=data.get("name", req_did),
                    port=data.get("port", 0),
                    metadata=data.get("metadata", {})
                )
                allowed = await runner.on_agent_join(agent)
                if allowed:
                    runner.agents[req_did] = agent
                    return {"status": "success", "message": "Joined group", "group_id": group_id}
                else:
                    return {"status": "error", "message": "Join request rejected"}
            resp_did = did
            data["type"] = "group_join"
            data["group_id"] = group_id
            data["req_did"] = req_did
            result = await self.router.route_request(req_did, resp_did, data, request)
            if asyncio.iscoroutine(result):
                result = await result
            return result

        @self.app.post("/agent/group/{did}/{group_id}/leave")
        async def leave_group(did: str, group_id: str, request: Request):
            data = await request.json()
            req_did = request.query_params.get("req_did", "demo_caller")
            runner = self.group_manager.get_runner(group_id)
            if runner and req_did in runner.agents:
                agent = runner.agents[req_did]
                await runner.on_agent_leave(agent)
                del runner.agents[req_did]
                return {"status": "success", "message": "Left group"}
            resp_did = did
            data["type"] = "group_leave"
            data["group_id"] = group_id
            data["req_did"] = req_did
            result = await self.router.route_request(req_did, resp_did, data, request)
            if asyncio.iscoroutine(result):
                result = await result
            return result

        @self.app.post("/agent/group/{did}/{group_id}/message")
        async def group_message(did: str, group_id: str, request: Request):
            data = await request.json()
            req_did = request.query_params.get("req_did", "demo_caller")
            runner = self.group_manager.get_runner(group_id)
            if runner:
                message = Message(
                    type=MessageType.TEXT,
                    content=data.get("content"),
                    sender_id=req_did,
                    group_id=group_id,
                    timestamp=time.time(),
                    metadata=data.get("metadata", {})
                )
                if not runner.is_member(req_did):
                    return {"status": "error", "message": "Not a member of this group"}
                response = await runner.on_message(message)
                if response:
                    return {"status": "success", "response": response.to_dict()}
                return {"status": "success"}
            resp_did = did
            data["type"] = "group_message"
            data["group_id"] = group_id
            data["req_did"] = req_did
            result = await self.router.route_request(req_did, resp_did, data, request)
            if asyncio.iscoroutine(result):
                result = await result
            return result

        @self.app.get("/agent/group/{did}/{group_id}/connect")
        async def group_connect(did: str, group_id: str, request: Request):
            req_did = request.query_params.get("req_did", "demo_caller")
            runner = self.group_manager.get_runner(group_id)
            if runner:
                if not runner.is_member(req_did):
                    return {"status": "error", "message": "Not a member of this group"}
                async def event_generator():
                    queue = asyncio.Queue()
                    runner.register_listener(req_did, queue)
                    try:
                        while True:
                            message = await queue.get()
                            yield f"data: {json.dumps(message)}\n\n"
                    except asyncio.CancelledError:
                        runner.unregister_listener(req_did)
                        raise
                return StreamingResponse(event_generator(), media_type="text/event-stream")
            resp_did = did
            data = {"type": "group_connect", "group_id": group_id, "req_did": req_did}
            result = await self.router.route_request(req_did, resp_did, data)
            if result and "event_generator" in result:
                return StreamingResponse(result["event_generator"], media_type="text/event-stream")
            return result

        @self.app.post("/agent/group/{did}/{group_id}/members")
        async def manage_group_members(did: str, group_id: str, request: Request):
            data = await request.json()
            req_did = request.query_params.get("req_did", "demo_caller")
            runner = self.group_manager.get_runner(group_id)
            if runner:
                action = data.get("action", "list")
                if action == "list":
                    members = [agent.to_dict() for agent in runner.get_members()]
                    return {"status": "success", "members": members}
                elif action == "add":
                    agent_id = data.get("agent_id")
                    agent = Agent(
                        id=agent_id,
                        name=data.get("name", agent_id),
                        port=data.get("port", 0),
                        metadata=data.get("metadata", {})
                    )
                    allowed = await runner.on_agent_join(agent)
                    if allowed:
                        runner.agents[agent_id] = agent
                        return {"status": "success", "message": "Member added"}
                    return {"status": "error", "message": "Add member rejected"}
                elif action == "remove":
                    agent_id = data.get("agent_id")
                    success = await runner.remove_member(agent_id)
                    if success:
                        return {"status": "success", "message": "Member removed"}
                    return {"status": "error", "message": "Member not found"}
                else:
                    return {"status": "error", "message": f"Unknown action: {action}"}
            resp_did = did
            data["type"] = "group_members"
            data["group_id"] = group_id
            data["req_did"] = req_did
            result = await self.router.route_request(req_did, resp_did, data, request)
            if asyncio.iscoroutine(result):
                result = await result
            return result

        @self.app.get("/agent/group/{did}/{group_id}/members")
        async def get_group_members(did: str, group_id: str, request: Request):
            req_did = request.query_params.get("req_did", "demo_caller")
            runner = self.group_manager.get_runner(group_id)
            if runner:
                members = [agent.to_dict() for agent in runner.get_members()]
                return {"status": "success", "members": members}
            resp_did = did
            data = {"type": "group_members", "action": "list", "group_id": group_id, "req_did": req_did}
            result = await self.router.route_request(req_did, resp_did, data, request)
            if asyncio.iscoroutine(result):
                result = await result
            return result

        @self.app.get("/agent/groups")
        async def list_groups(request: Request):
            groups = self.list_groups()
            return {"status": "success", "groups": groups}

        @self.app.post("/api/message")
        async def receive_message(request: Request):
            data = await request.json()
            return await self._handle_message(data)

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
                self.logger.debug(f"WebSocket客户端断开连接: {client_id}")
                if client_id in self.ws_connections:
                    del self.ws_connections[client_id]
            except Exception as e:
                self.logger.error(f"WebSocket处理错误: {e}")
                if client_id in self.ws_connections:
                    del self.ws_connections[client_id]

    async def _handle_message(self, message: Dict[str, Any]):
        logger.debug(f"准备处理接收到的消息内容: {message}")
        if "message" in message:
            message = message["message"]
        message_type = message.get("type", "*")
        handler = self.message_handlers.get(message_type) or self.message_handlers.get("*")
        if handler:
            try:
                result = handler(message)
                if asyncio.iscoroutine(result):
                    result = await result
                return result
            except Exception as e:
                self.logger.error(f"消息处理器执行错误: {e}")
                return {"status": "error", "message": str(e)}
        else:
            return {"status": "error", "message": f"未找到处理{message_type}类型消息的处理器"}

    def start_server(self):
        if self.server_running:
            self.logger.warning("服务器已经在运行")
            return True
        if os.name == 'posix' and 'darwin' in os.uname().sysname.lower():
            self.logger.debug("检测到Mac环境，使用特殊启动方式")
        for route_path, route_info in self.api_routes.items():
            func = route_info['func']
            methods = route_info['methods']
            self.app.add_api_route(f"/{route_path}", func, methods=methods)
        import uvicorn
        import threading
        from anp_open_sdk.config import get_global_config

        # 2. 修正配置项的名称
        config = get_global_config()

        port = config.anp_sdk.port
        host = config.anp_sdk.host

        app_instance = self.app

        if not self.debug_mode:
            config = uvicorn.Config(app_instance, host=host, port=port)
            server = uvicorn.Server(config)
            self.uvicorn_server = server

            def run_server():
                import asyncio
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(server.serve())

            server_thread = threading.Thread(target=run_server)
            server_thread.daemon = True
            server_thread.start()
            self.server_running = True
            return server_thread
        else:
            uvicorn.run(app_instance, host=host, port=port)
            self.server_running = True
        return True


    def stop_server(self):
        if not self.server_running:
            return True
        for ws in self.ws_connections.values():
            asyncio.create_task(ws.close())
        self.ws_connections.clear()
        self.sse_clients.clear()
        if hasattr(self, 'uvicorn_server'):
            self.uvicorn_server.should_exit = True
            self.logger.debug("已发送服务器关闭信号")
        self.server_running = False
        self.logger.debug("服务器已停止")
        return True

    def __del__(self):
        try:
            if self.server_running:
                self.stop_server()
        except Exception as e:
            pass

    def call_api(self, target_did: str, api_path: str, params: Dict[str, Any] = None, method: str = "GET"):
        try:
            if hasattr(self, 'enable_local_acceleration') and self.enable_local_acceleration and hasattr(self, 'accelerator') and self.accelerator.is_local_agent(target_did):
                return self.accelerator.call_api(
                    from_did=self.agent.id if self.agent else "unknown",
                    target_did=target_did,
                    api_path=api_path,
                    method=method,
                    data=params,
                    headers={}
                )

            if not self.agent:
                self.logger.error("智能体未初始化")
                return None

            host, port = self.get_did_host_port_from_did(target_did)
            target_url = f"{host}:{port}"
            url = f"http://{target_url}/{api_path}"

            return self.agent.call_api(url, params, method)

        except Exception as e:
            self.logger.error(f"API调用失败: {e}")
            return {"error": str(e)}

    def expose_api(self, route_path: str, methods: List[str] = None):
        if methods is None:
            methods = ["GET"]
        def decorator(func):
            self.api_routes[route_path] = {'func': func, 'methods': methods}
            if self.server_running:
                self.app.add_api_route(f"/{route_path}", func, methods=methods)
            return func
        return decorator

    def register_message_handler(self, message_type: str = None):
        def decorator(func):
            self.message_handlers[message_type or "*"] = func
            return func
        return decorator

    def send_message(self, target_did: str, message: str, message_type: str = "text") -> bool:
        try:
            if hasattr(self, 'enable_local_acceleration') and self.enable_local_acceleration and hasattr(self, 'accelerator') and self.accelerator.is_local_agent(target_did):
                return self.accelerator.send_message(
                    from_did=self.agent.id if self.agent else "unknown",
                    target_did=target_did,
                    message=message,
                    message_type=message_type
                )
            target_agent = self.router.get_agent(target_did)
            if not target_agent:
                self.logger.error(f"未找到目标智能体: {target_did}")
                return False
            message_data = {
                "from_did": self.agent.id if self.agent else "unknown",
                "to_did": target_did,
                "content": message,
                "type": message_type,
                "timestamp": datetime.now().isoformat()
            }
            success = target_agent.receive_message(message_data)
            if success:
                self.logger.debug(f"消息已发送到 {target_did}: {message[:50]}...")
            else:
                self.logger.error(f"消息发送失败到 {target_did}")
            return success

        except Exception as e:
            self.logger.error(f"发送消息失败: {e}")
            return False

    async def broadcast_message(self, message: Dict[str, Any]):
        for ws in self.ws_connections.values():
            try:
                await ws.send_json(message)
            except Exception as e:
                self.logger.error(f"WebSocket广播失败: {e}")
        self.logger.debug(f"向{len(self.sse_clients)}个SSE客户端广播消息")

    def __enter__(self):
        self.start_server()
        return self

    async def __aenter__(self):
        self.start_server()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop_server()

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.stop_server()

    async def _handle_api_call(self, req_did: str, resp_did: str, api_path: str, method: str, params: Dict[str, Any]):
        if resp_did != self.agent.id:
            return {"status": "error", "message": f"未找到智能体: {resp_did}"}
        api_key = f"{method.lower()}:{api_path}"
        if api_key in self.api_routes:
            handler = self.api_routes[api_key]
            try:
                result = await handler(req_did=req_did, **params)
                return result
            except Exception as e:
                self.logger.error(f"API调用错误: {e}")
                return {"status": "error", "message": str(e)}
        else:
            return {"status": "error", "message": f"未找到API: {api_path} [{method}]"}

    @staticmethod
    def get_did_host_port_from_did(did: str) -> tuple[str, int]:
        host, port = None, None
        if did.startswith('did:wba:'):
            try:
                did_parts = did.split(':')
                if len(did_parts) > 2:
                    host_port = did_parts[2]
                    if '%3A' in host_port:
                        host, port = host_port.split('%3A')
                    else:
                        host = did_parts[2]
                        port = did_parts[3]
                        if port is not int:
                            port = 80
            except Exception as e:
                logger.debug(f"解析did失败: {did}, 错误: {e}")
        if not host or not port:
            return "localhost", 9527
        return host, int(port)

    def unregister_agent(self, agent_id: str):
        try:
            if agent_id not in self.router.local_agents:
                self.logger.warning(f"Agent {agent_id} not found in the router")
                return False

            agent = self.router.local_agents.pop(agent_id, None)

            if agent_id in self.api_registry:
                del self.api_registry[agent_id]

            for group_id in self.list_groups():
                runner = self.get_group_runner(group_id)
                if runner and runner.is_member(agent_id):
                    runner.remove_member(agent_id)

            self.logger.debug(f"Successfully unregistered agent: {agent_id}")

            if not self.router.local_agents:
                self.logger.debug(f"No agents remaining in the router")

            return True

        except Exception as e:
            self.logger.error(f"Failed to unregister agent {agent_id}: {e}")
            return False
