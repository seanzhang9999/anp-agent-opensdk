import json
import logging
logger = logging.getLogger(__name__)

import string
from typing import Optional, Dict, Tuple, Any

import aiohttp
from aiohttp import ClientResponse

from .did_auth_wba import WBAAuth, get_response_DIDAuthHeader_Token, check_response_DIDAtuhHeader
from ..anp_sdk_agent import LocalAgent
from ..anp_sdk_user_data import LocalUserDataManager
from ..auth.schemas import DIDCredentials, AuthenticationContext
from ..auth.did_auth_base import BaseDIDAuthenticator



def create_authenticator(auth_method: str = "wba") -> BaseDIDAuthenticator:
    if auth_method == "wba":
        from ..auth.did_auth_wba import WBADIDResolver, WBADIDSigner, WBAAuthHeaderBuilder, WBADIDAuthenticator
        resolver = WBADIDResolver()
        signer = WBADIDSigner()
        header_builder = WBAAuthHeaderBuilder()
        base_auth = WBAAuth()
        return WBADIDAuthenticator(resolver, signer, header_builder, base_auth)
    else:
        raise ValueError(f"Unsupported authentication method: {auth_method}")

class AgentAuthManager:
    """智能体认证管理器"""
    def __init__(self, authenticator: BaseDIDAuthenticator):
        self.authenticator = authenticator

    async def agent_auth_two_way_v2(
        self,
        caller_credentials: DIDCredentials,
        target_did: str,
        request_url: str,
        method: str = "GET",
        json_data: Optional[Dict] = None,
        custom_headers: Dict[str, str] = None,
        use_two_way_auth: bool = True
    ) -> Tuple[int, str, str, bool]:
        if custom_headers is None:
            custom_headers = {}
        context = AuthenticationContext(
            caller_did=caller_credentials.did_document.did,
            target_did=target_did,
            request_url=request_url,
            method=method,
            custom_headers=custom_headers,
            json_data=json_data,
            use_two_way_auth=use_two_way_auth
        )
        caller_agent = LocalAgent.from_did(context.caller_did)
        try:
            status_code, response_auth_header, response_data = await self.authenticator.authenticate_request(
                context, caller_credentials
            )
            if status_code == 401 or status_code == 403:
                context.use_two_way_auth = False
                status_code, response_auth_header, response_data = await self.authenticator.authenticate_request(
                    context, caller_credentials
                )
                if status_code != 401 and status_code != 403:
                    auth_value, token = get_response_DIDAuthHeader_Token(response_auth_header)
                    if token:
                        if auth_value != "单向认证":
                            response_auth_header = json.loads(response_auth_header.get("Authorization"))
                            response_auth_header = response_auth_header[0].get("resp_did_auth_header")
                            response_auth_header = response_auth_header.get("Authorization")
                            if not await check_response_DIDAtuhHeader(response_auth_header):
                                message = f"接收方DID认证头验证失败! 状态: {status_code}\n响应: {response_data}"
                                return status_code, response_data, message, False
                            caller_agent.contact_manager.store_token_from_remote(context.target_did, token)
                            message = f"DID双向认证成功! 已保存 {context.target_did} 颁发的token:{token}"
                            return status_code, response_data, message, True
                        else:
                            caller_agent.contact_manager.store_token_from_remote(context.target_did, token)
                            message = f"单向认证成功! 已保存 {context.target_did} 颁发的token:{token}"
                            return status_code, response_data, message, True
                    else:
                        message = "无token，可能是无认证页面或第一代协议"
                        return status_code, response_data, message, True
                else:
                    message = "401错误，认证失败"
                    return 401, '', message, False
            else:
                if status_code != 401 and status_code != 403:
                    auth_value, token = get_response_DIDAuthHeader_Token(response_auth_header)
                    if token:
                        if auth_value != "单向认证":
                            response_auth_header = json.loads(response_auth_header.get("Authorization"))
                            response_auth_header = response_auth_header[0].get("resp_did_auth_header")
                            response_auth_header = response_auth_header.get("Authorization")
                            if not await check_response_DIDAtuhHeader(response_auth_header):
                                message = f"接收方DID认证头验证失败! 状态: {status_code}\n响应: {response_data}"
                                return status_code, response_data, message, False
                            caller_agent.contact_manager.store_token_from_remote(context.target_did, token)
                            message = f"DID双向认证成功! 已保存 {context.target_did} 颁发的token:{token}"
                            return status_code, response_data, message, True
                        else:
                            caller_agent.contact_manager.store_token_from_remote(context.target_did, token)
                            message = f"单向认证成功! 已保存 {context.target_did} 颁发的token:{token}"
                            return status_code, response_data, message, True
                    else:
                        message = "无token，可能是无认证页面或第一代协议"
                        return status_code, response_data, message, True
                else:
                    message = "401错误，认证失败"
                    return 401, '', message, False
        except Exception as e:
            logger.error(f"认证过程中发生错误: {e}")
            return 500, '', f"认证错误: {str(e)}", False

async def agent_auth_request(
    caller_agent: str,
    target_agent: str,
    request_url,
    method: str = "GET",
    json_data: Optional[Dict] = None,
    custom_headers: Optional[Dict[str, str]] = None,
    use_two_way_auth: bool = True,
    auth_method: str = "wba"
) -> Tuple[int, str, str, bool]:
    """通用认证函数，自动优先用本地token，否则走DID认证，token失效自动fallback"""
    user_data_manager = LocalUserDataManager()
    user_data = user_data_manager.get_user_data(caller_agent)
    caller_credentials = DIDCredentials.from_paths(
        did_document_path=user_data.did_doc_path,
        private_key_path=str(user_data.did_private_key_file_path)
    )
    authenticator = create_authenticator(auth_method=auth_method)
    auth_manager = AgentAuthManager(authenticator)
    """
    暂时屏蔽token分支 token方案需要升级保证安全
    caller_agent_obj = LocalAgent.from_did(caller_credentials.did_document.did)
    token_info = caller_agent_obj.contact_manager.get_token_to_remote(target_agent)
    from datetime import datetime, timezone
    if token_info and not token_info.get("is_revoked", False):
        expires_at = token_info.get("expires_at")
        if isinstance(expires_at, str):
            expires_at = datetime.fromisoformat(expires_at)
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) < expires_at:
            token = token_info["token"]
            status, response_data = await agent_token_request(
                request_url, token, caller_credentials.did_document.did, target_agent, method, json_data
            )
            if status == 401 or status == 403:
                if hasattr(caller_agent_obj.contact_manager, 'revoke_token_from_remote'):
                    caller_agent_obj.contact_manager.revoke_token_from_remote(target_agent)
            else:
                return status, response_data, "token认证请求", status == 200
    """
    return await auth_manager.agent_auth_two_way_v2(
        caller_credentials=caller_credentials,
        target_did=target_agent,
        request_url=request_url,
        method=method,
        json_data=json_data,
        custom_headers=custom_headers,
        use_two_way_auth=use_two_way_auth
    )
async def handle_response(response: Any) -> Dict:
    if isinstance(response, dict):
        return response
    elif isinstance(response, ClientResponse):
        try:
            if response.status >= 400:
                error_text = await response.text()
                logger.error(f"HTTP错误 {response.status}: {error_text}")
                return {"error": f"HTTP {response.status}", "message": error_text}
            content_type = response.headers.get('Content-Type', '')
            if 'application/json' in content_type:
                return await response.json()
            else:
                text = await response.text()
                logger.warning(f"非JSON响应，Content-Type: {content_type}")
                return {"content": text, "content_type": content_type}
        except json.JSONDecodeError as e:
            logger.error(f"JSON解析失败: {e}")
            text = await response.text()
            return {"error": "JSON解析失败", "raw_text": text}
        except Exception as e:
            logger.error(f"处理响应时出错: {e}")
            return {"error": str(e)}
    else:
        logger.error(f"未知响应类型: {type(response)}")
        return {"error": f"未知类型: {type(response)}"}

async def agent_token_request(target_url: str, token: str, sender_did: str, targeter_did: string, method: str = "GET",
                              json_data: Optional[Dict] = None) -> Tuple[int, Dict[str, Any]]:
    try:

        #当前方案需要后续改进，当前并不安全
        headers = {
            "Authorization": f"Bearer {token}",
            "req_did": f"{sender_did}",
            "resp_did": f"{targeter_did}"
        }

        async with aiohttp.ClientSession() as session:
            if method.upper() == "GET":
                async with session.get(
                    target_url,
                    headers=headers
                ) as response:
                    status = response.status
                    response_data = await response.json() if status == 200 else {}
                    return status, response_data
            elif method.upper() == "POST":
                async with session.post(
                    target_url,
                    headers=headers,
                    json=json_data
                ) as response:
                    status = response.status
                    response_data = await response.json() if status == 200 else {}
                    return status, response_data
            else:
                logger.debug(f"Unsupported HTTP method: {method}")
                return 400, {"error": "Unsupported HTTP method"}
    except Exception as e:
        logger.debug(f"Error sending request with token: {e}")
        return 500, {"error": str(e)}
