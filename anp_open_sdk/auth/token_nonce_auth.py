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


import os
from typing import Optional, Dict
import jwt
from fastapi import HTTPException

from datetime import datetime, timezone, timedelta
import logging
logger = logging.getLogger(__name__)
from anp_open_sdk.config import get_global_config



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
    config = get_global_config()
    token_expire_time = config.anp_sdk.token_expire_time

    to_encode = data.copy()
    expires = datetime.now(timezone.utc) + (timedelta(minutes=expires_delta) if expires_delta else timedelta(seconds=token_expire_time))
    to_encode.update({"exp": expires})
    
    # Get private key for signing
    private_key = get_jwt_private_key(private_key_path)
    if not private_key:
        logger.debug("Failed to load JWT private key")
        raise HTTPException(status_code=500, detail="Internal server error during token generation")
    
    jwt_algorithm = config.anp_sdk.jwt_algorithm
    # Create the JWT token using RS256 algorithm with private key
    encoded_jwt = jwt.encode(
        to_encode, 
        private_key, 
        algorithm=jwt_algorithm
    )
    return encoded_jwt


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
        config = get_global_config()
        nonce_expire_minutes = config.anp_sdk.nonce_expire_minutes
        # Verify timestamp is within valid period
        if time_diff > nonce_expire_minutes:
            logger.debug(f"Timestamp expired. Current time: {current_time}, Request time: {request_time}, Difference: {time_diff} minutes")
            return False

        return True

    except ValueError as e:
        logger.debug(f"Invalid timestamp format: {e}")
        return False
    except Exception as e:
        logger.debug(f"Error verifying timestamp: {e}")
        return False





def get_jwt_private_key(key_path: str = None ) -> Optional[str]:
    """
    Get the JWT private key from a PEM file.
    Args:
        key_path: Path to the private key PEM file (default: from config)

    Returns:
        Optional[str]: The private key content as a string, or None if the file cannot be read
    """

    if not os.path.exists(key_path):
        logger.debug(f"Private key file not found: {key_path}")
        return None

    try:
        with open(key_path, "r") as f:
            private_key = f.read()
        logger.debug(f"读取到Token签名密钥文件{key_path}，准备签发Token")
        return private_key
    except Exception as e:
        logger.debug(f"Error reading private key file: {e}")
        return None


def get_jwt_public_key(key_path: str = None) -> Optional[str]:
    """
    Get the JWT public key from a PEM file.

    Args:
        key_path: Path to the public key PEM file (default: from config)

    Returns:
        Optional[str]: The public key content as a string, or None if the file cannot be read
    """
    if not os.path.exists(key_path):
        logger.debug(f"Public key file not found: {key_path}")
        return None

    try:
        with open(key_path, "r") as f:
            public_key = f.read()
        logger.debug(f"Successfully read public key from {key_path}")
        return public_key
    except Exception as e:
        logger.debug(f"Error reading public key file: {e}")
        return None
