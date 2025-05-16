"""Bearer token authentication module."""
import logging
from typing import Optional, Dict
from datetime import datetime, timedelta
import jwt
from fastapi import HTTPException

from core.config import settings
from anp_core.auth.jwt_keys import get_jwt_public_key, get_jwt_private_key


def create_access_token(private_key_path, data: Dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Create a new JWT access token.
    
    Args:
        private_key_path: 私钥路径
        data: Data to encode in the token
        expires_delta: Optional expiration time
        
    Returns:
        str: Encoded JWT token
    """
    
    to_encode = data.copy()
    expires = datetime.utcnow() + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expires})
    
    # Get private key for signing
    private_key = get_jwt_private_key(private_key_path)
    if not private_key:
        logging.error("Failed to load JWT private key")
        raise HTTPException(status_code=500, detail="Internal server error during token generation")
    
    # Create the JWT token using RS256 algorithm with private key
    encoded_jwt = jwt.encode(
        to_encode, 
        private_key, 
        algorithm=settings.JWT_ALGORITHM
    )
    
    # 将token存储到LocalAgent中
    if "resp_did" in data and "req_did" in data:
        from demo_autorun import get_user_cfg_list, find_user_cfg_by_did, LocalAgent
        user_list, name_to_dir = get_user_cfg_list()
        resp_did = data["resp_did"]
        req_did = data["req_did"]
        
        resp_did_cfg = find_user_cfg_by_did(user_list, name_to_dir, resp_did)
        if resp_did_cfg:
            resp_did_agent = LocalAgent(
                id=resp_did_cfg.get('id'),
                user_dir=resp_did_cfg.get('user_dir')
            )
            
            # 存储token信息到LocalAgent中
            token_info = {
                "token": encoded_jwt,
                "created_at": datetime.utcnow(),
                "expires_at": expires,
                "is_revoked": False,
                "req_did": req_did
            }
            
            # 使用LocalAgent的store_token_info方法存储token信息
            resp_did_agent.store_token_info(req_did, token_info)
            logging.info(f"Token for {req_did} stored in LocalAgent {resp_did}")
    
    return encoded_jwt


async def handle_bearer_auth(token: str, req_did, resp_did) -> Dict:
    """
    Handle Bearer token authentication.
    
    Args:
        token: JWT token string
        req_did: 请求方DID
        resp_did: 响应方DID
        
    Returns:
        Dict: Token payload with DID information
        
    Raises:
        HTTPException: When token is invalid
    """
    try:
        # Remove 'Bearer ' prefix if present
        if token.startswith("Bearer "):
            token_body = token[7:]
        else:
            token_body = token
        
        # 从LocalAgent中获取token信息
        from demo_autorun import get_user_cfg_list, find_user_cfg_by_did, LocalAgent
        user_list, name_to_dir = get_user_cfg_list()
        resp_did_cfg = find_user_cfg_by_did(user_list, name_to_dir, resp_did)
        
        if not resp_did_cfg:
            logging.error(f"Cannot find configuration for resp_did: {resp_did}")
            raise HTTPException(status_code=401, detail="Invalid response DID")
        
        resp_did_agent = LocalAgent(
            id=resp_did_cfg.get('id'),
            user_dir=resp_did_cfg.get('user_dir')
        )
        
        # 检查LocalAgent中是否存储了该req_did的token信息
        token_info = resp_did_agent.get_token_info(req_did)
        if token_info:
            # 检查token是否被撤销
            if token_info["is_revoked"]:
                logging.error(f"Token for {req_did} has been revoked")
                raise HTTPException(status_code=401, detail="Token has been revoked")
            
            # 检查token是否过期（使用存储的过期时间，而不是token中的时间）
            if datetime.utcnow() > token_info["expires_at"]:
                logging.error(f"Token for {req_did} has expired")
                raise HTTPException(status_code=401, detail="Token has expired")
            
            # 验证token是否匹配
            if token_body != token_info["token"]:
                logging.error(f"Token mismatch for {req_did}")
                raise HTTPException(status_code=401, detail="Invalid token")
            
            logging.info(f"Token for {req_did} verified successfully from LocalAgent storage")
        else:
            # 如果LocalAgent中没有存储token信息，则使用公钥验证
            logging.warning(f"No token info found in LocalAgent for {req_did}, falling back to public key verification")
            
            public_key = get_jwt_public_key(resp_did_agent.jwt_public_key_path)
            if not public_key:
                logging.error("Failed to load JWT public key")
                raise HTTPException(status_code=500, detail="Internal server error during token verification")
                
            # Decode and verify the token using the public key
            payload = jwt.decode(
                token_body,
                public_key,
                algorithms=[settings.JWT_ALGORITHM]
            )
            
            # Check if token contains required fields
            if "req_did" not in payload:
                raise HTTPException(status_code=401, detail="Invalid token payload")
        
        return [{
            "access_token": token,
            "token_type": "bearer",
            "req_did": req_did,
            "resp_did": resp_did,
        }]
    
    except jwt.PyJWTError as e:
        logging.error(f"JWT verification error: {e}")
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")
    except Exception as e:
        logging.error(f"Token verification error: {e}")
        raise HTTPException(status_code=401, detail=f"Token verification failed: {str(e)}")
