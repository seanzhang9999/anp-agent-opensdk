#!/usr/bin/env python3
"""
ANP 智能体组装器 - 改造版本
将现有智能体组装到ANP网络，提供ANP通讯能力

核心理念：发现 → 包装 → 组装
- 发现现有智能体
- 为其配备ANP通讯能力（像配手机一样）
- 建立通讯协议适配
- 组装到ANP网络
- 测试ANP网络通讯

主要功能:
1. 发现并包装现有Python智能体
2. 为现有智能体配备ANP通讯接口
3. 使用智能爬虫测试组装后的智能体
4. 演示智能体间的ANP网络协作
"""

import os
import asyncio
import shutil
import sys
import json
import time
from datetime import datetime
from json import JSONEncoder
from typing import Dict, Any, List, Optional
from urllib.parse import quote

import yaml
from anyio import Path
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from loguru import logger
from openai.types.chat import ChatCompletionMessage
from starlette.responses import JSONResponse

# 加载环境变量
load_dotenv()

# 添加项目路径到系统路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from anp_open_sdk.config.dynamic_config import dynamic_config
from anp_open_sdk.config.path_resolver import path_resolver
from anp_open_sdk.anp_sdk import ANPSDK
from anp_open_sdk.anp_sdk_agent import LocalAgent
from anp_open_sdk.service.anp_tool import ANPTool
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


# ============================================================================
# 现有智能体模拟 - 代表开发者已有的智能体
# ============================================================================

class ExistingPythonAgent:
    """模拟开发者已有的Python代码生成智能体"""
    
    def __init__(self, name: str):
        self.name = name
        self.capabilities = ["code_generation", "code_review", "code_analysis"]
        self.version = "1.0.0"
        self.description = "专业的Python代码生成智能体，支持多种编程任务"
        
    async def generate_code(self, task: str) -> str:
        """现有智能体的核心功能 - 代码生成"""
        logger.info(f"[{self.name}] 正在生成代码: {task}")
        
        # 这里是开发者原有的智能体逻辑
        # 实际场景中，这里可能调用不同的AI模型或使用不同的代码生成算法
        try:
            # 调用现有智能体的代码生成逻辑
            code_result = await self._call_existing_llm_service(task)
            logger.info(f"[{self.name}] 代码生成完成")
            return code_result
        except Exception as e:
            logger.error(f"[{self.name}] 代码生成失败: {e}")
            return f"# [错误] 代码生成失败: {str(e)}"
    
    async def process_message(self, message: str) -> str:
        """现有智能体的消息处理功能"""
        logger.info(f"[{self.name}] 处理消息: {message}")
        
        # 根据消息内容判断处理方式
        if any(keyword in message.lower() for keyword in ["代码", "code", "生成", "写"]):
            return await self.generate_code(message)
        else:
            return f"[{self.name}] 已收到消息: {message}。我是一个代码生成智能体，可以帮您生成Python代码。"
    
    async def review_code(self, code: str) -> str:
        """现有智能体的代码审查功能"""
        logger.info(f"[{self.name}] 正在审查代码")
        return f"[{self.name}] 代码审查完成。代码结构良好，建议添加注释。"
    
    async def _call_existing_llm_service(self, prompt: str) -> str:
        """调用现有智能体的LLM服务"""
        try:
            # 模拟现有智能体可能使用的不同LLM服务
            llm_client = self._create_existing_llm_client()
            if not llm_client:
                return f"# [错误] 无法连接到现有智能体的LLM服务"
                
            model_name = os.environ.get("OPENAI_MODEL_NAME", "gpt-4")

            messages = [
                {"role": "system", "content": f"你是{self.name}，一个专业的Python代码生成助手。请生成高质量的Python代码。"},
                {"role": "user", "content": prompt}
            ]

            completion = await llm_client.chat.completions.create(
                model=model_name,
                messages=messages
            )

            response_message = completion.choices[0].message
            return response_message.content if response_message.content else "# 代码生成完成"
            
        except Exception as e:
            logger.error(f"[{self.name}] LLM服务调用失败: {e}")
            return f"# [错误] LLM服务调用失败: {str(e)}"
    
    def _create_existing_llm_client(self):
        """创建现有智能体的LLM客户端"""
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
                logger.error(f"[{self.name}] 需要配置 OpenAI")
                return None

        except Exception as e:
            logger.error(f"[{self.name}] 创建LLM客户端失败: {e}")
            return None


# ============================================================================
# ANP智能体包装器 - 将现有智能体包装为ANP兼容
# ============================================================================

class ANPAgentWrapper:
    """ANP智能体包装器 - 将现有智能体包装为ANP兼容智能体"""
    
    def __init__(self, existing_agent: ExistingPythonAgent, agent_identity: str):
        self.existing_agent = existing_agent
        self.agent_identity = agent_identity
        self.anp_capabilities = []
        self.capability_mapping = {}
        
        logger.info(f"创建ANP包装器: {existing_agent.name} -> {agent_identity}")
    
    def wrap_capability(self, capability_name: str, anp_endpoint: str, method_name: str = None):
        """包装现有能力为ANP接口"""
        if method_name is None:
            method_name = capability_name
            
        if not hasattr(self.existing_agent, method_name):
            logger.error(f"现有智能体不存在方法: {method_name}")
            return False
            
        capability_info = {
            "name": capability_name,
            "endpoint": anp_endpoint,
            "method_name": method_name,
            "original_method": getattr(self.existing_agent, method_name)
        }
        
        self.anp_capabilities.append(capability_info)
        self.capability_mapping[anp_endpoint] = capability_info
        
        logger.info(f"包装能力: {capability_name} -> {anp_endpoint} -> {method_name}")
        return True
    
    async def handle_anp_request(self, endpoint: str, data: dict) -> dict:
        """处理ANP请求并转发给原有智能体"""
        logger.info(f"处理ANP请求: {endpoint}")
        
        if endpoint not in self.capability_mapping:
            logger.error(f"未找到对应的能力映射: {endpoint}")
            return {"error": f"未找到对应的能力: {endpoint}"}
        
        capability = self.capability_mapping[endpoint]
        
        try:
            # 提取消息内容
            message = data.get("message", "")
            if not message:
                # 尝试从不同字段提取消息
                message = data.get("content", data.get("task", data.get("prompt", "")))
            
            if not message:
                return {"error": "请求中缺少消息内容"}
            
            # 调用原有智能体的方法
            result = await capability["original_method"](message)
            
            logger.info(f"ANP请求处理完成: {endpoint}")
            return {"result": result, "agent": self.existing_agent.name}
            
        except Exception as e:
            logger.error(f"ANP请求处理失败: {e}")
            return {"error": str(e), "agent": self.existing_agent.name}
    
    def get_capabilities_info(self) -> dict:
        """获取包装后的能力信息"""
        return {
            "agent_name": self.existing_agent.name,
            "agent_identity": self.agent_identity,
            "original_capabilities": self.existing_agent.capabilities,
            "anp_capabilities": [
                {
                    "name": cap["name"],
                    "endpoint": cap["endpoint"],
                    "method": cap["method_name"]
                }
                for cap in self.anp_capabilities
            ]
        }


# ============================================================================
# ANP智能体适配器 - 让现有智能体'穿上'ANP通讯能力
# ============================================================================

class ANPAgentAdapter:
    """ANP智能体适配器 - 让现有智能体具备ANP通讯能力"""
    
    def __init__(self, sdk: ANPSDK):
        self.sdk = sdk
        self.adapted_agents = {}
        
    def adapt_agent(self, existing_agent: ExistingPythonAgent, agent_config: dict = None) -> LocalAgent:
        """为现有智能体适配ANP通讯能力"""
        logger.info(f"开始适配智能体: {existing_agent.name}")
        
        agent_config = agent_config or {}
        
        # 1. 分配ANP通讯身份（手机号）
        anp_identity = self._assign_communication_identity(existing_agent, agent_config)
        if not anp_identity:
            logger.error(f"无法为智能体分配ANP身份: {existing_agent.name}")
            return None
            
        # 2. 创建ANP通讯接口（手机）
        communication_interface = LocalAgent(self.sdk, anp_identity, existing_agent.name)
        
        # 3. 建立通讯协议适配（通话协议）
        self._setup_communication_protocol(communication_interface, existing_agent)
        
        # 4. 注册到ANP网络
        self.sdk.register_agent(communication_interface)
        
        # 5. 保存适配关系
        self.adapted_agents[anp_identity] = {
            "original_agent": existing_agent,
            "communication_interface": communication_interface,
            "adapter": self
        }
        
        logger.info(f"智能体 {existing_agent.name} 已适配ANP通讯能力，身份: {anp_identity}")
        return communication_interface
    
    def _assign_communication_identity(self, existing_agent: ExistingPythonAgent, config: dict) -> str:
        """分配通讯身份 - 类似分配手机号码"""
        return self._discover_or_create_identity(existing_agent.name, config)
    
    def _discover_or_create_identity(self, agent_name: str, config: dict) -> str:
        """发现或创建ANP身份"""
        # 1. 首先尝试发现现有身份
        user_data = self.sdk.user_data_manager.get_user_data_by_name(agent_name)
        if user_data:
            logger.info(f"发现现有ANP身份: {user_data.did}")
            return user_data.did
        
        # 2. 如果没有，则创建新的ANP身份
        from anp_open_sdk.anp_sdk_tool import did_create_user
        
        temp_user_params = {
            'name': agent_name,
            'host': config.get('host', 'localhost'),
            'port': config.get('port', 9527),
            'dir': config.get('dir', 'wba'),
            'type': config.get('type', 'user')
        }
        
        did_document = did_create_user(temp_user_params)
        if did_document:
            logger.info(f"为智能体分配新的ANP身份: {did_document['id']}")
            return did_document['id']
            
        return None
    
    def _setup_communication_protocol(self, interface: LocalAgent, original_agent: ExistingPythonAgent):
        """建立通讯协议 - 类似设置手机的通话、短信等功能"""
        
        @interface.expose_api("/communicate", methods=["POST"])
        async def communication_endpoint(request_data, request: Request):
            """通用通讯端点"""
            try:
                body = await request.json()
                message = self._extract_message_from_body(body)
                
                if not message:
                    return JSONResponse({"error": "Missing message content"}, status_code=400)
                
                # 转换ANP协议到原智能体的接口
                result = await self._translate_and_forward(original_agent, message)
                
                response = {
                    "jsonrpc": "2.0",
                    "id": body.get("id"),
                    "result": result
                }
                
                return JSONResponse(response, status_code=200)
                
            except Exception as e:
                logger.error(f"通讯端点处理失败: {e}")
                return JSONResponse({"error": str(e)}, status_code=500)
        
        @interface.expose_api("/tasks/send", methods=["POST"])
        async def task_endpoint(request_data, request: Request):
            """任务处理端点"""
            try:
                body = await request.json()
                message = self._extract_message_from_body(body)
                
                if not message:
                    return JSONResponse({"error": "Missing message content"}, status_code=400)
                
                # 调用原智能体的代码生成能力
                result = await original_agent.generate_code(message)
                
                response = {
                    "jsonrpc": "2.0",
                    "id": body.get("id"),
                    "result": {"code": result}
                }
                
                return JSONResponse(response, status_code=200)
                
            except Exception as e:
                logger.error(f"任务端点处理失败: {e}")
                return JSONResponse({"error": str(e)}, status_code=500)
        
        @interface.register_message_handler("*")
        async def universal_message_handler(message_data):
            """通用消息处理器"""
            content = message_data.get("content", "")
            result = await self._translate_and_forward(original_agent, content)
            return {"anp_result": result}
    
    def _extract_message_from_body(self, body: dict) -> str:
        """从请求体中提取消息内容"""
        def find_message(data):
            """递归查找消息内容"""
            if isinstance(data, dict):
                for key in ["message", "content", "task", "prompt", "input"]:
                    if key in data and data[key]:
                        return data[key]
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
    
    async def _translate_and_forward(self, original_agent: ExistingPythonAgent, message: str) -> dict:
        """翻译ANP消息格式并转发给原智能体"""
        try:
            # 根据不同的智能体框架进行适配
            if hasattr(original_agent, 'process_message'):
                result = await original_agent.process_message(message)
            elif hasattr(original_agent, 'generate_code'):
                result = await original_agent.generate_code(message)
            else:
                result = f"智能体 {original_agent.name} 收到消息: {message}"
            
            return {
                "content": result,
                "agent": original_agent.name,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"消息转发失败: {e}")
            return {
                "error": str(e),
                "agent": original_agent.name,
                "timestamp": datetime.now().isoformat()
            }


# ============================================================================
# ANP 智能爬虫 - 测试组装后的智能体
# ============================================================================

class ANPToolCrawler:
    """ANP Tool 智能爬虫 - 测试组装后的智能体"""

    def __init__(self, sdk: ANPSDK):
        self.sdk = sdk

    async def run_crawler_demo(self, task_input: str, initial_url: str, 
                             use_two_way_auth: bool = True, req_did: str = None, 
                             resp_did: str = None, task_type: str = "code_generation"):
        """运行爬虫演示，测试组装后的智能体"""
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
            user_data_manager = self.sdk.user_data_manager
            user_data_manager.load_users()
            user_data = user_data_manager.get_user_data_by_name("托管智能体_did:wba:agent-did.com:test:public")
            if user_data:
                agent = LocalAgent(self.sdk, user_data.did, user_data.name)
                self.sdk.register_agent(agent)
                logger.info(f"使用托管身份智能体进行爬取: {agent.name}")
                return agent
            else:
                logger.error("未找到托管智能体")
                return None
        else:
            return LocalAgent(self.sdk, req_did)

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

        对于代码生成任务，你需要:
        1. 找到代码生成API端点
        2. 理解如何正确构造请求参数
        3. 发送代码生成请求
        4. 获取并展示生成的代码

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
# 智能体组装主要功能函数 - 发现→包装→组装模式
# ============================================================================

async def discover_existing_agent() -> ExistingPythonAgent:
    """步骤1: 发现现有智能体"""
    logger.info("步骤1: 发现现有智能体")
    
    # 模拟发现开发者已有的智能体
    existing_agent = ExistingPythonAgent("MyPythonCodeAgent")
    
    logger.info(f"发现现有智能体: {existing_agent.name}")
    logger.info(f"智能体能力: {existing_agent.capabilities}")
    logger.info(f"智能体描述: {existing_agent.description}")
    
    return existing_agent


async def discover_or_assign_anp_identity(sdk: ANPSDK, agent_name: str) -> str:
    """步骤2: 发现或分配ANP身份"""
    logger.info(f"步骤2: 为智能体 {agent_name} 发现或分配ANP身份")
    
    # 1. 首先尝试发现现有身份
    user_data = sdk.user_data_manager.get_user_data_by_name(agent_name)
    if user_data:
        logger.info(f"发现现有ANP身份: {user_data.did}")
        return user_data.did
    
    # 2. 如果没有，则创建新的ANP身份
    from anp_open_sdk.anp_sdk_tool import did_create_user
    
    temp_user_params = {
        'name': agent_name,
        'host': 'localhost',
        'port': 9527,
        'dir': 'wba',
        'type': 'user'
    }
    
    did_document = did_create_user(temp_user_params)
    if did_document:
        logger.info(f"为智能体分配新的ANP身份: {did_document['id']}")
        return did_document['id']
    
    return None


async def assemble_existing_agent(sdk: ANPSDK) -> tuple:
    """步骤3: 组装现有智能体到ANP网络"""
    logger.info("步骤3: 开始组装现有智能体到ANP网络")
    
    # 1. 发现现有智能体
    existing_agent = await discover_existing_agent()
    
    # 2. 为现有智能体分配或发现ANP身份
    agent_identity = await discover_or_assign_anp_identity(sdk, existing_agent.name)
    if not agent_identity:
        logger.error("无法为现有智能体分配ANP身份")
        return None, None
    
    # 3. 创建ANP包装器
    wrapper = ANPAgentWrapper(existing_agent, agent_identity)
    
    # 4. 包装现有能力
    wrapper.wrap_capability("generate_code", "/tasks/send", "generate_code")
    wrapper.wrap_capability("process_message", "/communicate", "process_message") 
    wrapper.wrap_capability("review_code", "/review", "review_code")
    
    # 5. 创建LocalAgent作为ANP适配器
    anp_agent = LocalAgent(sdk, agent_identity, existing_agent.name)
    
    # 6. 注册包装后的API处理器
    register_wrapped_api_handlers(anp_agent, wrapper)
    
    # 7. 注册到SDK
    sdk.register_agent(anp_agent)
    
    logger.info(f"智能体 {existing_agent.name} 已成功组装到ANP网络")
    logger.info(f"包装能力信息: {wrapper.get_capabilities_info()}")
    
    return anp_agent, wrapper


def register_wrapped_api_handlers(anp_agent: LocalAgent, wrapper: ANPAgentWrapper):
    """步骤4: 为包装后的智能体注册API处理器"""
    logger.info("步骤4: 注册包装后的API处理器")
    
    @anp_agent.expose_api("/tasks/send", methods=["POST"])
    async def wrapped_task_handler(request_data, request: Request):
        """包装后的任务处理器 - 代码生成"""
        try:
            body = await request.json()
            message = extract_message_from_body(body)
            
            if not message:
                return JSONResponse({"error": "Missing 'message' field"}, status_code=400)
            
            logger.info(f"转发代码生成请求到现有智能体: {message}")
            
            # 转发给现有智能体
            result = await wrapper.handle_anp_request("/tasks/send", {"message": message})
            
            response = {
                "jsonrpc": "2.0",
                "id": body.get("id"),
                "result": {"code": result.get("result", "")}
            }
            
            return JSONResponse(response, status_code=200)
            
        except Exception as e:
            logger.error(f"包装任务处理失败: {e}")
            return JSONResponse({"error": str(e)}, status_code=500)
    
    @anp_agent.expose_api("/communicate", methods=["POST"])
    async def wrapped_communication_handler(request_data, request: Request):
        """包装后的通讯处理器"""
        try:
            body = await request.json()
            message = extract_message_from_body(body)
            
            if not message:
                return JSONResponse({"error": "Missing 'message' field"}, status_code=400)
            
            logger.info(f"转发通讯请求到现有智能体: {message}")
            
            # 转发给现有智能体
            result = await wrapper.handle_anp_request("/communicate", {"message": message})
            
            response = {
                "jsonrpc": "2.0",
                "id": body.get("id"),
                "result": result
            }
            
            return JSONResponse(response, status_code=200)
            
        except Exception as e:
            logger.error(f"包装通讯处理失败: {e}")
            return JSONResponse({"error": str(e)}, status_code=500)
    
    @anp_agent.register_message_handler("text")
    async def wrapped_message_handler(message_data):
        """包装后的消息处理器"""
        content = message_data.get("content", "")
        result = await wrapper.handle_anp_request("/communicate", {"message": content})
        return {"anp_result": result}
    
    logger.info("包装后的API处理器注册完成")


async def configure_agent_interfaces(anp_agent: LocalAgent):
    """步骤5: 配置智能体ANP通讯接口"""
    logger.info("步骤5: 配置智能体ANP通讯接口")
    
    from anp_open_sdk.anp_sdk_tool import get_user_dir_did_doc_by_did
    
    # 获取用户目录
    success, did_doc, user_dir = get_user_dir_did_doc_by_did(anp_agent.id)
    if not success:
        logger.error("无法获取用户目录")
        return False
        
    user_dirs = dynamic_config.get('anp_sdk.user_did_path')
    user_full_path = os.path.join(user_dirs, user_dir)
    
    # 创建接口配置
    agent_id = f"http://localhost:9527/wba/user/{anp_agent.id}/ad.json"
    
    # 创建智能体描述文档
    agent_description = create_assembled_agent_description(anp_agent, agent_id)
    
    # 创建API接口描述
    api_interface = create_assembled_api_interface()
    
    # 创建JSON-RPC接口描述
    jsonrpc_interface = create_assembled_jsonrpc_interface()
    
    # 保存配置文件
    await save_interface_files(user_full_path, agent_description, api_interface, jsonrpc_interface)
    
    logger.info("智能体ANP通讯接口配置完成")
    return True


def create_assembled_agent_description(anp_agent: LocalAgent, agent_id: str):
    """创建组装后智能体的描述文档"""
    return {
        "@context": {
            "@vocab": "https://schema.org/",
            "did": "https://w3id.org/did#",
            "ad": "https://agent-network-protocol.com/ad#"
        },
        "@type": "ad:AgentDescription",
        "@id": agent_id,
        "name": f"ANPSDK组装智能体-{anp_agent.name}",
        "did": anp_agent.id,
        "owner": {
            "@type": "Organization",
            "name": "anp-assembled-agent.local",
            "@id": anp_agent.id
        },
        "description": "通过ANP组装的Python代码生成智能体，具备ANP网络通讯能力，可根据自然语言请求生成、审查和分析Python代码。",
        "version": "1.0.0",
        "created": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "endpoints": [
            f"http://localhost:9527/agent/api/{quote(anp_agent.id)}/tasks/send",
            f"http://localhost:9527/agent/api/{quote(anp_agent.id)}/communicate"
        ],
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
                "url": f"http://localhost:9527/wba/user/{quote(anp_agent.id)}/assembled-interface.json",
                "description": "组装智能体的自然语言接口JSON描述"
            }
        ],
        "ad:capabilities": [
            "code_generation",
            "code_review", 
            "code_analysis",
            "natural_language_processing",
            "anp_communication"
        ]
    }


def create_assembled_api_interface():
    """创建组装后智能体的API接口描述"""
    return {
        "openapi": "3.0.0",
        "info": {
            "title": "Assembled Python Agent API",
            "version": "1.0.0",
            "description": "通过ANP组装的Python智能体API"
        },
        "paths": {
            "/tasks/send": {
                "post": {
                    "summary": "代码生成服务 - 基于自然语言生成Python代码",
                    "description": "发送代码生成任务到组装后的智能体",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "message": {
                                            "type": "string",
                                            "description": "代码生成需求描述"
                                        }
                                    },
                                    "required": ["message"]
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
                                            "code": {
                                                "type": "string",
                                                "description": "生成的Python代码"
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            },
            "/communicate": {
                "post": {
                    "summary": "通用通讯服务 - 与智能体进行自然语言交互",
                    "description": "与组装后的智能体进行通用通讯",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "message": {
                                            "type": "string",
                                            "description": "消息内容"
                                        }
                                    },
                                    "required": ["message"]
                                }
                            }
                        }
                    },
                    "responses": {
                        "200": {
                            "description": "智能体响应",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "result": {
                                                "type": "string",
                                                "description": "智能体的响应内容"
                                            },
                                            "agent": {
                                                "type": "string",
                                                "description": "响应的智能体名称"
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
    }


def create_assembled_jsonrpc_interface():
    """创建组装后智能体的JSON-RPC接口描述"""
    return {
        "jsonrpc": "2.0",
        "summary": "ANP组装智能体 - 代码生成和通用通讯服务",
        "methods": [
            {
                "method": "generate_code",
                "endpoint": "/tasks/send",
                "params": {
                    "message": {
                        "type": "string",
                        "value": "用 Python 生成快速排序算法"
                    }
                },
                "result": {
                    "code": {
                        "type": "string"
                    }
                }
            },
            {
                "method": "communicate",
                "endpoint": "/communicate", 
                "params": {
                    "message": {
                        "type": "string",
                        "value": "你好，请介绍一下你的能力"
                    }
                },
                "result": {
                    "result": {
                        "type": "string"
                    },
                    "agent": {
                        "type": "string"
                    }
                }
            }
        ],
        "meta": {
            "openapi": "3.0.0",
            "info": {
                "title": "Assembled Python Agent API",
                "version": "1.0.0"
            },
            "httpMethod": "POST"
        }
    }


async def save_interface_files(user_full_path: str, agent_description: dict, 
                             api_interface: dict, jsonrpc_interface: dict):
    """保存组装后智能体的接口配置文件"""
    # 保存智能体描述文件
    template_ad_path = Path(user_full_path) / "template-ad.json"
    template_ad_path = Path(path_resolver.resolve_path(template_ad_path.as_posix()))
    await template_ad_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(template_ad_path, 'w', encoding='utf-8') as f:
        json.dump(agent_description, f, ensure_ascii=False, indent=2)
    logger.info(f"组装智能体描述文件已保存: {template_ad_path}")

    # 保存YAML接口文件
    template_yaml_path = Path(user_full_path) / "assembled-interface.yaml"
    template_yaml_path = Path(path_resolver.resolve_path(template_yaml_path.as_posix()))
    await template_yaml_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(template_yaml_path, "w", encoding="utf-8") as file:
        yaml.dump(api_interface, file, allow_unicode=True)
    logger.info(f"组装接口YAML文件已保存: {template_yaml_path}")

    # 保存JSON-RPC接口文件
    template_jsonrpc_path = Path(user_full_path) / "assembled-interface.json"
    template_jsonrpc_path = Path(path_resolver.resolve_path(template_jsonrpc_path.as_posix()))
    await template_jsonrpc_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(template_jsonrpc_path, "w", encoding="utf-8") as file:
        json.dump(jsonrpc_interface, file, indent=2, ensure_ascii=False)
    logger.info(f"组装接口JSON-RPC文件已保存: {template_jsonrpc_path}")


# ============================================================================
# 智能体适配器使用示例
# ============================================================================

async def adapter_demo(sdk: ANPSDK) -> LocalAgent:
    """智能体适配器演示 - 另一种组装方式"""
    logger.info("=== ANP智能体适配器演示开始 ===")
    
    # 1. 创建适配器
    adapter = ANPAgentAdapter(sdk)
    
    # 2. 发现现有智能体
    my_existing_agent = ExistingPythonAgent("MyCodeBot_Adapter")
    
    # 3. 为现有智能体适配ANP通讯能力
    anp_interface = adapter.adapt_agent(my_existing_agent, {
        'host': 'localhost',
        'port': 9527,
        'dir': 'wba',
        'type': 'user'
    })
    
    # 4. 现在智能体可以通过ANP网络通讯了
    logger.info(f"智能体 {my_existing_agent.name} 现在具备ANP通讯能力")
    logger.info(f"ANP身份: {anp_interface.id}")
    
    return anp_interface


# ============================================================================
# 测试和演示函数
# ============================================================================

async def run_assembled_agent_crawler_demo(crawler: ANPToolCrawler, target_agent: LocalAgent, 
                                         task_input: str, output_file: str = "assembled_agent_crawler_result.json"):
    """运行爬虫演示，测试组装后的智能体"""
    logger.info(f"开始测试组装后的智能体: {task_input}")
    
    result = await crawler.run_crawler_demo(
        task_input=task_input,
        initial_url=f"http://localhost:9527/wba/user/{target_agent.id}/ad.json",
        use_two_way_auth=True,
        req_did=None,
        resp_did=target_agent.id,
        task_type="code_generation"
    )
    
    # 保存结果到文件
    output_path = f"anp_sdk_demo/demo_data/{output_file}"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2, cls=CustomJSONEncoder)
    logger.info(f"组装智能体测试结果已保存到 {output_path}")
    
    return result


async def run_multi_agent_collaboration_demo(sdk: ANPSDK, anp_agent: LocalAgent, 
                                           wrapper: ANPAgentWrapper):
    """运行多智能体协作演示"""
    logger.info("=== 多智能体协作演示 ===")
    
    # 获取另一个智能体进行协作
    user_data = sdk.user_data_manager.get_user_data_by_name("本田")
    if user_data:
        collaborator = LocalAgent(sdk, user_data.did,user_data.name)
        logger.info(f"找到协作智能体: {collaborator.name}")
        
        # 模拟智能体间协作
        from anp_open_sdk.service.agent_message_p2p import agent_msg_post
        
        # 协作智能体向组装后的智能体发送消息
        resp = await agent_msg_post(
            sdk, 
            collaborator.id, 
            anp_agent.id, 
            "你好，我需要一个计算斐波那契数列的Python函数"
        )
        logger.info(f"协作消息响应: {resp}")
        
    else:
        logger.info("未找到协作智能体，跳过协作演示")


async def cleanup_assembled_resources(sdk: ANPSDK, anp_agent: LocalAgent):
    """清理组装后的智能体资源"""
    logger.info("步骤6: 清理组装后的智能体资源")
    
    try:
        from anp_open_sdk.anp_sdk_tool import get_user_dir_did_doc_by_did
        
        # 获取用户目录
        success, _, user_dir = get_user_dir_did_doc_by_did(anp_agent.id)
        if not success:
            logger.error("无法找到用户目录")
            return
            
        # 从SDK注销智能体
        sdk.unregister_agent(anp_agent.id)
        logger.info(f"组装智能体 {anp_agent.name} 已从ANP网络注销")
        
        # 删除用户目录
        user_dirs = dynamic_config.get('anp_sdk.user_did_path')
        user_full_path = os.path.join(user_dirs, user_dir)
        
        if os.path.exists(user_full_path):
            shutil.rmtree(user_full_path)
            logger.info(f"组装智能体目录已删除: {user_full_path}")
            
    except Exception as e:
        logger.error(f"清理组装资源时发生错误: {e}")


# ============================================================================
# 辅助函数
# ============================================================================

def extract_message_from_body(body: dict):
    """从请求体中提取message字段"""
    def find_message(data):
        """递归查找 'message' 值"""
        if isinstance(data, dict):
            for key in ["message", "content", "task", "prompt", "input"]:
                if key in data and data[key]:
                    return data[key]
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


# ============================================================================
# 主函数 - 体现组装理念的清晰流程
# ============================================================================

async def main_assemble_demo():
    """
    主函数：演示如何将现有智能体组装到ANP网络
    
    核心理念：发现 → 包装 → 组装
    1. 发现现有智能体
    2. 为其配备ANP通讯能力（像配手机一样）
    3. 建立通讯协议适配
    4. 组装到ANP网络
    5. 测试ANP网络通讯
    """
    logger.info("=== ANP智能体组装演示开始 ===")
    
    # 步骤1: 初始化ANP通讯网络
    logger.info("步骤1: 初始化ANP通讯网络")
    sdk = ANPSDK()
    
    # 步骤2: 发现并组装现有智能体
    anp_agent, wrapper = await assemble_existing_agent(sdk)
    if not anp_agent:
        logger.error("智能体组装失败，退出演示")
        return
    
    # 步骤3: 配置ANP通讯接口
    success = await configure_agent_interfaces(anp_agent)
    if not success:
        logger.error("ANP通讯接口配置失败，退出演示")
        return
    
    # 步骤4: 启动ANP通讯服务
    logger.info("步骤4: 启动ANP通讯服务")
    sdk_manager = DemoSDKManager()
    sdk_manager.start_server(sdk)
    
    # 步骤5: 测试ANP网络通讯
    logger.info("步骤5: 测试ANP网络通讯")
    crawler = ANPToolCrawler(sdk)
    
    try:
        # 演示1: 通过ANP网络调用组装后的智能体 - 快速排序
        logger.info("\n=== 演示1: ANP网络通讯测试 - 快速排序算法 ===")
        await run_assembled_agent_crawler_demo(
            crawler,
            anp_agent,
            "生成一个快速排序算法的Python代码，要求有详细注释",
            "assembled_quicksort_demo.json"
        )
        
        # 演示2: 测试不同类型的代码生成 - 数据结构
        logger.info("\n=== 演示2: ANP网络通讯测试 - 数据结构实现 ===")
        await run_assembled_agent_crawler_demo(
            crawler,
            anp_agent,
            "实现一个Python链表类，包含增删改查功能",
            "assembled_linkedlist_demo.json"
        )
        
        # 演示3: 测试智能体适配器模式
        logger.info("\n=== 演示3: 智能体适配器模式演示 ===")
        adapter_agent = await adapter_demo(sdk)
        if adapter_agent:
            await run_assembled_agent_crawler_demo(
                crawler,
                adapter_agent,
                "创建一个Python装饰器示例",
                "adapter_decorator_demo.json"
            )
        
        # 演示4: 多智能体协作
        logger.info("\n=== 演示4: 多智能体协作演示 ===")
        await run_multi_agent_collaboration_demo(sdk, anp_agent, wrapper)
        
        logger.info("\n=== 智能体组装演示完成 ===")
        logger.info("核心成果:")
        logger.info("1. 成功将现有智能体组装到ANP网络")
        logger.info("2. 现有智能体获得了ANP通讯能力")
        logger.info("3. 可以通过ANP协议进行智能体间通讯")
        logger.info("4. 保持了原有智能体的核心功能不变")
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        
    finally:
        # 步骤6: 清理组装资源
        await cleanup_assembled_resources(sdk, anp_agent)
        logger.info("=== ANP智能体组装演示结束 ===")



async def run_web_agent_crawler_demo(crawler: ANPToolCrawler, 
                                   task_input: str = "查询北京天津上海今天的天气",
                                   initial_url: str = "https://agent-search.ai/ad.json"):
    """运行Web智能体爬虫演示 - 集成自project_1"""
    logger.info(f"=== Web智能体查询演示 ===")
    logger.info(f"查询任务: {task_input}")
    logger.info(f"目标URL: {initial_url}")
    
    result = await crawler.run_crawler_demo(
        task_input=task_input,
        initial_url=initial_url,
        use_two_way_auth=True,
        req_did=None,  # 使用托管身份
        resp_did=None,  # Web智能体不需要特定目标DID
        task_type="weather_query"
    )
    
    # 保存结果到文件
    output_file = "anp_sdk_demo/demo_data/web_agent_crawler_result.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2, cls=CustomJSONEncoder)
    logger.info(f"Web智能体查询结果已保存到 {output_file}")
    
    return result


async def run_information_search_demo(crawler: ANPToolCrawler,
                                    task_input: str = "搜索人工智能最新发展趋势",
                                    initial_url: str = "https://agent-search.ai/ad.json"):
    """运行信息搜索演示"""
    logger.info(f"=== 信息搜索演示 ===")
    logger.info(f"搜索任务: {task_input}")
    
    result = await crawler.run_crawler_demo(
        task_input=task_input,
        initial_url=initial_url,
        use_two_way_auth=True,
        req_did=None,
        resp_did=None,
        task_type="information_search"
    )
    
    # 保存结果到文件
    output_file = "anp_sdk_demo/demo_data/information_search_result.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2, cls=CustomJSONEncoder)
    logger.info(f"信息搜索结果已保存到 {output_file}")
    
    return result


async def run_hybrid_agent_collaboration_demo(crawler: ANPToolCrawler, 
                                            local_agent: LocalAgent):
    """运行混合智能体协作演示 - 本地智能体 + Web智能体"""
    logger.info("=== 混合智能体协作演示 ===")
    
    # 场景1: 本地代码生成 + Web天气查询
    logger.info("\n--- 场景1: 代码生成 + 天气查询 ---")
    
    # 1. 先用本地智能体生成天气查询代码
    code_result = await run_assembled_agent_crawler_demo(
        crawler,
        local_agent,
        "生成一个Python函数，用于调用天气API查询指定城市的天气信息",
        "hybrid_weather_code_demo.json"
    )
    
    # 2. 再用Web智能体查询实际天气
    weather_result = await run_web_agent_crawler_demo(
        crawler,
        "查询北京今天的天气情况",
        "https://agent-search.ai/ad.json"
    )
    
    # 3. 组合结果
    hybrid_result = {
        "scenario": "code_generation_with_weather_query",
        "local_agent_result": code_result,
        "web_agent_result": weather_result,
        "collaboration_summary": "本地智能体生成了天气查询代码，Web智能体提供了实际天气数据"
    }
    
    # 保存组合结果
    with open("anp_sdk_demo/demo_data/hybrid_collaboration_demo.json", 'w', encoding='utf-8') as f:
        json.dump(hybrid_result, f, ensure_ascii=False, indent=2, cls=CustomJSONEncoder)
    
    logger.info("混合协作演示完成")
    return hybrid_result


# ============================================================================
# 扩展ANPToolCrawler以支持更多Web查询场景
# ============================================================================

class EnhancedANPToolCrawler(ANPToolCrawler):
    """增强版ANP工具爬虫 - 支持更多Web查询场景"""
    
    async def run_multi_web_query_demo(self, tasks: list):
        """运行多个Web查询任务"""
        logger.info("=== 多Web查询任务演示 ===")
        
        results = []
        for i, task in enumerate(tasks, 1):
            logger.info(f"\n--- 任务{i}: {task['description']} ---")
            
            result = await self.run_crawler_demo(
                task_input=task['input'],
                initial_url=task.get('url', 'https://agent-search.ai/ad.json'),
                use_two_way_auth=True,
                req_did=None,
                resp_did=None,
                task_type=task.get('type', 'general_query')
            )
            
            result['task_description'] = task['description']
            results.append(result)
            
            # 任务间间隔
            await asyncio.sleep(1)
        
        # 保存所有结果
        output_file = "anp_sdk_demo/demo_data/multi_web_query_results.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2, cls=CustomJSONEncoder)
        
        logger.info(f"多Web查询结果已保存到 {output_file}")
        return results
    
    def _create_information_search_prompt_template(self):
        """创建信息搜索提示模板"""
        return """
        你是一个智能信息搜索工具。你的目标是通过访问各种Web智能体来搜索和汇总信息。

        ## 当前任务
        {task_description}

        ## 重要提示
        1. 你将收到一个初始URL（{initial_url}），这是一个智能体描述文件。
        2. 你需要理解这个智能体的搜索能力和API使用方法。
        3. 你需要像智能搜索引擎一样发现和访问相关的信息源。
        4. 你可以使用anp_tool来获取任何URL的内容。
        5. 重点关注信息的准确性和时效性。
        6. 你需要自主决定搜索路径，不要等待用户指令。
        7. 最多可以访问10个不同的信息源。

        ## 搜索策略
        1. 首先获取初始智能体的能力描述。
        2. 识别与搜索任务相关的API端点。
        3. 构建合适的搜索请求。
        4. 分析搜索结果的可靠性。
        5. 如果需要，访问更多相关信息源。
        6. 汇总和总结所有找到的信息。

        对于信息搜索任务，你需要:
        1. 找到信息搜索API端点
        2. 构造准确的搜索查询
        3. 发送搜索请求
        4. 分析和筛选搜索结果
        5. 提供准确、全面的信息摘要

        提供详细的信息和清晰的解释，包括信息来源的可靠性评估。
        """


# ============================================================================
# 更新主函数以包含Web查询功能
# ============================================================================

async def main_assemble_demo_with_web():
    """
    增强版主函数：演示智能体组装 + Web查询的完整流程
    
    核心功能:
    1. 组装本地智能体到ANP网络
    2. 测试本地智能体ANP通讯
    3. 测试Web智能体查询功能
    4. 演示混合智能体协作
    """
    logger.info("=== ANP智能体组装 + Web查询演示开始 ===")
    
    # 步骤1-4: 组装本地智能体（与原版相同）
    logger.info("步骤1-4: 组装本地智能体到ANP网络")
    sdk = ANPSDK()
    
    anp_agent, wrapper = await assemble_existing_agent(sdk)
    if not anp_agent:
        logger.error("智能体组装失败，退出演示")
        return
    
    success = await configure_agent_interfaces(anp_agent)
    if not success:
        logger.error("ANP通讯接口配置失败，退出演示")
        return
    
    sdk_manager = DemoSDKManager()
    sdk_manager.start_server(sdk)
    
    # 步骤5: 创建增强版爬虫
    logger.info("步骤5: 创建增强版ANP爬虫")
    crawler = EnhancedANPToolCrawler(sdk)
    
    try:
        # ===== 本地智能体测试 =====
        logger.info("\n" + "="*60)
        logger.info("本地智能体ANP通讯测试")
        logger.info("="*60)
        
        # 演示1: 本地智能体 - 算法代码生成
        await run_assembled_agent_crawler_demo(
            crawler,
            anp_agent,
            "生成一个Python二分查找算法，包含详细注释和测试用例",
            "local_binary_search_demo.json"
        )
        
        # ===== Web智能体查询测试 =====
        logger.info("\n" + "="*60)
        logger.info("Web智能体查询测试")
        logger.info("="*60)
        
        # 演示2: Web智能体 - 天气查询
        await run_web_agent_crawler_demo(
            crawler,
            "查询北京、上海、广州今天的天气情况，包括温度、湿度和空气质量",
            "https://agent-search.ai/ad.json"
        )
        
        # 演示3: Web智能体 - 信息搜索
        await run_information_search_demo(
            crawler,
            "搜索2024年人工智能领域的最新突破和发展趋势"
        )
        
        # 演示4: 多Web查询任务
        web_tasks = [
            {
                "description": "科技新闻查询",
                "input": "查询最新的科技新闻和创新动态",
                "type": "news_query"
            },
            {
                "description": "股市信息查询", 
                "input": "查询今日股市行情和重要财经新闻",
                "type": "finance_query"
            },
            {
                "description": "学术论文搜索",
                "input": "搜索关于机器学习最新研究论文",
                "type": "academic_search"
            }
        ]
        
        await crawler.run_multi_web_query_demo(web_tasks)
        
        # ===== 混合智能体协作演示 =====
        logger.info("\n" + "="*60)
        logger.info("混合智能体协作演示")
        logger.info("="*60)
        
        # 演示5: 本地智能体 + Web智能体协作
        await run_hybrid_agent_collaboration_demo(crawler, anp_agent)
        
        # 演示6: 智能体适配器 + Web查询
        logger.info("\n--- 适配器模式 + Web查询 ---")
        adapter_agent = await adapter_demo(sdk)
        if adapter_agent:
            # 先让适配器智能体生成数据分析代码
            await run_assembled_agent_crawler_demo(
                crawler,
                adapter_agent,
                "生成一个Python数据分析脚本，用于分析股票价格趋势",
                "adapter_data_analysis_demo.json"
            )
            
            # 再查询实际的股市数据
            await run_information_search_demo(
                crawler,
                "获取苹果公司(AAPL)最近一周的股票价格数据"
            )
        
        # ===== 演示总结 =====
        logger.info("\n" + "="*60)
        logger.info("演示完成总结")
        logger.info("="*60)
        logger.info("✅ 成功完成的功能:")
        logger.info("1. 本地智能体组装到ANP网络")
        logger.info("2. 本地智能体ANP通讯测试")
        logger.info("3. Web智能体天气查询")
        logger.info("4. Web智能体信息搜索")
        logger.info("5. 多Web查询任务批处理")
        logger.info("6. 混合智能体协作（本地+Web）")
        logger.info("7. 智能体适配器模式测试")
        logger.info("\n🚀 ANP网络现在支持:")
        logger.info("   • 本地智能体间通讯")
        logger.info("   • Web智能体查询")
        logger.info("   • 混合模式协作")
        logger.info("   • 多任务并行处理")
        
    except Exception as e:
        logger.error(f"演示过程中发生错误: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        # 步骤6: 清理资源
        await cleanup_assembled_resources(sdk, anp_agent)
        logger.info("\n=== ANP智能体组装 + Web查询演示结束 ===")


# ============================================================================
# 更新ANPToolCrawler以支持不同任务类型的提示模板
# ============================================================================

def _create_enhanced_prompt_template(task_type: str):
    """根据任务类型创建对应的提示模板"""
    
    base_template = """
    你是一个通用智能网络数据探索工具。你的目标是通过递归访问各种数据格式来完成特定任务。

    ## 当前任务
    {task_description}

    ## 重要提示
    1. 你将收到一个初始URL（{initial_url}），这是一个智能体描述文件。
    2. 你需要理解这个智能体的结构、功能和API使用方法。
    3. 你需要像网络爬虫一样持续发现和访问新的URL和API端点。
    4. 你可以使用anp_tool来获取任何URL的内容。
    5. 此工具可以处理各种响应格式。
    6. 你需要自己决定爬取路径，不要等待用户指令。
    7. 注意：你最多可以爬取10个URL。
    """
    
    task_specific = {
        "weather_query": """
        对于天气查询任务，你需要:
        1. 找到天气查询API端点
        2. 理解如何正确构造请求参数（如城市名、日期等）
        3. 发送天气查询请求
        4. 获取并展示天气信息
        """,
        
        "information_search": """
        对于信息搜索任务，你需要:
        1. 找到信息搜索API端点
        2. 构造准确的搜索查询参数
        3. 发送搜索请求
        4. 分析和筛选搜索结果
        5. 提供准确、全面的信息摘要
        """,
        
        "news_query": """
        对于新闻查询任务，你需要:
        1. 找到新闻查询API端点
        2. 设置合适的新闻类别和时间范围
        3. 发送新闻查询请求
        4. 获取最新、相关的新闻信息
        """,
        
        "finance_query": """
        对于财经查询任务，你需要:
        1. 找到财经数据API端点
        2. 构造股票、市场查询参数
        3. 发送财经数据请求
        4. 获取准确的财经信息和市场数据
        """,
        
        "academic_search": """
        对于学术搜索任务，你需要:
        1. 找到学术搜索API端点
        2. 构造学术关键词和搜索条件
        3. 发送学术论文搜索请求
        4. 获取相关的学术研究信息
        """
    }
    
    return base_template + task_specific.get(task_type, task_specific["information_search"])

if __name__ == "__main__":
    # 运行智能体组装演示
    asyncio.run(main_assemble_demo_with_web())
    asyncio.run(main_assemble_demo())