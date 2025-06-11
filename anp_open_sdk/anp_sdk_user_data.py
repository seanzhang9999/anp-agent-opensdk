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

#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ANP用户工具

这个程序提供了ANP用户管理的基本功能：
1. 创建新用户 (-n)
2. 列出所有用户 (-l)
3. 按服务器信息排序显示用户 (-s)
"""

import os
import json
import secrets
from pathlib import Path

import jwt
import yaml
import argparse
import aiohttp
import asyncio
from datetime import datetime

from Crypto.PublicKey import RSA
from loguru import logger
from typing import Dict, List, Tuple, Optional, Any

from anp_open_sdk.config import path_resolver
from anp_open_sdk.config.path_resolver import path_resolver
from anp_open_sdk.config.dynamic_config import dynamic_config

def create_user(args):
    """创建新用户
    
    Args:
        args: 包含用户信息的命令行参数
    """
    name, host, port, host_dir, agent_type = args.n
    params = {
        'name': name,
        'host': host,
        'port': int(port),
        'dir': host_dir,
        'type': agent_type,
    }
    did_document = did_create_user(params)
    if did_document:
        print(f"用户 {name} 创建成功，DID: {did_document['id']}")
    else:
        logger.error(f"用户 {name} 创建失败")

def list_users():
    """列出所有用户信息，按从新到旧创建顺序排序"""
    user_list, name_to_dir = get_user_cfg_list()
    if not user_list:
        print("未找到任何用户")
        return
    
    users_info = []
    user_dirs = dynamic_config.get('anp_sdk.user_did_path')
    
    for name in user_list:
        user_dir = name_to_dir[name]
        dir_path = os.path.join(user_dirs, user_dir)
        created_time = os.path.getctime(dir_path)
        did_path = os.path.join(dir_path, "did_document.json")
        did_id = ""
        if os.path.exists(did_path):
            with open(did_path, 'r', encoding='utf-8') as f:
                did_dict = json.load(f)
                did_id = did_dict.get('id', '')
        cfg_path = os.path.join(dir_path, "agent_cfg.yaml")
        agent_type = ""
        host = ""
        port = ""
        if os.path.exists(cfg_path):
            with open(cfg_path, 'r', encoding='utf-8') as f:
                cfg = yaml.safe_load(f)
                agent_type = cfg.get('type', '')
                if did_id and 'did:wba:' in did_id:
                    parts = did_id.split(':')[2:]
                    if len(parts) >= 2:
                        host = parts[0]
                        if ':' in parts[1]:
                            port = parts[1].split(':')[0]
        users_info.append({
            'name': name,
            'dir': user_dir,
            'did': did_id,
            'type': agent_type,
            'host': host,
            'port': port,
            'created_time': created_time,
            'created_date': datetime.fromtimestamp(created_time).strftime('%Y-%m-%d %H:%M:%S')
        })
    users_info.sort(key=lambda x: x['created_time'], reverse=True)
    print(f"找到 {len(users_info)} 个用户，按创建时间从新到旧排序：")
    for i, user in enumerate(users_info, 1):
        print(f"[{i}] 用户名: {user['name']}")
        print(f"    DID: {user['did']}")
        print(f"    类型: {user['type']}")
        print(f"    服务器: {user['host']}:{user['port']}")
        print(f"    创建时间: {user['created_date']}")
        print(f"    目录: {user['dir']}")
        print("---")

def sort_users_by_server():
    """按服务器信息（主机、端口、用户类型）排序显示用户"""
    user_list, name_to_dir = get_user_cfg_list()
    if not user_list:
        print("未找到任何用户")
        return
    
    users_info = []
    user_dirs = dynamic_config.get('anp_sdk.user_did_path')
    
    for name in user_list:
        user_dir = name_to_dir[name]
        dir_path = os.path.join(user_dirs, user_dir)
        did_path = os.path.join(dir_path, "did_document.json")
        did_id = ""
        if os.path.exists(did_path):
            with open(did_path, 'r', encoding='utf-8') as f:
                did_dict = json.load(f)
                did_id = did_dict.get('id', '')
        cfg_path = os.path.join(dir_path, "agent_cfg.yaml")
        agent_type = ""
        host = ""
        port = ""
        if os.path.exists(cfg_path):
            with open(cfg_path, 'r', encoding='utf-8') as f:
                cfg = yaml.safe_load(f)
                agent_type = cfg.get('type', '')
                if did_id and 'did:wba:' in did_id:
                    parts = did_id.split(':')[2:]
                    if len(parts) >= 2:
                        host = parts[0]
                        if ':' in parts[1]:
                            port = parts[1].split(':')[0]
        users_info.append({
            'name': name,
            'dir': user_dir,
            'did': did_id,
            'type': agent_type,
            'host': host,
            'port': port
        })
    users_info.sort(key=lambda x: (x['host'], x['port'], x['type']))
    print(f"找到 {len(users_info)} 个用户，按服务器信息排序：")
    for i, user in enumerate(users_info, 1):
        print(f"[{i}] 服务器: {user['host']}:{user['port']}")
        print(f"    用户名: {user['name']}")
        print(f"    DID: {user['did']}")
        print(f"    类型: {user['type']}")
        print(f"    目录: {user['dir']}")
        print("---")

def main():
    parser = argparse.ArgumentParser(description='ANP用户工具')
    parser.add_argument('-n', nargs=5, metavar=('name', 'host', 'port', 'host_dir', 'agent_type'),
                        help='创建新用户，需要提供：用户名 主机名 端口号 主机路径 用户类型')
    parser.add_argument('-l', action='store_true', help='显示所有用户信息，按从新到旧创建顺序排序')
    parser.add_argument('-s', action='store_true', help='显示所有用户信息，按用户服务器 端口 用户类型排序')
    args = parser.parse_args()
    if args.n:
        create_user(args)
    elif args.l:
        list_users()
    elif args.s:
        sort_users_by_server()
    else:
        parser.print_help()

if __name__ == "__main__":
    main()

class LocalUserData:
    """存储单个用户的配置、DID文档和密码文件路径"""
    def __init__(self, folder_name: str, agent_cfg: Dict[str, Any], did_doc: Dict[str, Any], did_doc_path, password_paths: Dict[str, str], user_folder_path):
        self.folder_name = folder_name
        self.agent_cfg = agent_cfg
        self.did_doc = did_doc
        self.password_paths = password_paths
        self.did = did_doc.get("id")
        self.name = agent_cfg.get("name")
        self.unique_id = agent_cfg.get("unique_id")
        self.user_dir = user_folder_path
        self.did_doc_path = did_doc_path

        self.did_private_key_file_path = password_paths.get("did_private_key_file_path")
        self.did_public_key_file_path = password_paths.get("did_public_key_file_path")
        self.jwt_private_key_file_path = password_paths.get("jwt_private_key_file_path")
        self.jwt_public_key_file_path = password_paths.get("jwt_public_key_file_path")
        self.key_id = did_doc.get('key_id') or did_doc.get('publicKey', [{}])[0].get('id') if did_doc.get('publicKey') else None

class LocalUserDataManager:
    """管理本地用户数据，加载配置和DID文档"""
    def __init__(self, user_dir: Optional[str] = None):
        self._user_dir = user_dir or dynamic_config.get('anp_sdk.user_did_path')
        self.users: Dict[str, LocalUserData] = {}
        self.load_users()

    @property
    def user_dir(self):
        return self._user_dir

    def load_users(self):
        """遍历用户目录，加载每个用户的数据"""
        if not os.path.isdir(self._user_dir):
            logger.warning(f"用户目录不存在: {self._user_dir}")
            return

        for entry in os.scandir(self._user_dir):
            if entry.is_dir() and (entry.name.startswith('user_') or entry.name.startswith('user_hosted_')):
                user_folder_path = entry.path
                folder_name = entry.name
                try:
                    cfg_path = os.path.join(user_folder_path, 'agent_cfg.yaml')
                    agent_cfg = {}
                    if os.path.exists(cfg_path):
                        with open(cfg_path, 'r', encoding='utf-8') as f:
                            agent_cfg = yaml.safe_load(f)
                    did_doc_path = os.path.join(user_folder_path, 'did_document.json')
                    did_doc = {}
                    if os.path.exists(did_doc_path):
                        with open(did_doc_path, 'r', encoding='utf-8') as f:
                            did_doc = json.load(f)
                    key_id = did_doc.get('key_id') or did_doc.get('publicKey', [{}])[0].get('id') if did_doc.get('publicKey') else dynamic_config.get('anp_sdk.user_did_key_id')
                    did_private_key_file_path = os.path.join(user_folder_path, f"{key_id}_private.pem")
                    did_public_key_file_path = os.path.join(user_folder_path, f"{key_id}_public.pem")
                    jwt_private_key_file_path = os.path.join(user_folder_path, 'private_key.pem')
                    jwt_public_key_file_path = os.path.join(user_folder_path, 'public_key.pem')
                    password_paths = {
                        "did_private_key_file_path": did_private_key_file_path,
                        "did_public_key_file_path": did_public_key_file_path,
                        "jwt_private_key_file_path": jwt_private_key_file_path,
                        "jwt_public_key_file_path": jwt_public_key_file_path
                    }
                    if did_doc and agent_cfg:
                         user_data = LocalUserData(folder_name, agent_cfg, did_doc, did_doc_path, password_paths, user_folder_path)
                         self.users[user_data.did] = user_data
                except Exception as e:
                    logger.error(f"加载用户数据失败 ({folder_name}): {e}")
            else:
                logger.warning(f"不合格的文件或文件夹: {entry.name}")

        logger.info(f"加载用户数据共 {len(self.users)} 个用户")

    def get_user_data(self, did: str) -> Optional[LocalUserData]:
        """根据DID获取用户数据"""
        return self.users.get(did)

    def get_all_users(self) -> List[LocalUserData]:
        """获取所有加载的用户数据"""
        return list(self.users.values())

    def get_user_data_by_name(self, name: str) -> Optional[LocalUserData]:
        """根据智能体名称获取用户数据"""
        for user_data in self.users.values():
            if user_data.name == name:
                return user_data
        return None

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

def did_create_user(user_iput: dict, *, did_hex: bool = True, did_check_unique: bool = True):
    """创建DID
    Args:
        params: 包含以下字段的字典：
            name: 用户名
            host: 主机名
            port: 端口号
            dir: 路径段
            type: 智能体类型
        did_hex: 是否在DID末尾加8位hex
        did_check_unique: 如果不加hex，是否强制检查唯一性
    """
    from agent_connect.authentication.did_wba import create_did_wba_document
    import json
    import os
    from datetime import datetime
    import re
    import urllib.parse

    required_fields = ['name', 'host', 'port', 'dir', 'type']
    if not all(field in user_iput for field in required_fields):
        logger.error("缺少必需的参数字段")
        return None

    userdid_filepath = dynamic_config.get('anp_sdk.user_did_path')
    userdid_filepath = path_resolver.resolve_path(userdid_filepath)

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
        date_suffix = datetime.now().strftime('%Y%m%d')
        new_name = f"{base_name}_{date_suffix}"
        if new_name in existing_names:
            pattern = f"{re.escape(new_name)}_?(\\d+)?"
            matches = [re.match(pattern, name) for name in existing_names]
            numbers = [int(m.group(1)) if m and m.group(1) else 0 for m in matches if m]
            next_number = max(numbers + [0]) + 1
            new_name = f"{new_name}_{next_number}"
        user_iput['name'] = new_name
        logger.info(f"用户名 {base_name} 已存在，使用新名称：{new_name}")

    userdid_hostname = user_iput['host']
    userdid_port = int(user_iput['port'])
    unique_id = secrets.token_hex(8) if did_hex else None

    did_parts = ['did', 'wba', userdid_hostname]
    if userdid_port not in (80, 443):
        did_parts.append(f"3A{userdid_port}")
    if user_iput['dir']:
        did_parts.append(urllib.parse.quote(user_iput['dir'], safe=''))
    if user_iput['type']:
        did_parts.append(urllib.parse.quote(user_iput['type'], safe=''))
    if did_hex:
        did_parts.append(unique_id)
    did_id = ':'.join(did_parts)

    if not did_hex and did_check_unique:
        for d in os.listdir(userdid_filepath):
            did_path = os.path.join(userdid_filepath, d, 'did_document.json')
            if os.path.exists(did_path):
                with open(did_path, 'r', encoding='utf-8') as f:
                    did_dict = json.load(f)
                    if did_dict.get('id') == did_id:
                        logger.error(f"DID已存在: {did_id}")
        return None

    user_dir_name = f"user_{unique_id}" if did_hex else f"user_{user_iput['name']}"
    userdid_filepath = os.path.join(userdid_filepath, user_dir_name)

    path_segments = [user_iput['dir'], user_iput['type']]
    if did_hex:
        path_segments.append(unique_id)
    agent_description_url = f"http://{userdid_hostname}:{userdid_port}/{user_iput['dir']}/{user_iput['type']}{unique_id if did_hex else ''}/ad.json"

    did_document, keys = create_did_wba_document(
        hostname=userdid_hostname,
        port=userdid_port,
        path_segments=path_segments,
        agent_description_url=agent_description_url
        )
    did_document['id'] = did_id
    if keys:
        did_document['key_id'] = list(keys.keys())[0]

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

    private_key = RSA.generate(2048).export_key()
    public_key = RSA.import_key(private_key).publickey().export_key()
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
        headers = {
            'alg': 'RS256',
            'typ': 'JWT'
        }
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
        payload = jwt.decode(
            jwt=token,
            key=public_key,
            algorithms=['RS256']
        )
        return payload
    except jwt.InvalidTokenError as e:
        logger.error(f"验证 JWT token 失败: {e}")
        return None

def get_agent_cfg_by_user_dir(user_dir: str) -> dict:
    """
    从指定 user_dir 目录下加载 agent_cfg.yaml 文件，返回为字典对象。
    """
    import os
    import yaml
    did_path = Path(dynamic_config.get('anp_sdk.user_did_path'))
    did_path = did_path.joinpath(user_dir, "agent_cfg.yaml")
    cfg_path = Path(path_resolver.resolve_path(did_path.as_posix()))
    if not os.path.isfile(cfg_path):
        raise FileNotFoundError(f"agent_cfg.yaml not found in {user_dir}")
    with open(cfg_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return cfg
