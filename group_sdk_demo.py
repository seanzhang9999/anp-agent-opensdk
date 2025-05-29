import asyncio
import threading

from pydantic.v1.networks import host_regex

from anp_open_sdk.anp_sdk import ANPSDK
from anp_open_sdk.anp_sdk_group_runner import GroupRunner, Message, MessageType, Agent
from anp_open_sdk.anp_sdk_group_member import GroupMemberSDK
from anp_open_sdk.agent_types import LocalAgent
from anp_sdk_demo import demo_load_agents
import time  # 添加缺失的导入


# 自定义 GroupRunner 实现
class ChatRoomRunner(GroupRunner):
    """简单聊天室实现"""

    async def on_agent_join(self, agent: Agent) -> bool:
        # 广播加入消息
        await self.broadcast(Message(
            type=MessageType.SYSTEM,
            content=f"{agent.name} joined the chat",
            sender_id="system",
            group_id=self.group_id,
            timestamp=time.time()
        ))
        return True

    async def on_agent_leave(self, agent: Agent):
        await self.broadcast(Message(
            type=MessageType.SYSTEM,
            content=f"{agent.name} left the chat",
            sender_id="system",
            group_id=self.group_id,
            timestamp=time.time()
        ))

    async def on_message(self, message: Message):
        # 广播消息给所有人（除了发送者）
        await self.broadcast(message, exclude=[message.sender_id])

class ModeratedChatRunner(GroupRunner):
    """带审核的聊天室"""

    def __init__(self, group_id: str):
        super().__init__(group_id)
        self.banned_words = ["spam", "abuse"]
        self.moderators = []

    async def on_agent_join(self, agent: Agent) -> bool:
        # 检查黑名单
        if agent.metadata and agent.metadata.get("banned"):
            return False

        # 第一个加入的是管理员
        if not self.agents:
            agent.metadata = agent.metadata or {}
            agent.metadata["role"] = "moderator"
            self.moderators.append(agent.id)

        await self.broadcast(Message(
            type=MessageType.SYSTEM,
            content=f"{agent.name} joined as {agent.metadata.get('role', 'member')}",
            sender_id="system",
            group_id=self.group_id,
            timestamp=time.time()
        ))
        return True

    async def on_agent_leave(self, agent: Agent):
        """处理 agent 离开 - 实现抽象方法"""
        # 如果是管理员离开，移除管理员权限
        if agent.id in self.moderators:
            self.moderators.remove(agent.id)

        # 广播离开消息
        await self.broadcast(Message(
            type=MessageType.SYSTEM,
            content=f"{agent.name} left the moderated chat",
            sender_id="system",
            group_id=self.group_id,
            timestamp=time.time()
        ))

    async def on_message(self, message: Message):
        # 内容审核
        if any(word in message.content.lower() for word in self.banned_words):
            await self.send_to_agent(message.sender_id, Message(
                type=MessageType.SYSTEM,
                content="Your message contains banned words",
                sender_id="system",
                group_id=self.group_id,
                timestamp=time.time()
            ))
            return

        # 广播消息
        await self.broadcast(message, exclude=[message.sender_id])

async def main():
    # 创建并启动 SDK
    sdk = ANPSDK()
    agents = demo_load_agents(sdk)
    agent1 = agents[0]
    sdk.register_agent(agent1)

    # 注册不同类型的 GroupRunner
    sdk.register_group_runner("chatroom", ChatRoomRunner)
    sdk.register_group_runner("moderated_chat", ModeratedChatRunner)

    # 在后台线程启动服务器
    def start_server_in_thread():
        sdk.start_server()

    server_thread = threading.Thread(target=start_server_in_thread, daemon=True)
    server_thread.start()

    # 等待服务器启动
    await asyncio.sleep(3)
    print("Server started, beginning demo...")

    # 创建几个 agent 客户端

    agent2 = agents[1]
    agent3 = agents[2]
    sdk.register_agent(agent2)
    sdk.register_agent(agent3)

    host , port  = ANPSDK.get_did_host_port_from_did(agent2.id)

    alice = GroupMemberSDK(agent2.id, port)

    host , port  = ANPSDK.get_did_host_port_from_did(agent3.id)

    bob = GroupMemberSDK(agent3.id, port)

    # 设置本地 SDK（用于本地优化）
    alice.set_local_sdk(sdk)
    bob.set_local_sdk(sdk)

    # 定义消息处理回调
    async def alice_handler(message: Message):
        print(f"[Alice] {message.sender_id}: {message.content}")

    async def bob_handler(message: Message):
        print(f"[Bob] {message.sender_id}: {message.content}")

    # 加入群组
    await alice.join_group("chatroom", name="Alice")
    await bob.join_group("chatroom", name="Bob")

    # 开始监听消息
    await alice.listen_group("chatroom", alice_handler)
    await bob.listen_group("chatroom", bob_handler)

    # 发送消息
    await asyncio.sleep(1)
    await alice.send_message("chatroom", "Hello everyone!")
    await bob.send_message("chatroom", "Hi Alice!")

    # 查看成员列表
    members = await alice.get_members("chatroom")
    print(f"Chat room members: {members}")

    # 测试带审核的聊天室
    await alice.join_group("moderated_chat", name="Alice")
    await alice.listen_group("moderated_chat", alice_handler)

    await alice.send_message("moderated_chat", "This is a normal message")
    await alice.send_message("moderated_chat", "This contains spam")  # 将被拦截

    # 运行一段时间
    await asyncio.sleep(10)

    # 清理
    alice.stop_listening("chatroom")
    bob.stop_listening("chatroom")
    await alice.leave_group("chatroom")
    await bob.leave_group("chatroom")

    # 停止服务器
    sdk.stop_server()

if __name__ == "__main__":
    asyncio.run(main())

