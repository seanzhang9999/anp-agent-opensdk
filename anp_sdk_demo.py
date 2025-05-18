#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from Crypto.PublicKey import RSA
import os
from time import time
from datetime import datetime
import yaml
import secrets
from anp_open_sdk.service.anp_agent_api import agent_auth, agent_api_call_post, agent_api_call_get  # 已迁移到 anp_agent_api.py
from anp_open_sdk.anp_auth import check_response_DIDAtuhHeader  # 已迁移到 anp_auth.py


from anp_open_sdk.service.anp_message import agent_msg_post  # 已迁移到 anp_message.py


# 已迁移到 anp_utils.py

from anp_open_sdk.service.anp_group import agent_msg_group_post, agent_msg_group_members, listen_group_messages  # 已迁移到 anp_group.py

from colorama import init
init()  # 初始化 colorama

from anp_open_sdk.anp_sdk_utils import create_jwt, verify_jwt, get_response_DIDAuthHeader_Token, handle_response



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
    
    return agents, agent1, agent2, agent3



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



    # 创建 agent1 的群聊监听任务,指定存储位置
    script_dir = os.path.dirname(__file__)
    anp_sdk_dir = os.path.join(script_dir, dynamic_config.get("anp_sdk.group_msg_path"))
    message_file = os.path.join(anp_sdk_dir, "group_messages.json")
    with open(message_file, 'w') as f:
        f.write('')
    listen_task = asyncio.create_task(listen_group_messages(sdk, agent1.id,group_url, group_id,message_file))
    # 等待一会儿确保监听任务启动
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
    listen_task.cancel()
    try:
        await listen_task
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






# 已迁移到 anp_utils.py

def did_create_user(user_iput: dict):
    """创建DID
    
    Args:
        params: 包含以下字段的字典：
            name: 用户名
            host: 主机名
            port: 端口号
            dir1: 第一个路径段
            dir2: 第二个路径段
    """
    from anp_core.agent_connect.authentication.did_wba import create_did_wba_document
    import json
    import os
    from datetime import datetime
    import re

    # 验证所有必需字段
    required_fields = ['name', 'host', 'port', 'dir1', 'dir2']
    if not all(field in user_iput for field in required_fields):
        logger.error("缺少必需的参数字段")
        return None
    userdid_filepath = dynamic_config.get('anp_sdk.user_did_path')




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

    path_segments = [user_iput['dir1'], user_iput['dir2'], unique_id]
    agent_description_url = f"http://{userdid_hostname}:{userdid_port}/{user_iput['dir1']}/{user_iput['dir2']}{unique_id}/ad.json"

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
        "did": did_document["id"]
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
    return did_document

def did_jwt_generate():
    """生成 JWT 密钥对并进行测试"""
    import jwt
    from Crypto.PublicKey import RSA

    private_key = RSA.generate(2048).export_key()
    public_key = RSA.import_key(private_key).publickey().export_key()

    testcontent = {"user_id": 123}
    logger.info(f"原文: {testcontent}")

    token = create_jwt(testcontent, private_key)
    logger.info(f"密文: {token}")

    token = verify_jwt(token, public_key)
    logger.info(f"解密: {token}")

    if testcontent["user_id"] == token["user_id"]:
        logger.info(f"jwt正常: {token}")

    with open(f"private_key.pem", "wb") as f:
        f.write(private_key)
    with open(f"public_key.pem", "wb") as f:
        f.write(public_key)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='ANP SDK 演示程序')
    parser.add_argument('-p', action='store_true', help='启用步骤模式，每个步骤都会暂停等待用户确认')
    parser.add_argument('-f', action='store_true', help='快速模式，跳过所有等待用户确认的步骤')
    parser.add_argument('-u', nargs=5, metavar=('name', 'host', 'port', 'dir1', 'dir2'),
                        help='创建新用户，需要提供：用户名 主机名 端口号 路径段1 路径段2')
    args = parser.parse_args()

    if args.u:
        name, host, port, dir1, dir2 = args.u
        params = {
            'name': name,
            'host': host,
            'port': int(port),
            'dir1': dir1,
            'dir2': dir2
        }
        did_create_user(params)
    else:
        main(step_mode=args.p, fast_mode=args.f)