# Agent 端 SDK 用于简化 agent 与群组的交互
import asyncio
import json
import time  # 添加缺失的导入

import aiohttp
from typing import Dict, Any, Callable, List
from anp_open_sdk.service.interaction.anp_sdk_group_runner import Message, MessageType

class GroupMemberSDK:
    """Agent 端的群组 SDK"""

    def __init__(self, agent_id: str, port: int, base_url: str = "http://localhost",
                 use_local_optimization: bool = True):
        self.agent_id = agent_id
        self.port = port
        self.base_url = base_url
        self.use_local_optimization = use_local_optimization
        self._listeners: Dict[str, asyncio.Task] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._local_sdk = None

    def set_local_sdk(self, sdk):
        """设置本地 SDK 实例（用于本地优化）"""
        self._local_sdk = sdk

    async def join_group(self, group_id: str, did: str = None,
                        name: str = None, metadata: Dict[str, Any] = None) -> bool:
        """加入群组"""
        if self.use_local_optimization and self._local_sdk:
            # 本地优化路径
            runner = self._local_sdk.get_group_runner(group_id)
            if runner:
                from anp_open_sdk.service.interaction.anp_sdk_group_runner import Agent
                agent = Agent(
                    id=self.agent_id,
                    name=name or self.agent_id,
                    port=self.port,
                    metadata=metadata or {}
                )
                allowed = await runner.on_agent_join(agent)
                if allowed:
                    runner.agents[self.agent_id] = agent
                return allowed

        # HTTP 请求路径
        url = f"{self.base_url}:{self.port}/agent/group/{did or 'default'}/{group_id}/join"
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json={"name": name or self.agent_id, "metadata": metadata or {}},
                params={"req_did": self.agent_id}
            ) as resp:
                result = await resp.json()
                return result.get("status") == "success"

    async def leave_group(self, group_id: str, did: str = None) -> bool:
        """离开群组"""
        if self.use_local_optimization and self._local_sdk:
            # 本地优化路径
            runner = self._local_sdk.get_group_runner(group_id)
            if runner:
                return await runner.remove_member(self.agent_id)

        # HTTP 请求路径
        url = f"{self.base_url}:{self.port}/agent/group/{did or 'default'}/{group_id}/leave"
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json={},
                params={"req_did": self.agent_id}
            ) as resp:
                result = await resp.json()
                return result.get("status") == "success"

    async def send_message(self, group_id: str, content: Any, did: str = None,
                          message_type: MessageType = MessageType.TEXT,
                          metadata: Dict[str, Any] = None) -> bool:
        """发送消息到群组"""
        if self.use_local_optimization and self._local_sdk:
            # 本地优化路径
            runner = self._local_sdk.get_group_runner(group_id)
            if runner:
                message = Message(
                    type=message_type,
                    content=content,
                    sender_id=self.agent_id,
                    group_id=group_id,
                    timestamp=time.time(),
                    metadata=metadata
                )
                await runner.on_message(message)
                return True

        # HTTP 请求路径
        url = f"{self.base_url}:{self.port}/agent/group/{did or 'default'}/{group_id}/message"
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json={"content": content, "metadata": metadata or {}},
                params={"req_did": self.agent_id}
            ) as resp:
                result = await resp.json()
                return result.get("status") == "success"

    async def listen_group(self, group_id: str, callback: Callable[[Message], None],
                          did: str = None, message_types: List[MessageType] = None):
        """监听群组消息"""
        if self.use_local_optimization and self._local_sdk:
            # 本地优化路径
            runner = self._local_sdk.get_group_runner(group_id)
            if runner:
                queue = asyncio.Queue()
                runner.register_listener(self.agent_id, queue)

                async def local_listener():
                    while True:
                        message_dict = await queue.get()
                        message = Message(
                            type=MessageType(message_dict["type"]),
                            content=message_dict["content"],
                            sender_id=message_dict["sender_id"],
                            group_id=message_dict["group_id"],
                            timestamp=message_dict["timestamp"],
                            metadata=message_dict.get("metadata", {})
                        )
                        if message_types is None or message.type in message_types:
                            await callback(message)

                task = asyncio.create_task(local_listener())
                self._listeners[group_id] = task
                return

        # HTTP SSE 路径
        url = f"{self.base_url}:{self.port}/agent/group/{did or 'default'}/{group_id}/connect"

        async def sse_listener():
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    params={"req_did": self.agent_id}
                ) as resp:
                    async for line in resp.content:
                        if line.startswith(b'data: '):
                            data = json.loads(line[6:].decode())
                            message = Message(
                                type=MessageType(data["type"]),
                                content=data["content"],
                                sender_id=data["sender_id"],
                                group_id=data["group_id"],
                                timestamp=data["timestamp"],
                                metadata=data.get("metadata", {})
                            )
                            if message_types is None or message.type in message_types:
                                await callback(message)

        task = asyncio.create_task(sse_listener())
        self._listeners[group_id] = task

    def stop_listening(self, group_id: str):
        """停止监听群组消息"""
        if group_id in self._listeners:
            self._listeners[group_id].cancel()
            del self._listeners[group_id]

        if self.use_local_optimization and self._local_sdk:
            runner = self._local_sdk.get_group_runner(group_id)
            if runner:
                runner.unregister_listener(self.agent_id)

    async def get_members(self, group_id: str, did: str = None) -> List[Dict[str, Any]]:
        """获取群组成员列表"""
        if self.use_local_optimization and self._local_sdk:
            # 本地优化路径
            runner = self._local_sdk.get_group_runner(group_id)
            if runner:
                return [agent.to_dict() for agent in runner.get_members()]

        # HTTP 请求路径
        url = f"{self.base_url}:{self.port}/agent/group/{did or 'default'}/{group_id}/members"
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                params={"req_did": self.agent_id}
            ) as resp:
                result = await resp.json()
                return result.get("members", [])