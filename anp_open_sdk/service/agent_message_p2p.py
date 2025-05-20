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

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..","..")))
from typing import Optional, Dict, Any
from urllib.parse import urlencode, quote
from anp_open_sdk.config.dynamic_config import dynamic_config
from loguru import logger
from anp_sdk import RemoteAgent
from anp_open_sdk.anp_sdk_utils import handle_response
from anp_open_sdk.service.agent_auth import agent_auth_two_way
from anp_open_sdk.auth.did_auth import send_authenticated_request, send_request_with_token, DIDWbaAuthHeader
async def agent_msg_post(sdk, caller_agent:str , target_agent :str, content: str, message_type: str = "text"):
    """发送消息给目标智能体
    
    Args:
        sdk: ANPSDK 实例
        caller_agent: 调用方智能体ID
        target_agent: 目标智能体ID
        message: 消息内容
        
    Returns:
        Dict: 响应结果
    """
    caller_agent_obj = sdk.get_agent(caller_agent)
    target_agent_obj = RemoteAgent(target_agent)

    if caller_agent_obj.get_token_from_remote(target_agent_obj.id) is None:
        status, error = await agent_auth_two_way(sdk, caller_agent, target_agent)
        if status is False:
            return {"error": error}

    url_params = {
        "req_did": caller_agent_obj.id,
        "resp_did": target_agent_obj.id
    }
    url_params = urlencode(url_params)
    target_agent_path = quote(target_agent)

    msg = {
        "req_did": caller_agent_obj.id,
        "message_type": message_type,
        "content": content
    }
    
    msg_dir = dynamic_config.get("anp_sdk.msg_virtual_dir")

    url = f"http://{target_agent_obj.host}:{target_agent_obj.port}{msg_dir}/{target_agent_path}?{url_params}"
    token = caller_agent_obj.get_token_from_remote(target_agent_obj.id)["token"]

    status, response = await send_request_with_token(url, token, caller_agent_obj.id, target_agent_obj.id, method="POST", json_data=msg)
    if status == 401:
        status, error = await agent_auth_two_way(sdk, caller_agent, target_agent)
        if status is False:
            return {"error": error}
        else:
            token = caller_agent_obj.get_token_from_remote(target_agent_obj.id)["token"]
            status, response = await send_request_with_token(url, token, caller_agent_obj.id, target_agent_obj.id, method="POST", json_data=msg)

    response = await handle_response(response)
    return response