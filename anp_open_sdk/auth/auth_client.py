from typing import Optional, Dict, Tuple
from ..auth.schemas import DIDCredentials, AuthenticationContext
from ..auth.base_auth import BaseDIDAuthenticator
from loguru import logger

# 工厂函数，根据配置/参数选择具体认证器
def create_authenticator(auth_method: str = "wba") -> BaseDIDAuthenticator:
    if auth_method == "wba":
        from ..auth.wba_auth import WBADIDResolver, WBADIDSigner, WBAAuthHeaderBuilder, WBADIDAuthenticator
        resolver = WBADIDResolver()
        signer = WBADIDSigner()
        header_builder = WBAAuthHeaderBuilder()
        return WBADIDAuthenticator(resolver, signer, header_builder)
    # 未来可扩展其他认证方式
    else:
        raise ValueError(f"Unsupported authentication method: {auth_method}")

class AgentAuthManager:
    """智能体认证管理器"""
    def __init__(self, authenticator: BaseDIDAuthenticator):
        self.authenticator = authenticator

    async def agent_auth_two_way_v2(
        self,
        sdk,
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
        try:
            success, message, response_data = await self.authenticator.authenticate_request(
                context, caller_credentials
            )
            if success:
                status_code = response_data.get('status', 200) if isinstance(response_data, dict) else 200
                response_body = response_data.get('response', '') if isinstance(response_data, dict) else str(response_data)
                return status_code, response_body, message, True
            else:
                return 401, '', message, False
        except Exception as e:
            logger.error(f"认证过程中发生错误: {e}")
            return 500, '', f"认证错误: {str(e)}", False

async def agent_auth_two_way(
    sdk,
    caller_agent: str,
    target_agent: str,
    request_url,
    method: str = "GET",
    json_data: Optional[Dict] = None,
    custom_headers: Optional[Dict[str, str]] = None,
    use_two_way_auth: bool = False,
    auth_method: str = "wba"
) -> Tuple[int, str, str, bool]:
    """通用认证函数，支持多种认证方式"""
    user_data_manager = sdk.user_data_manager
    user_data = user_data_manager.get_user_data(caller_agent)
    caller_credentials = DIDCredentials.from_paths(
        did_document_path=user_data.did_doc_path,
        private_key_path=str(user_data.did_private_key_file_path)
    )
    authenticator = create_authenticator(auth_method=auth_method)
    auth_manager = AgentAuthManager(authenticator)
    return await auth_manager.agent_auth_two_way_v2(
        sdk=sdk,
        caller_credentials=caller_credentials,
        target_did=target_agent,
        request_url=request_url,
        method=method,
        json_data=json_data,
        custom_headers=custom_headers,
        use_two_way_auth=use_two_way_auth
    )
