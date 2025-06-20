import asyncio
import json
from datetime import datetime
from json import JSONEncoder

import yaml
import aiohttp
import os
from pathlib import Path
from typing import Dict, Any, Optional

from anp_open_sdk.anp_sdk import ANPSDK
from anp_open_sdk.anp_sdk_agent import LocalAgent
from anp_open_sdk.anp_sdk_user_data import LocalUserDataManager
from utils.log_base import logger

from agent_connect.authentication import DIDWbaAuthHeader
from anp_open_sdk.auth.auth_client import agent_auth_request



class ANPTool:
    name: str = "anp_tool"
    description: str = """使用代理网络协议（ANP）与其他智能体进行交互。
1. 使用时需要输入文档 URL 和 HTTP 方法。
2. 在工具内部，URL 将被解析，并根据解析结果调用相应的 API。
3. 注意：任何使用 ANPTool 获取的 URL 都必须使用 ANPTool 调用，不要直接调用。
"""
    parameters: dict = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "(必填) 代理描述文件或 API 端点的 URL",
            },
            "method": {
                "type": "string",
                "description": "(可选) HTTP 方法，如 GET、POST、PUT 等，默认为 GET",
                "enum": ["GET", "POST", "PUT", "DELETE", "PATCH"],
                "default": "GET",
            },
            "headers": {
                "type": "object",
                "description": "(可选) HTTP 请求头",
                "default": {},
            },
            "params": {
                "type": "object",
                "description": "(可选) URL 查询参数",
                "default": {},
            },
            "body": {
                "type": "object",
                "description": "(可选) POST/PUT 请求的请求体",
            },
        },
        "required": ["url"],
    }

    # 声明 auth_client 字段
    auth_client: Optional[DIDWbaAuthHeader] = None

    def __init__(
        self,
        did_document_path: Optional[str] = None,
        private_key_path: Optional[str] = None,
        **data,
    ):
        """
        使用 DID 认证初始化 ANPTool

        参数:
            did_document_path (str, 可选): DID 文档文件路径。如果为 None，则使用默认路径。
            private_key_path (str, 可选): 私钥文件路径。如果为 None，则使用默认路径。
        """
        super().__init__(**data)

        # 获取当前脚本目录
        current_dir = Path(__file__).parent
        # 获取项目根目录
        base_dir = current_dir.parent

        # 使用提供的路径或默认路径
        if did_document_path is None:
            # 首先尝试从环境变量中获取
            did_document_path = os.environ.get("DID_DOCUMENT_PATH")
            if did_document_path is None:
                # 使用默认路径
                did_document_path = str(base_dir / "use_did_test_public/coder.json")

        if private_key_path is None:
            # 首先尝试从环境变量中获取
            private_key_path = os.environ.get("DID_PRIVATE_KEY_PATH")
            if private_key_path is None:
                # 使用默认路径
                private_key_path = str(
                    base_dir / "use_did_test_public/key-1_private.pem"
                )

        logger.debug(
            f"ANPTool 初始化 - DID 路径: {did_document_path}, 私钥路径: {private_key_path}"
        )

        self.auth_client = DIDWbaAuthHeader(
            did_document_path=did_document_path, private_key_path=private_key_path
        )

    async def execute(
        self,
        url: str,
        method: str = "GET",
        headers: Dict[str, str] = None,
        params: Dict[str, Any] = None,
        body: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        """
        执行 HTTP 请求以与其他代理交互

        参数:
            url (str): 代理描述文件或 API 端点的 URL
            method (str, 可选): HTTP 方法，默认为 "GET"
            headers (Dict[str, str], 可选): HTTP 请求头
            params (Dict[str, Any], 可选): URL 查询参数
            body (Dict[str, Any], 可选): POST/PUT 请求的请求体

        返回:
            Dict[str, Any]: 响应内容
        """

        if headers is None:
            headers = {}
        if params is None:
            params = {}

        logger.debug(f"ANP 请求: {method} {url}")

        # 添加基本请求头
        if "Content-Type" not in headers and method in ["POST", "PUT", "PATCH"]:
            headers["Content-Type"] = "application/json"

        # 添加 DID 认证
        if self.auth_client:
            try:
                auth_headers = self.auth_client.get_auth_header(url)
                headers.update(auth_headers)
            except Exception as e:
                logger.debug(f"获取认证头失败: {str(e)}")

        async with aiohttp.ClientSession() as session:
            # 准备请求参数
            request_kwargs = {
                "url": url,
                "headers": headers,
                "params": params,
            }

            # 如果有请求体且方法支持，添加请求体
            if body is not None and method in ["POST", "PUT", "PATCH"]:
                request_kwargs["json"] = body

            # 执行请求
            http_method = getattr(session, method.lower())

            try:
                async with http_method(**request_kwargs) as response:
                    logger.debug(f"ANP 响应: 状态码 {response.status}")

                    # 检查响应状态
                    if (
                        response.status == 401
                        and "Authorization" in headers
                        and self.auth_client
                    ):
                        logger.warning(
                            "认证失败 (401)，尝试重新获取认证"
                        )
                        # 如果认证失败且使用了 token，清除 token 并重试
                        self.auth_client.clear_token(url)
                        # 重新获取认证头
                        headers.update(
                            self.auth_client.get_auth_header(url, force_new=True)
                        )
                        # 重新执行请求
                        request_kwargs["headers"] = headers
                        async with http_method(**request_kwargs) as retry_response:
                            logger.debug(
                                f"ANP 重试响应: 状态码 {retry_response.status}"
                            )
                            return await self._process_response(retry_response, url)

                    return await self._process_response(response, url)
            except aiohttp.ClientError as e:
                logger.debug(f"HTTP 请求失败: {str(e)}")
                return {"error": f"HTTP 请求失败: {str(e)}", "status_code": 500}

    async def _process_response(self, response, url):
        """处理 HTTP 响应"""
        # 如果认证成功，更新 token
        if response.status == 200 and self.auth_client:
            try:
                self.auth_client.update_token(url, dict(response.headers))
            except Exception as e:
                logger.debug(f"更新 token 失败: {str(e)}")

        # 获取响应内容类型
        content_type = response.headers.get("Content-Type", "").lower()

        # 获取响应文本
        text = await response.text()

        # 根据内容类型处理响应
        if "application/json" in content_type:
            # 处理 JSON 响应
            try:
                result = json.loads(text)
                logger.debug("成功解析 JSON 响应")
            except json.JSONDecodeError:
                logger.warning(
                    "Content-Type 声明为 JSON 但解析失败，返回原始文本"
                )
                result = {"text": text, "format": "text", "content_type": content_type}
        elif "application/yaml" in content_type or "application/x-yaml" in content_type:
            # 处理 YAML 响应
            try:
                result = yaml.safe_load(text)
                logger.debug("成功解析 YAML 响应")
                result = {
                    "data": result,
                    "format": "yaml",
                    "content_type": content_type,
                }
            except yaml.YAMLError:
                logger.warning(
                    "Content-Type 声明为 YAML 但解析失败，返回原始文本"
                )
                result = {"text": text, "format": "text", "content_type": content_type}
        else:
            # 默认返回文本
            result = {"text": text, "format": "text", "content_type": content_type}

        # 添加状态码到结果
        if isinstance(result, dict):
            result["status_code"] = response.status
        else:
            result = {
                "data": result,
                "status_code": response.status,
                "format": "unknown",
                "content_type": content_type,
            }

        # 添加 URL 到结果以便跟踪
        result["url"] = str(url)

        return result

    async def execute_with_two_way_auth(
            self,
            url: str,
            method: str = "GET",
            headers: Dict[str, str] = None,
            params: Dict[str, Any] = None,
            body: Dict[str, Any] = None,
            anpsdk=None,  # 添加 anpsdk 参数
            caller_agent: str = None,  # 添加发起 agent 参数
            target_agent: str = None,  # 添加目标 agent 参数
            use_two_way_auth: bool = False  # 是否使用双向认证
    ) -> Dict[str, Any]:
        """
        使用双向认证执行 HTTP 请求以与其他代理交互

        参数:
            url (str): 代理描述文件或 API 端点的 URL
            method (str, 可选): HTTP 方法，默认为 "GET"
            headers (Dict[str, str], 可选): HTTP 请求头（将传递给 agent_auth_two_way 处理）
            params (Dict[str, Any], 可选): URL 查询参数
            body (Dict[str, Any], 可选): POST/PUT 请求的请求体

        返回:
            Dict[str, Any]: 响应内容
        """

        if headers is None:
            headers = {}
        if params is None:
            params = {}

        logger.debug(f"ANP 双向认证请求: {method} {url}")

        try:
            # 1. 准备完整的 URL（包含查询参数）
            final_url = url
            if params:
                from urllib.parse import urlencode, urlparse, parse_qs, urlunparse
                parsed_url = urlparse(url)
                existing_params = parse_qs(parsed_url.query)

                # 合并现有参数和新参数
                for key, value in params.items():
                    existing_params[key] = [str(value)]

                # 重新构建 URL
                new_query = urlencode(existing_params, doseq=True)
                final_url = urlunparse((
                    parsed_url.scheme,
                    parsed_url.netloc,
                    parsed_url.path,
                    parsed_url.params,
                    new_query,
                    parsed_url.fragment
                ))

            # 2. 准备请求体数据
            request_data = None
            if body is not None and method.upper() in ["POST", "PUT", "PATCH"]:
                request_data = body

            # 3. 调用 agent_auth_two_way（需要传入必要的参数）
            # 注意：这里暂时使用占位符，后续需要根据实际情况调整

            status, response, info, is_auth_pass = await agent_auth_request(
                caller_agent=caller_agent,  # 需要传入调用方智能体ID
                target_agent=target_agent,  # 需要传入目标方智能体ID，如果对方没有ID，可以随便写，因为对方不会响应这个信息
                request_url=final_url,
                method=method.upper(),
                json_data=request_data,
                custom_headers=headers,  # 传递自定义头部给 agent_auth_two_way 处理
                use_two_way_auth= use_two_way_auth
            )

            logger.debug(f"ANP 双向认证响应: 状态码 {status}")

            # 4. 处理响应，保持与原 execute 方法相同的响应格式
            result = await self._process_two_way_response(response, final_url, status, info, is_auth_pass)

            return result

        except Exception as e:
            logger.debug(f"双向认证请求失败: {str(e)}")
            return {
                "error": f"双向认证请求失败: {str(e)}",
                "status_code": 500,
                "url": url
            }

    async def _process_two_way_response(self, response, url, status, info, is_auth_pass):
        """处理双向认证的 HTTP 响应"""

        # 如果 response 已经是处理过的字典格式
        if isinstance(response, dict):
            result = response
        elif isinstance(response, str):
            # 尝试解析为 JSON
            try:
                result = json.loads(response)
                logger.debug("成功解析 JSON 响应")
            except json.JSONDecodeError:
                # 如果不是 JSON，作为文本处理
                result = {
                    "text": response,
                    "format": "text",
                    "content_type": "text/plain"
                }
        else:
            # 其他类型的响应
            result = {
                "data": response,
                "format": "unknown",
                "content_type": "unknown"
            }

        # 添加状态码和其他信息
        if isinstance(result, dict):
            result["status_code"] = status
            result["url"] = str(url)
            result["auth_info"] = info
            result["is_auth_pass"] = is_auth_pass
        else:
            result = {
                "data": result,
                "status_code": status,
                "url": str(url),
                "auth_info": info,
                "is_auth_pass": is_auth_pass,
                "format": "unknown"
            }

        return result


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
                logger.debug(f"使用托管身份智能体进行爬取: {agent.name}")
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
        logger.debug(f"启动{agent_name}智能爬取: {initial_url}")

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
            logger.debug(f"成功获取初始URL: {initial_url}")
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
            logger.debug(f"开始爬取迭代 {current_iteration}/{max_documents}")

            if len(crawled_documents) >= max_documents:
                logger.debug(f"已达到最大爬取文档数 {max_documents}，停止爬取")
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

                logger.debug(f"\n模型思考:\n{response_message.content}")
                if response_message.tool_calls:
                    logger.debug(f"\n模型调用:\n{response_message.tool_calls}")

                if not response_message.tool_calls:
                    logger.debug("模型没有请求任何工具调用，结束爬取")
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
                logger.debug(f"模型发出调用消息：{message_value}")
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

            logger.debug(f"ANPTool 响应 [url: {url}]")

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
