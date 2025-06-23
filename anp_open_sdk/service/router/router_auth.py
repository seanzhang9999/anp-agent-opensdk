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
Authentication API router.
"""
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..","..")))
import logging
logger = logging.getLogger(__name__)

from typing import Dict
from fastapi import APIRouter, Request, HTTPException

router = APIRouter(tags=["authentication"])



@router.get("/wba/auth", summary="DID WBA authentication endpoint")
async def test_endpoint(request: Request) -> Dict:
    """
    Test endpoint for DID WBA authentication.
    
    Args:
        request: FastAPI request object
        
    Returns:
        Dict: Test result
    """
    # Try to get JSON data if available
    user = None
    req_did = request.query_params.get("req_did", "demo_caller")
    resp_did = request.query_params.get("resp_did", "demo_responser")
    if not req_did or not resp_did:
        raise HTTPException(status_code=401, detail="Missing req_did or resp_did in headers or query parameters")

    try:
        if req_did != "": # token 用户
            user = req_did
        else: # did 用户   
            auth_data = request.state.headers.get("authorization", "")
                # 检查auth_data是否为字符串
            if isinstance(auth_data, str) and " " in auth_data:
                auth_data = auth_data.split(" ", 1)[1]
                auth_dict =parse_auth_str_to_dict(auth_data)
                user = auth_dict.get("req_did")

    except Exception as e:
        logger.warning(f"解析认证数据时出错: {e}")
        user = None
    
    #logger.debug(f"请求方{user}通过认证中间件认证，认证方返回token和自身认证头")

    if not user:
        return {
            "status": "warning",
            "message": "No authentication provided, but access allowed"
        }
    
    return{
         "status": "success",
         "message": "Successfully authenticated",
         "RquestUser": user,
         "authenticated": True
    }
    
    

def parse_auth_str_to_dict(auth_str: str) -> dict:
    """
    将类似于 'key1="value1", key2="value2"' 的字符串解析为字典
    """
    result = {}
    try:
        # 先按逗号分割，再按等号分割
        for kv in auth_str.split(", "):
            if "=" in kv:
                k, v = kv.split("=", 1)
                result[k.strip()] = v.strip('"')
    except Exception as e:
        logger.warning(f"解析认证字符串为字典时出错: {e}")
    return result
    
    
