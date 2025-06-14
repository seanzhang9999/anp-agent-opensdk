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

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import os

from anp_open_sdk.auth.auth_client import agent_auth_request, handle_response, agent_token_request

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..","..")))

import sys
from typing import Optional, Dict, Any
import json
from urllib.parse import urlencode, quote

from anp_open_sdk.anp_sdk_agent import RemoteAgent,LocalAgent




async def agent_api_call_post( caller_agent: str, target_agent: str, api_path: str, params: Optional[Dict] = None) -> Dict:
    """通过 POST 方式调用智能体的 API
    
    Args:
        sdk: ANPSDK 实例
        caller_agent: 调用方智能体ID
        target_agent: 目标智能体ID
        api_path: API 路径
        params: API 参数
        
    Returns:
        Dict: API 响应结果
    """
    caller_agent_obj = LocalAgent.from_did(caller_agent)
    target_agent_obj = RemoteAgent(target_agent)

    req = {"params": params or {}}

    url_params = {
        "req_did": caller_agent_obj.id,
        "resp_did": target_agent_obj.id
    }
    url_params = urlencode(url_params)
    target_agent_path = quote(target_agent)

    url = f"http://{target_agent_obj.host}:{target_agent_obj.port}/agent/api/{target_agent_path}{api_path}?{url_params}"

    if caller_agent_obj.contact_manager.get_token_from_remote(target_agent_obj.id) is None:
        status, response, info, is_auth_pass = await agent_auth_request( caller_agent, target_agent, url, method="POST", json_data=req)
        response = await handle_response(response)
        return response
    token = caller_agent_obj.contact_manager.get_token_from_remote(target_agent_obj.id)["token"]
    status, response = await agent_token_request(url, token, caller_agent_obj.id, target_agent_obj.id, method="POST", json_data=req)
    if status == 401:
        status, response, info, is_auth_pass = await agent_auth_request( caller_agent, target_agent, url, method="POST", json_data=req)

    response = await handle_response(response)
    return response

async def agent_api_call_get(caller_agent: str,  target_agent: str, api_path: str, params: Optional[Dict] = None) -> Dict:
    """通过 GET 方式调用智能体的 API
    
    Args:
        sdk: ANPSDK 实例
        caller_agent: 调用方智能体ID
        target_agent: 目标智能体ID
        api_path: API 路径
        params: API 参数
        
    Returns:
        Dict: API 响应结果
    """


    caller_agent_obj = LocalAgent.from_did(caller_agent)

    target_agent_obj = RemoteAgent(target_agent)



    url_params = {
        "req_did": caller_agent_obj.id,
        "resp_did": target_agent_obj.id,
        "params": json.dumps(params) if params else ""
    }
    url_params = urlencode(url_params)
    target_agent_path = quote(target_agent)
    url = f"http://{target_agent_obj.host}:{target_agent_obj.port}/agent/api/{target_agent_path}{api_path}?{url_params}"

    if caller_agent_obj.contact_manager.get_token_from_remote(target_agent_obj.id) is None:
        status, response , info , is_auth_pass = await agent_auth_request( caller_agent, target_agent,url, method="GET")
        response = await handle_response(response)
        return response

    token = caller_agent_obj.contact_manager.get_token_from_remote(target_agent_obj.id)["token"]
    status, response = await agent_token_request(url, token, caller_agent_obj.id, target_agent_obj.id, method="GET")
    if status == 401:
        status, response , info , is_auth_pass = await agent_auth_request( caller_agent, target_agent,url, method="GET")
    response = await handle_response(response)
    return response




