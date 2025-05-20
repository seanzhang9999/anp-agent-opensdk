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
JWT configuration module providing functions to get JWT public and private keys.
"""

import os
import logging
from typing import Optional
from anp_open_sdk.config.dynamic_config import dynamic_config
from core.config import settings

# Ensure key files exist
if not os.path.exists(settings.JWT_PRIVATE_KEY_PATH):
    raise FileNotFoundError(f"JWT private key not found at: {settings.JWT_PRIVATE_KEY_PATH}")
if not os.path.exists(settings.JWT_PUBLIC_KEY_PATH):
    raise FileNotFoundError(f"JWT public key not found at: {settings.JWT_PUBLIC_KEY_PATH}")


def get_jwt_private_key(key_path: str = settings.JWT_PRIVATE_KEY_PATH) -> Optional[str]:
    """
    Get the JWT private key from a PEM file.

    Args:
        key_path: Path to the private key PEM file (default: from config)

    Returns:
        Optional[str]: The private key content as a string, or None if the file cannot be read
    """

    if not os.path.exists(key_path):
        logging.error(f"Private key file not found: {key_path}")
        return None

    try:
        with open(key_path, "r") as f:
            private_key = f.read()
        logging.info(f"读取到Token签名密钥文件{key_path}，准备签发Token")
        return private_key
    except Exception as e:
        logging.error(f"Error reading private key file: {e}")
        return None


def get_jwt_public_key(key_path: str = settings.JWT_PUBLIC_KEY_PATH) -> Optional[str]:
    """
    Get the JWT public key from a PEM file.

    Args:
        key_path: Path to the public key PEM file (default: from config)

    Returns:
        Optional[str]: The public key content as a string, or None if the file cannot be read
    """
    if not os.path.exists(key_path):
        logging.error(f"Public key file not found: {key_path}")
        return None

    try:
        with open(key_path, "r") as f:
            public_key = f.read()
        logging.info(f"Successfully read public key from {key_path}")
        return public_key
    except Exception as e:
        logging.error(f"Error reading public key file: {e}")
        return None
