import json
import time
import os
from typing import Dict, Any
from datetime import datetime

from anp_open_sdk.config import UnifiedConfig
from anp_open_sdk.service.interaction.anp_sdk_group_runner import GroupRunner, Message, MessageType, Agent
from anp_open_sdk.utils.log_base import logging  as logger


class FileLoggingGroupRunner(GroupRunner):
    """带文件日志功能的基础 GroupRunner"""

    def __init__(self, group_id: str):
        super().__init__(group_id)
        self.log_dir = UnifiedConfig.resolve_path("anp_open_sdk_demo/data_tmp_result/group_logs")
        os.makedirs(self.log_dir, exist_ok=True)
        logger.debug(f"🗂️ 群组日志目录已创建: {self.log_dir}")  # 添加调试信息

    async def save_message_to_file(self, message_data: Dict[str, Any]):
        """保存消息到文件"""
        log_file = os.path.join(self.log_dir, f"{self.group_id}_messages.json")

        # 读取现有消息
        messages = []
        if os.path.exists(log_file):
            try:
                with open(log_file, "r", encoding="utf-8") as f:
                    messages = json.load(f)
            except (json.JSONDecodeError, FileNotFoundError):
                messages = []

        # 添加新消息
        messages.append(message_data)

        # 写回文件
        with open(log_file, "w", encoding="utf-8") as f:
            json.dump(messages, f, ensure_ascii=False, indent=2)


class ChatRoomRunnerWithLogging(FileLoggingGroupRunner):
    """带日志的简单聊天室"""

    async def on_agent_join(self, agent: Agent) -> bool:
        logger.debug(f"🚪 {agent.name} is joining chat room {self.group_id}...")

        # 记录加入事件
        join_data = {
            "type": "join",
            "agent_id": agent.id,
            "agent_name": agent.name,
            "group_id": self.group_id,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "content": f"{agent.name} joined the chat"
        }
        await self.save_message_to_file(join_data)

        # 广播加入消息
        join_message = Message(
            type=MessageType.SYSTEM,
            content=f"{agent.name} joined the chat",
            sender_id="system",
            group_id=self.group_id,
            timestamp=time.time()
        )
        await self.broadcast(join_message)
        return True

    async def on_agent_leave(self, agent: Agent):
        logger.debug(f"🚪 {agent.name} is leaving chat room {self.group_id}...")

        # 记录离开事件
        leave_data = {
            "type": "leave",
            "agent_id": agent.id,
            "agent_name": agent.name,
            "group_id": self.group_id,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "content": f"{agent.name} left the chat"
        }
        await self.save_message_to_file(leave_data)

        # 广播离开消息
        leave_message = Message(
            type=MessageType.SYSTEM,
            content=f"{agent.name} left the chat",
            sender_id="system",
            group_id=self.group_id,
            timestamp=time.time()
        )
        await self.broadcast(leave_message)

    async def on_message(self, message: Message):
        logger.debug(f"📢 Broadcasting message from {message.sender_id} in {self.group_id}")

        # 保存消息到文件
        message_data = {
            "type": "message",
            "sender": message.sender_id,
            "content": message.content,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "group_id": message.group_id,
            "metadata": message.metadata or {}
        }
        await self.save_message_to_file(message_data)

        # 广播消息给所有人（除了发送者）
        await self.broadcast(message, exclude=[message.sender_id])


class ModeratedChatRunnerWithLogging(FileLoggingGroupRunner):
    """带日志和审核的聊天室"""

    def __init__(self, group_id: str):
        super().__init__(group_id)
        self.banned_words = ["spam", "abuse", "bad"]
        self.moderators = []

    async def on_agent_join(self, agent: Agent) -> bool:
        logger.debug(f"🛡️ {agent.name} is joining moderated chat {self.group_id}...")

        # 检查黑名单
        if agent.metadata and agent.metadata.get("banned"):
            logger.debug(f"❌ {agent.name} is banned and cannot join")
            return False

        # 第一个加入的是管理员
        role = "member"
        if not self.agents:
            agent.metadata = agent.metadata or {}
            agent.metadata["role"] = "moderator"
            self.moderators.append(agent.id)
            role = "moderator"
            logger.debug(f"👑 {agent.name} is now a moderator")

        # 记录加入事件
        join_data = {
            "type": "join",
            "agent_id": agent.id,
            "agent_name": agent.name,
            "role": role,
            "group_id": self.group_id,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "content": f"{agent.name} joined as {role}"
        }
        await self.save_message_to_file(join_data)

        # 广播加入消息
        join_message = Message(
            type=MessageType.SYSTEM,
            content=f"{agent.name} joined as {role}",
            sender_id="system",
            group_id=self.group_id,
            timestamp=time.time()
        )
        await self.broadcast(join_message)
        return True

    async def on_agent_leave(self, agent: Agent):
        logger.debug(f"🛡️ {agent.name} is leaving moderated chat {self.group_id}...")

        # 如果是管理员离开，移除管理员权限
        if agent.id in self.moderators:
            self.moderators.remove(agent.id)
            logger.debug(f"👑 {agent.name} is no longer a moderator")

        # 记录离开事件
        leave_data = {
            "type": "leave",
            "agent_id": agent.id,
            "agent_name": agent.name,
            "group_id": self.group_id,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "content": f"{agent.name} left the moderated chat"
        }
        await self.save_message_to_file(leave_data)

        # 广播离开消息
        leave_message = Message(
            type=MessageType.SYSTEM,
            content=f"{agent.name} left the moderated chat",
            sender_id="system",
            group_id=self.group_id,
            timestamp=time.time()
        )
        await self.broadcast(leave_message)

    async def on_message(self, message: Message):
        logger.debug(f"🔍 Checking message from {message.sender_id}: '{message.content}'")

        # 检查违禁词
        found_bad_words = [word for word in self.banned_words if word in message.content.lower()]
        if found_bad_words:
            logger.debug(f"🚫 Message blocked! Found banned words: {found_bad_words}")

            # 记录被拦截的消息
            blocked_data = {
                "type": "message_blocked",
                "sender": message.sender_id,
                "content": message.content,
                "reason": f"banned_words: {', '.join(found_bad_words)}",
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "group_id": message.group_id
            }
            await self.save_message_to_file(blocked_data)

            # 发送警告给发送者
            warning_message = Message(
                type=MessageType.SYSTEM,
                content=f"Your message contains banned words: {', '.join(found_bad_words)}",
                sender_id="system",
                group_id=self.group_id,
                timestamp=time.time()
            )
            await self.send_to_agent(message.sender_id, warning_message)
            return

        logger.debug(f"✅ Message approved, broadcasting...")

        # 保存通过审核的消息
        message_data = {
            "type": "message",
            "sender": message.sender_id,
            "content": message.content,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "group_id": message.group_id,
            "metadata": message.metadata or {}
        }
        await self.save_message_to_file(message_data)

        # 广播消息
        await self.broadcast(message, exclude=[message.sender_id])