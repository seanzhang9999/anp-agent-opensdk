"""anp agent opensdk demo_autorun"""
import argparse
import asyncio
import json
import logging
import os
from pathlib import Path
import secrets
import signal
import sys
import threading
import time
from typing import Any, Dict
from click.core import F
from loguru import logger
import uvicorn
import datetime
import yaml
from anp_core.client.client import ANP_req_auth, ANP_req_chat,chat_to_did

from anp_core.auth.did_auth import (
    generate_or_load_did, 
    send_authenticated_request,
    send_request_with_token,
    DIDWbaAuthHeader
)

from config import dynamic_config

unique_id = None



from api.anp_nlp_router import (
    resp_handle_request_msgs,
    resp_handle_request_new_msg_event as server_new_message_event,
)
from core.app import create_app
from core.config import settings
from anp_core.server.server import ANP_resp_start, ANP_resp_stop, server_status
from anp_core.client.client import ANP_req_auth, ANP_req_chat
from utils.log_base import set_log_color_level
user_dir = os.path.dirname(os.path.abspath(__file__))
user_dir = os.path.join(user_dir, "logs")

""" 抽象ANP SDK的主要内容 

"""




class UserDID:
    def __init__(self, id: str, user_dir: str):
        self.id = id
        self.user_dir = Path(user_dir)
        self.token_dict = {}  # 存储 targeter_did -> access_token 映射
        self.key_id = dynamic_config.get('demo_autorun.user-did-key-id')
        self.userdid_filepath = dynamic_config.get('demo_autorun.user-did-path')
        self.userdid_filepath = os.path.join(self.userdid_filepath, user_dir)
        self.did_document_path = f"{self.userdid_filepath}/did_document.json"
        self.private_key_path = f"{self.userdid_filepath}/{self.key_id}_private.pem"


    def set_token(self, targeter_did: str, access_token: str):
        """存储 token"""
        self.token_dict[targeter_did] = access_token

    def get_token(self, targeter_did: str):
        """获取 token"""
        return self.token_dict.get(targeter_did)







"""
class Msg: 封装消息的类
"""
class Msg:
    def __init__(self, content, sender: UserDID, targeter):
        self.content = content
        self.sender = sender
        self.targeter = targeter

"""
class UserDID: 封装用户DID的类

   用户did
   did文档地址 
   对话did的token
"""


# 设置日志


logger.add(f"{user_dir}/demo_autorun.log", rotation="1000 MB", retention="7 days", encoding="utf-8")




# 全局变量，用于存储服务器、客户端和聊天线程
server_thread = None
chat_thread = None
ws_client_thread = None  # WebSocket客户端线程
server_running = False

ws_client_running = False  # WebSocket客户端运行状态
server_instance = None  # 存储uvicorn.Server实例

# 全局变量，用于存储最新的聊天消息
client_chat_messages = []
# 事件，用于通知聊天线程有新消息
client_new_message_event = asyncio.Event()




def agent_service_start(port=None):
    """启动服务器线程
    
    Args:
        port: 可选的服务器端口号，如果提供则会覆盖默认端口
    """
    # 如果提供了端口号，则临时修改设置中的端口
    if port is not None:
        try:
            port_num = int(port)
            dynamic_config.set('demo_autorun.user-did-port',port_num)
            logger.info(f"Use a custom port: {port_num}")
        except ValueError:
            port_num = dynamic_config.get('demo_autorun.user-did-port')
            logger.warning(f"Error port : {port}，use default port: {port_num}")
    else:
        # 如果未提供端口号，则使用配置中的端口
        port = dynamic_config.get('demo_autorun.user-did-port')

    return ANP_resp_start(port=port)


def agent_service_stop():
    """停止服务器线程"""
    # 调用did_core中的stop_server函数
    return ANP_resp_stop()




def get_did_url_from_did(did):
    host, port = None, None
    if did.startswith('did:wba:'):
        try:
            # 例：did:wba:localhost%3A9527:wba:user:7c15257e086afeba
            did_parts = did.split(':')
            if len(did_parts) > 2:
                host_port = did_parts[2]
                if '%3A' in host_port:
                    host, port = host_port.split('%3A')
        except Exception as e:
            print(f"解析did失败: {did}, 错误: {e}")
    if not host or not port:
        raise ValueError(f"未能从did解析出host和port，did: {did}")
    return host, port





async def sendmsg(msg: Msg):
    """发送消息的实际实现
    """
    try:
        target_host, target_port = get_did_url_from_did(msg.targeter)
        base_url = f"http://{target_host}:{target_port}"
        token = msg.sender.get_token(msg.targeter)
        if not token:
            print(f"无token，正在启动客户端认证获取token...\n并发送消息: {msg}")
            await ANP_req_auth(unique_id=unique_id_arg, msg=msg)
            token = os.environ.get('did-token', None)
        print(f"使用token...\n发送消息: {msg}")
        status, response = await ANP_req_chat(base_url=base_url, msg=msg, token=token)
        
    except Exception as e:
        logging.error(f"发送消息时出错: {e}")
        print(f"发送消息时出错: {e}")
       
def anp_test():
    """测试函数，用于顺序测试服务器启动、消息发送和服务器停止
    
    按顺序执行以下操作并打印日志：
    1. 启动agent服务(多个user/agent在不同目录就位)
    2. 发送消息 
    3. 停止agent服务
    """
    import time
    import logging
    import os
    
    # 设置日志级别
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    

    # 1. 启动服务器
    logger.info("===== 步骤1: 启动服务器 =====")
    server_result = agent_service_start()
    logger.info(f"服务器启动结果: {server_result}")
    logger.info("等待服务器完全启动...")
    time.sleep(3)  # 等待服务器完全启动
        
    # 2. 发送消息
    logger.info("\n===== 步骤2: 发送消息 =====")

    import httpx


    logger.info("\n获取当前agent服务的用户列表")
    user_list, name_to_dir = get_userdid_list()

    status, did_dict, selected_name = get_user_did(1,user_list,name_to_dir)
    sender = {
        "status": status, 
        "did_dict": did_dict, 
        "name": selected_name,
        "user_dir":name_to_dir[selected_name]
        }
    logger.info(f"\n选择用户: {sender.name} did: {sender.did_dict['id']} 作为发送方")

    status, did_dict, selected_name = get_user_did(2,user_list,name_to_dir)
    targeter = {
        "status": status, 
        "did_dict": did_dict, 
        "name": selected_name,
        "user_dir":name_to_dir[selected_name]
        }

    logger.info(f"\n选择用户: {targeter.name}did: {sender.did_dict['id']} 作为接收方")


    user_dir = sender["user_dir"]



    auth_client = DIDWbaAuthHeader(
    did_document_path=str(did_document_path),
    private_key_path=str(private_key_path)
    )

    base_url = f"http://{userdid_hostname}:{userdid_port}"
    test_url = f"{base_url}/wba/test"

# 4. 发送带DID WBA认证的请求
    logging.info(f"发送认证请求到 {test_url}")

    resp_did = targeter["did_dict"]
    resp_did = resp_did["id"]

    status, response, response_header ,token =  asyncio.run( send_authenticated_request(test_url, auth_client , resp_did))
    

    resp_did_auth_header = None
    if isinstance(response_header, dict) and "Authorization" in response_header:
        auth_value = response_header["Authorization"]
        auth_value = json.loads(auth_value)
        token = auth_value["access_token"]
        auth_value = auth_value["resp_did_auth_header"]["Authorization"]
        print("获得双向'authorization' 字段，实际值：", auth_value)

    else:
        print("[错误] response_header 缺少 'authorization' 字段，实际值：", response_header)
 
   
    from anp_core.auth.custom_did_resolver import resolve_local_did_document
    from anp_core.agent_connect.authentication.did_wba import resolve_did_wba_document

    from anp_core.agent_connect.authentication.did_wba import verify_auth_header_signature
    from anp_core.auth.did_auth import extract_auth_header_parts, verify_timestamp, is_valid_server_nonce
        # Extract header parts

    try:
        header_parts = extract_auth_header_parts(auth_value)
    except Exception as e:
        print(f"Error extracting header parts: {e}")
        header_parts = None
        
    if not header_parts:
        print("没有返回双向认证头")  
    else:
        print(f"返回双向认证头：{header_parts}")

    # 解包顺序：(did, nonce, timestamp, verification_method, signature)
    did, nonce, timestamp, resp_did, keyid, signature = header_parts
    logging.info(f"Processing DID WBA authentication - DID: {did}, Key ID: {keyid}")
    if not verify_timestamp(timestamp):
        print("Timestamp expired or invalid")
            
    # 验证 nonce 有效性
    # if not is_valid_server_nonce(nonce):
    #     logging.error(f"Invalid or expired nonce: {nonce}")
    #     raise HTTPException(status_code=401, detail="Invalid or expired nonce")
        
    # 尝试使用自定义解析器解析DID文档
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
        # 重新构造完整的授权头
        full_auth_header = auth_value
        target_url = "virtual.WBAback" #迁就现在的url parse代码 
        
        # 调用验证函数
        is_valid, message = verify_auth_header_signature(
            auth_header=full_auth_header,
            did_document=did_document,
            service_domain=target_url
        )
            
        logging.info(f"签名验证结果: {is_valid}, 消息: {message}")
        
        if not is_valid:
            print(f"Invalid signature: {message}")
    except Exception as e:
        print(f"验证签名时出错: {e}")
        

    if status != 200:
        logging.error(f"认证失败! 状态: {status}")
        logging.error(f"响应: {response}")
        return
        
    logging.info(f"认证成功! 响应: {response}")
    
    # 5. 如果收到令牌，验证令牌并存储
    if token:
        logging.info("收到访问令牌，尝试用于下一个请求")
        sender_did =sender["did_dict"]["id"]
        status, response = asyncio.run( send_request_with_token(test_url, token,sender_did))
        
        if status == 200:
            logging.info(f"令牌认证成功! 保存当前令牌！响应: {response}")
            os.environ['did-token'] = token
            
            user_dir = user_dir.strip("_")[1]
            # 发送消息到聊天接口
            sender_uid = sender["user_dir"]
            targeter_uid= targeter["user_dir"]
            msg = f"我是来自demo_autorun的用户聊天测试消息，发送方为: {sender_uid}，目标为: {targeter_uid}"
            result , response = asyncio.run(chat_to_did(base_url, token, msg,sender_uid, user_dir, False, False))
            print(f"发送消息到聊天接口结果: {result}, 响应: {response}")

            msg = f"我是来自demo_autorun的用户第二条聊天测试消息，发送方为: {sender_uid}，目标为: {targeter_uid}"
            result , response = asyncio.run(chat_to_did(base_url, token, msg,sender_uid, user_dir, False, False))
            print(f"发送消息到聊天接口结果: {result}, 响应: {response}")
        else:
            logging.error(f"令牌认证失败! 状态: {status}")
            logging.error(f"响应: {response}")
            print("\n令牌认证失败，客户端示例完成。")

    else:
        logging.warning("未从服务器收到令牌")
        
    # 3. 停止服务器
    logger.info("\n===== 步骤3: 停止服务器 =====")
    stop_result = agent_service_stop()
    logger.info(f"服务器停止结果: {stop_result}")
    
    logger.info("\n===== 测试完成 =====")
    




def get_userdid_list():
    """获取用户列表
    
    从anp_core/anp_users目录中读取所有用户的配置文件，提取用户名
    
    Returns:
        tuple: (user_list, name_to_dir) 用户名列表和用户名到目录的映射
    """
    userdid_filepath = dynamic_config.get('demo_autorun.user-did-path')
    user_list = []
    name_to_dir = {}
    
    # 遍历用户目录
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


def get_user_did(choice, user_list, name_to_dir):
    """根据用户选择加载DID文档
    
    Args:
        choice: 用户选择的序号
        user_list: 用户名列表
        name_to_dir: 用户名到目录的映射
        
    Returns:
        tuple: (status, did_dict, selected_name) 操作状态、DID文档字典和选中的用户名
        status为True表示成功，False表示失败
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
                    print(f"已加载用户 {selected_name} 的 DID 文档")
                    print(f"DID: {did_dict['id']}")
                    return True, did_dict, selected_name
                except Exception as e:
                    print(f"加载 DID 文档出错: {e}")
                    return False, None, selected_name
            else:
                print(f"未找到用户 {selected_name} 的 DID 文档")
                return False, None, selected_name
        else:
            print("无效的选择")
            return False, None, None
    except ValueError:
        print("请输入有效的数字")
        return False, None, None

def did_create_user( username):
    """创建DID"""
    from anp_core.agent_connect.authentication.did_wba import create_did_wba_document
    import json
    import os
    
    userdid_filepath = dynamic_config.get('demo_autorun.user-did-path')
    userdid_hostname = dynamic_config.get('demo_autorun.user-did-hostname')
    userdid_port = dynamic_config.get('demo_autorun.user-did-port')

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




# 导入WebSocket客户端模块
from anp_core.client.ws_client import run_websocket_client

def start_ws_client(client_id=None):
    """启动WebSocket客户端线程
    
    Args:
        client_id: 可选的客户端ID，如果不提供则使用随机ID
    """
    global ws_client_thread, ws_client_running
    
    # 检查WebSocket客户端线程是否已在运行
    if ws_client_thread and ws_client_thread.is_alive():
        print("WebSocket客户端已经在运行中")
        return
    
    # 如果没有提供客户端ID，则使用随机ID
    if not client_id:
        client_id = f"agent-{secrets.token_hex(4)}"
    
    # 构建WebSocket服务器URI
    host = settings.TARGET_SERVER_HOST
    port = settings.TARGET_SERVER_PORT
    uri = f"ws://{host}:{port}/ws/"
    
    print(f"启动WebSocket客户端，连接到 {uri}，客户端ID: {client_id}")
    
    # 启动WebSocket客户端线程
    ws_client_running = True
    ws_client_thread = threading.Thread(
        target=lambda: asyncio.run(run_websocket_client_with_test_message(uri, client_id)),
        daemon=True
    )

    ws_client_thread.start()
    
    print("WebSocket客户端线程已启动")

# 修改run_websocket_client函数，添加启动后发送测试消息并接收服务器返回的功能
async def run_websocket_client_with_test_message(uri: str, client_id: str):
    """运行WebSocket客户端并在启动后发送测试消息，然后接收服务器返回
    
    Args:
        uri: WebSocket服务器URI
        client_id: 客户端ID
    """
    from anp_core.client.ws_client import WebSocketClient

    # 创建基础WebSocket客户端实例
    client = WebSocketClient(uri, client_id)
    await client.start()
    await asyncio.sleep(2)
    if client.connected:
        print("发送测试消息...")
        test_message = "这是一条自动发送的测试消息"
        await client.send_message("chat", test_message)
        print(f"测试消息已发送: {test_message}")
        print("等待服务器返回...")
        try:
            await asyncio.sleep(3)
            print("接收完成，如果有消息应该已经显示在上方")
            if hasattr(client, 'last_received_message') and client.last_received_message:
                print(f"最后接收到的消息: {client.last_received_message}")
            else:
                print("未接收到服务器返回消息，可能服务器没有响应或响应延迟")
        except Exception as e:
            print(f"接收服务器返回时出错: {e}")
    else:
        print("WebSocket客户端未连接，无法发送测试消息")
    
    # 等待客户端停止
    while client.running:
        await asyncio.sleep(1)
        
    await client.stop()

def stop_ws_client():
    """停止WebSocket客户端线程"""
    global ws_client_thread, ws_client_running
    if not ws_client_thread or not ws_client_thread.is_alive():
        print("WebSocket客户端未运行")
        return
    
    print("正在关闭WebSocket客户端线程...")
    ws_client_running = False
    # 注意：由于WebSocket客户端有自己的退出机制（通过输入/q或exit），
    # 这里不需要强制终止线程，只需设置标志位
    print("WebSocket客户端将在您输入退出命令后关闭")

if __name__ == "__main__":
    """主函数，处理命令行输入
    
    配置入口： 逐步转移到2
        1. core/config.py  settings
        2. config/dynamic_config.yaml  dynamic_config
    
    """
    set_log_color_level(logging.INFO)
    


    # 解析命令行参数
    parser = argparse.ArgumentParser(description="DID WBA Example with Server capabilities")
    parser.add_argument("--server", action="store_true", help="Run server at startup", default=False)
    parser.add_argument("--port", type=int, help=f"Server port (default: {settings.PORT})", default=settings.PORT)
    parser.add_argument("--ws", action="store_true", help="Run WebSocket client")
    parser.add_argument("--ws-id", type=str, help="WebSocket client ID")
    
    args = parser.parse_args()
    
    if args.port != settings.PORT:
        settings.PORT = args.port

    import os
    os.environ["PORT"] = f"{settings.PORT}"
    
    # 根据命令行参数启动服务
    if args.server:
        agent_service_start()
    
    # 如果指定了WebSocket客户端参数，启动WebSocket客户端
    if args.ws:
        start_ws_client(args.ws_id)
    
    print("DID WBA 示例程序已启动")
    print("输入'help'查看可用命令，输入'exit'退出程序")
    
    # 主循环，处理用户输入
    while True:
        try:
            # 如果聊天线程正在运行，则等待其退出，不处理命令
            if chat_running:
                # 等待聊天线程退出
                while chat_running:
                    time.sleep(0.5)
                if not chat_running:
                    print("聊天线程已退出，恢复命令行控制。")
            command = input("> ").strip().lower()
            if command == "exit":
                print("正在关闭服务...")
                stop_chat()
                agent_service_stop()
                if ws_client_thread and ws_client_thread.is_alive():
                    stop_ws_client()
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
            elif command == "help":
                show_help()
            elif command == "status":
                show_status()
            elif command.startswith("start resp"):
                # 检查是否指定了端口号
                parts = command.split()
                if len(parts) > 2:
                    agent_service_start(parts[2])
                else:
                    agent_service_start()
            elif command.startswith("stop resp"):
                agent_service_stop()
            elif command == "llm":
                start_chat()
                # 阻塞主进程直到 chat_thread 结束，避免输入竞争
                if chat_thread:
                    chat_thread.join()
                print("聊天线程已退出，恢复命令行控制。")
                continue  # 跳过本轮命令输入
            elif command == "stop llm":
                stop_chat()
            elif command.startswith("ws"):
                # 解析可能的客户端ID
                parts = command.split()
                client_id = None
                if len(parts) > 1:
                    client_id = parts[1]
                start_ws_client(client_id)
            elif command == "stop ws":
                stop_ws_client()
            elif command == "didrun":
                # 从 anp_core/anp_users 目录读取所有用户的 agent_cfg.yaml 文件
                # 提取 name 字段，让用户选择，然后加载对应的 did_document.json
                user_list, name_to_dir = get_userdid_list()
                
                if not user_list:
                    print("未找到可用的用户配置")
                    continue
                
                # 显示用户列表供选择
                print("可用的用户:")
                for i, name in enumerate(user_list):
                    print(f"{i+1}. {name}")
                
                # 获取用户选择
                choice = input("请选择用户 (输入序号): ")
                
                # 使用 get_user_did 函数加载 DID 文档
                status, did_dict, selected_name = get_user_did(choice, user_list, name_to_dir)
                
                # 如果加载成功，可以在这里添加更多处理逻辑
                if status and did_dict:
                    print(f"选择了did: {selected_name}:{did_dict}")# 这里可以添加更多处理逻辑
                    pass
            else:
                print(f"未知命令: {command}")
                print("输入'help'查看可用命令")
        except KeyboardInterrupt:
            print("\n检测到退出信号，正在关闭...")
            agent_service_stop()
            if ws_client_thread and ws_client_thread.is_alive():
                stop_ws_client()
            break
        except Exception as e:
            print(f"错误: {e}")
    
    print("程序已退出")
    sys.exit(0)