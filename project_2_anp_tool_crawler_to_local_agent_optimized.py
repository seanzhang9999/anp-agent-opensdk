#!/usr/bin/env python3
"""
ANP Tool 智能爬虫演示 - 优化版本
使用 ANP 协议进行智能体信息爬取，通过大模型自主决定爬取路径

主要功能:
1. 创建本地Python代码生成智能体
2. 配置智能体API接口
3. 使用智能爬虫调用本地智能体
4. 使用智能爬虫调用外部Web智能体
5. 演示智能体间的协作
"""

import os
import asyncio
import shutil
import sys
import json
import time
from datetime import datetime
from json import JSONEncoder
from urllib.parse import quote

import yaml
from anyio import Path
from dotenv import load_dotenv
from fastapi import Request
from loguru import logger
from starlette.responses import JSONResponse

from anp_open_sdk.anp_sdk_user_data import LocalUserDataManager

# 加载环境变量
load_dotenv()

# 添加项目路径到系统路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from anp_open_sdk.config.legacy.dynamic_config import dynamic_config
from anp_open_sdk.config.path_resolver import path_resolver
from anp_open_sdk.anp_sdk import ANPSDK
from anp_open_sdk.anp_sdk_agent import LocalAgent
from anp_open_sdk.service.interaction.anp_tool import ANPTool
from anp_sdk_demo.services.sdk_manager import DemoSDKManager


class CustomJSONEncoder(JSONEncoder):
    """自定义 JSON 编码器，处理 OpenAI 对象"""
    def default(self, obj):
        if hasattr(obj, '__dict__'):
            return obj.__dict__
        try:
            return super().default(obj)
        except TypeError:
            return str(obj)


class ANPToolCrawler:
    """ANP Tool 智能爬虫 - 简化版本"""

    def __init__(self, sdk: ANPSDK):
        self.sdk = sdk

    async def run_crawler_demo(self, task_input: str, initial_url: str, 
                             use_two_way_auth: bool = True, req_did: str = None, 
                             resp_did: str = None, task_type: str = "code_generation"):
        """运行爬虫演示"""
        try:
            # 获取调用者智能体
            caller_agent = await self._get_caller_agent(req_did)
            if not caller_agent:
                return {"error": "无法获取调用者智能体"}

            # 根据任务类型创建不同的提示模板
            if task_type == "weather_query":
                prompt_template = self._create_weather_search_prompt_template()
                agent_name = "天气查询爬虫"
            else:
                prompt_template = self._create_code_search_prompt_template()
                agent_name = "代码生成爬虫"

            # 调用通用智能爬虫
            result = await self._intelligent_crawler(
                anpsdk=self.sdk,
                caller_agent=str(caller_agent.id),
                target_agent=str(resp_did) if resp_did else str(caller_agent.id),
                use_two_way_auth=use_two_way_auth,
                user_input=task_input,
                initial_url=initial_url,
                prompt_template=prompt_template,
                did_document_path=caller_agent.did_document_path,
                private_key_path=caller_agent.private_key_path,
                task_type=task_type,
                max_documents=10,
                agent_name=agent_name
            )

            return result

        except Exception as e:
            logger.error(f"爬虫演示失败: {e}")
            return {"error": str(e)}

    async def _get_caller_agent(self, req_did: str = None):
        """获取调用者智能体"""
        if req_did is None:
            user_data_manager = LocalUserDataManager()
            user_data_manager.load_users()
            user_data = user_data_manager.get_user_data_by_name("托管智能体_did:wba:agent-did.com:test:public")
            if user_data:
                agent = LocalAgent.from_did(user_data.did)
                self.sdk.register_agent(agent)
                logger.info(f"使用托管身份智能体进行爬取: {agent.name}")
                return agent
            else:
                logger.error("未找到托管智能体")
                return None
        else:
            return LocalAgent.from_did(req_did)

    def _create_code_search_prompt_template(self):
        """创建代码搜索智能体的提示模板"""
        current_date = datetime.now().strftime("%Y-%m-%d")
        return f"""
        你是一个通用的智能代码工具。你的目标是根据用户输入要求调用工具完成代码任务。

        ## 当前任务
        {{task_description}}

        ## 重要提示
        1. 你将收到一个初始 URL（{{initial_url}}），这是一个代理描述文件。
        2. 你需要理解这个代理的结构、功能和 API 使用方法。
        3. 你需要像网络爬虫一样不断发现和访问新的 URL 和 API 端点。
        4. 你可以使用 anp_tool 获取任何 URL 的内容。
        5. 该工具可以处理各种响应格式。
        6. 阅读每个文档以找到与任务相关的信息或 API 端点。
        7. 你需要自己决定爬取路径，不要等待用户指令。
        8. 注意：你最多可以爬取 10 个 URL，达到此限制后必须结束搜索。

        ## 工作流程
        1. 获取初始 URL 的内容并理解代理的功能。
        2. 分析内容以找到所有可能的链接和 API 文档。
        3. 解析 API 文档以了解 API 的使用方法。
        4. 根据任务需求构建请求以获取所需的信息。
        5. 继续探索相关链接，直到找到足够的信息。
        6. 总结信息并向用户提供最合适的建议。

        提供详细的信息和清晰的解释，帮助用户理解你找到的信息和你的建议。

        ## 日期
        当前日期：{current_date}
        """

    def _create_weather_search_prompt_template(self):
        """创建天气搜索智能体的提示模板"""
        return """
        你是一个通用智能网络数据探索工具。你的目标是通过递归访问各种数据格式（包括JSON-LD、YAML等）来找到用户需要的信息和API以完成特定任务。

        ## 当前任务
        {task_description}

        ## 重要提示
        1. 你将收到一个初始URL（{initial_url}），这是一个代理描述文件。
        2. 你需要理解这个代理的结构、功能和API使用方法。
        3. 你需要像网络爬虫一样持续发现和访问新的URL和API端点。
        4. 你可以使用anp_tool来获取任何URL的内容。
        5. 此工具可以处理各种响应格式。
        6. 阅读每个文档以找到与任务相关的信息或API端点。
        7. 你需要自己决定爬取路径，不要等待用户指令。
        8. 注意：你最多可以爬取10个URL，并且必须在达到此限制后结束搜索。

        ## 爬取策略
        1. 首先获取初始URL的内容，理解代理的结构和API。
        2. 识别文档中的所有URL和链接，特别是serviceEndpoint、url、@id等字段。
        3. 分析API文档以理解API用法、参数和返回值。
        4. 根据API文档构建适当的请求，找到所需信息。
        5. 记录所有你访问过的URL，避免重复爬取。
        6. 总结所有你找到的相关信息，并提供详细的建议。

        对于天气查询任务，你需要:
        1. 找到天气查询API端点
        2. 理解如何正确构造请求参数（如城市名、日期等）
        3. 发送天气查询请求
        4. 获取并展示天气信息

        提供详细的信息和清晰的解释，帮助用户理解你找到的信息和你的建议。
        """

    async def _intelligent_crawler(self, user_input: str, initial_url: str, 
                                 prompt_template: str, did_document_path: str, 
                                 private_key_path: str, anpsdk=None, 
                                 caller_agent: str = None, target_agent: str = None,
                                 use_two_way_auth: bool = True, task_type: str = "general",
                                 max_documents: int = 10, agent_name: str = "智能爬虫"):
        """通用智能爬虫功能"""
        logger.info(f"启动{agent_name}智能爬取: {initial_url}")

        # 初始化变量
        visited_urls = set()
        crawled_documents = []

        # 初始化ANPTool
        anp_tool = ANPTool(
            did_document_path=did_document_path,
            private_key_path=private_key_path
        )

        # 获取初始URL内容
        try:
            initial_content = await anp_tool.execute_with_two_way_auth(
                url=initial_url, method='GET', headers={}, params={}, body={},
                anpsdk=anpsdk, caller_agent=caller_agent,
                target_agent=target_agent, use_two_way_auth=use_two_way_auth
            )
            visited_urls.add(initial_url)
            crawled_documents.append(
                {"url": initial_url, "method": "GET", "content": initial_content}
            )
            logger.info(f"成功获取初始URL: {initial_url}")
        except Exception as e:
            logger.error(f"获取初始URL失败: {str(e)}")
            return self._create_error_result(str(e), visited_urls, crawled_documents, task_type)

        # 创建LLM客户端
        client = self._create_llm_client()
        if not client:
            return self._create_error_result("LLM客户端创建失败", visited_urls, crawled_documents, task_type)

        # 创建初始消息
        messages = self._create_initial_messages(prompt_template, user_input, initial_url, initial_content, agent_name)

        # 开始对话循环
        result = await self._conversation_loop(
            client, messages, anp_tool, crawled_documents, visited_urls,
            max_documents, anpsdk, caller_agent, target_agent, use_two_way_auth
        )

        return self._create_success_result(result, visited_urls, crawled_documents, task_type, messages)

    def _create_error_result(self, error_msg: str, visited_urls: set, 
                           crawled_documents: list, task_type: str):
        """创建错误结果"""
        return {
            "content": f"错误: {error_msg}",
            "type": "error",
            "visited_urls": list(visited_urls),
            "crawled_documents": crawled_documents,
            "task_type": task_type,
        }

    def _create_success_result(self, content: str, visited_urls: set, 
                             crawled_documents: list, task_type: str, messages: list):
        """创建成功结果"""
        return {
            "content": content,
            "type": "text",
            "visited_urls": [doc["url"] for doc in crawled_documents],
            "crawled_documents": crawled_documents,
            "task_type": task_type,
            "messages": messages,
        }

    def _create_llm_client(self):
        """创建LLM客户端"""
        try:
            model_provider = os.environ.get("MODEL_PROVIDER", "openai").lower()
            if model_provider == "openai":
                from openai import AsyncOpenAI
                client = AsyncOpenAI(
                    api_key=os.environ.get("OPENAI_API_KEY"),
                    base_url=os.environ.get("OPENAI_API_BASE_URL", "https://api.openai.com/v1"),
        )                
                return client

            else:
                logger.error("需要配置 OpenAI")
                return None
        except Exception as e:
            logger.error(f"创建LLM客户端失败: {e}")
            return None

    def _create_initial_messages(self, prompt_template: str, user_input: str, 
                               initial_url: str, initial_content: dict, agent_name: str):
        """创建初始消息"""
        formatted_prompt = prompt_template.format(
            task_description=user_input, initial_url=initial_url
        )
        
        return [
            {"role": "system", "content": formatted_prompt},
            {"role": "user", "content": user_input},
            {
                "role": "system",
                "content": f"我已获取初始URL的内容。以下是{agent_name}的描述数据:\n\n```json\n{json.dumps(initial_content, ensure_ascii=False, indent=2)}\n```\n\n请分析这些数据，理解{agent_name}的功能和API使用方法。找到你需要访问的链接，并使用anp_tool获取更多信息以完成用户的任务。",
            },
        ]

    async def _conversation_loop(self, client, messages: list, anp_tool: ANPTool, 
                               crawled_documents: list, visited_urls: set, 
                               max_documents: int, anpsdk=None, caller_agent: str = None,
                               target_agent: str = None, use_two_way_auth: bool = True):
        """对话循环处理"""
        model_name = os.environ.get("OPENAI_MODEL_NAME", "gpt-4")
        current_iteration = 0

        while current_iteration < max_documents:
            current_iteration += 1
            logger.info(f"开始爬取迭代 {current_iteration}/{max_documents}")

            if len(crawled_documents) >= max_documents:
                logger.info(f"已达到最大爬取文档数 {max_documents}，停止爬取")
                messages.append({
                    "role": "system",
                    "content": f"你已爬取 {len(crawled_documents)} 个文档，达到最大爬取限制 {max_documents}。请根据获取的信息做出最终总结。",
                })

            try:
                completion = await client.chat.completions.create(
                    model=model_name,
                    messages=messages,
                    tools=self._get_available_tools(anp_tool),
                    tool_choice="auto",
                )

                response_message = completion.choices[0].message
                messages.append({
                    "role": "assistant",
                    "content": response_message.content,
                    "tool_calls": response_message.tool_calls,
                })

                logger.info(f"\n模型思考:\n{response_message.content}")
                if response_message.tool_calls:
                    logger.info(f"\n模型调用:\n{response_message.tool_calls}")

                if not response_message.tool_calls:
                    logger.info("模型没有请求任何工具调用，结束爬取")
                    break

                # 处理工具调用
                await self._handle_tool_calls(
                    response_message.tool_calls, messages, anp_tool, 
                    crawled_documents, visited_urls, anpsdk, caller_agent, 
                    target_agent, use_two_way_auth, max_documents
                )

                if len(crawled_documents) >= max_documents and current_iteration < max_documents:
                    continue

            except Exception as e:
                logger.error(f"模型调用失败: {e}")
                messages.append({
                    "role": "system",
                    "content": f"处理过程中发生错误: {str(e)}。请根据已获取的信息做出最佳判断。",
                })
                break

        # 返回最后的响应内容
        if messages and messages[-1]["role"] == "assistant":
            return messages[-1].get("content", "处理完成")
        return "处理完成"

    def _get_available_tools(self, anp_tool_instance):
        """获取可用工具列表"""
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

    async def _handle_tool_calls(self, tool_calls, messages: list, anp_tool: ANPTool,
                               crawled_documents: list, visited_urls: set,
                               anpsdk=None, caller_agent: str = None,
                               target_agent: str = None, use_two_way_auth: bool = False,
                               max_documents: int = 10):
        """处理工具调用"""
        for tool_call in tool_calls:
            if tool_call.function.name == "anp_tool":
                await self._handle_anp_tool_call(
                    tool_call, messages, anp_tool, crawled_documents, visited_urls,
                    anpsdk, caller_agent, target_agent, use_two_way_auth
                )
                
                if len(crawled_documents) >= max_documents:
                    break

    async def _handle_anp_tool_call(self, tool_call, messages: list, anp_tool: ANPTool,
                                  crawled_documents: list, visited_urls: set,
                                  anpsdk=None, caller_agent: str = None,
                                  target_agent: str = None, use_two_way_auth: bool = False):
        """处理ANP工具调用"""
        function_args = json.loads(tool_call.function.arguments)
        
        url = function_args.get("url")
        method = function_args.get("method", "GET")
        headers = function_args.get("headers", {})
        params = function_args.get("params", {})
        body = function_args.get("body", {})
        
        # 处理消息参数
        if len(body) == 0:
            message_value = self._find_message_in_args(function_args)
            if message_value is not None:
                logger.info(f"模型发出调用消息：{message_value}")
                body = {"message": message_value}

        try:
            if use_two_way_auth:
                result = await anp_tool.execute_with_two_way_auth(
                    url=url, method=method, headers=headers, params=params, body=body,
                    anpsdk=anpsdk, caller_agent=caller_agent,
                    target_agent=target_agent, use_two_way_auth=use_two_way_auth
                )
            else:
                result = await anp_tool.execute(
                    url=url, method=method, headers=headers, params=params, body=body
                )
            
            logger.info(f"ANPTool 响应 [url: {url}]")
            
            visited_urls.add(url)
            crawled_documents.append({"url": url, "method": method, "content": result})
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": json.dumps(result, ensure_ascii=False),
            })
            
        except Exception as e:
            logger.error(f"ANPTool调用失败 {url}: {str(e)}")
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": json.dumps({
                    "error": f"ANPTool调用失败: {url}",
                    "message": str(e),
                }),
            })

    def _find_message_in_args(self, data):
        """递归查找参数中的message值"""
        if isinstance(data, dict):
            if "message" in data:
                return data["message"]
            for value in data.values():
                result = self._find_message_in_args(value)
                if result:
                    return result
        elif isinstance(data, list):
            for item in data:
                result = self._find_message_in_args(item)
                if result:
                    return result
        return None


# ============================================================================
# 主要功能函数 - 简化版本
# ============================================================================

async def create_python_agent(sdk: ANPSDK):
    """创建Python代码生成智能体"""
    logger.info("步骤1: 创建Python代码生成智能体")

    from anp_open_sdk.anp_sdk_user_data import did_create_user

    # 创建临时用户参数
    temp_user_params = {
        'name': 'Python任务智能体',
        'host': 'localhost',
        'port': 9527,
        'dir': 'wba',
        'type': 'user'
    }

    # 创建DID文档
    did_document = did_create_user(temp_user_params)
    if not did_document:
        logger.error("智能体创建失败")
        return None

    logger.info(f"智能体创建成功，DID: {did_document['id']}")

    # 创建LocalAgent实例并注册
    python_agent = LocalAgent.from_did(did_document['id'])
    sdk.register_agent(python_agent)
    logger.info(f"智能体 {python_agent.name} 注册成功")
    
    return python_agent


def register_agent_api_handlers(sdk: ANPSDK, python_agent: LocalAgent):
    """为Python智能体注册API处理函数"""
    logger.info("步骤2: 注册API处理函数")
    
    @python_agent.expose_api("/tasks/send", methods=["POST"])
    async def task_receive(request_data, request: Request):
        """处理代码生成请求"""
        start = time.time()
        
        # 检查请求方法
        if request.method == "GET":
            return JSONResponse({"error": "GET method not allowed"}, status_code=405)
            
        try:
            # 验证请求格式
            if request.headers.get("Content-Type") != "application/json":
                return JSONResponse({"error": "请求必须是 JSON 格式"}, status_code=400)
                
            # 检查请求体
            raw_data = await request.body()
            if not raw_data:
                return JSONResponse({"error": "请求体为空"}, status_code=400)
                
            # 解析请求
            body = await request.json()
            message = extract_message_from_body(body)
            
            if not message:
                return JSONResponse({"error": "Missing 'message' field"}, status_code=400)
                
            logger.info(f"收到代码生成请求: {message}")
            
            # 调用LLM生成代码
            code_response = await call_llm(message)
            code = extract_code_from_response(code_response)
            
            logger.info("代码生成完成")
            
            # 构建响应
            response = {
                "jsonrpc": "2.0",
                "id": body.get("id"),
                "result": {"code": code}
            }
            
            return JSONResponse(json.loads(json.dumps(response)), status_code=200)
            
        except Exception as e:
            logger.error(f"任务处理失败: {e}")
            return JSONResponse({"error": str(e)}, status_code=500)
            
        finally:
            logger.info(f"任务耗时: {time.time() - start:.2f}s")


async def configure_agent_interfaces(python_agent: LocalAgent):
    """配置智能体API和接口描述"""
    logger.info("步骤3: 配置智能体接口")

    from anp_open_sdk.anp_sdk_user_data import get_user_dir_did_doc_by_did

    # 获取用户目录
    success, did_doc, user_dir = get_user_dir_did_doc_by_did(python_agent.id)
    if not success:
        logger.error("无法获取用户目录")
        return False
        
    user_dirs = dynamic_config.get('anp_sdk.user_did_path')
    user_full_path = os.path.join(user_dirs, user_dir)
    
    # 创建接口配置
    agent_id = f"http://localhost:9527/wba/user/{python_agent.id}/ad.json"
    
    # 创建智能体描述文档
    agent_description = create_agent_description(python_agent, agent_id)
    
    # 创建API接口描述
    api_interface = create_api_interface()
    
    # 创建JSON-RPC接口描述
    jsonrpc_interface = create_jsonrpc_interface()
    
    # 保存配置文件
    await save_interface_files(user_full_path, agent_description, api_interface, jsonrpc_interface)
    
    logger.info("智能体接口配置完成")
    return True


def create_agent_description(python_agent: LocalAgent, agent_id: str):
    """创建智能体描述文档"""
    return {
        "@context": {
            "@vocab": "https://schema.org/",
            "did": "https://w3id.org/did#",
            "ad": "https://agent-network-protocol.com/ad#"
        },
        "@type": "ad:AgentDescription",
        "@id": agent_id,
        "name": f"ANPSDK Agent{python_agent.name}",
        "did": python_agent.id,
        "owner": {
            "@type": "Organization",
            "name": "code-writer.local",
            "@id": python_agent.id
        },
        "description": "代码生成智能体，可根据自然语言请求生成 Python 示例代码。",
        "version": "1.0.0",
        "created": "2025-05-25T20:00:00Z",
        "endpoint": f"http://localhost:9527/agent/api/{quote(python_agent.id)}/tasks/send",
        "ad:securityDefinitions": {
            "didwba_sc": {
                "scheme": "didwba",
                "in": "header",
                "name": "Authorization"
            }
        },
        "ad:security": "didwba_sc",
        "ad:AgentDescription": [],
        "ad:interfaces": [
            {
                "@type": "ad:NaturalLanguageInterface",
                "protocol": "JSON",
                "url": f"http://localhost:9527/wba/user/{quote(python_agent.id)}/codegen-interface.json",
                "description": "自然语言代码生成接口的 JSON 描述"
            }
        ]
    }


def create_api_interface():
    """创建API接口描述"""
    return {
        "openapi": "3.0.0",
        "info": {
            "title": "Code Writer Agent API",
            "version": "1.0.0"
        },
        "paths": {
            "/tasks/send": {
                "post": {
                    "summary": "基于自然语言生成代码的服务,在post请求的body部分添加message参数,说明生成代码需求,服务将自动返回结果",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "message": {"type": "string"}
                                    }
                                }
                            }
                        }
                    },
                    "responses": {
                        "200": {
                            "description": "生成的代码",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "code": {"type": "string"}
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }


def create_jsonrpc_interface():
    """创建JSON-RPC接口描述"""
    return {
        "jsonrpc": "2.0",
        "summary": "基于自然语言生成代码的服务,在post请求的body部分添加message参数,说明生成代码需求,服务将自动返回结果",
        "method": "generate_code",
        "params": {
            "message": {
                "type": "string",
                "value": "用 Python 生成冒泡排序"
            }
        },
        "result": {
            "code": {
                "type": "string"
            }
        },
        "meta": {
            "openapi": "3.0.0",
            "info": {
                "title": "Code Writer Agent API",
                "version": "1.0.0"
            },
            "httpMethod": "POST",
            "endpoint": "/tasks/send"
        }
    }


async def save_interface_files(user_full_path: str, agent_description: dict, 
                             api_interface: dict, jsonrpc_interface: dict):
    """保存接口配置文件"""
    # 保存智能体描述文件
    template_ad_path = Path(user_full_path) / "template-ad.json"
    template_ad_path = Path(path_resolver.resolve_path(template_ad_path.as_posix()))
    await template_ad_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(template_ad_path, 'w', encoding='utf-8') as f:
        json.dump(agent_description, f, ensure_ascii=False, indent=2)
    logger.info(f"智能体描述文件已保存: {template_ad_path}")

    # 保存YAML接口文件
    template_yaml_path = Path(user_full_path) / "codegen-interface.yaml"
    template_yaml_path = Path(path_resolver.resolve_path(template_yaml_path.as_posix()))
    await template_yaml_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(template_yaml_path, "w", encoding="utf-8") as file:
        yaml.dump(api_interface, file, allow_unicode=True)
    logger.info(f"YAML接口文件已保存: {template_yaml_path}")

    # 保存JSON-RPC接口文件
    template_jsonrpc_path = Path(user_full_path) / "codegen-interface.json"
    template_jsonrpc_path = Path(path_resolver.resolve_path(template_jsonrpc_path.as_posix()))
    await template_jsonrpc_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(template_jsonrpc_path, "w", encoding="utf-8") as file:
        json.dump(jsonrpc_interface, file, indent=2, ensure_ascii=False)
    logger.info(f"JSON-RPC接口文件已保存: {template_jsonrpc_path}")


async def run_crawler_demo(crawler: ANPToolCrawler, target_agent: LocalAgent, 
                         task_input: str, output_file: str = "crawler_result.json"):
    """运行爬虫演示 - 基本版本"""
    logger.info(f"开始爬虫演示: {task_input}")
    
    result = await crawler.run_crawler_demo(
        task_input=task_input,
        initial_url=f"http://localhost:9527/wba/user/{target_agent.id}/ad.json",
        use_two_way_auth=True,
        req_did=None,
        resp_did=target_agent.id,
        task_type="code_generation"
    )
    
    # 保存结果到文件
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2, cls=CustomJSONEncoder)
    logger.info(f"爬取结果已保存到 {output_file}")
    
    return result


async def run_crawler_demo_with_different_agent(crawler: ANPToolCrawler, 
                                               target_agent: LocalAgent, 
                                               sdk: ANPSDK, task_input: str):
    """使用不同智能体身份运行爬虫演示"""
    logger.info(f"使用不同智能体身份运行爬虫演示: {task_input}")
    
    # 获取另一个智能体
    user_data = sdk.user_data_manager.get_user_data_by_name("本田")
    if not user_data:
        logger.warning("未找到'本田'智能体，跳过此演示")
        return None
        
    agent1 = LocalAgent.from_did(user_data.did)

    result = await crawler.run_crawler_demo(
        task_input=task_input,
        initial_url=f"http://localhost:9527/wba/user/{target_agent.id}/ad.json",
        use_two_way_auth=True,
        req_did=agent1.id,
        resp_did=target_agent.id,
        task_type="code_generation"
    )
    
    # 保存结果到文件
    output_file = "anp_sdk_demo/demo_data/agent1_crawler_result.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2, cls=CustomJSONEncoder)
    logger.info(f"爬取结果已保存到 {output_file}")
    
    return result


async def run_web_agent_crawler_demo(crawler: ANPToolCrawler, 
                                   task_input: str = "查询北京天津上海今天的天气",
                                   initial_url: str = "https://agent-search.ai/ad.json"):
    """运行Web智能体爬虫演示 - 来自project_1的功能"""
    logger.info(f"开始Web智能体爬虫演示: {task_input}")
    
    result = await crawler.run_crawler_demo(
        task_input=task_input,
        initial_url=initial_url,
        use_two_way_auth=True,
        req_did=None,
        resp_did=None,
        task_type="weather_query"
    )
    
    # 保存结果到文件
    output_file = "web_agent_crawler_result.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2, cls=CustomJSONEncoder)
    logger.info(f"Web智能体爬取结果已保存到 {output_file}")
    
    return result


async def cleanup_resources(sdk: ANPSDK, python_agent: LocalAgent):
    """清理临时资源"""
    logger.info("步骤6: 清理临时资源")
    
    try:
        from anp_open_sdk.anp_sdk_user_data import get_user_dir_did_doc_by_did

        # 获取用户目录
        success, _, user_dir = get_user_dir_did_doc_by_did(python_agent.id)
        if not success:
            logger.error("无法找到用户目录")
            return
            
        # 从SDK注销智能体
        sdk.unregister_agent(python_agent.id)
        logger.info(f"智能体 {python_agent.name} 已从SDK注销")
        
        # 删除用户目录
        user_dirs = dynamic_config.get('anp_sdk.user_did_path')
        user_full_path = os.path.join(user_dirs, user_dir)
        
        if os.path.exists(user_full_path):
            shutil.rmtree(user_full_path)
            logger.info(f"用户目录已删除: {user_full_path}")
            
    except Exception as e:
        logger.error(f"清理资源时发生错误: {e}")


# ============================================================================
# 辅助函数
# ============================================================================

def extract_message_from_body(body: dict):
    """从请求体中提取message字段"""
    def find_message(data):
        """递归查找 'message' 值"""
        if isinstance(data, dict):
            if "message" in data:
                return data["message"]
            for value in data.values():
                result = find_message(value)
                if result:
                    return result
        elif isinstance(data, list):
            for item in data:
                result = find_message(item)
                if result:
                    return result
        return None
        
    return find_message(body)


def extract_code_from_response(response):
    """从LLM响应中提取代码内容"""
    if isinstance(response, dict):
        return json.dumps(response)
    elif hasattr(response, "content"):
        return response.content
    elif hasattr(response, "__dict__"):
        return json.dumps(response.__dict__)
    return str(response)


async def call_llm(prompt: str):
    """调用LLM生成代码"""
    try:
        llm_client = create_llm_client()
        if not llm_client:
            return "# [错误] 无法创建LLM客户端"
            
        model_name = os.environ.get("OPENAI_MODEL_NAME", "gpt-4")

        messages = [
            {"role": "system", "content": "你是一个擅长写 Python 代码的助手"},
            {"role": "user", "content": prompt}
        ]

        completion = await llm_client.chat.completions.create(
            model=model_name,
            messages=messages
        )

        response_message = completion.choices[0].message
        return response_message
        
    except Exception as e:
        logger.error(f"模型服务调用失败: {e}")
        return "# [错误] 无法生成代码"


def create_llm_client():
    """创建LLM客户端"""
    try:
        model_provider = os.environ.get("MODEL_PROVIDER", "openai").lower()
        if model_provider == "openai":
            from openai import AsyncOpenAI
            client = AsyncOpenAI(
                api_key=os.environ.get("OPENAI_API_KEY"),
                base_url=os.environ.get("OPENAI_API_BASE_URL", "https://api.openai.com/v1"),
        )
            return client
        else:
            logger.error("需要配置OpenAI")
            return None

    except Exception as e:
        logger.error(f"创建LLM客户端失败: {e}")
        return None


# ============================================================================
# 主函数 - 清晰的流程展示
# ============================================================================

async def main():
    """
    主函数：演示ANP智能爬虫与本地/Web智能体交互的完整流程
    
    核心步骤:
    1. 创建并初始化SDK
    2. 创建本地Python代码生成智能体
    3. 配置智能体API和接口描述
    4. 启动服务并运行爬虫演示
    5. 运行Web智能体爬虫演示
    6. 清理资源
    """
    logger.info("=== ANP智能爬虫演示开始 ===")
    
    # 步骤1: 初始化SDK
    logger.info("步骤1: 初始化ANP SDK")
    sdk = ANPSDK()
    
    # 步骤2: 创建Python代码生成智能体
    python_agent = await create_python_agent(sdk)
    if not python_agent:
        logger.error("智能体创建失败，退出演示")
        return
    
    # 步骤3: 注册API服务函数
    register_agent_api_handlers(sdk, python_agent)
    
    # 步骤4: 配置智能体接口
    success = await configure_agent_interfaces(python_agent)
    if not success:
        logger.error("智能体接口配置失败，退出演示")
        return
    
    # 步骤5: 启动服务
    logger.info("步骤4: 启动ANP服务")
    sdk_manager = DemoSDKManager()
    sdk_manager.start_server(sdk)
    
    # 步骤6: 创建并运行爬虫演示
    logger.info("步骤5: 运行智能爬虫演示")
    crawler = ANPToolCrawler(sdk)
    
    try:
        # 演示1: 基本爬虫功能 - 生成冒泡排序代码
        logger.info("\n=== 演示1: 本地智能体 - 基本爬虫功能 ===")
        await run_crawler_demo(
            crawler, 
            python_agent, 
            "写个冒泡法排序代码",
            "anp_sdk_demo/demo_data/agent_anptool_crawler_result.json"
        )
        
        # 演示2: 使用不同智能体身份 - 生成随机数代码
        logger.info("\n=== 演示2: 本地智能体 - 使用不同智能体身份 ===")
        await run_crawler_demo_with_different_agent(
            crawler, 
            python_agent, 
            sdk, 
            "写个随机数生成代码"
        )
        
        # 演示3: Web智能体爬虫演示 - 来自project_1的功能
        logger.info("\n=== 演示3: Web智能体 - 天气查询功能 ===")
        await run_web_agent_crawler_demo(
            crawler,
            "查询北京天津上海今天的天气",
            "https://agent-search.ai/ad.json"
        )
        
        logger.info("\n=== 所有演示完成 ===")
        
    except Exception as e:
        logger.error(f"演示过程中发生错误: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        # 步骤7: 清理资源
        await cleanup_resources(sdk, python_agent)
        logger.info("=== ANP智能爬虫演示结束 ===")


if __name__ == "__main__":
    # 运行主函数
    asyncio.run(main())