# anp_open_sdk/service/agent_auth_v2.py
from typing import Optional, Dict, Tuple
from ..auth.schemas import DIDCredentials, AuthenticationContext
from ..auth.wba_auth import WBADIDResolver, WBADIDSigner, WBAAuthHeaderBuilder, WBADIDAuthenticator
from loguru import logger

class AgentAuthManager:
    """智能体认证管理器"""
    
    def __init__(self):
        # 初始化WBA认证器
        self.wba_resolver = WBADIDResolver()
        self.wba_signer = WBADIDSigner()
        self.wba_header_builder = WBAAuthHeaderBuilder()
        self.wba_authenticator = WBADIDAuthenticator(
            self.wba_resolver, 
            self.wba_signer, 
            self.wba_header_builder
        )
    
    async def agent_auth_two_way_v2(
        self,
        sdk,
        caller_credentials: DIDCredentials,  # 内存对象
        target_did: str,
        request_url: str,
        method: str = "GET",
        json_data: Optional[Dict] = None,
        custom_headers: Dict[str, str] = None,
        use_two_way_auth: bool = True
    ) -> Tuple[int, str, str, bool]:
        """
        执行智能体之间的认证 - 重构版本
        
        Args:
            sdk: ANP SDK实例
            caller_credentials: 调用方DID凭证（内存对象）
            target_did: 目标智能体DID
            request_url: 请求URL
            method: HTTP方法
            json_data: JSON数据
            custom_headers: 自定义头
            use_two_way_auth: 是否使用双向认证
            
        Returns:
            tuple[int, str, str, bool]: (状态码, 响应, 信息, 是否成功)
        """
        
        if custom_headers is None:
            custom_headers = {}
        
        # 构建认证上下文
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
            # 执行认证
            success, message, response_data = await self.wba_authenticator.authenticate_request(
                context, caller_credentials
            )
            
            if success:
                return response_data.get('status', 200), response_data.get('response', ''), message, True
            else:
                return 401, '', message, False
                
        except Exception as e:
            logger.error(f"认证过程中发生错误: {e}")
            return 500, '', f"认证错误: {str(e)}", False

# 向后兼容的包装函数
async def agent_auth_two_way(
    sdk, 
    caller_agent: str, 
    target_agent: str, 
    request_url, 
    method: str = "GET",
    json_data: Optional[Dict] = None,
    custom_headers: dict[str, str] = None, 
    use_two_way_auth: bool = False
) -> tuple[bool, str]:
    """向后兼容的认证函数"""
    
    # 从路径加载凭证（向后兼容）
    user_data_manager = sdk.user_data_manager
    user_data = user_data_manager.get_user_data(caller_agent)
    
    caller_credentials = DIDCredentials.from_paths(
        did_document_path=user_data.did_doc_path,
        private_key_path=str(user_data.did_private_key_file_path)
    )
    
    # 使用新的认证管理器
    auth_manager = AgentAuthManager()
    
    status, response, info, success = await auth_manager.agent_auth_two_way_v2(
        sdk=sdk,
        caller_credentials=caller_credentials,
        target_did=target_agent,
        request_url=request_url,
        method=method,
        json_data=json_data,
        custom_headers=custom_headers,
        use_two_way_auth=use_two_way_auth
    )
    
    return status, response, info, success