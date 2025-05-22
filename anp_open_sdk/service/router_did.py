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
DID document API router.
"""
import sys
import os
from anp_open_sdk.anp_sdk_utils import get_user_cfg_by_did
from urllib3 import response

from anp_open_sdk.agent_types import LocalAgent
from anp_open_sdk.config import path_resolver

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..","..")))
import os
import json
import logging
from typing import Dict, Optional
from pathlib import Path
from fastapi import APIRouter, Request, Response, HTTPException
from anp_open_sdk.config.dynamic_config import dynamic_config
from anp_open_sdk.config.path_resolver import path_resolver

from loguru import logger

router = APIRouter(tags=["did"])


@router.get("/wba/user/{user_id}/did.json", summary="Get DID document")
async def get_did_document(user_id: str) -> Dict:
    """
    Retrieve a DID document by user ID.
    
    Args:
        user_id: User identifier
        
    Returns:
        Dict: DID document
    """
    # 构建DID文档路径 路径和did_router所在目录严重相关 现在did_router在三级目录
    did_path = Path(dynamic_config.get('anp_sdk.user_did_path'))
    did_path = did_path.joinpath( f"user_{user_id}" , "did_document.json" )
    did_path = Path(path_resolver.resolve_path(did_path.as_posix()))
    # logger.info(f"current_dir: {current_dir}\n did_path = {did_path}" )
    # did_path = current_dir.joinpath( did_path,f"user_{user_id}" , "did_document.json" )



    if not did_path.exists():
        raise HTTPException(status_code=404, detail=f"DID document not found for user {user_id}")
    
    # 加载DID文档
    try:
        with open(did_path, 'r', encoding='utf-8') as f:
            did_document = json.load(f)
        return did_document
    except Exception as e:
        logging.error(f"Error loading DID document: {e}")
        raise HTTPException(status_code=500, detail="Error loading DID document")



@router.get("/wba/user/{resp_did}/ad.json", summary="Get agent description")
async def get_agent_description(resp_did: str) -> Dict:
    """
    Get agent description document.
    
    Args:
        resp_did: The DID of the agent to get description for
    
    Returns:
        Dict: Agent description
    """
    success, did_doc, user_dir = get_user_cfg_by_did(resp_did)
    if not success:
        raise HTTPException(status_code=404, detail=f"Agent with DID {resp_did} not found")
    
    from fastapi import Request
    import inspect
    # 尝试从调用栈获取 request
    request = None
    for frame_info in inspect.stack():
        local_vars = frame_info.frame.f_locals
        if 'request' in local_vars:
            request = local_vars['request']
            break
    if request is None:
        raise RuntimeError("无法获取 FastAPI request 实例，无法获取 sdk")
    sdk = request.app.state.sdk
    agent = sdk.get_agent(resp_did)
    if agent is None:
        agent = LocalAgent(did_doc['id'], user_dir)
    
    # 获取基础端点
    endpoints = {
        "auth": "/wba/auth",
        "message": f"/agent/message/post/{resp_did}"
    }
    
    # 添加agent注册的API端点
    for path, _ in agent.api_routes.items():
        endpoint_name = path.replace('/', '_').strip('_')
        endpoints[endpoint_name] = f"/agent/api/{resp_did}/{path}"

    return {
        "id": resp_did,
        "name": f"DID WBA Example Agent{agent.name}",
        "description": "An example agent implementing DID WBA authentication",
        "version": "0.1.0",
        "capabilities": [
            "did-wba-authentication",
            "token-authentication"
        ],
        "endpoints": endpoints,
        "owner": "DID WBA Example",
        "created_at": "2025-04-21T00:00:00Z"
    }
