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

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..","..")))
from typing import Optional, Dict, Any
from urllib.parse import urlencode, quote
from loguru import logger
import aiohttp
import json
from anp_open_sdk.anp_sdk_utils import handle_response
from anp_open_sdk.service.agent_auth import agent_auth_two_way
import aiofiles
import asyncio

async def agent_msg_group_post(sdk, caller_agent: str,     group_hoster:str, group_url: str, group_id: str, message: str):
 
    caller_agent_obj = sdk.get_agent(caller_agent)
    message = {
        "content": message or {}
    }
    url_params = {
        "req_did": caller_agent_obj.id,
        "group_id": group_id
    }
    url_params = urlencode(url_params)
    group_hoster = quote(group_hoster)
    url = f"http://{group_url}/agent/group/{group_hoster}/{group_id}/message?{url_params}"
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=message) as response:
                status = response.status
                if status == 200:
                    response_data = await response.json()
                    return response_data
                else:
                    error = f"发送群组消息失败! 状态: {status}"
                    return {"error": error}
    except Exception as e:
        logger.error(f"发送群组消息时出错: {e}")
        return {"error": str(e)}
async def agent_msg_group_members(sdk, caller_agent:str, group_hoster:str ,  group_url,group_id: str , action):
    """向群组添加成员
    
    Args:
        sdk: ANPSDK 实例
        caller_agent: 调用方智能体ID
        group_url: 群组URL
        group_id: 群组ID
        members: 成员列表
        
    Returns:
        Dict: 响应结果
    """
    caller_agent_obj = sdk.get_agent(caller_agent)
    
    url_params = {
        "req_did": caller_agent_obj.id,
        "group_id": group_id
    }
    url_params = urlencode(url_params)
    group_hoster = quote(group_hoster)
    url = f"http://{group_url}/agent/group/{group_hoster}/{group_id}/members?{url_params}"
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=action) as response:
                status = response.status
                if status == 200:
                    response_data = await response.json()
                    return response_data
                else:
                    error = f"添加群组成员失败! 状态: {status}"
                    return {"error": error}
    except Exception as e:
        logger.error(f"添加群组成员时出错: {e}")
        return {"error": str(e)}



async def listen_group_messages(sdk, caller_agent: str, group_hoster:str, group_url, group_id, event_handlers=None):
    """
    监听群聊消息并通过事件类型分发给 LocalAgent 的群事件服务。
    Args:
        sdk: SDK实例
        caller_agent: 调用方智能体ID
        group_url: 群组URL
        group_id: 群组ID
        event_handlers: 兼容旧接口，优先使用 LocalAgent 注册的事件处理机制
    """
    caller_agent_obj = sdk.get_agent(caller_agent)
    url_params = {
        "req_did": caller_agent_obj.id,
    }
    url_params = urlencode(url_params)
    group_hoster = quote(group_hoster)
    try:
        async with aiohttp.ClientSession() as session:
            url = f"http://{group_url}/agent/group/{group_hoster}/{group_id}/connect?{url_params}"
            async with session.get(url) as response:
                async for line in response.content:
                    if line:
                        try:
                            decoded_line = line.decode("utf-8").strip()
                            if not decoded_line:
                                continue
                            # 移除 "data:" 前缀
                            if decoded_line.startswith("data:"):
                                decoded_line = decoded_line[5:].strip()
                            try:
                                import json
                                msg_obj = json.loads(decoded_line)
                                event_type = msg_obj.get("event_type") or msg_obj.get("type") or "*"
                                # 优先走 LocalAgent 的注册机制
                                if hasattr(caller_agent_obj, "_dispatch_group_event"):
                                    await caller_agent_obj._dispatch_group_event(group_id, event_type, msg_obj)
                                # 兼容旧接口
                                elif event_handlers and event_type in event_handlers:
                                    await event_handlers[event_type](msg_obj)
                                elif event_handlers and "*" in event_handlers:
                                    await event_handlers["*"](msg_obj)
                                else:
                                    logger.debug(f"未注册群事件处理函数")
                            except Exception as e:
                                logger.error(f"消息解析或分发出错: {e}")
                        except Exception as e:
                            logger.error(f"消息处理时出错: {e}")
    except asyncio.CancelledError:
        logger.info(f"{caller_agent} 的群聊监听已停止")
        # 添加资源清理代码
        try:
            # 清理会话资源
            if 'session' in locals() and session is not None:
                await session.close()
        except Exception as e:
            logger.error(f"清理资源时出错: {e}")
        # 重新抛出异常，让调用者知道任务已取消
        raise
    except Exception as e:
        logger.error(f"{caller_agent} 的群聊监听发生错误: {e}")
        # 清理资源
        try:
            if 'session' in locals() and session is not None:
                await session.close()
        except Exception as cleanup_error:
            logger.error(f"清理资源时出错: {cleanup_error}")
        await asyncio.sleep(3)  # 延迟后重连