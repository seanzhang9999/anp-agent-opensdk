# anp_open_sdk/auth/wba_auth.py

from agent_connect.authentication import resolve_did_wba_document
from anp_open_sdk.config import get_global_config

from .did_auth_base import BaseDIDResolver, BaseDIDSigner, BaseAuthHeaderBuilder, BaseDIDAuthenticator, BaseAuth
from .did_auth_wba_custom_did_resolver import resolve_local_did_document
from .token_nonce_auth import verify_timestamp
from .schemas import DIDDocument, DIDKeyPair, DIDCredentials, AuthenticationContext
import json
import base64
from typing import Optional, Dict, Any, Tuple
import re
import logging
logger = logging.getLogger(__name__)

from agent_connect.authentication.did_wba import extract_auth_header_parts

from ..agent_connect_hotpatch.authentication.did_wba import extract_auth_header_parts_two_way, \
    verify_auth_header_signature_two_way
from ..anp_sdk_user_data import LocalUserDataManager



class WBADIDResolver(BaseDIDResolver):
    """WBA DID解析器实现"""
    
    async def resolve_did_document(self, did: str) -> Optional[DIDDocument]:
        """解析WBA DID文档"""
        try:
            # 先尝试本地解析
            from anp_open_sdk.auth.did_auth_wba_custom_did_resolver import resolve_local_did_document
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
    def build_auth_header(self, context, credentials):
        user_data_manager = LocalUserDataManager()
        user_data = user_data_manager.get_user_data(context.caller_did)

        did_document_path = user_data.did_doc_path
        private_key_path =user_data.did_private_key_file_path

        if context.use_two_way_auth:
            # 优先用 hotpatch 的 DIDWbaAuthHeader
            from anp_open_sdk.agent_connect_hotpatch.authentication.did_wba_auth_header import DIDWbaAuthHeader as TwoWayDIDWbaAuthHeader
            auth_client = TwoWayDIDWbaAuthHeader(
                did_document_path=did_document_path,
                private_key_path=private_key_path
            )
        else:
            # 用 agent_connect 的 DIDWbaAuthHeader
            from agent_connect.authentication.did_wba_auth_header import DIDWbaAuthHeader as OneWayDIDWbaAuthHeader
            auth_client = OneWayDIDWbaAuthHeader(
                did_document_path=did_document_path,
                private_key_path=private_key_path
            )

        # 判断是否有 get_auth_header_two_way 方法
        if hasattr(auth_client, 'get_auth_header_two_way'):
            # 双向认证
            auth_headers = auth_client.get_auth_header_two_way(
                context.request_url, context.target_did
            )
        else:
            # 单向/降级认证
            auth_headers = auth_client.get_auth_header(
                context.request_url
            )
        return auth_headers

    def parse_auth_header(self, auth_header: str) -> Dict[str, Any]:
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
        import aiohttp


        """执行WBA认证请求"""
        try:
            # 构建认证头
            auth_headers = self.header_builder.build_auth_header(context, credentials)
            request_url = context.request_url
            method = getattr(context, 'method', 'GET')
            json_data = getattr(context, 'json_data', None)
            custom_headers = getattr(context, 'custom_headers', None)
            resp_did = getattr(context, 'target_did', None)
            if custom_headers:
                # 合并认证头和自定义头，auth_headers 优先覆盖
                merged_headers = {**custom_headers ,**auth_headers}
            else:
                merged_headers = auth_headers
            # 发送带认证头的请求
            async with aiohttp.ClientSession() as session:
                if method.upper() == "GET":
                    async with session.get(request_url, headers=merged_headers) as response:
                        status = response.status
                        try:
                            response_data = await response.json()
                        except Exception:
                            response_text = await response.text()
                            try:
                                response_data = json.loads(response_text)
                            except Exception:
                                response_data = {"text": response_text}
                                # 检查 Authorization header
                        return status, response.headers, response_data
                elif method.upper() == "POST":
                    async with session.post(request_url, headers=merged_headers, json=json_data) as response:
                        status = response.status
                        try:
                            response_data = await response.json()
                        except Exception:
                            response_text = await response.text()
                            try:
                                response_data = json.loads(response_text)
                            except Exception:
                                response_data = {"text": response_text}
                        return status, response.headers, response_data
                else:
                    logger.debug(f"Unsupported HTTP method: {method}")
                    return False, "",{"error": "Unsupported HTTP method"}
        except Exception as e:
            logger.debug(f"Error in authenticate_request: {e}", exc_info=True)
            return False, "", {"error": str(e)}


    async def verify_response(self, auth_header: str  ,context: AuthenticationContext) -> Tuple[bool, str]:
        """验证WBA响应（借鉴 handle_did_auth 主要认证逻辑）"""
        try:
            from anp_open_sdk.agent_connect_hotpatch.authentication.did_wba import (
                extract_auth_header_parts_two_way, verify_auth_header_signature_two_way, resolve_did_wba_document
            )
            from anp_open_sdk.auth.did_auth_wba_custom_did_resolver import resolve_local_did_document



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
            config = get_global_config()
            nonce_expire_minutes = config.anp_sdk.nonce_expire_minutes
            from datetime import datetime, timezone
            try:
                request_time = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                current_time = datetime.now(timezone.utc)
                time_diff = abs((current_time - request_time).total_seconds() / 60)
                if time_diff > nonce_expire_minutes:
                    return False, f"Timestamp expired. Current time: {current_time}, Request time: {request_time}, Difference: {time_diff} minutes"
            except Exception as e:
                return False, f"Invalid timestamp: {e}"

            # Verify nonce validity
            from .auth_server import is_valid_server_nonce
            if not is_valid_server_nonce(nonce):
                logger.debug(f"Invalid or expired nonce: {nonce}")
                return False, f"Invalid nonce: {e}"
            else:
                logger.debug(f"nonce通过防重放验证{nonce}")

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
            from .auth_server import generate_auth_response

            header_parts = await generate_auth_response(did, is_two_way_auth, resp_did)
            return True, header_parts
        except Exception as e:
            return False, f"Exception in verify_response: {e}"

class WBAAuth(BaseAuth):
    def extract_did_from_auth_header(self, auth_header: str) -> Tuple[Optional[str], Optional[str]]:
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

def get_response_DIDAuthHeader_Token(response_header: Dict) -> Tuple[Optional[str], Optional[str]]:
    """从响应头中获取DIDAUTHHeader

    Args:
        response_header: 响应头字典

    Returns:
        Tuple[str, str]: (did_auth_header, token) 双向认证头和访问令牌
    """
    if "Authorization" in response_header:
        auth_value = response_header["Authorization"]
        if isinstance(auth_value, str) and auth_value.startswith('Bearer '):
                token = auth_value[7:]  # Extract token after 'Bearer '
                logger.debug("获得单向认证令牌，兼容无双向认证的服务")
                return "单向认证", token
        # If Authorization is a dict, execute existing logic
        else:
            try:
                auth_value =  response_header.get("Authorization")
                auth_value= json.loads(auth_value)
                token = auth_value[0].get("access_token")
                did_auth_header =auth_value[0].get("resp_did_auth_header", {}).get("Authorization")
                if did_auth_header and token:
                    logger.debug("令牌包含双向认证信息，进行双向校验")
                    return "双向认证", token
                else:
                    logger.error("[错误] 解析失败，缺少必要字段" + str(auth_value))
                    return None, None
            except Exception as e:
                logger.error("[错误] 处理 Authorization 字典时出错: " + str(e))
                return None, None
    else:
        logger.debug("response_header不包含'Authorization',无需处理令牌")
        return None, None

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
    logger.debug(f"用 {did}的{keyid}检验")

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

        logger.debug(f"签名验证结果: {is_valid}, 消息: {message}")
        return is_valid

    except Exception as e:
        logger.error(f"验证签名时出错: {e}")
        return False


