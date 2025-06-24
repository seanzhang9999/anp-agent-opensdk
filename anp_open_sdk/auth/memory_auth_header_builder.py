# anp_open_sdk/auth/memory_auth_header_builder.py

"""
内存版本的认证头构建器

这个模块提供了不依赖文件路径的认证头构建功能，直接使用内存中的密钥数据。
"""

import json
import base64
import hashlib
from datetime import datetime, timezone
from typing import Dict, Any, Optional
import logging

from .schemas import DIDCredentials, AuthenticationContext
from .did_auth_base import BaseAuthHeaderBuilder

logger = logging.getLogger(__name__)

class MemoryWBAAuthHeaderBuilder(BaseAuthHeaderBuilder):
    """基于内存数据的WBA认证头构建器"""
    
    def build_auth_header(self, context: AuthenticationContext, credentials: DIDCredentials) -> Dict[str, str]:
        """使用内存中的凭证数据构建认证头"""
        try:
            # 获取密钥对
            key_pair = credentials.get_key_pair("key-1")
            if not key_pair:
                raise ValueError("未找到密钥对")
            
            # 生成nonce和时间戳
            import secrets
            nonce = secrets.token_hex(16)
            timestamp = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
            
            # 构建签名载荷
            if context.use_two_way_auth:
                # 双向认证格式
                payload_parts = [
                    f"did={credentials.did_document.did}",
                    f"nonce={nonce}",
                    f"timestamp={timestamp}",
                    f"resp_did={context.target_did}",
                    f"url={context.request_url}"
                ]
            else:
                # 单向认证格式
                payload_parts = [
                    f"did={credentials.did_document.did}",
                    f"nonce={nonce}",
                    f"timestamp={timestamp}",
                    f"url={context.request_url}"
                ]
            
            payload = "&".join(payload_parts)
            
            # 使用私钥签名
            signature = self._sign_payload(payload, key_pair.private_key)
            
            # 构建认证头
            if context.use_two_way_auth:
                auth_header = (
                    f"DID-WBA did={credentials.did_document.did}, "
                    f"nonce={nonce}, "
                    f"timestamp={timestamp}, "
                    f"resp_did={context.target_did}, "
                    f"keyid=key-1, "
                    f"signature={signature}"
                )
            else:
                auth_header = (
                    f"DID-WBA did={credentials.did_document.did}, "
                    f"nonce={nonce}, "
                    f"timestamp={timestamp}, "
                    f"keyid=key-1, "
                    f"signature={signature}"
                )
            
            return {"Authorization": auth_header}
            
        except Exception as e:
            logger.error(f"构建认证头失败: {e}")
            raise
    
    def _sign_payload(self, payload: str, private_key_bytes: bytes) -> str:
        """使用私钥签名载荷"""
        try:
            from cryptography.hazmat.primitives.asymmetric import ec
            from cryptography.hazmat.primitives import hashes
            
            # 从字节重建私钥对象
            private_key_obj = ec.derive_private_key(
                int.from_bytes(private_key_bytes, byteorder="big"), 
                ec.SECP256K1()
            )
            
            # 签名
            signature_bytes = private_key_obj.sign(
                payload.encode('utf-8'),
                ec.ECDSA(hashes.SHA256())
            )
            
            # 转换为base64
            return base64.b64encode(signature_bytes).decode('utf-8')
            
        except Exception as e:
            logger.error(f"签名失败: {e}")
            raise
    
    def parse_auth_header(self, auth_header: str) -> Dict[str, Any]:
        """解析认证头（继承自基类的实现）"""
        try:
            # 移除 "DID-WBA " 前缀
            if auth_header.startswith("DID-WBA "):
                auth_header = auth_header[8:]
            
            # 解析参数
            params = {}
            for part in auth_header.split(", "):
                if "=" in part:
                    key, value = part.split("=", 1)
                    params[key.strip()] = value.strip()
            
            return params
            
        except Exception as e:
            logger.error(f"解析认证头失败: {e}")
            return {}

class MemoryAuthHeaderWrapper:
    """内存认证头包装器，兼容现有的DIDWbaAuthHeader接口"""
    
    def __init__(self, credentials: DIDCredentials):
        self.credentials = credentials
        self.builder = MemoryWBAAuthHeaderBuilder()
    
    def get_auth_header_two_way(self, target_url: str, target_did: str) -> Dict[str, str]:
        """生成双向认证头"""
        context = AuthenticationContext(
            caller_did=self.credentials.did_document.did,
            target_did=target_did,
            request_url=target_url,
            use_two_way_auth=True
        )
        return self.builder.build_auth_header(context, self.credentials)
    
    def get_auth_header(self, target_url: str) -> Dict[str, str]:
        """生成单向认证头"""
        context = AuthenticationContext(
            caller_did=self.credentials.did_document.did,
            target_did="",
            request_url=target_url,
            use_two_way_auth=False
        )
        return self.builder.build_auth_header(context, self.credentials)

def create_memory_auth_header_client(credentials: DIDCredentials) -> MemoryAuthHeaderWrapper:
    """创建基于内存数据的认证头客户端"""
    return MemoryAuthHeaderWrapper(credentials)
