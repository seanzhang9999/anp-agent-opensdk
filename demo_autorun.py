"""anp agent opensdk demo_autorun"""
import argparse

import asyncio

import json
import logging
import time
import logging

# 导入WebSocket客户端模块

from anp_core.client.ws_client import run_websocket_client
import os
import os

from pathlib import Path
import secrets
import signal

import sys

import threading
import time

from anp_sdk import ANPSDK
from typing import Any, Dict

from click.core import F
from loguru import logger

import uvicorn
import datetime

import yaml

from anp_core.client.client import ANP_req_auth, ANP_req_chat,chat_to_did

import httpx


from anp_core.auth.did_auth import (

    generate_or_load_did, 

    send_authenticated_request,

    send_request_with_token,

    DIDWbaAuthHeader
)


from config import dynamic_config

from api.anp_nlp_router import (

    resp_handle_request_msgs,

    resp_handle_request_new_msg_event as server_new_message_event,
)
from core.app import create_app as core_create_app
from core.config import settings

from anp_core.server.server import ANP_resp_start, ANP_resp_stop, server_status

from anp_core.client.client import ANP_req_auth, ANP_req_chat

from utils.log_base import set_log_color_level


import logging

from fastapi import FastAPI

from fastapi.middleware.cors import CORSMiddleware

from core.config import settings

from api import auth_router, did_router, ad_router, anp_nlp_router

from anp_core.auth.auth_middleware import auth_middleware




user_dir = os.path.dirname(os.path.abspath(__file__))

user_dir = os.path.join(user_dir, "logs")


""" 抽象ANP SDK的主要内容 

"""





class LocalAgent:

    def __init__(self, id: str, user_dir: str):
        self.id = id

        self.user_dir = Path(user_dir)

        self.token_dict = {}  # 存储 targeter_did -> access_token 映射

        self.token_info_dict = {}  # 存储 req_did -> token_info 映射，包含token、创建时间、过期时间和撤销状态

        self.key_id = dynamic_config.get('demo_autorun.user_did_key_id')

        self.userdid_filepath = dynamic_config.get('demo_autorun.user_did_path')

        self.userdid_filepath = os.path.join(self.userdid_filepath, user_dir)

        self.did_document_path = f"{self.userdid_filepath}/did_document.json"

        self.private_key_path = f"{self.userdid_filepath}/{self.key_id}_private.pem"

        self.jwt_private_key_path = f"{self.userdid_filepath}/private_key.pem"

        self.jwt_public_key_path = f"{self.userdid_filepath}/public_key.pem"


    def set_token(self, targeter_did: str, access_token: str):

        """存储 token"""

        self.token_dict[targeter_did] = access_token


    def get_token(self, targeter_did: str):

        """获取 token"""

        return self.token_dict.get(targeter_did)
    
    def store_token_info(self, req_did: str, token_info: Dict):
        """存储token详细信息
        
        Args:
            req_did: 请求方DID
            token_info: token信息字典，包含token、创建时间、过期时间和撤销状态
        """
        self.token_info_dict[req_did] = token_info
        logging.info(f"Token info for {req_did} stored in LocalAgent {self.id}")
    
    def get_token_info(self, req_did: str):
        """获取token详细信息
        
        Args:
            req_did: 请求方DID
            
        Returns:
            Dict: token信息字典，如果不存在则返回None
        """
        return self.token_info_dict.get(req_did)
    
    def revoke_token(self, req_did: str):
        """撤销token
        
        Args:
            req_did: 请求方DID
            
        Returns:
            bool: 是否成功撤销
        """
        if req_did in self.token_info_dict:
            self.token_info_dict[req_did]["is_revoked"] = True
            logging.info(f"Token for {req_did} has been revoked by LocalAgent {self.id}")
            return True
        return False


class RemoteAgent:

    def __init__(self, id: str):
        self.id = id

        host, port = get_did_host_port_from_did(id)

        self.host = host
        self.port = port
 




"""

class Msg: 封装消息的类
"""

class Msg:

    def __init__(self, content, sender: LocalAgent, targeter: RemoteAgent, channel="http"):
        self.content = content
        self.sender = sender
        self.targeter = targeter
        self.channel = channel

"""

class UserDID: 封装用户DID的类


   用户did

   did文档地址 

   对话did的token
"""



# 设置日志



logger.add(f"{user_dir}/demo_autorun.log", rotation="1000 MB", retention="7 days", encoding="utf-8")





def resp_start(port):

    """启动服务器线程
    

    Args:

        port: 可选的服务器端口号，如果提供则会覆盖默认端口
    """

    return ANP_resp_start(port=port)



def resp_stop(port=None):

    """停止服务器线程
    

    Args:

        port: 可选的服务器端口号，如果不提供则停止所有服务器
    """

    # 调用did_core中的stop_server函数

    return ANP_resp_stop(port=port)






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


def check_response_DIDAtuhHeader(auth_value):

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

    logging.info(f"Processing DID WBA authentication - DID: {did}, Key ID: {keyid}")

    if not verify_timestamp(timestamp):

        print("Timestamp expired or invalid")

    # 验证 nonce 有效性

    # if not is_valid_server_nonce(nonce):

    #     logging.error(f"Invalid or expired nonce: {nonce}")

    #     raise HTTPException(status_code=401, detail="Invalid or expired nonce")
        

    # 尝试使用自定义解析器解析DID文档, 如果失败则使用标准解析器

    # 自定义解析器的DID地址http_url = f"http://{hostname}/wba/user/{user_id}/did.json"

    did_document = asyncio.run(resolve_local_did_document(did))


    # 如果自定义解析器失败，尝试使用标准解析器
    if not did_document:

        logging.info(f"本地DID解析失败，尝试使用标准解析器 for DID: {did}")

        try:

            did_document = asyncio.run(resolve_did_wba_document(did))

        except Exception as e:

            logging.error(f"标准DID解析器也失败: {e}")

            did_document = None
        
    if not did_document:

        print("Failed to resolve DID document")
        

    logging.info(f"成功解析DID文档: {did}")
        

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
            

        logging.info(f"签名验证结果: {is_valid}, 消息: {message}")

        if is_valid:

            return True
        else:

            print(f"Invalid signature: {message}")

            return False

    except Exception as e:

        print(f"验证签名时出错: {e}")


def _pause_if_step_mode(step_mode: bool, step_name: str = ""):
    if step_mode:

        input(f"--- {step_name} --- 按任意键继续...")


async def msg_send_http(msg: Msg):



    """发送消息的实际实现
    """

    try:

        target_host, target_port = get_did_host_port_from_did(msg.targeter.id)

        base_url = f"http://{target_host}:{target_port}"

        token = msg.sender.get_token(msg.targeter.id)

        if not token:

            logger.info(f"无token，正在启动客户端认证获取token...\n并发送消息: {msg}")

            await ANP_req_auth(msg=msg)

        logger.info(f"使用token...\n发送消息: {msg}")

        status, response = await ANP_req_chat( msg=msg, token=token)


        if status == 200:

            logger.info(f"消息发送成功: {response}")

            return True, response
        else:

            logger.info(f"消息发送失败: {response}")

            return False, response


    except Exception as e:

        logging.error(f"发送消息时出错: {e}")

        print(f"发送消息时出错: {e}")
       





def anp_test(step_mode: bool = False):

    """测试函数，用于顺序测试服务器启动、消息发送和服务器停止
    

    按顺序执行以下操作并打印日志：

    1. 启动agent服务(多个user/agent在不同目录就位)

    2. 发送消息 

    3. 停止agent服务
    """

    

    


    logger.info("===== 步骤1: 启动服务器 =====")

    _pause_if_step_mode(step_mode, "步骤1: 启动服务器")

    server_result_1 = resp_start(dynamic_config.get('demo_autorun.user_did_port_1'))

    logger.info(f"服务器启动结果: {server_result_1}")

    time.sleep(2)  # 等待第一个服务器完全启动 避免多线程mac下的冲突

    server_result_2 = resp_start(dynamic_config.get('demo_autorun.user_did_port_2'))

    logger.info(f"服务器启动结果: {server_result_2}")


        


    logger.info("\n===== 步骤2: 读取本地智能体配置 =====")

    _pause_if_step_mode(step_mode, "步骤2: 读取本地智能体配置")

    user_list, name_to_dir = get_user_cfg_list()

    logger.info("\n===== 读取本地智能体配置成功 =====")



    logger.info("\n===== 步骤3: 选取认证发起方和接收方 =====")

    _pause_if_step_mode(step_mode, "步骤3: 选取认证发起方和接收方")


    status, did_dict, selected_name = get_user_cfg(1,user_list,name_to_dir)

    sender_cfg = {

        "status": status, 

        "did_dict": did_dict, 

        "name": selected_name,

        "user_dir":name_to_dir[selected_name]

        }


    logger.info(f"\n选择智能体: {sender_cfg.get('name')} did: {sender_cfg.get('did_dict')['id']} 作为发起方")


    status, did_dict, selected_name = get_user_cfg(2,user_list,name_to_dir)

    targeter_cfg = {

        "status": status, 

        "did_dict": did_dict, 

        "name": selected_name,

        "user_dir":name_to_dir[selected_name]

        }

    logger.info(f"\n选择智能体: {targeter_cfg.get('name')}did: {targeter_cfg.get('did_dict')['id']} 作为接收方")


    logger.info("\n===== 步骤4: 初始化发起方接收方智能体对象 =====")

    _pause_if_step_mode(step_mode, "步骤4: 初始化发起方接收方智能体对象")

    sender = LocalAgent(

        id=sender_cfg.get('did_dict')['id'],

        user_dir=sender_cfg.get('user_dir')
        )


    targeter = RemoteAgent( 

        id=targeter_cfg.get('did_dict')['id']
        )
    

    logger.info("\n===== 步骤5: 生成发送方DIDWbaAuthHeader =====")

    _pause_if_step_mode(step_mode, "步骤5: 生成发送方DIDWbaAuthHeader")

    auth_client = DIDWbaAuthHeader(

    did_document_path=str(sender.did_document_path),

    private_key_path=str(sender.private_key_path),
    )



    logger.info("\n===== 步骤6: 发送DID认证请求到接收方 =====")

    _pause_if_step_mode(step_mode, "步骤6: 发送DID认证请求到接收方")

    base_url = f"http://{targeter.host}:{targeter.port}"

    test_url = f"{base_url}/{dynamic_config.get('demo_autorun.auth_virutaldir')}"

    logging.info(f"发送认证请求到 {test_url}")

    status, response, response_header ,token =  asyncio.run( send_authenticated_request(test_url, auth_client , targeter.id))
    

    auth_value, token = get_response_DIDAuthHeader_Token(response_header)

    logger.info("\n取得接收方认证状态{status}\nDID认证头:{auth_value} \ntoken:{token}")


    logger.info("\n===== 步骤7: 检查接收方是否通过发起方的DID认证 =====")

    _pause_if_step_mode(step_mode, "步骤7: 检查接收方是否通过发起方的DID认证")

    if status != 200:

        logging.error(f"发起方发出的DID认证失败! 状态: {status}")

        logging.error(f"响应: {response}")
        return


    logging.info(f"发起方发出的DID认证接收方认证成功! 响应: {response}")



    logger.info("\n===== 步骤8: 验证接收方DID认证头是否正确 =====") 

    _pause_if_step_mode(step_mode, "步骤8: 验证接收方DID认证头是否正确")

    if check_response_DIDAtuhHeader(auth_value) is False:

        logger.info("\n接收方DID认证头验证失败")
        return
    

    logger.info("\n接收方DID认证头验证成功！双向DID验证通过！")


    logger.info("\n===== 步骤9: 用令牌接收方颁发的令牌尝试认证 =====") 

    _pause_if_step_mode(step_mode, "步骤9: 用令牌接收方颁发的令牌尝试认证")

    if token:

        logging.info("收到访问令牌，尝试用于下一个请求")

        status, response = asyncio.run( send_request_with_token(test_url, token, sender.id, targeter.id))
        

        if status == 200:

            logging.info(f"令牌认证成功! 保存当前令牌！响应: {response}")

            sender.set_token(targeter.id,token)
        else:

            logging.error(f"令牌认证失败! 状态: {status}")

            logging.error(f"响应: {response}")

            print("\n令牌认证失败，客户端示例完成。")
    else:

        logging.warning("未从服务器收到令牌")


    logger.info("\n===== 步骤10: 发送HTTP消息 =====") 

    _pause_if_step_mode(step_mode, "步骤10: 发送HTTP消息")

    msg = Msg(
        content="Hello World!",

        sender=sender,

        targeter=targeter,
    )
    response = asyncio.run( msg_send_http(msg))
    logger.info("收到回复：{response}")

        

    logger.info("\n===== 步骤END: 停止服务器 =====") 

    _pause_if_step_mode(step_mode, "步骤END: 停止服务器")
    stop_result = resp_stop()

    logger.info(f"服务器停止结果: {stop_result}")

    logger.info("\n===== 测试完成 =====")
    



def find_user_cfg_by_did(user_list, name_to_dir, did):

    """遍历 user_list，匹配 did_dict 是否等于 resp_id"""
    

    user_count = len(user_list)  # 获取数组长度

    logger.info(f"共有 {user_count} 个用户配置")  # 仅供调试
    

    for index in range(user_count):  # 遍历 user_list

        status, did_dict, selected_name = get_user_cfg(index+1, user_list, name_to_dir)
        

        if did_dict['id'] == did:  # 检查 did_dict 是否匹配 resp_id

            return {  

                "status": status,

                "did_dict": did_dict,

                "name": selected_name,

                "user_dir": name_to_dir[selected_name]

            }
    

    return None  # 如果没有匹配项，返回 None

def get_user_cfg_list():

    """获取用户列表
    

    从anp_core/anp_users目录中读取所有用户的配置文件，提取用户名
    

    Returns:

        tuple: (user_list, name_to_dir) 用户名列表和用户名到目录的映射
    """

    userdid_filepath = dynamic_config.get('demo_autorun.user_did_path')

    user_list = []

    name_to_dir = {}
    

    user_dirs = dynamic_config.get('demo_autorun.user_did_path')
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

    """根据用户选择加载用户配置
    

    Args:

        choice: 用户选择的序号

        user_list: 用户名列表

        name_to_dir: 用户名到目录的映射
        

    Returns:

        tuple: (status, did_dict, selected_name) 操作状态、DID文档字典和选中的用户名

        status为True表示成功，False表示失败


        did文档字典包括 did_document.json 的内容

    """

    user_dirs = os.path.join(os.path.dirname(os.path.abspath(__file__)), "anp_core", "anp_users")
    

    try:

        idx = int(choice) - 1

        if 0 <= idx < len(user_list):

            selected_name = user_list[idx]

            user_dir = name_to_dir[selected_name]
            
            

            # 加载 did_document.json

            did_path = os.path.join(user_dirs, user_dir, "did_document.json")

            if os.path.exists(did_path):

                try:

                    with open(did_path, 'r', encoding='utf-8') as f:

                        did_dict = json.load(f)

                    logger.info(f"已加载用户 {selected_name} 的 DID 文档")

                    logger.info(f"DID: {did_dict['id']}")

                    return True, did_dict, selected_name

                except Exception as e:

                    logger.error(f"加载 DID 文档出错: {e}")

                    return False, None, selected_name
            else:

                logger.error(f"未找到用户 {selected_name} 的 DID 文档")

                return False, None, selected_name
        else:

            print("无效的选择")

            return False, None, None

    except ValueError:

        print("请输入有效的数字")

        return False, None, None


def did_create_user( username , portchoice = 1):

    """创建DID"""

    from anp_core.agent_connect.authentication.did_wba import create_did_wba_document

    import json
    import os
    

    userdid_filepath = dynamic_config.get('demo_autorun.user_did_path')

    userdid_hostname = dynamic_config.get('demo_autorun.user_did_hostname')

    if portchoice == 1:

        userdid_port = dynamic_config.get('demo_autorun.user_did_port_1')
    else:

        userdid_port = dynamic_config.get('demo_autorun.user_did_port_2')


    unique_id = secrets.token_hex(8)

    userdid_filepath = os.path.join(userdid_filepath,f"user_{unique_id}")


    # 用户智能体did基本格式为 did:wba:[host]%3A[port]:wba:user:[unique_id]

    # 含义为当前地址端口下wba/user/[unique_id]目录为用户智能体的根目录

    # 其中[unique_id]为随机生成的8位十六进制字符串

    # 类似 服务智能体did基本格式为 did:wba:[host]%3A[port]:wba:agent[unique_id]

    


    path_segments = ["wba", "user", unique_id]

    agent_description_url = f"http://{userdid_hostname}:{userdid_port}/wba/user{unique_id}/ad.json"
    

    # 调用函数创建DID文档和密钥

    did_document, keys = create_did_wba_document(

        hostname = userdid_hostname,

        port = userdid_port,

        path_segments=path_segments,
        agent_description_url=agent_description_url
    )


    

    # 将DID文档保存到文件

    os.makedirs(userdid_filepath, exist_ok=True)

    with open(f"{userdid_filepath}/did_document.json", "w") as f:

        json.dump(did_document, f, indent=4)
    

    # 将私钥和公钥保存到文件

    for key_id, (private_key_pem, public_key_pem) in keys.items():

        with open(f"{userdid_filepath}/{key_id}_private.pem", "wb") as f:

            f.write(private_key_pem)

        with open(f"{userdid_filepath}/{key_id}_public.pem", "wb") as f:

            f.write(public_key_pem)




    agent_cfg = {

        "name": username,

        "unique_id": unique_id,

        "did": did_document["id"]

    }

    

    os.makedirs(userdid_filepath, exist_ok=True)

    with open(f"{userdid_filepath}/agent_cfg.yaml", "w", encoding='utf-8') as f:

        yaml.dump( agent_cfg, f, default_flow_style=False, allow_unicode=True, sort_keys=False)



    import jwt

    from Crypto.PublicKey import RSA


    # 生成 RSA 密钥对

    private_key = RSA.generate(2048).export_key()

    public_key = RSA.import_key(private_key).publickey().export_key()


    def create_jwt(payload: dict, private_key):

        payload["exp"] = datetime.datetime.utcnow() + datetime.timedelta(hours=1)  # 过期时间

        return jwt.encode(payload, private_key, algorithm="RS256")


    def verify_jwt(token: str, public_key):

        try:

            return jwt.decode(token, public_key, algorithms=["RS256"])

        except jwt.ExpiredSignatureError:

            return {"error": "Token expired"}

        except jwt.InvalidTokenError:

            return {"error": "Invalid token"}

    # 创建 JWT


    testcontent = {"user_id": 123}

    token = create_jwt(testcontent, private_key)

    token = verify_jwt(token, public_key)

    if testcontent["user_id"] == token["user_id"]:
        

        with open(f"{userdid_filepath}/private_key.pem", "wb") as f:

            f.write(private_key)

        with open(f"{userdid_filepath}/public_key.pem", "wb") as f:

            f.write(public_key)
    
    

    print(f"DID创建成功: {did_document['id']}")

    print(f"DID文档已保存到: {userdid_filepath}")

    print(f"密钥已保存到: {userdid_filepath}")

    print(f"用户文件已保存到: {userdid_filepath}")

    print(f"jwt密钥已保存到: {userdid_filepath}")
    return did_document



def did_jwt_generate():

    import jwt

    from Crypto.PublicKey import RSA


    # 生成 RSA 密钥对

    private_key = RSA.generate(2048).export_key()

    public_key = RSA.import_key(private_key).publickey().export_key()


    def create_jwt(payload: dict, private_key):

        payload["exp"] = datetime.datetime.utcnow() + datetime.timedelta(hours=1)  # 过期时间

        return jwt.encode(payload, private_key, algorithm="RS256")


    def verify_jwt(token: str, public_key):

        try:

            return jwt.decode(token, public_key, algorithms=["RS256"])

        except jwt.ExpiredSignatureError:

            return {"error": "Token expired"}

        except jwt.InvalidTokenError:

            return {"error": "Invalid token"}

    # 创建 JWT

    testcontent = {"user_id": 123}

    print(f"原文: {testcontent}")

    token = create_jwt(testcontent, private_key)

    print(f"密文: {token}")

    token = verify_jwt(token, public_key)

    print(f"解密: {token}")

    if testcontent["user_id"] == token["user_id"]:

        print(f"jwt正常: {token}")

    with open(f"private_key.pem", "wb") as f:

        f.write(private_key)

    with open(f"public_key.pem", "wb") as f:

        f.write(public_key)






if __name__ == "__main__":

    """主函数，处理命令行输入
    

    配置入口： 逐步转移到2

        1. core/config.py  settings

        2. config/dynamic_config.yaml  dynamic_config
    
    """


    # 设置日志级别

    logging.basicConfig(level=logging.INFO)

    logger = logging.getLogger(__name__)

    set_log_color_level(logging.INFO)
    
    

    print("demo authrun示例程序已启动,输入'exit'退出程序")
    

    # 主循环，处理用户输入

    while True:

        try:

            # 如果聊天线程正在运行，则等待其退出，不处理命令

            command = input("> ").strip().lower()
            if command == "test":

                anp_test(step_mode=False)
            elif command == "step":

                anp_test(step_mode=True)

            elif command == "exit":

                print("正在关闭服务...")
                resp_stop()

                break
            elif command == "test":
                anp_test()

            elif command == ("jwt"):

                did_jwt_generate()

            elif command.startswith("didnew"):

                 # 检查是否指定了用户名
                parts = command.split(" ")

                if len(parts) > 1:

                   did_create_user(parts[1])
                else:

                    print("请输入用户名。")

                    continue  # 跳过本轮命令输入
            else:

                print(f"未知命令: {command}")

        except KeyboardInterrupt:

            print("\n检测到退出信号，正在关闭...")
            resp_stop()

            break

        except Exception as e:

            print(f"错误: {e}")
            resp_stop()

            break

    print("程序已退出")

    sys.exit(0)



