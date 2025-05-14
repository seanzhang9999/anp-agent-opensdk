"""DID WBA Web API - 为Web界面提供API接口

重构版本：使用类封装和配置分离模式
"""

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
from pydantic import BaseModel

# 本地模块
from core.config import settings
from web_anp_llmapp import (
    resp_start, resp_stop,
    start_chat, stop_chat,
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
# 导入服务类
from services import llm_service, chat_history_service, agent_service
from config import dynamic_config

# 配置日志
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

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
    
class BookmarkUrlRequest(BaseModel):
    url: str

# 定义探索智能体请求模型
class DiscoverAgentRequest(BaseModel):
    bookmark_id: str
    url: str
    port: str

# 上次检查智能体消息的时间
last_agent_check_time = 0

# 在应用启动时加载聊天历史
@app.on_event("startup")
async def startup_event():
    # 加载聊天历史
    chat_history_service.load_history()
    logger.info("应用已启动，聊天历史已加载")

# 在应用关闭时保存聊天历史
@app.on_event("shutdown")
async def shutdown_event():
    # 保存聊天历史
    chat_history_service.save_history()
    logger.info("应用已关闭，聊天历史已保存")

# 在send_message函数中添加对isRecommendation的处理
@app.post("/api/chat/send")
async def send_message(request: MessageRequest):
    global chat_running
    try:
        # 从anp_llmapp_web模块获取最新的聊天状态
        from web_anp_llmapp import chat_running as current_chat_running
        chat_running = current_chat_running
        
        if not chat_running:
            return {"success": False, "message": "请先启动聊天"}
        
        message = request.message
        
        # 添加用户消息到聊天历史
        chat_history_service.add_user_message(message)
        
        # 如果是智能体推荐请求
        if request.isRecommendation:
            try:
                # 调用LLM服务处理推荐请求
                success, response = await llm_service.process_recommendation(message)
                
                if success:
                    # 添加助手回复到聊天历史
                    chat_history_service.add_assistant_message(response)
                    return {"success": True, "response": response}
                else:
                    return {"success": False, "message": response}
            except Exception as e:
                logger.error(f"智能体推荐处理出错: {e}")
                fallback_response = f"抱歉，无法完成推荐: {str(e)}"
                return {"success": False, "message": fallback_response}
        # 如果是智能体命令
        elif request.isAgentCommand:
            try:
                # 使用智能体服务发送消息
                success, response = await agent_service.send_message(
                    message, 
                    agent_info=request.agentInfo
                )
                
                # 添加系统消息到聊天历史
                chat_history_service.add_system_message(response)
                
                if success:
                    return {"success": True, "response": response}
                else:
                    return {"success": False, "message": response}
            except Exception as e:
                logger.error(f"智能体命令处理出错: {e}")
                error_msg = f"处理智能体命令时出错: {str(e)}"
                chat_history_service.add_system_message(error_msg)
                return {"success": False, "message": error_msg}
        else:
            # 普通消息，使用LLM服务处理
            try:
                # 调用LLM服务处理消息
                success, response = await llm_service.process_message(
                    message, 
                    chat_history_service.get_history()
                )
                
                if success:
                    # 添加前缀
                    response = "localAI：" + response
                    # 添加助手回复到聊天历史
                    chat_history_service.add_assistant_message(response)
                    return {"success": True, "response": response}
                else:
                    # 如果LLM处理失败，返回错误信息
                    fallback_response = f"抱歉，处理您的消息时出现了问题: {response}"
                    chat_history_service.add_assistant_message(fallback_response)
                    return {"success": True, "response": fallback_response}
            except Exception as e:
                logger.error(f"大模型处理出错: {e}")
                # 如果大模型处理失败，返回简单回复
                fallback_response = f"抱歉，处理您的消息时出现了问题: {str(e)}"
                chat_history_service.add_assistant_message(fallback_response)
                return {"success": True, "response": fallback_response}
    except Exception as e:
        logger.error(f"发送消息出错: {e}")
        return {"success": False, "message": str(e)}

# 根路径 - 返回静态HTML页面
@app.get("/")
async def read_root():
    return FileResponse("static/chat/index.html")

# 检查是否有新的智能体消息
def check_agent_messages():
    global last_agent_check_time
    try:
        # 从web_anp_llmapp模块获取最新的客户端消息
        from web_anp_llmapp import client_chat_messages
        
        # 如果没有新消息，直接返回
        if not client_chat_messages:
            return
        
        # 添加消息处理计数器，防止死循环
        processed_count = 0
        max_process_count = dynamic_config.get('chat.max_process_count', 50)
        
        # 直接遍历所有智能体消息，避免仅依赖时间戳
        for msg in client_chat_messages:
            # 限制单次处理的消息数量
            if processed_count >= max_process_count:
                logger.warning(f"单次处理消息数量已达上限 {max_process_count}，跳过剩余消息")
                break
                
            processed_count += 1
            # 只处理assistant类型且from_agent为True的消息，或anp_nlp类型的远程智能体消息
            if (msg.get('type') == 'assistant' and msg.get('from_agent', False)):
                # 检查这条消息是否已经在聊天历史中
                message_content = msg.get('content', '')
                if not chat_history_service.message_exists(message_content, 'assistant'):
                    # 添加到聊天历史
                    chat_history_service.add_assistant_message(
                        message_content,
                        from_agent=True,
                        save=False
                    )
                    logger.info(f"添加智能体消息到聊天历史: {message_content}")
            elif msg.get('type') == 'anp_nlp':
                # 为anp_nlp类型消息添加时间戳（如果不存在）
                if not msg.get('timestamp'):
                    msg['timestamp'] = time.time()
                
                # 使用assistant_message作为消息内容
                message_content = msg.get('assistant_message', '[无回复]')
                
                # 检查这条消息是否已经在聊天历史中
                if not chat_history_service.message_exists(message_content, 'anp_nlp'):
                    # 添加到聊天历史
                    chat_history_service.add_agent_message(
                        message_content,
                        save=False
                    )
                    logger.info(f"添加anp_nlp消息到聊天历史: {message_content[:50]}...")
            else:
                # 非 assistant 或 anp_nlp 类型消息可根据需要处理或跳过，这里简单跳过
                continue
        # 更新时间为当前时间
        last_agent_check_time = time.time()
        # 保存聊天历史
        chat_history_service.save_history()
    except Exception as e:
        logger.error(f"检查智能体消息出错: {e}")

# 获取聊天历史
@app.get("/api/chat/history")
async def get_chat_history():
    # 先检查是否有新的智能体消息
    check_agent_messages()
    # 返回聊天历史
    return {"success": True, "history": chat_history_service.get_history()}

# 清除聊天历史
@app.post("/api/chat/clear-history")
async def clear_chat_history():
    chat_history_service.clear_history()
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
            user_dir = Path(settings.DID_DOCUMENTS_PATH) / f"user_{unique_id}"
            did_document_path = user_dir / settings.DID_DOCUMENT_FILENAME
            return {
                "running": server_running,
                "did_id": did_id,
                "did_document_path": str(did_document_path) if did_document_path.exists() else ''
            }
    
    # 如果服务器未运行或无法获取DID信息，只返回运行状态
    return {"running": False}

@app.post("/api/server/start")
async def start_server():
    global server_running
    try:
        if not server_running:
            # 检查是否每次生成新的DID
            generate_new_did = dynamic_config.get('server.generate_new_did_each_time', True)
            
            if generate_new_did:
                # 生成新的唯一ID
                unique_id = secrets.token_hex(8)
                os.environ['unique-id'] = unique_id
                logger.info(f"使用唯一ID: {unique_id}")
            
            # 启动服务器
            result = resp_start()
            if result:
                server_running = True
                return {"success": True}
            else:
                return {"success": False, "message": "启动服务器失败"}
        else:
            return {"success": True, "message": "服务器已经在运行中"}
    except Exception as e:
        logger.error(f"启动服务器出错: {e}")
        return {"success": False, "message": str(e)}

@app.post("/api/server/stop")
async def stop_server():
    global server_running
    try:
        if server_running:
            result = resp_stop()
            if result:
                server_running = False
                return {"success": True}
            else:
                return {"success": False, "message": "停止服务器失败"}
        else:
            return {"success": True, "message": "服务器已经停止"}
    except Exception as e:
        logger.error(f"停止服务器出错: {e}")
        return {"success": False, "message": str(e)}

# 聊天API
@app.post("/api/chat/start")
async def start_chat_api():
    global chat_running
    try:
        if not chat_running:
            start_chat()
            chat_running = True
            return {"success": True}
        else:
            return {"success": True, "message": "聊天已经在运行中"}
    except Exception as e:
        logger.error(f"启动聊天出错: {e}")
        return {"success": False, "message": str(e)}

@app.post("/api/chat/stop")
async def stop_chat_api():
    global chat_running
    try:
        if chat_running:
            stop_chat()
            chat_running = False
            return {"success": True}
        else:
            return {"success": True, "message": "聊天已经停止"}
    except Exception as e:
        logger.error(f"停止聊天出错: {e}")
        return {"success": False, "message": str(e)}

# 书签API
@app.get("/api/bookmarks")
async def get_bookmarks():
    try:
        bookmarks = agent_service.get_bookmarks()
        return {"success": True, "bookmarks": bookmarks}
    except Exception as e:
        logger.error(f"获取书签出错: {e}")
        return {"success": False, "message": str(e)}

@app.post("/api/bookmarks")
async def create_bookmark(bookmark: Bookmark):
    try:
        bookmark_data = bookmark.dict()
        success = agent_service.save_bookmark(bookmark_data)
        if success:
            return {"success": True, "bookmark": bookmark_data}
        else:
            return {"success": False, "message": "保存书签失败"}
    except Exception as e:
        logger.error(f"创建书签出错: {e}")
        return {"success": False, "message": str(e)}

@app.delete("/api/bookmarks/{bookmark_id}")
async def delete_bookmark(bookmark_id: str):
    try:
        success = agent_service.delete_bookmark(bookmark_id)
        if success:
            return {"success": True}
        else:
            return {"success": False, "message": "删除书签失败"}
    except Exception as e:
        logger.error(f"删除书签出错: {e}")
        return {"success": False, "message": str(e)}
        
@app.post("/api/bookmarks/load-from-url")
async def load_bookmarks_from_url(request: BookmarkUrlRequest):
    try:
        success, message, bookmarks = await agent_service.load_bookmarks_from_url(request.url)
        if success:
            return {"success": True, "bookmarks": bookmarks}
        else:
            return {"success": False, "message": message}
    except Exception as e:
        logger.error(f"从URL加载书签出错: {e}")
        return {"success": False, "message": str(e)}

# 探索智能体API
@app.post("/api/discoveragent/")
async def discoveragent(request: DiscoverAgentRequest):
    try:
        logger.info("开始处理探索智能体请求")
        
        # 获取请求数据
        bookmark_id = request.bookmark_id
        url = request.url
        port = request.port
        
        logger.info(f"处理智能体探索请求: bookmark_id={bookmark_id}, url={url}, port={port}")
        
        # 初始化工具和客户端
        anp_tool, client = await _initialize_discovery_tools()
        
        # 构建完整URL
        full_url = _build_full_url(url, port)
        
        # 初始化变量
        visited_urls = set()
        crawled_documents = []
        
        try:
            # 执行智能体探索
            discovery_results = await _explore_agent(
                anp_tool, client, full_url, visited_urls, crawled_documents
            )
            
            logger.info(f"智能体探索完成: {bookmark_id}")
            
            # 返回结果给前端
            return {
                "success": True, 
                "message": "智能体探索成功",
                "discovery": discovery_results  # 返回探索结果给前端
            }
        except Exception as e:
            logger.error(f"获取智能体信息失败 {full_url}: {str(e)}")
            return {"success": False, "message": f"获取智能体信息失败: {str(e)}"}
    except Exception as e:
        logger.error(f"处理探索智能体请求出错: {e}")
        return {"success": False, "message": str(e)}
    finally:
        logger.info("处理探索智能体请求完成")

async def _initialize_discovery_tools():
    """初始化智能体探索所需的工具和客户端"""
    # 初始化ANPTool
    from anp_core.discover.anp_tool import ANPTool
    anp_tool = await ANPTool.create_async()
    
    # 初始化OpenAI客户端
    from openai import AsyncAzureOpenAI
    client = AsyncAzureOpenAI(
        api_key=os.getenv("AZURE_OPENAI_API_KEY"),
        api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
        azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
        azure_deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT"),
    )
    
    return anp_tool, client

def _build_full_url(url, port):
    """构建完整的URL，包括端口和协议"""
    if port:
        full_url = f"{url}:{port}"
    else:
        full_url = url
    if not full_url.startswith("http://") and not full_url.startswith("https://"):
        full_url = "http://" + full_url
    return full_url

def _get_available_tools(anp_tool_instance):
    """获取可用的工具列表"""
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

async def _handle_tool_call(tool_call, messages, anp_tool, crawled_documents, visited_urls):
    """处理工具调用，获取URL内容并更新消息和文档"""
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
            logger.info(f"ANPTool响应 [url: {url}]")
            
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
            logger.error(f"使用ANPTool获取URL {url}时出错: {str(e)}")
            
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

async def _explore_agent(anp_tool, client, full_url, visited_urls, crawled_documents):
    """执行智能体探索，爬取API并返回结构化信息"""
    # 获取初始URL内容
    initial_content = await anp_tool.execute(url=full_url)
    visited_urls.add(full_url)
    crawled_documents.append({"url": full_url, "method": "GET", "content": initial_content})
    
    logger.info(f"成功获取初始URL: {full_url}")
    
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
    response_message = None
    
    while current_iteration < max_documents and len(crawled_documents) < max_documents:
        current_iteration += 1
        logger.info(f"开始爬取迭代 {current_iteration}/{max_documents}")
        
        # 获取模型响应
        completion = await client.chat.completions.create(
            model=os.getenv("AZURE_OPENAI_MODEL"),
            messages=messages,
            tools=_get_available_tools(anp_tool),
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
            logger.info("模型没有请求任何工具调用，结束爬取")
            break
        
        # 处理工具调用
        for tool_call in response_message.tool_calls:
            await _handle_tool_call(tool_call, messages, anp_tool, crawled_documents, visited_urls)
            
            # 如果达到最大爬取文档数，停止处理工具调用
            if len(crawled_documents) >= max_documents:
                break
    
    # 创建结果
    discovery_results = {
        "initial_url": full_url,
        "agent_info": initial_content,
        "visited_urls": list(visited_urls),
        "crawled_documents": crawled_documents[:3],  # 只返回前3个文档以避免数据过大
        "summary": response_message.content if response_message else ""
    }
    
    logger.info(f"智能体探索完成，共爬取了 {len(crawled_documents)} 个文档")
    return discovery_results

# 配置API
@app.get("/api/config")
async def get_config():
    try:
        # 获取动态配置
        config = dynamic_config._config
        return {"success": True, "config": config}
    except Exception as e:
        logger.error(f"获取配置出错: {e}")
        return {"success": False, "message": str(e)}

@app.post("/api/config")
async def update_config(config: Dict[str, Any]):
    try:
        # 更新动态配置
        success = dynamic_config.update(config)
        
        # 同时更新各服务的配置
        if 'llm' in config:
            llm_service.update_config(config['llm'])
        if 'agent' in config:
            agent_service.update_config(config['agent'])
        if 'chat' in config and 'max_history_items' in config['chat']:
            chat_history_service.update_config(config['chat']['max_history_items'])
        
        if success:
            return {"success": True, "config": dynamic_config._config}
        else:
            return {"success": False, "message": "更新配置失败"}
    except Exception as e:
        logger.error(f"更新配置出错: {e}")
        return {"success": False, "message": str(e)}

@app.post("/api/config/reset")
async def reset_config():
    try:
        # 重置为默认配置
        success = dynamic_config.reset_to_default()
        if success:
            return {"success": True, "config": dynamic_config._config}
        else:
            return {"success": False, "message": "重置配置失败"}
    except Exception as e:
        logger.error(f"重置配置出错: {e}")
        return {"success": False, "message": str(e)}

# 主函数
if __name__ == "__main__":
    import uvicorn
    # 启动FastAPI应用
    host = dynamic_config.get('web_api.server.webui-host')
    port = dynamic_config.get('web_api.server.webui-port')
    uvicorn.run(app, host=host, port=port)
