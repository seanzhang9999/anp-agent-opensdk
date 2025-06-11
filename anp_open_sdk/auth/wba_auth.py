# anp_open_sdk/auth/wba_auth.py
from .base_auth import BaseDIDResolver, BaseDIDSigner, BaseAuthHeaderBuilder, BaseDIDAuthenticator
from .schemas import DIDDocument, DIDKeyPair, DIDCredentials, AuthenticationContext
import json
import base64
from typing import Optional, Dict, Any, Tuple

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
        # 实现WBA特定的认证头解析逻辑
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
    
    async def authenticate_request(self, context: AuthenticationContext, credentials: DIDCredentials) -> Tuple[bool, str, Dict[str, Any]]:
        """执行WBA认证请求"""
        # 实现完整的WBA认证流程，包含单向/双向认证逻辑
        pass
    
    async def verify_response(self, auth_header: str, context: AuthenticationContext) -> Tuple[bool, str]:
        """验证WBA响应"""
        # 实现响应验证逻辑
        pass