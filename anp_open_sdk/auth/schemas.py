# anp_open_sdk/auth/schemas.py
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from cryptography.hazmat.primitives.asymmetric import ed25519
from datetime import datetime

from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization

class DIDKeyPair(BaseModel):
    """DID密钥对内存对象 (支持 secp256k1)"""
    private_key: bytes = Field(..., description="私钥字节")
    public_key: bytes = Field(..., description="公钥字节")
    key_id: str = Field(..., description="密钥ID")
    """DID密钥对内存对象"""
    class Config:
        arbitrary_types_allowed = True

    @classmethod
    def from_private_key_bytes(cls, private_key_bytes: bytes, key_id: str = "key-1"):
        """从 secp256k1 私钥字节创建密钥对"""
        private_key_obj = ec.derive_private_key(
            int.from_bytes(private_key_bytes, byteorder="big"), ec.SECP256K1()
        )
        public_key_obj = private_key_obj.public_key()
        public_key_bytes = public_key_obj.public_bytes(
            encoding=serialization.Encoding.X962,
            format=serialization.PublicFormat.UncompressedPoint
        )
        return cls(
            private_key=private_key_bytes,
            public_key=public_key_bytes,
            key_id=key_id
        )

    @classmethod
    def from_file_path(cls, private_key_path: str, key_id: str = "key-1"):
        """从PEM/PKCS8 secp256k1私钥文件创建密钥对"""
        with open(private_key_path, "rb") as key_file:
            private_key = serialization.load_pem_private_key(
                key_file.read(),
                password=None
            )
            if not isinstance(private_key, ec.EllipticCurvePrivateKey):
                raise ValueError("Loaded private key is not an EC key")
            if private_key.curve.name != "secp256k1":
                raise ValueError("Private key is not secp256k1 curve")
            private_key_bytes = private_key.private_numbers().private_value.to_bytes(32, byteorder="big")
            public_key_bytes = private_key.public_key().public_bytes(
                encoding=serialization.Encoding.X962,
                format=serialization.PublicFormat.UncompressedPoint
            )
        return cls(
            private_key=private_key_bytes,
            public_key=public_key_bytes,
            key_id=key_id
        )


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
    
    @classmethod
    def from_memory_data(cls, did_document_dict: Dict[str, Any], private_key_bytes: bytes, key_id: str = "key-1"):
        """从内存数据创建DID凭证"""
        # 创建DID文档对象
        did_doc = DIDDocument(
            did=did_document_dict.get('id', ''),
            verification_methods=did_document_dict.get('verificationMethod', []),
            authentication=did_document_dict.get('authentication', []),
            service_endpoints=did_document_dict.get('service', []),
            raw_document=did_document_dict
        )
        
        # 创建密钥对对象
        key_pair = DIDKeyPair.from_private_key_bytes(private_key_bytes, key_id)
        
        # 创建凭证对象
        credentials = cls(did_document=did_doc)
        credentials.add_key_pair(key_pair)
        return credentials
    
    @classmethod
    def from_user_data(cls, user_data):
        """从用户数据对象创建DID凭证"""
        # 读取私钥文件内容到内存
        with open(user_data.did_private_key_file_path, "rb") as key_file:
            private_key_pem = key_file.read()
        
        # 解析私钥
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        private_key = serialization.load_pem_private_key(private_key_pem, password=None)
        
        # 获取私钥字节
        if isinstance(private_key, ec.EllipticCurvePrivateKey):
            # EC私钥（secp256k1等）
            private_key_bytes = private_key.private_numbers().private_value.to_bytes(32, byteorder="big")
        else:
            # 其他类型私钥的处理 - 先尝试序列化为DER格式
            try:
                private_key_bytes = private_key.private_bytes(
                    encoding=serialization.Encoding.DER,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.NoEncryption()
                )
            except Exception:
                # 如果失败，尝试PEM格式
                private_key_bytes = private_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.NoEncryption()
                )
        
        # 获取key_id
        key_id = getattr(user_data, 'key_id', 'key-1')
        if not key_id:
            key_id = 'key-1'
        
        return cls.from_memory_data(user_data.did_doc, private_key_bytes, key_id)

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
    domain: Optional[str] = None  # 新增 domain 字段
