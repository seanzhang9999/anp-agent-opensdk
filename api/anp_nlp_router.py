"""Chat API router for OpenRouter LLM chat relay."""
import os
import logging
import httpx
import asyncio
from fastapi import APIRouter, Request, HTTPException, Header, WebSocket, WebSocketDisconnect, Depends
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from agent_connect.authentication import (
    verify_auth_header_signature,
    resolve_did_wba_document,
    extract_auth_header_parts,
    create_did_wba_document,
    DIDWbaAuthHeader
)

from core.config import Settings

# 导入新创建的适配器模块中的函数
from anp_core.agent.anp_llm_adapter import resp_handle_request, resp_handle_request_msgs, resp_handle_request_new_msg_event, notify_chat_thread
import json

router = APIRouter(tags=["chat"])

class ChatRequest(BaseModel):
    message: str
    
class ConnectionManager:
    def __init__(self):
        # 存储所有活跃的WebSocket连接
        self.active_connections: Dict[str, WebSocket] = {}
        
    async def connect(self, websocket: WebSocket, client_id: str):
        await websocket.accept()
        self.active_connections[client_id] = websocket
        await self.broadcast({"type": "system", "message": f"用户 {client_id} 已连接", "sender": "system"})
        
    def disconnect(self, client_id: str):
        if client_id in self.active_connections:
            del self.active_connections[client_id]
            
    async def send_personal_message(self, message: Dict[str, Any], client_id: str):
        if client_id in self.active_connections:
            await self.active_connections[client_id].send_json(message)
            
    async def broadcast(self, message: Dict[str, Any]):
        # 向所有连接的客户端广播消息
        for client_id, connection in self.active_connections.items():
            await connection.send_json(message)
            
    async def broadcast_except_sender(self, message: Dict[str, Any], sender_id: str):
        # 向除了发送者之外的所有客户端广播消息
        for client_id, connection in self.active_connections.items():
            if client_id != sender_id:
                await connection.send_json(message)
                
    def get_active_clients(self) -> List[str]:
        # 获取所有活跃客户端ID列表
        return list(self.active_connections.keys())

# 创建连接管理器实例
manager = ConnectionManager()


def get_and_validate_port(request) -> str:
    """
    从请求中获取端口号。
    
    Args:
        request: FastAPI request对象或WebSocket scope
        
    Returns:
        str: 请求中的端口号
    """
    # 检查是否为WebSocket scope
    if isinstance(request, dict) and "headers" in request:
        # 从WebSocket scope中获取host
        for header in request["headers"]:
            if header[0] == b"host":
                host = header[1].decode()
                if ":" in host:
                    return host.split(":")[1]
                return "80"  # 默认HTTP端口
    else:
        # 从HTTP请求中获取host
        host = request.headers.get('host', '')
        if ":" in host:
            return host.split(":")[1]
        return "80"  # 默认HTTP端口

@router.post("/anp-nlp/", summary="ANP的NLP接口，Chat with OpenRouter LLM")
async def anp_nlp_service(
    request: Request,
    chat_req: ChatRequest,
    authorization: Optional[str] = Header(None)
):
    """
    Relay chat message to OpenRouter LLM and return the response.
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    if not chat_req.message:
        raise HTTPException(status_code=400, detail="Empty message")
        
    resp_did = request.headers.get("resp_did")
    req_did = request.headers.get("req_did")
    requestport = get_and_validate_port(request)
    
    # 调用封装的OpenRouter请求函数
    status_code, response_data = await resp_handle_request(chat_req.message, req_did,resp_did, requestport)
    
    

    if status_code != 200:
        raise HTTPException(status_code=status_code, detail=response_data["answer"])
        
    return JSONResponse(content=response_data)


async def sse_event_generator(message: str, req_did: str, resp_did: str, requestport: str):
    """
    生成SSE事件流
    """
    try:
        # 发送初始事件
        yield f"data: {json.dumps({'type': 'start', 'message': '开始处理请求'})}\n\n"
        
        
        # 调用封装的OpenRouter请求函数
        status_code, response_data = await resp_handle_request(message, req_did, resp_did, requestport)
        
        if status_code != 200:
            error_message = response_data.get("answer", "未知错误")
            yield f"data: {json.dumps({'type': 'error', 'message': error_message})}\n\n"
        else:
            # 发送成功响应
            answer = response_data.get("answer", "")
            # 模拟流式输出，将回答分成多个小块发送
            chunk_size = 10  # 每个块的字符数
            for i in range(0, len(answer), chunk_size):
                chunk = answer[i:i+chunk_size]
                yield f"data: {json.dumps({'type': 'chunk', 'content': chunk})}\n\n"
                await asyncio.sleep(0.1)  # 添加小延迟模拟流式效果
            
            # 发送完整消息
            yield f"data: {json.dumps({'type': 'message', 'content': answer})}\n\n"
        
        # 发送结束事件
        yield f"data: {json.dumps({'type': 'end', 'message': '处理完成'})}\n\n"
    except Exception as e:
        logging.error(f"SSE事件生成错误: {str(e)}")
        error_msg = f"服务器处理错误: {str(e)}"
        yield f"data: {json.dumps({'type': 'error', 'message': error_msg})}\n\n"
        yield f"data: {json.dumps({'type': 'end', 'message': '处理异常终止'})}\n\n"

@router.post("/anp-nlp/sse/{user_id}/", summary="ANP的NLP接口(SSE版本)，使用Server-Sent Events流式返回OpenRouter LLM响应")
async def anp_nlp_sse_service(
    user_id: str,
    request: Request,
    chat_req: ChatRequest,
    authorization: Optional[str] = Header(None)
):
    """
    使用Server-Sent Events (SSE)流式返回OpenRouter LLM响应。
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    if not chat_req.message:
        raise HTTPException(status_code=400, detail="Empty message")
        
    resp_did = user_id
    req_did = request.headers.get("DID")
    requestport = get_and_validate_port(request)
    
    # 返回SSE流
    return StreamingResponse(
        sse_event_generator(chat_req.message, req_did, resp_did, requestport),
        media_type="text/event-stream"
    )

@router.websocket("/anp_nlp/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    """
    WebSocket端点，支持多人接入和消息转发
    """
    await manager.connect(websocket, client_id)
    try:
        # 发送当前在线用户列表
        await manager.send_personal_message(
            {
                "type": "system", 
                "message": "已连接到服务器", 
                "active_clients": manager.get_active_clients(),
                "sender": "system"
            },
            client_id
        )
        
        while True:
            # 接收客户端消息
            data = await websocket.receive_json()
            
            # 处理不同类型的消息
            if "type" in data and "message" in data:
                if data["type"] == "chat":
                    # 聊天消息，转发给其他客户端
                    message_data = {
                        "type": "chat",
                        "message": data["message"],
                        "sender": client_id,
                        "timestamp": asyncio.get_event_loop().time()
                    }
                    
                    # 如果指定了接收者，则只发送给特定接收者
                    if "recipient" in data and data["recipient"] in manager.active_connections:
                        await manager.send_personal_message(message_data, data["recipient"])
                        # 同时发送给发送者自己，作为确认
                        await manager.send_personal_message(message_data, client_id)
                    else:
                        # 否则广播给所有人
                        await manager.broadcast(message_data)
                        
                elif data["type"] == "nlp":
                    # NLP请求，调用OpenRouter处理
                    message = data["message"]
                    resp_did = data.get("recipient", "all")
                    req_did = client_id
                    requestport = get_and_validate_port(websocket.scope)
                    
                    # 异步处理NLP请求
                    asyncio.create_task(process_nlp_request(message, req_did, resp_did, requestport, client_id))
                    
                elif data["type"] == "system":
                    # 系统消息，例如请求用户列表
                    if data["message"] == "get_users":
                        await manager.send_personal_message(
                            {
                                "type": "system", 
                                "message": "用户列表", 
                                "active_clients": manager.get_active_clients(),
                                "sender": "system"
                            },
                            client_id
                        )
            
    except WebSocketDisconnect:
        manager.disconnect(client_id)
        await manager.broadcast(
            {
                "type": "system", 
                "message": f"用户 {client_id} 已断开连接", 
                "sender": "system"
            }
        )
    except Exception as e:
        logging.error(f"WebSocket错误: {str(e)}")
        manager.disconnect(client_id)

async def process_nlp_request(message: str, req_did: str, resp_did: str, requestport: str, client_id: str):
    """
    处理NLP请求并通过WebSocket返回结果
    """
    try:
        # 通知客户端开始处理
        await manager.send_personal_message(
            {"type": "nlp_status", "status": "processing", "message": "正在处理NLP请求"},
            client_id
        )
        
        # 调用OpenRouter处理函数
        status_code, response_data = await resp_handle_request(message, req_did, resp_did, requestport)
        
        if status_code != 200:
            # 处理错误
            error_message = response_data.get("answer", "未知错误")
            await manager.send_personal_message(
                {"type": "nlp_error", "message": error_message},
                client_id
            )
        else:
            # 处理成功响应
            answer = response_data.get("answer", "")
            
            # 如果指定了接收者，则只发送给特定接收者
            if resp_did != "all" and resp_did in manager.active_connections:
                await manager.send_personal_message(
                    {"type": "nlp_response", "message": answer, "sender": "system", "recipient": resp_did},
                    resp_did
                )
                # 同时发送给请求者
                await manager.send_personal_message(
                    {"type": "nlp_response", "message": answer, "sender": "system", "recipient": resp_did},
                    client_id
                )
            else:
                # 广播给所有人
                await manager.broadcast(
                    {"type": "nlp_response", "message": answer, "sender": "system"}
                )
    except Exception as e:
        logging.error(f"处理NLP请求错误: {str(e)}")
        await manager.send_personal_message(
            {"type": "nlp_error", "message": f"处理NLP请求错误: {str(e)}"},
            client_id
        )

@router.post("/ws/broadcast-message/", summary="服务端广播消息给所有WebSocket客户端")
async def broadcast_message(request: Request):
    """
    服务端API，用于广播消息给所有连接的WebSocket客户端
    """
    try:
        data = await request.json()
        message = data.get("message")
        message_type = data.get("type", "system")
        
        if not message:
            raise HTTPException(status_code=400, detail="消息内容不能为空")
            
        # 广播消息给所有客户端
        await manager.broadcast({
            "type": message_type,
            "message": message,
            "sender": "server"
        })
        
        return JSONResponse(content={"status": "success", "message": "消息已广播"})
    except Exception as e:
        logging.error(f"广播消息错误: {str(e)}")
        raise HTTPException(status_code=500, detail=f"广播消息错误: {str(e)}")