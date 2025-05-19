#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from Crypto.PublicKey import RSA
import os
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
from anp_open_sdk.auth.did_auth import send_authenticated_request,send_request_with_token,DIDWbaAuthHeader
import aiofiles
import json
import asyncio
import threading
import aiohttp
from loguru import logger
from urllib.parse import urlencode, quote

from anp_sdk import ANPSDK, LocalAgent, RemoteAgent
from anp_open_sdk.anp_sdk_utils import get_user_cfg_list, get_user_cfg


# 批量加载本地DID用户并实例化LocalAgent
def load_agents():
    user_list, name_to_dir = get_user_cfg_list()
    agents = []
    for idx, name in enumerate(user_list):
        status, did_dict, selected_name = get_user_cfg(idx + 1, user_list, name_to_dir)
        if status:
            agent = LocalAgent(id=did_dict['id'], user_dir=name_to_dir[selected_name])
            agent.name = selected_name
            agents.append(agent)
            # logger.info(f"已加载 LocalAgent: {did_dict['id']} -> 目录: {name_to_dir[selected_name]}")
        else:
            logger.warning(f"加载用户 {name} 失败")
    return agents

# 注册API和消息处理器
def register_handlers(agents):
    if len(agents) < 3:
        logger.error("本地DID用户不足3个，无法完成全部演示")
        return agents, None, None, None
    
    agent1, agent2, agent3 = agents[0], agents[1], agents[2]
    
    # 为agent1注册API 装饰器方式
    @agent1.expose_api("/hello")
    def hello_api(request):
        return {"msg": f" {agent1.name}的/hello接口收到请求:", "param": request.get("params")}
    
    # 为agent2注册API 函数注册方式
    def info_api(request):
        return {"msg": f"{agent2.name}的/info接口收到请求:", "data": request.get("params")}
    agent2.expose_api("/info", info_api)
    
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
            async with aiofiles.open(message_file, 'a') as f:
                await f.write(json.dumps(event_data, ensure_ascii=False) + '\n')
                return
        except Exception as e:
            logger.error(f"保存消息到文件时出错: {e}")
            return
    agent1.register_group_event_handler(my_handler, group_id=None, event_type=None)

    
    return agents, agent1, agent2, agent3,



async def demo(sdk, agent1, agent2, agent3, step_mode: bool = False):
    def _pause_if_step_mode(step_name: str = ""):
        if step_mode:
            from colorama import Fore, Style
            input(f"{Fore.GREEN}--- {step_name} ---{Style.RESET_ALL} {Fore.YELLOW}按任意键继续...{Style.RESET_ALL}")
    if not all([agent1, agent2, agent3]):
        logger.error("智能体不足，无法执行演示")
        return
    """演示智能体之间的消息和API调用"""

     # 演示API调用
    _pause_if_step_mode("步骤1: 演示API调用,第一次请求会包含did双向认证和颁发token,log比较长")
 

    resp = await agent_api_call_post(sdk, agent1.id, agent2.id, "/info", {"from": f"{agent1.name}"})
    logger.info(f"{agent1.name}get调用{agent2.name}的/info接口后收到响应: {resp}")

    _pause_if_step_mode("post请求到/info接口,header提交authorization认证头,url提交req_did,resp_did,body传输params")

          
    logger.info(f"演示agent1:{agent1.name}get调用agent2:{agent2.name}的API /info接口")
    resp = await agent_api_call_get(sdk, agent1.id, agent2.id, "/info", {"from": f"{agent1.name}"})
    logger.info(f"{agent1.name}get调用{agent2.name}的/info接口后收到响应: {resp}")
   
    _pause_if_step_mode("get请求到/info接口,header提交authorization认证头,url提交req_did,resp_did,params")

    # 演示消息发送
    _pause_if_step_mode("步骤2: 演示消息发送,双方第一次消息发送会包含did双向认证和颁发token,注意观察")
    
    logger.info(f"演示：agent2:{agent2.name}向agent3:{agent3.name}发送消息 ...")
    # agent2 向 agent3 发送消息
    resp = await agent_msg_post(sdk, agent2.id, agent3.id, f"你好，我是{agent2.name}")
    logger.info(f"\n{agent2.name}向{agent3.name}发送消息后收到响应: {resp}")

    _pause_if_step_mode("post请求发送消息,使用token认证,body传递消息,接收方注册消息回调接口收消息回复，请比对")

    
    # agent3 向 agent1 发送消息
    logger.info(f"演示agent3:{agent3.name}向agent1:{agent1.name}发送消息 ...")
    resp = await agent_msg_post(sdk, agent3.id, agent1.id, f"你好，我是{agent3.name}")
    logger.info(f"{agent3.name}向{agent1.name}发送消息后收到响应: {resp}")
    
    _pause_if_step_mode("post请求发送消息,使用token认证,body传递消息,接收方注册消息回调接口收消息回复，请比对")

    # 演示群聊功能
    _pause_if_step_mode("步骤3: 演示群聊功能,群聊当前未加入认证,未来计划用did-vc模式,即创建群组者给其他用户颁发vc,加入者使用vc认证加入群聊")
    group_id = "demo_group"
    group_url = f"localhost:{sdk.port}"  #理论上群聊可以在任何地方# Replace with your group URL and port numbe
    


    _pause_if_step_mode(f"群聊演示分三步:建群拉人,发消息,{agent1.name}后台sse长连接接收群聊消息存到本地后加载显示")

    
    # 创建群组并添加 agent1（创建者自动成为成员）
    action = {"action": "add", "did": agent1.id}
    resp = await agent_msg_group_members(sdk, agent1.id, group_url, group_id, action)
    logger.info(f"{agent1.name}创建群组{group_id}并添加{agent1.name},服务响应为: {resp}")

    _pause_if_step_mode(f"验证群组逻辑:第一个访问群并加人的自动成为成员")


    # 添加 agent2 到群组
    action = {"action": "add", "did": agent2.id}
    resp = await agent_msg_group_members(sdk, agent1.id, group_url, group_id, action)
    logger.info(f"{agent1.name}邀请{agent2.name}的响应: {resp}")
    
    _pause_if_step_mode(f"验证群组逻辑:创建人成员可以拉人")

    # 添加 agent3 到群组
    action = {"action": "add", "did": agent3.id}
    resp = await agent_msg_group_members(sdk, agent2.id, group_url, group_id, action)
    logger.info(f"{agent2.name}邀请{agent3.name}的响应: {resp}")
   
    _pause_if_step_mode(f"验证群组逻辑:其他成员也可以拉人，群组逻辑可以自定义")

    message_file = dynamic_config.get("anp_sdk.group_msg_path")
    message_file = path_resolver.resolve_path(message_file)
    message_file = os.path.join(message_file, "group_messages.json")
    async with aiofiles.open(message_file, 'w') as f:
        await f.write("")






    task = await agent1.start_group_listening(sdk, group_url, group_id)



    await asyncio.sleep(1)
        
    _pause_if_step_mode(f"建群拉人结束，{agent1.name} 开始启动子线程，用于监听群聊 {group_id} 存储消息到json记录文件")
    
    # agent1 发送群聊消息
    time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logger.info(f"\n演示：{agent1.name}在{time}“发送群聊消息...")
    message = f"大家好，我是{agent1.name}，现在是{time},欢迎来到群聊！"
    resp = await agent_msg_group_post(sdk, agent1.id, group_url, group_id, message)
    logger.info(f"{agent1.name}发送群聊消息的响应: {resp}")

    _pause_if_step_mode(f"{agent1.name} 向 {group_id} 发消息,所有成员可以通过sse长连接接收消息")

    
    # agent2 发送群聊消息
    await asyncio.sleep(2)
    time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logger.info(f"\n演示:{agent2.name}等待2秒后在{time}发送群聊消息...")
    message = f"大家好，我是{agent2.name}，现在是{time},欢迎来到群聊！"
    resp = await agent_msg_group_post(sdk, agent2.id, group_url, group_id, message)
    logger.info(f"{agent2.name}发送群聊消息的响应: {resp}")

    _pause_if_step_mode(f"{agent2.name} 向 {group_id} 发消息,所有成员可以通过sse长连接接收消息")

    
    # 等待一会儿确保消息被接收
    await asyncio.sleep(2)

    _pause_if_step_mode(f"{agent1.name}将停止监听，加载json文件显示sse长连接群聊收到的信息,注意观察时间戳")

    
    # 取消监听任务
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    
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

    
    # 注意：实际接收消息需要通过 SSE 连接，这里只演示了发送消息
    # 可以使用 examples/group_chat.html 页面来测试完整的群聊功能
    







# 主函数
def main(step_mode: bool = False, fast_mode: bool = False):
    def _pause_if_step_mode(step_name: str = ""):
        if step_mode:
            from colorama import Fore, Style
            input(f"{Fore.GREEN}--- {step_name} ---{Style.RESET_ALL} {Fore.YELLOW}按任意键继续...{Style.RESET_ALL}")
    
    # 1. 初始化 SDK
    _pause_if_step_mode("准备步骤1: 初始化 SDK")
    from anp_sdk import ANPSDK
    sdk = ANPSDK()
    
    # 2. 加载智能体
    _pause_if_step_mode("准备步骤2: 从本地加载智能体，方便演示")
    agents = load_agents()
    
    # 3. 注册处理器
    _pause_if_step_mode("准备步骤3: 智能体注册自己的消息处理函数和对外服务API)")
    agents, agent1, agent2, agent3 = register_handlers(agents)
    
    # 4. 注册智能体到 SDK
    _pause_if_step_mode("准备步骤4: 智能体注册到SDK,SDK会自动路由请求到各个智能体")
    for agent in agents:
        sdk.register_agent(agent)
        
    # 5. 启动服务器
    _pause_if_step_mode("准备步骤5: 启动SDK服务器，智能体的DID查询和API/消息接口对外服务就绪")
    import threading
    def start_server():
        sdk.start_server()
    server_thread = threading.Thread(target=start_server)
    server_thread.start()
    import time
    time.sleep(0.5)


    if not fast_mode:
        input("服务器已启动，查看'/'了解状态,'/docs'了解基础api,按回车继续....")

    # 6. 启动演示任务和服务器
    if all([agent1, agent2, agent3]):
        _pause_if_step_mode("准备完成:启动演示任务")
        import threading
        def run_demo():
            asyncio.run(demo(sdk, agent1, agent2, agent3, step_mode=step_mode))
        thread = threading.Thread(target=run_demo)
        thread.start()
        thread.join()  # 等待线程完成

        _pause_if_step_mode("演示完成")







if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='ANP SDK 演示程序')
    parser.add_argument('-p', action='store_true', help='启用步骤模式，每个步骤都会暂停等待用户确认')
    parser.add_argument('-f', action='store_true', help='快速模式，跳过所有等待用户确认的步骤')
    parser.add_argument('-n', nargs=5, metavar=('name', 'host', 'port', 'host_dir', 'agent_type'),
                        help='创建新用户，需要提供：用户名 主机名 端口号 主机路径 用户类型')
    args = parser.parse_args()

    if args.n:
        name, host, port, host_dir, agent_type = args.n
        params = {
            'name': name,
            'host': host,
            'port': int(port),
            'dir': host_dir,
            'type': agent_type,
        }
        did_create_user(params)
    else:
        main(step_mode=args.p, fast_mode=args.f)