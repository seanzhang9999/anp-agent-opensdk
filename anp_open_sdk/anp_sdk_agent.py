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
import asyncio
import inspect
import json
import os
from datetime import datetime
from typing import Dict, Any, Callable, List

import nest_asyncio
from fastapi import FastAPI, Request
import logging
logger = logging.getLogger(__name__)
from starlette.responses import JSONResponse


from anp_open_sdk.config import get_global_config
from anp_open_sdk.service.publisher.anp_sdk_publisher_mail_backend import EnhancedMailManager
from anp_open_sdk.auth.did_auth_wba import parse_wba_did_host_port
from anp_open_sdk.contact_manager import ContactManager
from anp_open_sdk.sdk_mode import SdkMode

class RemoteAgent:
    def __init__(self, id: str, name: str = None, host: str = None, port: int = None, **kwargs):
        self.id = id
        self.name = name
        self.host = host
        self.port = port
        if self.id and (self.host is None or self.port is None):
            self.host, self.port = parse_wba_did_host_port(self.id)
        self.extra = kwargs

    def to_dict(self):
        return {
            "did": self.id,
            "name": self.name,
            "host": self.host,
            "port": self.port,
            **self.extra
        }

class LocalAgent:
    """本地智能体，代表当前用户的DID身份"""
    api_config: List[Dict[str, Any]]  # 用于多智能体加载时 从agent_mappings.yaml加载api相关扩展描述

    def __init__(self, user_data, name: str = "未命名", agent_type: str = "personal"):
        """初始化本地智能体
        
        Args:
            user_data: 用户数据对象
            agent_type: 智能体类型，"personal"或"service"
        """
        self.user_data = user_data
        user_dir = self.user_data.user_dir

        if name == "未命名":
            if self.user_data.name  is not None:
                self.name = self.user_data.name
            else:
                self.name = f"未命名智能体{self.user_data.did}"
        self.id = self.user_data.did
        self.name = name
        self.user_dir = user_dir
        self.agent_type = agent_type
        config = get_global_config()
        self.key_id = config.anp_sdk.user_did_key_id

        self.did_document_path = self.user_data.did_doc_path
        self.private_key_path = self.user_data.did_private_key_file_path
        self.jwt_private_key_path = self.user_data.jwt_private_key_file_path
        self.jwt_public_key_path = self.user_data.jwt_public_key_file_path

        self.logger = logger
        self._ws_connections = {}
        self._sse_clients = set()
        # 托管DID标识
        self.is_hosted_did = self._check_if_hosted_did()
        self.parent_did = self._get_parent_did() if self.is_hosted_did else None
        self.hosted_info = self._get_hosted_info() if self.is_hosted_did else None
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

        # 群组相关属性
        self.group_queues = {}  # 群组消息队列: {group_id: {client_id: Queue}}
        self.group_members = {}  # 群组成员列表: {group_id: set(did)}

        # 新增：联系人管理器
        self.contact_manager = ContactManager(self.user_data)

    @classmethod
    def from_did(cls, did: str, name: str = "未命名", agent_type: str = "personal"):
        from anp_open_sdk.anp_sdk_user_data import LocalUserDataManager
        user_data_manager = LocalUserDataManager()
        user_data_manager.load_users()
        user_data = user_data_manager.get_user_data(did)
        if name == "未命名":
            name = user_data.name
        if not user_data:
            raise ValueError(f"未找到 DID 为 {did} 的用户数据")
        return cls(user_data, name, agent_type)

    @classmethod
    def from_name(cls, name: str, agent_type: str = "personal"):
        from anp_open_sdk.anp_sdk_user_data import LocalUserDataManager
        user_data_manager = LocalUserDataManager()
        user_data_manager.load_users()
        user_data = user_data_manager.get_user_data_by_name(name)
        if not user_data:
            logger.error(f"未找到 name 为 {name} 的用户数据")
            return cls( None, name, agent_type)
        return cls(user_data, name, agent_type)

    def __del__(self):
        """确保在对象销毁时释放资源"""
        try:
            for ws in self._ws_connections.values():
                self.logger.debug(f"LocalAgent {self.id} 销毁时存在未关闭的WebSocket连接")
            self._ws_connections.clear()
            self._sse_clients.clear()
            self.logger.debug(f"LocalAgent {self.id} 资源已释放")
        except Exception:
            pass
                
    def get_host_dids(self):
        """获取用户目录"""
        return self.user_dir

    # 支持装饰器和函数式注册API
    def expose_api(self, path: str, func: Callable = None, methods=None):
        methods = methods or ["GET", "POST"]
        if func is None:
            def decorator(f):
                self.api_routes[path] = f
                api_info = {
                    "path": f"/agent/api/{self.id}{path}",
                    "methods": methods,
                    "summary": f.__doc__ or f"{self.name}的{path}接口",
                    "agent_id": self.id,
                    "agent_name": self.name
                }
                from anp_open_sdk.anp_sdk import ANPSDK
                if hasattr(ANPSDK, 'instance') and ANPSDK.instance:
                    if self.id not in ANPSDK.instance.api_registry:
                        ANPSDK.instance.api_registry[self.id] = []
                    ANPSDK.instance.api_registry[self.id].append(api_info)
                    logger.debug(f"注册 API: {api_info}")
                return f
            return decorator
        else:
            self.api_routes[path] = func
            api_info = {
                "path": f"/agent/api/{self.id}{path}",
                "methods": methods,
                "summary": func.__doc__ or f"{self.name}的{path}接口",
                "agent_id": self.id,
                "agent_name": self.name
            }
            from anp_open_sdk.anp_sdk import ANPSDK
            if hasattr(ANPSDK, 'instance') and ANPSDK.instance:
                if self.id not in ANPSDK.instance.api_registry:
                    ANPSDK.instance.api_registry[self.id] = []
                ANPSDK.instance.api_registry[self.id].append(api_info)
                logger.debug(f"注册 API: {api_info}")
            return func

    def register_message_handler(self, msg_type: str, func: Callable = None):
        if func is None:
            def decorator(f):
                self.message_handlers[msg_type] = f
                return f
            return decorator
        else:
            self.message_handlers[msg_type] = func
            return func

    def register_group_event_handler(self, handler: Callable, group_id: str = None, event_type: str = None):
        if group_id is None and event_type is None:
            self._group_global_handlers.append((None, handler))
        elif group_id is None:
            self._group_global_handlers.append((event_type, handler))
        else:
            key = (group_id, event_type)
            self._group_event_handlers.setdefault(key, []).append(handler)

    def _get_group_event_handlers(self, group_id: str, event_type: str):
        handlers = []
        for et, h in self._group_global_handlers:
            if et is None or et == event_type:
                handlers.append(h)
        for (gid, et), hs in self._group_event_handlers.items():
            if gid == group_id and (et is None or et == event_type):
                handlers.extend(hs)
        return handlers

    async def _dispatch_group_event(self, group_id: str, event_type: str, event_data: dict):
        handlers = self._get_group_event_handlers(group_id, event_type)
        for handler in handlers:
            try:
                ret = handler(group_id, event_type, event_data)
                if inspect.isawaitable(ret):
                    await ret
            except Exception as e:
                self.logger.error(f"群事件处理器出错: {e}")

    async def handle_request(self, req_did: str, request_data: Dict[str, Any], request: Request):
        req_type = request_data.get("type")
        if req_type in ("group_message", "group_connect", "group_members"):
            handler = self.message_handlers.get(req_type)
            if handler:
                try:
                    nest_asyncio.apply()
                    if asyncio.iscoroutinefunction(handler):
                        loop = asyncio.get_event_loop()
                        if loop.is_running():
                            future = asyncio.ensure_future(handler(request_data))
                            return loop.run_until_complete(future)
                        else:
                            return loop.run_until_complete(handler(request_data))
                    else:
                        result = handler(request_data)
                    if isinstance(result, dict) and "anp_result" in result:
                        return result
                    return {"anp_result": result}
                except Exception as e:
                    self.logger.error(f"Group message handling error: {e}")
                    return {"anp_result": {"status": "error", "message": str(e)}}
            else:
                return {"anp_result": {"status": "error", "message": f"No handler for group type: {req_type}"}}
        if req_type == "api_call":
            api_path = request_data.get("path")
            handler = self.api_routes.get(api_path)
            if handler:
                try:
                    result = await handler(request_data, request)
                    if isinstance(result, dict):
                        status_code = result.pop('status_code', 200)
                        return JSONResponse(
                            status_code=status_code,
                            content=result
                        )
                    else:
                        return result
                except Exception as e:
                    self.logger.debug(
                        f"发送到 handler的请求数据{request_data}\n"                        
                        f"完整请求为 url: {request.url} \n"
                        f"body: {await request.body()}")
                    self.logger.error(f"API调用错误: {e}")
                    return JSONResponse(
                        status_code=500,
                        content={"status": "error", "error_message": str(e)}
                    )
            else:
                return JSONResponse(
                    status_code=404,
                    content={"status": "error", "message": f"未找到API: {api_path}"}
                )
        elif req_type == "message":
            msg_type = request_data.get("message_type", "*")
            handler = self.message_handlers.get(msg_type) or self.message_handlers.get("*")
            if handler:
                try:
                    result = await handler(request_data)
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


    def get_token_to_remote(self, remote_did, hosted_did=None):
        return self.contact_manager.get_token_to_remote(remote_did)

    def store_token_from_remote(self, remote_did, token, hosted_did=None):
        return self.contact_manager.store_token_from_remote(remote_did, token)

    def get_token_from_remote(self, remote_did, hosted_did=None):
        return self.contact_manager.get_token_from_remote(remote_did)

    def revoke_token_to_remote(self, remote_did, hosted_did=None):
        return self.contact_manager.revoke_token_to_remote(remote_did)

    def add_contact(self, remote_agent):
        contact = remote_agent if isinstance(remote_agent, dict) else remote_agent.to_dict() if hasattr(remote_agent, "to_dict") else {
            "did": remote_agent.id,
            "host": getattr(remote_agent, "host", None),
            "port": getattr(remote_agent, "port", None),
            "name": getattr(remote_agent, "name", None)
        }
        self.contact_manager.add_contact(contact)

    def get_contact(self, remote_did: str):
        return self.contact_manager.get_contact(remote_did)

    def list_contacts(self):
        return self.contact_manager.list_contacts()

    async def check_hosted_did(self):
        try:
            import re
            import json
            from anp_open_sdk.config import get_global_config
            config = get_global_config()
            use_local = config.mail.use_local_backend
            logger.debug(f"注册邮箱检查前初始化，使用本地文件邮件后端参数设置:{use_local}")
            mail_manager = EnhancedMailManager(use_local_backend=use_local)
            responses = mail_manager.get_unread_hosted_responses()
            if not responses:
                return "没有找到匹配的托管 DID 激活邮件"
            count = 0
            for response in responses:
                try:
                    body = response.get('content', '')
                    message_id = response.get('message_id')
                    try:
                        if isinstance(body, str):
                            did_document = json.loads(body)
                        else:
                            did_document = body
                    except Exception as e:
                        logger.debug(f"无法解析 did_document: {e}")
                        continue
                    did_id = did_document.get('id', '')
                    m = re.search(r'did:wba:([^:]+)%3A(\d+):', did_id)
                    if not m:
                        logger.debug(f"无法从id中提取host:port: {did_id}")
                        continue
                    host = m.group(1)
                    port = m.group(2)
                    success, hosted_dir_name = self._create_hosted_did_folder(host, port, did_document)
                    if success:
                        mail_manager.mark_message_as_read(message_id)
                        logger.debug(f"已创建托管DID文件夹: {hosted_dir_name}")
                        count += 1
                    else:
                        logger.error(f"创建托管DID文件夹失败: {host}:{port}")
                except Exception as e:
                    logger.error(f"处理邮件时出错: {e}")
            if count > 0:
                return f"成功处理{count}封托管DID邮件"
            else:
                return "未能成功处理任何托管DID邮件"
        except Exception as e:
            logger.error(f"检查托管DID时发生错误: {e}")
            return f"检查托管DID时发生错误: {e}"

    async def register_hosted_did(self, sdk):
        try:
            from anp_open_sdk.service.publisher.anp_sdk_publisher_mail_backend import EnhancedMailManager
            user_data_manager = sdk.user_data_manager
            user_data = user_data_manager.get_user_data(self.id)
            did_document = user_data.did_doc
            if did_document is None:
                raise ValueError("当前 LocalAgent 未包含 did_document")
            from anp_open_sdk.config import get_global_config
            config = get_global_config()
            use_local = config.mail.use_local_backend
            logger.debug(f"注册邮箱检查前初始化，使用本地文件邮件后端参数设置:{use_local}")
            mail_manager = EnhancedMailManager(use_local_backend=use_local)
            register_email = os.environ.get('REGISTER_MAIL_USER')
            success = mail_manager.send_hosted_did_request(did_document, register_email)
            if success:
                logger.debug("托管DID申请邮件已发送")
                return True
            else:
                logger.error("发送托管DID申请邮件失败")
                return False
        except Exception as e:
            logger.error(f"注册托管DID失败: {e}")
            return False

    def _check_if_hosted_did(self) -> bool:
        from pathlib import Path
        user_dir_name = Path(self.user_dir).name
        return user_dir_name.startswith('user_hosted_')

    def _get_parent_did(self) -> str:
        import yaml
        from pathlib import Path
        config_path = Path(self.user_dir) / 'agent_cfg.yaml'
        if config_path.exists():
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)
                    hosted_config = config.get('hosted_config', {})
                    return hosted_config.get('parent_did')
            except Exception as e:
                logger.warning(f"读取托管配置失败: {e}")
        return None

    def _get_hosted_info(self) -> dict:
        from pathlib import Path
        user_dir_name = Path(self.user_dir).name
        if user_dir_name.startswith('user_hosted_'):
            parts = user_dir_name[12:].rsplit('_', 2)
            if len(parts) >= 2:
                if len(parts) == 3:
                    host, port, did_suffix = parts
                    return {'host': host, 'port': port, 'did_suffix': did_suffix}
                else:
                    host, port = parts
                    return {'host': host, 'port': port}
        return None

    def _create_hosted_did_folder(self, host: str, port: str, did_document: dict) -> tuple[bool, str]:
        import shutil
        import yaml
        from pathlib import Path
        try:
            did_id = did_document.get('id', '')
            import re
            pattern = r"did:wba:[^:]+:[^:]+:[^:]+:([a-zA-Z0-9]{16})"
            match = re.search(pattern, did_id)
            if match:
                did_suffix = match.group(1)
            else:
                did_suffix = "无法匹配随机数"
            original_user_dir = Path(self.user_dir)
            parent_dir = original_user_dir.parent
            hosted_dir_name = f"user_hosted_{host}_{port}_{did_suffix}"
            hosted_dir = parent_dir / hosted_dir_name
            hosted_dir.mkdir(parents=True, exist_ok=True)
            key_files = ['key-1_private.pem', 'key-1_public.pem', 'private_key.pem', 'public_key.pem']
            for key_file in key_files:
                src_path = original_user_dir / key_file
                dst_path = hosted_dir / key_file
                if src_path.exists():
                    shutil.copy2(src_path, dst_path)
                    logger.debug(f"已复制密钥文件: {key_file}")
                else:
                    logger.warning(f"源密钥文件不存在: {src_path}")
            did_doc_path = hosted_dir / 'did_document.json'
            with open(did_doc_path, 'w', encoding='utf-8') as f:
                json.dump(did_document, f, ensure_ascii=False, indent=2)
            hosted_config = {
                'did': did_document.get('id', ''),
                'unique_id': did_suffix,
                'hosted_config': {
                    'parent_did': self.id,
                    'host': host,
                    'port': int(port),
                    'created_at': datetime.now().isoformat(),
                    'purpose': f"对外托管服务 - {host}:{port}"
                }
            }
            config_path = hosted_dir / 'agent_cfg.yaml'
            with open(config_path, 'w', encoding='utf-8') as f:
                yaml.dump(hosted_config, f, default_flow_style=False, allow_unicode=True)
            logger.debug(f"托管DID文件夹创建成功: {hosted_dir}")
            return True, hosted_dir_name
        except Exception as e:
            logger.error(f"创建托管DID文件夹失败: {e}")
            return False, ''

    def start(self, mode: SdkMode, ws_proxy_url=None, host="0.0.0.0", port=8000):
        if mode == SdkMode.AGENT_SELF_SERVICE:
            self._start_self_service(host, port)
        elif mode == SdkMode.AGENT_WS_PROXY_CLIENT:
            self._start_self_service(host, port)
            asyncio.create_task(self._start_ws_proxy_client(ws_proxy_url))
        # 其他模式由ANPSDK主导

    def _start_self_service(self, host, port):
        self.app = FastAPI(title=f"{self.name} LocalAgent", description="LocalAgent Self-Service API", version="1.0.0")
        self._register_self_routes()
        import uvicorn
        uvicorn.run(self.app, host=host, port=port)

    def _register_self_routes(self):
        from fastapi import Request

        @self.app.post("/agent/api/{agent_id}/{path:path}")
        async def agent_api(agent_id: str, path: str, request: Request):
            if agent_id != self.id:
                return JSONResponse(status_code=404, content={"status": "error", "message": "Agent ID not found"})
            request_data = await request.json()
            return await self.handle_request(agent_id, request_data, request)

        # 可扩展更多自服务API

    async def _start_ws_proxy_client(self, ws_proxy_url):
        import websockets
        while True:
            try:
                async with websockets.connect(ws_proxy_url) as ws:
                    await self._ws_proxy_loop(ws)
            except Exception as e:
                self.logger.error(f"WebSocket代理连接失败: {e}")
                await asyncio.sleep(5)

    async def _ws_proxy_loop(self, ws):
        await ws.send(json.dumps({"type": "register", "did": self.id}))
        async for msg in ws:
            data = json.loads(msg)
            # 处理来自中心的请求
            # 这里可以根据data内容调用self.handle_request等
            # 例如:
            req_type = data.get("type")
            if req_type == "api_call":
                # 伪造一个Request对象
                class DummyRequest:
                    def __init__(self, json_data):
                        self._json = json_data
                    async def json(self):
                        return self._json
                response = await self.handle_request(self.id, data, DummyRequest(data))
                await ws.send(json.dumps({"type": "response", "data": response}))
            # 可扩展其他消息类型
