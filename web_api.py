"""DID WBA Web API - 为Web界面提供API接口"""

# Python 标准库
import asyncio
import json
import logging
import os
import re
import secrets
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from urllib.parse import urlparse

# 第三方库
import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from openai import AsyncAzureOpenAI
from pydantic import BaseModel

# 本地模块
from core.config import settings
from web_anp_llmapp import (
    resp_start, resp_stop,
    start_chat, stop_chat,
    chat_to_ANP,
    server_thread, chat_thread,
    server_running, chat_running,
    client_chat_messages, client_new_message_event
)
from anp_core.auth.did_auth import (
    generate_or_load_did, 
    send_authenticated_request,
    send_request_with_token,
    DIDWbaAuthHeader
)

async def llm_recommand_handler(message: str):
    """
    大模型处理函数，处理推荐
    """
    OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
    OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
    
    if not OPENROUTER_API_KEY:
        error_msg = "OpenRouter API key未配置，请在环境变量中设置OPENROUTER_API_KEY"
        return error_msg
    
    # 预处理消息，确保格式正确并避免内容被认为不合适
    formatted_messages = [
        {"role": "system", "content": "你是一个智能助手，请根据用户的需求推荐最合适的智能体，并在回复的最后使用@智能体名称的格式标注推荐结果。"}, 
        {"role": "user", "content": message}
    ]
    
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "deepseek/deepseek-chat-v3-0324:free",
        "messages": formatted_messages,
        "max_tokens": 2048
    }
    
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(OPENROUTER_API_URL, headers=headers, json=payload)
            if resp.status_code != 200:
                error_msg = f"API请求失败: {resp.status_code} - {resp.text}"
                return error_msg
            
            response_data = resp.json()
            assistant_message = response_data["choices"][0]["message"]["content"]
            if isinstance(assistant_message, bytes):
                assistant_message = assistant_message.decode('utf-8')
            return assistant_message
    except Exception as e:
        error_msg = f"处理请求时出错: {str(e)}"
        return error_msg

# 添加大模型处理函数
async def llm_handler(message: str, chat_history: List[Dict[str, Any]]):
    """
    大模型处理函数，基于聊天历史和当前消息生成回复
    """
    OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
    OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
    
    if not OPENROUTER_API_KEY:
        error_msg = "OpenRouter API key未配置，请在环境变量中设置OPENROUTER_API_KEY"
        return error_msg
    
    # 构建消息历史
    messages = [
        {"role": "system", "content": "你是一个智能助手，请根据用户的提问进行专业、简洁的回复。"}
    ]
    
    # 添加聊天历史
    for item in chat_history:
        if item["type"] == "user":
            messages.append({"role": "user", "content": item["message"]})
        elif item["type"] == "assistant" and not item.get("from_agent", False):
            messages.append({"role": "assistant", "content": item["message"]})
    
    # 确保最后一条消息是当前用户消息
    if not messages[-1]["role"] == "user" or not messages[-1]["content"] == message:
        messages.append({"role": "user", "content": message})
    
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "deepseek/deepseek-chat-v3-0324:free",
        "messages": messages,
        "max_tokens": 512
    }
    
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(OPENROUTER_API_URL, headers=headers, json=payload)
            if resp.status_code != 200:
                error_msg = f"API请求失败: {resp.status_code} - {resp.text}"
                return error_msg
            
            response_data = resp.json()
            assistant_message = response_data["choices"][0]["message"]["content"]
            return assistant_message
    except Exception as e:
        error_msg = f"处理请求时出错: {str(e)}"
        return error_msg



# 创建FastAPI应用
app = FastAPI(title="DID WBA Web API", description="为DID WBA Web界面提供API接口")

# 添加CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)



# 挂载静态文件目录
app.mount("/static", StaticFiles(directory="static/chat"), name="static")
# 挂载WebSocket客户端静态文件
app.mount("/ws-client", StaticFiles(directory="static"), name="ws-client")

# 定义请求和响应模型
class MessageRequest(BaseModel):
    message: str
    isAgentCommand: bool = False
    isRecommendation: bool = False
    agentInfo: Optional[Dict[str, Any]] = None

class BookmarkRequest(BaseModel):
    name: str

class Bookmark(BaseModel):
    id: str
    name: str
    did: Optional[str] = None
    url: Optional[str] = None
    port: Optional[str] = None
    discovery: Optional[str] = None


# 定义探索智能体请求模型
class DiscoverAgentRequest(BaseModel):
    bookmark_id: str
    url: str
    port: str

# 存储智能体书签
bookmarks: List[Bookmark] = []

# 存储聊天历史
chat_history: List[Dict[str, Any]] = []

# 上次检查智能体消息的时间
last_agent_check_time = 0

# 在send_message函数中添加对isRecommendation的处理
@app.post("/api/chat/send")
async def send_message(request: MessageRequest):
    global chat_running, chat_history
    try:
        # 从anp_llmapp_web模块获取最新的聊天状态
        from web_anp_llmapp import chat_running as current_chat_running
        chat_running = current_chat_running
        
        if not chat_running:
            return {"success": False, "message": "请先启动聊天"}
        
        message = request.message
        
        # 添加用户消息到聊天历史
        chat_history.append({
            "type": "user",
            "message": message,
            "timestamp": time.time()
        })
        
        # 如果是智能体推荐请求
        if request.isRecommendation:
            try:
                # 直接调用大模型处理推荐请求
                response = await llm_recommand_handler(message)
                
                # 添加助手回复到聊天历史
                chat_history.append({
                    "type": "assistant",
                    "message": response,
                    "timestamp": time.time()
                })
                
                # 保存聊天历史
                save_chat_history()
                
                return {"success": True, "response": response}
            except Exception as e:
                logging.error(f"智能体推荐处理出错: {e}")
                fallback_response = f"抱歉，无法完成推荐: {str(e)}"
                return {"success": False, "message": fallback_response}
        # 如果是智能体命令
        elif request.isAgentCommand:
            parts = message.strip().split(" ", 1)
            agentname = parts[0].strip().split("@", 1)
            agentname = agentname[1]
            
            # 默认消息
            custom_msg = "ANPbot的问候，请二十字内回复我"
            if len(parts) > 1 and parts[1].strip():
                custom_msg = parts[1].strip()
            
            # 优先使用前端传递的智能体信息
            if request.agentInfo:
                agent_info = request.agentInfo
                agentname = agent_info.get('name')
                did = agent_info.get('did')
                url = agent_info.get('url')
                port = agent_info.get('port')
                
                # 确保port是字符串类型
                if port is not None:
                    port = str(port)
                    
                print(f"使用前端传递的智能体信息 - 名称:{agentname} DID:{did} 地址:{url} 端口:{port}")
                
                # 设置环境变量
                if port:
                    os.environ['target-port'] = port
                if url:
                    os.environ['target-host'] = url
                    
                # 获取token，如果环境变量中不存在则使用None
                token = os.environ.get('did-token', None)
                
                # 发送到ANP服务器
                print(f"将向智能体发送消息: {custom_msg}")
                chat_running = False
                unique_id = os.environ.get('unique_id')

                chat_to_ANP(custom_msg, token=token, unique_id_arg = unique_id)
                
                # 添加系统消息到聊天历史
                chat_history.append({
                    "type": "system",
                    "message": "已发送到智能体，请等待回复（可能需要刷新页面查看）",
                    "timestamp": time.time()
                })
                
                # 保存聊天历史
                save_chat_history()
                
                return {"success": True, "response": "已发送到智能体，请等待回复（可能需要刷新页面查看）"}
            else:
                # 从本地文件读取智能体信息（兼容旧版本）
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
                        # 确保port是字符串类型
                        if port is not None:
                            port = str(port)
                    print(f"使用{agentname}智能体DID: {did}地址：{url}端口：{port}通讯")
                    
                    # 设置环境变量
                    if port:
                        os.environ['target-port'] = port
                    if url:
                        os.environ['target-host'] = url
                        
                    # 获取token，如果环境变量中不存在则使用None
                    token = os.environ.get('did-token', None)
                    
                    # 发送到ANP服务器
                    print(f"将向智能体发送消息: {custom_msg}")
                    chat_running = False

                    unique_id = os.environ.get('unique_id')
                    
                    chat_to_ANP(custom_msg, token=token, unique_id_arg = unique_id)
                    
                    # 添加系统消息到聊天历史
                    chat_history.append({
                        "type": "system",
                        "message": "已发送到智能体，请等待回复（可能需要刷新页面查看）",
                        "timestamp": time.time()
                    })
                    
                    # 保存聊天历史
                    save_chat_history()
                    
                    return {"success": True, "response": "已发送到智能体，请等待回复（可能需要刷新页面查看）"}
                else:
                    # 书签文件不存在
                    error_msg = f"找不到智能体书签文件: {agentname}"
                    print(error_msg)
                    
                    # 添加错误消息到聊天历史
                    chat_history.append({
                        "type": "system",
                        "message": error_msg,
                        "timestamp": time.time()
                    })
                    
                    # 保存聊天历史
                    save_chat_history()
                    
                    return {"success": False, "message": error_msg}
        else:
            # 普通消息，使用大模型处理
            try:
                # 调用大模型处理函数
                response = await llm_handler(message, chat_history)
                
                response = "localAI：" + response
                # 添加助手回复到聊天历史
                chat_history.append({
                    "type": "assistant",
                    "message": response,
                    "timestamp": time.time()
                })
                
                # 保存聊天历史
                save_chat_history()
                
                return {"success": True, "response": response}
            except Exception as e:
                logging.error(f"大模型处理出错: {e}")
                # 如果大模型处理失败，返回简单回复
                fallback_response = f"抱歉，处理您的消息时出现了问题: {str(e)}"
                
                # 添加助手回复到聊天历史
                chat_history.append({
                    "type": "assistant",
                    "message": fallback_response,
                    "timestamp": time.time()
                })
                
                # 保存聊天历史
                save_chat_history()
                
                return {"success": True, "response": fallback_response}
    except Exception as e:
        logging.error(f"发送消息出错: {e}")
        return {"success": False, "message": str(e)}

# 保存聊天历史到文件
def save_chat_history():
    try:
        history_file = Path(__file__).parent / "chat_history.json"
        with open(history_file, "w", encoding="utf-8") as f:
            json.dump(chat_history, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logging.error(f"保存聊天历史出错: {e}")

# 加载聊天历史
def load_chat_history():
    global chat_history
    try:
        history_file = Path(__file__).parent / "chat_history.json"
        if history_file.exists():
            with open(history_file, "r", encoding="utf-8") as f:
                chat_history = json.load(f)
    except Exception as e:
        logging.error(f"加载聊天历史出错: {e}")
        chat_history = []

# 根路径 - 返回静态HTML页面
@app.get("/")
async def read_root():
    return FileResponse("static/chat/index.html")

# 检查是否有新的智能体消息
def check_agent_messages():
    global chat_history, last_agent_check_time
    try:
        # 从web_anp_llmapp模块获取最新的客户端消息
        from web_anp_llmapp import client_chat_messages
        
        # 如果没有新消息，直接返回
        if not client_chat_messages:
            return
        
        # 添加消息处理计数器，防止死循环
        processed_count = 0
        max_process_count = 50  # 设置最大处理消息数量
        
        # 直接遍历所有智能体消息，避免仅依赖时间戳
        for msg in client_chat_messages:
            # 限制单次处理的消息数量
            if processed_count >= max_process_count:
                logging.warning(f"单次处理消息数量已达上限 {max_process_count}，跳过剩余消息")
                break
                
            processed_count += 1
            # 只处理assistant类型且from_agent为True的消息，或anp_nlp类型的远程智能体消息
            if (msg.get('type') == 'assistant' and msg.get('from_agent', False)):
                # 检查这条消息是否已经在聊天历史中
                if not any(h.get('timestamp') == msg.get('timestamp') and h.get('message') == msg.get('content', '') for h in chat_history):
                    # 直接写入聊天历史
                    chat_history.append({
                        "type": msg.get('type', 'assistant'),
                        "message": msg.get('content', ''),
                        "timestamp": msg.get('timestamp'),
                        "from_agent": msg.get('from_agent', False)
                    })
                    logging.info(f"添加智能体消息到聊天历史: {msg.get('content', '')}")
            elif msg.get('type') == 'anp_nlp':
                # 为anp_nlp类型消息添加时间戳（如果不存在）
                if not msg.get('timestamp'):
                    msg['timestamp'] = time.time()
                
                # 使用assistant_message作为消息内容
                message_content = msg.get('assistant_message', '[无回复]')
                
                # 生成唯一标识用于检查消息是否已存在
                msg_id = f"{msg.get('type')}-{msg.get('user_message')}-{message_content}"
                
                # 检查这条消息是否已经在聊天历史中
                if not any(h.get('message') == message_content and h.get('type') == 'anp_nlp' for h in chat_history):
                    # 直接写入聊天历史
                    chat_history.append({
                        "type": 'anp_nlp',
                        "message": message_content,
                        "timestamp": msg.get('timestamp'),
                        "from_agent": True
                    })
                    logging.info(f"添加anp_nlp消息到聊天历史: {message_content[:50]}...")
            else:
                # 非 assistant 或 anp_nlp 类型消息可根据需要处理或跳过，这里简单跳过
                continue
        # 更新时间为当前时间
        last_agent_check_time = time.time()
        # 保存聊天历史
        save_chat_history()
    except Exception as e:
        logging.error(f"检查智能体消息出错: {e}")

# 获取聊天历史
@app.get("/api/chat/history")
async def get_chat_history():
   return {"success": True, "history": chat_history}

# 清除聊天历史
@app.post("/api/chat/clear-history")
async def clear_chat_history():
    global chat_history
    chat_history = []
    save_chat_history()
    return {"success": True}

# 服务器API
@app.get("/api/server/status")
async def get_server_status():
    # 直接从anp_core.server.server模块获取最新的服务器状态
    from anp_core.server.server import server_status
    # 更新全局变量以保持一致
    global server_running
    # 确保server_running反映实际的服务器状态
    server_running = server_status.is_running()
    
    # 如果服务器正在运行，返回DID信息
    if server_running:
        did_id = os.environ.get('did-id', '')
        # 尝试获取DID文档路径
        unique_id = os.environ.get('unique-id', '')
        if unique_id:
            user_dir = Path(settings.DID_KEYS_DIR) / f"user_{unique_id}"
            did_document_path = user_dir / settings.DID_DOCUMENT_FILENAME
            return {
                "running": server_running,
                "did_id": did_id,
                "did_document_path": str(did_document_path) if did_document_path.exists() else ''
            }
    
    # 如果服务器未运行或无法获取DID信息，只返回运行状态
    # 确保返回的running状态为False
    return {"running": False}

@app.post("/api/server/start")
async def start_server():
    global server_running
    try:
        if not server_running:
            # demo期间每次生成新的did
            unique_id = secrets.token_hex(8)
            
            os.environ['unique-id'] = unique_id
            logging.info(f"使用唯一ID: {unique_id}")
            
            did_document, keys, user_dir = await generate_or_load_did(unique_id)
            os.environ['did-id'] = did_document.get('id')
            did_document_path = Path(user_dir) / settings.DID_DOCUMENT_FILENAME
            private_key_path = Path(user_dir) / settings.PRIVATE_KEY_FILENAME
            
            logging.info(f"DID文档路径: {did_document_path}")
            logging.info(f"私钥路径: {private_key_path}")
            result = resp_start()
            if result:
                # 直接从anp_core.server.server模块获取最新的服务器状态
                from anp_core.server.server import server_status
                server_running = server_status.is_running()
                # 返回DID信息和文档路径
                return {
                    "success": True,
                    "did_id": did_document.get('id'),
                    "did_document_path": str(did_document_path)
                }
            else:
                return {"success": False, "message": "服务器启动失败"}
        return {"success": True, "message": "服务器已经在运行"}
    except Exception as e:
        logging.error(f"启动服务器出错: {e}")
        return {"success": False, "message": str(e)}

@app.get("/api/status")
async def get_status():
    # 添加一个统一的状态API端点
    from anp_core.server.server import server_status
    # 更新全局变量以保持一致
    global server_running
    server_running = server_status.is_running()
    return {"server": server_running, "chat": chat_running}

@app.post("/api/server/stop")
async def stop_server():
    global server_running
    try:
        if server_running:
            # 如果聊天在运行，先停止聊天
            if chat_running:
                stop_chat()
            
            result = resp_stop()
            if result:
                return {"success": True}
            else:
                return {"success": False, "message": "服务器停止失败"}
        return {"success": True, "message": "服务器已经停止"}
    except Exception as e:
        logging.error(f"停止服务器出错: {e}")
        return {"success": False, "message": str(e)}

# 聊天API
@app.get("/api/chat/status")
async def get_chat_status():
    # 从anp_llmapp_web模块获取最新的聊天状态
    global chat_running
    from web_anp_llmapp import chat_running as current_chat_running
    chat_running = current_chat_running
    return {"running": chat_running}

@app.post("/api/chat/start")
async def start_chat_api():
    global chat_running, server_running
    try:
        # 先从server_status获取最新的服务器状态
        from anp_core.server.server import server_status
        server_running = server_status.is_running()
        
        # 添加日志以便调试
        logging.info(f"服务器状态检查: {server_running}")
        
        if not server_running:
            # 再次尝试获取服务器状态
            from anp_core.server.server import server_status
            server_running = server_status.is_running()
            logging.info(f"再次检查服务器状态: {server_running}")
            
            # 如果服务器确实没有运行，返回错误
            if not server_running:
                return {"success": False, "message": "请先启动服务器"}
        
        if not chat_running:
            # 启动聊天但不阻塞主线程
            threading.Thread(target=start_chat, daemon=True).start()
            # 等待聊天线程启动
            time.sleep(1)
            return {"success": True}
        return {"success": True, "message": "聊天已经在运行"}
    except Exception as e:
        logging.error(f"启动聊天出错: {e}")
        return {"success": False, "message": str(e)}

@app.post("/api/chat/stop")
async def stop_chat_api():
    global chat_running
    try:
        if chat_running:
            stop_chat()
            return {"success": True}
        return {"success": True, "message": "聊天已经停止"}
    except Exception as e:
        logging.error(f"停止聊天出错: {e}")
        return {"success": False, "message": str(e)}

# 书签API
@app.get("/api/bookmarks")
async def get_bookmarks(url: Optional[str] = None):
    # 如果提供了URL，从URL加载书签
    if url:
        # 确保load_bookmarks函数已定义
        from web_api import load_bookmarks
        result = load_bookmarks(url)
        return result
    # 否则返回本地书签
    return {"success": True, "bookmarks": bookmarks}

@app.post("/api/bookmarks/add")
async def add_bookmark(request: BookmarkRequest):
    try:
        name = request.name
        
        # 检查是否已存在同名书签
        if any(b.name == name for b in bookmarks):
            return {"success": False, "message": "已存在同名书签"}
        
        # 创建新书签
        bookmark_id = name.lower().replace(" ", "_")
        new_bookmark = Bookmark(id=bookmark_id, name=name)
        bookmarks.append(new_bookmark)
        
        # 保存到文件
        bookmark_dir = Path(__file__).parent / "anp_core" / "anp_bookmark"
        bookmark_dir.mkdir(exist_ok=True, parents=True)
        
        bookmark_file = bookmark_dir / f"{bookmark_id}.js"
        with open(bookmark_file, "w", encoding="utf-8") as f:
            json.dump({
                "name": name,
                "did": "",
                "url": "",
                "port": ""
            }, f, ensure_ascii=False, indent=2)
        
        return {"success": True, "bookmark": new_bookmark}
    except Exception as e:
        logging.error(f"添加书签出错: {e}")
        return {"success": False, "message": str(e)}

@app.delete("/api/bookmarks/{bookmark_id}")
async def delete_bookmark(bookmark_id: str):
    try:
        # 查找书签
        bookmark = next((b for b in bookmarks if b.id == bookmark_id), None)
        if not bookmark:
            return {"success": False, "message": "书签不存在"}
        
        # 从列表中删除
        bookmarks.remove(bookmark)
        
        # 删除文件
        bookmark_file = Path(__file__).parent / "anp_core" / "anp_bookmark" / f"{bookmark_id}.js"
        if bookmark_file.exists():
            bookmark_file.unlink()
        
        return {"success": True}
    except Exception as e:
        logging.error(f"删除书签出错: {e}")
        return {"success": False, "message": str(e)}


# 探索智能体细节描述
@app.post("/api/find/")
async def discoveragent(request: DiscoverAgentRequest):
    try:
        # 添加调试日志
        logging.info("开始处理探索智能体请求")
        
        # 获取请求数据
        bookmark_id = request.bookmark_id
        url = request.url
        port = request.port
        
        # 处理请求逻辑
        logging.info(f"处理智能体探索请求: bookmark_id={bookmark_id}, url={url}, port={port}")
        
        
        # 初始化ANPTool
        from anp_core.discover.anp_tool import ANPTool
        anp_tool = await ANPTool.create_async()
        
        # 构建完整URL
        if port:
            full_url = f"{url}:{port}"
        else:
            full_url = url
        if not full_url.startswith("http://") and not full_url.startswith("https://"):
            full_url = "http://" + full_url
            
        # 初始化变量
        visited_urls = set()
        crawled_documents = []
        discovery_results = {}
        
        # 初始化OpenAI客户端
        client = AsyncAzureOpenAI(
            api_key=os.getenv("AZURE_OPENAI_API_KEY"),
            api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
            azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
            azure_deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT"),
        )
        
        # 定义可用工具
        def get_available_tools(anp_tool_instance):
            return [
                {
                    "type": "function",
                    "function": {
                        "name": "anp_tool",
                        "description": anp_tool_instance.description,
                        "parameters": anp_tool_instance.parameters,
                    },
                }
            ]
        
        # 处理工具调用
        async def handle_tool_call(tool_call, messages, anp_tool, crawled_documents, visited_urls):
            function_name = tool_call.function.name
            function_args = json.loads(tool_call.function.arguments)
            
            if function_name == "anp_tool":
                url = function_args.get("url")
                method = function_args.get("method", "GET")
                headers = function_args.get("headers", {})
                params = function_args.get("params", {})
                body = function_args.get("body")
                
                try:
                    # 使用ANPTool获取URL内容
                    result = await anp_tool.execute(
                        url=url, method=method, headers=headers, params=params, body=body
                    )
                    logging.info(f"ANPTool响应 [url: {url}]")
                    
                    # 记录已访问的URL和获取的内容
                    visited_urls.add(url)
                    crawled_documents.append({"url": url, "method": method, "content": result})
                    
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": json.dumps(result, ensure_ascii=False),
                        }
                    )
                except Exception as e:
                    logging.error(f"使用ANPTool获取URL {url}时出错: {str(e)}")
                    
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": json.dumps(
                                {
                                    "error": f"获取URL失败: {url}",
                                    "message": str(e),
                                }
                            ),
                        }
                    )
        
        try:
            # 获取初始URL内容
            initial_content = await anp_tool.execute(url=full_url)
            visited_urls.add(full_url)
            crawled_documents.append({"url": full_url, "method": "GET", "content": initial_content})
            
            logging.info(f"成功获取初始URL: {full_url}")
            
            # 创建提示模板
            current_date = datetime.now().strftime("%Y-%m-%d")
            prompt_template = f"""
            您是一个通用智能网络数据探索工具。您的目标是通过递归访问各种数据格式（包括JSON-LD、YAML等）来查找用户需要的信息和API，以完成特定任务。
            
            ## 当前任务
            探索智能体的结构和功能，找出所有可用的API端点和服务。
            
            ## 重要说明
            1. 您将收到一个初始URL ({full_url})，这是一个智能体描述文件。
            2. 您需要理解这个智能体的结构、功能和API使用方法。
            3. 您需要像网络爬虫一样持续发现并访问新的URL和API端点。
            4. 您可以使用anp_tool获取任何URL的内容。
            5. 这个工具可以处理各种响应格式，包括：
               - JSON格式：将直接解析为JSON对象。
               - YAML格式：将返回文本内容，您需要分析其结构。
               - 其他文本格式：将返回原始文本内容。
            6. 阅读每个文档，查找与任务相关的信息或API端点。
            7. 您需要自己决定爬取路径，不要等待用户指示。
            8. 注意：您最多可以爬取5个URL，并且必须在达到此限制后结束搜索。
            9. 前两个URL必须尝试"/ad.json"和"/agents/example/ad.json"。
            10. 如果两个ad.json文件爬取遇到验证失败，一定要在总结中说明返回的错误。
            11. 如果两个ad.json文件爬取成功，要将其description字段的原文在总结一开始引用。
            
            ## 爬取策略
            1. 首先获取初始URL的内容，了解智能体的结构和API。
            2. 识别文档中的所有URL和链接，特别是serviceEndpoint、url、@id等字段。
            3. 分析API文档，了解API使用、参数和返回值。
            4. 根据API文档构建适当的请求，查找所需信息。
            5. 记录您访问过的所有URL，避免重复爬取。
            6. 总结您找到的所有相关信息，并提供详细建议。
            
            ## 工作流程
            1. 获取初始URL的内容，了解智能体的功能。
            2. 分析内容，查找所有可能的链接和API文档。
            3. 解析API文档，了解API使用方法。
            4. 根据任务要求构建请求，获取所需信息。
            5. 继续探索相关链接，直到找到足够的信息。
            6. 总结信息，向用户提供最合适的建议。
            
            ## JSON-LD数据解析提示
            1. 注意@context字段，它定义了数据的语义上下文。
            2. @type字段表示实体类型，帮助您理解数据的含义。
            3. @id字段通常是可以进一步访问的URL。
            4. 查找serviceEndpoint、url等字段，它们通常指向API或更多数据。
            
            提供详细信息和清晰解释，帮助用户理解您找到的信息和您的建议。
            
            ## 日期
            当前日期: {current_date}
            """
            
            # 创建初始消息
            messages = [
                {"role": "system", "content": prompt_template},
                {"role": "user", "content": f"请探索智能体 {full_url} 的结构和功能"},
                {
                    "role": "system",
                    "content": f"我已获取初始URL的内容。以下是智能体的描述数据：\n\n```json\n{json.dumps(initial_content, ensure_ascii=False, indent=2)}\n```\n\n请分析这些数据，了解智能体的功能和API使用方法。找出您需要访问的链接，并使用anp_tool获取更多信息，以完成用户的任务。",
                },
            ]
            
            # 开始对话循环
            max_documents = 10  # 最多爬取10个文档
            current_iteration = 0
            
            while current_iteration < max_documents and len(crawled_documents) < max_documents:
                current_iteration += 1
                logging.info(f"开始爬取迭代 {current_iteration}/{max_documents}")
                
                # 获取模型响应
                completion = await client.chat.completions.create(
                    model=os.getenv("AZURE_OPENAI_MODEL"),
                    messages=messages,
                    tools=get_available_tools(anp_tool),
                    tool_choice="auto",
                )
                
                response_message = completion.choices[0].message
                messages.append(
                    {
                        "role": "assistant",
                        "content": response_message.content,
                        "tool_calls": response_message.tool_calls,
                    }
                )
                
                # 检查对话是否应该结束
                if not response_message.tool_calls:
                    logging.info("模型没有请求任何工具调用，结束爬取")
                    break
                
                # 处理工具调用
                for tool_call in response_message.tool_calls:
                    await handle_tool_call(tool_call, messages, anp_tool, crawled_documents, visited_urls)
                    
                    # 如果达到最大爬取文档数，停止处理工具调用
                    if len(crawled_documents) >= max_documents:
                        break
            
            # 创建结果
            discovery_results = {
                "initial_url": full_url,
                "agent_info": initial_content,
                "visited_urls": list(visited_urls),
                "crawled_documents": crawled_documents[:3],  # 只返回前3个文档以避免数据过大
                "summary": response_message.content
            }
            
            logging.info(f"智能体探索完成，共爬取了 {len(crawled_documents)} 个文档")
        except Exception as e:
            logging.error(f"获取智能体信息失败 {full_url}: {str(e)}")
            return {"success": False, "message": f"获取智能体信息失败: {str(e)}"}
        
      
        logging.info(f"智能体探索完成: {bookmark_id}")
        
        # 返回结果给前端
        return {
            "success": True, 
            "message": "智能体探索成功",
            "discovery": discovery_results  # 返回探索结果给前端
        }
    except Exception as e:
        logging.error(f"处理探索智能体请求出错: {e}")
        return {"success": False, "message": str(e)}
    finally:
        logging.info("处理探索智能体请求完成")







# 加载已有的智能体书签
def load_bookmarks(url=None):
    global bookmarks
    bookmarks = []
    
    # 如果提供了URL，从URL获取书签数据
    if url:
        try:
            import requests
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                data = response.json()
                for agent in data:
                    # 确保port是字符串类型
                    port = agent.get("port")
                    if port is not None:
                        port = str(port)
                    
                    bookmark = Bookmark(
                        id=agent.get("name", "").lower().replace(" ", "_"),
                        name=agent.get("name", ""),
                        did=agent.get("did"),
                        url=agent.get("url"),
                        port=port,
                        discovery=agent.get("discovery")
                    )
                    bookmarks.append(bookmark)
                return {"success": True, "bookmarks": bookmarks}
            else:
                logging.error(f"从URL加载书签失败: {response.status_code}")
                return {"success": False, "message": f"从URL加载书签失败: {response.status_code}"}
        except Exception as e:
            logging.error(f"从URL加载书签失败: {e}")
            return {"success": False, "message": str(e)}
    
    # 否则从本地文件加载
    bookmark_dir = Path(__file__).parent / "anp_core" / "anp_bookmark"
    bookmark_dir.mkdir(exist_ok=True, parents=True)
    
    for file in bookmark_dir.glob("*.js"):
        try:
            with open(file, "r", encoding="utf-8") as f:
                data = json.load(f)
                # 确保port是字符串类型
                port = data.get("port")
                if port is not None:
                    port = str(port)
                
                bookmark = Bookmark(
                    id=file.stem,
                    name=data.get("name", file.stem),
                    did=data.get("did"),
                    url=data.get("url"),
                    port=port,
                    discovery=data.get("discovery")
                )
                bookmarks.append(bookmark)
        except Exception as e:
            logging.error(f"加载书签文件 {file} 出错: {e}")
    
    return {"success": True, "bookmarks": bookmarks}

# 启动时加载书签
@app.on_event("startup")
def startup_event():
    # load_bookmarks()
    # 加载聊天历史（如果有）
    load_chat_history()
    # 设置智能体消息事件监听器
    asyncio.create_task(listen_for_agent_messages())

# 异步监听智能体消息事件
async def listen_for_agent_messages():
    from web_anp_llmapp import client_new_message_event
    
    while True:
        try:
            # 等待新消息事件
            await client_new_message_event.wait()
            # 处理新消息
            check_agent_messages()
            # 重置事件状态，准备接收下一个消息
            client_new_message_event.clear()
        except Exception as e:
            logging.error(f"处理智能体消息事件出错: {e}")
            # 短暂等待后继续监听
            await asyncio.sleep(0.5)

# 启动服务器
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)


