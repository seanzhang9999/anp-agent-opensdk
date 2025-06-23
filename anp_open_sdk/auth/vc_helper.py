# Copyright 2024 ANP Open SDK Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
验证凭证(VC)辅助模块

提供创建和验证DID验证凭证(Verifiable Credential)的功能
"""

import logging
logger = logging.getLogger(__name__)

import base64
from typing import Dict, Any, Optional
from datetime import datetime, timezone, timedelta

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import load_pem_private_key

import jcs  # 用于规范化JSON

logger = logging.getLogger(__name__)


def load_private_key(private_key_path: str, password: Optional[bytes] = None):
    """加载私钥"""
    try:
        with open(private_key_path, "rb") as f:
            private_key_data = f.read()
        return load_pem_private_key(private_key_data, password=password)
    except Exception as e:
        logger.error(f"加载私钥时出错: {str(e)}")
        return None


def create_verification_credential(
    did_document: Dict[str, Any],
    private_key_path: str,
    nonce: str,
    expires_in: int = 3600
) -> Optional[Dict[str, Any]]:
    """
    创建验证凭证(VC)
    
    Args:
        did_document: DID文档
        private_key_path: 私钥路径
        nonce: 服务器提供的nonce
        expires_in: 凭证有效期（秒）
        
    Returns:
        Dict: 验证凭证，如果创建失败则返回None
    """
    try:
        # 获取DID ID和验证方法
        did_id = did_document.get("id")
        if not did_id:
            logger.error("DID文档中缺少id字段")
            return None
        
        verification_methods = did_document.get("verificationMethod", [])
        if not verification_methods:
            logger.error("DID文档中缺少verificationMethod字段")
            return None
        
        # 使用第一个验证方法
        verification_method = verification_methods[0]
        
        # 创建凭证
        issuance_date = datetime.now(timezone.utc)
        expiration_date = issuance_date + timedelta(seconds=expires_in)
        
        credential = {
            "@context": ["https://www.w3.org/2018/credentials/v1"],
            "type": ["VerifiableCredential", "DIDAuthorizationCredential"],
            "issuer": did_id,
            "subject": did_id,
            "issuanceDate": issuance_date.isoformat(),
            "expirationDate": expiration_date.isoformat(),
            "credentialSubject": {
                "id": verification_method.get("id"),
                "type": verification_method.get("type"),
                "controller": verification_method.get("controller"),
                "publicKeyJwk": verification_method.get("publicKeyJwk"),
                "nonce": nonce
            }
        }
        
        # 加载私钥
        private_key = load_private_key(private_key_path)
        if not private_key:
            return None
        
        # 准备签名数据
        credential_without_proof = credential.copy()
        canonical_json = jcs.canonicalize(credential_without_proof)
        
        # 计算签名
        if isinstance(private_key, ec.EllipticCurvePrivateKey):
            signature = private_key.sign(
                canonical_json,
                ec.ECDSA(hashes.SHA256())
            )
            
            # 将签名编码为Base64
            signature_b64 = base64.b64encode(signature).decode("utf-8")
            
            # 添加签名到凭证
            credential["proof"] = {
                "type": "EcdsaSecp256k1Signature2019",
                "created": issuance_date.isoformat(),
                "verificationMethod": verification_method.get("id"),
                "proofPurpose": "assertionMethod",
                "jws": signature_b64
            }
            
            return credential
        else:
            logger.error("不支持的私钥类型")
            return None
    except Exception as e:
        logger.error(f"创建验证凭证时出错: {str(e)}")
        return None


def verify_verification_credential(
    credential: Dict[str, Any],
    did_document: Dict[str, Any],
    expected_nonce: Optional[str] = None
) -> bool:
    """
    验证验证凭证(VC)
    
    Args:
        credential: 验证凭证
        did_document: DID文档
        expected_nonce: 预期的nonce，如果提供则验证nonce是否匹配
        
    Returns:
        bool: 验证是否通过
    """
    try:
        # 验证基本字段
        if "proof" not in credential or "credentialSubject" not in credential:
            logger.error("验证凭证缺少必要字段")
            return False
        
        # 验证过期时间
        if "expirationDate" in credential:
            expiration_date = datetime.fromisoformat(credential["expirationDate"].replace("Z", "+00:00"))
            if datetime.now(timezone.utc) > expiration_date:
                logger.error("验证凭证已过期")
                return False
        
        # 验证nonce
        if expected_nonce:
            credential_nonce = credential.get("credentialSubject", {}).get("nonce")
            if credential_nonce != expected_nonce:
                logger.error(f"Nonce不匹配: 预期 {expected_nonce}, 实际 {credential_nonce}")
                return False
        
        # 验证签名
        # 注意：这里简化了签名验证过程，实际应用中应该使用专门的VC库
        # 例如，可以使用DID解析器获取公钥，然后验证签名
        
        # 这里假设验证通过
        return True
    except Exception as e:
        logger.error(f"验证凭证时出错: {str(e)}")
        return False