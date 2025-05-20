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
3. 推送用户文档到服务器 (-p)
4. 按服务器信息排序显示用户 (-s)
"""

import os
import json
import yaml
import argparse
import aiohttp
import asyncio
from datetime import datetime
from loguru import logger
from typing import Dict, List, Tuple, Optional

from anp_open_sdk.config.path_resolver import path_resolver
from anp_open_sdk.config.dynamic_config import dynamic_config
from anp_open_sdk.anp_sdk_utils import did_create_user, get_user_cfg_list, get_user_cfg


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
    
    # 获取用户详细信息和创建时间
    users_info = []
    user_dirs = dynamic_config.get('anp_sdk.user_did_path')
    
    for name in user_list:
        user_dir = name_to_dir[name]
        dir_path = os.path.join(user_dirs, user_dir)
        
        # 获取目录创建时间作为用户创建时间
        created_time = os.path.getctime(dir_path)
        
        # 读取DID文档
        did_path = os.path.join(dir_path, "did_document.json")
        did_id = ""
        if os.path.exists(did_path):
            with open(did_path, 'r', encoding='utf-8') as f:
                did_dict = json.load(f)
                did_id = did_dict.get('id', '')
        
        # 读取配置文件获取更多信息
        cfg_path = os.path.join(dir_path, "agent_cfg.yaml")
        agent_type = ""
        host = ""
        port = ""
        if os.path.exists(cfg_path):
            with open(cfg_path, 'r', encoding='utf-8') as f:
                cfg = yaml.safe_load(f)
                agent_type = cfg.get('type', '')
                # 从DID中提取host和port
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
    
    # 按创建时间从新到旧排序
    users_info.sort(key=lambda x: x['created_time'], reverse=True)
    
    # 显示用户信息
    print(f"找到 {len(users_info)} 个用户，按创建时间从新到旧排序：")
    for i, user in enumerate(users_info, 1):
        print(f"[{i}] 用户名: {user['name']}")
        print(f"    DID: {user['did']}")
        print(f"    类型: {user['type']}")
        print(f"    服务器: {user['host']}:{user['port']}")
        print(f"    创建时间: {user['created_date']}")
        print(f"    目录: {user['dir']}")
        print("---")


async def push_user_document(user_dir: str, target_host: str, target_port: int):
    """推送用户DID文档和ad.json到指定服务器
    
    Args:
        user_dir: 用户目录
        target_host: 目标服务器主机
        target_port: 目标服务器端口
        
    Returns:
        bool: 是否成功
    """
    user_dirs = dynamic_config.get('anp_sdk.user_did_path')
    dir_path = os.path.join(user_dirs, user_dir)
    
    # 读取DID文档
    did_path = os.path.join(dir_path, "did_document.json")
    if not os.path.exists(did_path):
        logger.error(f"未找到DID文档: {did_path}")
        return False
    
    with open(did_path, 'r', encoding='utf-8') as f:
        did_document = json.load(f)
    
    # 创建ad.json文件（如果不存在）
    ad_path = os.path.join(dir_path, "ad.json")
    if not os.path.exists(ad_path):
        # 从DID文档中提取信息创建简单的ad.json
        ad_data = {
            "id": did_document.get("id", ""),
            "name": did_document.get("name", "Unknown Agent"),
            "description": "ANP Agent",
            "version": "1.0.0",
            "protocols": ["anp/1.0.0"],
            "services": []
        }
        with open(ad_path, 'w', encoding='utf-8') as f:
            json.dump(ad_data, f, indent=2)
        print(f"已创建ad.json文件: {ad_path}")
    
    # 读取ad.json
    with open(ad_path, 'r', encoding='utf-8') as f:
        ad_data = json.load(f)
    
    # 推送DID文档到服务器
    try:
        async with aiohttp.ClientSession() as session:
            # 推送DID文档
            did_url = f"http://{target_host}:{target_port}/did/register"
            async with session.post(did_url, json=did_document) as response:
                if response.status != 200:
                    logger.error(f"推送DID文档失败: {await response.text()}")
                    return False
                print(f"成功推送DID文档到 {did_url}")
            
            # 推送ad.json
            # 从DID中提取路径
            if 'did:wba:' in did_document.get("id", ""):
                parts = did_document["id"].split(':')[2:]
                if len(parts) >= 3:
                    path_segments = parts[2:]
                    ad_path = "/".join(path_segments)
                    ad_url = f"http://{target_host}:{target_port}/{ad_path}/ad.json"
                    async with session.post(ad_url, json=ad_data) as response:
                        if response.status != 200:
                            logger.error(f"推送ad.json失败: {await response.text()}")
                            return False
                        print(f"成功推送ad.json到 {ad_url}")
                else:
                    logger.error("无法从DID中提取路径信息")
                    return False
            else:
                logger.error("DID格式不正确，无法提取路径信息")
                return False
        
        return True
    except Exception as e:
        logger.error(f"推送文档时出错: {e}")
        return False


def push_user_documents():
    """选择用户并推送其文档到服务器"""
    user_list, name_to_dir = get_user_cfg_list()
    if not user_list:
        print("未找到任何用户")
        return
    
    # 显示用户列表
    print("请选择要推送的用户:")
    for i, name in enumerate(user_list, 1):
        print(f"[{i}] {name}")
    
    try:
        choice = int(input("请输入用户编号: "))
        if choice < 1 or choice > len(user_list):
            logger.error("无效的选择")
            return
        
        selected_name = user_list[choice-1]
        user_dir = name_to_dir[selected_name]
        
        # 输入目标服务器信息
        target_host = input("请输入目标服务器主机 (默认: localhost): ") or "localhost"
        target_port = int(input("请输入目标服务器端口: "))
        
        # 推送文档
        print(f"正在推送用户 {selected_name} 的文档到 {target_host}:{target_port}...")
        asyncio.run(push_user_document(user_dir, target_host, target_port))
    except ValueError:
        logger.error("请输入有效的数字")
    except Exception as e:
        logger.error(f"推送文档时出错: {e}")


def sort_users_by_server():
    """按服务器信息（主机、端口、用户类型）排序显示用户"""
    user_list, name_to_dir = get_user_cfg_list()
    if not user_list:
        print("未找到任何用户")
        return
    
    # 获取用户详细信息
    users_info = []
    user_dirs = dynamic_config.get('anp_sdk.user_did_path')
    
    for name in user_list:
        user_dir = name_to_dir[name]
        dir_path = os.path.join(user_dirs, user_dir)
        
        # 读取DID文档
        did_path = os.path.join(dir_path, "did_document.json")
        did_id = ""
        if os.path.exists(did_path):
            with open(did_path, 'r', encoding='utf-8') as f:
                did_dict = json.load(f)
                did_id = did_dict.get('id', '')
        
        # 读取配置文件获取更多信息
        cfg_path = os.path.join(dir_path, "agent_cfg.yaml")
        agent_type = ""
        host = ""
        port = ""
        if os.path.exists(cfg_path):
            with open(cfg_path, 'r', encoding='utf-8') as f:
                cfg = yaml.safe_load(f)
                agent_type = cfg.get('type', '')
                # 从DID中提取host和port
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
    
    # 按服务器信息排序：主机、端口、用户类型
    users_info.sort(key=lambda x: (x['host'], x['port'], x['type']))
    
    # 显示用户信息
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
    parser.add_argument('-p', action='store_true', help='列出用户，选择一个推送did-document和ad.json到指定服务器')
    parser.add_argument('-s', action='store_true', help='显示所有用户信息，按用户服务器 端口 用户类型排序')
    
    args = parser.parse_args()
    
    # 根据参数执行相应功能
    if args.n:
        create_user(args)
    elif args.l:
        list_users()
    elif args.p:
        push_user_documents()
    elif args.s:
        sort_users_by_server()
    else:
        # 无参数时显示帮助信息
        parser.print_help()


if __name__ == "__main__":
    main()