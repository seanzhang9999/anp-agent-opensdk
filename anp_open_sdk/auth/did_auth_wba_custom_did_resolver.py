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
自定义DID文档解析器，用于本地测试环境
"""
import json
import logging
logger = logging.getLogger(__name__)

import aiohttp
from pathlib import Path
from typing import Dict, Optional
from urllib.parse import unquote


async def resolve_local_did_document(did: str) -> Optional[Dict]:
    """
    解析本地DID文档
    
    Args:
        did: DID标识符，例如did:wba:localhost%3A8000:wba:user:123456
    
    Returns:
        Optional[Dict]: 解析出的DID文档，如果解析失败则返回None
    """
    try:
        # logger.debug(f"解析本地DID文档: {did}")
        
        # 解析DID标识符
        parts = did.split(':')
        if len(parts) < 5 or parts[0] != 'did' or parts[1] != 'wba':
            logger.debug(f"无效的DID格式: {did}")
            return None
        
        # 提取主机名、端口和用户ID
        hostname = parts[2]
        # 解码端口部分，如果存在
        if '%3A' in hostname:
            hostname = unquote(hostname)  # 将 %3A 解码为 :
            
        path_segments = parts[3:]
        user_id = path_segments[-1]
        user_dir = path_segments[-2]
        
        # logger.debug(f"DID 解析结果 - 主机名: {hostname}, 用户ID: {user_id}")
        
        # 查找本地文件系统中的DID文档
        current_dir = Path(__file__).parent.parent.absolute()
        did_path = current_dir / 'did_keys' / f"user_{user_id}" / "did.json"
        
        if did_path.exists():
            # logger.debug(f"找到本地DID文档: {did_path}")
            with open(did_path, 'r', encoding='utf-8') as f:
                did_document = json.load(f)
            return did_document
        
        # 如果本地未找到，尝试通过HTTP请求获取
        http_url = f"http://{hostname}/wba/{user_dir}/{user_id}/did.json"

        
        # 这里使用异步HTTP请求
        async with aiohttp.ClientSession() as session:
            async with session.get(http_url, ssl=False) as response:
                if response.status == 200:
                    did_document = await response.json()
                    logger.debug(f"通过DID标识解析的{http_url}获取{did}的DID文档")
                    return did_document
                else:
                    logger.debug(f"did本地解析器地址{http_url}获取失败，状态码: {response.status}")
                    return None
    
    except Exception as e:
        logger.debug(f"解析DID文档时出错: {e}")
        return None
