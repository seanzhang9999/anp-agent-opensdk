import asyncio
import time
import json
from datetime import datetime
from typing import List
from urllib.parse import quote

import requests
import aiofiles
from loguru import logger

from anp_open_sdk.anp_sdk import ANPSDK, LocalAgent
from anp_open_sdk.config.path_resolver import path_resolver
from anp_open_sdk.service.agent_api_call import agent_api_call_post, agent_api_call_get
from anp_open_sdk.service.agent_message_group import agent_msg_group_post, agent_msg_group_members
from anp_open_sdk.service.agent_message_p2p import agent_msg_post

from .step_helper import DemoStepHelper
from .group_runner import DemoGroupRunner, DemoGroupMember


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
            # 运行基础演示
            await self.run_api_demo(agent1, agent2)
            await self.run_message_demo(agent2, agent3, agent1)
            await self.run_group_chat_demo(agent1, agent2, agent3)
            
            # 开发模式特有的功能
            if self.dev_mode:
                await self.run_development_features()
                
            self.step_helper.pause("所有演示完成")
            
        except Exception as e:
            logger.error(f"演示执行过程中发生错误: {e}")
            raise

    async def run_api_demo(self, agent1: LocalAgent, agent2: LocalAgent):
        """API调用演示"""
        self.step_helper.pause("步骤1: 演示API调用")

        # 显示智能体信息
        await self._show_agent_info(agent1, agent2)

        # POST请求演示
        self.step_helper.pause("演示POST请求到/info接口")
        resp = await agent_api_call_post(
            self.sdk, agent1.id, agent2.id, "/info", {"from": agent1.name}
        )
        logger.info(f"{agent1.name}POST调用{agent2.name}的/info接口响应: {resp}")

        # GET请求演示
        self.step_helper.pause("演示GET请求到/info接口")
        resp = await agent_api_call_get(
            self.sdk, agent1.id, agent2.id, "/info", {"from": agent1.name}
        )
        logger.info(f"{agent1.name}GET调用{agent2.name}的/info接口响应: {resp}")

    async def run_message_demo(self, agent2: LocalAgent, agent3: LocalAgent, agent1: LocalAgent):
        """消息发送演示"""
        self.step_helper.pause("步骤2: 演示消息发送")

        logger.info(f"演示：{agent2.name}向{agent3.name}发送消息")
        resp = await agent_msg_post(self.sdk, agent2.id, agent3.id, f"你好，我是{agent2.name}")
        logger.info(f"{agent2.name}向{agent3.name}发送消息响应: {resp}")

        self.step_helper.pause("消息发送完成，观察回复")

        logger.info(f"演示：{agent3.name}向{agent1.name}发送消息")
        resp = await agent_msg_post(self.sdk, agent3.id, agent1.id, f"你好，我是{agent3.name}")
        logger.info(f"{agent3.name}向{agent1.name}发送消息响应: {resp}")
    
    async def run_group_chat_demo(self, agent1: LocalAgent, agent2: LocalAgent, agent3: LocalAgent):
        """群聊功能演示"""
        self.step_helper.pause("步骤3: 演示群聊功能")

        group_id = "demo_group"
        group_url = f"localhost:{self.sdk.port}"

        # 创建群组运行器和成员
        group_runner = DemoGroupRunner(agent1, group_id)
        group_runner.register_group_handlers()

        member2 = DemoGroupMember(agent2)
        member3 = DemoGroupMember(agent3)
        member2.register_group_event_handler()
        member3.register_group_event_handler()

        # 设置群组和发送消息
        await self._setup_group(agent1, agent2, agent3, group_url, group_id)
        await self._demo_group_messages(agent1, agent2, agent3, group_url, group_id)

        # 显示接收到的消息
        message_files = [
            path_resolver.resolve_path(f"{agent.name}_group_messages.json") 
            for agent in [agent1, agent2, agent3]
        ]
        
        for agent, message_file in zip([agent1, agent2, agent3], message_files):
            await self._show_received_messages(agent.name, message_file)

    async def run_development_features(self):
        """开发模式特有功能"""
        self.step_helper.pause("步骤4: 开发模式特有功能演示")
        logger.info("开发模式：运行额外的测试功能...")
        
        # 可以添加开发模式特有的功能
        # 例如：性能测试、错误处理测试、创建新用户等
        await self._run_user_creation_demo()
        await self._run_performance_test()

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

                logger.info(f"{agent.name}的ad.json信息:")
                if isinstance(data, dict):
                    logger.info(f"name: {data.get('name')}")
                    logger.info(f"ad:endpoints: {data.get('ad:endpoints')}")
                else:
                    logger.info(f"响应: {data}")
            except Exception as e:
                logger.error(f"获取{agent.name}信息失败: {e}")

    async def _setup_group(self, agent1: LocalAgent, agent2: LocalAgent,
                           agent3: LocalAgent, group_url: str, group_id: str):
        """设置群组"""
        self.step_helper.pause("建群拉人步骤")
        
        # 创建群组并添加agent1
        action = {"action": "add", "did": agent1.id}
        resp = await agent_msg_group_members(self.sdk, agent1.id, agent1.id, group_url, group_id, action)
        logger.info(f"{agent1.name}创建群组响应: {resp}")

        # 添加其他成员
        for agent in [agent2, agent3]:
            action = {"action": "add", "did": agent.id}
            resp = await agent_msg_group_members(self.sdk, agent1.id, agent1.id, group_url, group_id, action)
            logger.info(f"添加{agent.name}到群组响应: {resp}")

    async def _demo_group_messages(self, agent1, agent2: LocalAgent, agent3: LocalAgent,
                                   group_url: str, group_id: str):
        """演示群组消息"""
        self.step_helper.pause("开始群聊消息演示")
        
        # 清空消息文件
        for agent in [agent1, agent2, agent3]:
            message_file = path_resolver.resolve_path(f"{agent.name}_group_messages.json")
            try:
                async with aiofiles.open(message_file, 'w', encoding='utf-8') as f:
                    await f.write("")
            except Exception as e:
                logger.warning(f"清空{agent.name}消息文件失败: {e}")

        # 启动监听
        task2 = await agent2.start_group_listening(self.sdk, agent1.id, group_url, group_id)
        task3 = await agent3.start_group_listening(self.sdk, agent1.id, group_url, group_id)
        await asyncio.sleep(2)

        try:
            # 发送消息
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            message = f"大家好，我是{agent1.name}，现在是{timestamp}"
            await agent_msg_group_post(self.sdk, agent1.id, agent1.id, group_url, group_id, message)
            logger.info(f"{agent1.name}发送群聊消息")

            await asyncio.sleep(2)

            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            message = f"大家好，我是{agent2.name}，现在是{timestamp}"
            await agent_msg_group_post(self.sdk, agent2.id, agent2.id, group_url, group_id, message)
            logger.info(f"{agent2.name}发送群聊消息")

            await asyncio.sleep(3)

        finally:
            # 取消监听任务
            for task in [task2, task3]:
                task.cancel()
            try:
                await asyncio.gather(task2, task3, return_exceptions=True)
            except Exception as e:
                logger.warning(f"取消监听任务时出现异常: {e}")
            logger.info("群聊监听任务已取消")

    async def _show_received_messages(self, agent_name: str, message_file: str):
        """显示接收到的消息"""
        logger.info(f"\n{agent_name}接收到的群聊消息:")
        try:
            messages = []
            async with aiofiles.open(message_file, 'r', encoding='utf-8') as f:
                async for line in f:
                    if line.strip():
                        messages.append(json.loads(line))

            if messages:
                logger.info(f"批量收到消息:\n{json.dumps(messages, ensure_ascii=False, indent=2)}")
            else:
                logger.info("未收到任何消息")
        except Exception as e:
            logger.error(f"读取消息文件失败: {e}")

    async def _run_user_creation_demo(self):
        """用户创建演示（开发模式）"""
        logger.info("开发模式：演示用户创建功能")
        # 这里可以实现动态创建用户的逻辑
        pass

    async def _run_performance_test(self):
        """性能测试（开发模式）"""
        logger.info("开发模式：运行性能测试")
        
        if len(self.agents) >= 2:
            agent1, agent2 = self.agents[0], self.agents[1]
            
            # 测试API调用性能
            start_time = time.time()
            for i in range(5):
                resp = await agent_api_call_get(
                    self.sdk, agent1.id, agent2.id, "/info", {"test": f"performance_{i}"}
                )
            end_time = time.time()
            
            avg_time = (end_time - start_time) / 5 * 1000
            logger.info(f"API调用平均耗时: {avg_time:.2f}ms")
            
            # 测试消息发送性能
            start_time = time.time()
            for i in range(5):
                resp = await agent_msg_post(
                    self.sdk, agent1.id, agent2.id, f"性能测试消息 {i}"
                )
            end_time = time.time()
            
            avg_time = (end_time - start_time) / 5 * 1000
            logger.info(f"消息发送平均耗时: {avg_time:.2f}ms")