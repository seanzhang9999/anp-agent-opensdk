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
DID WBA authentication module with both client and server capabilities.
"""
import os
import json
import logging
import traceback
import secrets
import string
import random
import aiohttp
from typing import Dict, Tuple, Optional, Any
from datetime import datetime, timezone, timedelta
from pathlib import Path
# from anp_open_sdk.anp_sdk import ANPSDK  # 延迟导入，避免循环依赖

from fastapi import Request, HTTPException
from canonicaljson import encode_canonical_json
from agent_connect.authentication import create_did_wba_document

from anp_open_sdk.agent_connect_hotpatch.authentication.did_wba_auth_header import DIDWbaAuthHeader
from anp_open_sdk.agent_connect_hotpatch.authentication.did_wba import  extract_auth_header_parts, verify_auth_header_signature,resolve_did_wba_document

from anp_open_sdk.auth.custom_did_resolver import resolve_local_did_document

from anp_open_sdk.config.dynamic_config import dynamic_config
# from anp_open_sdk.auth.token_auth import create_access_token  # 延迟导入，避免循环依赖

# 存储服务端生成的nonce
VALID_SERVER_NONCES: Dict[str, datetime] = {}


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


def get_and_validate_domain(request: Request) -> str:
    """
    Get the domain from the request.
    
    Args:
        request: FastAPI request object
        
    Returns:
        str: Domain from request host header
    """
    # Get host from request
    host = request.headers.get('host', '')
    domain = host.split(":")[0]
    return domain

async def handle_did_auth(authorization: str, domain: str , request: Request , sdk = None) -> Dict:
    """
    Handle DID WBA authentication and return token.
    
    Args:
        authorization: DID WBA authorization header
        domain: Domain for DID WBA verification
        
    Returns:
        Dict: Authentication result with token
        
    Raises:
        HTTPException: When authentication fails
    """
    try:
       # logging.info(f"Processing DID WBA authentication - domain: {domain}, Authorization header: {authorization}")

        # Extract header parts
        from anp_open_sdk.anp_sdk import ANPSDK
        header_parts = extract_auth_header_parts(authorization)
        
        if not header_parts:
            raise HTTPException(status_code=401, detail="Invalid authorization header format")
            
        # 解包顺序：(did, nonce, timestamp, verification_method, signature)
        did, nonce, timestamp, resp_did, keyid, signature = header_parts
        
    #   # logging.info(f"Processing DID WBA authentication - DID: {did}, Key ID: {keyid}")
        
        # 验证时间戳
        if not verify_timestamp(timestamp):
            raise HTTPException(status_code=401, detail="Timestamp expired or invalid")
            
        # 验证 nonce 有效性
        # if not is_valid_server_nonce(nonce):
        #     logging.error(f"Invalid or expired nonce: {nonce}")
        #     raise HTTPException(status_code=401, detail="Invalid or expired nonce")
        
        # 尝试使用自定义解析器解析DID文档
        did_document = await resolve_local_did_document(did)
        
        # 如果自定义解析器失败，尝试使用标准解析器
        if not did_document:
           # logging.info(f"本地DID解析失败，尝试使用标准解析器 for DID: {did}")
            try:
                did_document = await resolve_did_wba_document(did)
            except Exception as e:
                logging.error(f"标准DID解析器也失败: {e}")
                did_document = None
        
        if not did_document:
            raise HTTPException(status_code=401, detail="Failed to resolve DID document")
            
        # logging.info(f"成功解析DID文档: {did}")
        
        # 验证签名
        try:
            # 重新构造完整的授权头
            full_auth_header = authorization
            
            # 调用验证函数
            is_valid, message = verify_auth_header_signature(
                auth_header=full_auth_header,
                did_document=did_document,
                service_domain=domain
            )
            
            logging.info(f" {did}签名验证结果: {is_valid}, 消息: {message}")
            
            if not is_valid:
                raise HTTPException(status_code=401, detail=f"Invalid signature: {message}")
        except Exception as e:
            logging.error(f"验证签名时出错: {e}")
            raise HTTPException(status_code=401, detail=f"Error verifying signature: {str(e)}")
        

        from typing import cast
        from anp_open_sdk.anp_sdk import ANPSDK
        sdk = cast(ANPSDK, sdk)
        resp_did_agent = sdk.get_agent(resp_did)

       
        # 生成访问令牌
        from anp_open_sdk.config.dynamic_config import dynamic_config
        from anp_open_sdk.auth.token_auth import create_access_token
        expiration_time = dynamic_config.get('anp_sdk.token_expire_time')
        access_token = create_access_token(
            resp_did_agent.jwt_private_key_path,
            data={"req_did": did, "resp_did": resp_did, "comments": "open for req_did" },
            expires_delta = expiration_time
            )
            
        resp_did_agent.store_token_to_remote(did, access_token,  expiration_time)
       
        
       # logging.info(f"认证成功，已生成访问令牌")
        
        # 如果resp_did存在，加载resp_did的DID文档并组装DID认证头
        resp_did_auth_header = None
        if resp_did and resp_did != "没收到":
            try:
                from anp_open_sdk.config.dynamic_config import dynamic_config
                # 获取resp_did用户目录
                key_id = "key-1"

                userdid_filepath = dynamic_config.get('anp_sdk.user_did_path')
                userdid_filepath = os.path.join(userdid_filepath, f"user_{resp_did[-16:]}")
                did_document_path = f"{userdid_filepath}/did_document.json"
                private_key_path = f"{userdid_filepath}/{key_id}_private.pem"

                if resp_did_agent.is_hosted_did:
                    did_document_path = resp_did_agent.did_document_path
                    private_key_path = resp_did_agent.private_key_path
                
                # 检查文件是否存在
                if Path(did_document_path).exists() and Path(private_key_path).exists():
                    # 创建DID认证客户端
                    resp_auth_client = DIDWbaAuthHeader(
                        did_document_path=str(did_document_path),
                        private_key_path=str(private_key_path)
                    )
                    
                    # 获取认证头（用于返回给req_did进行验证,此时 req是现在的did）
                    target_url = "http://virtual.WBAback:9999"  # 使用当前请求的域名
                    resp_did_auth_header = resp_auth_client.get_auth_header(target_url, did)

                    # 打印认证头
                   # logging.info(f"Generated resp_did_auth_header: {resp_did_auth_header}")

                   # logging.info(f"成功加载resp_did的DID文档并生成认证头")
                else:
                    logging.warning(f"resp_did的DID文档或私钥不存在: {did_document_path} or {private_key_path}")
            except Exception as e:
                logging.error(f"加载resp_did的DID文档时出错: {e}")
                resp_did_auth_header = None
        
        
        return [
            {   
                "access_token": access_token,
                "token_type": "bearer",
                "req_did": did,
                "resp_did": resp_did,
                "resp_did_auth_header": resp_did_auth_header
             } 

        ]

        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error during DID authentication: {e}")
        logging.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail="Authentication error")


# 客户端相关功能
async def generate_or_load_did(unique_id: str = None) -> Tuple[Dict, Dict, str]:
    """
    生成新的DID文档或者加载已经存在的DID文档
    
    Args:
        unique_id: 可选的用户唯一标识符
    
    Returns:
        Tuple[Dict, Dict, str]: 包含DID文档、密钥和DID路径
    """
    if not unique_id:
        unique_id = secrets.token_hex(8)
    
    # 检查是否已经有DID文档
    current_dir = Path(__file__).parent.parent.absolute()
    user_dir = current_dir / settings.DID_DOCUMENTS_PATH / f"user_{unique_id}"
    did_path = user_dir / settings.DID_DOCUMENT_FILENAME
    
    if did_path.exists():
       # logging.info(f"Loading existing DID document from {did_path}")
        
        # 加载DID文档
        with open(did_path, 'r', encoding='utf-8') as f:
            did_document = json.load(f)
        
        # 创建空的keys字典，因为我们已经有了私钥文件
        keys = {}
        
        return did_document, keys, str(user_dir)
    
    # 创建DID文档
   # logging.info("Creating new DID document...")
    host = f"localhost"
    port = settings.PORT
    if os.getenv('AGENT_PORT'):
        port = f"{os.getenv('AGENT_PORT')}"
    if os.getenv('AGENT_URL'):
        host = f"{os.getenv('AGENT_URL')}"
    


    did_document, keys = create_did_wba_document(
        host,
        port,
        path_segments=["wba", "user", unique_id],
        agent_description_url=f"http://{host}:{port}/agents/example/ad.json"
    )
    
    # 保存私钥和DID文档
    user_dir.mkdir(parents=True, exist_ok=True)
    
    # 保存私钥
    for method_fragment, (private_key_bytes, _) in keys.items():
        private_key_path = user_dir / f"{method_fragment}_private.pem"
        with open(private_key_path, 'wb') as f:
            f.write(private_key_bytes)
       # logging.info(f"Saved private key '{method_fragment}' to {private_key_path}")
    
    # 保存DID文档
    with open(did_path, 'w', encoding='utf-8') as f:
        json.dump(did_document, f, indent=2)
   # logging.info(f"Saved DID document to {did_path}")
    
    return did_document, keys, str(user_dir)


async def send_authenticated_request(target_url: str, auth_client: DIDWbaAuthHeader, resp_did: str, method: str = "GET", 
                                     json_data: Optional[Dict] = None) -> Tuple[int, Dict[str, Any], Optional[str]]:
    """
    发送带有DID WBA认证的请求
    
    Args:
        target_url: 目标URL
        auth_client: DID WBA认证客户端
        method: HTTP方法
        json_data: 可选的JSON数据
        
    Returns:
        Tuple[int, Dict[str, Any], Optional[str]]: 状态码、响应和令牌
    """
    try:
        # 获取认证头
        auth_headers = auth_client.get_auth_header(target_url , resp_did)

       # logging.info(f"Sending authenticated request to {target_url} with headers: {auth_headers}")
        
        async with aiohttp.ClientSession() as session:
            if method.upper() == "GET":
                async with session.get(
                    target_url,
                    headers=auth_headers
                ) as response:
                    status = response.status
                    response_data = await response.json() if status == 200 else {}
                    # x = dict(response.headers)
                    token = auth_client.update_token(target_url, dict(response.headers))
                    # token = auth_client.update_token(target_url, response_data )
                    return status, response_data, dict(response.headers), token
            elif method.upper() == "POST":
                async with session.post(
                    target_url,
                    headers=auth_headers,
                    json=json_data
                ) as response:
                    status = response.status
                    response_data = await response.json() if status == 200 else {}
                    token = auth_client.update_token(target_url, dict(response.headers))
                    return status, response_data,dict(response.headers) ,token
            else:
                logging.error(f"Unsupported HTTP method: {method}")
                return 400, {"error": "Unsupported HTTP method"}, dict(response.headers) , None
    except Exception as e:
        logging.error(f"Error sending authenticated request: {e}", exc_info=True)
        return 500, {"error": str(e)}, dict(response.headers) ,None


async def send_request_with_token(target_url: str, token: str, sender_did: str, targeter_did:string, method: str = "GET",
                                  json_data: Optional[Dict] = None) -> Tuple[int, Dict[str, Any]]:
    """
    使用已获取的令牌发送请求
    
    Args:
        target_url: 目标URL
        token: 访问令牌
        method: HTTP方法
        json_data: 可选的JSON数据
        
    Returns:
        Tuple[int, Dict[str, Any]]: 状态码和响应
    """
    try:
        headers = {
            "Authorization": f"Bearer {token}",
            "req_did": f"{sender_did}",
            "resp_did": f"{targeter_did}"
        }

        async with aiohttp.ClientSession() as session:
            if method.upper() == "GET":
                async with session.get(
                    target_url,
                    headers=headers
                ) as response:
                    status = response.status
                    response_data = await response.json() if status == 200 else {}
                    return status, response_data
            elif method.upper() == "POST":
                async with session.post(
                    target_url,
                    headers=headers,
                    json=json_data
                ) as response:
                    status = response.status
                    response_data = await response.json() if status == 200 else {}
                    return status, response_data
            else:
                logging.error(f"Unsupported HTTP method: {method}")
                return 400, {"error": "Unsupported HTTP method"}
    except Exception as e:
        logging.error(f"Error sending request with token: {e}")
        return 500, {"error": str(e)}
