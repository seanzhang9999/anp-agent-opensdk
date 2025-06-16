# anp_open_sdk/auth/wba_auth.py

from agent_connect.authentication import resolve_did_wba_document

from .did_auth_base import (
    BaseDIDResolver,
    BaseDIDSigner,
    BaseAuthHeaderBuilder,
    BaseDIDAuthenticator,
    BaseAuth,
    BaseDIDUserManager,
)
from .did_auth_wba_custom_did_resolver import resolve_local_did_document
from .token_nonce_auth import verify_timestamp
from .schemas import (
    DIDDocument,
    DIDKeyPair,
    DIDCredentials,
    AuthenticationContext,
    DIDUser,
)
import json
import base64
from typing import Optional, Dict, Any, Tuple, List
import re
from loguru import logger
                    from agent_connect.authentication.did_wba import extract_auth_header_parts

from ..agent_connect_hotpatch.authentication.did_wba import (
    extract_auth_header_parts_two_way,
    verify_auth_header_signature_two_way,
                    )
from ..anp_sdk_user_data import LocalUserDataManager

from anp_open_sdk.anp_sdk_user_data import (
    save_user_to_file,
    load_user_from_file,
    list_all_users_from_file,
                    )

import secrets
import os
import yaml
from datetime import datetime

from Crypto.PublicKey import RSA

class WBADIDResolver(BaseDIDResolver):
    """WBA DID解析器实现"""

    async def resolve_did_document(self, did: str) -> Optional[DIDDocument]:
        """解析WBA DID文档"""
        try:
            from anp_open_sdk.auth.did_auth_wba_custom_did_resolver import resolve_local_did_document
            did_doc_dict = await resolve_local_did_document(did)

            if not did_doc_dict:
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
        private_key_path = user_data.did_private_key_file_path

        if context.use_two_way_auth:
            from anp_open_sdk.agent_connect_hotpatch.authentication.did_wba_auth_header import DIDWbaAuthHeader as TwoWayDIDWbaAuthHeader
            auth_client = TwoWayDIDWbaAuthHeader(
                did_document_path=did_document_path,
                private_key_path=private_key_path
        )
        else:
            from agent_connect.authentication.did_wba_auth_header import DIDWbaAuthHeader as OneWayDIDWbaAuthHeader
            auth_client = OneWayDIDWbaAuthHeader(
                did_document_path=did_document_path,
                private_key_path=private_key_path
            )

        if hasattr(auth_client, 'get_auth_header_two_way'):
            auth_headers = auth_client.get_auth_header_two_way(
                context.request_url, context.target_did
            )
        else:
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

    async def authenticate_request(self, context: AuthenticationContext, credentials: DIDCredentials) -> Tuple[bool, str, Dict[str, Any]]:
        import aiohttp
        import logging
        try:
            auth_headers = self.header_builder.build_auth_header(context, credentials)
            request_url = context.request_url
            method = getattr(context, 'method', 'GET')
            json_data = getattr(context, 'json_data', None)
            custom_headers = getattr(context, 'custom_headers', None)
            resp_did = getattr(context, 'target_did', None)
            if custom_headers:
                merged_headers = {**custom_headers, **auth_headers}
            else:
                merged_headers = auth_headers
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
                    logging.error(f"Unsupported HTTP method: {method}")
                    return False, "", {"error": "Unsupported HTTP method"}
        except Exception as e:
            logging.error(f"Error in authenticate_request: {e}", exc_info=True)
            return False, "", {"error": str(e)}

    async def verify_response(self, auth_header: str, context: AuthenticationContext) -> Tuple[bool, str]:
        try:
            from anp_open_sdk.agent_connect_hotpatch.authentication.did_wba import (
                extract_auth_header_parts_two_way, verify_auth_header_signature_two_way, resolve_did_wba_document
            )
            from anp_open_sdk.auth.did_auth_wba_custom_did_resolver import resolve_local_did_document
            from anp_open_sdk.config.legacy.dynamic_config import dynamic_config
            import logging

            try:
                header_parts = extract_auth_header_parts_two_way(auth_header)
                if not header_parts:
                    return False, "Invalid authorization header format"
                did, nonce, timestamp, resp_did, keyid, signature = header_parts
                is_two_way_auth = True
            except (ValueError, TypeError) as e:
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

            from .auth_server import is_valid_server_nonce
            if not is_valid_server_nonce(nonce):
                logging.error(f"Invalid or expired nonce: {nonce}")
                return False, f"Invalid nonce: {e}"
            else:
                logger.info(f"nonce通过防重放验证{nonce}")

            did_document = await resolve_local_did_document(did)
            if not did_document:
                try:
                    did_document = await resolve_did_wba_document(did)
                except Exception as e:
                    return False, f"Failed to resolve DID document: {e}"
            if not did_document:
                return False, "Failed to resolve DID document"

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
        try:
            from anp_open_sdk.agent_connect_hotpatch.authentication.did_wba import extract_auth_header_parts_two_way
            parts = extract_auth_header_parts_two_way(auth_header)
            if parts and len(parts) == 6:
                did, nonce, timestamp, resp_did, keyid, signature = parts
                return did, resp_did
        except Exception:
            pass

        try:
            parts = extract_auth_header_parts(auth_header)
            if parts and len(parts) >= 4:
                did, nonce, timestamp, keyid, signature = parts
                return did, None
        except Exception:
            pass

        return None, None

def parse_wba_did_host_port(did: str) -> Tuple[Optional[str], Optional[int]]:
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
    if "Authorization" in response_header:
        auth_value = response_header["Authorization"]
        if isinstance(auth_value, str) and auth_value.startswith('Bearer '):
            token = auth_value[7:]
            logger.info("获得单向认证令牌，兼容无双向认证的服务")
            return "单向认证", token
        else:
            try:
                auth_value = response_header.get("Authorization")
                auth_value = json.loads(auth_value)
                token = auth_value[0].get("access_token")
                did_auth_header = auth_value[0].get("resp_did_auth_header", {}).get("Authorization")
                if did_auth_header and token:
                    logger.info("令牌包含双向认证信息，进行双向校验")
                    return "双向认证", token
                else:
                    logger.error("[错误] 解析失败，缺少必要字段" + str(auth_value))
                    return None, None
            except Exception as e:
                logger.error("[错误] 处理 Authorization 字典时出错: " + str(e))
                return None, None
    else:
        logger.info("response_header不包含'Authorization',无需处理令牌")
        return None, None

async def check_response_DIDAtuhHeader(auth_value: str) -> bool:
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

    did_document = await resolve_local_did_document(did)

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
        full_auth_header = auth_value
        target_url = "virtual.WBAback"
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

class WBADIDUserManager(BaseDIDUserManager):
    """WBA DID用户管理实现"""

    def create_user(self, params: Dict[str, Any]) -> DIDUser:
        unique_id = secrets.token_hex(8)
        path_segments = [params['dir'], params['type'], unique_id]
        agent_description_url = f"http://{params['host']}:{params['port']}/{params['dir']}/{params['type']}{unique_id}/ad.json"
        from agent_connect.authentication.did_wba import create_did_wba_document
        did_document, keys = create_did_wba_document(
            hostname=params['host'],
            port=params['port'],
            path_segments=path_segments,
            agent_description_url=agent_description_url
        )
        did_id = did_document['id']
        key_id = did_document.get('key_id') or list(keys.keys())[0]
        agent_cfg = {
            "name": params['name'],
            "unique_id": unique_id,
            "did": did_id,
            "type": params['type'],
            "owner": {"name": "anpsdk 创造用户", "@id": "https://localhost"},
            "description": params.get("description", "anpsdk的测试用户"),
            "version": "0.1.0",
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        user_dir = params.get("user_dir") or f"user_{unique_id}"
        user_dir_path = os.path.abspath(user_dir)
        try:
            os.makedirs(user_dir_path, exist_ok=True)
            # 写 agent_cfg.yaml
            with open(os.path.join(user_dir_path, "agent_cfg.yaml"), "w", encoding="utf-8") as f:
                yaml.dump(agent_cfg, f, allow_unicode=True, sort_keys=False)
            # 写 did_document.json
            with open(os.path.join(user_dir_path, "did_document.json"), "w", encoding="utf-8") as f:
                json.dump(did_document, f, indent=4, ensure_ascii=False)
            # 写密钥
            for kid, (priv, pub) in keys.items():
                with open(os.path.join(user_dir_path, f"{kid}_private.pem"), "wb") as f:
                    f.write(priv)
                with open(os.path.join(user_dir_path, f"{kid}_public.pem"), "wb") as f:
                    f.write(pub)
            # 生成JWT密钥对
            try:
            rsa_key = RSA.generate(2048)
            private_jwt = rsa_key.export_key()
            public_jwt = rsa_key.publickey().export_key()
            jwt_private_key_path = os.path.join(user_dir_path, "private_key.pem")
            jwt_public_key_path = os.path.join(user_dir_path, "public_key.pem")
            with open(jwt_private_key_path, "wb") as f:
                f.write(private_jwt)
            with open(jwt_public_key_path, "wb") as f:
                f.write(public_jwt)
        except Exception as e:
            raise RuntimeError(f"JWT密钥生成失败: {e}")
        except Exception as e:
            import shutil
            shutil.rmtree(user_dir_path, ignore_errors=True)
            raise RuntimeError(f"创建DID用户文件失败: {e}")

        return DIDUser(
            name=agent_cfg["name"],
            unique_id=agent_cfg["unique_id"],
            did=agent_cfg["did"],
            agent_type=agent_cfg["type"],
            cfg=agent_cfg,
            did_document=did_document,
            did_document_path=os.path.join(user_dir_path, "did_document.json"),
            key_id=key_id,
            did_private_key_path=os.path.join(user_dir_path, f"{key_id}_private.pem"),
            did_public_key_path=os.path.join(user_dir_path, f"{key_id}_public.pem"),
            jwt_private_key_path=os.path.join(user_dir_path, "private_key.pem"),
            jwt_public_key_path=os.path.join(user_dir_path, "public_key.pem"),
            user_dir=user_dir_path,
            created_at=agent_cfg["created_at"],
            owner=agent_cfg.get("owner"),
            hosted_config=agent_cfg.get("hosted_config")
        )

    def save_user(self, user: DIDUser):
        save_user_to_file(user)

    def load_user(self, did: str) -> Optional[DIDUser]:
        return load_user_from_file(did)

    def list_users(self) -> list:
        return list_all_users_from_file()
