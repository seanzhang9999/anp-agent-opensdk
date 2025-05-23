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
from Crypto.PublicKey import RSA
import requests
import os
import sys
from time import time
from datetime import datetime
import yaml
import secrets
from anp_open_sdk.config.path_resolver import path_resolver
from anp_open_sdk.service.agent_auth import agent_auth_two_way
from anp_open_sdk.service.agent_api_call import agent_api_call_post, agent_api_call_get  # 已迁移到 anp_agent_api.py
from anp_open_sdk.service.agent_auth import check_response_DIDAtuhHeader  # 已迁移到 anp_auth.py


from anp_open_sdk.service.agent_message_p2p import agent_msg_post  # 已迁移到 anp_message.py


# 已迁移到 anp_utils.py

from anp_open_sdk.service.agent_message_group import agent_msg_group_post, agent_msg_group_members, listen_group_messages  # 已迁移到 anp_group.py

from colorama import init
init()  # 初始化 colorama

from anp_open_sdk.anp_sdk_utils import create_jwt, verify_jwt, get_response_DIDAuthHeader_Token, handle_response,did_create_user



"""ANP SDK 演示程序

这个程序演示了如何使用ANP SDK进行基本操作：
1. 初始化SDK和智能体
2. 注册API和消息处理器
3. 启动服务器
4. 演示智能体之间的消息和API调用
"""
from typing import Optional, Dict, Tuple, Any
from types import DynamicClassAttribute
from anp_open_sdk.config.dynamic_config import dynamic_config
from anp_open_sdk.auth.did_auth import send_authenticated_request,send_request_with_token
from anp_open_sdk.agent_connect_hotpatch.authentication.did_wba_auth_header import DIDWbaAuthHeader
import aiofiles
import json
import asyncio
import threading
import aiohttp
from loguru import logger
from urllib.parse import urlencode, quote

from anp_open_sdk.anp_sdk import ANPSDK, LocalAgent, RemoteAgent
from anp_open_sdk.anp_sdk_utils import get_user_cfg_list
from anp_open_sdk.config.dynamic_config import dynamic_config
from anp_open_sdk.config.path_resolver import path_resolver
import os, json, yaml



def demo3_1_host_start(args):
    import uvicorn
    from fastapi import FastAPI, Request
    import shutil
    from anp_open_sdk.anp_sdk import ANPSDK, LocalAgent
    from anp_open_sdk.config.dynamic_config import dynamic_config
    from anp_open_sdk.config.path_resolver import path_resolver
    import os, yaml, json

    # 读取配置文件中的 host, port, did_hoster
    agent_cfg = dynamic_config.get('anp_sdk.agent', {})
    did_hoster = agent_cfg.get('did_hoster')
    host, port = ANPSDK.get_did_host_port_from_did(did_hoster)
    if not did_hoster:
        raise RuntimeError('dynamic_config.yaml 缺少 anp_sdk.agent.did_hoster 字段')
    # 允许命令行参数覆盖 did_hoster
    if args is not None:
        did_hoster = args[0]
    did = did_hoster
    user_did_path = dynamic_config.get('anp_sdk.user_did_path')
    user_did_path = path_resolver.resolve_path(user_did_path)
    # 在 anp_users 目录下查找 did 对应目录
    user_dir = None
    for d in os.listdir(user_did_path):
        did_path = os.path.join(user_did_path, d, 'did_document.json')
        if os.path.exists(did_path):
            with open(did_path, 'r', encoding='utf-8') as f:
                did_doc = json.load(f)
                if did_doc.get('id') == did:
                    user_dir = d
                    break
    if not user_dir:
        raise RuntimeError(f'anp_users 目录下未找到 DID={did} 的目录')
    agent_dir = os.path.join(user_did_path, user_dir)
    did_path = os.path.join(agent_dir, 'did_document.json')
    cfg_path = os.path.join(agent_dir, 'agent_cfg.yaml')
    with open(did_path, 'r', encoding='utf-8') as f:
        did_document = json.load(f)
    if os.path.exists(cfg_path):
        with open(cfg_path, 'r', encoding='utf-8') as f:
            agent_cfg = yaml.safe_load(f)
    else:
        agent_cfg = {}
    agent_cfg['host_did'] = True
    with open(cfg_path, 'w', encoding='utf-8') as f:
        yaml.dump(agent_cfg, f, allow_unicode=True, sort_keys=False)
    agent_did_host = LocalAgent(id=did_document['id'], user_dir=user_dir)
    sdk = ANPSDK()
    sdk.register_agent(agent_did_host)
    @sdk.app.post("/publish_did")
    async def publish_did(request: Request):
        data = await request.json()
        did_doc = data.get('did_document')
        ad_json = data.get('ad_json')
        if not (did_doc and ad_json):
            return {"error": "缺少 did_document 或 ad_json"}
        save_dir = os.path.join(user_did_path, user_dir)
        os.makedirs(save_dir, exist_ok=True)
        with open(os.path.join(save_dir, 'did_document.json'), 'w', encoding='utf-8') as f:
            json.dump(did_doc, f, ensure_ascii=False, indent=2)
        agent_cfg_path = os.path.join(save_dir, 'agent_cfg.yaml')
        if os.path.exists(agent_cfg_path):
            with open(agent_cfg_path, 'r', encoding='utf-8') as f:
                cfg = yaml.safe_load(f)
        else:
            cfg = {}
        cfg['host_did'] = True
        with open(agent_cfg_path, 'w', encoding='utf-8') as f:
            yaml.dump(cfg, f, allow_unicode=True, sort_keys=False)
        return {"msg": "DID文档和ad.json已保存", "path": save_dir}

    import threading
    def start_server():
        try:
            uvicorn.run(sdk.app, host=host, port=port)
        except Exception as e:
            print(f"服务器启动错误: {e}")
    server_thread = threading.Thread(target=start_server)
    server_thread.daemon = True
    server_thread.start()
    import time
    time.sleep(0.5)





# 批量加载本地DID用户并实例化LocalAgent
def demo1_1_1_load_agents(sdk: ANPSDK):
    """
    从   dynamic_config.yaml 的 anp_sdk.agent 中读取 demo_agent1, demo_agent2, demo_agent3 字段
    从   anp_users 目录下加载对应的 DID 文档
    实例化 LocalAgent 并返回
    :return: agents, user_dirs
    """
    # 使用 ANPSDK 实例中的 LocalUserDataManager
    user_data_manager = sdk.user_data_manager

    # 从 dynamic_config.yaml 获取 demo 智能体的 DID 列表
    agent_cfg = dynamic_config.get('anp_sdk.agent', {})
    agent_names = [
        agent_cfg.get('demo_agent1'),
        agent_cfg.get('demo_agent2'),
        agent_cfg.get('demo_agent3')
    ]

    agents = []
    # 遍历 DID 列表，通过 LocalUserDataManager 加载用户数据并创建 LocalAgent
    for agent_name in agent_names:
        if not agent_name:
            continue
        user_data = user_data_manager.get_user_data_by_name(agent_name)
        if user_data:
            agent = LocalAgent(sdk, id=user_data.did, name = user_data.name)
            # 从加载的用户数据中设置智能体名称
            agent.name = user_data.agent_cfg.get('name', user_data.user_dir)
            agents.append(agent)
        else:
            logger.warning(f'未找到预设名字={agent_name} 的用户数据')

    return agents

# 注册API和消息处理器
def demo1_1_2_register_handlers(agents):
    if len(agents) < 3:
        logger.error("本地DID用户不足3个，无法完成全部演示")
        return agents, None, None, None
    
    agent1, agent2, agent3 = agents[0], agents[1], agents[2]
    
    # 为agent1注册API 装饰器方式
    @agent1.expose_api("/hello",methods=["GET"])
    def hello_api(request):
        return {"msg": f" {agent1.name}的/hello接口收到请求:", "param": request.get("params")}
    
    # 为agent2注册API 函数注册方式
    def info_api(request):
        return {"msg": f"{agent2.name}的/info接口收到请求:", "data": request.get("params")}
    agent2.expose_api("/info", info_api,  methods=["POST","GET"])
    
    # 为agent1注册消息处理器 装饰器方式
    @agent1.register_message_handler("text")
    def handle_text1(msg):
        logger.info(f"{agent1.name}收到text消息: {msg}")
        return {"reply": f"{agent1.name}回复:确认收到text消息:{msg.get('content')}"}
    
    # 为agent2注册消息处理器 函数注册方式
    def handle_text2(msg):
        logger.info(f"{agent2.name}收到text消息: {msg}")
        return {"reply": f"{agent2.name}回复:确认收到text消息:{msg.get('content')}"}
    agent2.register_message_handler("text", handle_text2)
    
    # 为agent3注册通配消息处理器 装饰器方式
    @agent3.register_message_handler("*")
    def handle_any(msg):
        logger.info(f"{agent3.name}收到*类型消息: {msg}")
        return {"reply": f"{agent3.name}回复:确认收到{msg.get('type')}类型{msg.get('message_type')}格式的消息:{msg.get('content')}"}
    
    # 为agent1 注册群聊消息监听处理 函数注册方式
    async def my_handler(group_id, event_type, event_data):
        print(f"收到群{group_id}的{event_type}事件，内容：{event_data}")
        message_file = dynamic_config.get("anp_sdk.group_msg_path")
        message_file = path_resolver.resolve_path(message_file)
        message_file = os.path.join(message_file, "group_messages.json")
        try:
            async with aiofiles.open(message_file, 'a' , encoding='utf-8') as f:
                await f.write(json.dumps(event_data, ensure_ascii=False) + '\n')
                return
        except Exception as e:
            logger.error(f"保存消息到文件时出错: {e}")
            return
    agent1.register_group_event_handler(my_handler, group_id=None, event_type=None)
    
    # 为agent1注册群组消息发送处理函数
    async def group_message_handler(data):
        group_id = data.get("group_id")
        req_did = data.get("req_did", "demo_caller")
        
        # 初始化群组成员列表
        if not hasattr(agent1, "group_members"):
            agent1.group_members = {}
        if not hasattr(agent1, "group_queues"):
            agent1.group_queues = {}
            
        # 验证发送者权限
        if group_id not in agent1.group_members or req_did not in agent1.group_members[group_id]:
            return {"error": "无权在此群组发送消息"}
        
        time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 构造消息
        message = {
            "sender": req_did,
            "content": data.get("content", ""),
            "timestamp": time,
            "type": "group_message"
        }
        
        # 将消息发送到群组队列
        if group_id in agent1.group_queues:
            for queue in agent1.group_queues[group_id].values():
                await queue.put(message)
        
        return {"status": "success"}
    
    # 为agent1注册群组连接处理函数
    async def group_connect_handler(data):
        group_id = data.get("group_id")
        req_did = data.get("req_did")
        
        # 初始化群组成员列表
        if not hasattr(agent1, "group_members"):
            agent1.group_members = {}
        if not hasattr(agent1, "group_queues"):
            agent1.group_queues = {}
            
        if req_did and req_did.find("%3A") == -1:
            parts = req_did.split(":", 4)  # 分割 4 份 把第三个冒号替换成%3A
            req_did = ":".join(parts[:3]) + "%3A" + ":".join(parts[3:])
        if not req_did:
            return {"error": "未提供订阅者 DID"}

        # 验证订阅者权限
        if group_id not in agent1.group_members or req_did not in agent1.group_members[group_id]:
            return {"error": "无权订阅此群组消息"}
        
        async def event_generator():
            # 初始化群组
            if group_id not in agent1.group_queues:
                agent1.group_queues[group_id] = {}
            
            # 为该客户端创建消息队列
            client_id = f"{group_id}_{req_did}_{id(req_did)}"
            agent1.group_queues[group_id][client_id] = asyncio.Queue()
            
            try:
                # 发送初始连接成功消息
                yield f"data: {json.dumps({'status': 'connected', 'group_id': group_id})}\n\n"
                
                # 保持连接打开并等待消息
                while True:
                    try:
                        message = await asyncio.wait_for(
                            agent1.group_queues[group_id][client_id].get(),
                            timeout=30
                        )
                        yield f"data: {json.dumps(message)}\n\n"
                    except asyncio.TimeoutError:
                        # 发送心跳包
                        yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"
            except Exception as e:
                logger.error(f"群组 {group_id} SSE连接错误: {e}")
            finally:
                # 清理资源
                if group_id in agent1.group_queues and client_id in agent1.group_queues[group_id]:
                    del agent1.group_queues[group_id][client_id]
                    if not agent1.group_queues[group_id]:
                        del agent1.group_queues[group_id]
        
        return {"event_generator": event_generator()}
    
    # 为agent1注册群组成员管理处理函数
    async def group_members_handler(data):
        group_id = data.get("group_id")
        action = data.get("action")
        target_did = data.get("did")
        req_did = data.get("req_did")
        
        # 初始化群组成员列表
        if not hasattr(agent1, "group_members"):
            agent1.group_members = {}
            
        if req_did and req_did.find("%3A") == -1:
            parts = req_did.split(":", 3)  # 只分割前 3 个
            req_did = ":".join(parts[:2]) + "%3A" + ":".join(parts[2:])
            
        if not all([action, target_did, req_did]):
            return {"error": "缺少必要参数"}
        
        # 初始化群组成员列表
        if group_id not in agent1.group_members:
            agent1.group_members[group_id] = set()
        
        # 如果是空群组，第一个加入的人自动成为成员
        if not agent1.group_members[group_id]:
            if action == "add":
                agent1.group_members[group_id].add(req_did) # 添加请求者为首个成员
                if target_did != req_did:  # 如果目标不是请求者自己，也添加目标
                    agent1.group_members[group_id].add(target_did)
                    return {"status": "success", "message": "成功创建群组并添加了创建者和创建者邀请的成员"}
                return {"status": "success", "message": "成功创建群组并添加创建者为首个成员"}
            return {"error": "群组不存在"}
        
        # 验证请求者是否是群组成员
        if req_did not in agent1.group_members[group_id]:
            return {"error": "无权管理群组成员"}
        
        if action == "add":
            agent1.group_members[group_id].add(target_did)
            return {"status": "success", "message": "成功添加成员"}
        elif action == "remove":
            if target_did in agent1.group_members[group_id]:
                agent1.group_members[group_id].remove(target_did)
                return {"status": "success", "message": "成功移除成员"}
            return {"error": "成员不存在"}
        else:
            return {"error": "不支持的操作"}
    
    # 注册群组处理函数
    agent1.register_message_handler("group_message", group_message_handler)
    agent1.register_message_handler("group_connect", group_connect_handler)
    agent1.register_message_handler("group_members", group_members_handler)

    
    return agents, agent1, agent2, agent3,




class StepModeHelper:
    def __init__(self, step_mode: bool = False):
        self.step_mode = step_mode
    def pause(self, step_name: str = "" , step_id: str = None):
        if step_id is not None:
            step_name = helper_load(lang=dynamic_config.get("anp_sdk.helper_lang"), step_id=step_id)
        if self.step_mode:
            from colorama import Fore, Style
            input(f"{Fore.GREEN}--- {step_name} ---{Style.RESET_ALL} {Fore.YELLOW}按任意键继续...{Style.RESET_ALL}")



async def demo1_2_demo(sdk, agent1, agent2, agent3, step_mode: bool = False):
    step_helper = StepModeHelper(step_mode=step_mode)    
    if not all([agent1, agent2, agent3]):
        logger.error("智能体不足，无法执行演示")
        return
    """演示智能体之间的消息和API调用"""

    


     # 获取每个agent的ad.json
    step_helper.pause("获取每个agent的ad.json,查看其endpoints和name")
    


    for agent in [agent1, agent2, agent3]:
        host, port = ANPSDK.get_did_host_port_from_did(agent.id)
        user_id = str(agent.id)
        user_id = quote(user_id)
        url = f"http://{host}:{port}/wba/user/{user_id}/ad.json"
        resp = requests.get(url)

        try:
            data = resp.json()  # 尝试解析 JSON
        except ValueError:
            data = resp.text  # 如果解析失败，返回文本数据

        print(resp.status_code)  # 获取 HTTP 状态码
        print(data)  # 获取响应文本
        enpoints= data.get("ad:endpoints")

        logger.info(f"{agent.name}的ad.json信息:")
        logger.info(f"name: {data['name']}")
        logger.info(f"ad:endpoints: {enpoints}\n")

    # 演示API调用
    step_helper.pause("步骤1: 演示API调用,第一次请求会包含did双向认证和颁发token,log比较长")
 

    resp = await agent_api_call_post(sdk, agent1.id, agent2.id, "/info", {"from": f"{agent1.name}"})
    logger.info(f"{agent1.name}get调用{agent2.name}的/info接口后收到响应: {resp}")

    step_helper.pause("post请求到/info接口,header提交authorization认证头,url提交req_did,resp_did,body传输params")

          
    logger.info(f"演示agent1:{agent1.name}get调用agent2:{agent2.name}的API /info接口")
    resp = await agent_api_call_get(sdk, agent1.id, agent2.id, "/info", {"from": f"{agent1.name}"})
    logger.info(f"{agent1.name}get调用{agent2.name}的/info接口后收到响应: {resp}")
   
    step_helper.pause("get请求到/info接口,header提交authorization认证头,url提交req_did,resp_did,params")

    # 演示消息发送
    step_helper.pause("步骤2: 演示消息发送,双方第一次消息发送会包含did双向认证和颁发token,注意观察")
    
    logger.info(f"演示：agent2:{agent2.name}向agent3:{agent3.name}发送消息 ...")
    # agent2 向 agent3 发送消息
    resp = await agent_msg_post(sdk, agent2.id, agent3.id, f"你好，我是{agent2.name}")
    logger.info(f"\n{agent2.name}向{agent3.name}发送消息后收到响应: {resp}")
    step_helper.pause("post请求发送消息,使用token认证,body传递消息,接收方注册消息回调接口收消息回复，请比对")

    
    # agent3 向 agent1 发送消息
    logger.info(f"演示agent3:{agent3.name}向agent1:{agent1.name}发送消息 ...")
    resp = await agent_msg_post(sdk, agent3.id, agent1.id, f"你好，我是{agent3.name}")
    logger.info(f"{agent3.name}向{agent1.name}发送消息后收到响应: {resp}")
    step_helper.pause("post请求发送消息,使用token认证,body传递消息,接收方注册消息回调接口收消息回复，请比对")

    # 演示群聊功能
    step_helper.pause("步骤3: 演示群聊功能,群聊当前未加入认证,未来计划用did-vc模式,即创建群组者给其他用户颁发vc,加入者使用vc认证加入群聊")
    group_id = "demo_group"
    group_url = f"localhost:{sdk.port}"  #理论上群聊可以在任何地方# Replace with your group URL and port numbe
    step_helper.pause(f"群聊演示分三步:建群拉人,发消息,{agent1.name}后台sse长连接接收群聊消息存到本地后加载显示")
   
    # 创建群组并添加 agent1（创建者自动成为成员）
    action = {"action": "add", "did": agent1.id}
    resp = await agent_msg_group_members(sdk, agent1.id,agent1.id, group_url, group_id, action)
    logger.info(f"{agent1.name}创建群组{group_id}并添加{agent1.name},服务响应为: {resp}")
    step_helper.pause(f"验证群组逻辑:第一个访问群并加人的自动成为成员")

    # 添加 agent2 到群组
    action = {"action": "add", "did": agent2.id}
    resp = await agent_msg_group_members(sdk, agent1.id,agent1.id, group_url, group_id, action)
    logger.info(f"{agent1.name}邀请{agent2.name}的响应: {resp}")
    step_helper.pause(f"验证群组逻辑:创建人成员可以拉人")

    # 添加 agent3 到群组
    action = {"action": "add", "did": agent3.id}
    resp = await agent_msg_group_members(sdk, agent2.id,agent1.id, group_url, group_id, action)
    logger.info(f"{agent2.name}邀请{agent3.name}的响应: {resp}")
    step_helper.pause(f"验证群组逻辑:其他成员也可以拉人，群组逻辑可以自定义")

    # 清空群聊消息文件 准备本轮监听
    message_file = dynamic_config.get("anp_sdk.group_msg_path")
    message_file = path_resolver.resolve_path(message_file)
    message_file = os.path.join(message_file, "group_messages.json")
    async with aiofiles.open(message_file, 'w') as f:
        await f.write("")

    #启动agent1的监听任务，返回一个Task object
    task = await agent1.start_group_listening(sdk, agent1.id,group_url, group_id)
    await asyncio.sleep(1)
    step_helper.pause(f"建群拉人结束，{agent1.name} 开始启动子线程，用于监听群聊 {group_id} 存储消息到json记录文件")

    # agent1 发送群聊消息
    time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logger.info(f"\n演示：{agent1.name}在{time}“发送群聊消息...")
    message = f"大家好，我是{agent1.name}，现在是{time},欢迎来到群聊！"
    resp = await agent_msg_group_post(sdk, agent1.id, agent1.id,group_url, group_id, message)
    logger.info(f"{agent1.name}发送群聊消息的响应: {resp}")
    step_helper.pause(f"{agent1.name} 向 {group_id} 发消息,所有成员可以通过sse长连接接收消息")
    
    # agent2 发送群聊消息
    await asyncio.sleep(2)
    time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logger.info(f"\n演示:{agent2.name}等待2秒后在{time}发送群聊消息...")
    message = f"大家好，我是{agent2.name}，现在是{time},欢迎来到群聊！"
    resp = await agent_msg_group_post(sdk, agent2.id, agent1.id,group_url, group_id, message)
    logger.info(f"{agent2.name}发送群聊消息的响应: {resp}")
    step_helper.pause(f"{agent2.name} 向 {group_id} 发消息,所有成员可以通过sse长连接接收消息")
    
    # 等待一会儿确保消息被接收
    await asyncio.sleep(0.5)
    step_helper.pause(f"{agent1.name}将停止监听，加载json文件显示sse长连接群聊收到的信息,注意观察时间戳")
   
    # 取消监听任务并确保资源被清理
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        logger.info("群聊监听任务已取消")
    except Exception as e:
        logger.error(f"取消群聊监听任务时出错: {e}")
    finally:
        # 确保任何资源都被清理
        logger.info("群聊监听资源已清理")
    
    # 读取并显示接收到的消息
    logger.info(f"\n{agent1.name}接收到的群聊消息:")
    try:
        messages = []  # 存储所有消息
        with open(message_file, 'r', encoding='utf-8') as f:
            for line in f:
                messages.append(json.loads(line))  # 先收集所有消息
        logger.info(f"批量收到消息:\n{json.dumps(messages, ensure_ascii=False, indent=2)}")  # 一次性输出
    except Exception as e:
        logger.error(f"读取消息文件失败: {e}")


def demo1_1_pre_demo(step_mode: bool = False, fast_mode: bool = False):
    
    step_helper = StepModeHelper(step_mode=step_mode)  
    # 1. 初始化 SDK
    step_helper.pause(step_id = "demo1_1_0")
    from anp_open_sdk.anp_sdk import ANPSDK
    sdk = ANPSDK()
    
    # 2. 加载智能体
    step_helper.pause(step_id = "demo1_1_1")
    agents = demo1_1_1_load_agents(sdk)
    
    # 3. 注册处理器
    step_helper.pause(step_id = "demo1_1_2")
    agents, agent1, agent2, agent3 = demo1_1_2_register_handlers(agents)
    
    # 4. 注册智能体到 SDK
    step_helper.pause(step_id = "demo1_1_3")
    for agent in agents:
        sdk.register_agent(agent)
        
    # 5. 启动服务器
    step_helper.pause(step_id = "demo1_1_4")
    import threading
    def start_server():
        try:
            sdk.start_server()
        except Exception as e:
            logger.error(f"服务器启动错误: {e}")
    server_thread = threading.Thread(target=start_server)
    server_thread.daemon = True  # 设置为守护线程，确保主程序退出时线程也会退出
    server_thread.start()
    import time
    time.sleep(0.5)

    if not fast_mode:
        input("服务器已启动，查看'/'了解状态,'/docs'了解基础api,按回车继续....")
    return sdk, agent1, agent2, agent3

def helper_load(lang='zh', step_id=None):
    """从helper.json文件中读取帮助内容
    
    Args:
        lang (str, optional): 语言类型，支持'zh'和'en'. 默认为'zh'.
        step_id (str, optional): 步骤ID. 如果不指定，返回所有内容.
    
    Returns:
        str或dict: 如果指定step_id，返回对应语言的帮助内容字符串；否则返回所有帮助内容字典
    """
    import os
    import json
    
    # 获取当前文件所在目录
    current_dir = os.path.dirname(os.path.abspath(__file__))
    helper_file = os.path.join(current_dir, 'helper.json')
    
    # 检查文件是否存在
    if not os.path.exists(helper_file):
        logger.error(f"帮助文件不存在: {helper_file}")
        return {} if step_id is None else ""
    
    try:
        # 读取JSON文件
        with open(helper_file, 'r', encoding='utf-8') as f:
            helper_data = json.load(f)
        
        # 确保语言类型有效
        if lang not in ['zh', 'en']:
            logger.warning(f"不支持的语言类型: {lang}, 使用默认语言'zh'")
            lang = 'zh'
        
        # 如果指定了步骤ID，返回对应的帮助内容
        if step_id is not None:
            return helper_data.get(str(step_id), {}).get(lang, "")
        
        # 返回所有帮助内容
        return {k: v[lang] for k, v in helper_data.items() if lang in v}
        
    except json.JSONDecodeError as e:
        logger.error(f"JSON解析错误: {e}")
        return {} if step_id is None else ""
    except Exception as e:
        logger.error(f"读取帮助文件时发生错误: {e}")
        return {} if step_id is None else ""
    
import inspect


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='ANP SDK 演示程序')
    parser.add_argument('-d', action='store_true', help='开发者学习模式')
    parser.add_argument('-s', action='store_true', help='启用步骤模式，每个步骤都会暂停等待用户确认')
    parser.add_argument('-f', action='store_true', help='快速模式，跳过所有等待用户确认的步骤')
    parser.add_argument('-p', nargs='?', metavar='did',
                        help='启动DID发布专用Agent，参数为：可选DID，未指定时自动读取配置文件 did_hoster 并查找anp_users目录下对应目录')
    args = parser.parse_args()

    if args.p is not None or '-p' in sys.argv:
        demo3_1_host_start(args.p)

    elif  '-d' in sys.argv:
        step_mode = True
         # 启动开发者交互式学习模式
        step_helper = StepModeHelper(step_mode=step_mode)    
        demo2_1(step_helper)


    else:
        # 启动演示服务器
        sdk , agent1 , agent2 ,agent3  = demo1_1_pre_demo(step_mode=args.s, fast_mode=args.f)
         # 6. 启动演示任务
        if all([agent1, agent2, agent3]):
            step_helper = StepModeHelper(step_mode=args.s)
            step_helper.pause("准备完成:启动演示任务")
            import threading
            def run_demo():
                try:
                    asyncio.run(demo1_2_demo(sdk, agent1, agent2, agent3, step_mode=args.s,))
                except Exception as e:
                    logger.error(f"演示运行错误: {e}")
            thread = threading.Thread(target=run_demo)
            thread.start()
            try:
                thread.join()  # 等待线程完成
            except KeyboardInterrupt:
                logger.info("用户中断演示")
                # 这里可以添加清理代码

            step_helper.pause("演示完成")

