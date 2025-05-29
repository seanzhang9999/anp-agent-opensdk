import asyncio
import json
from datetime import datetime
from typing import Dict, Any, List
import os

from anp_open_sdk.anp_sdk import LocalAgent
from anp_open_sdk.config.path_resolver import path_resolver
from loguru import logger
import aiofiles


async def demo_save_group_msg_to_file(agent: LocalAgent, message: Dict[str, Any]):
    """保存群聊消息到文件"""
    message_file = path_resolver.resolve_path(f"{agent.name}_group_messages.json")
    try:
        # 确保目录存在
        message_dir = os.path.dirname(message_file)
        if message_dir and not os.path.exists(message_dir):
            os.makedirs(message_dir, exist_ok=True)

        # 追加消息到文件
        async with aiofiles.open(message_file, 'a', encoding='utf-8') as f:
            await f.write(json.dumps(message, ensure_ascii=False) + '\n')
    except Exception as e:
        logger.error(f"保存群聊消息到文件时出错: {e}")


class DemoGroupMember:
    """群组成员处理器"""
    
    def __init__(self, agent: LocalAgent):
        self.agent = agent
    
    async def handle_group_message(self, msg: Dict[str, Any]):
        """处理群组消息"""
        await demo_save_group_msg_to_file(self.agent, msg)
        logger.info(f"{self.agent.name}收到群聊消息: {msg}")
        return {"status": "success"}

    async def _group_event_handler(self, group_id, event_type, event_data):
        """群组事件处理器"""
        logger.info(f"收到群{group_id}的{event_type}事件，内容：{event_data}")
        await self.handle_group_message(event_data)

    def register_group_event_handler(self):
        """注册群组事件处理器"""
        self.agent.register_group_event_handler(self._group_event_handler)


class DemoGroupRunner:
    """
    演示群组运行器
    
    主要功能：
    1. 群组成员管理 - 添加/移除成员
    2. 群组消息处理 - 接收和分发群组消息
    3. SSE连接管理 - 处理实时消息推送连接
    4. 事件记录 - 保存群组活动日志
    """
    
    def __init__(self, agent: LocalAgent, group_id: str):
        self.agent = agent
        self.group_id = group_id
        self._ensure_group_attributes()

    def _ensure_group_attributes(self):
        """确保群组属性存在"""
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

    def register_group_handlers(self):
        """注册群组处理器"""
        self.agent.register_message_handler("group_message", self._group_message_handler)
        self.agent.register_message_handler("group_connect", self._group_connect_handler)
        self.agent.register_message_handler("group_members", self._group_members_handler)

    async def _group_message_handler(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """处理群组消息"""
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
            await demo_save_group_msg_to_file(self.agent, message)
        return {"status": "success"}

    async def _group_connect_handler(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """处理群组连接"""
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
        """处理群组成员管理"""
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

    def _create_event_generator(self, group_id: str, req_did: str):
        """创建事件生成器"""
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
                            await demo_save_group_msg_to_file(self.agent, message)
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
        """保存成员事件"""
        event = {
            "type": "member_event",
            "group_id": group_id,
            "action": action,
            "members": members,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        await demo_save_group_msg_to_file(self.agent, event)

    async def _save_connection_event(self, group_id: str, req_did: str, status: str):
        """保存连接事件"""
        event = {
            "type": "connection_event",
            "group_id": group_id,
            "member": req_did,
            "status": status,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        await demo_save_group_msg_to_file(self.agent, event)