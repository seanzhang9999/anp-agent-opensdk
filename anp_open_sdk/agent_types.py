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
from datetime import datetime
from anp_open_sdk.config.path_resolver import path_resolver
import inspect
from typing import Dict, Any, Callable, Optional, Union, List
from warnings import simplefilter
from loguru import logger

from anp_open_sdk.anp_sdk_utils import get_user_dir_did_doc_by_did
from anp_open_sdk.config.dynamic_config import dynamic_config

class RemoteAgent:
    """远程智能体，代表其他DID身份"""
    
    def __init__(self, id: str):
        """初始化远程智能体
        
        Args:
            id: DID标识符
        """
        self.id = id
        from anp_open_sdk.anp_sdk import ANPSDK
        host, port = ANPSDK.get_did_host_port_from_did(id)
        self.host = host
        self.port = port

class LocalAgent:
    """本地智能体，代表当前用户的DID身份"""

    
    def __init__(self, sdk , id: str, name :str = "未命名",  agent_type: str = "personal"):
        """初始化本地智能体
        
        Args:
            id: DID标识符
            user_dir: 用户目录
            agent_type: 智能体类型，"personal"或"service"
        """

        

        user_data_manager = sdk.user_data_manager
        self.user_data = user_data_manager.get_user_data(id)
        user_dir = user_data.user_dir


        if name == "未命名":
            if user_data.name:
                self.name = user_data.name
            else:
                self.name = f"未命名智能体{id}"
        self.id = id
        self.name = name
        self.user_dir = user_dir
        self.agent_type = agent_type
        self.key_id = dynamic_config.get('anp_sdk.user_did_key_id')

        
        self.did_document_path = user_data.did_doc_path

    

        self.private_key_path =user_data.did_private_key_file_path

        self.jwt_private_key_path = user_data.jwt_private_key_file_path

        self.jwt_public_key_path = user_data.jwt_public_key_file_path

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

        # 群组相关属性
        self.group_queues = {}  # 群组消息队列: {group_id: {client_id: Queue}}
        self.group_members = {}  # 群组成员列表: {group_id: set(did)}


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
        except Exception as e:
            self.logger.error(f"LocalAgent {self.id} 资源释放出错: {e}")


    def get_host_dids(self):
        """获取用户目录"""
        return self.user_dir

    # 支持装饰器和函数式注册API
    def expose_api(self, path: str, func: Callable = None, methods=None):
        methods = methods or ["GET", "POST"] 
        if func is None:
            def decorator(f):
                self.api_routes[path] = f
                # 生成API信息
                api_info = {
                    "path": f"/agent/api/{self.id}{path}",
                    "methods": methods,
                    "summary": f.__doc__ or f"{self.name}的{path}接口",
                    "agent_id": self.id,
                    "agent_name": self.name
                }
                # 将API信息添加到SDK的注册表中
                
                from anp_open_sdk.anp_sdk import ANPSDK
                if hasattr(ANPSDK, 'instance') and ANPSDK.instance:
                    if self.id not in ANPSDK.instance.api_registry:
                        ANPSDK.instance.api_registry[self.id] = []
                    ANPSDK.instance.api_registry[self.id].append(api_info)
                    print(f"注册 API: {api_info}")
                return f
            return decorator
        else:
            self.api_routes[path] = func
            # 生成API信息
            api_info = {
                "path": f"/agent/api/{self.id}{path}",
                "methods": methods,
                "summary": func.__doc__ or f"{self.name}的{path}接口",
                "agent_id": self.id,
                "agent_name": self.name
            }
            # 将API信息添加到SDK的注册表中
            from anp_open_sdk.anp_sdk import ANPSDK
            if hasattr(ANPSDK, 'instance') and ANPSDK.instance:
                if self.id not in ANPSDK.instance.api_registry:
                    ANPSDK.instance.api_registry[self.id] = []
                ANPSDK.instance.api_registry[self.id].append(api_info)
                print(f"注册 API: {api_info}")
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
                
    async def start_group_listening(self, sdk, group_hoster:str,group_url: str, group_id: str):
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
            listen_group_messages(sdk, self.id, group_hoster, group_url, group_id)
        )
        
        self.logger.info(f"已启动群组 {group_id} 的消息监听")
        return task
       

    def handle_request(self, req_did: str, request_data: Dict[str, Any]):
        """Handle requests from req_did
        Args:
            req_did: Requester's DID
            request_data: Request data
        Returns:
            Processing result
        """
        req_type = request_data.get("type")
        # Directly handle group_message, group_connect, group_members
        if req_type in ("group_message", "group_connect", "group_members"):
            handler = self.message_handlers.get(req_type)
            if handler:
                try:
                    import asyncio
                    import nest_asyncio
                    nest_asyncio.apply()
                    if asyncio.iscoroutinefunction(handler):
                        loop = asyncio.get_event_loop() 
                        if loop.is_running():
                            future = asyncio.ensure_future(handler(request_data))
                            return loop.run_until_complete(future)  # 获取任务结果
                        else:
                            return loop.run_until_complete(handler(request_data))
                        #asyncio.set_event_loop(loop)
                        #result = loop.run_until_complete(handler(request_data))  # 运行异步任务
                        #result = asyncio.create_task(handler(request_data))
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
    
    def store_token_to_remote(self, remote_did: str, token: str, expires_delta: int , hosted_did:str = None):
        """存储颁发给其他方的token信息

        Args:
            req_did: 请求方DID
            token: 生成的token
            expires_delta: 过期时间（秒）
        """
        from datetime import datetime, timedelta, timezone
        now = datetime.now(timezone.utc)
        """存储颁发给其他方的token信息
        
        Args:
            remote_did: 请求方DID
            token: 生成的token
            expires_delta: 过期时间（秒）
        """
        from datetime import datetime, timedelta, timezone
        now = datetime.now(timezone.utc)
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_delta)
        
        self.token_to_remote_dict[remote_did] = {
            "token": token,
            "created_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
            "is_revoked": False,
            "req_did": remote_did
        }
    
    def get_token_from_remote(self, remote_did: str, hosted_did:str = None):
        """获取从其他方拿到存储在自己空间的token信息
        
        Args:
            remote_did: token颁发方
            
        Returns:
            token信息字典，如果不存在则返回None
        """
        return self.token_from_remote_dict.get(remote_did)
    

    def store_token_from_remote(self, remote_did: str, token: str, hosted_did:str = None):
        """存储从其他方拿到的token信息
        
        Args:
            remote_did: token颁发方DID
            token: 生成的token
            expires_delta: 过期时间（秒）
        """
        now = datetime.now()
        self.token_from_remote_dict[remote_did] = {
            "token": token,
            "created_at": now.isoformat(),
            "req_did": remote_did
        }
    
    def get_token_to_remote(self, remote_did: str, hosted_did:str = None):
        """获取颁发给其他方的token信息
        
        Args:
            remote_did: 请求方DID
            
        Returns:
            token信息字典，如果不存在则返回None
        """
        return self.token_to_remote_dict.get(remote_did)
    
    def revoke_token_to_remote(self, remote_did: str, hosted_did:str = None):
        """撤销颁发给其他方的token
        
        Args:
            remote_did: 请求方DID
            
        Returns:
            是否成功撤销
        """
        if remote_did in self.token_to_remote_dict:
            self.token_to_remote_dict[remote_did]["is_revoked"] = True
            return True
        return False

    async def check_hosted_did(self):
        """
        检查邮箱，收到'保存HOST-DID,等待开通' 邮件后，保存DID_document到 user_dir 下，文件名为 host_{host}:{port}_did_document.json
        """
        import imaplib
        import email
        from email.header import decode_header
        import os, json, re
        from pathlib import Path

        import socks
        
        # 设置 SOCKS5 代理
        socks.setdefaultproxy(socks.PROXY_TYPE_SOCKS5, "127.0.0.1", 1080)
        socks.wrapmodule(imaplib)
        # 邮箱配置
        mail_user = os.environ.get('SENDER_MAIL_USER')
        mail_pass = os.environ.get('SENDER_PASSWORD')
        if not (mail_user and mail_pass):
            raise ValueError('请在环境变量中配置 SENDER_MAIL_USER/SENDER_PASSWORD')
        # 连接IMAP
        imap = imaplib.IMAP4_SSL('imap.gmail.com')
        imap.login(mail_user, mail_pass)
        imap.select('INBOX')
        status, messages = imap.search(None, '(UNSEEN SUBJECT "ANP-DID host request received, waiting for activation")')
        if status != 'OK':
            imap.logout()
            return "查询邮件失败"
        msg_ids = messages[0].split()
        count = 0
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
                logger.info(f"无法解析 did_document: {e}")
                continue
            # 提取 host:port
            did_id = did_document.get('id', '')
            m = re.search(r'did:wba:([^:]+)%3A(\d+):', did_id)
            if not m:
                logger.info(f"无法从id中提取host:port: {did_id}")
                return "无法从id中提取host:port"
            host = m.group(1)
            port = m.group(2)
            # user_dir 目录名
            # 存到 LocalAgent 的 user_dir 下
            user_dir = Path(getattr(self, 'user_dir', '.'))
            user_dir.mkdir(parents=True, exist_ok=True)
            fname = f"host_{host}:{port}_did_document.json"
            fpath = user_dir / fname
            with open(fpath, 'w', encoding='utf-8') as f:
                json.dump(did_document, f, ensure_ascii=False, indent=2)
            imap.store(num, '+FLAGS', '\\Seen')
            logger.info(f"已保存 did_document 到 {fpath}")
            count += 1
        imap.logout()
        return f"处理{count}封邮件"

    async def register_hosted_did(self,sdk):
        """注册托管DID，将 did_document 邮件发送到 seanzhang9999@gmail.com 申请开通"""
        import smtplib
        from email.mime.text import MIMEText
        from email.header import Header
        import json
        import socks
                # 设置 SOCKS5 代理
        socks.setdefaultproxy(socks.PROXY_TYPE_SOCKS5, "127.0.0.1", 1080)
        socks.wrapmodule(smtplib)
        
        user_data_manager = sdk.user_data_manager
        user_data = user_data_manager.get_user_data(self.id)

        # 获取 did_document 内容
        did_document = user_data.did_doc 
        if did_document is None:
            raise ValueError("当前 LocalAgent 未包含 did_document")
        
        # 邮件正文
        body = json.dumps(did_document, ensure_ascii=False, indent=2)
        msg = MIMEText(body, 'plain', 'utf-8')
        msg['Subject'] = Header('ANP-DID host request')
        mail_user = os.environ.get('SENDER_MAIL_USER')
        mail_to = os.environ.get('REGISTER_MAIL_USER')
        msg['From'] = mail_user
        msg['To'] = mail_to
        
        # 发送邮件（请根据实际环境配置 SMTP 服务器，下面为本地 sendmail 示例）
        try:
            # 使用 Gmail SMTP 发送邮件
            # 需要在 Google 账号后台生成“应用专用密码”
            app_password = os.environ.get('SENDER_PASSWORD')
            if not app_password:
                raise ValueError("请在 .env 或环境变量中设置 GMAIL_APP_PASSWORD（Gmail 应用专用密码）")
            smtp = smtplib.SMTP_SSL('smtp.gmail.com', 465)
            smtp.login(os.environ.get('SENDER_MAIL_USER'), app_password)
            smtp.sendmail(os.environ.get('SENDER_MAIL_USER'), [os.environ.get('REGISTER_MAIL_USER')], msg.as_string())
            smtp.quit()
            return True
        except Exception as e:
            print(f"发送邮件失败: {e}")
            return False
        