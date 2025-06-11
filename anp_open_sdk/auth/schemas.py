# anp_open_sdk/auth/schemas.py
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from cryptography.hazmat.primitives.asymmetric import ed25519
from datetime import datetime

class DIDKeyPair(BaseModel):
    """DID密钥对内存对象"""
    private_key: bytes = Field(..., description="私钥字节")
    public_key: bytes = Field(..., description="公钥字节")
    key_id: str = Field(..., description="密钥ID")
    
    class Config:
        arbitrary_types_allowed = True
    
    @classmethod
    def from_private_key_bytes(cls, private_key_bytes: bytes, key_id: str = "key-1"):
        """从私钥字节创建密钥对"""
        private_key_obj = ed25519.Ed25519PrivateKey.from_private_bytes(private_key_bytes)
        public_key_bytes = private_key_obj.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw
        )
        return cls(
            private_key=private_key_bytes,
            public_key=public_key_bytes,
            key_id=key_id
        )
    
    @classmethod
    def from_file_path(cls, private_key_path: str, key_id: str = "key-1"):
        """从文件路径加载（向后兼容）"""
        with open(private_key_path, 'rb') as f:
            private_key_bytes = f.read()
        return cls.from_private_key_bytes(private_key_bytes, key_id)

class DIDDocument(BaseModel):
    """DID文档内存对象"""
    did: str = Field(..., description="DID标识符")
    verification_methods: List[Dict[str, Any]] = Field(default_factory=list)
    authentication: List[str] = Field(default_factory=list)
    service_endpoints: List[Dict[str, Any]] = Field(default_factory=list)
    raw_document: Dict[str, Any] = Field(default_factory=dict)
    
    @classmethod
    def from_file_path(cls, did_document_path: str):
        """从文件路径加载（向后兼容）"""
        import json
        with open(did_document_path, 'r', encoding='utf-8') as f:
            doc = json.load(f)
        
        return cls(
            did=doc.get('id', ''),
            verification_methods=doc.get('verificationMethod', []),
            authentication=doc.get('authentication', []),
            service_endpoints=doc.get('service', []),
            raw_document=doc
        )
    
    def get_verification_method(self, key_id: str) -> Optional[Dict[str, Any]]:
        """获取指定的验证方法"""
        for vm in self.verification_methods:
            if vm.get('id', '').endswith(f"#{key_id}"):
                return vm
        return None

class DIDCredentials(BaseModel):
    """DID凭证集合"""
    did_document: DIDDocument
    key_pairs: Dict[str, DIDKeyPair] = Field(default_factory=dict)
    
    def get_key_pair(self, key_id: str = "key-1") -> Optional[DIDKeyPair]:
        """获取指定的密钥对"""
        return self.key_pairs.get(key_id)
    
    def add_key_pair(self, key_pair: DIDKeyPair):
        """添加密钥对"""
        self.key_pairs[key_pair.key_id] = key_pair
    
    @classmethod
    def from_paths(cls, did_document_path: str, private_key_path: str, key_id: str = "key-1"):
        """从文件路径创建（向后兼容）"""
        did_doc = DIDDocument.from_file_path(did_document_path)
        key_pair = DIDKeyPair.from_file_path(private_key_path, key_id)
        
        credentials = cls(did_document=did_doc)
        credentials.add_key_pair(key_pair)
        return credentials

class AuthenticationContext(BaseModel):
    """认证上下文"""
    caller_did: str
    target_did: str
    request_url: str
    method: str = "GET"
    timestamp: Optional[datetime] = None
    nonce: Optional[str] = None
    custom_headers: Dict[str, str] = Field(default_factory=dict)
    json_data: Optional[Dict[str, Any]] = None
    use_two_way_auth: bool = True