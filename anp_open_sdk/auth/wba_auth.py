# anp_open_sdk/auth/wba_auth.py
from .base_auth import BaseDIDResolver, BaseDIDSigner, BaseAuthHeaderBuilder, BaseDIDAuthenticator, BaseAuth
from .schemas import DIDDocument, DIDKeyPair, DIDCredentials, AuthenticationContext
import json
import base64
from typing import Optional, Dict, Any, Tuple
import re
from loguru import logger

from agent_connect.authentication.did_wba import extract_auth_header_parts



def parse_wba_did_host_port(did: str) -> Tuple[Optional[str], Optional[int]]:
    """
    从 did:wba:host%3Aport:xxxx / did:wba:host:port:xxxx / did:wba:host:xxxx
    解析 host 和 port
    """
    m = re.match(r"did:wba:([^%:]+)%3A(\d+):", did)
    if m:
        return m.group(1), int(m.group(2))
    m = re.match(r"did:wba:([^:]+):(\d+):", did)
    if m:
        return m.group(1), int(m.group(2))
    m = re.match(r"did:wba:([^:]+):", did)
    if m:
        return m.group(1), 80
    return None, None

class WBADIDResolver(BaseDIDResolver):
    """WBA DID解析器实现"""
    
    async def resolve_did_document(self, did: str) -> Optional[DIDDocument]:
        """解析WBA DID文档"""
        try:
            # 先尝试本地解析
            from anp_open_sdk.auth.custom_did_resolver import resolve_local_did_document
            did_doc_dict = await resolve_local_did_document(did)
            
            if not did_doc_dict:
                # 回退到标准解析器
                from agent_connect.authentication.did_wba import resolve_did_wba_document
                did_doc_dict = await resolve_did_wba_document(did)
            
            if did_doc_dict:
                return DIDDocument(
                    did=did_doc_dict.get('id', did),
                    verification_methods=did_doc_dict.get('verificationMethod', []),
                    authentication=did_doc_dict.get('authentication', []),
                    service_endpoints=did_doc_dict.get('service', []),
                    raw_document=did_doc_dict
                )
            
        except Exception as e:
            logger.error(f"DID解析失败: {e}")
        
        return None
    
    def supports_did_method(self, did: str) -> bool:
        """检查是否支持WBA DID方法"""
        return did.startswith("did:wba:") or did.startswith("did:key:")

class WBADIDSigner(BaseDIDSigner):
    """WBA DID签名器实现"""
    
    def sign_payload(self, payload: str, key_pair: DIDKeyPair) -> str:
        """使用Ed25519签名"""
        from cryptography.hazmat.primitives.asymmetric import ed25519
        
        private_key_obj = ed25519.Ed25519PrivateKey.from_private_bytes(key_pair.private_key)
        signature_bytes = private_key_obj.sign(payload.encode('utf-8'))
        return base64.b64encode(signature_bytes).decode('utf-8')
    
    def verify_signature(self, payload: str, signature: str, public_key: bytes) -> bool:
        """验证Ed25519签名"""
        try:
            from cryptography.hazmat.primitives.asymmetric import ed25519
            
            public_key_obj = ed25519.Ed25519PublicKey.from_public_bytes(public_key)
            signature_bytes = base64.b64decode(signature)
            public_key_obj.verify(signature_bytes, payload.encode('utf-8'))
            return True
        except Exception as e:
            logger.error(f"签名验证失败: {e}")
            return False

class WBAAuthHeaderBuilder(BaseAuthHeaderBuilder):
    """WBA认证头构建器实现"""
    
    def build_auth_header(self, context: AuthenticationContext, credentials: DIDCredentials) -> str:
        """构建WBA认证头"""
        # 实现WBA特定的认证头构建逻辑
        # 基于现有的DIDWbaAuthHeader逻辑
        pass
    
    def parse_auth_header(self, auth_header: str) -> Dict[str, Any]:
        """解析WBA认证头"""
        from anp_open_sdk.agent_connect_hotpatch.authentication.did_wba import extract_auth_header_parts_two_way
        
        try:
            header_parts = extract_auth_header_parts_two_way(auth_header)
            if header_parts:
                did, nonce, timestamp, resp_did, keyid, signature = header_parts
                return {
                    'did': did,
                    'nonce': nonce,
                    'timestamp': timestamp,
                    'resp_did': resp_did,
                    'key_id': keyid,
                    'signature': signature
                }
        except Exception as e:
            logger.error(f"解析认证头失败: {e}")
        
        return {}

class WBADIDAuthenticator(BaseDIDAuthenticator):
    """WBA DID认证器实现"""

    def __init__(self, resolver, signer, header_builder, base_auth):
        super().__init__(resolver, signer, header_builder, base_auth)
        # 其他初始化（如有）

    async def authenticate_request(self, context: AuthenticationContext, credentials: DIDCredentials) -> Tuple[bool, str, Dict[str, Any]]:
        """执行WBA认证请求"""
        # 实现完整的WBA认证流程，包含单向/双向认证逻辑
        pass


    async def verify_response(self, auth_header: str, sdk  ,context: AuthenticationContext) -> Tuple[bool, str]:
        """验证WBA响应（借鉴 handle_did_auth 主要认证逻辑）"""
        try:
            from anp_open_sdk.agent_connect_hotpatch.authentication.did_wba import (
                extract_auth_header_parts_two_way, verify_auth_header_signature_two_way, resolve_did_wba_document
            )
            from anp_open_sdk.auth.custom_did_resolver import resolve_local_did_document
            from anp_open_sdk.config.dynamic_config import dynamic_config
            import logging

            # 1. 尝试解析为两路认证
            try:
                header_parts = extract_auth_header_parts_two_way(auth_header)
                if not header_parts:
                    return False, "Invalid authorization header format"
                did, nonce, timestamp, resp_did, keyid, signature = header_parts
                is_two_way_auth = True
            except (ValueError, TypeError) as e:
                # 回退到标准认证
                try:
                    from agent_connect.authentication.did_wba import extract_auth_header_parts
                    header_parts = extract_auth_header_parts(auth_header)
                    if not header_parts or len(header_parts) < 4:
                        return False, "Invalid standard authorization header"
                    did, nonce, timestamp, keyid, signature = header_parts
                    resp_did = None
                    is_two_way_auth = False
                except Exception as fallback_error:
                    return False, f"Authentication parsing failed: {fallback_error}"

            # 2. 验证时间戳
            nonce_expire_minutes = dynamic_config.get('anp_sdk.nonce_expire_minutes')
            from datetime import datetime, timezone
            try:
                request_time = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                current_time = datetime.now(timezone.utc)
                time_diff = abs((current_time - request_time).total_seconds() / 60)
                if time_diff > nonce_expire_minutes:
                    return False, f"Timestamp expired. Current time: {current_time}, Request time: {request_time}, Difference: {time_diff} minutes"
            except Exception as e:
                return False, f"Invalid timestamp: {e}"

            # 3. 解析DID文档
            did_document = await resolve_local_did_document(did)
            if not did_document:
                try:
                    did_document = await resolve_did_wba_document(did)
                except Exception as e:
                    return False, f"Failed to resolve DID document: {e}"
            if not did_document:
                return False, "Failed to resolve DID document"

            # 4. 验证签名
            try:
                if is_two_way_auth:
                    is_valid, message = verify_auth_header_signature_two_way(
                        auth_header=auth_header,
                        did_document=did_document,
                        service_domain=context.domain if hasattr(context, 'domain') else None
                    )
                else:
                    from agent_connect.authentication.did_wba import verify_auth_header_signature
                    is_valid, message = verify_auth_header_signature(
                        auth_header=auth_header,
                        did_document=did_document,
                        service_domain=context.domain if hasattr(context, 'domain') else None
                    )
                if not is_valid:
                    return False, f"Invalid signature: {message}"
            except Exception as e:
                return False, f"Error verifying signature: {e}"

            from .did_auth import generate_auth_response
            header_parts = await generate_auth_response(did, is_two_way_auth, resp_did, sdk)
            return True, header_parts
        except Exception as e:
            return False, f"Exception in verify_response: {e}"

class WBAAuth(BaseAuth):
    def extract_dids_from_auth_header(self, auth_header: str) -> Tuple[Optional[str], Optional[str]]:
        """
        支持两路和标准认证头的 DID 提取
        """
        try:
            # 优先尝试两路认证
            from anp_open_sdk.agent_connect_hotpatch.authentication.did_wba import extract_auth_header_parts_two_way
            parts = extract_auth_header_parts_two_way(auth_header)
            if parts and len(parts) == 6:
                did, nonce, timestamp, resp_did, keyid, signature = parts
                return did, resp_did
        except Exception:
            pass

        try:
            # 回退到标准认证
            parts = extract_auth_header_parts(auth_header)
            if parts and len(parts) >= 4:
                did, nonce, timestamp, keyid, signature = parts
                return did, None
        except Exception:
            pass

        return None, None
