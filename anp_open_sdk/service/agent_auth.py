#!/usr/bin/env python3
# -*- coding: utf-8 -*-

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
import sys
import os
from typing import Optional, Dict
from urllib.parse import urlencode, quote
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from anp_open_sdk.anp_sdk_agent import LocalAgent
from anp_open_sdk.auth.did_auth import send_authenticated_request, send_request_with_token, DIDWbaAuthHeader, \
    get_response_DIDAuthHeader_Token
from loguru import logger
from anp_open_sdk.auth.custom_did_resolver import resolve_local_did_document
from agent_connect.authentication.did_wba import resolve_did_wba_document
from anp_open_sdk.auth.did_auth import verify_timestamp
from anp_open_sdk.agent_connect_hotpatch.authentication.did_wba import verify_auth_header_signature_two_way
from anp_open_sdk.agent_connect_hotpatch.authentication.did_wba import extract_auth_header_parts_two_way
from anp_open_sdk.anp_sdk import RemoteAgent

from anp_open_sdk.config.dynamic_config import dynamic_config
from anp_open_sdk.agent_connect_hotpatch.authentication.did_wba_auth_header import DIDWbaAuthHeader


async def check_response_DIDAtuhHeader(auth_value: str) -> bool:

    """检查响应头中的DIDAUTHHeader是否正确
    
    Args:
        auth_value: 认证头字符串
        
    Returns:
        bool: 验证是否成功
    """
    try:
        header_parts = extract_auth_header_parts_two_way(auth_value)
    except Exception as e:
        logger.error(f"无法从AuthHeader中解析信息: {e}")
        return False

    if not header_parts:
        logger.error("AuthHeader格式错误")
        return False

    did, nonce, timestamp, resp_did, keyid, signature = header_parts
    logger.info(f"用 {did}的{keyid}检验")

    if not verify_timestamp(timestamp):
        logger.error("Timestamp expired or invalid")
        return False

    # 尝试使用自定义解析器解析DID文档
    did_document = await resolve_local_did_document(did)

    # 如果自定义解析器失败，尝试使用标准解析器
    if not did_document:
        try:
            did_document = await resolve_did_wba_document(did)
        except Exception as e:
            logger.error(f"标准DID解析器也失败: {e}")
            return False
        
    if not did_document:
        logger.error("Failed to resolve DID document")
        return False

    try:
        # 重新构造完整的授权头
        full_auth_header = auth_value
        target_url = "virtual.WBAback" # 迁就现在的url parse代码

        # 调用验证函数
        is_valid, message = verify_auth_header_signature_two_way(
            auth_header=full_auth_header,
            did_document=did_document,
            service_domain=target_url
        )

        logger.info(f"签名验证结果: {is_valid}, 消息: {message}")
        return is_valid

    except Exception as e:
        logger.error(f"验证签名时出错: {e}")
        return False

async def agent_auth_two_way(sdk, caller_agent: str, target_agent: str , request_url, method: str = "GET",json_data: Optional[Dict] = None,
    custom_headers: dict[str,str] = None, use_two_way_auth: bool = False # 是否使用双向认证
                             ) -> tuple[bool, str]:
    """执行智能体之间的认证
    
    Args:
        sdk: ANPSDK 实例
        caller_agent: 调用方智能体ID
        target_agent: 目标智能体ID
        
    Returns:
        tuple[bool, str]: (认证是否成功, 错误信息)
    """

    if custom_headers is None:
        custom_headers = {}
    caller_agent_obj = LocalAgent(sdk,caller_agent)

    target_agent_obj = RemoteAgent(target_agent)


    user_data_manager = sdk.user_data_manager

    user_data = user_data_manager.get_user_data (caller_agent)
    did_document_path = user_data.did_doc_path



    from anp_open_sdk.agent_connect_hotpatch.authentication.did_wba_auth_header import DIDWbaAuthHeader
    auth_client = DIDWbaAuthHeader(
        did_document_path=did_document_path,
        private_key_path=str(user_data.did_private_key_file_path)
    )



    status, response, response_header, token = await send_authenticated_request(
        target_url = request_url,auth_client=  auth_client, resp_did = str(target_agent_obj.id), custom_headers= custom_headers, method=method, json_data = json_data)
    
    if status!= 401:
        auth_value, token = get_response_DIDAuthHeader_Token(response_header)
        if token:
            if auth_value != "单向认证":
                if await check_response_DIDAtuhHeader(auth_value) is False:
                    info = f"\n接收方DID认证头验证失败! 状态: {status}\n响应: {response}"
                    return status, response, info, False
                else:
                    caller_agent_obj.store_token_from_remote(target_agent_obj.id, token)
                    info = f"\nDID双向认证成功! {caller_agent_obj.id} 已保存 {target_agent_obj.id}颁发的token:{token}"
                    return status, response, info, True
        else:
            info = f"\n不是401，无token，应该是无认证页面"
            return status, response, info, True

    else:
        # 回落尝试单向认证
        from agent_connect.authentication.did_wba_auth_header import DIDWbaAuthHeader
        auth_client = DIDWbaAuthHeader(
            did_document_path=did_document_path,
            private_key_path=str(user_data.did_private_key_file_path)
        )
        status, response, response_header, token = await send_authenticated_request(
            target_url=request_url, auth_client=auth_client, resp_did=str(target_agent_obj.id),
            custom_headers=custom_headers, method=method, json_data=json_data)
        if status != 401:
            auth_value, token = get_response_DIDAuthHeader_Token(response_header)
            if auth_value == "单向认证" and token:
                info = f"\n尝试单向认证头认证成功! 状态: {status}\n响应: {response}\nDID认证成功! {caller_agent_obj.id} 已保存 {target_agent_obj.id}颁发的token:{token}"
                caller_agent_obj.store_token_from_remote(target_agent_obj.id, token)
                return status, response, info , True
            else:
                info = f"\n单向认证通过没有返回token，应该是第一代协议，无token继续"
                return status, response, info, True
        else:
            info = f"发起方发出的DID认证失败! 状态: {status}\n响应: {response}"
            return status, response, info , False


        