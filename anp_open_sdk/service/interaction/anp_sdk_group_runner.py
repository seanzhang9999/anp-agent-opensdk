# Copyright 2024 ANP Open SDK Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from enum import Enum
import asyncio
import time
from anp_open_sdk.utils.log_base import  logging as logger

class MessageType(Enum):
    """消息类型枚举"""
    TEXT = "text"
    JOIN = "join"
    LEAVE = "leave"
    SYSTEM = "system"
    COMMAND = "command"

@dataclass
class Message:
    """群组消息"""
    type: MessageType
    content: Any
    sender_id: str
    group_id: str
    timestamp: float
    metadata: Dict[str, Any] = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "type": self.type.value,
            "content": self.content,
            "sender_id": self.sender_id,
            "group_id": self.group_id,
            "timestamp": self.timestamp,
            "metadata": self.metadata or {}
        }

@dataclass
class Agent:
    """Agent 信息"""
    id: str
    name: str
    port: int
    metadata: Dict[str, Any] = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "name": self.name,
            "port": self.port,
            "metadata": self.metadata or {}
        }

class GroupRunner(ABC):
    """GroupRunner 基类 - 开发者继承此类实现自己的群组逻辑"""

    def __init__(self, group_id: str):
        self.group_id = group_id
        self.agents: Dict[str, Agent] = {}
        self.listeners: Dict[str, asyncio.Queue] = {}  # agent_id -> queue
        self._running = False

    @abstractmethod
    async def on_agent_join(self, agent: Agent) -> bool:
        """处理 agent 加入请求

        Args:
            agent: 要加入的 Agent 信息

        Returns:
            True 允许加入，False 拒绝
        """
        pass

    @abstractmethod
    async def on_agent_leave(self, agent: Agent):
        """处理 agent 离开

        Args:
            agent: 离开的 Agent 信息
        """
        pass

    @abstractmethod
    async def on_message(self, message: Message) -> Optional[Message]:
        """处理消息

        Args:
            message: 接收到的消息

        Returns:
            可选的响应消息
        """
        pass

    async def broadcast(self, message: Message, exclude: List[str] = None):
        """广播消息给所有监听的 agent"""
        exclude = exclude or []
        message_dict = message.to_dict()

        for agent_id, queue in self.listeners.items():
            if agent_id not in exclude:
                try:
                    await queue.put(message_dict)
                except Exception as e:
                    logger.error(f"Failed to send message to {agent_id}: {e}")


    async def send_to_agent(self, agent_id: str, message: Message):
        """发送消息给特定 agent"""
        if agent_id in self.listeners:
            try:
                await self.listeners[agent_id].put(message.to_dict())
            except Exception as e:
                logger.error(f"Failed to send message to {agent_id}: {e}")

    async def remove_member(self, agent_id: str) -> bool:
        """移除成员"""
        if agent_id in self.agents:
            agent = self.agents[agent_id]
            await self.on_agent_leave(agent)
            del self.agents[agent_id]
            # 清理监听器
            if agent_id in self.listeners:
                del self.listeners[agent_id]
            return True
        return False

    def get_members(self) -> List[Agent]:
        """获取所有成员"""
        return list(self.agents.values())

    def get_member(self, agent_id: str) -> Optional[Agent]:
        """获取特定成员"""
        return self.agents.get(agent_id)

    def is_member(self, agent_id: str) -> bool:
        """检查是否是成员"""
        return agent_id in self.agents


    def register_listener(self, agent_id: str, queue: asyncio.Queue):
        """注册消息监听器"""
        self.listeners[agent_id] = queue
        logger.debug(f"Registered listener for {agent_id} in group {self.group_id}")

    def unregister_listener(self, agent_id: str):
        """注销消息监听器"""
        if agent_id in self.listeners:
            del self.listeners[agent_id]
            logger.debug(f"Unregistered listener for {agent_id} in group {self.group_id}")



    async def start(self):
        """启动 GroupRunner"""
        self._running = True
        logger.debug(f"GroupRunner for {self.group_id} started")

    async def stop(self):
        """停止 GroupRunner"""
        self._running = False
        # 通知所有成员群组关闭
        shutdown_msg = Message(
            type=MessageType.SYSTEM,
            content="Group is shutting down",
            sender_id="system",
            group_id=self.group_id,
            timestamp=time.time()
        )
        await self.broadcast(shutdown_msg)
        logger.debug(f"GroupRunner for {self.group_id} stopped")

class GroupManager:
    """群组管理器 - 管理所有 GroupRunner"""

    def __init__(self, sdk):
        self.sdk = sdk
        self.runners: Dict[str, GroupRunner] = {}
        self.custom_routes: Dict[str, str] = {}  # group_id -> custom_url_pattern

    def register_runner(self, group_id: str, runner_class: type[GroupRunner],
                       url_pattern: Optional[str] = None):
        """注册 GroupRunner"""
        if group_id in self.runners:
            logger.warning(f"GroupRunner for {group_id} already exists, replacing...")

        runner = runner_class(group_id)
        self.runners[group_id] = runner

        # 保存自定义路由模式
        if url_pattern:
            self.custom_routes[group_id] = url_pattern

        logger.debug(f"Registered GroupRunner for group {group_id}")

        # 启动 runner
        asyncio.create_task(runner.start())

    def unregister_runner(self, group_id: str):
        """注销 GroupRunner"""
        if group_id in self.runners:
            runner = self.runners[group_id]
            asyncio.create_task(runner.stop())
            del self.runners[group_id]
            if group_id in self.custom_routes:
                del self.custom_routes[group_id]
            logger.debug(f"Unregistered GroupRunner for group {group_id}")

    def get_runner(self, group_id: str) -> Optional[GroupRunner]:
        """获取群组的 runner"""
        return self.runners.get(group_id)

    def list_groups(self) -> List[str]:
        """列出所有群组"""
        return list(self.runners.keys())