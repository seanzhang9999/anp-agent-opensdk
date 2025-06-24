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

from anp_open_sdk.anp_sdk_agent import LocalAgent, RemoteAgent
from urllib.parse import urlencode, quote
from anp_open_sdk.config import get_global_config
from anp_open_sdk.auth.auth_client import agent_auth_request, handle_response

async def agent_msg_post(sdk, caller_agent: str, target_agent: str, content: str, message_type: str = "text"):
    """发送消息给目标智能体"""
    caller_agent_obj = LocalAgent.from_did(caller_agent)
    target_agent_obj = RemoteAgent(target_agent)
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
    config = get_global_config()
    msg_dir = config.anp_sdk.msg_virtual_dir
    url = f"http://{target_agent_obj.host}:{target_agent_obj.port}{msg_dir}/{target_agent_path}/post?{url_params}"

    status, response, info, is_auth_pass = await agent_auth_request(
        caller_agent, target_agent, url, method="POST", json_data=msg
    )
    return await handle_response(response)
