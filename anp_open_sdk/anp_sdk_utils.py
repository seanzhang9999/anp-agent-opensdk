from Crypto.PublicKey import RSA
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
    from anp_core.agent_connect.authentication.did_wba import create_did_wba_document
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

    agent_cfg = {
        "name": user_iput['name'],
        "unique_id": unique_id,
        "did": did_document["id"],
        "type": user_iput['type']
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