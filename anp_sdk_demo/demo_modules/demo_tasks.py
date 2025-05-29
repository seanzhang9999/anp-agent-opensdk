import asyncio
import time
import os
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



from anp_sdk_demo.demo_modules.customized_group_member import (
    GroupMemberWithStorage,
    GroupMemberWithStats,
    GroupMemberComplete
)
from anp_sdk_demo.demo_modules.customized_group_runner import (
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
            # 运行基础演示
            # 开发模式特有的功能
            #if self.dev_mode:
            #    await self.run_development_features()

            await self.run_api_demo(agent1, agent2)
            await self.run_message_demo(agent2, agent3, agent1)
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

  
    async def run_group_chat_demo(self, agent1: LocalAgent, agent2: LocalAgent, agent3: LocalAgent):
        """使用新的 GroupRunner SDK 运行群聊演示"""
        print("\n" + "=" * 60)
        print("🚀 运行增强群聊演示 (使用增强的 GroupMember 与 GroupRunner)")
        print("=" * 60)
        try:
            # 注册 GroupRunner
            print("📋 注册 GroupRunner...")
            self.sdk.register_group_runner("sample_group", ChatRoomRunnerWithLogging)
            self.sdk.register_group_runner("moderated_group", ModeratedChatRunnerWithLogging)

            # 创建 GroupMember 客户端（使用不同的扩展类）
            print("👥 创建群组成员客户端...")
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
                print(f"[{agent1.name}] 📨 {message.sender_id}: {message.content}")

            async def member2_handler(message):
                print(f"[{agent2.name}] 📨 {message.sender_id}: {message.content}")

            async def member3_handler(message):
                print(f"[{agent3.name}] 📨 {message.sender_id}: {message.content}")

            # 演示1: 普通群聊
            print("\n📋 演示1: 普通群聊")
            print("-" * 40)

            # 加入群组
            print("👥 加入普通群聊...")
            await member1.join_group("sample_group", name=agent1.name)
            await member2.join_group("sample_group", name=agent2.name)
            await member3.join_group("sample_group", name=agent3.name)

            # 开始监听
            await member1.listen_group("sample_group", member1_handler)
            await member2.listen_group("sample_group", member2_handler)
            await member3.listen_group("sample_group", member3_handler)

            await asyncio.sleep(1)  # 等待监听器启动

            # 发送消息
            print("\n💬 发送普通群聊消息...")
            await member1.send_message("sample_group", f"Hello from {agent1.name}!")
            await asyncio.sleep(0.5)
            await member2.send_message("sample_group", f"Hi everyone, this is {agent2.name}")
            await asyncio.sleep(0.5)
            await member3.send_message("sample_group", f"Greetings from {agent3.name}!")
            await asyncio.sleep(1)

            # 演示2: 审核群聊
            print("\n🛡️ 演示2: 审核群聊")
            print("-" * 40)

            # 加入审核群组
            print("👥 加入审核群聊...")
            await member1.join_group("moderated_group", name=agent1.name)
            await member2.join_group("moderated_group", name=agent2.name)

            # 开始监听审核群组
            await member1.listen_group("moderated_group", member1_handler)
            await member2.listen_group("moderated_group", member2_handler)
            await asyncio.sleep(1)

            # 发送正常消息
            print("\n💬 发送正常消息...")
            await member1.send_message("moderated_group", "This is a normal message")
            await asyncio.sleep(0.5)

            # 发送违规消息
            print("\n🚫 发送违规消息...")
            await member2.send_message("moderated_group", "This message contains spam content")
            await asyncio.sleep(0.5)

            # 发送另一个正常消息
            await member1.send_message("moderated_group", "Back to normal conversation")
            await asyncio.sleep(2)

            # 显示扩展信息
            print("\n📊 扩展功能信息:")
            print("-" * 40)
            print("存储功能 (member1):")
            storage_stats = member1.get_storage_stats()
            print(json.dumps(storage_stats, indent=2))

            print("\n统计功能 (member2):")
            stats = member2.get_stats()
            print(json.dumps(stats, indent=2))

            if isinstance(member3, GroupMemberComplete):
                print("\n完整功能 (member3):")
                complete_info = member3.get_complete_info()
                print(json.dumps(complete_info, indent=2))
                
            # 显示群组日志
            print("\n📋 显示群组运行日志:")
            print("-" * 40)
            group_log_files = [
                path_resolver.resolve_path("anp_sdk_demo/demo_data/group_logs/sample_group_messages.json"),
                path_resolver.resolve_path("anp_sdk_demo/demo_data/group_logs/moderated_group_messages.json")
            ]
            for group_name, log_file in zip(["普通群聊", "审核群聊"], group_log_files):
                await self._show_group_logs(group_name, log_file)

    


            # 显示接收到的消息
            print("\n📁 显示接收到的群组消息:")
            print("-" * 40)

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
                    message_file = path_resolver.resolve_path(f"anp_sdk_demo/demo_data/member_messages/{agent_prefix}_group_messages.json")
                    await self._show_received_group_messages(agent.name, message_file)
                     # 清空对应文件
                    try:
                        if os.path.exists(message_file):
                            with open(message_file, 'w', encoding='utf-8') as f:
                                f.write("")
                            print(f"📝 已清空 {agent.name} 的消息文件")
                    except Exception as e:
                        print(f"❌ 清空 {agent.name} 消息文件失败: {e}")
                            
                else:
                    print(f"\n📨 {agent.name}: 使用的是 {agent_type} 类，不具备存储功能")







            # 清理
            print("\n🧹 清理群聊连接...")
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

            print("✅ 增强群聊演示完成")

        except Exception as e:
            print(f"❌ 增强群聊演示过程中出错: {e}")
            import traceback
            traceback.print_exc()

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

    async def _show_received_group_messages(self, agent_name: str, message_file: str):
        """显示 agent 接收到的群组消息"""
        try:
            if os.path.exists(message_file):
                with open(message_file, 'r', encoding='utf-8') as f:
                    messages = json.load(f)
                print(f"\n📨 {agent_name} 接收到的消息 ({len(messages)} 条):")
                for msg in messages:
                    msg_type = msg.get('type', 'unknown')
                    sender = msg.get('sender', 'unknown')
                    content = msg.get('content', '')
                    timestamp = msg.get('timestamp', '')
                    group_id = msg.get('group_id', '')
                    icon = "🔔" if msg_type == "system" else "💬"
                    print(f"  {icon} [{timestamp}] [{group_id}] {sender}: {content}")
            else:
                print(f"\n📨 {agent_name}: 没有找到消息文件")
        except Exception as e:
            print(f"❌ 读取 {agent_name} 的消息文件时出错: {e}")

    async def _show_group_logs(self, group_name: str, log_file: str):
        """显示群组运行日志"""
        try:
            if os.path.exists(log_file):
                with open(log_file, 'r', encoding='utf-8') as f:
                    logs = json.load(f)
                print(f"\n📋 {group_name} 运行日志 ({len(logs)} 条):")
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
                    print(f"  {icon} [{timestamp}] {content}")
            else:
                print(f"\n📋 {group_name}: 没有找到日志文件")
        except Exception as e:
            print(f"❌ 读取 {group_name} 日志文件时出错: {e}")


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