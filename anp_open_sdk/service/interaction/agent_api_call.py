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

from anp_open_sdk.auth.auth_client import agent_auth_request, handle_response
from anp_open_sdk.anp_sdk_agent import RemoteAgent, LocalAgent
from urllib.parse import urlencode, quote
import json
from typing import Optional, Dict

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

async def agent_api_call(
    caller_agent: str,
    target_agent: str,
    api_path: str,
    params: Optional[Dict] = None,
    method: str = "GET"
) -> Dict:
        """通用方式调用智能体的 API (支持 GET/POST)"""
        caller_agent_obj = LocalAgent.from_did(caller_agent)
        target_agent_obj = RemoteAgent(target_agent)
        target_agent_path = quote(target_agent)
        if method.upper() == "POST":
            req = {"params": params or {}}
            url_params = {
                "req_did": caller_agent_obj.id,
                    "resp_did": target_agent_obj.id
            }
            url_params = urlencode(url_params)
            url = f"http://{target_agent_obj.host}:{target_agent_obj.port}/agent/api/{target_agent_path}{api_path}?{url_params}"
            status, response, info, is_auth_pass = await agent_auth_request(
                caller_agent, target_agent, url, method="POST", json_data=req
            )
        else:
            url_params = {
                "req_did": caller_agent_obj.id,
                "resp_did": target_agent_obj.id,
                "params": json.dumps(params) if params else ""
            }
            url_params = urlencode(url_params)
            url = f"http://{target_agent_obj.host}:{target_agent_obj.port}/agent/api/{target_agent_path}{api_path}?{url_params}"
            status, response, info, is_auth_pass = await agent_auth_request(
                caller_agent, target_agent, url, method="GET")
        return await handle_response(response)

async def agent_api_call_post(caller_agent: str, target_agent: str, api_path: str, params: Optional[Dict] = None) -> Dict:
    return await agent_api_call(caller_agent, target_agent, api_path, params, method="POST")

async def agent_api_call_get(caller_agent: str, target_agent: str, api_path: str, params: Optional[Dict] = None) -> Dict:
    return await agent_api_call(caller_agent, target_agent, api_path, params, method="GET")
