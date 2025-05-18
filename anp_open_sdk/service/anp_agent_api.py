#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import Optional, Dict, Any
import json
from urllib.parse import urlencode, quote
from loguru import logger
from anp_open_sdk.config.dynamic_config import dynamic_config
from anp_sdk import RemoteAgent
from anp_open_sdk.anp_sdk_utils import handle_response
from anp_open_sdk.anp_auth import check_response_DIDAtuhHeader
from anp_open_sdk.auth.did_auth import send_authenticated_request, send_request_with_token
from anp_core.agent_connect.authentication.did_wba_auth_header import DIDWbaAuthHeader
from anp_open_sdk.anp_sdk_utils import get_response_DIDAuthHeader_Token


async def agent_auth(sdk, caller_agent: str, target_agent: str) -> tuple[bool, str]:
    """执行智能体之间的认证
    
    Args:
        sdk: ANPSDK 实例
        caller_agent: 调用方智能体ID
        target_agent: 目标智能体ID
        
    Returns:
        tuple[bool, str]: (认证是否成功, 错误信息)
    """
    caller_agent_obj = sdk.get_agent(caller_agent)
    target_agent_obj = RemoteAgent(target_agent)
    auth_dir = dynamic_config.get("anp_sdk.auth_virtual_dir")

    auth_client = DIDWbaAuthHeader(
        did_document_path=str(caller_agent_obj.did_document_path),
        private_key_path=str(caller_agent_obj.private_key_path)
    )

    url_params = {
        "req_did": caller_agent_obj.id,
        "resp_did": target_agent_obj.id
    }
    url_params = urlencode(url_params)

    base_url = f"http://{target_agent_obj.host}:{target_agent_obj.port}"
    test_url = f"{base_url}/{auth_dir}?{url_params}"

    status, response, response_header, token = await send_authenticated_request(test_url, auth_client, str(target_agent_obj.id))
    
    auth_value, token = get_response_DIDAuthHeader_Token(response_header)

    if status != 200:
        error = f"发起方发出的DID认证失败! 状态: {status}\n响应: {response}"
        return False, error

    if await check_response_DIDAtuhHeader(auth_value) is False:
        error = f"\n接收方DID认证头验证失败! 状态: {status}\n响应: {response}"
        return False, error

    if token:
        status, response = await send_request_with_token(test_url, token, caller_agent_obj.id, target_agent_obj.id)
        
        if status == 200:
            caller_agent_obj.store_token_from_remote(target_agent_obj.id, token)
            error = f"\nDID认证成功! {caller_agent_obj.id} 已保存 {target_agent_obj.id}颁发的token:{token}"
            return True, error
        else:
            error = f"\n令牌认证失败! 状态: {status}\n响应: {response}"
            return False, error
    else:
        error = "未从服务器收到令牌"
        return False, error

async def agent_api_call_post(sdk, caller_agent: str, target_agent: str, api_path: str, params: Optional[Dict] = None) -> Dict:
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
    caller_agent_obj = sdk.get_agent(caller_agent)
    target_agent_obj = RemoteAgent(target_agent)

    if caller_agent_obj.get_token_from_remote(target_agent_obj.id) is None:
        status, error = await agent_auth(sdk, caller_agent, target_agent)
        if status is False:
            return error

    req = {"params": params or {}}
    
    url_params = {
        "req_did": caller_agent_obj.id,
        "resp_did": target_agent_obj.id
    }
    url_params = urlencode(url_params)
    target_agent_path = quote(target_agent)
    
    url = f"http://{target_agent_obj.host}:{target_agent_obj.port}/agent/api/{target_agent_path}{api_path}?{url_params}"
    token = caller_agent_obj.get_token_from_remote(target_agent_obj.id)["token"]

    status, response = await send_request_with_token(url, token, caller_agent_obj.id, target_agent_obj.id, method="POST", json_data=req)
    if status == 401:
        status, error = await agent_auth(sdk, caller_agent, target_agent)
        if status is False:
            return error
        else:
            token = caller_agent_obj.get_token_from_remote(target_agent_obj.id)["token"]
            status, response = await send_request_with_token(url, token, caller_agent_obj.id, target_agent_obj.id, method="POST", json_data=req)

    response = await handle_response(response)
    return response

async def agent_api_call_get(sdk, caller_agent: str, target_agent: str, api_path: str, params: Optional[Dict] = None) -> Dict:
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
    caller_agent_obj = sdk.get_agent(caller_agent)
    target_agent_obj = RemoteAgent(target_agent)

    if caller_agent_obj.get_token_from_remote(target_agent_obj.id) is None:
        status, error = await agent_auth(sdk, caller_agent, target_agent)
        if status is False:
            return error

    url_params = {
        "req_did": caller_agent_obj.id,
        "resp_did": target_agent_obj.id,
        "params": json.dumps(params) if params else ""
    }
    url_params = urlencode(url_params)
    target_agent_path = quote(target_agent)

    url = f"http://{target_agent_obj.host}:{target_agent_obj.port}/agent/api/{target_agent_path}{api_path}?{url_params}"
    token = caller_agent_obj.get_token_from_remote(target_agent_obj.id)["token"]

    status, response = await send_request_with_token(url, token, caller_agent_obj.id, target_agent_obj.id, method="GET")
    if status == 401:
        status, error = await agent_auth(sdk, caller_agent, target_agent)
        if status is False:
            return error
        else:
            token = caller_agent_obj.get_token_from_remote(target_agent_obj.id)["token"]
            status, response = await send_request_with_token(url, token, caller_agent_obj.id, target_agent_obj.id, method="GET")

    response = await handle_response(response)
    return response