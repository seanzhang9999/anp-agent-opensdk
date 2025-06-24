from typing import List, Dict, Any
import os
import json
from fastapi.responses import JSONResponse
from anp_open_sdk.utils.log_base import  logging as logger

from fastapi import Request
import aiofiles


from anp_open_sdk.anp_sdk import LocalAgent


class DemoAgentRegistry:
    """演示用Agent注册器"""
    
    @staticmethod
    def register_api_handlers(agents: List[LocalAgent]) -> None:
        """注册API处理器"""
        if len(agents) < 2:
            logger.warning("智能体数量不足，无法注册所有API处理器")
            return

        agent1, agent2 = agents[0], agents[1]



        # 智能体的第一种API发布方式：装饰器
        @agent1.expose_api("/hello", methods=["GET"])
        async def hello_api(request_data, request:Request):
            return JSONResponse(
                content={
                "msg": f"{agent1.name}的/hello接口收到请求:",
                "param": request_data.get("params")
                },
                 status_code = 200
            )

        # 智能体的另一种API发布方式：显式注册
        async def info_api(request_data, request:Request):
            return JSONResponse(
                content={
                "msg": f"{agent2.name}的/info接口收到请求:",
                "param": request_data.get("params")
                },
                 status_code = 200
            )
        agent2.expose_api("/info", info_api, methods=["POST", "GET"])

    @staticmethod
    def register_message_handlers(agents: List[LocalAgent]) -> None:
        """注册消息处理器"""
        if len(agents) < 3:
            logger.warning("智能体数量不足，无法注册所有消息处理器")
            return

        agent1, agent2, agent3 = agents[0], agents[1], agents[2]

        @agent1.register_message_handler("text")
        async def handle_text1(msg):
            logger.debug(f"{agent1.name}收到text消息: {msg}")
            return {"reply": f"{agent1.name}回复:确认收到text消息:{msg.get('content')}"}

        async def handle_text2(msg):
            logger.debug(f"{agent2.name}收到text消息: {msg}")
            return {"reply": f"{agent2.name}回复:确认收到text消息:{msg.get('content')}"}
        agent2.register_message_handler("text", handle_text2)

        @agent3.register_message_handler("*")
        async def handle_any(msg):
            logger.debug(f"{agent3.name}收到*类型消息: {msg}")
            return {
                "reply": f"{agent3.name}回复:确认收到{msg.get('type')}类型"
                         f"{msg.get('message_type')}格式的消息:{msg.get('content')}"
            }

    @staticmethod
    def register_group_event_handlers(agents: List[LocalAgent]) -> None:
        """注册群组事件处理器"""
        for agent in agents:
            async def group_event_handler(group_id, event_type, event_data):
                logger.debug(f"{agent.name}收到群{group_id}的{event_type}事件，内容：{event_data}")
                await DemoAgentRegistry._save_group_message_to_file(agent, event_data)
            
            agent.register_group_event_handler(group_event_handler)

    @staticmethod
    async def _save_group_message_to_file(agent: LocalAgent, message: Dict[str, Any]):
        """保存群聊消息到文件"""
        message_file = UnifiedConfig.resolve_path(f"anp_sdk_demo/demo_data/{agent.name}_group_messages.json")
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