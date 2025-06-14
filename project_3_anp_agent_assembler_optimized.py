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
        self.capabilities = ["code_generation","code_analysis"]
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
# ANP智能体包装器 - 优化版，消除功能重叠
# ============================================================================
class ANPAgentWrapper:
    """ANP智能体包装器 - 优化版，消除功能重叠"""

    def __init__(self, existing_agent: ExistingPythonAgent, sdk: ANPSDK = None, agent_config: dict = None):
        self.existing_agent = existing_agent
        self.sdk = sdk
        self.agent_config = agent_config or {}
        self.anp_agent = None
        self.agent_identity = None
        self.anp_capabilities = []
        self.capability_mapping = {}
        self._default_capabilities_setup = False  # 防止重复设置
        
        logger.info(f"创建ANP包装器: {existing_agent.name}")

    async def assemble_to_anp_network(self) -> bool:
        """将现有智能体组装到ANP网络"""
        try:
            logger.info(f"开始将智能体 {self.existing_agent.name} 组装到ANP网络")
            
            # 1. 分配/发现ANP身份
            self.agent_identity = await self._discover_or_create_identity()
            if not self.agent_identity:
                logger.error("无法分配ANP身份")
                return False
            
            # 2. 创建ANP通信接口
            self.anp_agent = LocalAgent.from_did(self.agent_identity)
            self.anp_agent.name = self.existing_agent.name
            
            # 3. 设置默认通信协议（统一处理）
            await self._setup_default_capabilities()
            
            # 4. 注册到SDK
            if self.sdk:
                self.sdk.register_agent(self.anp_agent)
            
            logger.info(f"✅ 智能体 {self.existing_agent.name} 已组装到ANP网络")
            logger.info(f"   ANP身份: {self.agent_identity}")
            
            return True
            
        except Exception as e:
            logger.error(f"组装到ANP网络失败: {e}")
            return False

    async def _setup_default_capabilities(self):
        """设置默认能力 - 统一处理，避免重复"""
        if self._default_capabilities_setup:
            logger.debug("默认能力已设置，跳过")
            return
        
        logger.info("设置默认通信能力")
        
        # 1. 自动发现并包装现有智能体的主要方法
        default_mappings = [
            ("process_message", "/communicate", "process_message"),
            ("generate_code", "/tasks/send", "generate_code"),
        ]
        
        for method_name, endpoint, capability_name in default_mappings:
            if hasattr(self.existing_agent, method_name):
                self.wrap_capability(capability_name, endpoint, method_name)
                logger.info(f"✅ 自动包装能力: {capability_name}")
        
        # 2. 注册通用消息处理器（只注册一次）
        self._register_universal_message_handler()
        
        self._default_capabilities_setup = True

    def _register_universal_message_handler(self):
        """注册通用消息处理器 - 独立方法，避免重复"""
        if not self.anp_agent:
            logger.warning("ANP智能体未创建，无法注册消息处理器")
            return
        
        @self.anp_agent.register_message_handler("*")
        async def universal_message_handler(message_data):
            """通用消息处理器 - 智能路由"""
            content = message_data.get("content", "")
            result = await self._route_message_intelligently(content)
            return {"anp_result": result}
        
        logger.debug("✅ 注册通用消息处理器")

    async def _route_message_intelligently(self, message: str) -> dict:
        """智能消息路由 - 统一处理逻辑"""
        try:
            # 按优先级尝试不同的处理方法
            method_priority = [
                'process_message',  # 优先使用专门的消息处理方法
                'generate_code',    # 其次是代码生成
            ]
            
            result = None
            used_method = None
            
            for method_name in method_priority:
                if hasattr(self.existing_agent, method_name):
                    result = await self._call_method_safely(method_name, message)
                    used_method = method_name
                    break
            
            if result is None:
                result = f"智能体 {self.existing_agent.name} 收到消息: {message}"
                used_method = "default_response"
            
            return {
                "content": result,
                "agent": self.existing_agent.name,
                "method_used": used_method,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"智能消息路由失败: {e}")
            return {
                "error": str(e),
                "agent": self.existing_agent.name,
                "timestamp": datetime.now().isoformat()
            }

    def wrap_capability(self, capability_name: str, anp_endpoint: str, method_name: str = None, 
                       methods: list = None, response_key: str = None) -> bool:
        """包装现有能力为ANP接口 - 简化版，避免重复逻辑"""
        if method_name is None:
            method_name = capability_name

        if methods is None:
            methods = ["POST"]

        # 验证输入参数
        if not capability_name or not anp_endpoint:
            logger.error("能力名称和端点不能为空")
            return False

        if not hasattr(self.existing_agent, method_name):
            logger.error(f"现有智能体不存在方法: {method_name}")
            return False

        # 检查端点是否已存在
        if anp_endpoint in self.capability_mapping:
            logger.warning(f"端点 {anp_endpoint} 已存在，将覆盖原有映射")

        # 创建能力信息
        capability_info = {
            "name": capability_name,
            "endpoint": anp_endpoint,
            "method_name": method_name,
            "methods": methods,
            "response_key": response_key,
            "original_method": getattr(self.existing_agent, method_name),
            "wrapped_at": datetime.now().isoformat()
        }

        # 存储能力信息
        self.anp_capabilities.append(capability_info)
        self.capability_mapping[anp_endpoint] = capability_info

        # 立即注册（如果ANP智能体已创建）
        if self.anp_agent:
            return self._register_single_capability(capability_info)
        else:
            logger.info(f"📦 包装能力: {capability_name} -> {anp_endpoint} (待注册)")
            return True

    def _register_single_capability(self, capability_info: dict) -> bool:
        """注册单个能力 - 统一注册逻辑"""
        try:
            endpoint = capability_info["endpoint"]
            methods = capability_info["methods"]

            async def wrapped_handler(request_data, request):
                return await self._handle_wrapped_capability(capability_info, request_data, request)

            # 使用 LocalAgent 的 expose_api 方法注册
            self.anp_agent.expose_api(endpoint, wrapped_handler, methods=methods)

            logger.info(f"✅ 注册能力: {capability_info['name']} -> {endpoint}")
            return True

        except Exception as e:
            logger.error(f"注册能力失败 {capability_info['name']}: {e}")
            return False

    def _register_all_capabilities(self) -> int:
        """注册所有已包装的能力 - 批量注册"""
        if not self.anp_agent:
            logger.error("ANP智能体未创建，无法注册能力")
            return 0

        success_count = 0
        for capability_info in self.anp_capabilities:
            if self._register_single_capability(capability_info):
                success_count += 1

        logger.info(f"✅ 批量注册能力完成: {success_count}/{len(self.anp_capabilities)}")
        return success_count

    def set_anp_agent(self, anp_agent):
        """设置ANP智能体 - 简化版，保持向后兼容"""
        self.anp_agent = anp_agent
        
        # 注册所有已包装的能力
        success_count = self._register_all_capabilities()
        
        # 如果还没有设置默认能力，现在设置
        if not self._default_capabilities_setup:
            asyncio.create_task(self._setup_default_capabilities())
        
        return success_count == len(self.anp_capabilities)

    # 其他方法保持不变...
    async def _discover_or_create_identity(self) -> str:
        """发现或创建ANP身份"""
        if not self.sdk:
            logger.error("需要SDK实例来管理身份")
            return None
        
        # 1. 尝试发现现有身份
        current_agent = None
        try:

            current_agent = LocalAgent.from_name(self.existing_agent.name)
        finally:
            if current_agent is not None:
                logger.info(f"发现现有ANP身份: {current_agent.id}")
                return current_agent.id
            else:
                # 2. 创建新身份
                from anp_open_sdk.anp_sdk_user_data import did_create_user

                temp_user_params = {
                    'name': self.existing_agent.name,
                    'host': self.agent_config.get('host', 'localhost'),
                    'port': self.agent_config.get('port', 9527),
                    'dir': self.agent_config.get('dir', 'wba'),
                    'type': self.agent_config.get('type', 'user')
                }

                did_document = did_create_user(temp_user_params)
                if did_document:
                    logger.info(f"创建新ANP身份: {did_document['id']}")
                    return did_document['id']
        return None

    async def _handle_wrapped_capability(self, capability_info, request_data, request):
        """处理包装能力的请求"""
        try:
            capability_name = capability_info["name"]
            method_name = capability_info["method_name"]
            response_key = capability_info.get("response_key")

            logger.info(f"处理包装能力请求: {capability_name}")

            # 提取消息
            message = await self._extract_message_from_request(request_data, request)
            if not message:
                return self._create_error_response("Missing message content", capability_info)

            # 调用原始方法
            result = await self._call_method_safely(method_name, message)

            # 构建响应
            response_data = result
            if response_key:
                response_data = {response_key: result}

            response = {
                "status": "success",
                "capability": capability_name,
                "result": response_data,
                "agent": self.existing_agent.name,
                "timestamp": datetime.now().isoformat(),
                "endpoint": capability_info["endpoint"]
            }

            logger.info(f"✅ 包装能力执行成功: {capability_name}")
            return response

        except Exception as e:
            logger.error(f"包装能力执行失败 {capability_info['name']}: {e}")
            return self._create_error_response(str(e), capability_info)

    async def _extract_message_from_request(self, request_data, request):
        """提取请求消息"""
        # 1. 从request_data提取
        message = self._extract_message_from_data(request_data)
        if message:
            return message
        
        # 2. 从request对象提取
        if hasattr(request, 'json'):
            try:
                request_body = await request.json()
                message = self._extract_message_from_data(request_body)
                if message:
                    return message
            except Exception:
                pass
        
        # 3. 从查询参数提取
        if hasattr(request, 'query_params'):
            query_params = dict(request.query_params)
            message = self._extract_message_from_data(query_params)
            if message:
                return message
        
        return None

    def _extract_message_from_data(self, data):
        """从数据中提取消息"""
        if isinstance(data, str):
            return data
        
        if not isinstance(data, dict):
            return str(data) if data else None
        
        # 尝试多个字段名
        for field in ["message", "content", "task", "prompt", "input", "text"]:
            if field in data and data[field]:
                return data[field]
        
        # 如果没有找到消息，尝试将整个 data 作为参数
        if data:
            # 过滤掉一些系统字段
            filtered_data = {k: v for k, v in data.items()
                             if k not in ['type', 'path', 'method', 'timestamp']}
            if filtered_data:
                return filtered_data

        return None

    async def _call_method_safely(self, method_name: str, message):
        """安全调用方法"""
        try:
            method = getattr(self.existing_agent, method_name)
            logger.debug(f"调用原始方法: {method_name}, 参数: {message}")

            if asyncio.iscoroutinefunction(method):
                # 异步方法
                if message:
                    if isinstance(message, dict) and len(message) > 0:
                        try:
                            return await method(**message)
                        except TypeError:
                            return await method(message)
                    else:
                        return await method(message)
                else:
                    return await method()
            else:
                # 同步方法
                if message:
                    if isinstance(message, dict) and len(message) > 0:
                        try:
                            return method(**message)
                        except TypeError:
                            return method(message)
                    else:
                        return method(message)
                else:
                    return method()

        except Exception as e:
            logger.error(f"调用原始方法失败: {e}")
            raise

    def _create_error_response(self, error_msg: str, capability_info: dict):
        """创建错误响应"""
        return {
            "status": "error",
            "capability": capability_info["name"],
            "error": error_msg,
            "agent": self.existing_agent.name,
            "timestamp": datetime.now().isoformat(),
            "endpoint": capability_info["endpoint"]
        }

    # 配置和管理方法保持不变...
    async def configure_interfaces(self):
        """配置ANP接口"""
        if not self.anp_agent:
            logger.error("需要先组装到ANP网络")
            return False
        
        return await configure_agent_interfaces(self.anp_agent)

    def get_capabilities_info(self) -> dict:
        """获取包装后的能力信息"""
        return {
            "agent_name": self.existing_agent.name,
            "agent_identity": self.agent_identity,
            "has_anp_agent": self.anp_agent is not None,
            "sdk_registered": self.sdk is not None,
            "default_capabilities_setup": self._default_capabilities_setup,
            "original_capabilities": getattr(self.existing_agent, 'capabilities', []),
            "anp_capabilities": [
                {
                    "name": cap["name"],
                    "endpoint": cap["endpoint"],
                    "method": cap["method_name"],
                    "methods": cap["methods"],
                    "response_key": cap.get("response_key"),
                    "wrapped_at": cap["wrapped_at"]
                }
                for cap in self.anp_capabilities
            ],
            "total_wrapped": len(self.anp_capabilities)
        }

    async def cleanup(self):
        """清理资源"""
        if self.sdk and self.anp_agent:
            self.sdk.unregister_agent(self.anp_agent.id)
            logger.info(f"智能体 {self.existing_agent.name} 已从ANP网络注销")


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
        你是一个代码工具的调用者。你的目标是根据用户输入要求去寻找调用工具完成代码任务。

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
            
            logger.info(f"ANPTool 响应 [url: {url}]\n{result}")
            
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
# 智能体组装主要功能函数 - 使用优化后的ANPAgentWrapper
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


async def assemble_existing_agent(sdk: ANPSDK) -> ANPAgentWrapper:
    """步骤2: 使用优化后的ANPAgentWrapper组装现有智能体"""
    logger.info("步骤2: 使用优化后的ANPAgentWrapper组装现有智能体")
    
    # 1. 发现现有智能体
    existing_agent = await discover_existing_agent()
    
    # 2. 创建优化后的包装器
    wrapper = ANPAgentWrapper(
        existing_agent=existing_agent,
        sdk=sdk,
        agent_config={
            'host': 'localhost',
            'port': 9527,
            'dir': 'wba',
            'type': 'user'
        }
    )
    
    # 3. 组装到ANP网络（自动完成身份分配、LocalAgent创建、默认能力包装、SDK注册）
    success = await wrapper.assemble_to_anp_network()
    if not success:
        logger.error("组装失败")
        return None
    
    # 4. 可选：添加额外的能力包装
    wrapper.wrap_capability("analyze_code", "/analyze", "generate_code", response_key="analysis")
    
    # 5. 显示组装信息
    info = wrapper.get_capabilities_info()
    logger.info(f"📋 组装完成:")
    logger.info(f"  - 智能体: {info['agent_name']}")
    logger.info(f"  - ANP身份: {info['agent_identity']}")
    logger.info(f"  - 默认能力设置: {info['default_capabilities_setup']}")
    logger.info(f"  - 包装能力: {info['total_wrapped']} 个")
    
    for cap in info['anp_capabilities']:
        logger.info(f"    - {cap['name']}: {cap['endpoint']} ({', '.join(cap['methods'])})")
    
    return wrapper


async def configure_agent_interfaces(anp_agent: LocalAgent):
    """步骤3: 配置智能体ANP通讯接口"""
    logger.info("步骤3: 配置智能体ANP通讯接口")

    from anp_open_sdk.anp_sdk_user_data import get_user_dir_did_doc_by_did

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
# 测试和演示函数 - 使用优化后的wrapper
# ============================================================================

async def run_assembled_agent_crawler_demo(crawler: ANPToolCrawler, target_wrapper: ANPAgentWrapper, 
                                         task_input: str, output_file: str = "assembled_agent_crawler_result.json"):
    """运行爬虫演示，测试组装后的智能体"""
    logger.info(f"开始测试组装后的智能体: {task_input}")
    
    result = await crawler.run_crawler_demo(
        task_input=task_input,
        initial_url=f"http://localhost:9527/wba/user/{target_wrapper.anp_agent.id}/ad.json",
        use_two_way_auth=True,
        req_did=None,
        resp_did=target_wrapper.anp_agent.id,
        task_type="code_generation"
    )
    
    # 保存结果到文件
    output_path = f"anp_sdk_demo/demo_data/{output_file}"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2, cls=CustomJSONEncoder)
    logger.info(f"组装智能体测试结果已保存到 {output_path}")
    
    return result


async def run_multi_agent_collaboration_demo(sdk: ANPSDK, wrapper: ANPAgentWrapper):
    """运行多智能体协作演示"""
    logger.info("=== 多智能体协作演示 ===")
    
    # 获取另一个智能体进行协作
    user_data = sdk.user_data_manager.get_user_data_by_name("本田")
    if user_data:
        collaborator = LocalAgent.from_did(user_data.did)
        logger.info(f"找到协作智能体: {collaborator.name}")

        # 模拟智能体间协作 - 通过智能爬虫完成任务
        # 创建爬虫实例
        crawler = ANPToolCrawler(sdk)

        # 协作智能体通过爬虫向组装后的智能体请求服务
        task_description = "我需要一个计算斐波那契数列的Python函数，请帮我生成代码"

        try:
            result = await crawler.run_crawler_demo(
                req_did=collaborator.id,  # 请求方是协作智能体
                resp_did=wrapper.anp_agent.id,  # 目标是组装后的智能体
                task_input=task_description,
                initial_url=f"http://localhost:{sdk.port}/wba/user/{wrapper.anp_agent.id}/ad.json",
                use_two_way_auth=True,  # 使用双向认证
            )
            logger.info(f"智能协作结果: {result}")
            return

        except Exception as e:
            logger.error(f"智能协作过程中出错: {e}")
            return

    else:
        logger.info("未找到协作智能体，跳过协作演示")
        return


async def cleanup_assembled_resources(sdk: ANPSDK, wrapper: ANPAgentWrapper):
    """清理组装后的智能体资源"""
    logger.info("步骤4: 清理组装后的智能体资源")
    
    try:
        from anp_open_sdk.anp_sdk_user_data import get_user_dir_did_doc_by_did

        # 获取用户目录
        success, _, user_dir = get_user_dir_did_doc_by_did(wrapper.anp_agent.id)
        if not success:
            logger.error("无法找到用户目录")
            return
            
        # 使用包装器的清理方法
        await wrapper.cleanup()
        
        # 删除用户目录
        user_dirs = dynamic_config.get('anp_sdk.user_did_path')
        user_full_path = os.path.join(user_dirs, user_dir)
        
        if os.path.exists(user_full_path):
            shutil.rmtree(user_full_path)
            logger.info(f"组装智能体目录已删除: {user_full_path}")
            
    except Exception as e:
        logger.error(f"清理组装资源时发生错误: {e}")


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
# 主函数 - 使用优化后的ANPAgentWrapper
# ============================================================================

async def main_assemble_demo():
    """
    主函数：演示如何将现有智能体组装到ANP网络
    
    使用优化后的ANPAgentWrapper，简化组装流程
    """
    logger.info("=== ANP智能体组装演示开始 (使用优化后的ANPAgentWrapper) ===")
    
    # 步骤1: 初始化ANP通讯网络
    logger.info("步骤1: 初始化ANP通讯网络")
    sdk = ANPSDK()
    
    # 步骤2: 使用优化后的ANPAgentWrapper组装现有智能体
    wrapper = await assemble_existing_agent(sdk)
    if not wrapper:
        logger.error("智能体组装失败，退出演示")
        return
    
    # 步骤3: 配置ANP通讯接口
    success = await wrapper.configure_interfaces()
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
            wrapper,
            "生成一个快速排序算法的Python代码，要求有详细注释",
            "assembled_quicksort_demo.json"
        )
        
        # 演示2: 测试另一个任务
        logger.info("\n=== 演示2: ANP网络通讯测试 - 装饰器示例 ===")
        await run_assembled_agent_crawler_demo(
            crawler,
            wrapper,
            "创建一个Python装饰器示例，用于计算函数执行时间",
            "assembled_decorator_demo.json"
        )
            
        logger.info("\n=== 演示3: Web智能体 - 天气查询功能 ===")
        await run_web_agent_crawler_demo(
            crawler,
            "查询北京天津上海今天的天气",
            "https://agent-search.ai/ad.json"
        )
        
        # 演示4: 多智能体协作
        logger.info("\n=== 演示4: 多智能体协作演示 ===")
        await run_multi_agent_collaboration_demo(sdk, wrapper)
        
        logger.info("\n=== 智能体组装演示完成 ===")
        logger.info("核心成果:")
        logger.info("1. 成功将现有智能体组装到ANP网络")
        logger.info("2. 现有智能体获得了ANP通讯能力")
        logger.info("3. 可以通过ANP协议进行智能体间通讯")
        logger.info("4. 保持了原有智能体的核心功能不变")
        logger.info("5. 使用优化后的ANPAgentWrapper简化了组装流程")
        logger.info("6. 消除了重复逻辑，提高了代码质量")
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        
    finally:
        # 步骤6: 清理组装资源
        await cleanup_assembled_resources(sdk, wrapper)
        logger.info("=== ANP智能体组装演示结束 ===")


if __name__ == "__main__":
    # 运行智能体组装演示
    asyncio.run(main_assemble_demo())