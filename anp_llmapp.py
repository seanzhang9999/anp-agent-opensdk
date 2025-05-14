"""DID WBA Example with both Client and Server capabilities."""
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

import httpx
from loguru import logger
import uvicorn

from api.anp_nlp_router import (
    resp_handle_request_msgs,
    resp_handle_request_new_msg_event as server_new_message_event,
)
from core.app import create_app
from core.config import settings
from anp_core.auth.did_auth import (
    DIDWbaAuthHeader,
    generate_or_load_did,
    send_authenticated_request,
    send_request_with_token,
)
from anp_core.client.client import (
    ANP_connector_start as core_start_client,
    ANP_connector_stop,
    ANP_req_auth,
    ANP_req_chat,
    client_chat_messages as core_client_chat_messages,
    client_new_message_event as core_client_new_message_event,
    connector_running as core_client_running,
)
from anp_core.server.server import ANP_resp_start, ANP_resp_stop, server_status
from utils.log_base import set_log_color_level

# 全局变量，用于存储最新的聊天消息
client_chat_messages = []
# 事件，用于通知聊天线程有新消息
client_new_message_event = asyncio.Event()

user_dir = os.path.dirname(os.path.abspath(__file__))
user_dir = os.path.join(user_dir, "logs")
# 设置日志
logger.add(f"{user_dir}/anp_llmapp.log", rotation="1000 MB", retention="7 days", encoding="utf-8")

# Create FastAPI application
app = create_app()


@app.get("/", tags=["status"])
async def root():
    """
    Root endpoint for server status check.
    
    Returns:
        dict: Server status information
    """
    return {
        "status": "running",
        "service": "DID WBA Example",
        "version": "0.1.0",
        "mode": "Client and Server",
        "documentation": "/docs"
    }

"""
async def client_example(unique_id: str = None, silent: bool = False, from_chat: bool = False , msg : str = None):
    Run the client example to demonstrate DID WBA authentication.
    
    Args:
        unique_id: Optional unique identifier
        silent: Whether to suppress log output
        from_chat: Whether the call is from chat thread
        msg: Message to send

    if msg is None:
        msg = "ANP客户端的问候，请回复我今天北京的天气"
    try:
        # 1. Generate or load DID document
        if not unique_id:
            unique_id = secrets.token_hex(8)
       
        logging.info(f"Using unique ID: {unique_id}")

        did_document, keys, user_dir = await generate_or_load_did(unique_id)
        os.environ['did-id'] = did_document.get('id')
        did_document_path = Path(user_dir) / settings.DID_DOCUMENT_FILENAME
        private_key_path = Path(user_dir) / settings.PRIVATE_KEY_FILENAME
        
        logging.info(f"DID document path: {did_document_path}")
        logging.info(f"Private key path: {private_key_path}")
        
        # 2. Target server information
        target_host = settings.TARGET_SERVER_HOST
        target_port = settings.TARGET_SERVER_PORT
        base_url = f"http://{target_host}:{target_port}"
        test_url = f"{base_url}/wba/test"
        
        # 3. Create DIDWbaAuthHeader instance
        auth_client = DIDWbaAuthHeader(
            did_document_path=str(did_document_path),
            private_key_path=str(private_key_path)
        )
        
        # 4. Send request with DID WBA authentication
        logging.info(f"Sending authenticated request to {test_url}")
        status, response, token = await send_authenticated_request(test_url, auth_client)
        
        if status != 200:
            logging.error(f"Authentication failed! Status: {status}")
            logging.error(f"Response: {response}")
            return
            
        logging.info(f"Authentication successful! Response: {response}")
        
        # 5. If we received a token, use it for subsequent requests
        if token:
            logging.info("Received access token, trying to use it for next request")
            status, response = await send_request_with_token(test_url, token)
            
            if status == 200:
                logging.info(f"Token authentication successful! Response: {response}")
                # 发送默认消息"我是anp来敲门"到聊天接口
                anp_nlp_url = f"{base_url}/wba/anp-nlp"
                logging.info("发送默认消息到聊天接口")
                try:
                    chat_status, chat_response = await send_request_with_token(
                        anp_nlp_url, 
                        token, 
                        method="POST", 
                        json_data={"message": msg}
                    )
                    if chat_status == 200:
                        logging.info(f"消息发送成功! 回复: {chat_response}")
                        if from_chat:
                            # 如果是从聊天线程调用，发送通知而不是打印
                            await client_notify_chat_thread({
                                "type": "client_example",
                                "user_message": msg,
                                "assistant_message": chat_response.get('answer', '[无回复]'),
                                "status": "success"
                            })
                        elif not silent:
                            print(f"\nanp消息\"{msg}\"成功发送，服务器回复: {chat_response.get('answer', '[无回复]')}")
                    else:
                        logging.error(f"消息发送失败! 状态: {chat_status}")
                        logging.error(f"响应: {chat_response}")
                        if from_chat:
                            await client_notify_chat_thread({
                                "type": "client_example",
                                "status": "error",
                                "message": "消息发送失败"
                            })
                        elif not silent:
                            print("\n消息发送失败，客户端示例完成。")
                except Exception as ce:
                    logging.error(f"发送消息时出错: {ce}")
                    if from_chat:
                        await client_notify_chat_thread({
                            "type": "client_example",
                            "status": "error",
                            "message": f"发送消息时出错: {ce}"
                        })
                    elif not silent:
                        print(f"\n发送消息时出错: {ce}")
                if not from_chat and not silent:
                    print("\n客户端示例完成。")
            else:
                logging.error(f"Token authentication failed! Status: {status}")
                logging.error(f"Response: {response}")
                if from_chat:
                    await client_notify_chat_thread({
                        "type": "client_example",
                        "status": "error",
                        "message": "令牌认证失败"
                    })
                elif not silent:
                    print("\n令牌认证失败，客户端示例完成。")

        else:
            logging.warning("No token received from server")
            
    except Exception as e:
        logging.error(f"Error in client example: {e}")
"""

# 全局变量，用于存储服务器、客户端和聊天线程
server_thread = None
client_thread = None
chat_thread = None
server_running = False
client_running = False
chat_running = False
unique_id = None
server_instance = None  # 存储uvicorn.Server实例

"""
def run_server():
    在子线程中运行uvicorn服务器
    global server_running, server_instance
    try:
        config = uvicorn.Config(
            app,  # 直接使用已创建的FastAPI应用实例
            host=settings.HOST,
            port=settings.PORT,
            reload=settings.DEBUG,
            # 关闭内部信号处理
            use_colors=True,
            log_level="error"
        )
        server_instance = uvicorn.Server(config)
        # 这一行很关键：关闭uvicorn自带的信号处理
        server_instance.install_signal_handlers = lambda: None
        server_running = True
        server_status.set_running(True, port=settings.PORT)  # 同时设置server_status
        server_instance.run()
    except Exception as e:
        logging.error(f"服务器运行出错: {e}")
    finally:
        server_running = False
        server_status.set_running(False)  # 同时设置server_status
"""

async def client_notify_chat_thread(message_data: Dict[str, Any]):
    """
    通知聊天线程有新消息
    
    Args:
        message_data: 消息数据
    """
    global client_chat_messages, client_new_message_event
    
    # 添加消息到全局列表
    client_chat_messages.append(message_data)
    
    # 如果列表太长，保留最近的50条消息
    if len(client_chat_messages) > 50:
        client_chat_messages = client_chat_messages[-50:]
    
    # 设置事件，通知聊天线程
    client_new_message_event.set()
    
    # 在控制台显示通知
    logging.info(f"ANP客户请求: {message_data['user_message']}")
    logging.info(f"ANP对方响应: {message_data['assistant_message']}")
    
    # 打印到控制台，确保在聊天线程中可见
    print(f"\nANP-req从本地发出: {message_data['user_message']}")
    print(f"\nANP-req从@{settings.TARGET_SERVER_PORT}收到:  {message_data['assistant_message']}\n")
    
    # 重置事件，为下一次通知做准备
    client_new_message_event.clear()

"""
def run_client(port=None, unique_id_arg=None, silent=False, from_chat=False , msg = None):
    在子线程中运行客户端示例
    
    Args:
        port: 可选的目标服务器端口号
        unique_id_arg: 可选的唯一ID
        silent: 是否静默模式（不显示日志）
        from_chat: 是否从聊天线程调用
        msg: 要发送的消息
    
    global client_running
    try:
        # 等待2秒确保服务器已启动
        time.sleep(2)
        # 在新线程中创建事件循环运行客户端示例
        client_running = True
        
        # 如果是静默模式，临时禁用日志输出
        original_log_level = None
        if silent:
            original_log_level = logging.getLogger().level
            logging.getLogger().setLevel(logging.ERROR)  # 只显示错误日志
        # 如果提供了端口号，临时修改目标服务器端口设置
        original_port = None
        if port is not None:
            try:
                port_num = int(port)
                original_port = settings.TARGET_SERVER_PORT
                settings.TARGET_SERVER_PORT = port_num
                if not silent:
                    logging.info(f"使用自定义目标服务器端口: {port_num}")
            except ValueError:
                if not silent:
                    logging.error(f"无效的端口号: {port}，使用默认端口: {settings.TARGET_SERVER_PORT}")
        
        # 运行客户端示例
        asyncio.run(client_example(unique_id_arg, silent, from_chat , msg))
        
        # 恢复原始端口设置
        if original_port is not None:
            settings.TARGET_SERVER_PORT = original_port
            
        # 恢复原始日志级别
        if silent and original_log_level is not None:
            logging.getLogger().setLevel(original_log_level)
    except Exception as e:
        logging.error(f"客户端运行出错: {e}")
    finally:
        client_running = False

"""

def resp_start(port=None):
    """启动服务器线程
    
    Args:
        port: 可选的服务器端口号，如果提供则会覆盖默认端口
    """
    # 如果提供了端口号，则临时修改设置中的端口
    if port is not None:
        try:
            port_num = int(port)
            settings.PORT = port_num
            logger.info(f"Use a custom port: {port_num}")
        except ValueError:
            logger.error(f"Error prot : {port}，use default port: {settings.PORT}")
    
    # 调用did_core中的start_server函数
    return ANP_resp_start(port=port)


def resp_stop():
    """停止服务器线程"""
    # 调用did_core中的stop_server函数
    return ANP_resp_stop()

"""
def start_anp_request(port=None, unique_id_arg=None, silent=False, from_chat=False, msg=None):
    启动客户端线程
    
    Args:
        port: 可选的目标服务器端口号
        unique_id_arg: 可选的唯一ID
        silent: 是否静默模式（不显示日志）
        from_chat: 是否从聊天线程调用
        msg: 要发送的消息

    global unique_id
    
    if unique_id_arg:
        unique_id = unique_id_arg
    
    
    return ANP_req_auth(unique_id=unique_id_arg, silent=silent, from_chat=from_chat, msg=msg)
    # return core_start_client(port=port, unique_id=unique_id_arg, message=msg)
"""

"""
def stop_client():
    停止客户端线程
    # 调用did_core中的stop_client函数
    return core_stop_client()
"""

def chat_to_ANP(custom_msg, token=None, unique_id_arg=None):
    """发送消息到目标服务器（非阻塞方式）
    
    Args:
        custom_msg: 要发送的消息
        token: 认证令牌，如果为None则会启动客户端认证获取token
        unique_id_arg: 可选的唯一ID，用于客户端认证
    """
    # 使用线程模式运行，避免事件循环问题
    thread = threading.Thread(
        target=_chat_to_ANP_thread,
        args=(custom_msg, token, unique_id_arg),
        daemon=True
    )
    thread.start()
    return True

def _chat_to_ANP_thread(custom_msg, token=None, unique_id_arg=None):
    """在线程中运行异步函数的同步包装器"""
    # 创建新的事件循环
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        # 运行异步函数
        loop.run_until_complete(_chat_to_ANP_impl(custom_msg, token, unique_id_arg))
    except Exception as e:
        logging.error(f"线程中运行_chat_to_ANP_impl时出错: {e}")
        print(f"发送消息时出错: {e}")
    finally:
        # 关闭事件循环
        loop.close()
async def _chat_to_ANP_impl(custom_msg, token=None, unique_id_arg=None):
    """发送消息的实际实现（内部函数）
    """
    try:
        target_host = settings.TARGET_SERVER_HOST
        target_port = settings.TARGET_SERVER_PORT
        if os.environ.get('target-port'):
            target_port = os.environ.get('target-port')
        if os.environ.get('target-host'):
            target_host = os.environ.get('target-host')

        base_url = f"http://{target_host}:{target_port}"
        
        if not token:
            print(f"无token，正在启动客户端认证获取token...\n并发送消息: {custom_msg}")
            await ANP_req_auth(unique_id=unique_id_arg, msg=custom_msg)
            token = os.environ.get('did-token', None)
            
        print(f"使用token...\n发送消息: {custom_msg}")
        # 调用did_core中的send_message_to_chat函数
        status, response = await ANP_req_chat(base_url=base_url, silent=True, from_chat=True, msg=custom_msg, token=token)
        
        # 通知聊天线程有新消息
        if status:
            await client_notify_chat_thread({
                "type": "anp_nlp",  # 确保类型与run_chat中的处理逻辑匹配
                "user_message": custom_msg,
                "assistant_message": response.get('answer', '[无回复]') if isinstance(response, dict) else str(response),
                "status": "success"
            })
        else:
            await client_notify_chat_thread({
                "type": "anp_nlp",
                "status": "error",
                "message": f"发送消息失败: {response}"
            })
    except Exception as e:
        logging.error(f"发送消息时出错: {e}")
        print(f"发送消息时出错: {e}")
        # 通知聊天线程出错
        try:
            await client_notify_chat_thread({
                "type": "anp_nlp",
                "status": "error",
                "message": f"发送消息时出错: {e}"
            })
        except Exception:
            pass


async def run_chat():
    """运行LLM聊天线程 - 直接调用OpenRouter API"""
    global chat_running, original_log_level 

    try:
        # 导入ANP-NLP路由器中的事件和消息
        from api.anp_nlp_router import resp_handle_request_new_msg_event, resp_handle_request_msgs, notify_chat_thread
        
        # 检查OpenRouter API密钥是否配置
        openrouter_api_key = os.getenv("OPENROUTER_API_KEY", "")
        if not openrouter_api_key:
            print("[错误] 未配置OpenRouter API密钥，请在环境变量中设置OPENROUTER_API_KEY")
            chat_running = False
            return
            
        # OpenRouter API配置
        openrouter_api_url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {openrouter_api_key}",
            "Content-Type": "application/json"
        }
        
        print("\n已启动LLM聊天线程。输入消息与AI对话，输入 /q 退出。")
        print("特殊命令: 输入 @[agent-name] [msg]")
        logging.info("聊天线程启动 - 直接调用OpenRouter API")
        
        # 进入聊天模式
        async with httpx.AsyncClient(timeout=30) as client:
            chat_running = True
            while chat_running:
                user_msg = input("你: ").strip()
                
                if user_msg.lower() == "/q":
                    print("退出聊天线程。\n")
                    break
                
                # 处理特殊命令 @anp-bot
                if user_msg.strip().startswith("@") and user_msg.strip().find(" ") :
                    parts = user_msg.strip().split(" ", 1)
                    agentname = parts[0].strip().split("@", 1)
                    agentname = agentname[1]
                    bookmark_config_dir = os.path.dirname(os.path.abspath(__file__))
                    bookmark_config_dir = os.path.join(bookmark_config_dir, "anp_core", "anp_bookmark")
                    os.makedirs(bookmark_config_dir, exist_ok=True)
                    bookmark_config_file = os.path.join(bookmark_config_dir, f"{agentname}.js")
                    if os.path.exists(bookmark_config_file):
                    # 读取已有的配置文件
                        print(f"找到智能体书签文件: {bookmark_config_file}")
                        with open(bookmark_config_file, 'r', encoding='utf-8') as f:
                            config_data = json.loads(f.read())
                            agentname = config_data.get('name')
                            did = config_data.get('did')
                            url = config_data.get('url')
                            port = config_data.get('port')
                        print(f"使用{agentname}智能体DID: {did}地址：{url}端口：{port}通讯")
                        os.environ['target-port'] = f"{port}"
                        custom_msg = "ANPbot的问候，请二十字内回复我"
                        if len(parts) > 1 and parts[1].strip():
                            custom_msg = parts[1].strip()
                        print(f"将向智能体{port}发送消息: {custom_msg}")
                        chat_running = False
                        os.environ['target-port'] = f"{port}"
                        os.environ['target-host'] = f"{url}"
                        # 获取token，如果环境变量中不存在则使用None
                        token = os.environ.get('did-token', None)
                        # 调用send_msg函数发送消息（非阻塞方式）
                        chat_to_ANP(custom_msg, token, unique_id)
                        
                        print("\n客户端执行中，你可以先聊。")
                        chat_running = True
                    else:
                        print(f"您要交流的智能体{agentname}不存在，请通过智能体搜索寻找合适的智能体")# 生成或加载智能体的DID
                    continue
                    
                try:
                    # 准备请求数据
                    payload = {
                        "model": "deepseek/deepseek-chat-v3-0324:free",  # 免费模型
                        "messages": [{"role": "user", "content": user_msg}],
                        "max_tokens": 512
                    }
                    
                    # 发送请求到OpenRouter API
                    resp = await client.post(
                        openrouter_api_url,
                        headers=headers,
                        json=payload
                    )
                    
                    if resp.status_code == 200:
                        data = resp.json()
                        answer = data['choices'][0]['message']['content']
                        print(f"助手: {answer}")
                    else:
                        print(f"[错误] OpenRouter API返回: {resp.status_code} {resp.text}")
                except Exception as ce:

                    print(f"白嫖的OpenRouter生气了: {ce}")
                    if not chat_running:  # 如果线程被外部终止
                        break
                
                # 检查是否有来自ANP-NLP API或client_example的新消息
                try:
                    # 创建两个等待事件的任务
                    server_wait = asyncio.create_task(asyncio.wait_for(resp_handle_request_new_msg_event.wait(), 0.1))
                    client_wait = asyncio.create_task(asyncio.wait_for(client_new_message_event.wait(), 0.1))
                    
                    # 等待任意一个任务完成
                    done, pending = await asyncio.wait(
                        [server_wait, client_wait],
                        return_when=asyncio.FIRST_COMPLETED,
                        timeout=0.1
                    )
                    
                    # 取消未完成的任务
                    for task in pending:
                        task.cancel()
                    
                    # 处理服务器端消息
                    if server_wait in done and resp_handle_request_new_msg_event.is_set():
                        # 重置事件
                        resp_handle_request_new_msg_event.clear()
                        
                        # 获取最新消息
                        if resp_handle_request_msgs:
                            latest_message = resp_handle_request_msgs[-1]
                            
                            # 根据消息类型显示不同内容
                            if latest_message.get("type") == "client_example":
                                # 处理来自client_example的消息
                                status = latest_message.get("status")
                                if status == "success":
                                    user_msg = latest_message.get("user_message", "")
                                    assistant_msg = latest_message.get("assistant_message", "")
                                    print(f"\n[服务器] 消息\"{user_msg}\"发送成功，服务器回复: {assistant_msg}")
                                else:
                                    error_msg = latest_message.get("message", "未知错误")
                                    print(f"\n[服务器] 错误: {error_msg}")
                    
                    # 处理客户端消息
                    if client_wait in done and client_new_message_event.is_set():
                        # 重置事件
                        client_new_message_event.clear()
                        
                        # 获取最新消息
                        if client_chat_messages:
                            latest_message = client_chat_messages[-1]
                            
                            # 根据消息类型显示不同内容
                            if latest_message.get("type") == "anp_nlp":
                                # 处理来自ANP_req_chat的消息
                                status = latest_message.get("status")
                                if status == "success":
                                    user_msg = latest_message.get("user_message", "")
                                    assistant_msg = latest_message.get("assistant_message", "")
                                    print(f"\n[客户端] 消息\"{user_msg}\"发送成功，服务器回复: {assistant_msg}")
                                else:
                                    error_msg = latest_message.get("message", "未知错误")
                                    print(f"\n[客户端] 错误: {error_msg}")
                    
                except asyncio.TimeoutError:
                    # 超时，继续下一次循环
                    pass
                except Exception as e:
                    logging.error(f"处理消息通知时出错: {e}")
                    pass
    except Exception as e:
        logging.error(f"聊天线程出错: {e}")
    finally:
        chat_running = False


def start_chat():
    """启动LLM聊天线程 - 直接调用OpenRouter API，同时自动启动服务器"""
    global chat_thread, chat_running, server_thread, server_running
    
    # 检查聊天线程是否已在运行
    if chat_thread and chat_thread.is_alive():
        print("聊天线程已经在运行中")
        return
    
    # 检查服务器是否已在运行，如果没有则自动启动（静默模式）
    if not server_thread or not server_thread.is_alive():
        # 启动服务器线程（不打印日志信息）
        original_log_level = logging.getLogger().level
        logging.getLogger().setLevel(logging.ERROR)  # 只显示错误日志
        
        server_thread = threading.Thread(target=resp_start, daemon=True)
        server_thread.start()
        
        # 等待服务器启动
        time.sleep(1)
        
    
    # 启动聊天线程
    chat_thread = threading.Thread(target=lambda: asyncio.run(run_chat()), daemon=True)
    chat_thread.start()
    print("LLM聊天线程已启动")


def stop_chat():
    """停止LLM聊天线程，同时处理自动启动的服务器线程"""
    global chat_thread, chat_running, server_thread, server_running, server_instance
    if not chat_thread or not chat_thread.is_alive():
        print("聊天线程未运行")
        return
    
    print("正在关闭聊天线程...")
    chat_running = False
    chat_thread.join(timeout=5)
    if chat_thread.is_alive():
        print("聊天线程关闭超时，可能需要重启程序")
    else:
        print("聊天线程已关闭")
        chat_thread = None
    
        
    # 如果服务器是由聊天线程自动启动的，也需要关闭服务器
    # 这里不自动关闭服务器，因为可能有其他功能仍在使用服务器
    # 如果需要关闭服务器，用户可以手动调用stop_server()函数


def show_status():
    """显示当前服务器、客户端和聊天状态"""
    server_status = "运行中" if server_thread and server_thread.is_alive() else "已停止"
    client_status = "运行中" if client_thread and client_thread.is_alive() else "已停止"
    chat_status = "运行中" if chat_thread and chat_thread.is_alive() else "已停止"
    
    print(f"监听状态: {server_status}")
    print(f"请求状态: {client_status}")
    print(f"聊天状态: {chat_status}")
    if unique_id:
        print(f"当前客户端ID: {unique_id}")


def show_help():
    """显示帮助信息"""
    print("可用命令:")
    print("  start resp [port] - 启动anp服务器，可选指定端口号")
    print("  stop resp - 停止anp服务器")
    print("  start req [msg] [port] [unique_id] - 启动anp请求，可选指定目标服务器端口和唯一ID")
    print("  stop req - 停止anp请求")
    print("  start llm - 启动LLM聊天线程")
    print("  stop llm - 停止LLM聊天线程")
    print("  status - 显示服务器、客户端和聊天状态")
    print("  help - 显示此帮助信息")
    print("  test - 测试anp")
    print("  exit - 退出程序")


def anp_test():
    """测试函数，用于顺序测试服务器启动、消息发送和服务器停止
    
    按顺序执行以下操作并打印日志：
    1. resp_start - 启动服务器
    2. chat_to_ANP - 发送消息
    3. resp_stop - 停止服务器
    """
    import time
    import logging
    
    # 设置日志级别
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    
    try:
        # 1. 启动服务器
        logger.info("===== 步骤1: 启动服务器 =====")
        server_result = resp_start()
        logger.info(f"服务器启动结果: {server_result}")
        logger.info("等待服务器完全启动...")
        time.sleep(3)  # 等待服务器完全启动
        
        # 2. 发送消息
        logger.info("\n===== 步骤2: 发送消息 =====")
        test_message = "这是一条测试消息，请回复"  
        logger.info(f"发送消息: {test_message}")
        # 获取token，如果环境变量中不存在则使用None
        token = os.environ.get('did-token', None)
        chat_result = chat_to_ANP(test_message, token)
        logger.info(f"消息发送结果: {chat_result}")
        logger.info("等待消息处理...")
        time.sleep(5)  # 等待消息处理
        
        # 3. 停止服务器
        logger.info("\n===== 步骤3: 停止服务器 =====")
        stop_result = resp_stop()
        logger.info(f"服务器停止结果: {stop_result}")
        
        logger.info("\n===== 测试完成 =====")
        
    except Exception as e:
        logger.error(f"测试过程中出错: {e}")
        import traceback
        logger.error(traceback.format_exc())


def main():
    """主函数，处理命令行输入"""
    global unique_id


    
    set_log_color_level(logging.INFO)
    
    # 解析命令行参数
    parser = argparse.ArgumentParser(description="DID WBA Example with Client and Server capabilities")
    parser.add_argument("--client", action="store_true", help="Run client example at startup")
    parser.add_argument("--server", action="store_true", help="Run server at startup", default=False)
    parser.add_argument("--unique-id", type=str, help="Unique ID for client example", default=None)
    parser.add_argument("--port", type=int, help=f"Server port (default: {settings.PORT})", default=settings.PORT)
    parser.add_argument("--target-port", type=int, help=f"Target server port for client (default: {settings.TARGET_SERVER_PORT})", default=None)
    
    args =parser.parse_args()
    
    
    if args.target_port:
        settings.TARGET_SERVER_PORT = args.target_port
    
    if args.port != settings.PORT:
        settings.PORT = args.port

    import os
    os.environ["PORT"] = f"{settings.PORT}"
    
    if args.unique_id:
        unique_id = args.unique_id
    
    # 根据命令行参数启动服务
    if args.server:
        resp_start()
    
    if args.client:
        start_anp_request(args.target_port, args.unique_id, silent=False)
    
    print("DID WBA 示例程序已启动")
    print("输入'help'查看可用命令，输入'exit'退出程序")
    
    # 主循环，处理用户输入
    while True:
        try:
            # 如果客户端或聊天线程正在运行，则等待其退出，不处理命令
            if client_running or chat_running:
                # 等待客户端或聊天线程退出
                while client_running or chat_running:
                    time.sleep(0.5)
                if not client_running and not chat_running:
                    print("客户端或聊天线程已退出，恢复命令行控制。")
            command = input("> ").strip().lower()
            
            if command == "exit":
                print("正在关闭服务...")
                stop_chat()
                ANP_connector_stop()
                resp_stop()
                break
            elif command == "test":
                anp_test()
            elif command == "help":
                show_help()
            elif command == "status":
                show_status()
            elif command.startswith("start resp"):
                # 检查是否指定了端口号
                parts = command.split()
                if len(parts) > 2:
                    resp_start(parts[2])
                else:
                    resp_start()
            elif command.startswith("stop resp"):
                resp_stop()
            elif command.startswith("stop req"):
                ANP_connector_stop()
            elif command.startswith("start req"):
                # 检查是否指定了port和unique_id
                parts = command.split()
                if len(parts) > 4:
                    #
                    chat_to_ANP(parts[2],parts[3], parts[4])
                elif len(parts) > 3:
                    # 只指定了port
                    chat_to_ANP(parts[2],parts[3])
                elif len(parts) > 2:
                    # 只指定了port
                    chat_to_ANP(parts[2])
                else:
                    # 没有指定参数
                    chat_to_ANP("这是一条测试消息，请回复")
                # 阻塞主进程直到 client_thread 结束，避免输入竞争
                if client_thread:
                    client_thread.join()
                print("客户端已退出，恢复命令行控制。")
                continue  # 跳过本轮命令输入
            elif command == "start llm":
                start_chat()
                # 阻塞主进程直到 chat_thread 结束，避免输入竞争
                if chat_thread:
                    chat_thread.join()
                print("聊天线程已退出，恢复命令行控制。")
                continue  # 跳过本轮命令输入
            elif command == "stop llm":
                stop_chat()
            else:
                print(f"未知命令: {command}")
                print("输入'help'查看可用命令")
                
        except KeyboardInterrupt:
            print("\n检测到退出信号，正在关闭...")
            ANP_connector_stop()
            resp_stop()
            break
        except Exception as e:
            print(f"错误: {e}")
    
    print("程序已退出")
    sys.exit(0)


if __name__ == "__main__":
    main()