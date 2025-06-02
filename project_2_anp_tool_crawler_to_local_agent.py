#!/usr/bin/env python3
"""
ANP Tool 智能爬虫演示
使用 ANP 协议进行智能体信息爬取，通过大模型自主决定爬取路径
"""
from datetime import datetime
import os
import asyncio
import shutil
import sys
import json
import time
from json import JSONEncoder
from typing import Dict, Any, List, Optional, Coroutine
from urllib.parse import quote
from fastapi import Request
from fastapi import FastAPI, Request

import yaml
from anyio import Path
from dotenv import load_dotenv
from fastapi.openapi.utils import status_code_ranges
from loguru import logger
from openai.types.chat import ChatCompletionMessage
from starlette.responses import JSONResponse

from anp_open_sdk.config.dynamic_config import dynamic_config
from anp_open_sdk.config.path_resolver import path_resolver
from anp_sdk_demo.services.sdk_manager import DemoSDKManager

# 加载环境变量
load_dotenv()

# 添加项目路径到系统路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from anp_open_sdk.anp_sdk import ANPSDK
from anp_open_sdk.anp_sdk_agent import LocalAgent
from anp_open_sdk.service.anp_tool import ANPTool
from anp_sdk_demo.demo_modules import agent_loader


class ANPToolCrawler:
    """ANP Tool 智能爬虫"""

    def __init__(self, sdk:ANPSDK):
        self.sdk = sdk
        self.agents = []
        self.anp_tool = None




    async def run_crawler_demo(self,
                             task_input: str = "查询北京天津上海今天的天气",
                             initial_url: str = "https://agent-search.ai/ad.json",
                             use_two_way_auth: bool = True,
                               req_did: str = None,
                               resp_did: str = None):



        try:
            # 尝试加载托管智能体


            if req_did is None:
                user_data_manager = self.sdk.user_data_manager
                user_data_manager.load_users()
                user_data = user_data_manager.get_user_data_by_name("托管智能体_did:wba:agent-did.com:test:public")
                if user_data:
                    agent_anptool = LocalAgent(self.sdk, user_data.did, user_data.name)
                    self.sdk.register_agent(agent_anptool)
                    logger.info(f"使用托管智能体: {agent_anptool.name}")
                else:
                    logger.error("未找到托管智能体，停止")
                    return

            else:
                agent_anptool = LocalAgent(self.sdk, req_did)


        except Exception as e:
            logger.warning(f"加载托管智能体失败: {e}，停止")
            return

        # 定义任务
        task = {
            "input": task_input,
            "type": "weather_query",
        }

        # 创建搜索智能体的提示模板
        # SEARCH_AGENT_PROMPT_TEMPLATE =
        """
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
        current_date = datetime.now().strftime("%Y-%m-%d")
        SEARCH_AGENT_PROMPT_TEMPLATE = f"""
        你是一个通用的智能代码工具。你的目标是根据用户输入要求调用工具完成代码任务。

        ## 当前任务
        {{task_description}}

        ## 重要提示
        1. 你将收到一个初始 URL（{{initial_url}}），这是一个代理描述文件。
        2. 你需要理解这个代理的结构、功能和 API 使用方法。
        3. 你需要像网络爬虫一样不断发现和访问新的 URL 和 API 端点。
        4. 你可以使用 anp_tool 获取任何 URL 的内容。
        5. 该工具可以处理各种响应格式，包括：
           - JSON 格式：将直接解析为 JSON 对象。
           - YAML 格式：将返回文本内容，你需要分析其结构，并将其作为后续生成请求的输入。
           - 其他文本格式：将返回原始文本内容。
        6. 阅读每个文档以找到与任务相关的信息或 API 端点。
        7. 你需要自己决定爬取路径，不要等待用户指令。
        8. 注意：你最多可以爬取 10 个 URL，达到此限制后必须结束搜索。

        ## 爬取策略
        1. 首先获取初始 URL 的内容以了解代理的结构和 API。
        2. 识别文档中的所有 URL 和链接，尤其是 serviceEndpoint、url、@id 等字段。
        3. 分析 API 文档以了解 API 的使用方法、参数和返回值。
        4. 根据 API 文档构建适当的请求以找到所需的信息。
        5. 记录所有访问过的 URL 以避免重复爬取。
        6. 总结你找到的所有相关信息并提供详细的建议。
        7. 出错时，要特别注意是否链接参数输出错误，以及post输出参数忽略了body

        ## 工作流程
        1. 获取初始 URL 的内容并理解代理的功能。
        2. 分析内容以找到所有可能的链接和 API 文档。
        3. 解析 API 文档以了解 API 的使用方法。
        4. 根据任务需求构建请求以获取所需的信息。
        5. 继续探索相关链接，直到找到足够的信息。
        6. 总结信息并向用户提供最合适的建议。

        ## JSON-LD 数据解析提示
        1. 注意 @context 字段，它定义了数据的语义上下文。
        2. @type 字段表示实体的类型，帮助你理解数据的含义。
        3. @id 字段通常是一个可以进一步访问的 URL。
        4. 查找 serviceEndpoint、url 等字段，这些字段通常指向 API 或更多数据。

        提供详细的信息和清晰的解释，帮助用户理解你找到的信息和你的建议。

        ## 日期
        当前日期：{current_date}
        """
        # 调用通用智能爬虫
        result = await self.anptool_intelligent_crawler(
            anpsdk=self.sdk,
            caller_agent=str(agent_anptool.id),
            target_agent=str(resp_did), # 对单向认证web 目标id提供一个dummy即可，否则要提供目标did
            use_two_way_auth=use_two_way_auth,
            user_input=task["input"],
            initial_url=initial_url,
            prompt_template=SEARCH_AGENT_PROMPT_TEMPLATE,
            did_document_path=agent_anptool.did_document_path,
            private_key_path=agent_anptool.private_key_path,
            task_type=task["type"],
            max_documents=10,
            agent_name="搜索智能体"
        )

        return result

    async def anptool_intelligent_crawler(
        self,
        user_input: str,
        initial_url: str,
        prompt_template: str,
        did_document_path: str,
        private_key_path: str,
        anpsdk=None,
        caller_agent: str = None,
        target_agent: str = None,
        use_two_way_auth: bool = True,
        task_type: str = "general",
        max_documents: int = 10,
        agent_name: str = "智能爬虫"
    ):
        """
        通用智能爬虫功能 - 使用大模型自主决定爬取路径

        参数:
            user_input: 用户输入的任务描述
            initial_url: 初始URL，作为爬虫的起始点
            prompt_template: 提示模板字符串，需要包含{task_description}和{initial_url}占位符
            did_document_path: DID文档路径，用于身份认证
            private_key_path: 私钥路径，用于签名认证
            anpsdk: ANP SDK实例，可选参数
            caller_agent: 调用者智能体ID
            target_agent: 目标智能体ID
            use_two_way_auth: 是否使用双向认证，默认True
            task_type: 任务类型，用于分类和处理，默认"general"
            max_documents: 最大爬取文档数，防止无限爬取，默认10
            agent_name: 代理名称，用于日志显示，默认"智能爬虫"

        返回:
            Dict: 包含爬取结果的字典，包含以下字段：
                - content: 爬取结果的主要内容
                - type: 结果类型（text/error）
                - visited_urls: 访问过的URL列表
                - crawled_documents: 爬取的文档详细信息
                - task_type: 任务类型
                - messages: 与大模型的对话历史（可选）
        """
        logger.info(f"启动{agent_name}智能爬取: {initial_url}")

        # 初始化变量
        visited_urls = set()
        crawled_documents = []

        # 初始化ANPTool
        logger.info("初始化ANP工具...")
        anp_tool = ANPTool(
            did_document_path=did_document_path,
            private_key_path=private_key_path
        )

        # 获取初始URL内容
        try:
            logger.info(f"开始获取初始URL: {initial_url}")
            initial_content = await anp_tool.execute_with_two_way_auth(
            url=initial_url, method = 'GET', headers ={}, params ={}, body ={},
            anpsdk = anpsdk, caller_agent = caller_agent,
            target_agent = target_agent, use_two_way_auth = use_two_way_auth
            )
            visited_urls.add(initial_url)
            crawled_documents.append(
                {"url": initial_url, "method": "GET", "content": initial_content}
            )
            logger.info(f"成功获取初始URL: {initial_url}")
        except Exception as e:
            logger.error(f"获取初始URL {initial_url} 失败: {str(e)}")
            return {
                "content": f"获取初始URL失败: {str(e)}",
                "type": "error",
                "visited_urls": list(visited_urls),
                "crawled_documents": crawled_documents,
                "task_type": task_type,
            }

        # 创建初始消息
        formatted_prompt = prompt_template.format(
            task_description=user_input, initial_url=initial_url
        )

        messages = [
            {"role": "system", "content": formatted_prompt},
            {"role": "user", "content": user_input},
            {
                "role": "system",
                "content": f"我已获取初始URL的内容。以下是{agent_name}的描述数据:\n\n```json\n{json.dumps(initial_content, ensure_ascii=False, indent=2)}\n```\n\n请分析这些数据，理解{agent_name}的功能和API使用方法。找到你需要访问的链接，并使用anp_tool获取更多信息以完成用户的任务。",
            },
        ]

        # 创建客户端
        try:
            model_provider = os.environ.get("MODEL_PROVIDER", "azure").lower()
            model_name = os.environ.get("AZURE_OPENAI_MODEL_NAME", "gpt-4")

            if model_provider == "azure":
                # Azure OpenAI
                from openai import AsyncAzureOpenAI
                client = AsyncAzureOpenAI(
                    api_key=os.environ.get("AZURE_OPENAI_API_KEY"),
                    api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2023-05-15"),
                    azure_endpoint=os.environ.get("AZURE_OPENAI_ENDPOINT"),
                    azure_deployment=os.environ.get("AZURE_OPENAI_DEPLOYMENT"),
                )
            else:
                logger.error(f"创建LLM客户端失败: 需要 azure配置")
                return {
                    "content": "LLM客户端创建失败: 需要配置Azure OpenAI",
                    "type": "error",
                    "visited_urls": list(visited_urls),
                    "crawled_documents": crawled_documents,
                    "task_type": task_type,
                }

        except Exception as e:
            logger.error(f"创建LLM客户端失败: {e}")
            return {
                "content": f"LLM客户端创建失败: {str(e)}",
                "type": "error",
                "visited_urls": list(visited_urls),
                "crawled_documents": crawled_documents,
                "task_type": task_type,
            }

        # 开始对话循环
        current_iteration = 0

        while current_iteration < max_documents:
            current_iteration += 1
            logger.info(f"开始爬取迭代 {current_iteration}/{max_documents}")

            # 检查是否已达到最大爬取文档数
            if len(crawled_documents) >= max_documents:
                logger.info(f"已达到最大爬取文档数 {max_documents}，停止爬取")
                messages.append({
                    "role": "system",
                    "content": f"你已爬取 {len(crawled_documents)} 个文档，达到最大爬取限制 {max_documents}。请根据获取的信息做出最终总结。",
                })

            # 获取模型响应
            logger.info(f"迭代 {current_iteration}: 请求模型分析和决策")

            try:
                completion = await client.chat.completions.create(
                    model=model_name,
                    messages=messages,
                    tools=self.get_available_tools(anp_tool),
                    tool_choice="auto",
                )

                response_message = completion.choices[0].message
                messages.append({
                    "role": "assistant",
                    "content": response_message.content,
                    "tool_calls": response_message.tool_calls,
                })
                # 显示模型分析与API计划
                logger.info(f"\n本地模型思考:\n{response_message.content}\n本地模型调用:\n{response_message.tool_calls}")




                # 检查对话是否应该结束
                if not response_message.tool_calls:
                    logger.info("模型没有请求任何工具调用，结束爬取")
                    break

                # 处理工具调用
                logger.info(f"迭代 {current_iteration}: 执行工具调用")
                logger.info(f"执行 {len(response_message.tool_calls)} 个工具调用")

                for tool_call in response_message.tool_calls:
                    if use_two_way_auth:
                        await self.handle_tool_call(
                            tool_call, messages, anp_tool, crawled_documents, visited_urls,
                            anpsdk=anpsdk, caller_agent=caller_agent, target_agent=target_agent,
                            use_two_way_auth=use_two_way_auth
                        )
                    else:
                        await self.handle_tool_call(
                            tool_call, messages, anp_tool, crawled_documents, visited_urls
                        )

                    # 如果已达到最大爬取文档数，停止处理工具调用
                    if len(crawled_documents) >= max_documents:
                        break

                # 如果已达到最大爬取文档数，做出最终总结
                if (len(crawled_documents) >= max_documents and current_iteration < max_documents):
                    logger.info(f"已达到最大爬取文档数 {max_documents}，做出最终总结")
                    continue

            except Exception as e:
                logger.error(f"模型调用或工具处理失败: {e}")
                import traceback
                logger.error(traceback.format_exc())

                # 添加失败信息到消息列表
                messages.append({
                    "role": "system",
                    "content": f"在处理过程中发生错误: {str(e)}。请根据已获取的信息做出最佳判断。",
                })

                # 再给模型一次机会总结
                try:
                    final_completion = await client.chat.completions.create(
                        model=model_name,
                        messages=messages,
                    )
                    response_message = final_completion.choices[0].message
                except Exception:
                    # 如果再次失败，使用最后成功的消息
                    if len(messages) > 3 and messages[-2]["role"] == "assistant":
                        response_message = messages[-2]
                    else:
                        # 创建一个简单的错误回复
                        response_message = type('obj', (object,), {
                            'content': f"很抱歉，在处理您的请求时遇到了错误。已爬取的文档数: {len(crawled_documents)}。"
                        })
                # 退出循环
                break
        # 创建结果
        result = {
            "content": response_message.content if hasattr(response_message, "content") else response_message.get(
                "content", ""),
            "type": "text",
            "visited_urls": [doc["url"] for doc in crawled_documents],
            "crawled_documents": crawled_documents,
            "task_type": task_type,
            "messages": messages,
        }

        # 显示结果
        logger.info(f"\n=== {agent_name}响应 ===")
        logger.info(result["content"])

        logger.info("\n=== 访问过的URL ===")
        for url in result.get("visited_urls", []):
            logger.info(url)

        logger.info(f"\n=== 总共爬取了 {len(result.get('crawled_documents', []))} 个文档 ===")

        return result

    def get_available_tools(self, anp_tool_instance):
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

    async def handle_tool_call(
            self,
            tool_call: Any,
            messages: List[Dict],
            anp_tool: ANPTool,
            crawled_documents: List[Dict],
            visited_urls: set,
            anpsdk=None,
            caller_agent: str = None,
            target_agent: str = None,
            use_two_way_auth: bool = False
    ) -> None:
        """处理工具调用"""
        function_name = tool_call.function.name
        function_args = json.loads(tool_call.function.arguments)

        if function_name == "anp_tool":
            url = function_args.get("url")
            method = function_args.get("method", "GET")
            headers = function_args.get("headers", {})
            params = function_args.get("params", {})
            body = function_args.get("body",{})
            message_value = None
            if len(body) == 0:
                def find_message(data):
                    """递归查找 'message' 值"""
                    if isinstance(data, dict):  # 如果是字典，遍历键值
                        if "message" in data:
                            return data["message"]
                        for value in data.values():
                            result = find_message(value)  # 递归搜索
                            if result:
                                return result
                    elif isinstance(data, list):  # 如果是列表，遍历每个元素
                        for item in data:
                            result = find_message(item)
                            if result:
                                return result
                    return None  # 如果未找到，返回 None

                message_value = find_message(function_args)
            if message_value is not None:
                logger.info(f"本地模型发出调用消息：{message_value}")
                body = {"message": message_value}

            try:
                # 使用 ANPTool 获取 URL 内容
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

                # 记录访问过的 URL 和获取的内容
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
                logger.error(f"使用 ANPTool 获取 URL {url} 时出错: {str(e)}")

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(
                            {
                                "error": f"使用 ANPTool 获取 URL 失败: {url}",
                                "message": str(e),
                            }
                        ),
                    }
                )

class CustomJSONEncoder(JSONEncoder):
    """自定义 JSON 编码器，处理 OpenAI 对象"""

    def default(self, obj):
        # 处理 OpenAI 的对象
        if hasattr(obj, '__dict__'):
            return obj.__dict__
        # 处理其他不可序列化的对象
        try:
            return super().default(obj)
        except TypeError:
            return str(obj)





async def call_llm(prompt: str) -> str | ChatCompletionMessage:
    try:
        llm_client=create_llm_client()
        model_name = os.environ.get("AZURE_OPENAI_MODEL_NAME", "gpt-4")

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


async def main():


    sdk = ANPSDK()

    from anp_open_sdk.anp_sdk_tool import did_create_user, get_user_dir_did_doc_by_did
    # 1. 创建临时用户
    logger.info("步骤1: 创建临时用户")
    temp_user_params = {
        'name': 'Python任务智能体',
        'host': 'localhost',
        'port': 9527,  # 演示在同一台服务器，使用相同端口
        'dir': 'wba',  # 理论上可以自定义，当前由于did 路由的did.json服务在wba/user，所以要保持一致
        'type': 'user'  # 用户可以自定义did 路由的did.json服务在路径，确保和did名称路径一致即可
    }

    did_document = did_create_user(temp_user_params)
    if not did_document:
        logger.error("临时用户创建失败")
        return

    logger.info(f"临时用户创建成功，DID: {did_document['id']}")

    # 创建LocalAgent实例
    python_agent = LocalAgent(sdk,
                            id=did_document['id'],
                            name=temp_user_params['name']
                            )

    # 注册到SDK
    sdk.register_agent(python_agent)
    logger.info(f"临时智能体 {python_agent.name} 注册成功")

    # 3. 为临时智能体注册API服务函数
    logger.info("步骤3: 注册消息监听函数")

    @python_agent.expose_api("/tasks/send", methods=["POST"])
    async def task_receive(request_data, request:Request):
        start = time.time()
        # 检查请求方法，如果是GET方法直接拒绝
        if request.method == "GET":
            return JSONResponse(
                {"error": "GET method not allowed"},
                status_code=405
            )
        try:
            # 先检查 Content-Type
            if request.headers.get("Content-Type") != "application/json":
                return JSONResponse({"error": "请求必须是 JSON 格式"}, status_code=400)

            # 先检查请求体是否为空
            raw_data = await request.body()
            if not raw_data:
                return JSONResponse({"error": "请求体为空"}, status_code=400)

            # 解析 JSON
            body = await request.json()

            def find_message(data):
                """递归查找 'message' 值"""
                if isinstance(data, dict):  # 如果是字典，遍历键值
                    if "message" in data:
                        return data["message"]
                    for value in data.values():
                        result = find_message(value)  # 递归搜索
                        if result:
                            return result
                elif isinstance(data, list):  # 如果是列表，遍历每个元素
                    for item in data:
                        result = find_message(item)
                        if result:
                            return result
                return None  # 如果未找到，返回 None

            message_value = find_message(body)


            message = message_value
            if message is None:
                return JSONResponse(
                    {"error": "Missing 'message' field in your post body"},
                    status_code=400
                )
            logger.info(f"\n远程智能体收到本地大模型发出的任务\n{message}")
            task_text = message if message else ""

            code = await call_llm(task_text)
            if isinstance(code, dict):
                code = json.dumps(code)  # ✅ 如果是字典，则转换为 JSON
            elif hasattr(code, "content"):
                code = code.content  # ✅ 如果是 LLM 对象，则提取文本部分
            elif hasattr(code, "__dict__"):
                code = json.dumps(code.__dict__)  # ✅ 可能是 Python 类实例，转换为字典
            logger.info(f"\n远程智能体完成本地大模型发出的任务\n{code}")
            code = {
                "jsonrpc": "2.0",
                "id": body.get("id"),
                "result": {
                    "code": code
                }}


            return JSONResponse(
                json.loads(json.dumps(code)),
                status_code = 200
            )
        except Exception as e:
            logger.error(f"任务处理失败: {e}")
            return JSONResponse({"error": str(e)}, status_code=500)
        finally:
            logger.info(f"任务耗时: {time.time() - start:.2f}s")


    agent_id = f"http://localhost:9527/wba/user/{python_agent.id}/ad.json"

    # 默认模板内容
    default_template = \
        {
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

    yaml_data = {
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

    json_rpc_methods = []

    for path, methods in yaml_data["paths"].items():
        for method, details in methods.items():
            json_rpc_methods.append({
                "jsonrpc": "2.0",
                "summary": details.get("summary", ""),
                "method": f"{method.upper()} {path}",
                "params": details.get("requestBody", {}).get("content", {}).get("application/json", {}).get("schema", {}).get("properties", {}),
                "result": details.get("responses", {}).get("200", {}).get("content", {}).get("application/json", {}).get("schema", {}).get("properties", {}),
            })

    json_rpc = {
    "jsonrpc": "2.0",
    "summary": "基于自然语言生成代码的服务,在post请求的body部分添加message参数,说明生成代码需求,服务将自动返回结果",
    "method": "generate_code",
      "params": {
        "message":{
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



    import jsonschema
    import json

    # 加载 JSON Schema
    with open("jsonrpc_request_schema.json", "r", encoding="utf-8") as f:
        schema = json.load(f)

    # 进行验证
    try:
        jsonschema.validate(instance=json_rpc, schema=schema)
        print("✅ JSON-RPC 格式符合 Schema 规范!")
    except jsonschema.ValidationError as e:
        print(f"❌ JSON-RPC 格式错误: {e.message}")



    success, did_doc, user_dir = get_user_dir_did_doc_by_did(python_agent.id)
    user_dirs = dynamic_config.get('anp_sdk.user_did_path')
    user_full_path = os.path.join(user_dirs, user_dir)
    # 写入 ad.json 模板文件
    template_ad_path = Path(user_full_path)/"template-ad.json"
    template_ad_path = Path(path_resolver.resolve_path(template_ad_path.as_posix()))
    await template_ad_path.parent.mkdir(parents=True, exist_ok=True)  # 确保目录存在
    # 将default_template写入template_ad_path
    with open(template_ad_path, 'w', encoding='utf-8') as f:
        json.dump(default_template, f, ensure_ascii=False, indent=2)
    logger.info(f"模板文件已写入: {template_ad_path}")

    # 保存 YAML 文件
    template_yaml_path = Path(user_full_path) / "codegen-interface.yaml"
    template_yaml_path = Path(path_resolver.resolve_path(template_yaml_path.as_posix()))
    await template_yaml_path.parent.mkdir(parents=True, exist_ok=True)  # 确保目录存在
    with open(template_yaml_path, "w", encoding="utf-8") as file:
        yaml.dump(yaml_data, file, allow_unicode=True)


    # 保存 JSON RPC 文件
    template_jsonrpc_path = Path(user_full_path) / "codegen-interface.json"
    template_jsonrpc_path = Path(path_resolver.resolve_path(template_jsonrpc_path.as_posix()))
    await template_jsonrpc_path.parent.mkdir(parents=True, exist_ok=True)  # 确保目录存在
    with open(template_jsonrpc_path, "w", encoding="utf-8") as file:
            json.dump(json_rpc, file, indent=2, ensure_ascii=False)

    sdk.register_agent(python_agent)
    sdk_manager = DemoSDKManager()
    sdk_manager.start_server(sdk)
    crawler = ANPToolCrawler(sdk)
    try:


        # 运行爬虫演示
        # 可以自定义参数
        result = await crawler.run_crawler_demo(
            task_input="写个冒泡法排序代码",  # 可以修改为其他任务
            initial_url=f"http://localhost:9527/wba/user/{python_agent.id}/ad.json",  # 可以修改为其他URL
            use_two_way_auth=True,  # 是否使用双向认证
            req_did = None,
            resp_did = python_agent.id
        )
        # 保存结果到文件（可选）
        output_file = "agent_anptool_crawler_result.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2, cls=CustomJSONEncoder)
        logger.info(f"爬取结果已保存到 {output_file}")

        user_data = sdk.user_data_manager.get_user_data_by_name("本田")
        agent1 = LocalAgent(sdk,user_data.did)

        result = await crawler.run_crawler_demo(
            task_input="写个随机数生成代码",  # 可以修改为其他任务
            initial_url=f"http://localhost:9527/wba/user/{python_agent.id}/ad.json",  # 可以修改为其他URL
            use_two_way_auth=True,  # 是否使用双向认证
            req_did=agent1.id,
            resp_did=python_agent.id
        )
        # 保存结果到文件（可选）
        output_file = "agent1_crawler_result.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2, cls=CustomJSONEncoder)
        logger.info(f"爬取结果已保存到 {output_file}")


    except Exception as e:
        logger.error(f"演示过程中发生错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # 5. 清理：删除临时用户
        logger.info("步骤5: 清理临时用户")

        try:

            success, did_doc, user_dir = get_user_dir_did_doc_by_did(python_agent.id)
            if not success:
                logger.error("无法找到刚创建的用户目录")
                return

            temp_user_dir = user_dir
            if python_agent:
                # 从SDK中注销
                sdk.unregister_agent(python_agent.id)
                logger.info(f"临时智能体 {python_agent.name} 已从SDK注销")

            if temp_user_dir:
                # 删除用户目录
                user_dirs = dynamic_config.get('anp_sdk.user_did_path')
                user_full_path = os.path.join(user_dirs, temp_user_dir)

                if os.path.exists(user_full_path):
                    shutil.rmtree(user_full_path)
                    logger.info(f"临时用户目录已删除: {user_full_path}")
                else:
                    logger.warning(f"临时用户目录不存在: {user_full_path}")

            logger.info("临时智能体清理完成")

        except Exception as e:
            logger.error(f"清理临时用户时发生错误: {e}")


def create_llm_client():
    try:
        model_provider = os.environ.get("MODEL_PROVIDER", "azure").lower()


        if model_provider == "azure":
            # Azure OpenAI
            from openai import AsyncAzureOpenAI
            client = AsyncAzureOpenAI(
                api_key=os.environ.get("AZURE_OPENAI_API_KEY"),
                api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2023-05-15"),
                azure_endpoint=os.environ.get("AZURE_OPENAI_ENDPOINT"),
                azure_deployment=os.environ.get("AZURE_OPENAI_DEPLOYMENT"),
            )
            return client
        else:
            logger.error(f"创建LLM客户端失败: 需要 azure配置")
            return None

    except Exception as e:
        logger.error(f"创建LLM客户端失败: {e}")
        return None

if __name__ == "__main__":


    # 运行主函数
    asyncio.run(main())