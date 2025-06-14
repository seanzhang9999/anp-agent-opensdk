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

"""Bearer token authentication module."""
import logging
import random
import string
from typing import Optional, Dict
from datetime import datetime, timedelta, timezone
import jwt
from fastapi import HTTPException

from datetime import datetime, timezone, timedelta
from anp_open_sdk.anp_sdk_agent import LocalAgent
from anp_open_sdk.auth.did_auth import VALID_SERVER_NONCES
from anp_open_sdk.config.dynamic_config import dynamic_config
from anp_open_sdk.auth.jwt_keys import get_jwt_public_key, get_jwt_private_key

def create_access_token(private_key_path, data: Dict, expires_delta: int = None) -> str:
    """
    Create a new JWT access token.
    
    Args:
        private_key_path: 私钥路径
        data: Data to encode in the token
        expires_delta: Optional expiration time
        
    Returns:
        str: Encoded JWT token
    """

    token_expire_time = dynamic_config.get("anp_sdk.token_expire_time")
    
    to_encode = data.copy()
    expires = datetime.now(timezone.utc) + (timedelta(minutes= expires_delta) or timedelta(secondes = token_expire_time))
    to_encode.update({"exp": expires})
    
    # Get private key for signing
    private_key = get_jwt_private_key(private_key_path)
    if not private_key:
        logging.error("Failed to load JWT private key")
        raise HTTPException(status_code=500, detail="Internal server error during token generation")
    
    jwt_algorithm = dynamic_config.get("anp_sdk.jwt_algorithm")

    # Create the JWT token using RS256 algorithm with private key
    encoded_jwt = jwt.encode(
        to_encode, 
        private_key, 
        algorithm=jwt_algorithm
    )
    
   
    
    return encoded_jwt



async def handle_bearer_auth(token: str, req_did, resp_did, sdk= None) -> Dict:
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
        

        resp_did_agent = LocalAgent.from_did(resp_did)
        token_info = resp_did_agent.contact_manager.get_token_to_remote(req_did)

        
        # 检查LocalAgent中是否存储了该req_did的token信息

        if token_info:
            # Convert expires_at string to datetime object and ensure it's timezone-aware
            try:
                if isinstance(token_info["expires_at"], str):
                    expires_at_dt = datetime.fromisoformat(token_info["expires_at"])
                else:
                    expires_at_dt = token_info["expires_at"]  # Assuming it's already a datetime object from
                # Ensure the datetime is timezone-aware (assume UTC if naive)
                if expires_at_dt.tzinfo is None:
                    logging.warning(f"Stored expires_at for {req_did} is timezone-naive. Assuming UTC.")
                    expires_at_dt = expires_at_dt.replace(tzinfo=timezone.utc)
                token_info["expires_at"] = expires_at_dt
            except ValueError as e:
                 logging.error(f"Failed to parse expires_at string '{token_info['expires_at']}': {e}")
                 raise HTTPException(status_code=401, detail="Invalid token expiration format")

            # 检查token是否被撤销
            if token_info["is_revoked"]:
                logging.error(f"Token for {req_did} has been revoked")
                raise HTTPException(status_code=401, detail="Token has been revoked")
            
            # 检查token是否过期（使用存储的过期时间，而不是token中的时间）
            if datetime.now(timezone.utc) > token_info["expires_at"]:
                logging.error(f"Token for {req_did} has expired")
                raise HTTPException(status_code=401, detail="Token has expired")
            
            # 验证token是否匹配
            if token_body != token_info["token"]:
                logging.error(f"Token mismatch for {req_did}")
                raise HTTPException(status_code=401, detail="Invalid token")
            
            logging.info(f" {req_did}提交的token在LocalAgent存储中未过期,快速通过!")
        else:
            # 如果LocalAgent中没有存储token信息，则使用公钥验证
             
            public_key = get_jwt_public_key(resp_did_agent.jwt_public_key_path)
            if not public_key:
                logging.error("Failed to load JWT public key")
                raise HTTPException(status_code=500, detail="Internal server error during token verification")
                
            jwt_algorithm = dynamic_config.get("anp_sdk.jwt_algorithm")

            # Decode and verify the token using the public key
            payload = jwt.decode(
                token_body,
                public_key,
                algorithms=[jwt_algorithm]
            )
            
            # Check if token contains required fields
            if "req_did" not in payload:
                raise HTTPException(status_code=401, detail="Invalid token payload")
            
            logging.info(f"LocalAgent存储中未找到{req_did}提交的token,公钥验证通过")
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


def verify_timestamp(timestamp_str: str) -> bool:
    """
    Verify if a timestamp is within the valid period.

    Args:
        timestamp_str: ISO format timestamp string

    Returns:
        bool: Whether the timestamp is valid
    """
    try:
        # Parse the timestamp string
        request_time = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))

        # Get current time
        current_time = datetime.now(timezone.utc)

        # Calculate time difference
        time_diff = abs((current_time - request_time).total_seconds() / 60)

        nonce_expire_minutes = dynamic_config.get('anp_sdk.nonce_expire_minutes')

        # Verify timestamp is within valid period
        if time_diff > nonce_expire_minutes:
            logging.error(f"Timestamp expired. Current time: {current_time}, Request time: {request_time}, Difference: {time_diff} minutes")
            return False

        return True

    except ValueError as e:
        logging.error(f"Invalid timestamp format: {e}")
        return False
    except Exception as e:
        logging.error(f"Error verifying timestamp: {e}")
        return False


def is_valid_server_nonce(nonce: str) -> bool:
    """
    Check if a nonce is valid and not expired.

    Args:
        nonce: The nonce to check

    Returns:
        bool: Whether the nonce is valid
    """
    if nonce not in VALID_SERVER_NONCES:
        return True

    nonce_time = VALID_SERVER_NONCES[nonce]
    current_time = datetime.now(timezone.utc)

    nonce_expire_minutes = dynamic_config.get('anp_sdk.nonce_expire_minutes')

    return current_time - nonce_time <= timedelta(minutes=nonce_expire_minutes)


def generate_nonce(length: int = 16) -> str:
    """
    Generate a random nonce of specified length.

    Args:
        length: Length of the nonce to generate

    Returns:
        str: Generated nonce
    """
    characters = string.ascii_letters + string.digits
    nonce = ''.join(random.choice(characters) for _ in range(length))
    VALID_SERVER_NONCES[nonce] = datetime.now(timezone.utc)
    return nonce
