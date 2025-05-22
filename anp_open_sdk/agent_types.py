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
import inspect
from typing import Dict, Any, Callable, Optional, Union, List
from loguru import logger

from anp_open_sdk.anp_sdk_utils import get_user_cfg_by_did
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
    
    def __init__(self, id: str, user_dir: str = "", name:str = "未命名", agent_type: str = "personal"):
        """初始化本地智能体
        
        Args:
            id: DID标识符
            user_dir: 用户目录
            agent_type: 智能体类型，"personal"或"service"
        """

        if not user_dir:
            result ,did_dict, user_dir = get_user_cfg_by_did(id)
            if did_dict['name'] is not None and name == "未命名":
                self.name = did_dict['name']
            if result is True:
                raise ValueError(f"未找到DID为 {id} 的用户文档")



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


        # 支持装饰器和函数式注册API
    
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

