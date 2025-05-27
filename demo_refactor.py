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
from encodings.punycode import selective_find
from typing import List, Optional, Dict, Any
from urllib.parse import quote

import requests
import aiofiles
from colorama import init, Fore, Style
from loguru import logger

from anp_open_sdk.anp_sdk import ANPSDK, LocalAgent, LocalUserDataManager
from anp_open_sdk.config.dynamic_config import dynamic_config
from anp_open_sdk.config.path_resolver import path_resolver
from anp_open_sdk.service.agent_api_call import agent_api_call_post, agent_api_call_get
from anp_open_sdk.service.agent_message_group import agent_msg_group_post, agent_msg_group_members
from anp_open_sdk.service.agent_message_p2p import agent_msg_post
from anp_open_sdk.service.local_agent_accelerator import LocalAgentAccelerator



class DemoToolsStepModeHelper:
    def __init__(self, step_mode: bool = False):
        self.step_mode = step_mode

    def pause(self, step_name: str = "", step_id: str = None):
        if step_id is not None:
            step_name = self._load_helper_text(step_id=step_id)

        if self.step_mode:
            input(f"{Fore.GREEN}--- {step_name} ---{Style.RESET_ALL} "
                  f"{Fore.YELLOW}按任意键继续...{Style.RESET_ALL}")

    @staticmethod
    def _load_helper_text(step_id: str, lang: str = None) -> str:
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

    @staticmethod
    def find_hosted_agent(sdk: ANPSDK, user_datas) -> Optional[LocalAgent]:
        for user_data in user_datas:
            agent = LocalAgent(sdk, user_data.did)
            if agent.is_hosted_did:
                logger.info(f"hosted_did: {agent.id}")
                logger.info(f"parent_did: {agent.parent_did}")
                logger.info(f"hosted_info: {agent.hosted_info}")
                return agent
        return None
    @staticmethod
    def load_demo_agents(sdk: ANPSDK) -> List[LocalAgent]:
        user_data_manager: LocalUserDataManager = sdk.user_data_manager

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


class AgentRegistryForAPI:
    @staticmethod
    def register_api_handlers(agents: List[LocalAgent]) -> None:
        if len(agents) < 2:
            logger.warning("智能体数量不足，无法注册所有API处理器")
            return

        agent1, agent2 = agents[0], agents[1]


        # 智能体的第一种API发布方式：装饰器
        # 使用@agent.expose_api装饰器注册API端点，支持指定路径和HTTP方法
        @agent1.expose_api("/hello", methods=["GET"])
        def hello_api(request):
            return {
                "msg": f"{agent1.name}的/hello接口收到请求:",
                "param": request.get("params")
            }


        # 智能体的另一种API发布方式：显式注册
        # 使用agent.expose_api()方法注册API端点，支持指定路径和HTTP方法
        def info_api(request):
            return {
                "msg": f"{agent2.name}的/info接口收到请求:",
                "data": request.get("params")
            }
        agent2.expose_api("/info", info_api, methods=["POST", "GET"])
class AgentRegistryForMessage:
    @staticmethod
    def register_message_handlers(agents: List[LocalAgent]) -> None:
        if len(agents) < 3:
            logger.warning("智能体数量不足，无法注册所有消息处理器")
            return

        agent1, agent2, agent3 = agents[0], agents[1], agents[2]

        @agent1.register_message_handler("text")
        def handle_text1(msg):
            logger.info(f"{agent1.name}收到text消息: {msg}")
            return {"reply": f"{agent1.name}回复:确认收到text消息:{msg.get('content')}"}

        def handle_text2(msg):
            logger.info(f"{agent2.name}收到text消息: {msg}")
            return {"reply": f"{agent2.name}回复:确认收到text消息:{msg.get('content')}"}
        agent2.register_message_handler("text", handle_text2)

        @agent3.register_message_handler("*")
        def handle_any(msg):
            logger.info(f"{agent3.name}收到*类型消息: {msg}")
            return {
                "reply": f"{agent3.name}回复:确认收到{msg.get('type')}类型"
                         f"{msg.get('message_type')}格式的消息:{msg.get('content')}"
            }

async def demo_show_save_group_msg_to_file(agent:LocalAgent, message: Dict[str, Any]):
    message_file = path_resolver.resolve_path(f"{agent.name}_group_messages.json")
    try:
        # 确保目录存在
        message_dir = os.path.dirname(message_file)
        if message_dir and not os.path.exists(message_dir):
            os.makedirs(message_dir, exist_ok=True)

        # 如果文件不存在则创建，存在则追加
        async with aiofiles.open(message_file, 'a', encoding='utf-8') as f:
            await f.write(json.dumps(message, ensure_ascii=False) + '\n')
    except Exception as e:
        logger.error(f"保存群聊消息到文件时出错: {e}")

class AgentGroupMember:
    def __init__(self, agent: LocalAgent):
        self.agent = agent
    async def handle_group_message(self, msg: Dict[str, Any]):
        await demo_show_save_group_msg_to_file(self.agent, msg)
        logger.info(f"{self.agent.name}收到群聊消息: {msg}")
        return {"status": "success"}

    async def _my_handler(self, group_id, event_type, event_data):
        print(f"收到群{group_id}的{event_type}事件，内容：{event_data}")
        await self.handle_group_message(event_data)

    def register_group_event_handler(self):
        self.agent.register_group_event_handler(self._my_handler)



class AgentGroupRunner:
    """
    AgentGroupRunner - 群组运行演示类

    这是一个group的运行demo，注册了对group的成员管理、消息接受处理、SSE监听分发的处理函数，
    在register_group_handlers后一直响应，其实应该也有注销handler的动作

    主要功能：
    1. 群组成员管理 - 添加/移除成员
    2. 群组消息处理 - 接收和分发群组消息
    3. SSE连接管理 - 处理实时消息推送连接
    4. 事件记录 - 保存群组活动日志
    """
    def __init__(self, agent: LocalAgent , group_id):
        self.agent = agent
        self._ensure_group_attributes()
        self.group_id = group_id


    def _ensure_group_attributes(self):
        if not hasattr(self.agent, "group_members"):
            self.agent.group_members = {}
        if not hasattr(self.agent, "group_queues"):
            self.agent.group_queues = {}

    def _normalize_did(self, did: str) -> str:
        """统一的 DID 编码处理"""
        if did and did.find("%3A") == -1:
            parts = did.split(":", 4)
            return ":".join(parts[:3]) + "%3A" + ":".join(parts[3:])
        return did

    async def _group_message_handler(self, data: Dict[str, Any]) -> Dict[str, Any]:
        group_id = data.get("group_id")
        req_did = data.get("req_did", "demo_caller")

        if (group_id not in self.agent.group_members or
                req_did not in self.agent.group_members[group_id]):
            return {"error": "无权在此群组发送消息"}
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        message = {
            "sender": req_did,
            "content": data.get("content", ""),
            "timestamp": timestamp,
            "type": "group_message",
            "group_id": group_id
        }
        if group_id in self.agent.group_queues:
            for queue in self.agent.group_queues[group_id].values():
                await queue.put(message)

        if self.agent.group_members.get(group_id) and req_did in self.agent.group_members[group_id]:
            await demo_show_save_group_msg_to_file(self.agent, message)
        return {"status": "success"}

    async def _group_connect_handler(self, data: Dict[str, Any]) -> Dict[str, Any]:
        group_id = data.get("group_id")
        req_did = self._normalize_did(data.get("req_did"))

        if not req_did:
            return {"error": "未提供订阅者 DID"}

        if (group_id not in self.agent.group_members or
                req_did not in self.agent.group_members[group_id]):
            return {"error": "无权订阅此群组消息"}

        await self._save_connection_event(group_id, req_did, "connected")

        return {"event_generator": self._create_event_generator(group_id, req_did)}

    async def _group_members_handler(self, data: Dict[str, Any]) -> Dict[str, Any]:
        group_id = data.get("group_id")
        action = data.get("action")
        target_did = data.get("did")
        req_did = self._normalize_did(data.get("req_did"))

        if not all([action, target_did, req_did]):
            return {"error": "缺少必要参数"}

        if group_id not in self.agent.group_members:
            self.agent.group_members[group_id] = set()

        if not self.agent.group_members[group_id]:
            if action == "add":
                self.agent.group_members[group_id].add(req_did)
                if target_did != req_did:
                    self.agent.group_members[group_id].add(target_did)
                    await self._save_member_event(group_id, "add", [req_did, target_did])
                    return {"status": "success", "message": "成功创建群组并添加了创建者和邀请成员"}
                await self._save_member_event(group_id, "add", [req_did])
                return {"status": "success", "message": "成功创建群组并添加创建者为首个成员"}
            return {"error": "群组不存在"}

        if req_did not in self.agent.group_members[group_id]:
            return {"error": "无权管理群组成员"}

        if action == "add":
            self.agent.group_members[group_id].add(target_did)
            await self._save_member_event(group_id, "add", [target_did])
            return {"status": "success", "message": "成功添加成员"}
        elif action == "remove":
            if target_did in self.agent.group_members[group_id]:
                self.agent.group_members[group_id].remove(target_did)
                await self._save_member_event(group_id, "remove", [target_did])
                return {"status": "success", "message": "成功移除成员"}
            return {"error": "成员不存在"}
        else:
            return {"error": "不支持的操作"}

    def register_group_handlers(self):
        self.agent.register_message_handler("group_message", self._group_message_handler)
        self.agent.register_message_handler("group_connect", self._group_connect_handler)
        self.agent.register_message_handler("group_members", self._group_members_handler)


    def _create_event_generator(self, group_id: str, req_did: str):

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
                        if req_did != list(self.agent.group_members[group_id])[0]:
                            await demo_show_save_group_msg_to_file(self.agent, message)
                        yield f"data: {json.dumps(message)}\n\n"
                    except asyncio.TimeoutError:
                        yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"
            except Exception as e:
                logger.error(f"群组 {group_id} SSE连接错误: {e}")
                await self._save_connection_event(group_id, req_did, "disconnected")
            finally:
                if (group_id in self.agent.group_queues and
                        client_id in self.agent.group_queues[group_id]):
                    del self.agent.group_queues[group_id][client_id]
                if not self.agent.group_queues.get(group_id):
                    self.agent.group_queues.pop(group_id, None)

        return event_generator()


    async def _save_member_event(self, group_id: str, action: str, members: List[str]):
        event = {
            "type": "member_event",
            "group_id": group_id,
            "action": action,
            "members": members,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        await demo_show_save_group_msg_to_file(self.agent, event)

    async def _save_connection_event(self, group_id: str, req_did: str, status: str):
        event = {
            "type": "connection_event",
            "group_id": group_id,
            "member": req_did,
            "status": status,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        await demo_show_save_group_msg_to_file(self.agent, event)


class DemoPrepare:
    def __init__(self, step_mode: bool = False):
        self.step_helper = DemoToolsStepModeHelper(step_mode)
        self.sdk = None
        self.agents = []

    def initialize_sdk_and_agents(self, fast_mode: bool = False) -> tuple:
        self.step_helper.pause(step_id="demo1_1_0")
        self.sdk = ANPSDK()

        self.step_helper.pause(step_id="demo1_1_1")
        self.agents = AgentLoader.load_demo_agents(self.sdk)

        if len(self.agents) < 3:
            logger.error("智能体不足3个，无法完成全部演示")
            return None, None, None, None

        self.step_helper.pause(step_id="demo1_1_2")
        AgentRegistryForAPI.register_api_handlers(self.agents)
        AgentRegistryForMessage.register_message_handlers(self.agents)

        self.step_helper.pause(step_id="demo1_1_3")
        for agent in self.agents:
            self.sdk.register_agent(agent)

        self.step_helper.pause(step_id="demo1_1_4")
        self._start_server()
        time.sleep(0.5)

        return self.sdk, self.agents[0], self.agents[1], self.agents[2]

    def _start_server(self):
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
    def __init__(self, sdk: ANPSDK, step_helper: DemoToolsStepModeHelper):
        self.sdk = sdk
        self.step_helper = step_helper

    async def run_api_demo(self, agent1: LocalAgent, agent2: LocalAgent):
        self.step_helper.pause("步骤1: 演示API调用")

        await self._show_agent_info(agent1, agent2)

        resp = await agent_api_call_post(
            self.sdk, agent1.id, agent2.id, "/info", {"from": agent1.name}
        )
        logger.info(f"{agent1.name}POST调用{agent2.name}的/info接口响应: {resp}")

        self.step_helper.pause("演示GET请求到/info接口")
        resp = await agent_api_call_get(
            self.sdk, agent1.id, agent2.id, "/info", {"from": agent1.name}
        )
        logger.info(f"{agent1.name}GET调用{agent2.name}的/info接口响应: {resp}")

    async def run_message_demo(self, agent2: LocalAgent, agent3: LocalAgent, agent1: LocalAgent):
        self.step_helper.pause("步骤2: 演示消息发送")

        logger.info(f"演示：{agent2.name}向{agent3.name}发送消息")
        resp = await agent_msg_post(self.sdk, agent2.id, agent3.id, f"你好，我是{agent2.name}")
        logger.info(f"{agent2.name}向{agent3.name}发送消息响应: {resp}")

        self.step_helper.pause("消息发送完成，观察回复")

        logger.info(f"演示：{agent3.name}向{agent1.name}发送消息")
        resp = await agent_msg_post(self.sdk, agent3.id, agent1.id, f"你好，我是{agent3.name}")
        logger.info(f"{agent3.name}向{agent1.name}发送消息响应: {resp}")

    async def run_group_chat_demo(self, agent1: LocalAgent, agent2: LocalAgent, agent3: LocalAgent):
        self.step_helper.pause("步骤3: 演示群聊功能")

        group_id = "demo_group"
        group_url = f"localhost:{self.sdk.port}"

        group_runner = AgentGroupRunner(agent1, group_id)
        group_runner.register_group_handlers()

        member2 = AgentGroupMember(agent2)
        member3 = AgentGroupMember(agent3)
        member2.register_group_event_handler()
        member3.register_group_event_handler()

        await self._setup_group(agent1, agent2, agent3, group_url, group_id)

        await self._demo_group_messages(agent1, agent2, agent3, group_url, group_id)



        message_file1 = path_resolver.resolve_path(f"{agent1.name}_group_messages.json")
        message_file2 = path_resolver.resolve_path(f"{agent2.name}_group_messages.json")
        message_file3 = path_resolver.resolve_path(f"{agent3.name}_group_messages.json")

        await self._show_received_messages(agent1.name, message_file1)
        await self._show_received_messages(agent2.name, message_file2)
        await self._show_received_messages(agent3.name, message_file3)


    async def run_accelerator_demo(self, agent1: LocalAgent, agent2: LocalAgent, agent3: LocalAgent):
        self.step_helper.pause("步骤4: 演示本地智能体加速器")

        accelerator = LocalAgentAccelerator()

        for agent in [agent1, agent2, agent3]:
            accelerator.register_agent(agent)
            logger.info(f"注册智能体到加速器: {agent.name}")

        start_time = time.time()
        result = await accelerator.route_api_call(
            str(agent1.id), str(agent2.id), "/info", "GET", {"from": agent1.name}
        )
        api_latency = (time.time() - start_time) * 1000

        logger.info(f"加速器API调用结果: {result}")
        logger.info(f"加速器API调用耗时: {api_latency:.2f}ms")

        start_time = time.time()
        result = await accelerator.route_message(
            str(agent2.id), str(agent3.id),
            {"message_type": "text", "content": f"你好，我是{agent2.name}，通过加速器发送"}
        )
        msg_latency = (time.time() - start_time) * 1000

        logger.info(f"加速器消息发送结果: {result}")
        logger.info(f"加速器消息发送耗时: {msg_latency:.2f}ms")

        stats = accelerator.get_performance_stats()
        logger.info(f"加速器性能统计:\n{json.dumps(stats, ensure_ascii=False, indent=2)}")

    async def _show_agent_info(self, *agents):
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


        action = {"action": "add", "did": agent1.id}
        resp = await agent_msg_group_members(self.sdk, agent1.id, agent1.id, group_url, group_id, action)
        logger.info(f"{agent1.name}创建群组响应: {resp}")

        for agent in [agent2, agent3]:
            action = {"action": "add", "did": agent.id}
            resp = await agent_msg_group_members(self.sdk, agent1.id, agent1.id, group_url, group_id, action)
            logger.info(f"添加{agent.name}到群组响应: {resp}")

    async def _demo_group_messages(self, agent1, agent2: LocalAgent, agent3: LocalAgent,
                                   group_url: str, group_id: str):




        task2 = await agent2.start_group_listening(self.sdk, agent1.id, group_url, group_id)
        task3 = await agent3.start_group_listening(self.sdk, agent1.id, group_url, group_id)
        await asyncio.sleep(2)

        try:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            message = f"大家好，我是{agent1.name}，现在是{timestamp}"
            await agent_msg_group_post(self.sdk, agent1.id, agent1.id, group_url, group_id, message)

            await asyncio.sleep(2)

            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            message = f"大家好，我是{agent2.name}，现在是{timestamp}"
            await agent_msg_group_post(self.sdk, agent2.id, agent2.id, group_url, group_id, message)

            await asyncio.sleep(2)

            await asyncio.sleep(3)

        finally:
            for task in [ task2,task3 ]:
                task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                logger.info("群聊监听任务已取消")



    async def _show_received_messages(self, agent_name: str, message_file: str):
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
    import argparse

    parser = argparse.ArgumentParser(description='ANP SDK 演示程序')
    parser.add_argument('-s', action='store_true', help='启用步骤模式')
    parser.add_argument('-f', action='store_true', help='快速模式')

    args = parser.parse_args()


    runner = DemoPrepare(step_mode=args.s)
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
