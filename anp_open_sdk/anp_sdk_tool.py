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

from Crypto.PublicKey import RSA
from pathlib import Path
import os
import json
import yaml
import secrets
from loguru import logger
from anp_open_sdk.config import path_resolver
from anp_open_sdk.config.dynamic_config import dynamic_config
import jwt
import json
from loguru import logger
from typing import Optional, Dict, Tuple, Any
from aiohttp import ClientResponse
from anp_open_sdk.config.path_resolver import path_resolver
from anp_open_sdk.config.dynamic_config import dynamic_config

def get_user_cfg_list():
    """获取用户列表和目录映射"""
    user_list = []
    name_to_dir = {}
    user_dirs = dynamic_config.get('anp_sdk.user_did_path')
    for user_dir in os.listdir(user_dirs):
        cfg_path = os.path.join(user_dirs, user_dir, "agent_cfg.yaml")
        if os.path.exists(cfg_path):
            try:
                with open(cfg_path, 'r', encoding='utf-8') as f:
                    cfg = yaml.safe_load(f)
                if cfg and 'name' in cfg:
                    user_list.append(cfg['name'])
                    name_to_dir[cfg['name']] = user_dir
            except Exception as e:
                print(f"读取配置文件 {cfg_path} 出错: {e}")
    return user_list, name_to_dir

def get_user_dir_did_doc_by_did(did):
    """根据did查找对应的用户文件夹并加载配置
    返回 did_doc, user_dir
    """
    user_dirs = dynamic_config.get('anp_sdk.user_did_path')
    for user_dir in os.listdir(user_dirs):
        did_path = os.path.join(user_dirs, user_dir, "did_document.json")
        if os.path.exists(did_path):
            try:
                with open(did_path, 'r', encoding='utf-8') as f:
                    did_dict = json.load(f)
                    if did_dict.get('id') == did:
                        logger.info(f"已加载用户 {user_dir} 的 DID 文档")
                        return True, did_dict, user_dir
            except Exception as e:
                logger.error(f"读取DID文档 {did_path} 出错: {e}")
                continue
    
    logger.error(f"未找到DID为 {did} 的用户文档")
    return False, None, None

def did_create_user(user_iput: dict):
    """创建DID
    
    Args:
        params: 包含以下字段的字典：
            name: 用户名
            host: 主机名
            port: 端口号
            dir: 路径段
            type: 智能体类型
    """
    from agent_connect.authentication.did_wba import create_did_wba_document
    import json
    import os
    from datetime import datetime
    import re

    # 验证所有必需字段
    required_fields = ['name', 'host', 'port', 'dir', 'type']
    if not all(field in user_iput for field in required_fields):
        logger.error("缺少必需的参数字段")
        return None

    userdid_filepath = dynamic_config.get('anp_sdk.user_did_path')
    userdid_filepath = path_resolver.resolve_path(userdid_filepath)
    # 检查用户名是否重复
    def get_existing_usernames(userdid_filepath):
        if not os.path.exists(userdid_filepath):
            return []
        usernames = []
        for d in os.listdir(userdid_filepath):
            if os.path.isdir(os.path.join(userdid_filepath, d)):
                cfg_path = os.path.join(userdid_filepath, d, 'agent_cfg.yaml')
                if os.path.exists(cfg_path):
                    with open(cfg_path, 'r') as f:
                        try:
                            cfg = yaml.safe_load(f)
                            if cfg and 'name' in cfg:
                                usernames.append(cfg['name'])
                        except:
                            pass
        return usernames

    base_name = user_iput['name']
    existing_names = get_existing_usernames(userdid_filepath)
    
    if base_name in existing_names:
        # 添加日期后缀
        date_suffix = datetime.now().strftime('%Y%m%d')
        new_name = f"{base_name}_{date_suffix}"
        
        # 如果带日期的名字也存在，添加序号
        if new_name in existing_names:
            pattern = f"{re.escape(new_name)}_?(\d+)?"
            matches = [re.match(pattern, name) for name in existing_names]
            numbers = [int(m.group(1)) if m and m.group(1) else 0 for m in matches if m]
            next_number = max(numbers + [0]) + 1
            new_name = f"{new_name}_{next_number}"
        
        user_iput['name'] = new_name
        logger.info(f"用户名 {base_name} 已存在，使用新名称：{new_name}")


    userdid_hostname = user_iput['host']
    userdid_port = user_iput['port']
    unique_id = secrets.token_hex(8)
    userdid_filepath = os.path.join(userdid_filepath, f"user_{unique_id}")

    path_segments = [user_iput['dir'], user_iput['type'], unique_id]
    agent_description_url = f"http://{userdid_hostname}:{userdid_port}/{user_iput['dir']}/{user_iput['type']}{unique_id}/ad.json"

    did_document, keys = create_did_wba_document(
        hostname=userdid_hostname,
        port=userdid_port,
        path_segments=path_segments,
        agent_description_url=agent_description_url
    )

    os.makedirs(userdid_filepath, exist_ok=True)
    with open(f"{userdid_filepath}/did_document.json", "w") as f:
        json.dump(did_document, f, indent=4)

    for key_id, (private_key_pem, public_key_pem) in keys.items():
        with open(f"{userdid_filepath}/{key_id}_private.pem", "wb") as f:
            f.write(private_key_pem)
        with open(f"{userdid_filepath}/{key_id}_public.pem", "wb") as f:
            f.write(public_key_pem)
    
    time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    agent_cfg = {
        "name": user_iput['name'],
        "unique_id": unique_id,
        "did": did_document["id"],
        "type": user_iput['type'],
        "owner": {"name": "anpsdk 创造用户", "@id": "https://localhost"},
        "description": "anpsdk的测试用户",
        "version": "0.1.0",
        "created_at": time
    }

    with open(f"{userdid_filepath}/agent_cfg.yaml", "w", encoding='utf-8') as f:
        yaml.dump(agent_cfg, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


    # 生成 JWT 密钥
    private_key = RSA.generate(2048).export_key()
    public_key = RSA.import_key(private_key).publickey().export_key()

    # 测试 JWT 密钥
    testcontent = {"user_id": 123}
    token = create_jwt(testcontent, private_key)
    token = verify_jwt(token, public_key)

    if testcontent["user_id"] == token["user_id"]:
        with open(f"{userdid_filepath}/private_key.pem", "wb") as f:
            f.write(private_key)
        with open(f"{userdid_filepath}/public_key.pem", "wb") as f:
            f.write(public_key)



    logger.info(f"DID创建成功: {did_document['id']}")
    logger.info(f"DID文档已保存到: {userdid_filepath}")
    logger.info(f"密钥已保存到: {userdid_filepath}")
    logger.info(f"用户文件已保存到: {userdid_filepath}")
    logger.info(f"jwt密钥已保存到: {userdid_filepath}")


    if user_iput['type'] == "agent":
        agent_dir = os.path.join(userdid_filepath, "agent")
        os.makedirs(agent_dir, exist_ok=True)
        logger.info(f"为agent创建目录: {agent_dir}")
    return did_document


def create_jwt(content: dict, private_key: str) -> str:
    """使用私钥创建 JWT token
    
    Args:
        content: 需要编码的内容
        private_key: RSA 私钥字符串
    
    Returns:
        str: JWT token
    """
    try:
        # 设置 JWT header
        headers = {
            'alg': 'RS256',
            'typ': 'JWT'
        }
        # 生成 JWT token
        token = jwt.encode(
            payload=content,
            key=private_key,
            algorithm='RS256',
            headers=headers
        )
        return token
    except Exception as e:
        logger.error(f"生成 JWT token 失败: {e}")
        return None

def verify_jwt(token: str, public_key: str) -> dict:
    """验证 JWT token
    
    Args:
        token: JWT token 字符串
        public_key: RSA 公钥字符串
    
    Returns:
        dict: 解码后的 payload，验证失败返回 None
    """
    try:
        # 使用公钥验证并解码 token
        payload = jwt.decode(
            jwt=token,
            key=public_key,
            algorithms=['RS256']
        )
        return payload
    except jwt.InvalidTokenError as e:
        logger.error(f"验证 JWT token 失败: {e}")
        return None

def get_response_DIDAuthHeader_Token(response_header: Dict) -> Tuple[Optional[str], Optional[str]]:
    """从响应头中获取DIDAUTHHeader

    Args:
        response_header: 响应头字典

    Returns:
        Tuple[str, str]: (did_auth_header, token) 双向认证头和访问令牌
    """
    if "Authorization" in response_header:
        auth_value = response_header["Authorization"]
        if isinstance(auth_value, str) and auth_value.startswith('Bearer '):
                token = auth_value[7:]  # Extract token after 'Bearer '
                logger.info("获得单向认证令牌，兼容无双向认证的服务")
                return "单向认证", token
        # If Authorization is a dict, execute existing logic
        else:
            try:
                auth_value =  response_header.get("Authorization")
                auth_value= json.loads(auth_value)
                token = auth_value.get("access_token")
                did_auth_header =auth_value.get("resp_did_auth_header", {}).get("Authorization")
                if did_auth_header and token:
                    logger.info("获得认证方返回的 'Authorization' 字段，进行双向校验")
                    return did_auth_header, token
                else:
                    logger.error("[错误] 解析失败，缺少必要字段" + str(auth_value))
                    return None, None
            except Exception as e:
                logger.error("[错误] 处理 Authorization 字典时出错: " + str(e))
                return None, None
    else:
        logger.info("response_header 没有 'Authorization' 字段，但是返回值200")
        return None, None

async def handle_response(response: Any) -> Dict:
    """处理响应数据

    Args:
        response: 响应数据，可以是字典或 aiohttp.ClientResponse

    Returns:
        Dict: 处理后的响应数据

    Raises:
        TypeError: 当响应类型未知时抛出
    """
    if isinstance(response, dict):  
        return response  # 直接返回字典
    elif isinstance(response, ClientResponse):  
        try:
            # 检查响应状态码
            if response.status >= 400:
                error_text = await response.text()
                logger.error(f"HTTP错误 {response.status}: {error_text}")
                return {"error": f"HTTP {response.status}", "message": error_text}

            # 检查内容类型
            content_type = response.headers.get('Content-Type', '')
            if 'application/json' in content_type:
                return await response.json()
            else:
                # 非JSON响应，返回文本
                text = await response.text()
                logger.warning(f"非JSON响应，Content-Type: {content_type}")
                return {"content": text, "content_type": content_type}
        except json.JSONDecodeError as e:
            logger.error(f"JSON解析失败: {e}")
            text = await response.text()
            return {"error": "JSON解析失败", "raw_text": text}
        except Exception as e:
            logger.error(f"处理响应时出错: {e}")
            return {"error": str(e)}
    else:
        logger.error(f"未知响应类型: {type(response)}")
        return {"error": f"未知类型: {type(response)}"}


def get_agent_cfg_by_user_dir(user_dir: str) -> dict:
        """
        从指定 user_dir 目录下加载 agent_cfg.yaml 文件，返回为字典对象。
        """
        import os
        import yaml
        did_path = Path(dynamic_config.get('anp_sdk.user_did_path'))
        did_path = did_path.joinpath( user_dir , "agent_cfg.yaml" )
        cfg_path = Path(path_resolver.resolve_path(did_path.as_posix()))

        if not os.path.isfile(cfg_path):
            raise FileNotFoundError(f"agent_cfg.yaml not found in {user_dir}")
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        return cfg