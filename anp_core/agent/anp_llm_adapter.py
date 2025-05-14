# -*- coding: utf-8 -*-
"""OpenRouter LLM API适配器

提供与OpenRouter API交互的功能，用于发送消息和接收响应。
为开发者提供统一的事件基类和注册机制，便于自定义对接。
"""
import os
import logging
import httpx
import asyncio
from typing import Dict, Any, Tuple, Optional, Callable, Awaitable, List

class ANPEventBase:
    """
    事件基类，开发者可继承并实现handle方法。
    """
    def __init__(self):
        self._handlers: List[Callable[[str, str, Optional[str]], Awaitable[Tuple[int, Dict[str, Any]]]]] = []

    def register(self, handler: Callable[[str, str, Optional[str]], Awaitable[Tuple[int, Dict[str, Any]]]]):
        """
        注册事件处理函数。
        """
        self._handlers.append(handler)

    async def trigger(self, message: str, req_did: str, resp_did:str , requestport: str = None):
        """
        触发事件，依次调用所有注册的处理函数。
        """
        results = []
        for handler in self._handlers:
            result = await handler(message, req_did, resp_did, requestport)
            results.append(result)
        return results[-1] if results else (500, {"answer": "No handler registered"})

# 全局事件实例，开发者可直接注册自己的处理函数
resp_handle_request_event = ANPEventBase()

# 保留全局消息和事件
resp_handle_request_msgs = []
resp_handle_request_new_msg_event = asyncio.Event()

async def openrouter_handler(message: str, req_did: str = None, resp_did: str = None, requestport: str = None):
    """
    默认OpenRouter LLM处理函数，开发者可参考此实现自定义handler。
    """
    OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
    OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
    if not OPENROUTER_API_KEY:
        error_msg = "OpenRouter API key not configured"
        message_data = {
            "type": "anp_nlp",
            "user_message": message,
            "assistant_message": error_msg
        }
        await notify_chat_thread(message_data, did)
        return 500, {"answer": error_msg}
    agentname = os.environ.get('AGENT_NAME')

    prompt = f"你是{agentname}，一个智能的AI助手，你的任务是回答用户的问题。如果你不知道答案，你可以说“我不知道”，但不要试图编造答案。"
    if os.environ.get("prompts"):
        prompt = os.environ.get("prompts")

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "deepseek/deepseek-chat-v3-0324:free",
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": message}
        ],
        "max_tokens": 512
    }
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(OPENROUTER_API_URL, headers=headers, json=payload)
            if resp.status_code != 200:
                logging.error(f"OpenRouter error: {resp.text}")
                error_msg = f"OpenRouter query failed: {resp.status_code}"
                message_data = {
                    "type": "anp_nlp",
                    "user_message": message,
                    "assistant_message": error_msg
                }
                await notify_chat_thread(message_data, req_did)
                return resp.status_code, {"answer": error_msg}
            data = resp.json()
            agentname = os.environ.get('AGENT_NAME')
            if agentname is None:
                answer = data['choices'][0]['message']['content']
            else:
                answer = agentname + ":" + data['choices'][0]['message']['content']
            message_data = {
                "type": "anp_nlp",
                "user_message": message,
                "assistant_message": answer
            }
            await notify_chat_thread(message_data, req_did)
            if req_did is not None and resp_did is not None:
                return 200, {"answer": f"收到{req_did}的问题，回复如下：{answer}"}
            else:
                return 200, {"answer": f"{answer}"}
    except Exception as e:
        error_msg = f"白嫖的OpenRouter生气了:{e}"
        message_data = {
            "type": "anp_nlp",
            "user_message": message,
            "assistant_message": error_msg
        }
        await notify_chat_thread(message_data, req_did)
        return 500, {"answer": error_msg}

# 默认注册OpenRouter处理函数，开发者可按需替换
resp_handle_request_event.register(openrouter_handler)

async def resp_handle_request(message: str, req_did: str, resp_did: str,  requestport: str = None):
    """
    统一对外接口，触发事件。
    """
    return await resp_handle_request_event.trigger(message, req_did, resp_did, requestport)

async def notify_chat_thread(message_data: Dict[str, Any], did: str):
    global resp_handle_request_msgs, resp_handle_request_new_msg_event
    resp_handle_request_msgs.append(message_data)
    if len(resp_handle_request_msgs) > 50:
        resp_handle_request_msgs = resp_handle_request_msgs[-50:]
    resp_handle_request_new_msg_event.set()
    port = os.environ.get("PORT")
    print(f"\nANP-resp收自@{did}: {message_data['user_message']}")
    print(f"\nANP-resp从{port}返回: {message_data['assistant_message']}\n")
    # 注释掉重置事件的代码，让mcp_server.py中的监听器来清除事件
    # new_message_event.clear()

"""
使用说明：
1. 开发者只需继承ANPEventBase类，实现自己的handler函数，并通过resp_handle_request_event.register(handler)注册即可。
2. handler函数签名需为async def handler(message: str, did: str, requestport: str = None): ...
3. 通过resp_handle_request触发事件，自动调用所有已注册的handler。
4. 可参考openrouter_handler实现自定义业务逻辑。
"""