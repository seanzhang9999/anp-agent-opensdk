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
from anp_open_sdk.anp_sdk_utils import get_user_dir_did_doc_by_did
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
async def get_agent_description(resp_did: str, request: Request) -> Dict:
    """
    返回符合 schema.org/did/ad 规范的 JSON-LD 格式智能体描述，端点信息动态取自 agent 实例。
    """
    if resp_did and resp_did.find("%3A") == -1:
        parts = resp_did.split(":", 4)  # 分割 4 份 把第三个冒号替换成%3A
        resp_did = ":".join(parts[:3]) + "%3A" + ":".join(parts[3:])
    success, did_doc, user_dir = get_user_dir_did_doc_by_did(resp_did)
    if not success:
        raise HTTPException(status_code=404, detail=f"Agent with DID {resp_did} not found")
    
    sdk = request.app.state.sdk
    agent = sdk.get_agent(resp_did)
    if agent is None:
        agent = LocalAgent(did_doc['id'], user_dir)

    
    from anp_open_sdk.anp_sdk_utils import get_agent_cfg_by_user_dir
    user_cfg = get_agent_cfg_by_user_dir(user_dir)
    
    # 获取基础端点
    # 动态遍历 FastAPI 路由，自动生成 endpoints
    endpoints = {
    }
    for route in sdk.app.routes:
        if hasattr(route, "methods") and hasattr(route, "path"):
            path = route.path
            # 只导出 /agent/api/、/agent/message/、/agent/group/、/wba/ 相关路由
            if not (path.startswith("/agent/api/") or path.startswith("/agent/message/") or path.startswith("/agent/group/") or path.startswith("/wba/")):
                continue
            # endpoint 名称自动生成
            endpoint_name = path.replace("/agent/api/", "api_").replace("/agent/message/", "message_").replace("/agent/group/", "group_").replace("/wba/", "wba_").replace("/", "_").strip("_")
            endpoints[endpoint_name] = {
                "path": path,
                "description": getattr(route, "summary", getattr(route, "name", "相关端点"))
            }
   
    for path, _ in agent.api_routes.items():
        endpoint_name = path.replace('/', '_').strip('_')
        endpoints[endpoint_name] = {
            "path": f"/agent/api/{resp_did}{path}",
            "description": f"API 路径 {path} 的端点"
        }
    agent_id = f"https://agent-search.ai/ad.json"
    agent_name = user_cfg.get("name", f"DID WBA Example Agent{agent.name}")
    agent_owner = user_cfg.get("owner", {"name": "DID WBA Example", "@id": "https://agent-search.ai"})
    agent_description = user_cfg.get("description", "An example agent implementing DID WBA authentication")
    agent_version = user_cfg.get("version", "0.1.0")
    agent_created = user_cfg.get("created_at", "2025-04-21T00:00:00Z")
    security_def = {
        "didwba_sc": {
            "scheme": "didwba",
            "in": "header",
            "name": "Authorization"
        }
    }
    interfaces = []  # 可根据实际需求补充
    sub_agents = []  # 可根据实际需求补充
    result = {
        "@context": {
            "@vocab": "https://schema.org/",
            "did": "https://w3id.org/did#",
            "ad": "https://agent-network-protocol.com/ad#"
        },
        "@type": "ad:AgentDescription",
        "@id": agent_id,
        "name": agent_name,
        "did": resp_did,
        "owner": {
            "@type": "Organization",
            "name": agent_owner.get("name", "DID WBA Example"),
            "@id": agent_owner.get("@id", "https://agent-search.ai")
        },
        "description": agent_description,
        "version": agent_version,
        "created": agent_created,
        "ad:securityDefinitions": security_def,
        "ad:security": "didwba_sc",
        "ad:endpoints": endpoints,
        "ad:AgentDescription": sub_agents,
        "ad:interfaces": interfaces
    }
    return result


@router.get("/wba/user/{resp_did}/agent.yaml", summary="Get agent OpenAPI YAML")
async def get_agent_openapi_yaml(resp_did: str, request: Request):
    import urllib.parse
    import yaml

    if resp_did and resp_did.find("%3A") == -1:
        parts = resp_did.split(":", 4)  # 分割 4 份 把第三个冒号替换成%3A
        resp_did = ":".join(parts[:3]) + "%3A" + ":".join(parts[3:])
    success, did_doc, user_dir = get_user_dir_did_doc_by_did(resp_did)
    if not success:
        raise HTTPException(status_code=404, detail="User not found")
    dquote_did = urllib.parse.quote(resp_did, safe='')
    
    user_did_path = dynamic_config.get('anp_sdk.user_did_path')
    user_did_path = path_resolver.resolve_path(user_did_path)


    yaml_path = os.path.join(user_did_path, user_dir, f"openapi_{dquote_did}.yaml")
    if not os.path.exists(yaml_path):
        raise HTTPException(status_code=404, detail="OpenAPI YAML not found")
    with open(yaml_path, 'r', encoding='utf-8') as f:
        yaml_content = f.read()
    return Response(content=yaml_content, media_type="application/x-yaml")
