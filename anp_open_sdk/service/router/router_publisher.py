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
import logging
logger = logging.getLogger(__name__)
from typing import Dict
from pathlib import Path
from fastapi import APIRouter, Request, HTTPException
from anp_open_sdk.config import get_global_config, UnifiedConfig
from anp_open_sdk.utils.log_base import  logging as logger

router = APIRouter(tags=["publisher"])


@router.get("/wba/hostuser/{user_id}/did.json", summary="Get Hosted DID document")
async def get_hosted_did_document(user_id: str) -> Dict:
    """
    Retrieve a DID document by user ID from anp_users_hosted.
    """
    config=get_global_config()

    did_path = Path(config.anp_sdk.user_hosted_path)
    did_path = did_path.joinpath(f"user_{user_id}", "did_document.json")
    did_path = Path(UnifiedConfig.resolve_path(did_path.as_posix()))
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

