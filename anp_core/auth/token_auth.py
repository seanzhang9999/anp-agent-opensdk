"""
Bearer token authentication module.
"""
import logging
from typing import Optional, Dict
from datetime import datetime, timedelta
import jwt
from fastapi import HTTPException

from core.config import settings
from anp_core.auth.jwt_keys import get_jwt_public_key, get_jwt_private_key


def create_access_token( private_key_path, data: Dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Create a new JWT access token.
    
    Args:
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
    return encoded_jwt


async def handle_bearer_auth(token: str, req_did,resp_did) -> Dict:
    """
    Handle Bearer token authentication.
    
    Args:
        token: JWT token string
        
    Returns:
        Dict: Token payload with DID information
        
    Raises:
        HTTPException: When token is invalid
    """
    try:
        # Remove 'Bearer ' prefix if present
        if token.startswith("Bearer "):
            token_body = token[7:]
        
        # Get public key for verification

        from demo_autorun import get_user_cfg_list, find_user_cfg_by_did, LocalAgent
        user_list, name_to_dir = get_user_cfg_list()
        resp_did_cfg = find_user_cfg_by_did(user_list, name_to_dir,resp_did)
        
        resp_did_agent = LocalAgent(
        id=resp_did_cfg.get('id'),
        user_dir=resp_did_cfg.get('user_dir')
        )
  

        
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
            
        return token
    
        
    except jwt.PyJWTError as e:
        logging.error(f"JWT token error: {e}")
        raise HTTPException(status_code=401, detail="Invalid token")
    except Exception as e:
        logging.error(f"Error during token authentication: {e}")
        raise HTTPException(status_code=500, detail="Authentication error")
