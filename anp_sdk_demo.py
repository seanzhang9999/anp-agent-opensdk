#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""ANP SDK 演示程序

这个程序演示了如何使用ANP SDK进行基本操作：
1. 初始化SDK和智能体
2. 注册API和消息处理器
3. 启动服务器
4. 演示智能体之间的消息和API调用
"""
from typing import Optional, Dict, Tuple, Any
from types import DynamicClassAttribute
from config.dynamic_config import dynamic_config
from anp_core.auth.did_auth import send_authenticated_request,send_request_with_token,DIDWbaAuthHeader
import aiofiles
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


async def agent_auth(sdk, caller_agent:str, target_agent:str):

    caller_agent_obj = sdk.get_agent(caller_agent)
    target_agent_obj = RemoteAgent(target_agent)

    
    auth_client = DIDWbaAuthHeader(

        did_document_path=str(caller_agent_obj.did_document_path),

        private_key_path=str(caller_agent_obj.private_key_path),
        )

    base_url = f"http://{target_agent_obj.host}:{target_agent_obj.port}"

    test_url = f"{base_url}/{dynamic_config.get('anp_sdk.auth_virtual_dir')}"

    status, response, response_header ,token = await send_authenticated_request(test_url, auth_client , str(target_agent_obj.id))
    
    auth_value, token = get_response_DIDAuthHeader_Token(response_header)

    if status != 200:
        error = f"发起方发出的DID认证失败! 状态: {status}\n响应: {response}"
        return False, error

    if await check_response_DIDAtuhHeader(auth_value) is False:
        error = f"\n接收方DID认证头验证失败! 状态: {status}\n响应: {response}"
        return False, error


    if token:

        status, response = await send_request_with_token(test_url, token, caller_agent_obj.id, target_agent_obj.id)
        
        if status == 200:
            caller_agent_obj.store_token_from_remote(target_agent_obj.id,token, dynamic_config.get('anp_sdk.token_expire_time'))
            error = f"\nDID认证成功! {caller_agent_obj.id} 已保存 {target_agent_obj.id}颁发的token:{token}"
            return True, error
        else:
            error = f"\n令牌认证失败! 状态: {status}\n响应: {response}"
            return False, error
    else:
        error = "未从服务器收到令牌"
        return False, error

    
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


    if caller_agent_obj.get_token_from_remote(target_agent_obj.id) is None:
        status, error = await agent_auth(sdk, caller_agent, target_agent)
        if status is False:
            return error

    req = {
        "params": params or {}
    }
    
    url_params = {
        "req_did": caller_agent_obj.id,
    }
    url_params = urlencode(url_params)
    target_agent_path = quote(target_agent)
    
    url = f"http://{target_agent_obj.host}:{target_agent_obj.port}/agent/api/{target_agent_path}{api_path}?{url_params}"
    token = caller_agent_obj.get_token_from_remote(target_agent_obj.id)['token']

    status,response = await send_request_with_token(url, token, caller_agent_obj.id, target_agent_obj.id, method="POST" ,  json_data=req)
    response = await handle_response(response)
    return response


async def send_request_with_token(target_url: str, token: str, sender_did: str, targeter_did:str, method: str = "GET",
                                  json_data: Optional[Dict] = None) -> Tuple[int, Dict[str, Any]]:
    """
    使用已获取的令牌发送请求
    
    Args:
        target_url: 目标URL
        token: 访问令牌
        method: HTTP方法
        json_data: 可选的JSON数据
        
    Returns:
        Tuple[int, Dict[str, Any]]: 状态码和响应
    """
    try:
        headers = {
            "Authorization": f"Bearer {token}",
            "req_did": f"{sender_did}",
            "resp_did": f"{targeter_did}"
        }

        async with aiohttp.ClientSession() as session:
            if method.upper() == "GET":
                async with session.get(
                    target_url,
                    headers=headers
                ) as response:
                    status = response.status
                    response_data = await response.json() if status == 200 else {}
                    return status, response_data
            elif method.upper() == "POST":
                async with session.post(
                    target_url,
                    headers=headers,
                    json=json_data
                ) as response:
                    status = response.status
                    response_data = await response.json() if status == 200 else {}
                    return status, response_data
            else:
                logging.error(f"Unsupported HTTP method: {method}")
                return 400, {"error": "Unsupported HTTP method"}
    except Exception as e:
        logging.error(f"Error sending request with token: {e}")
        return 500, {"error": str(e)}

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

        if caller_agent_obj.get_token_from_remote(target_agent_obj.id) is None:
            status, error = await agent_auth(sdk, caller_agent, target_agent)
            if status is False:
                return error

        url_params = {
            "req_did": caller_agent_obj.id,
            "params": json.dumps(params) if params else ""
        }
        target_agent_path =  quote(target_agent)

        url = f"http://{target_agent_obj.host}:{target_agent_obj.port}/agent/api/{target_agent_path}{api_path}?{url_params}"
        token = caller_agent_obj.get_token_from_remote(target_agent_obj.id)['token']

        status,response = await send_request_with_token(url, token, caller_agent_obj.id, target_agent_obj.id, method="GET")
        response = await handle_response(response)
        return response


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

    if caller_agent_obj.get_token_from_remote(target_agent_obj.id) is None:
        status, error = await agent_auth(sdk, caller_agent, target_agent)
        if status is False:
            return error

    url_params = {
        "req_did": caller_agent_obj.id,
    }
    url_params = urlencode(url_params)
    
    target_agent_path =  quote(target_agent)

    msg = {
        "req_did": caller_agent_obj.id,
        "message_type": message_type,
        "content": content
    }

    url = f"http://{target_agent_obj.host}:{target_agent_obj.port}/agent/message/post/{target_agent_path}?{url_params}"
    token = caller_agent_obj.get_token_from_remote(target_agent_obj.id)['token']

    status,response = await send_request_with_token(url, token, caller_agent_obj.id, target_agent_obj.id, method="POST" ,  json_data=msg)
    response = await handle_response(response)
    return response


async def handle_response(response):
    if isinstance(response, dict):  
        return response  # 直接返回字典
    elif isinstance(response, aiohttp.ClientResponse):  
        return await response.json()  # 解析 JSON
    else:
        raise TypeError(f"未知类型: {type(response)}")

async def agent_msg_group_post(sdk, caller_agent:str, group_url ,group_id: str, message: str):

    caller_agent_obj = sdk.get_agent(caller_agent)
    message = {
        "content": message or {}
    }
    url_params = {
        "req_did": caller_agent_obj.id,
    }
    url_params = urlencode(url_params)
    async with aiohttp.ClientSession() as session:
        url = f"http://{group_url}/group/{group_id}/message?{url_params}"
        async with session.post(url, json=message) as response:
            resp = await response.json()
    return resp
async def agent_msg_group_members(sdk, caller_agent:str, group_url, group_id: str , action):
    caller_agent_obj = sdk.get_agent(caller_agent)
    url_params = {
        "req_did": caller_agent_obj.id,
    }
    url_params = urlencode(url_params)
    async with aiohttp.ClientSession() as session:
        url = f"http://{group_url}/group/{group_id}/members?{url_params}"
        async with session.post(url, json=action) as response:
            resp = await response.json()
    return resp
async def listen_group_messages(sdk, caller_agent:str, group_id, message_file):
    """监听群聊消息并保存到文件
    
    Args:
        agent: 智能体实例
        group_id: 群组ID
        message_file: 消息保存的文件路径
    """


    caller_agent_obj = sdk.get_agent(caller_agent)
    url_params = {
        "req_did": caller_agent_obj.id,
    }
    url_params = urlencode(url_params)

    host , port = ANPSDK.get_did_host_port_from_did(caller_agent_obj.id)
    try:
        async with aiohttp.ClientSession() as session:
            url = f"http://{host}:{port}/group/{group_id}/connect?{url_params}"
            async with session.get(url) as response:
                async for line in response.content:
                    if line:
                        try:
                            decoded_line = line.decode("utf-8").strip()  # 确保 UTF-8 解码
                            if not decoded_line:  # 额外检查是否为空
                                continue  # 跳过空数据
                            # 确保数据格式正确
                            if decoded_line.startswith("data:"):
                                decoded_line = decoded_line.replace("data:", "", 1).strip()  # 去掉 "data:"
                            message = json.loads(decoded_line)  # 解析 JSON
                            async with aiofiles.open(message_file, 'a', encoding="utf-8") as f:
                                await f.write(json.dumps(message,ensure_ascii=False) + '\n')  # 异步写入
                        except json.JSONDecodeError:
                            logger.info("JSON 解析错误:", line.decode("utf-8"))  # 记录错误数据
    except asyncio.CancelledError:
        logger.info(f"{caller_agent} 的群聊监听已停止")
    except Exception as e:
        logger.error(f"{caller_agent} 的群聊监听发生错误: {e}")

async def demo(sdk, agent1, agent2, agent3, step_mode: bool = False):
    def _pause_if_step_mode(step_name: str = ""):
        if step_mode:
            input(f"--- {step_name} --- 按任意键继续...")
    if not all([agent1, agent2, agent3]):
        logger.error("智能体不足，无法执行演示")
        return
    """演示智能体之间的消息和API调用"""

     # 演示API调用
    logger.info("\n===== 步骤1: 演示API调用 =====")
    _pause_if_step_mode("步骤1: 演示API调用")
    
    logger.info(f"演示：\nagent1:{agent1.name}post调用\nagent2:{agent2.name}的API /info ...")
    resp = await agent_api_call_post(sdk, agent1.id, agent2.id, "/info", {"from": f"{agent1.name}"})
    logger.info(f"\n{agent1.name}get调用{agent2.name}的/info接口后收到响应: {resp}")
           
    logger.info(f"演示：\nagent1:{agent1.name}get调用\nagent2:{agent2.name}的API /info ...")
    resp = await agent_api_call_get(sdk, agent1.id, agent2.id, "/info", {"from": f"{agent1.name}"})
    logger.info(f"\n{agent1.name}get调用{agent2.name}的/info接口后收到响应: {resp}")
   

    # 演示消息发送
    logger.info("\n===== 步骤2: 演示消息发送 =====")
    _pause_if_step_mode("步骤2: 演示消息发送")
    
    logger.info(f"演示：\nagent2:{agent2.name}向\nagent3:{agent3.name}发送消息 ...")
    # agent2 向 agent3 发送消息
    resp = await agent_msg_post(sdk, agent2.id, agent3.id, f"你好，我是{agent2.name}")
    logger.info(f"\n{agent2.name}向{agent3.name}发送消息后收到响应: {resp}")
    
    # agent3 向 agent1 发送消息
    logger.info(f"演示：\nagent3:{agent3.name}向\nagent1:{agent1.name}发送消息 ...")
    resp = await agent_msg_post(sdk, agent3.id, agent1.id, f"你好，我是{agent3.name}")
    logger.info(f"\n{agent3.name}向{agent1.name}发送消息后收到响应: {resp}")
    
    # 演示群聊功能
    logger.info("\n===== 步骤3: 演示群聊功能 =====")
    _pause_if_step_mode("步骤3: 演示群聊功能")
    group_id = "demo_group"
    group_url = f"localhost:{sdk.port}"  # Replace with your group URL and port numbe
    message_file = "group_messages.json"
    logger.info(f"\n演示：创建群聊并添加成员...")
    
    # 清空消息文件
    with open(message_file, 'w') as f:
        f.write('')
    
    # 创建群组并添加 agent1（创建者自动成为成员）
    action = {"action": "add", "did": agent1.id}
    resp = await agent_msg_group_members(sdk, agent1.id, group_url, group_id, action)
    logger.info(f"创建群组并添加{agent1.name}的响应: {resp}")
    
    # 添加 agent2 到群组
    action = {"action": "add", "did": agent2.id}
    resp = await agent_msg_group_members(sdk, agent1.id, group_url, group_id, action)
    logger.info(f"{agent1.name}邀请{agent2.name}的响应: {resp}")
    
    # 添加 agent3 到群组
    action = {"action": "add", "did": agent3.id}
    resp = await agent_msg_group_members(sdk, agent2.id, group_url, group_id, action)
    logger.info(f"{agent2.name}邀请{agent3.name}的响应: {resp}")
    
    # 创建 agent1 的群聊监听任务
    logger.info(f"{agent1.name} 开始监听群聊 {group_id} 的消息")
    listen_task = asyncio.create_task(listen_group_messages(sdk, agent1.id, group_id, message_file))
    
    # 等待一会儿确保监听任务启动
    await asyncio.sleep(1)
    
    # agent1 发送群聊消息
    logger.info(f"\n演示：{agent1.name}发送群聊消息...")
    message = f"大家好，我是{agent1.name}，欢迎来到群聊！"
    resp = await agent_msg_group_post(sdk, agent1.id, group_url, group_id, message)
    logger.info(f"{agent1.name}发送群聊消息的响应: {resp}")

    
    # agent2 发送群聊消息
    logger.info(f"\n演示：{agent2.name}发送群聊消息...")
    message = f"大家好，我是{agent2.name}，欢迎来到群聊！"
    resp = await agent_msg_group_post(sdk, agent2.id, group_url, group_id, message)
    logger.info(f"{agent2.name}发送群聊消息的响应: {resp}")
    
    # 等待一会儿确保消息被接收
    await asyncio.sleep(2)
    
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
    


def get_response_DIDAuthHeader_Token(response_header):

    """从响应头中获取DIDAUTHHeader

    返回值:

    - did_auth_header: 双向认证头

    - token: 访问令牌
    """

    if isinstance(response_header, dict) and "Authorization" in response_header:

        try:

            auth_value = json.loads(response_header["Authorization"])
            

            token = auth_value.get("access_token")

            did_auth_header = auth_value.get("resp_did_auth_header", {}).get("Authorization")


            if did_auth_header and token:

                print("获得双向 'Authorization' 字段，实际值：", did_auth_header)

                return did_auth_header, token
            else:

                print("[错误] 解析失败，缺少必要字段", auth_value)

                return None, None


        except json.JSONDecodeError:

            print("[错误] Authorization 头格式错误，无法解析 JSON:", response_header["Authorization"])

            return None, None
    else:

        print("[错误] response_header 缺少 'Authorization' 字段，实际值：", response_header)

        return None, None



async def check_response_DIDAtuhHeader(auth_value):

    """检查响应头中的DIDAUTHHeader是否正确"""

    from anp_core.auth.custom_did_resolver import resolve_local_did_document

    from anp_core.agent_connect.authentication.did_wba import resolve_did_wba_document

    from anp_core.agent_connect.authentication.did_wba import verify_auth_header_signature

    from anp_core.auth.did_auth import extract_auth_header_parts, verify_timestamp, is_valid_server_nonce

        # Extract header parts

    try:

        header_parts = extract_auth_header_parts(auth_value)

    except Exception as e:

        print(f"无法从AuthHeader中解析信息: {e}")

        header_parts = None

    if not header_parts:

        print("AuthHeader格式错误")  
    else:

        print(f"AuthHeader解析成功:{header_parts}")


    # 解包顺序：(did, nonce, timestamp, verification_method, signature)

    did, nonce, timestamp, resp_did, keyid, signature = header_parts

    logger.info(f"Processing DID WBA authentication - DID: {did}, Key ID: {keyid}")

    if not verify_timestamp(timestamp):

        print("Timestamp expired or invalid")

    # 验证 nonce 有效性

    # if not is_valid_server_nonce(nonce):

    #     logging.error(f"Invalid or expired nonce: {nonce}")

    #     raise HTTPException(status_code=401, detail="Invalid or expired nonce")
        

    # 尝试使用自定义解析器解析DID文档, 如果失败则使用标准解析器

    # 自定义解析器的DID地址http_url = f"http://{hostname}/wba/user/{user_id}/did.json"

    did_document = await resolve_local_did_document(did)


    # 如果自定义解析器失败，尝试使用标准解析器
    if not did_document:

        logger.info(f"本地DID解析失败，尝试使用标准解析器 for DID: {did}")

        try:

            did_document = await(resolve_did_wba_document(did))

        except Exception as e:

            logger.error(f"标准DID解析器也失败: {e}")

            did_document = None
        
    if not did_document:

        print("Failed to resolve DID document")
        

    logger.info(f"成功解析DID文档: {did}")
        

    # 验证签名

    try:

        # 重新构造完整的授权头，target URL 是为了迁就现在的url parse函数检查要求写的虚拟值

        full_auth_header = auth_value

        target_url = "virtual.WBAback" #迁就现在的url parse代码 
        

        # 调用验证函数

        is_valid, message = verify_auth_header_signature(

            auth_header=full_auth_header,

            did_document=did_document,

            service_domain=target_url
        )
            

        logger.info(f"签名验证结果: {is_valid}, 消息: {message}")

        if is_valid:

            return True
        else:

            print(f"Invalid signature: {message}")

            return False

    except Exception as e:

        print(f"验证签名时出错: {e}")




# 主函数
def main(step_mode: bool = False):
    def _pause_if_step_mode(step_name: str = ""):
        if step_mode:
            input(f"--- {step_name} --- 按任意键继续...")
    
    # 1. 初始化 SDK
    logger.info("===== 步骤1: 初始化 SDK =====")
    _pause_if_step_mode("步骤1: 初始化 SDK")
    from anp_sdk import ANPSDK
    sdk = ANPSDK()
    
    # 2. 加载智能体
    logger.info("===== 步骤2: 加载智能体 =====")
    _pause_if_step_mode("步骤2: 加载智能体")
    agents = load_agents()
    
    # 3. 注册处理器
    logger.info("===== 步骤3: 注册处理器 =====")
    _pause_if_step_mode("步骤3: 注册处理器")
    agents, agent1, agent2, agent3 = register_handlers(agents)
    
    # 4. 注册智能体到 SDK
    logger.info("===== 步骤4: 注册智能体到 SDK =====")
    _pause_if_step_mode("步骤4: 注册智能体到 SDK")
    for agent in agents:
        sdk.register_agent(agent)
        
    # 5. 启动服务器
    logger.info("===== 步骤5: 启动服务器 =====")
    _pause_if_step_mode("步骤5: 启动服务器")
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
        logger.info("===== 步骤6: 启动演示任务 =====")
        _pause_if_step_mode("步骤6: 启动演示任务")
        import threading
        def run_demo():
            asyncio.run(demo(sdk, agent1, agent2, agent3, step_mode=step_mode))
        thread = threading.Thread(target=run_demo)
        thread.start()
        thread.join()  # 等待线程完成
        
        logger.info("===== 演示完成 =====")
        _pause_if_step_mode("演示完成")






if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='ANP SDK 演示程序')
    parser.add_argument('-p', action='store_true', help='启用步骤模式，每个步骤都会暂停等待用户确认')
    args = parser.parse_args()
    main(step_mode=args.p)