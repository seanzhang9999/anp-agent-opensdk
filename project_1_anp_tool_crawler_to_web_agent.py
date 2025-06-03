#!/usr/bin/env python3
"""
ANP Tool 智能爬虫演示
使用 ANP 协议进行智能体信息爬取，通过大模型自主决定爬取路径
"""
import os
import asyncio
import sys
import json
from json import JSONEncoder
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv
from loguru import logger

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
    def __init__(self,sdk:ANPSDK):
        self.sdk = sdk
        self.agents = []
        self.anp_tool = None





    async def run_crawler_demo(self,
                             task_input: str = "查询北京天津上海今天的天气",
                             initial_url: str = "https://agent-search.ai/ad.json",
                             use_two_way_auth: bool = True):



        try:
            # 尝试加载托管智能体
            agent_anptool = None

            user_data_manager = self.sdk.user_data_manager
            user_data_manager.load_users()
            user_data = user_data_manager.get_user_data_by_name("托管智能体_did:wba:agent-did.com:test:public")

            if user_data:
                agent_anptool = LocalAgent(self.sdk, user_data.did)
                self.sdk.register_agent(agent_anptool)
                logger.info(f"使用托管智能体: {agent_anptool.name}")
            else:
                logger.error("未找到托管智能体，停止")
                return
        except Exception as e:
            logger.warning(f"加载托管智能体失败: {e}，停止")
            return

        # 定义任务
        task = {
            "input": task_input,
            "type": "weather_query",
        }

        # 创建搜索智能体的提示模板
        SEARCH_AGENT_PROMPT_TEMPLATE = """
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

        # 调用通用智能爬虫
        result = await self.anptool_intelligent_crawler(
            anpsdk=self.sdk,
            caller_agent=str(agent_anptool.id),
            target_agent=str(agent_anptool.id), # 对单向认证web 目标id提供一个dummy即可
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
            model_provider = os.environ.get("MODEL_PROVIDER", "openai").lower()
            if model_provider == "openai":
                from openai import AsyncOpenAI
                client = AsyncOpenAI(
                    api_key=os.environ.get("OPENAI_API_KEY"),
                    base_url=os.environ.get("OPENAI_API_BASE_URL", "https://api.openai.com/v1"),
        )
            else:
                logger.error(f"创建LLM客户端失败: 需要 openai配置")
                return {
                    "content": "LLM客户端创建失败: 需要配置 OpenAI",
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

                # 显示模型分析
                if response_message.content:
                    logger.info(f"模型分析:\n{response_message.content}")

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
            body = function_args.get("body")

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

async def main():
    """主函数"""

    sdk = ANPSDK()

    crawler = ANPToolCrawler(sdk)

    try:

        # 运行爬虫演示
        # 可以自定义参数
        result = await crawler.run_crawler_demo(
            task_input="查询北京天津上海今天的天气",  # 可以修改为其他任务
            initial_url="https://agent-search.ai/ad.json",  # 可以修改为其他URL
            use_two_way_auth=True  # 是否使用双向认证
        )
        # 保存结果到文件（可选）
        output_file = "anp_sdk_demo/demo_data/crawler_result.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2, cls=CustomJSONEncoder)
        logger.info(f"爬取结果已保存到 {output_file}")

    except Exception as e:
        logger.error(f"演示过程中发生错误: {e}")
        import traceback
        traceback.print_exc()



if __name__ == "__main__":


    # 运行主函数
    asyncio.run(main())