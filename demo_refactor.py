#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Copyright 2024 ANP Open SDK Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""ANP SDK 演示程序

这个程序演示了如何使用ANP SDK进行基本操作：
1. 初始化SDK和智能体
2. 注册API和消息处理器
3. 启动服务器
4. 演示智能体之间的消息和API调用
"""
import os
import sys
import time
import json
import asyncio
import threading
from datetime import datetime
from typing import List, Optional, Dict, Any
from urllib.parse import quote

import requests
import aiofiles
from colorama import init, Fore, Style
from loguru import logger

from anp_open_sdk.anp_sdk import ANPSDK, LocalAgent
from anp_open_sdk.config.dynamic_config import dynamic_config
from anp_open_sdk.config.path_resolver import path_resolver
from anp_open_sdk.service.agent_api_call import agent_api_call_post, agent_api_call_get
from anp_open_sdk.service.agent_message_group import agent_msg_group_post, agent_msg_group_members
from anp_open_sdk.service.agent_message_p2p import agent_msg_post
from anp_open_sdk.service.local_agent_accelerator import LocalAgentAccelerator

# 初始化 colorama
init()


class StepModeHelper:
    """步骤模式辅助类，用于演示过程中的暂停和提示"""

    def __init__(self, step_mode: bool = False):
        self.step_mode = step_mode

    def pause(self, step_name: str = "", step_id: str = None):
        """在步骤模式下暂停并等待用户确认"""
        if step_id is not None:
            step_name = self._load_helper_text(step_id=step_id)

        if self.step_mode:
            input(f"{Fore.GREEN}--- {step_name} ---{Style.RESET_ALL} "
                  f"{Fore.YELLOW}按任意键继续...{Style.RESET_ALL}")

    def _load_helper_text(self, step_id: str, lang: str = None) -> str:
        """从helper.json文件中读取帮助内容"""
        if lang is None:
            lang = dynamic_config.get("anp_sdk.helper_lang", "zh")

        import os
        current_dir = os.path.dirname(os.path.abspath(__file__))
        helper_file = os.path.join(current_dir, 'helper.json')

        try:
            with open(helper_file, 'r', encoding='utf-8') as f:
                helper_data = json.load(f)
            return helper_data.get(str(step_id), {}).get(lang, "")
        except Exception as e:
            logger.error(f"读取帮助文件时发生错误: {e}")
            return ""


class AgentLoader:
    """智能体加载器"""

    @staticmethod
    def load_demo_agents(sdk: ANPSDK) -> List[LocalAgent]:
        """批量加载本地DID用户并实例化LocalAgent"""
        user_data_manager = sdk.user_data_manager

        # 从配置中获取demo智能体的DID列表
        agent_cfg = dynamic_config.get('anp_sdk.agent', {})
        agent_names = [
            agent_cfg.get('demo_agent1'),
            agent_cfg.get('demo_agent2'),
            agent_cfg.get('demo_agent3')
        ]

        agents = []
        for agent_name in agent_names:
            if not agent_name:
                continue

            user_data = user_data_manager.get_user_data_by_name(agent_name)
            if user_data:
                agent = LocalAgent(sdk, id=user_data.did, name=user_data.name)
                agent.name = user_data.agent_cfg.get('name', user_data.user_dir)
                agents.append(agent)
            else:
                logger.warning(f'未找到预设名字={agent_name} 的用户数据')

        return agents

    @staticmethod
    def find_hosted_agent(sdk: ANPSDK, user_datas) -> Optional[LocalAgent]:
        """查找并返回托管DID智能体"""
        for user_data in user_datas:
            agent = LocalAgent(sdk, user_data.did)
            if agent.is_hosted_did:
                logger.info(f"hosted_did: {agent.id}")
                logger.info(f"parent_did: {agent.parent_did}")
                logger.info(f"hosted_info: {agent.hosted_info}")
                return agent
        return None


class APIHandlerRegistry:
    """API处理器注册管理"""

    @staticmethod
    def register_api_handlers(agents: List[LocalAgent]) -> None:
        """为智能体注册API处理器"""
        if len(agents) < 2:
            logger.warning("智能体数量不足，无法注册所有API处理器")
            return

        agent1, agent2 = agents[0], agents[1]

        # agent1 的API处理器
        @agent1.expose_api("/hello", methods=["GET"])
        def hello_api(request):
            return {
                "msg": f"{agent1.name}的/hello接口收到请求:",
                "param": request.get("params")
            }

        # agent2 的API处理器
        def info_api(request):
            return {
                "msg": f"{agent2.name}的/info接口收到请求:",
                "data": request.get("params")
            }

        agent2.expose_api("/info", info_api, methods=["POST", "GET"])


class MessageHandlerRegistry:
    """消息处理器注册管理"""

    @staticmethod
    def register_message_handlers(agents: List[LocalAgent]) -> None:
        """为智能体注册消息处理器"""
        if len(agents) < 3:
            logger.warning("智能体数量不足，无法注册所有消息处理器")
            return

        agent1, agent2, agent3 = agents[0], agents[1], agents[2]

        # agent1 的消息处理器
        @agent1.register_message_handler("text")
        def handle_text1(msg):
            logger.info(f"{agent1.name}收到text消息: {msg}")
            return {"reply": f"{agent1.name}回复:确认收到text消息:{msg.get('content')}"}

        # agent2 的消息处理器
        def handle_text2(msg):
            logger.info(f"{agent2.name}收到text消息: {msg}")
            return {"reply": f"{agent2.name}回复:确认收到text消息:{msg.get('content')}"}

        agent2.register_message_handler("text", handle_text2)

        # agent3 的通配消息处理器
        @agent3.register_message_handler("*")
        def handle_any(msg):
            logger.info(f"{agent3.name}收到*类型消息: {msg}")
            return {
                "reply": f"{agent3.name}回复:确认收到{msg.get('type')}类型"
                         f"{msg.get('message_type')}格式的消息:{msg.get('content')}"
            }


class GroupChatManager:
    """群聊管理器"""

    def __init__(self, agent: LocalAgent):
        self.agent = agent
        self._ensure_group_attributes()

    def _ensure_group_attributes(self):
        """确保智能体具有群聊相关属性"""
        if not hasattr(self.agent, "group_members"):
            self.agent.group_members = {}
        if not hasattr(self.agent, "group_queues"):
            self.agent.group_queues = {}

    def register_group_handlers(self):
        """注册群聊相关的消息处理器"""
        self.agent.register_message_handler("group_message", self._group_message_handler)
        self.agent.register_message_handler("group_connect", self._group_connect_handler)
        self.agent.register_message_handler("group_members", self._group_members_handler)

        # 注册群聊事件监听
        self.agent.register_group_event_handler(
            self._group_event_handler,
            group_id=None,
            event_type=None
        )

    async def _group_message_handler(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """处理群聊消息发送"""
        group_id = data.get("group_id")
        req_did = data.get("req_did", "demo_caller")

        # 验证发送者权限
        if (group_id not in self.agent.group_members or
                req_did not in self.agent.group_members[group_id]):
            return {"error": "无权在此群组发送消息"}

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        message = {
            "sender": req_did,
            "content": data.get("content", ""),
            "timestamp": timestamp,
            "type": "group_message"
        }

        # 分发消息到群组队列
        if group_id in self.agent.group_queues:
            for queue in self.agent.group_queues[group_id].values():
                await queue.put(message)

        return {"status": "success"}

    async def _group_connect_handler(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """处理群聊连接请求"""
        group_id = data.get("group_id")
        req_did = data.get("req_did")

        if req_did and req_did.find("%3A") == -1:
            parts = req_did.split(":", 4)
            req_did = ":".join(parts[:3]) + "%3A" + ":".join(parts[3:])

        if not req_did:
            return {"error": "未提供订阅者 DID"}

        # 验证订阅者权限
        if (group_id not in self.agent.group_members or
                req_did not in self.agent.group_members[group_id]):
            return {"error": "无权订阅此群组消息"}

        return {"event_generator": self._create_event_generator(group_id, req_did)}

    def _create_event_generator(self, group_id: str, req_did: str):
        """创建SSE事件生成器"""

        async def event_generator():
            if group_id not in self.agent.group_queues:
                self.agent.group_queues[group_id] = {}

            client_id = f"{group_id}_{req_did}_{id(req_did)}"
            self.agent.group_queues[group_id][client_id] = asyncio.Queue()

            try:
                yield f"data: {json.dumps({'status': 'connected', 'group_id': group_id})}\n\n"

                while True:
                    try:
                        message = await asyncio.wait_for(
                            self.agent.group_queues[group_id][client_id].get(),
                            timeout=30
                        )
                        yield f"data: {json.dumps(message)}\n\n"
                    except asyncio.TimeoutError:
                        yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"
            except Exception as e:
                logger.error(f"群组 {group_id} SSE连接错误: {e}")
            finally:
                # 清理资源
                if (group_id in self.agent.group_queues and
                        client_id in self.agent.group_queues[group_id]):
                    del self.agent.group_queues[group_id][client_id]
                if not self.agent.group_queues.get(group_id):
                    self.agent.group_queues.pop(group_id, None)

        return event_generator()

    async def _group_members_handler(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """处理群组成员管理"""
        group_id = data.get("group_id")
        action = data.get("action")
        target_did = data.get("did")
        req_did = data.get("req_did")

        if req_did and req_did.find("%3A") == -1:
            parts = req_did.split(":", 3)
            req_did = ":".join(parts[:2]) + "%3A" + ":".join(parts[2:])

        if not all([action, target_did, req_did]):
            return {"error": "缺少必要参数"}

        if group_id not in self.agent.group_members:
            self.agent.group_members[group_id] = set()

        # 处理空群组的情况
        if not self.agent.group_members[group_id]:
            if action == "add":
                self.agent.group_members[group_id].add(req_did)
                if target_did != req_did:
                    self.agent.group_members[group_id].add(target_did)
                    return {"status": "success", "message": "成功创建群组并添加了创建者和邀请成员"}
                return {"status": "success", "message": "成功创建群组并添加创建者为首个成员"}
            return {"error": "群组不存在"}

        # 验证权限
        if req_did not in self.agent.group_members[group_id]:
            return {"error": "无权管理群组成员"}

        if action == "add":
            self.agent.group_members[group_id].add(target_did)
            return {"status": "success", "message": "成功添加成员"}
        elif action == "remove":
            if target_did in self.agent.group_members[group_id]:
                self.agent.group_members[group_id].remove(target_did)
                return {"status": "success", "message": "成功移除成员"}
            return {"error": "成员不存在"}
        else:
            return {"error": "不支持的操作"}

    async def _group_event_handler(self, group_id: str, event_type: str, event_data: Dict[str, Any]):
        """群聊事件处理器"""
        print(f"收到群{group_id}的{event_type}事件，内容：{event_data}")

        message_file = dynamic_config.get("anp_sdk.group_msg_path")
        message_file = path_resolver.resolve_path(message_file)
        message_file = os.path.join(message_file, "group_messages.json")

        try:
            async with aiofiles.open(message_file, 'a', encoding='utf-8') as f:
                await f.write(json.dumps(event_data, ensure_ascii=False) + '\n')
        except Exception as e:
            logger.error(f"保存消息到文件时出错: {e}")


class DemoRunner:
    """演示运行器"""

    def __init__(self, step_mode: bool = False):
        self.step_helper = StepModeHelper(step_mode)
        self.sdk = None
        self.agents = []

    def initialize_sdk_and_agents(self, fast_mode: bool = False) -> tuple:
        """初始化SDK和智能体"""
        # 1. 初始化 SDK
        self.step_helper.pause(step_id="demo1_1_0")
        self.sdk = ANPSDK()

        # 2. 加载智能体
        self.step_helper.pause(step_id="demo1_1_1")
        self.agents = AgentLoader.load_demo_agents(self.sdk)

        if len(self.agents) < 3:
            logger.error("智能体不足3个，无法完成全部演示")
            return None, None, None, None

        # 3. 注册处理器
        self.step_helper.pause(step_id="demo1_1_2")
        self._register_handlers()

        # 4. 注册智能体到SDK
        self.step_helper.pause(step_id="demo1_1_3")
        for agent in self.agents:
            self.sdk.register_agent(agent)

        # 5. 启动服务器
        self.step_helper.pause(step_id="demo1_1_4")
        self._start_server()
        time.sleep(0.5)

        if not fast_mode:
            input("服务器已启动，查看'/'了解状态,'/docs'了解基础api,按回车继续....")

        return self.sdk, self.agents[0], self.agents[1], self.agents[2]

    def _register_handlers(self):
        """注册各种处理器"""
        APIHandlerRegistry.register_api_handlers(self.agents)
        MessageHandlerRegistry.register_message_handlers(self.agents)

        # 为第一个智能体注册群聊管理器
        if self.agents:
            group_manager = GroupChatManager(self.agents[0])
            group_manager.register_group_handlers()

    def _start_server(self):
        """在新线程中启动服务器"""

        def start_server_thread():
            try:
                self.sdk.start_server()
            except Exception as e:
                logger.error(f"服务器启动错误: {e}")

        thread = threading.Thread(target=start_server_thread)
        thread.daemon = True
        thread.start()
        return thread


class DemoTasks:
    """演示任务集合"""

    def __init__(self, sdk: ANPSDK, step_helper: StepModeHelper):
        self.sdk = sdk
        self.step_helper = step_helper

    async def run_api_demo(self, agent1: LocalAgent, agent2: LocalAgent):
        """演示API调用"""
        self.step_helper.pause("步骤1: 演示API调用")

        # 获取智能体信息
        await self._show_agent_info(agent1, agent2)

        # 演示POST请求
        resp = await agent_api_call_post(
            self.sdk, agent1.id, agent2.id, "/info", {"from": agent1.name}
        )
        logger.info(f"{agent1.name}POST调用{agent2.name}的/info接口响应: {resp}")

        # 演示GET请求
        self.step_helper.pause("演示GET请求到/info接口")
        resp = await agent_api_call_get(
            self.sdk, agent1.id, agent2.id, "/info", {"from": agent1.name}
        )
        logger.info(f"{agent1.name}GET调用{agent2.name}的/info接口响应: {resp}")

    async def run_message_demo(self, agent2: LocalAgent, agent3: LocalAgent, agent1: LocalAgent):
        """演示消息发送"""
        self.step_helper.pause("步骤2: 演示消息发送")

        # agent2 向 agent3 发送消息
        logger.info(f"演示：{agent2.name}向{agent3.name}发送消息")
        resp = await agent_msg_post(self.sdk, agent2.id, agent3.id, f"你好，我是{agent2.name}")
        logger.info(f"{agent2.name}向{agent3.name}发送消息响应: {resp}")

        self.step_helper.pause("消息发送完成，观察回复")

        # agent3 向 agent1 发送消息
        logger.info(f"演示：{agent3.name}向{agent1.name}发送消息")
        resp = await agent_msg_post(self.sdk, agent3.id, agent1.id, f"你好，我是{agent3.name}")
        logger.info(f"{agent3.name}向{agent1.name}发送消息响应: {resp}")

    async def run_group_chat_demo(self, agent1: LocalAgent, agent2: LocalAgent, agent3: LocalAgent):
        """演示群聊功能"""
        self.step_helper.pause("步骤3: 演示群聊功能")

        group_id = "demo_group"
        group_url = f"localhost:{self.sdk.port}"

        # 创建群组和管理成员
        await self._setup_group(agent1, agent2, agent3, group_url, group_id)

        # 演示群聊消息
        await self._demo_group_messages(agent1, agent2, group_url, group_id)

    async def run_accelerator_demo(self, agent1: LocalAgent, agent2: LocalAgent, agent3: LocalAgent):
        """演示本地智能体加速器"""
        self.step_helper.pause("步骤4: 演示本地智能体加速器")

        accelerator = LocalAgentAccelerator()

        # 注册智能体
        for agent in [agent1, agent2, agent3]:
            accelerator.register_agent(agent)
            logger.info(f"注册智能体到加速器: {agent.name}")

        # 演示加速API调用
        start_time = time.time()
        result = await accelerator.route_api_call(
            str(agent1.id), str(agent2.id), "/info", "GET", {"from": agent1.name}
        )
        api_latency = (time.time() - start_time) * 1000

        logger.info(f"加速器API调用结果: {result}")
        logger.info(f"加速器API调用耗时: {api_latency:.2f}ms")

        # 演示加速消息发送
        start_time = time.time()
        result = await accelerator.route_message(
            str(agent2.id), str(agent3.id),
            {"message_type": "text", "content": f"你好，我是{agent2.name}，通过加速器发送"}
        )
        msg_latency = (time.time() - start_time) * 1000

        logger.info(f"加速器消息发送结果: {result}")
        logger.info(f"加速器消息发送耗时: {msg_latency:.2f}ms")

        # 显示性能统计
        stats = accelerator.get_performance_stats()
        logger.info(f"加速器性能统计:\n{json.dumps(stats, ensure_ascii=False, indent=2)}")

    async def _show_agent_info(self, *agents):
        """显示智能体信息"""
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
        """设置群组和成员"""
        # 创建群组
        action = {"action": "add", "did": agent1.id}
        resp = await agent_msg_group_members(self.sdk, agent1.id, agent1.id, group_url, group_id, action)
        logger.info(f"{agent1.name}创建群组响应: {resp}")

        # 添加其他成员
        for agent in [agent2, agent3]:
            action = {"action": "add", "did": agent.id}
            resp = await agent_msg_group_members(self.sdk, agent1.id, agent1.id, group_url, group_id, action)
            logger.info(f"添加{agent.name}到群组响应: {resp}")

    async def _demo_group_messages(self, agent1: LocalAgent, agent2: LocalAgent,
                                   group_url: str, group_id: str):
        """演示群聊消息"""
        # 清空消息文件
        message_file = self._get_group_message_file()
        async with aiofiles.open(message_file, 'w') as f:
            await f.write("")

        # 启动监听
        task = await agent1.start_group_listening(self.sdk, agent1.id, group_url, group_id)
        await asyncio.sleep(1)

        try:
            # 发送消息
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            message = f"大家好，我是{agent1.name}，现在是{timestamp}"
            await agent_msg_group_post(self.sdk, agent1.id, agent1.id, group_url, group_id, message)

            await asyncio.sleep(1)

            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            message = f"大家好，我是{agent2.name}，现在是{timestamp}"
            await agent_msg_group_post(self.sdk, agent2.id, agent1.id, group_url, group_id, message)

            await asyncio.sleep(0.5)

        finally:
            # 清理监听任务
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                logger.info("群聊监听任务已取消")

        # 显示接收到的消息
        await self._show_received_messages(agent1.name, message_file)

    def _get_group_message_file(self) -> str:
        """获取群聊消息文件路径"""
        message_path = dynamic_config.get("anp_sdk.group_msg_path")
        message_path = path_resolver.resolve_path(message_path)
        return os.path.join(message_path, "group_messages.json")

    async def _show_received_messages(self, agent_name: str, message_file: str):
        """显示接收到的群聊消息"""
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


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description='ANP SDK 演示程序')
    parser.add_argument('-d', action='store_true', help='新开发功能测试')
    parser.add_argument('-s', action='store_true', help='启用步骤模式')
    parser.add_argument('-f', action='store_true', help='快速模式')

    args = parser.parse_args()

    if args.d:
        # 开发测试模式
        from dev_functions import run_dev_tests
        run_dev_tests(args.s)
    else:
        # 正常演示模式
        runner = DemoRunner(step_mode=args.s)
        sdk, agent1, agent2, agent3 = runner.initialize_sdk_and_agents(fast_mode=args.f)

        if all([agent1, agent2, agent3]):
            async def run_all_demos():
                demo_tasks = DemoTasks(sdk, runner.step_helper)

                await demo_tasks.run_api_demo(agent1, agent2)
                await demo_tasks.run_message_demo(agent2, agent3, agent1)
                await demo_tasks.run_group_chat_demo(agent1, agent2, agent3)
                await demo_tasks.run_accelerator_demo(agent1, agent2, agent3)

            try:
                asyncio.run(run_all_demos())
                runner.step_helper.pause("演示完成")
            except KeyboardInterrupt:
                logger.info("用户中断演示")
            except Exception as e:
                logger.error(f"演示运行错误: {e}")


if __name__ == "__main__":
    main()