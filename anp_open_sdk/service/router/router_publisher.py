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

"""
Publisher API router for hosted DID documents, agent descriptions, and API forwarding.
"""
import json
import yaml
from anp_open_sdk.utils.log_base import logger
from typing import Dict
from pathlib import Path
from fastapi import APIRouter, Request, HTTPException
from anp_open_sdk.config.legacy.dynamic_config import dynamic_config
from anp_open_sdk.config.path_resolver import path_resolver
from anp_open_sdk.utils.log_base import  logging as logger

router = APIRouter(tags=["publisher"])


@router.get("/wba/hostuser/{user_id}/did.json", summary="Get Hosted DID document")
async def get_hosted_did_document(user_id: str) -> Dict:
    """
    Retrieve a DID document by user ID from anp_users_hosted.
    """
    did_path = Path(dynamic_config.get('anp_sdk.user_hosted_path', 'anp_users_hosted'))
    did_path = did_path.joinpath(f"user_{user_id}", "did_document.json")
    did_path = Path(path_resolver.resolve_path(did_path.as_posix()))
    if not did_path.exists():
        raise HTTPException(status_code=404, detail=f"Hosted DID document not found for user {user_id}")
    try:
        with open(did_path, 'r', encoding='utf-8') as f:
            did_document = json.load(f)
        return did_document
    except Exception as e:
        logger.debug(f"Error loading hosted DID document: {e}")
        raise HTTPException(status_code=500, detail="Error loading hosted DID document")


@router.get("/publisher/agents", summary="Get published agent list")
async def get_agent_publishers(request: Request) -> Dict:
    """
    获取已发布的代理列表，直接从运行中的 SDK 实例获取。
    发布设置:
    - open: 公开给所有人
    """
    try:
        # 通过 request.app.state 获取在 ANPSDK 初始化时存储的 sdk 实例
        sdk = request.app.state.sdk

        # 从 SDK 实例中获取所有已注册的 agent
        all_agents = sdk.get_agents() # 使用 get_agents() 公共方法

        public_agents = []
        for agent in all_agents:
                public_agents.append({
                    "did": getattr(agent, "id", "unknown"),
                    "name": getattr(agent, "name", "unknown")
                })

        return {
            "agents": public_agents,
            "count": len(public_agents)
        }
    except Exception as e:
        logger.error(f"Error getting agent list from SDK instance: {e}")
        raise HTTPException(status_code=500, detail="Error getting agent list from SDK instance")


@router.get("/publisher/agents/{did}", summary="Get specific agent publisher info")
async def get_agent_publisher(did: str, request: Request) -> Dict:
    """
    获取特定代理的发布信息，根据发布设置进行权限检查。
    
    发布设置:
    - open: 公开给所有人
    - local: 公开给指定域名/did列表
    - self: 不公开，仅代理自身可访问
    """
    publisher_config_path = Path(dynamic_config.get('anp_sdk.publisher_config_path', 'publisher_config.yaml'))
    publisher_config_path = Path(path_resolver.resolve_path(publisher_config_path.as_posix()))
    
    if not publisher_config_path.exists():
        raise HTTPException(status_code=404, detail="Publisher configuration not found")
    
    try:
        with open(publisher_config_path, 'r', encoding='utf-8') as f:
            publisher_config = yaml.safe_load(f)
        
        if not publisher_config or "agents" not in publisher_config:
            raise HTTPException(status_code=404, detail="No agents configured in publisher configuration")
        
        # 查找特定代理
        target_agent = None
        for agent in publisher_config.get("agents", []):
            if agent.get("did") == did:
                target_agent = agent
                break
        
        if not target_agent:
            raise HTTPException(status_code=404, detail=f"Agent with DID {did} not found in publisher configuration")
        
        # 检查发布权限
        publisher_type = target_agent.get("publisher", "self")
        
        # 如果是公开的，直接返回
        if publisher_type == "open":
            return target_agent
        
        # 如果是本地的，检查请求者是否在允许列表中
        elif publisher_type == "local":
            # 获取请求者信息（这里需要根据实际情况实现）
            # 例如，从请求头中获取 DID 或域名
            requester_did = request.headers.get("X-Requester-DID")
            requester_domain = request.headers.get("Origin")
            
            allowed_dids = target_agent.get("allowed_dids", [])
            allowed_domains = target_agent.get("allowed_domains", [])
            
            if (requester_did and requester_did in allowed_dids) or \
               (requester_domain and any(domain in requester_domain for domain in allowed_domains)):
                return target_agent
            else:
                raise HTTPException(status_code=403, detail="Access denied: not in allowed list")
        
        # 如果是私有的，只有自己可以访问
        elif publisher_type == "self":
            # 检查请求者是否是代理自身
            requester_did = request.headers.get("X-Requester-DID")
            if requester_did and requester_did == did:
                return target_agent
            else:
                raise HTTPException(status_code=403, detail="Access denied: self-access only")
        
        else:
            raise HTTPException(status_code=400, detail=f"Unknown publisher type: {publisher_type}")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing agent publisher request: {e}")
        raise HTTPException(status_code=500, detail="Error processing agent publisher request")
