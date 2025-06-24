import json
import os
import time
from typing import Dict, Any, Callable, List
from datetime import datetime

from anp_open_sdk.config import UnifiedConfig
from anp_open_sdk.service.interaction.anp_sdk_group_member import GroupMemberSDK
from anp_open_sdk.service.interaction.anp_sdk_group_runner import Message, MessageType
from anp_open_sdk.utils.log_base import logging as logger

class GroupMemberWithStorage(GroupMemberSDK):
    """带存储功能的 GroupMemberSDK"""

    def __init__(self, agent_id: str, port: int, base_url: str = "http://localhost",
                 use_local_optimization: bool = True,
                 enable_storage: bool = True,
                 storage_dir: str = "anp_open_sdk_demo/data_tmp_result/member_messages"):
        super().__init__(agent_id, port, base_url, use_local_optimization)

        self.enable_storage = enable_storage
        if self.enable_storage:
            self.storage_dir = UnifiedConfig.resolve_path(storage_dir)
            os.makedirs(self.storage_dir, exist_ok=True)
            logger.debug(f"🗂️ 存储目录已创建: {self.storage_dir}")  # 添加调试信息

    async def save_received_message(self, group_id: str, message: Message):
        """保存接收到的消息"""
        if not self.enable_storage:
            return

        agent_name = self.agent_id.split(":")[-1] if ":" in self.agent_id else self.agent_id
        message_file = os.path.join(self.storage_dir, f"{agent_name}_group_messages.json")
        logger.debug(f"📝 正在保存消息到 {message_file}")  # 添加调试信息

        message_data = {
            "type": message.type.value,
            "sender": message.sender_id,
            "content": message.content,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "group_id": group_id,
            "receiver": self.agent_id,
            "metadata": message.metadata or {}
        }

        # 读取现有消息
        messages = []
        if os.path.exists(message_file):
            try:
                with open(message_file, "r", encoding="utf-8") as f:
                    messages = json.load(f)
            except (json.JSONDecodeError, FileNotFoundError):
                messages = []

        # 添加新消息
        messages.append(message_data)

        # 写回文件
        with open(message_file, "w", encoding="utf-8") as f:
            json.dump(messages, f, ensure_ascii=False, indent=2)

    async def save_group_event(self, event_type: str, group_id: str, extra_data: Dict[str, Any] = None):
        """保存群组事件"""
        if not self.enable_storage:
            return

        agent_name = self.agent_id.split(":")[-1] if ":" in self.agent_id else self.agent_id
        event_file = os.path.join(self.storage_dir, f"{agent_name}_group_events.json")

        event_data = {
            "event_type": event_type,
            "agent_id": self.agent_id,
            "group_id": group_id,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "extra_data": extra_data or {}
        }

        # 读取现有事件
        events = []
        if os.path.exists(event_file):
            try:
                with open(event_file, "r", encoding="utf-8") as f:
                    events = json.load(f)
            except (json.JSONDecodeError, FileNotFoundError):
                events = []

        # 添加新事件
        events.append(event_data)

        # 写回文件
        with open(event_file, "w", encoding="utf-8") as f:
            json.dump(events, f, ensure_ascii=False, indent=2)

    async def join_group(self, group_id: str, did: str = None,
                         name: str = None, metadata: Dict[str, Any] = None) -> bool:
        """重写加入群组方法，添加存储功能"""
        result = await super().join_group(group_id, did, name, metadata)

        if result and self.enable_storage:
            await self.save_group_event("join", group_id, {
                "name": name or self.agent_id,
                "metadata": metadata or {}
            })
            logger.debug(f"📝 {self.agent_id.split(':')[-1]} joined group {group_id} (logged)")

        return result

    async def leave_group(self, group_id: str, did: str = None) -> bool:
        """重写离开群组方法，添加存储功能"""
        result = await super().leave_group(group_id, did)

        if result and self.enable_storage:
            await self.save_group_event("leave", group_id)
            logger.debug(f"📝 {self.agent_id.split(':')[-1]} left group {group_id} (logged)")

        return result

    async def send_message(self, group_id: str, content: Any, did: str = None,
                           message_type: MessageType = MessageType.TEXT,
                           metadata: Dict[str, Any] = None) -> bool:
        """重写发送消息方法，添加存储功能"""
        result = await super().send_message(group_id, content, did, message_type, metadata)

        if result and self.enable_storage:
            # 保存发送的消息
            sent_message = Message(
                type=message_type,
                content=content,
                sender_id=self.agent_id,
                group_id=group_id,
                timestamp=time.time(),
                metadata=metadata
            )
            await self.save_sent_message(group_id, sent_message)

        return result

    async def save_sent_message(self, group_id: str, message: Message):
        """保存发送的消息"""
        if not self.enable_storage:
            return

        agent_name = self.agent_id.split(":")[-1] if ":" in self.agent_id else self.agent_id
        sent_file = os.path.join(self.storage_dir, f"{agent_name}_sent_messages.json")

        message_data = {
            "type": message.type.value,
            "content": message.content,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "group_id": group_id,
            "sender": self.agent_id,
            "metadata": message.metadata or {}
        }

        # 读取现有消息
        messages = []
        if os.path.exists(sent_file):
            try:
                with open(sent_file, "r", encoding="utf-8") as f:
                    messages = json.load(f)
            except (json.JSONDecodeError, FileNotFoundError):
                messages = []

        # 添加新消息
        messages.append(message_data)

        # 写回文件
        with open(sent_file, "w", encoding="utf-8") as f:
            json.dump(messages, f, ensure_ascii=False, indent=2)

    async def listen_group(self, group_id: str, callback: Callable[[Message], None],
                           did: str = None, message_types: List[MessageType] = None):
        """重写监听方法，添加存储功能"""

        # 包装回调函数以添加存储功能
        async def storage_callback(message: Message):
            # 先存储消息
            if self.enable_storage:
                await self.save_received_message(group_id, message)

            # 再调用原始回调
            await callback(message)

        # 调用父类的监听方法
        await super().listen_group(group_id, storage_callback, did, message_types)

    def get_storage_stats(self) -> Dict[str, Any]:
        """获取存储统计信息"""
        if not self.enable_storage:
            return {"storage_enabled": False}

        agent_name = self.agent_id.split(":")[-1] if ":" in self.agent_id else self.agent_id
        stats = {"storage_enabled": True, "files": {}}

        # 统计各种文件
        file_types = [
            ("received_messages", f"{agent_name}_group_messages.json"),
            ("sent_messages", f"{agent_name}_sent_messages.json"),
            ("events", f"{agent_name}_group_events.json")
        ]

        for file_type, filename in file_types:
            file_path = os.path.join(self.storage_dir, filename)
            if os.path.exists(file_path):
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    stats["files"][file_type] = {
                        "count": len(data),
                        "file_path": file_path,
                        "latest": data[-1] if data else None
                    }
                except:
                    stats["files"][file_type] = {"count": 0, "error": "Failed to read"}
            else:
                stats["files"][file_type] = {"count": 0, "file_path": file_path}

        return stats


class GroupMemberWithStats(GroupMemberSDK):
    """带统计功能的 GroupMemberSDK"""

    def __init__(self, agent_id: str, port: int, base_url: str = "http://localhost",
                 use_local_optimization: bool = True):
        super().__init__(agent_id, port, base_url, use_local_optimization)

        self.message_stats = {
            "received_count": 0,
            "sent_count": 0,
            "groups_joined": set(),
            "senders": {},
            "message_types": {}
        }

    async def join_group(self, group_id: str, did: str = None,
                         name: str = None, metadata: Dict[str, Any] = None) -> bool:
        """重写加入群组方法，添加统计功能"""
        result = await super().join_group(group_id, did, name, metadata)

        if result:
            self.message_stats["groups_joined"].add(group_id)
            logger.debug(f"📊 {self.agent_id.split(':')[-1]} joined group {group_id} (stats updated)")

        return result

    async def send_message(self, group_id: str, content: Any, did: str = None,
                           message_type: MessageType = MessageType.TEXT,
                           metadata: Dict[str, Any] = None) -> bool:
        """重写发送消息方法，添加统计功能"""
        result = await super().send_message(group_id, content, did, message_type, metadata)

        if result:
            self.message_stats["sent_count"] += 1
            msg_type = message_type.value
            if msg_type not in self.message_stats["message_types"]:
                self.message_stats["message_types"][msg_type] = 0
            self.message_stats["message_types"][msg_type] += 1

        return result

    async def listen_group(self, group_id: str, callback: Callable[[Message], None],
                           did: str = None, message_types: List[MessageType] = None):
        """重写监听方法，添加统计功能"""

        async def stats_callback(message: Message):
            # 更新统计
            self.message_stats["received_count"] += 1

            sender = message.sender_id
            if sender not in self.message_stats["senders"]:
                self.message_stats["senders"][sender] = 0
            self.message_stats["senders"][sender] += 1

            msg_type = message.type.value
            if msg_type not in self.message_stats["message_types"]:
                self.message_stats["message_types"][msg_type] = 0
            self.message_stats["message_types"][msg_type] += 1

            # 调用原始回调
            await callback(message)

        await super().listen_group(group_id, stats_callback, did, message_types)

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        stats = self.message_stats.copy()
        stats["groups_joined"] = list(stats["groups_joined"])  # 转换 set 为 list
        return stats


class GroupMemberComplete(GroupMemberWithStorage):
    """完整功能的 GroupMember（继承存储功能，添加统计功能）"""

    def __init__(self, agent_id: str, port: int, base_url: str = "http://localhost",
                 use_local_optimization: bool = True,
                 enable_storage: bool = True,
                 storage_dir: str = "anp_open_sdk_demo/data_tmp_result/member_messages"):
        super().__init__(agent_id, port, base_url, use_local_optimization, enable_storage, storage_dir)

        # 添加统计功能
        self.message_stats = {
            "received_count": 0,
            "sent_count": 0,
            "groups_joined": set(),
            "senders": {},
            "message_types": {}
        }

    async def join_group(self, group_id: str, did: str = None,
                         name: str = None, metadata: Dict[str, Any] = None) -> bool:
        """重写加入群组方法，同时支持存储和统计"""
        result = await super().join_group(group_id, did, name, metadata)

        if result:
            self.message_stats["groups_joined"].add(group_id)

        return result

    async def send_message(self, group_id: str, content: Any, did: str = None,
                           message_type: MessageType = MessageType.TEXT,
                           metadata: Dict[str, Any] = None) -> bool:
        """重写发送消息方法，同时支持存储和统计"""
        result = await super().send_message(group_id, content, did, message_type, metadata)

        if result:
            self.message_stats["sent_count"] += 1
            msg_type = message_type.value
            if msg_type not in self.message_stats["message_types"]:
                self.message_stats["message_types"][msg_type] = 0
            self.message_stats["message_types"][msg_type] += 1

        return result

    async def listen_group(self, group_id: str, callback: Callable[[Message], None],
                           did: str = None, message_types: List[MessageType] = None):
        """重写监听方法，同时支持存储和统计"""

        async def complete_callback(message: Message):
            # 更新统计
            self.message_stats["received_count"] += 1

            sender = message.sender_id
            if sender not in self.message_stats["senders"]:
                self.message_stats["senders"][sender] = 0
            self.message_stats["senders"][sender] += 1

            msg_type = message.type.value
            if msg_type not in self.message_stats["message_types"]:
                self.message_stats["message_types"][msg_type] = 0
            self.message_stats["message_types"][msg_type] += 1

            # 存储功能在父类的 listen_group 中已经处理
            # 调用原始回调
            await callback(message)

        # 调用 GroupMemberWithStorage 的 listen_group，它会处理存储
        await GroupMemberWithStorage.listen_group(self, group_id, complete_callback, did, message_types)

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        stats = self.message_stats.copy()
        stats["groups_joined"] = list(stats["groups_joined"])
        return stats

    def get_complete_info(self) -> Dict[str, Any]:
        """获取完整信息（存储 + 统计）"""
        return {
            "storage": self.get_storage_stats(),
            "stats": self.get_stats()
        }