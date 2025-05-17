#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""ANP SDK 演示程序

这个程序演示了如何使用ANP SDK进行基本操作：
1. 初始化SDK和智能体
2. 注册API和消息处理器
3. 启动服务器
4. 演示智能体之间的消息和API调用
"""
import json
import asyncio
import threading
import aiohttp
from loguru import logger
from urllib.parse import urlencode, quote

from anp_sdk import LocalAgent
from anp_sdk_utils import get_user_cfg_list, get_user_cfg

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
            logger.info(f"已加载 LocalAgent: {did_dict['id']} -> 目录: {name_to_dir[selected_name]}")
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



# 演示智能体之间的消息和API调用
async def demo(sdk, agent1, agent2, agent3):
    if not all([agent1, agent2, agent3]):
        logger.error("智能体不足，无法执行演示")
        return
    
    await asyncio.sleep(1)
    
    # 演示API调用
    logger.info(f"演示：\nagent1:{agent1.name}调用\nagent2:{agent2.name}的API /info ...")
    req = {
        "req_did": agent1.id,
        "path_to": "/info",
        "method": "GET",
        "params": {"from":f"{agent1.name}"}
    }

    url_params = f"from:{agent1.name}"
    url_params = json.dumps(url_params)
    url_params = {
        "req_did": agent1.id,
        "params": url_params
    }
    url_params = urlencode(url_params)
    async with aiohttp.ClientSession() as session:
        url = f"http://localhost:{sdk.port}/agent/api/{agent2.id}/info?{url_params}"
        async with session.post(url, json=req) as response:
            resp = await response.json()
            logger.info(f"\n{agent1.name}调用{agent2.name}的/info接口后收到响应: {resp}")


    logger.info(f"演示：\nagent1:{agent1.name}用get调用\nagent2:{agent2.name}的API /info ...")
    params = f"from:{agent1.name}"
    params = json.dumps(params)
    req = {
        "req_did": agent1.id,
        "params": params
    }
    from urllib.parse import quote
    async with aiohttp.ClientSession() as session:
        url = f"http://localhost:{sdk.port}/agent/api/{agent2.id}/info"
        async with session.get(url, params=req) as response:
            resp = await response.json()
            logger.info(f"\n{agent1.name}调用{agent2.name}的/info接口后收到响应: {resp}")
    
   

    # 演示消息发送
    logger.info(f"演示：\nagent2:{agent2.name}向\nagent3:{agent3.name}发送消息 ...")
    msg = {
        "req_did": agent2.id,
        "message_type": "text",
        "content": f"你好，我是{agent2.name}"
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(f"http://localhost:{sdk.port}/agent/message/{agent3.id}", json=msg) as response:
            resp = await response.json()
            logger.info(f"\n{agent2.name}向{agent3.name}发送消息后收到响应: {resp}")
    
    logger.info(f"演示：\nagent3:{agent3.name}向\nagent1:{agent1.name}发送消息 ...")
    msg = {
        "req_did": agent3.id,
        "message_type": "text",
        "content": f"你好，我是{agent3.name}"
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(f"http://localhost:{sdk.port}/agent/message/{agent1.id}", json=msg) as response:
            resp = await response.json()
            logger.info(f"\n{agent3.name}向{agent1.name}发送消息后收到响应: {resp}")

# 主函数
def main():
    # 1. 初始化 SDK
    from anp_sdk import ANPSDK
    sdk = ANPSDK(port=9001)
    
    # 2. 加载智能体
    agents = load_agents()
    
    # 3. 注册处理器
    agents, agent1, agent2, agent3 = register_handlers(agents)
    
    # 4. 注册智能体到 SDK
    for agent in agents:
        sdk.register_agent(agent)
    
    
    # 5. 启动服务器
    sdk.start_server()
    import threading

    def start_server():
        sdk.start_server()

    server_thread = threading.Thread(target=start_server)
    server_thread.start()
    import time
    time.sleep(0.5)

    input("服务器已启动，按回车继续....")

    # 6. 启动演示任务和服务器
    if all([agent1, agent2, agent3]):
        import threading
        def run_demo():
            asyncio.run(demo(sdk, agent1, agent2, agent3))
        thread = threading.Thread(target=run_demo)
        thread.start()
        thread.join()  # 等待线程完成






if __name__ == "__main__":
    main()