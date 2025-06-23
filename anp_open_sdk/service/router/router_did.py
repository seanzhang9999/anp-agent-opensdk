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
import urllib
from urllib.parse import quote

from fastapi.responses import JSONResponse
import sys
import os
from anp_open_sdk.anp_sdk_user_data import get_user_dir_did_doc_by_did, get_agent_cfg_by_user_dir

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..","..")))
import os
import json
import logging
logger = logging.getLogger(__name__)

from typing import Dict
from pathlib import Path
from fastapi import APIRouter, Request, Response, HTTPException
from anp_open_sdk.config import get_global_config,UnifiedConfig

from anp_open_sdk.utils.log_base import  logging as logger

router = APIRouter(tags=["did"])




@router.get("/wba/user/{user_id}/did.json", summary="Get DID document")
async def get_did_document(user_id: str, request: Request) -> Dict:
    """
    Retrieve a DID document by user ID from anp_users.
    """

    config=get_global_config()

    did_path = Path(config.anp_sdk.user_did_path)
    did_path = did_path.joinpath( f"user_{user_id}" , "did_document.json" )
    did_path = Path(UnifiedConfig.resolve_path(did_path.as_posix()))

  
    
    
    if not did_path.exists():
        raise HTTPException(status_code=404, detail=f"DID document not found for user {user_id}")
    try:
        with open(did_path, 'r', encoding='utf-8') as f:
            did_document = json.load(f)
        return did_document
    except Exception as e:
        logger.debug(f"Error loading DID document: {e}")
        raise HTTPException(status_code=500, detail="Error loading DID document")


# 注意：托管 DID 文档的功能已移至 router_publisher.py
# 未来对于托管 did-doc/ad.json/yaml 以及消息转发/api转发都将通过 publisher 路由处理


@router.get("/wba/user/{user_id}/ad.json", summary="Get agent description")
async def get_agent_description(user_id: str, request: Request) -> Dict:
    """
    user_id可以是did 也可以是 最后hex序号
    返回符合 schema.org/did/ad 规范的 JSON-LD 格式智能体描述，端点信息动态取自 agent 实例。
    """
    host = request.url.hostname
    port = request.url.port

    resp_did = url_did_format(user_id,request)

    success, did_doc, user_dir = get_user_dir_did_doc_by_did(resp_did)
    if not success:
        raise HTTPException(status_code=404, detail=f"Agent with DID {resp_did} not found")
    
    sdk = request.app.state.sdk
    agent = sdk.get_agent(resp_did)


    if agent.is_hosted_did:
        raise HTTPException(status_code=403, detail=f"{resp_did} is hosted did")

    user_cfg = get_agent_cfg_by_user_dir(user_dir)
    
    # 获取基础端点
    # 动态遍历 FastAPI 路由，自动生成 endpoints
    endpoints = {
    }
    for route in sdk.app.routes:
        if hasattr(route, "methods") and hasattr(route, "path"):
            path = route.path
            # 只导出 /agent/api/、/agent/message/、/agent/group/、/wba/ 相关路由
            # if not (path.startswith("/agent/api/") or path.startswith("/agent/message/") or path.startswith("/agent/group/") or path.startswith("/wba/")):
            if not (path.startswith("/agent/api/")) :
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
    agent_id = f"{request.url.scheme}://{request.url.netloc}/wba/user/{resp_did}/ad.json"
    # 读取 ad.json 模板文件
    config=get_global_config()

    user_dirs = config.anp_sdk.user_did_path
    user_full_path = os.path.join(user_dirs, user_dir)

    template_ad_path = Path(user_full_path) / "template-ad.json"
    template_ad_path = Path(UnifiedConfig.resolve_path(template_ad_path.as_posix()))

    # 默认模板内容
    default_template = {
        "name": f"ANP Agent {agent.name}",
        "owner": {
            "name": f"{agent.name}的开发者",
            "@id": agent.id
        },
        "description": "ANP Agent ",
        "version": "0.1.0",
        "created_at": "2025-04-21T00:00:00Z",
        "security_definitions": {
        "didwba_sc": {
            "scheme": "didwba",
            "in": "header",
            "name": "Authorization"
        }
        },
        "interfaces": [],
        "sub_agents": []
    }

    template_data = default_template

    result = template_data

    # 从模板获取或初始化接口列表，使用 "ad:interfaces" 作为标准键，并兼容旧的 "interfaces"
    # 只保留 /agent/api/ 相关接口
    all_interfaces = result.get("ad:interfaces", result.get("interfaces", [])).copy()

    # 添加您指定的静态接口
    # 添加静态接口（如需保留，可注释掉以下三项）
    all_interfaces.extend([
        {
            "@type": "ad:NaturalLanguageInterface",
            "protocol": "YAML",
            "url": f"http://{host}:{port}/wba/user/{quote(resp_did)}/nlp_interface.yaml",
            "description": "提供自然语言交互接口的OpenAPI的YAML文件，可以通过接口与智能体进行自然语言交互."
        },
        {
            "@type": "ad:StructuredInterface",
            "protocol": "YAML",
            "url": f"http://{host}:{port}/wba/user/{quote(resp_did)}/api_interface.yaml",
            "description": "智能体的 YAML 描述的接口调用方法"
        },
        {
            "@type": "ad:StructuredInterface",
            "protocol": "JSON",
            "url": f"http://{host}:{port}/wba/user/{quote(resp_did)}/api_interface.json",
            "description": "智能体的 JSON RPC 描述的接口调用方法"
        }
    ])

    # 只添加 /agent/api/ 相关端点
    for name, data in endpoints.items():
        if data.get("path", "").startswith("/agent/api/"):
            all_interfaces.append({
                "@type": "ad:StructuredInterface",
                "protocol": "HTTP",
                "name": name,
                "url": data.get("path"),
                "description": data.get("description")
            })

    result["ad:interfaces"] = all_interfaces
    if "interfaces" in result:
        del result["interfaces"]

    # 添加动态发现的端点，并统一格式
    for name, data in endpoints.items():
        all_interfaces.append({
            "@type": "ad:StructuredInterface",
            "protocol": "HTTP",
            "name": name,
            "url": data.get("path"),
            "description": data.get("description")
        })

    result["ad:interfaces"] = all_interfaces
    if "interfaces" in result:
        del result["interfaces"]


    # 确保必要的字段存在
    result["@context"] = result.get("@context", {
            "@vocab": "https://schema.org/",
            "did": "https://w3id.org/did#",
            "ad": "https://agent-network-protocol.com/ad#"
    })
    result["@type"] = result.get("@type", "ad:AgentDescription")
    return result


def url_did_format(user_id,request):
    host = request.url.hostname
    port = request.url.port
    user_id = urllib.parse.unquote(user_id)
    if user_id.startswith("did:wba"):
        # 新增处理：如果 user_id 不包含 %3A，按 : 分割，第四个部分是数字，则把第三个 : 换成 %3A
        if "%3A" not in user_id:
            parts = user_id.split(":")
            if len(parts) > 4 and parts[3].isdigit():
                resp_did = ":".join(parts[:3]) + "%3A" + ":".join(parts[3:])
    elif len(user_id) == 16: # unique_id
        if port == 80 or port == 443:
            resp_did = f"did:wba:{host}:wba:user:{user_id}"
        else:
            resp_did = f"did:wba:{host}%3A{port}:wba:user:{user_id}"
    else :
        resp_did = "not_did_wba"

    return resp_did


@router.get("/wba/user/{resp_did}/{yaml_file_name}.yaml", summary="Get agent OpenAPI YAML")
async def get_agent_openapi_yaml(resp_did: str, yaml_file_name, request: Request):
    resp_did = url_did_format(resp_did, request)

    success, did_doc, user_dir = get_user_dir_did_doc_by_did(resp_did)
    if not success:
        raise HTTPException(status_code=404, detail="User not found")


    sdk = request.app.state.sdk
    agent = sdk.get_agent(resp_did)

    if agent.is_hosted_did:
        raise HTTPException(status_code=403, detail=f"{resp_did} is hosted did")
    
    config=get_global_config()

    user_did_path = config.anp_sdk.user_did_path
    user_did_path = UnifiedConfig.resolve_path(user_did_path)


    yaml_path = os.path.join(user_did_path, user_dir, f"{yaml_file_name}.yaml")
    if not os.path.exists(yaml_path):
        raise HTTPException(status_code=404, detail="OpenAPI YAML not found")
    with open(yaml_path, 'r', encoding='utf-8') as f:
        yaml_content = f.read()
    return Response(content=yaml_content, media_type="application/x-yaml")





@router.get("/wba/user/{resp_did}/{jsonrpc_file_name}.json", summary="Get agent JSON-RPC")
async def get_agent_jsonrpc(resp_did: str, jsonrpc_file_name, request: Request):


    resp_did = url_did_format(resp_did,request)

    success, did_doc, user_dir = get_user_dir_did_doc_by_did(resp_did)
    if not success:
        raise HTTPException(status_code=404, detail="User not found")


    sdk = request.app.state.sdk
    agent = sdk.get_agent(resp_did)

    if agent.is_hosted_did:
        raise HTTPException(status_code=403, detail=f"{resp_did} is hosted did")
    
    config=get_global_config()

    user_did_path = config.anp_sdk.user_did_path
    user_did_path = UnifiedConfig.resolve_path(user_did_path)


    json_path = os.path.join(user_did_path, user_dir, f"{jsonrpc_file_name}.json")
    if not os.path.exists(json_path):
        raise HTTPException(status_code=404, detail="json rpc not found")
    with open(json_path, 'r', encoding='utf-8') as f:
        json_content = json.load(f)
    return JSONResponse(content=json_content, status_code=200)