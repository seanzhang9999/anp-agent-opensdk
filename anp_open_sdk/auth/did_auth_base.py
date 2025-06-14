# anp_open_sdk/auth/base_auth.py
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, Tuple
from .schemas import DIDCredentials, AuthenticationContext, DIDDocument, DIDKeyPair



class BaseDIDResolver(ABC):
    """DID解析器基类"""
    
    @abstractmethod
    async def resolve_did_document(self, did: str) -> Optional[DIDDocument]:
        """解析DID文档"""
        pass
    
    @abstractmethod
    def supports_did_method(self, did: str) -> bool:
        """检查是否支持该DID方法"""
        pass

class BaseDIDSigner(ABC):
    """DID签名器基类"""
    
    @abstractmethod
    def sign_payload(self, payload: str, key_pair: DIDKeyPair) -> str:
        """签名载荷"""
        pass
    
    @abstractmethod
    def verify_signature(self, payload: str, signature: str, public_key: bytes) -> bool:
        """验证签名"""
        pass

class BaseAuthHeaderBuilder(ABC):
    """认证头构建器基类"""
    
    @abstractmethod
    def build_auth_header(self, context: AuthenticationContext, credentials: DIDCredentials) -> str:
        """构建认证头"""
        pass
    
    @abstractmethod
    def parse_auth_header(self, auth_header: str) -> Dict[str, Any]:
        """解析认证头"""
        pass

class BaseAuth(ABC):
    """
    认证基类，包含通用认证相关方法
    """

    def extract_did_from_auth_header(self, auth_header: str) -> Tuple[Optional[str], Optional[str]]:
        """
        抽象方法：从认证头中提取 req_did 和 target_did（或 resp_did）
        """
        raise NotImplementedError

class BaseDIDAuthenticator(ABC):
    """DID认证器基类"""
    
    def __init__(self, resolver: BaseDIDResolver, signer: BaseDIDSigner, header_builder: BaseAuthHeaderBuilder, base_auth : BaseAuth):
        self.resolver = resolver
        self.signer = signer
        self.header_builder = header_builder
        self.base_auth = base_auth
    
    @abstractmethod
    async def authenticate_request(self, context: AuthenticationContext, credentials: DIDCredentials) -> Tuple[bool, str, Dict[str, Any]]:
        """认证请求"""
        pass


    @abstractmethod
    async def verify_response(self,  auth_header: str, context: AuthenticationContext) -> Tuple[bool, str]:
        """验证响应"""
        pass