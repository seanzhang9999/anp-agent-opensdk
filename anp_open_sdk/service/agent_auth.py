#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import os
from urllib.parse import urlencode, quote
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from anp_open_sdk.anp_sdk_utils import get_response_DIDAuthHeader_Token
from anp_open_sdk.auth.did_auth import send_authenticated_request, send_request_with_token, DIDWbaAuthHeader
from loguru import logger
from anp_open_sdk.auth.custom_did_resolver import resolve_local_did_document
from anp_core.agent_connect.authentication.did_wba import resolve_did_wba_document
from anp_core.agent_connect.authentication.did_wba import verify_auth_header_signature
from anp_open_sdk.auth.did_auth import extract_auth_header_parts, verify_timestamp, is_valid_server_nonce
from anp_sdk import RemoteAgent
async def check_response_DIDAtuhHeader(auth_value: str) -> bool:

    """检查响应头中的DIDAUTHHeader是否正确
    
    Args:
        auth_value: 认证头字符串
        
    Returns:
        bool: 验证是否成功
    """
    try:
        header_parts = extract_auth_header_parts(auth_value)
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
        is_valid, message = verify_auth_header_signature(
            auth_header=full_auth_header,
            did_document=did_document,
            service_domain=target_url
        )

        logger.info(f"签名验证结果: {is_valid}, 消息: {message}")
        return is_valid

    except Exception as e:
        logger.error(f"验证签名时出错: {e}")
        return False
from anp_open_sdk.config.dynamic_config import dynamic_config
from anp_core.agent_connect.authentication.did_wba_auth_header import DIDWbaAuthHeader

async def agent_auth_two_way(sdk, caller_agent: str, target_agent: str) -> tuple[bool, str]:
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

        