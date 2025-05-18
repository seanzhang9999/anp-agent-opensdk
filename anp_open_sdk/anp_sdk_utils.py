import os
import json
import yaml
from loguru import logger
from anp_open_sdk.config.dynamic_config import dynamic_config
import jwt
import json
from loguru import logger
from typing import Optional, Dict, Tuple, Any
from aiohttp import ClientResponse


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

def get_user_cfg(choice, user_list, name_to_dir):
    """根据用户选择加载用户配置"""
    user_dirs = dynamic_config.get('anp_sdk.user_did_path')
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(user_list):
            selected_name = user_list[idx]
            user_dir = name_to_dir[selected_name]
            did_path = os.path.join(user_dirs, user_dir, "did_document.json")
            if os.path.exists(did_path):
                with open(did_path, 'r', encoding='utf-8') as f:
                    did_dict = json.load(f)
                logger.info(f"已加载用户 {selected_name} 的 DID 文档")
                return True, did_dict, selected_name
            else:
                logger.error(f"未找到用户 {selected_name} 的 DID 文档")
                return False, None, selected_name
        else:
            print("无效的选择")
            return False, None, None
    except ValueError:
        print("请输入有效的数字")
        return False, None, None

def did_create_user(username, portchoice=1):
    """创建DID用户目录、DID文档和配置文件，返回用户目录和DID文档"""
    import os, json, yaml
    from anp_core.agent_connect.authentication.did_wba import create_did_wba_document

    userdid_filepath = dynamic_config.get('anp_sdk.user_did_path')
    userdid_hostname = dynamic_config.get('anp_sdk.user_did_hostname')
    if not userdid_filepath or not userdid_hostname:
        raise ValueError('dynamic_config 缺少 user_did_path 或 user_did_hostname 配置')
    # 端口处理
    port = 9001 + int(portchoice) - 1
    did = f"did:wba:{userdid_hostname}%3A{port}:wba:user:{username}"
    user_dir = os.path.join(userdid_filepath, username)
    os.makedirs(user_dir, exist_ok=True)
    # 生成DID文档
    did_document = create_did_wba_document(username, port=port, hostname=userdid_hostname)
    # 保存DID文档
    did_path = os.path.join(user_dir, "did_document.json")
    with open(did_path, 'w', encoding='utf-8') as f:
        json.dump(did_document, f, ensure_ascii=False, indent=2)
    # 生成agent_cfg.yaml
    agent_cfg = {"name": username, "did": did}
    cfg_path = os.path.join(user_dir, "agent_cfg.yaml")
    with open(cfg_path, 'w', encoding='utf-8') as f:
        yaml.safe_dump(agent_cfg, f, allow_unicode=True)
    return user_dir, did_document



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
    if isinstance(response_header, dict) and "Authorization" in response_header:
        try:
            auth_value = json.loads(response_header["Authorization"])
            token = auth_value.get("access_token")
            did_auth_header = auth_value.get("resp_did_auth_header", {}).get("Authorization")

            if did_auth_header and token:
                logger.info("获得认证方返回的 'Authorization' 字段，进行双向校验")
                return did_auth_header, token
            else:
                logger.error("[错误] 解析失败，缺少必要字段" + str(auth_value))
                return None, None
        except json.JSONDecodeError:
            logger.error("[错误] Authorization 头格式错误，无法解析 JSON:" + str(response_header["Authorization"]))
            return None, None
    else:
        logger.error("[错误] response_header 缺少 'Authorization' 字段，实际值：" + str(response_header))
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
        return await response.json()  # 解析 JSON
    else:
        raise TypeError(f"未知类型: {type(response)}")