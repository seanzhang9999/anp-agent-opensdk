#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import Optional, Dict, Any
from urllib.parse import urlencode, quote
from loguru import logger
import aiohttp
import json
from anp_open_sdk.anp_sdk_utils import handle_response
from anp_open_sdk.service.anp_agent_api import agent_auth
import aiofiles
import asyncio

async def agent_msg_group_post(sdk, caller_agent: str, group_url: str, group_id: str, message: str):
 
    caller_agent_obj = sdk.get_agent(caller_agent)
    message = {
        "content": message or {}
    }
    url_params = {
        "req_did": caller_agent_obj.id,
        "group_id": group_id
    }
    url_params = urlencode(url_params)
    
    url = f"http://{group_url}/group/{group_id}/message?{url_params}"
    
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
async def agent_msg_group_members(sdk, caller_agent:str, group_url, group_id: str , action):
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
    url = f"http://{group_url}/group/{group_id}/members?{url_params}"
    
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

async def listen_group_messages(sdk, caller_agent:str, group_url ,group_id, message_file):
    """监听群聊消息并保存到文件
    
    Args:
        agent: 智能体实例
        group_id: 群组ID
        message_file: 消息保存的文件路径
    """
    caller_agent_obj = sdk.get_agent(caller_agent)
    url_params = {
        "req_did": caller_agent_obj.id,
    }
    url_params = urlencode(url_params)

    try:
        async with aiohttp.ClientSession() as session:
            url = f"http://{group_url}/group/{group_id}/connect?{url_params}"
            async with session.get(url) as response:
                async for line in response.content:
                    if line:
                        try:
                            decoded_line = line.decode("utf-8").strip()  # 确保 UTF-8 解码
                            if not decoded_line:  # 额外检查是否为空
                                continue  # 跳过空数据
                            # 确保数据格式正确
                            if decoded_line.startswith("data:"):
                                decoded_line = decoded_line.replace("data:", "", 1).strip()  # 去掉 "data:"
                            message = json.loads(decoded_line)  # 解析 JSON
                            async with aiofiles.open(message_file, 'a', encoding="utf-8") as f:
                                await f.write(json.dumps(message,ensure_ascii=False) + '\n')  # 异步写入
                        except json.JSONDecodeError:
                            logger.info("JSON 解析错误:", line.decode("utf-8"))  # 记录错误数据
    except asyncio.CancelledError:
        logger.info(f"{caller_agent} 的群聊监听已停止")
    except Exception as e:
        logger.error(f"{caller_agent} 的群聊监听发生错误: {e}")
