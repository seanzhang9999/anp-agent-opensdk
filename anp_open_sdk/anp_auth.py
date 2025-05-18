#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from loguru import logger
from anp_open_sdk.auth.custom_did_resolver import resolve_local_did_document
from anp_core.agent_connect.authentication.did_wba import resolve_did_wba_document
from anp_core.agent_connect.authentication.did_wba import verify_auth_header_signature
from anp_open_sdk.auth.did_auth import extract_auth_header_parts, verify_timestamp, is_valid_server_nonce

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