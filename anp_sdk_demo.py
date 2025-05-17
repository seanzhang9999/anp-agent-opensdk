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

from anp_sdk import ANPSDK, LocalAgent, RemoteAgent
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
    
async def agent_api_call_post(sdk, caller_agent:str, target_agent:str, api_path: str, params: dict = None):
    """通过 POST 方式调用智能体的 API
    
    Args:
        sdk: ANPSDK 实例
        caller_agent: 调用方智能体
        target_agent: 目标智能体
        api_path: API 路径
        params: API 参数
    """

    caller_agent_obj = sdk.get_agent(caller_agent)
    target_agent_obj = RemoteAgent(target_agent)
    req = {
        "params": params or {}
    }
    
    url_params = {
        "req_did": caller_agent_obj.id,
   }
    url_params = urlencode(url_params)

    async with aiohttp.ClientSession() as session:
        url = f"http://{target_agent_obj.host}:{target_agent_obj.port}/agent/api/{target_agent_obj.id}{api_path}?{url_params}"
        async with session.post(url, json=req) as response:
            resp = await response.json()
            return resp

async def agent_api_call_get(sdk, caller_agent:str, target_agent:str, api_path: str, params: dict = None):
        """通过 GET 方式调用智能体的 API
        
        Args:
            sdk: ANPSDK 实例
            caller_agent: 调用方智能体
            target_agent: 目标智能体
            api_path: API 路径
            params: API 参数
        """

        caller_agent_obj = sdk.get_agent(caller_agent)
        target_agent_obj = RemoteAgent(target_agent)
        url_params = {
            "req_did": caller_agent_obj.id,
            "params": json.dumps(params) if params else ""
        }

        async with aiohttp.ClientSession() as session:
            url = f"http://{target_agent_obj.host}:{target_agent_obj.port}/agent/api/{target_agent_obj.id}{api_path}"
            async with session.get(url, params=url_params) as response:
                resp = await response.json()
                return resp

async def demo(sdk, agent1, agent2, agent3):
    """演示智能体之间的消息和API调用"""
    # 演示API调用
    logger.info(f"演示：\nagent1:{agent1.name}post调用\nagent2:{agent2.name}的API /info ...")
    resp = await agent_api_call_post(sdk, agent1.id, agent2.id, "/info", {"from": f"{agent1.name}"})
    logger.info(f"\n{agent1.name}get调用{agent2.name}的/info接口后收到响应: {resp}")
           

    logger.info(f"演示：\nagent1:{agent1.name}get调用\nagent2:{agent2.name}的API /info ...")
    resp = await agent_api_call_get(sdk, agent1.id, agent2.id, "/info", {"from": f"{agent1.name}"})
    logger.info(f"\n{agent1.name}get调用{agent2.name}的/info接口后收到响应: {resp}")
   
 
    # 演示消息发送
    logger.info(f"演示：\nagent2:{agent2.name}向\nagent3:{agent3.name}发送消息 ...")
    # agent2 向 agent3 发送消息
    resp = await agent_msg_post(sdk, agent2.id, agent3.id, f"你好，我是{agent2.name}")
    logger.info(f"\n{agent2.name}向{agent3.name}发送消息后收到响应: {resp}")
    
    # agent3 向 agent1 发送消息
    logger.info(f"演示：\nagent3:{agent3.name}向\nagent1:{agent1.name}发送消息 ...")
    resp = await agent_msg_post(sdk, agent3.id, agent1.id, f"你好，我是{agent3.name}")
    logger.info(f"\n{agent3.name}向{agent1.name}发送消息后收到响应: {resp}")

async def agent_msg_post(sdk, caller_agent:str , target_agent :str, content: str, message_type: str = "text"):
    """通过 POST 方式发送消息
    
    Args:
        sdk: ANPSDK 实例
        sender_agent: 发送方智能体
        target_agent: 目标智能体
        content: 消息内容
        message_type: 消息类型，默认为text
    """

    caller_agent_obj = sdk.get_agent(caller_agent)
    target_agent_obj = RemoteAgent(target_agent)

    msg = {
        "req_did": caller_agent_obj.id,
        "message_type": message_type,
        "content": content
    }
    async with aiohttp.ClientSession() as session:
        url = f"http://{target_agent_obj.host}:{target_agent_obj.port}/agent/message/{target_agent_obj.id}"
        async with session.post(url, json=msg) as response:
            return await response.json()

# 主函数
def main():
    # 1. 初始化 SDK
    from anp_sdk import ANPSDK
    sdk = ANPSDK()
    
    # 2. 加载智能体
    agents = load_agents()
    
    # 3. 注册处理器
    agents, agent1, agent2, agent3 = register_handlers(agents)
    
    # 4. 注册智能体到 SDK
    for agent in agents:
        sdk.register_agent(agent)
        
    # 5. 启动服务器
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