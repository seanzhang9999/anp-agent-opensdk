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
import inspect

from anp_open_sdk.service.router.router_did import url_did_format
import logging
logger = logging.getLogger(__name__)


from fastapi import Request
from typing import Dict, Any, List
from datetime import datetime
import time

from anp_open_sdk.utils.log_base import  logging as logger
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..","..")))

class AgentSearchRecord:
    """智能体搜索记录"""
    
    def __init__(self):
        self.search_history = []
    
    def record_search(self, searcher_did: str, query: str, results: List[str]):
        """记录搜索行为"""
        self.search_history.append({
            "timestamp": datetime.now().isoformat(),
            "searcher_did": searcher_did,
            "query": query,
            "results": results,
            "result_count": len(results)
        })
        
    def get_recent_searches(self, limit: int = 10):
        """获取最近的搜索记录"""
        return self.search_history[-limit:]


class AgentContactBook:
    """智能体通讯录"""
    
    def __init__(self, owner_did: str):
        self.owner_did = owner_did
        self.contacts = {}  # did -> 联系人信息
    
    def add_contact(self, did: str, name: str = None, description: str = "", tags: List[str] = None):
        """添加联系人"""
        if did not in self.contacts:
            self.contacts[did] = {
                "did": did,
                "name": name or did.split(":")[-1],
                "description": description,
                "tags": tags or [],
                "first_contact": datetime.now().isoformat(),
                "last_contact": datetime.now().isoformat(),
                "interaction_count": 1
            }
        else:
            self.update_interaction(did)
    
    def update_interaction(self, did: str):
        """更新交互记录"""
        if did in self.contacts:
            self.contacts[did]["last_contact"] = datetime.now().isoformat()
            self.contacts[did]["interaction_count"] += 1
    
    def get_contacts(self, tag: str = None):
        """获取联系人列表"""
        if tag:
            return {did: info for did, info in self.contacts.items() if tag in info["tags"]}
        return self.contacts


class SessionRecord:
    """会话记录"""
    
    def __init__(self):
        self.sessions = {}  # session_id -> 会话信息
    
    def create_session(self, req_did: str, resp_did: str):
        """创建会话"""
        session_id = f"{req_did}_{resp_did}_{int(time.time())}"
        self.sessions[session_id] = {
            "session_id": session_id,
            "req_did": req_did,
            "resp_did": resp_did,
            "start_time": datetime.now().isoformat(),
            "end_time": None,
            "messages": [],
            "status": "active"
        }
        return session_id
    
    def add_message(self, session_id: str, message: Dict):
        """添加消息"""
        if session_id in self.sessions:
            self.sessions[session_id]["messages"].append({
                "timestamp": datetime.now().isoformat(),
                "content": message,
                "direction": "outgoing" if message.get("sender") == self.sessions[session_id]["req_did"] else "incoming"
            })
    
    def close_session(self, session_id: str):
        """关闭会话"""
        if session_id in self.sessions:
            self.sessions[session_id]["end_time"] = datetime.now().isoformat()
            self.sessions[session_id]["status"] = "closed"
    
    def get_active_sessions(self):
        """获取活跃会话"""
        return {sid: session for sid, session in self.sessions.items() if session["status"] == "active"}


class ApiCallRecord:
    """API调用记录"""
    
    def __init__(self):
        self.api_calls = []
    
    def record_api_call(self, caller_did: str, target_did: str, api_path: str, method: str, params: Dict, response: Dict, duration_ms: int):
        """记录API调用"""
        self.api_calls.append({
            "timestamp": datetime.now().isoformat(),
            "caller_did": caller_did,
            "target_did": target_did,
            "api_path": api_path,
            "method": method,
            "params": params,
            "response_status": response.get("status"),
            "duration_ms": duration_ms,
            "success": response.get("status") == "success"
        })
    
    def get_recent_calls(self, limit: int = 20):
        """获取最近的API调用记录"""
        return self.api_calls[-limit:]


class AgentRouter:
    """智能体路由器，负责管理多个本地智能体并路由请求"""
    
    def __init__(self):
        self.local_agents = {}  # did -> LocalAgent实例
        self.logger = logger
    
    def register_agent(self, agent):
        """注册一个本地智能体"""
        self.local_agents[str(agent.id)] = agent
        self.logger.debug(f"已注册智能体到多智能体路由: {agent.id}")
        return agent
        
    def get_agent(self, did: str):
        """获取指定DID的本地智能体"""
        return self.local_agents.get(str(did))

    async def route_request(self, req_did: str, resp_did: str, request_data: Dict , request: Request) -> Any:
        """路由请求到对应的本地智能体"""
        resp_did = url_did_format(resp_did,request)

        if resp_did in self.local_agents:

            if hasattr(self.local_agents[resp_did].handle_request, "__call__"):  # 确保 `handle_request` 可调用
                resp_agent = self.local_agents[resp_did]
                # 将agent实例 挂载到request.state 方便在处理中引用
                request.state.agent = resp_agent
                logger.info(
                        f"成功路由到{resp_agent.id}的处理函数, 请求数据为{request_data}\n"
                        f"完整请求为 url: {request.url} \n"
                        f"body: {await request.body()}")
                return await self.local_agents[resp_did].handle_request(req_did, request_data , request)
            else:
                self.logger.error(f"{resp_did} 的 `handle_request` 不是一个可调用对象")
                raise TypeError(f"{resp_did} 的 `handle_request` 不是一个可调用对象")
        else:
            self.logger.error(f"智能体路由器未找到本地智能体注册的调用方法: {resp_did}")
            raise ValueError(f"未找到本地智能体: {resp_did}")


    
    def get_all_agents(self):
        """获取所有本地智能体"""
        return self.local_agents


import functools

def wrap_business_handler(business_func):
    sig = inspect.signature(business_func)
    param_names = list(sig.parameters.keys())
    @functools.wraps(business_func)
    async def api_handler(request_data, request):
        import json
        try:
            kwargs = {k: request_data.get(k) for k in param_names if k in request_data}
            if "params" in request_data:
                params = request_data["params"]
                if isinstance(params, str):
                    params = json.loads(params)
                for k in param_names:
                    if k in params:
                        kwargs[k] = params[k]
            kwargs_str = json.dumps(kwargs, ensure_ascii=False)
            logger.info(f"api封装器发送参数 {kwargs_str}到{business_func.__name__}")
            if 'request' in sig.parameters:
                return await business_func(request, **kwargs)
            else:
                return await business_func(**kwargs)
        except Exception as e :
            logger.error(f"wrap error {e}")
            return f"wrap error {e}"
    return api_handler
