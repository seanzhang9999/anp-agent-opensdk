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
from math import lgamma
import os
import urllib.parse
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
import yaml
import pathlib

# 安全中间件
from anp_open_sdk.anp_sdk_utils import get_user_dir_did_doc_by_did
from anp_open_sdk.auth.auth_middleware import auth_middleware
from anp_open_sdk.anp_sdk_utils import path_resolver

# 两个历史遗留路由 用于认证 和 did发布 
from anp_open_sdk.service import router_auth, router_did


# 导入ANP核心组件

from anp_open_sdk.config.dynamic_config import dynamic_config
from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect, Response, FastAPI
from fastapi.responses import StreamingResponse



# 配置日志
from loguru import logger


from anp_open_sdk.agent_types import RemoteAgent

from anp_open_sdk.agent_types import LocalAgent


class LocalUserData:
    """存储单个用户的配置、DID文档和密码文件路径"""
    def __init__(self, folder_name: str, agent_cfg: Dict[str, Any], did_doc: Dict[str, Any], did_doc_path, password_paths: Dict[str, str] , user_folder_path):
        self.folder_name = folder_name
        self.agent_cfg = agent_cfg
        self.did_doc = did_doc
        self.password_paths = password_paths
        self.did = did_doc.get("id")
        self.name = agent_cfg.get("name")
        self.unique_id = agent_cfg.get("unique_id")
        self.user_dir = user_folder_path
        self.did_doc_path=did_doc_path
        self.did_private_key_file_path=password_paths.get("did_private_key_file_path")
        self.did_public_key_file_path=password_paths.get("did_public_key_file_path")
        self.jwt_private_key_file_path=password_paths.get("jwt_private_key_file_path")
        self.jwt_public_key_file_path=password_paths.get("jwt_public_key_file_path")
        self.key_id = dynamic_config.get('anp_sdk.user_did_key_id')


class LocalUserDataManager:
    """管理本地用户数据，加载配置和DID文档"""
    def __init__(self, user_dir: Optional[str] = None):
        self.user_dir = user_dir or dynamic_config.get('anp_sdk.user_did_path')
        self.users: Dict[str, LocalUserData] = {}
        self._load_users()

    def _load_users(self):
        """遍历用户目录，加载每个用户的数据"""
        if not os.path.isdir(self.user_dir):
            logger.warning(f"用户目录不存在: {self.user_dir}")
            return

        for entry in os.scandir(self.user_dir):
            if entry.is_dir() and entry.name.startswith('user_'):
                user_folder_path = entry.path
                folder_name = entry.name
                try:
                    # 读取 agent_cfg.yaml
                    cfg_path = os.path.join(user_folder_path, 'agent_cfg.yaml')
                    agent_cfg = {}
                    if os.path.exists(cfg_path):
                        with open(cfg_path, 'r', encoding='utf-8') as f:
                            agent_cfg = yaml.safe_load(f)

                    # 读取 did_document.json
                    did_doc_path = os.path.join(user_folder_path, 'did_document.json')
                    did_doc = {}
                    if os.path.exists(did_doc_path):
                        with open(did_doc_path, 'r', encoding='utf-8') as f:
                            did_doc = json.load(f)
                    key_id = dynamic_config.get('anp_sdk.user_did_key_id')

                    # 获取密码文件路径
                    did_private_key_file_path = os.path.join(user_folder_path, f"{key_id}_private.pem")
                    did_public_key_file_path = os.path.join(user_folder_path, f"{key_id}_public.pem")
                    jwt_private_key_file_path = os.path.join(user_folder_path, 'private_key.pem')
                    jwt_public_key_file_path = os.path.join(user_folder_path, 'public_key.pem')
                    password_paths = {
                        "did_private_key_file_path": did_private_key_file_path,
                        "did_public_key_file_path": did_public_key_file_path,
                        "jwt_private_key_file_path": jwt_private_key_file_path,
                        "jwt_public_key_file_path": jwt_public_key_file_path
                    }

                    # 创建 LocalUserData 对象并存储
                    if did_doc and agent_cfg:
                         user_data = LocalUserData(folder_name, agent_cfg, did_doc, did_doc_path, password_paths,user_folder_path)
                         self.users[user_data.did] = user_data
                         logger.info(f"加载用户数据成功: {user_data.did}")
                    else:
                         logger.warning(f"跳过加载用户数据 (缺少 agent_cfg.yaml 或 did_document.json): {folder_name}")

                except Exception as e:
                    logger.error(f"加载用户数据失败 ({folder_name}): {e}")

    def get_user_data(self, did: str) -> Optional[LocalUserData]:
        """根据DID获取用户数据"""
        return self.users.get(did)

    def get_all_users(self) -> List[LocalUserData]:
        """获取所有加载的用户数据"""
        return list(self.users.values())

    def get_user_data_by_name(self, name: str) -> Optional[LocalUserData]:
        """根据智能体名称获取用户数据"""
        for user_data in self.users.values():
            if user_data.name == name:
                return user_data
        return None


class ANPSDK:
    """ANP SDK主类，提供简单易用的接口"""
    
    # 单例模式
    instance = None
    _instances = {}

    # 单例模式 并支持多端口分别运行 各端口无需指定 通过注册的agent列表中第一个agent获取agent名字中的port
    @classmethod
    def get_instance(cls, port):
        if port not in cls._instances:
            cls._instances[port] = cls(port)
        return cls._instances[port]
    
    def __new__(cls, *args, **kwargs):
        if cls.instance is None:
            cls.instance = super().__new__(cls)
        return cls.instance
    
    def __init__(self, port: int = None):
        """初始化ANP SDK
        
        Args:
            did: 可选，指定使用的DID，如果不指定则提供选择或创建新DID的功能
            user_dir: 可选，指定用户目录，默认使用配置中的目录
            port: 可选，指定服务器端口，默认使用配置中的端口
        """

        self.port = port
        if not hasattr(self, 'initialized'):
            self.server_running = False
            self.port = port or dynamic_config.get('anp_sdk.user_did_port_1')
            self.agent = None
            self.api_routes = {}
            self.api_registry = {}
            self.message_handlers = {}
            self.ws_connections = {}
            self.sse_clients = set()
            self.initialized = True
        
        debugmode = dynamic_config.get("anp_sdk.debugmode")

        # 绑定 sdk 实例到 app.state，便于全局获取
        self.app = None
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

        # 绑定 sdk 实例到 app.state，便于全局获取
        self.app.state.sdk = self

        # 初始化 LocalUserDataManager
        self.user_data_manager = LocalUserDataManager()

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
        
    async def check_did_host_request(self):
        """
        检查管理邮箱，自动处理 ANP-DID申请开通 邮件并生成托管 DID。
        """
        import imaplib
        import email
        from email.header import decode_header, make_header
        import os, json, random, string, socket
        from pathlib import Path
        import smtplib
        from email.mime.text import MIMEText
        from email.header import Header
        import socks
        from urllib.parse import quote
        from urllib.parse import unquote
        from urllib.parse import urlencode
        
        # 设置 SOCKS5 代理
        socks.setdefaultproxy(socks.PROXY_TYPE_SOCKS5, "127.0.0.1", 1080)
        socks.wrapmodule(imaplib)

        # 读取邮箱配置
        mail_user = os.environ.get('HOSTER_MAIL_USER')
        mail_pass = os.environ.get('HOSTER_MAIL_PASSWORD')
       
        if not (mail_user and mail_pass):
            raise ValueError('请在环境变量中配置 REGISTER_MAIL_USER/GMAIL_USER/GMAIL_APP_PASSWORD')
        
        # 连接Gmail IMAP
        imap = imaplib.IMAP4_SSL('imap.gmail.com')
        imap.login(mail_user, mail_pass)
        imap.select('INBOX')
        subject = "ANP-DID host request"
        
        status, messages = imap.search(None, f'(UNSEEN SUBJECT "{subject}")')
        if status != 'OK':
            imap.logout()
            return 0
        msg_ids = messages[0].split()
        count = 0
        result = "开始处理"
        for num in msg_ids:
            status, data = imap.fetch(num, '(RFC822)')
            if status != 'OK':
                continue
            msg = email.message_from_bytes(data[0][1])
            # 解析正文
            body = None
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == 'text/plain':
                        charset = part.get_content_charset() or 'utf-8'
                        body = part.get_payload(decode=True).decode(charset)
                        break
            else:
                charset = msg.get_content_charset() or 'utf-8'
                body = msg.get_payload(decode=True).decode(charset)
            if not body:
                continue
            try:
                did_document = json.loads(body)
            except Exception as e:
                logger.error(f"无法解析 did_document: {e}")
                continue
            # 检查是否已存在同 id 的 did_document_request.json
            import secrets
            hosted_dir = Path(os.environ.get('ANP_USER_HOSTED_PATH', 'anp_open_sdk/anp_users_hosted'))
            duplicate_found = False
            for user_req in hosted_dir.glob('user_*/did_document_request.json'):
                try:
                    with open(user_req, 'r', encoding='utf-8') as f:
                        req_doc = json.load(f)
                    if req_doc.get('id', None) == did_document.get('id', None):
                        duplicate_found = True
                        break
                except Exception as e:
                    continue
            if duplicate_found:
                # 已申请，回复邮件
                reply = MIMEText('dupplicated request, contact admin', 'plain', 'utf-8')
                reply['Subject'] = Header('DID已申请', 'utf-8')
                reply['From'] = mail_user
                reply['To'] = msg['From']
                try:
                    smtp = smtplib.SMTP_SSL('smtp.gmail.com', 465)
                    smtp.login(mail_user, mail_pass)
                    smtp.sendmail(mail_user, [msg['From']], reply.as_string())
                    smtp.quit()
                except Exception as e:
                    print(f"回复邮件失败: {e}")
                imap.store(num, '+FLAGS', '\\Seen')
                count += 1
                result = f"{result}\n{msg['From']}DID{did_document.get('id', None)}已申请,退回\n"
                continue
            # 生成新 sid
            sid = secrets.token_hex(8)
            user_dir = hosted_dir / f"user_{sid}"
            user_dir.mkdir(parents=True, exist_ok=True)
            req_path = user_dir / 'did_document_request.json'
            with open(req_path, 'w', encoding='utf-8') as f:
                json.dump(did_document, f, ensure_ascii=False, indent=2)
            # 获取本机主机名和端口
            hostname = socket.gethostname()
            hostip = socket.gethostbyname(hostname)
            hostport = os.environ.get('HOST_DID_PORT', '9527')
            hostdomain = os.environ.get('HOST_DID_DOMAIN', 'localhost')
            # 修改 id 字段
            old_id = did_document['id']
            parts = old_id.split(':')
            # 只替换主机和端口部分
            if len(parts) > 3:
                parts[2] = f"{hostdomain}%3A{hostport}"
                parts[-1] = sid
                new_id = ':'.join(parts)
                did_document['id'] = new_id
                # 同步修改 verificationMethod、authentication、service 等字段
                if 'verificationMethod' in did_document:
                    for vm in did_document['verificationMethod']:
                        if 'id' in vm:
                            vm['id'] = vm['id'].replace(old_id, new_id)
                        if 'controller' in vm:
                            vm['controller'] = vm['controller'].replace(old_id, new_id)
                if 'authentication' in did_document:
                    did_document['authentication'] = [a.replace(old_id, new_id) for a in did_document['authentication']]
                if 'service' in did_document:
                    for svc in did_document['service']:
                        if 'id' in svc:
                            svc['id'] = svc['id'].replace(old_id, new_id)
                        if 'serviceEndpoint' in svc:
                            svc['serviceEndpoint'] = svc['serviceEndpoint'].replace(hostdomain, hostdomain).replace(hostport, hostport).replace(parts[-2], sid)
            # 保存到 anp_user_hosted/user_{sid}/did_document.json
            user_dir2 = hosted_dir / f"user_{sid}"
            user_dir2.mkdir(parents=True, exist_ok=True)
            did_path2 = user_dir2 / 'did_document.json'
            with open(did_path2, 'w', encoding='utf-8') as f:
                json.dump(did_document, f, ensure_ascii=False, indent=2)
            logger.info(f"新 Host DID 保存: {did_document['id']}")
            result = f"{result}\n{msg['From']}DID{did_document['id']}已保存\n"

            # 回复邮件
            reply = MIMEText(json.dumps(did_document, ensure_ascii=False, indent=2), 'plain', 'utf-8')
            reply['Subject'] = Header('ANP-DID host request received, waiting for activation', 'utf-8')
            reply['From'] = mail_user
            reply['To'] = msg['From']
            try:
                smtp = smtplib.SMTP_SSL('smtp.gmail.com', 465)
                smtp.login(mail_user, mail_pass)
                smtp.sendmail(mail_user, [msg['From']], reply.as_string())
                smtp.quit()
            except Exception as e:
                print(f"回复邮件失败: {e}")
            # 标记已读
            imap.store(num, '+FLAGS', '\\Seen')
            count += 1
        imap.logout()
        return result

    def register_agent(self, agent: LocalAgent):
        """注册智能体到路由器
        
        Args:
            agent: LocalAgent实例
        """
        self.router.register_agent(agent)
        self.logger.info(f"已注册智能体到路由器: {agent.id}")
            
        # 注册默认路由
        self._register_default_routes()
        
        # 在服务器启动时生成 OpenAPI YAML
        @self.app.on_event("startup")
        async def generate_openapi_yaml():
            self.save_openapi_yaml()
    
    def save_openapi_yaml(self):
        """生成并保存 OpenAPI YAML 文档"""
        import yaml
        import os
        
        # 确保 docs 目录存在
        docs_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'anp_open_sdk', 'anp_users')
        os.makedirs(docs_dir, exist_ok=True)
        
        # 为每个智能体生成单独的 YAML 文件
        # 遍历所有已注册的本地智能体
        for agent_id, agent in self.router.local_agents.items():
            # 动态遍历 FastAPI 路由，自动生成 OpenAPI paths
            openapi_spec = {
                "openapi": "3.0.0",
                "info": {
                    "title": f"Agent {agent_id} API Documentation",
                    "version": "1.0.0"
                },
                "paths": {}
            }
            # 1. 先处理 /agent/api/ 路由（直接遍历 self.api_registry）
            if hasattr(self, 'api_registry') and self.api_registry:
                for agent_api_id, apis in self.api_registry.items():
                    # 只导出当前 agent_id 的 api
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
                            # 修正拼接，避免重复 /agent/api/{agent_id}/agent/api/{agent_id}/xxx
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
                            # operationId
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

            # 2. 再处理其他路由（message/group/wba等，依然用 self.app.routes）
            for route in self.app.routes:
                if hasattr(route, "methods") and hasattr(route, "path"):
                    methods = route.methods
                    path = route.path
                    # 跳过 /agent/api/ 路由，已由上面处理
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

            
            # 保存YAML文件
            # 从agent_id中提取用户ID
            user_id = agent_id.split(':')[-1]  # 提取DID最后部分
            user_dir = f"user_{user_id}"
            user_path = os.path.join(dynamic_config.get('anp_sdk.user_did_path'), user_dir)
            safe_agent_id = urllib.parse.quote(agent_id, safe="")  # 编码所有特殊字符

            
            # 确保用户目录存在
            if os.path.exists(user_path):
                # 保存到用户目录
                yaml_path = os.path.join(user_path, f"openapi_{safe_agent_id}.yaml")
                with open(yaml_path, 'w', encoding='utf-8') as f:
                    yaml.dump(openapi_spec, f, allow_unicode=True, sort_keys=False)
                """
                # 同时保存到docs目录（保持向后兼容）
                docs_yaml_path = os.path.join(docs_dir, f"openapi_{agent_id}.yaml")
                with open(docs_yaml_path, 'w', encoding='utf-8') as f:
                    yaml.dump(openapi_spec, f, allow_unicode=True, sort_keys=False)
                
                self.logger.info(f"Generated OpenAPI documentation for agent {agent_id} at {docs_yaml_path}")
                """
                self.logger.info(f"Generated OpenAPI documentation for agent {agent_id} at {yaml_path} ")

            else:
                # 如果用户目录不存在，只保存到docs目录
                yaml_path = os.path.join(docs_dir, f"openapi_{safe_agent_id}.yaml")
                with open(yaml_path, 'w', encoding='utf-8') as f:
                    yaml.dump(openapi_spec, f, allow_unicode=True, sort_keys=False)
                
                self.logger.info(f"Generated OpenAPI documentation for agent {agent_id} at {yaml_path} (user directory not found)")

    
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
        @self.app.post("/agent/message/{did}/post")
        async def message_entry_post(did: str, request: Request):
            data = await request.json()
            req_did = request.query_params.get("req_did", "demo_caller")
            resp_did = did
            data["type"] = "message"
            result = self.router.route_request(req_did, resp_did, data)
            return result

        # 群组消息队列
        self.group_queues = {}
        # 群组成员列表
        self.group_members = {}
        
        # 注册群聊消息发送路由 - 由agent处理
        @self.app.post("/agent/group/{did}/{group_id}/message")
        async def group_message(did: str, group_id: str, request: Request):
            data = await request.json()
            req_did = request.query_params.get("req_did", "demo_caller")
            resp_did = did
            data["type"] = "group_message"
            data["group_id"] = group_id
            data["req_did"] = req_did
            result = self.router.route_request(req_did, resp_did, data)
            return result
        
        # 注册群聊SSE连接端点 - 由agent处理
        @self.app.get("/agent/group/{did}/{group_id}/connect")
        async def group_connect(did: str, group_id: str, request: Request):
            req_did = request.query_params.get("req_did", "demo_caller")
            resp_did = did
            data = {"type": "group_connect", "group_id": group_id}
            data["req_did"] = req_did
            result = self.router.route_request(req_did, resp_did, data)
            
            # 如果agent返回了event_generator函数，则使用它创建SSE响应
            if result and "event_generator" in result:
                return StreamingResponse(result["event_generator"], media_type="text/event-stream")
            return result
        
        # 注册群组成员管理路由 - 由agent处理
        @self.app.post("/agent/group/{did}/{group_id}/members")
        async def manage_group_members(did: str, group_id: str, request: Request):
            data = await request.json()
            req_did = request.query_params.get("req_did", "demo_caller")
            resp_did = did
            data["type"] = "group_members"
            data["group_id"] = group_id
            data["req_did"] = req_did
            result = self.router.route_request(req_did, resp_did, data)
            return result


        

        """
        暂时无用
        """
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

        # 从第一个agent中获取host和port，这样通过load不同端口的agent，即可启动不同的服务器
        agent1 = list(self.get_agents())[0]

        host, port = self.get_did_host_port_from_did(agent1.id)   

        app_instance = self.app
        uvicorn.run(app_instance, host="0.0.0.0", port=port)


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

