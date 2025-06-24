import asyncio
import os
import json
from dotenv import load_dotenv

from anp_open_sdk.config import UnifiedConfig

load_dotenv()  # 这会加载项目根目录下的 .env 文件

from typing import List, Dict, Any
from urllib.parse import quote

import requests
import aiofiles
from anp_open_sdk.utils.log_base import  logging as logger

from anp_open_sdk.anp_sdk import ANPSDK, LocalAgent
from anp_open_sdk.service.interaction.agent_api_call import agent_api_call_post, agent_api_call_get
from anp_open_sdk.service.interaction.agent_message_p2p import agent_msg_post
from anp_open_sdk.service.interaction.anp_tool import ANPTool
from .step_helper import DemoStepHelper



from anp_open_sdk_demo.demo_modules.customized_group_member import (
    GroupMemberWithStorage,
    GroupMemberWithStats,
    GroupMemberComplete
)
from anp_open_sdk_demo.demo_modules.customized_group_runner import (
    ChatRoomRunnerWithLogging,
    ModeratedChatRunnerWithLogging
)




class DemoTaskRunner:
    """演示任务运行器"""
    
    def __init__(self, sdk: ANPSDK, agents: List[LocalAgent], step_helper: DemoStepHelper, 
                 dev_mode=False, step_mode=False, fast_mode=False):
        self.sdk = sdk
        self.agents = agents
        self.step_helper = step_helper
        self.dev_mode = dev_mode
        self.step_mode = step_mode
        self.fast_mode = fast_mode

    async def run_all_demos(self):
        """运行所有演示"""
        if len(self.agents) < 3:
            logger.error("智能体不足，无法执行演示")
            return

        agent1, agent2, agent3 = self.agents[0], self.agents[1], self.agents[2]

        try:
            await self.run_anp_tool_crawler_agent_search_ai_ad_jason(agent1, agent2)
            await self.run_api_demo(agent1, agent2)
            await self.run_message_demo(agent2, agent3, agent1)
            await self.run_agent_lifecycle_demo(agent1,agent2,agent3)
            await self.run_hosted_did_demo(agent1)  # 添加托管 DID 演示
            await self.run_group_chat_demo(agent1, agent2,agent3)
            self.step_helper.pause("所有演示完成")
            
        except Exception as e:
            logger.error(f"演示执行过程中发生错误: {e}")
            raise

    async def run_api_demo(self, agent1: LocalAgent, agent2: LocalAgent):
        """API调用演示"""
        self.step_helper.pause("步骤1: 演示API调用")

        # 显示智能体信息
        await self._show_agent_info(agent1, agent2)
        # GET请求演示
        self.step_helper.pause("演示GET请求到/hello接口")
        resp = await agent_api_call_get(
             agent2.id, agent1.id, "/hello", {"from": agent2.name}
        )
        logger.debug(f"{agent2.name}GET调用{agent1.name}的/hello接口响应: {resp}")
        # POST请求演示
        self.step_helper.pause("演示POST请求到/info接口")
        resp = await agent_api_call_post(
            agent1.id, agent2.id, "/info", {"from": agent1.name}
        )
        logger.debug(f"{agent1.name}POST调用{agent2.name}的/info接口响应: {resp}")

        # GET请求演示
        self.step_helper.pause("演示GET请求到/info接口")
        resp = await agent_api_call_get(
            agent1.id, agent2.id, "/info", {"from": agent1.name}
        )
        logger.debug(f"{agent1.name}GET调用{agent2.name}的/info接口响应: {resp}")

    async def run_agent_lifecycle_demo(self, agent1,agent2,agent3):
        # 导入必要的模块
        from anp_open_sdk.anp_sdk_user_data import did_create_user, get_user_dir_did_doc_by_did
        from anp_open_sdk.anp_sdk_agent import LocalAgent
        from anp_open_sdk.config import get_global_config
        import os
        import shutil

        temp_agent = None
        temp_user_dir = None

        try:
            logger.debug("=== 开始消息演示（包含临时用户创建） ===")

            # 1. 创建临时用户
            logger.debug("步骤1: 创建临时用户")
            temp_user_params = {
                'name': '智能体创建删除示范用户',
                'host': 'localhost',
                'port': 9527,  # 演示在同一台服务器，使用相同端口
                'dir': 'wba', # 理论上可以自定义，当前由于did 路由的did.json服务在wba/user，所以要保持一致
                'type': 'user'# 用户可以自定义did 路由的did.json服务在路径，确保和did名称路径一致即可
            }

            did_document = did_create_user(temp_user_params)
            if not did_document:
                logger.error("临时用户创建失败")
                return

            logger.debug(f"临时用户创建成功，DID: {did_document['id']}")

            # 创建LocalAgent实例
            temp_agent = LocalAgent.from_did(did_document['id'])

            # 注册到SDK
            self.sdk.register_agent(temp_agent)
            logger.debug(f"临时智能体 {temp_agent.name} 注册成功")

            # 3. 为临时智能体注册消息监听函数
            logger.debug("步骤3: 注册消息监听函数")


            @temp_agent.register_message_handler("*")
            async def handle_temp_message(msg):
                """临时智能体的消息处理函数"""
                logger.debug(f"[{temp_agent.name}] 收到消息: {msg}")

                # 自动回复消息
                reply_content = f"这是来自临时智能体 {temp_agent.name} 的自动回复,确认收到消息{msg.get('content')}"
                reply_message = {
                    "reply": reply_content,
                }
                return  reply_message

            logger.debug(f"临时智能体 {temp_agent.name} 消息监听函数注册完成")

            # 4. 与其他智能体进行消息交互
            logger.debug("步骤4: 开始消息交互演示")

            # 临时智能体向agent2发送消息
            logger.debug(f"=== {temp_agent.name} -> {agent2.name} ===")
            resp = await agent_msg_post(self.sdk, temp_agent.id, agent2.id, f"你好，我是{temp_agent.name}")
            logger.debug(f"[{temp_agent.name}] 已发送消息给 {agent2.name},响应: {resp}")


            # 临时智能体向agent3发送消息
            logger.debug(f"=== {temp_agent.name} -> {agent3.name} ===")
            resp = await agent_msg_post(self.sdk, temp_agent.id, agent3.id, f"你好，我是{temp_agent.name}")
            logger.debug(f"[{temp_agent.name}] 已发送消息给 {agent3.name},响应: {resp}")


            # agent1向临时智能体发送消息
            logger.debug(f"=== {agent1.name} -> {temp_agent.name} ===")
            resp = await agent_msg_post(self.sdk, agent1.id, temp_agent.id, f"你好，我是{agent1.name}")
            logger.debug(f"[{agent1.name}] 已发送消息给 {temp_agent.name},响应: {resp}")



            # 显示消息交互总结
            logger.debug("=== 消息交互总结 ===")
            logger.debug(f"临时智能体 {temp_agent.name} 成功与以下智能体进行了消息交互:")
            logger.debug(f"  - 发送消息给: {agent2.name}, {agent3.name}")
            logger.debug(f"  - 接收消息来自: {agent1.name}")
            logger.debug("所有消息都已正确处理和回复")

        except Exception as e:
            logger.error(f"消息演示过程中发生错误: {e}")
            import traceback
            logger.error(f"详细错误信息: {traceback.format_exc()}")

        finally:
            # 5. 清理：删除临时用户
            logger.debug("步骤5: 清理临时用户")

            try:

                success, did_doc, user_dir = get_user_dir_did_doc_by_did(temp_agent.id)
                if not success:
                    logger.error("无法找到刚创建的用户目录")
                    return

                temp_user_dir = user_dir
                if temp_agent:
                    # 从SDK中注销
                    self.sdk.unregister_agent(temp_agent.id)
                    logger.debug(f"临时智能体 {temp_agent.name} 已从SDK注销")

                if temp_user_dir:
                    # 删除用户目录
                    config = get_global_config()
                    user_dirs = config.anp_sdk.user_did_path
                    user_full_path = os.path.join(user_dirs, temp_user_dir)

                    if os.path.exists(user_full_path):
                        shutil.rmtree(user_full_path)
                        logger.debug(f"临时用户目录已删除: {user_full_path}")
                    else:
                        logger.warning(f"临时用户目录不存在: {user_full_path}")

                logger.debug("临时智能体清理完成")

            except Exception as e:
                logger.error(f"清理临时用户时发生错误: {e}")

    async def run_hosted_did_demo(self, agent1: LocalAgent):
        """托管 DID 演示"""
        self.step_helper.pause("步骤5: 演示托管 DID 功能")
        
        try:
            # Part 1: 申请托管 DID
            logger.debug("=== Part 1: 申请托管 DID ===")
            self.step_helper.pause("准备申请 hosted_did")
            
            result = await agent1.register_hosted_did(self.sdk)
            if result:
                logger.debug(f"✓ {agent1.name} 申请托管 DID 发送成功")
            else:
                logger.debug(f"✗ {agent1.name} 申请托管 DID 发送失败")
                return
            
            await asyncio.sleep(0.5)
            
            # 服务器查询托管申请状态
            logger.debug("服务器查询托管 DID 申请状态...")
            server_result = await self.sdk.check_did_host_request()
            await asyncio.sleep(2)
            logger.debug(f"服务器处理托管情况: {server_result}")
            
            # 智能体查询自己的托管状态
            agent_result = await agent1.check_hosted_did()
            logger.debug(f"{agent1.name} 托管申请查询结果: {agent_result}")
            
            # Part 2: 托管智能体消息交互演示
            logger.debug("\n=== Part 2: 托管智能体消息交互演示 ===")
            self.step_helper.pause("开始托管智能体消息交互")
            
            # 加载用户数据
            user_data_manager = self.sdk.user_data_manager
            user_data_manager.load_users()
            user_datas = user_data_manager.get_all_users()
            
            # 查找并注册托管智能体
            hosted_agents = find_and_register_hosted_agent(self.sdk, user_datas)

            if not hosted_agents:
                logger.warning("未找到托管智能体，跳过托管消息演示")
                return
            # 跳过 公共托管智能体 找到最近的一个自己申请的托管智能体 因为公共托管智能体没开消息服务
            hosted_agent = next((agent for agent in hosted_agents if agent.parent_did is not None), None)
            hosted_agent.name = "本地托管智能体"

            @hosted_agent.register_message_handler("*")
            async def handle_hosted_message(msg):
                logger.debug(f"[{hosted_agent.name}] 收到消息: {msg}")
                reply_content = f"这是来自托管智能体 {hosted_agent.name} 的自动回复，已收到消息: {msg.get('content')}"
                reply_message = {
                    "reply": reply_content,
                }
                return reply_message

            self.sdk.register_agent(hosted_agent)

            # 查找公共托管智能体
            public_hosted_data = user_data_manager.get_user_data_by_name("托管智能体_did:wba:agent-did.com:test:public")
            if public_hosted_data:
                public_hosted_agent = LocalAgent.from_did(public_hosted_data.did)
                self.sdk.register_agent(public_hosted_agent)
                logger.debug(f"注册公共托管智能体: {public_hosted_agent.name}")
                
                # 托管智能体之间的消息交互
                self.step_helper.pause("托管智能体消息交互演示")
                
                # 公共托管智能体向托管智能体发送消息
                resp = await agent_msg_post(
                    self.sdk, 
                    public_hosted_agent.id, 
                    hosted_agent.id, 
                    f"你好，我是{public_hosted_agent.name}"
                )
                logger.debug(f"{public_hosted_agent.name} -> {hosted_agent.name}: {resp}")
                
                await asyncio.sleep(1)
                
                # 托管智能体向普通智能体发送消息
                resp = await agent_msg_post(
                    self.sdk,
                    hosted_agent.id,
                    agent1.id,
                    f"你好，我是托管智能体 {hosted_agent.name}"
                )
                logger.debug(f"{hosted_agent.name} -> {agent1.name}: {resp}")
                
                await asyncio.sleep(1)
                
                # 普通智能体向托管智能体发送消息
                resp = await agent_msg_post(
                    self.sdk,
                    agent1.id,
                    hosted_agent.id,
                    f"你好托管智能体，我是 {agent1.name}"
                )
                logger.debug(f"{agent1.name} -> {hosted_agent.name}: {resp}")
                
                # 显示托管状态总结
                logger.debug("\n=== 托管 DID 演示总结 ===")
                logger.debug(f"1. {agent1.name} 成功申请了托管 DID")
                logger.debug(f"2. 托管智能体 {hosted_agent.name} 已注册并可以正常通信")
                logger.debug("3. 托管智能体可以与普通智能体和其他托管智能体进行消息交互")
                
                # 清理：注销托管智能体
                self.sdk.unregister_agent(hosted_agent.id)
                if public_hosted_data:
                    self.sdk.unregister_agent(public_hosted_agent.id)
                logger.debug("托管智能体已注销")
                
            else:
                logger.warning("未找到公共托管智能体，跳过部分演示")
                
        except Exception as e:
            logger.error(f"托管 DID 演示过程中发生错误: {e}")
            import traceback
            logger.error(f"详细错误信息: {traceback.format_exc()}")
            
        self.step_helper.pause("托管 DID 演示完成")
        
        
    async def run_message_demo(self, agent2: LocalAgent, agent3: LocalAgent, agent1: LocalAgent):
        """消息发送演示"""
        self.step_helper.pause("步骤2: 演示消息发送")

        logger.debug(f"演示：{agent2.name}向{agent3.name}发送消息")
        resp = await agent_msg_post(self.sdk, agent2.id, agent3.id, f"你好，我是{agent2.name}")
        logger.debug(f"{agent2.name}向{agent3.name}发送消息响应: {resp}")

        self.step_helper.pause("消息发送完成，观察回复")

        logger.debug(f"演示：{agent3.name}向{agent1.name}发送消息")
        resp = await agent_msg_post(self.sdk, agent3.id, agent1.id, f"你好，我是{agent3.name}")
        logger.debug(f"{agent3.name}向{agent1.name}发送消息响应: {resp}")
    
    async def run_anp_tool_crawler_agent_search_ai_ad_jason(self, agent1: LocalAgent, agent2: LocalAgent):
        """ANP工具爬虫演示 - 使用ANP协议进行智能体信息爬取"""
        self.step_helper.pause("步骤3: 演示ANP工具爬虫功能")

        # 引入必要的依赖
        logger.debug("成功导入ANPTool")
        
        
        user_data_manager = self.sdk.user_data_manager
        user_data_manager.load_users()
   
        user_data = user_data_manager.get_user_data_by_name("托管智能体_did:wba:agent-did.com:test:public")
        agent_anptool = LocalAgent.from_did(user_data.did)
        self.sdk.register_agent(agent_anptool)    
            


         # 搜索智能体的URL
        search_agent_url = "https://agent-search.ai/ad.json"
        
        # 定义任务
        task = {
            "input": "查询北京天津上海今天的天气",
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
        # 获取 did_document_path, private_key_path
        did_document_path = user_data.did_doc_path
        private_key_path = user_data.jwt_private_key_file_path
        

        # 调用通用智能爬虫
        result = await self.anptool_intelligent_crawler(
            anpsdk=self.sdk,  # 添加 anpsdk 参数
            caller_agent = str(agent_anptool.id) ,  # 添加发起 agent 参数
            target_agent = str(agent2.id)  ,  # 添加目标 agent 参数
            use_two_way_auth = True,  # 是否使用双向认证
            user_input=task["input"],
            initial_url=search_agent_url,
            prompt_template=SEARCH_AGENT_PROMPT_TEMPLATE,
            did_document_path=did_document_path,
            private_key_path=private_key_path,
            task_type=task["type"],
            max_documents=10,
            agent_name="搜索智能体"
        )

        self.step_helper.pause("搜索智能体演示完成")



    async def _show_agent_info(self, *agents):
        """显示智能体信息"""
        self.step_helper.pause("显示智能体ad.json信息")
        
        for agent in agents:
            host, port = ANPSDK.get_did_host_port_from_did(agent.id)
            user_id = quote(str(agent.id))
            url = f"http://{host}:{port}/wba/user/{user_id}/ad.json"

            try:
                resp = requests.get(url)
                data = resp.json() if resp.status_code == 200 else resp.text

                logger.debug(f"{agent.name}的ad.json信息:")
                if isinstance(data, dict):
                    logger.debug(f"name: {data.get('name')}")
                    logger.debug(f"ad:endpoints: {data.get('ad:endpoints')}")
                else:
                    logger.debug(f"响应: {data}")
            except Exception as e:
                logger.error(f"获取{agent.name}信息失败: {e}")


    async def anptool_intelligent_crawler(
        self,
        user_input: str,
        initial_url: str,
        prompt_template: str,
        did_document_path : str,
        private_key_path : str,
        anpsdk=None,  # 添加 anpsdk 参数
        caller_agent: str = None,  # 添加发起 agent 参数
        target_agent: str = None,  # 添加目标 agent 参数
        use_two_way_auth: bool = False,  # 是否使用双向认证
        task_type: str = "general",
        max_documents: int = 10,
        agent_name: str = "智能爬虫"

    ):
        """
        通用智能爬虫功能 - 使用大模型自主决定爬取路径
        
        参数:
            user_input: 用户输入的任务描述
            initial_url: 初始URL
            prompt_template: 提示模板字符串，需要包含{task_description}和{initial_url}占位符
            task_type: 任务类型
            max_documents: 最大爬取文档数
            agent_name: 代理名称（用于日志显示）
            did_document_path: DID文档路径，如果为None将使用默认路径
            private_key_path: 私钥路径，如果为None将使用默认路径
        
        返回:
            Dict: 包含爬取结果的字典
        """
        self.step_helper.pause(f"启动{agent_name}智能爬取: {initial_url}")
        
        # 引入必要的依赖
        from anp_open_sdk.service.interaction.anp_tool import ANPTool
        
        # 初始化变量
        visited_urls = set()
        crawled_documents = []
        
        # 初始化ANPTool
        logger.debug("初始化ANP工具...")
        anp_tool = ANPTool(
            did_document_path=did_document_path, 
            private_key_path=private_key_path
        )
        
        # 获取初始URL内容
        try:
            logger.debug(f"开始获取初始URL: {initial_url}")
            initial_content = await anp_tool.execute(url=initial_url)
            visited_urls.add(initial_url)
            crawled_documents.append(
                {"url": initial_url, "method": "GET", "content": initial_content}
            )
            logger.debug(f"成功获取初始URL: {initial_url}")
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
            # 尝试使用环境变量创建合适的客户端
            from anp_open_sdk.config import get_global_config
            config = get_global_config()
            api_key = config.secrets.openai_api_key
            base_url = config.llm.api_url
            model_name = os.environ.get("OPENAI_MODEL_NAME", "gpt-4o")
            model_provider = os.environ.get("MODEL_PROVIDER", "openai").lower()
            if model_provider == "openai":
                from openai import AsyncOpenAI
                client = AsyncOpenAI(
                    api_key=api_key,
                    base_url=base_url
                )
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
            logger.debug(f"开始爬取迭代 {current_iteration}/{max_documents}")
            
            # 检查是否已达到最大爬取文档数
            if len(crawled_documents) >= max_documents:
                logger.debug(f"已达到最大爬取文档数 {max_documents}，停止爬取")
                # 添加消息通知模型已达到最大爬取限制
                messages.append({
                    "role": "system",
                    "content": f"你已爬取 {len(crawled_documents)} 个文档，达到最大爬取限制 {max_documents}。请根据获取的信息做出最终总结。",
                })
            
            # 获取模型响应
            self.step_helper.pause(f"迭代 {current_iteration}: 请求模型分析和决策")
            
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
                    logger.debug(f"模型分析:\n{response_message.content}")
                
                # 检查对话是否应该结束
                if not response_message.tool_calls:
                    logger.debug("模型没有请求任何工具调用，结束爬取")
                    break
                    
                # 处理工具调用
                self.step_helper.pause(f"迭代 {current_iteration}: 执行工具调用")
                logger.debug(f"执行 {len(response_message.tool_calls)} 个工具调用")
                
                for tool_call in response_message.tool_calls:

                    if use_two_way_auth:
                        await self.handle_tool_call(
                            tool_call, messages, anp_tool, crawled_documents, visited_urls,
                            anpsdk = anpsdk,caller_agent =caller_agent,target_agent =target_agent,use_two_way_auth =use_two_way_auth)
                    else:
                        await self.handle_tool_call(
                            tool_call, messages, anp_tool, crawled_documents, visited_urls
                        )

                    # 如果已达到最大爬取文档数，停止处理工具调用
                    if len(crawled_documents) >= max_documents:
                        break
                        
                # 如果已达到最大爬取文档数，做出最终总结
                if (len(crawled_documents) >= max_documents and current_iteration < max_documents):
                    logger.debug(f"已达到最大爬取文档数 {max_documents}，做出最终总结")
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
                        response_message = {
                            "content": f"很抱歉，在处理您的请求时遇到了错误。已爬取的文档数: {len(crawled_documents)}。"
                        }
                
                # 退出循环
                break
        
        # 创建结果
        result = {
            "content": response_message.content if hasattr(response_message, "content") else response_message["content"],
            "type": "text",
            "visited_urls": [doc["url"] for doc in crawled_documents],
            "crawled_documents": crawled_documents,
            "task_type": task_type,
            "messages": messages,
        }

        # 显示结果
        self.step_helper.pause(f"{agent_name}智能爬取完成，显示结果")
        logger.debug(f"\n=== {agent_name}响应 ===")
        logger.debug(result["content"])

        logger.debug("\n=== 访问过的URL ===")
        for url in result.get("visited_urls", []):
            logger.debug(url)

        logger.debug(f"\n=== 总共爬取了 {len(result.get('crawled_documents', []))} 个文档 ===")

        return result

        # 定义可用工具
    def get_available_tools(self,anp_tool_instance):
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
        anpsdk = None,  # 添加 anpsdk 参数
        caller_agent: str = None,  # 添加发起 agent 参数
        target_agent: str = None,  # 添加目标 agent 参数
        use_two_way_auth: bool = False  # 是否使用双向认证
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
                        target_agent=target_agent,use_two_way_auth=use_two_way_auth)
                else:
                    result = await anp_tool.execute(
                        url=url, method=method, headers=headers, params=params, body=body
                    )
                logger.debug(f"ANPTool 响应 [url: {url}]")

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

    
    async def run_group_chat_demo(self, agent1: LocalAgent, agent2: LocalAgent, agent3: LocalAgent):
        """使用新的 GroupRunner SDK 运行群聊演示"""
        logger.debug("\n" + "=" * 60)
        logger.debug("🚀 运行增强群聊演示 (使用增强的 GroupMember 与 GroupRunner)")
        logger.debug("=" * 60)
        try:
            # 注册 GroupRunner
            logger.debug("📋 注册 GroupRunner...")
            self.sdk.register_group_runner("sample_group", ChatRoomRunnerWithLogging)
            self.sdk.register_group_runner("moderated_group", ModeratedChatRunnerWithLogging)

            # 创建 GroupMember 客户端（使用不同的扩展类）
            logger.debug("👥 创建群组成员客户端...")
            host1, port1 = ANPSDK.get_did_host_port_from_did(agent1.id)
            host2, port2 = ANPSDK.get_did_host_port_from_did(agent2.id)
            host3, port3 = ANPSDK.get_did_host_port_from_did(agent3.id)

            # 使用不同的扩展 GroupMember
            member1 = GroupMemberWithStorage(agent1.id, port1, enable_storage=True)
            member2 = GroupMemberWithStats(agent2.id, port2)
            member3 = GroupMemberComplete(agent3.id, port3)

            # 设置本地 SDK 优化
            member1.set_local_sdk(self.sdk)
            member2.set_local_sdk(self.sdk)
            member3.set_local_sdk(self.sdk)

            # 定义消息处理器
            async def member1_handler(message):
                logger.debug(f"[{agent1.name}] 📨 {message.sender_id}: {message.content}")

            async def member2_handler(message):
                logger.debug(f"[{agent2.name}] 📨 {message.sender_id}: {message.content}")

            async def member3_handler(message):
                logger.debug(f"[{agent3.name}] 📨 {message.sender_id}: {message.content}")

            # 演示1: 普通群聊
            logger.debug("\n📋 演示1: 普通群聊")
            logger.debug("-" * 40)

            # 加入群组
            logger.debug("👥 加入普通群聊...")
            await member1.join_group("sample_group", name=agent1.name)
            await member2.join_group("sample_group", name=agent2.name)
            await member3.join_group("sample_group", name=agent3.name)

            # 开始监听
            await member1.listen_group("sample_group", member1_handler)
            await member2.listen_group("sample_group", member2_handler)
            await member3.listen_group("sample_group", member3_handler)

            await asyncio.sleep(1)  # 等待监听器启动

            # 发送消息
            logger.debug("\n💬 发送普通群聊消息...")
            await member1.send_message("sample_group", f"Hello from {agent1.name}!")
            await asyncio.sleep(0.5)
            await member2.send_message("sample_group", f"Hi everyone, this is {agent2.name}")
            await asyncio.sleep(0.5)
            await member3.send_message("sample_group", f"Greetings from {agent3.name}!")
            await asyncio.sleep(1)

            # 演示2: 审核群聊
            logger.debug("\n🛡️ 演示2: 审核群聊")
            logger.debug("-" * 40)

            # 加入审核群组
            logger.debug("👥 加入审核群聊...")
            await member1.join_group("moderated_group", name=agent1.name)
            await member2.join_group("moderated_group", name=agent2.name)

            # 开始监听审核群组
            await member1.listen_group("moderated_group", member1_handler)
            await member2.listen_group("moderated_group", member2_handler)
            await asyncio.sleep(1)

            # 发送正常消息
            logger.debug("\n💬 发送正常消息...")
            await member1.send_message("moderated_group", "This is a normal message")
            await asyncio.sleep(0.5)

            # 发送违规消息
            logger.debug("\n🚫 发送违规消息...")
            await member2.send_message("moderated_group", "This message contains spam content")
            await asyncio.sleep(0.5)

            # 发送另一个正常消息
            await member1.send_message("moderated_group", "Back to normal conversation")
            await asyncio.sleep(2)

            # 显示扩展信息
            logger.debug("\n📊 扩展功能信息:")
            logger.debug("-" * 40)
            logger.debug("存储功能 (member1):")
            storage_stats = member1.get_storage_stats()
            logger.debug(json.dumps(storage_stats, indent=2))

            logger.debug("\n统计功能 (member2):")
            stats = member2.get_stats()
            logger.debug(json.dumps(stats, indent=2))

            if isinstance(member3, GroupMemberComplete):
                logger.debug("\n完整功能 (member3):")
                complete_info = member3.get_complete_info()
                logger.debug(json.dumps(complete_info, indent=2))
                
            # 显示群组日志
            logger.debug("\n📋 显示群组运行日志:")
            logger.debug("-" * 40)
            group_log_files = [
                UnifiedConfig.resolve_path("anp_open_sdk_demo/data_tmp_result/group_logs/sample_group_messages.json"),
                UnifiedConfig.resolve_path("anp_open_sdk_demo/data_tmp_result/group_logs/moderated_group_messages.json")
            ]
            for group_name, log_file in zip(["普通群聊", "审核群聊"], group_log_files):
                await self._show_group_logs(group_name, log_file)




            # 显示接收到的消息
            logger.debug("\n📁 显示接收到的群组消息:")
            logger.debug("-" * 40)

            # 获取简化的 agent ID 作为文件名前缀
            agent1_prefix = agent1.id.split(":")[-1] if ":" in agent1.id else agent1.id
            agent2_prefix = agent2.id.split(":")[-1] if ":" in agent2.id else agent2.id
            agent3_prefix = agent3.id.split(":")[-1] if ":" in agent3.id else agent3.id
            # 只显示有存储功能的 agent 的消息
            storage_agents = [(agent1, agent1_prefix, "GroupMemberWithStorage"),
                              (agent2, agent2_prefix, "GroupMemberWithStats"),
                              (agent3, agent3_prefix, "GroupMemberComplete")]

            for agent, agent_prefix, agent_type in storage_agents:
                if agent_type in ["GroupMemberWithStorage", "GroupMemberComplete"]:
                    message_file = UnifiedConfig.resolve_path(f"anp_open_sdk_demo/data_tmp_result/member_messages/{agent_prefix}_group_messages.json")
                    await self._show_received_group_messages(agent.name, message_file)
                else:
                    logger.debug(f"\n📨 {agent.name}: 使用的是 {agent_type} 类，不具备存储功能")

            # 清空所有文件
            await self.clean_demo_data()





            # 清理
            logger.debug("\n🧹 清理群聊连接...")
            member1.stop_listening("sample_group")
            member2.stop_listening("sample_group")
            member3.stop_listening("sample_group")
            member1.stop_listening("moderated_group")
            member2.stop_listening("moderated_group")

            await member1.leave_group("sample_group")
            await member2.leave_group("sample_group")
            await member3.leave_group("sample_group")
            await member1.leave_group("moderated_group")
            await member2.leave_group("moderated_group")

            logger.debug("✅ 增强群聊演示完成")

        except Exception as e:
            logger.debug(f"❌ 增强群聊演示过程中出错: {e}")
            import traceback
            traceback.print_exc()
            
    async def clean_demo_data(self):
        """清空demo_data目录及其子目录中的所有文件，但保留目录结构"""
        self.step_helper.pause("开始清空demo_data目录下的所有文件")
        
        try:
            # 获取demo_data目录路径
            demo_data_path = UnifiedConfig.resolve_path("anp_open_sdk_demo/data_tmp_result")
            if not os.path.exists(demo_data_path):
                logger.warning(f"demo_data目录不存在: {demo_data_path}")
                return
            
            count_removed = 0
            logger.debug(f"正在清空目录: {demo_data_path}")
            
            # 遍历目录及其子目录
            for root, dirs, files in os.walk(demo_data_path):
                # 清空文件
                for file in files:
                    file_path = os.path.join(root, file)
                    try:
                        # 清空文件内容而非删除文件，这样保留文件结构
                        with open(file_path, 'w', encoding='utf-8') as f:
                            f.write("")
                        count_removed += 1
                        logger.debug(f"已清空文件: {file_path}")
                    except Exception as e:
                        logger.error(f"清空文件失败 {file_path}: {e}")
            
            logger.debug(f"清空完成，共处理了 {count_removed} 个文件")
        except Exception as e:
            logger.error(f"清空demo_data时发生错误: {e}")
            import traceback
            logger.error(traceback.format_exc())
        
        self.step_helper.pause("demo_data清空完成")

    async def _show_received_messages(self, agent_name: str, message_file: str):
        """显示接收到的消息"""
        logger.debug(f"\n{agent_name}接收到的群聊消息:")
        try:
            messages = []
            async with aiofiles.open(message_file, 'r', encoding='utf-8') as f:
                async for line in f:
                    if line.strip():
                        messages.append(json.loads(line))

            if messages:
                logger.debug(f"批量收到消息:\n{json.dumps(messages, ensure_ascii=False, indent=2)}")
            else:
                logger.debug("未收到任何消息")
        except Exception as e:
            logger.error(f"读取消息文件失败: {e}")


    async def _show_received_group_messages(self, agent_name: str, message_file: str):
        """显示 agent 接收到的群组消息"""
        try:
            if os.path.exists(message_file):
                with open(message_file, 'r', encoding='utf-8') as f:
                    messages = json.load(f)
                logger.debug(f"\n📨 {agent_name} 接收到的消息 ({len(messages)} 条):")
                for msg in messages:
                    msg_type = msg.get('type', 'unknown')
                    sender = msg.get('sender', 'unknown')
                    content = msg.get('content', '')
                    timestamp = msg.get('timestamp', '')
                    group_id = msg.get('group_id', '')
                    icon = "🔔" if msg_type == "system" else "💬"
                    logger.debug(f"  {icon} [{timestamp}] [{group_id}] {sender}: {content}")
            else:
                logger.debug(f"\n📨 {agent_name}: 没有找到消息文件")
        except Exception as e:
            logger.debug(f"❌ 读取 {agent_name} 的消息文件时出错: {e}")

    async def _show_group_logs(self, group_name: str, log_file: str):
        """显示群组运行日志"""
        try:
            if os.path.exists(log_file):
                with open(log_file, 'r', encoding='utf-8') as f:
                    logs = json.load(f)
                logger.debug(f"\n📋 {group_name} 运行日志 ({len(logs)} 条):")
                for log in logs:
                    log_type = log.get('type', 'unknown')
                    timestamp = log.get('timestamp', '')
                    content = log.get('content', '')
                    if log_type == "join":
                        icon = "🚪➡️"
                    elif log_type == "leave":
                        icon = "🚪⬅️"
                    elif log_type == "message":
                        icon = "💬"
                    elif log_type == "message_blocked":
                        icon = "🚫"
                        content += f" (原因: {log.get('reason', 'unknown')})"
                    else:
                        icon = "📝"
                    logger.debug(f"  {icon} [{timestamp}] {content}")
            else:
                logger.debug(f"\n📋 {group_name}: 没有找到日志文件")
        except Exception as e:
            logger.debug(f"❌ 读取 {group_name} 日志文件时出错: {e}")



def find_and_register_hosted_agent(sdk, user_datas):
        hosted_agents = []
        for user_data in user_datas:
            agent = LocalAgent.from_did(user_data.did)
            if agent.is_hosted_did:
                logger.debug(f"hosted_did: {agent.id}")
                logger.debug(f"parent_did: {agent.parent_did}")
                logger.debug(f"hosted_info: {agent.hosted_info}")
                hosted_agents.append(agent)

        # Return the first hosted agent if any were found, otherwise None
        return hosted_agents if hosted_agents else None