import asyncio
import json
import logging
import uuid
from typing import Dict, Any, List, Set, Optional
from datetime import datetime

import websockets
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, HTTPException, Depends
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ws_proxy_server")

# 创建FastAPI应用
app = FastAPI(title="ANP WebSocket代理服务器")

# 添加CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 存储连接的客户端
class ProxyManager:
    def __init__(self):
        self.clients = {}  # did -> WebSocket连接
        self.client_info = {}  # did -> 客户端信息
        self.sse_clients = {}  # did -> Set[client_id]
        self.message_queue = {}  # did -> List[消息]
    
    def register_client(self, did: str, websocket: WebSocket, info: Dict[str, Any]):
        """注册WebSocket客户端"""
        self.clients[did] = websocket
        self.client_info[did] = {
            "connected_at": datetime.now().isoformat(),
            "last_active": datetime.now().isoformat(),
            "ip": info.get("ip", "unknown"),
            "user_agent": info.get("user_agent", "unknown"),
            "apis": info.get("apis", []),
            "message_handlers": info.get("message_handlers", [])
        }
        if did not in self.message_queue:
            self.message_queue[did] = []
        if did not in self.sse_clients:
            self.sse_clients[did] = set()
        logger.info(f"客户端注册: {did}")
    
    def unregister_client(self, did: str):
        """注销WebSocket客户端"""
        if did in self.clients:
            del self.clients[did]
            logger.info(f"客户端注销: {did}")
    
    def register_sse_client(self, did: str, client_id: str):
        """注册SSE客户端"""
        if did not in self.sse_clients:
            self.sse_clients[did] = set()
        self.sse_clients[did].add(client_id)
        logger.info(f"SSE客户端注册: {did} - {client_id}")
    
    def unregister_sse_client(self, did: str, client_id: str):
        """注销SSE客户端"""
        if did in self.sse_clients and client_id in self.sse_clients[did]:
            self.sse_clients[did].remove(client_id)
            logger.info(f"SSE客户端注销: {did} - {client_id}")
    
    def is_client_connected(self, did: str) -> bool:
        """检查客户端是否连接"""
        return did in self.clients
    
    def get_client_info(self, did: str) -> Optional[Dict[str, Any]]:
        """获取客户端信息"""
        return self.client_info.get(did)
    
    def update_client_activity(self, did: str):
        """更新客户端活动时间"""
        if did in self.client_info:
            self.client_info[did]["last_active"] = datetime.now().isoformat()
    
    def add_message_to_queue(self, did: str, message: Dict[str, Any]):
        """添加消息到队列"""
        if did not in self.message_queue:
            self.message_queue[did] = []
        self.message_queue[did].append({
            "timestamp": datetime.now().isoformat(),
            "message": message
        })
        # 限制队列大小
        if len(self.message_queue[did]) > 100:
            self.message_queue[did] = self.message_queue[did][-100:]
    
    def get_messages(self, did: str) -> List[Dict[str, Any]]:
        """获取消息队列"""
        return self.message_queue.get(did, [])
    
    def get_all_clients(self) -> Dict[str, Dict[str, Any]]:
        """获取所有客户端信息"""
        return self.client_info

# 创建代理管理器实例
proxy_manager = ProxyManager()

# 请求模型
class MessageRequest(BaseModel):
    req_did: str
    resp_did: str
    type: str
    content: Any
    timestamp: Optional[str] = None

class ApiRequest(BaseModel):
    req_did: str
    resp_did: str
    api_path: str
    method: str = "GET"
    params: Dict[str, Any] = {}

# WebSocket连接处理
@app.websocket("/ws/proxy")
async def websocket_proxy(websocket: WebSocket):
    await websocket.accept()
    did = None
    
    try:
        # 等待客户端发送注册消息
        registration = await websocket.receive_json()
        did = registration.get("did")
        
        if not did:
            await websocket.send_json({"status": "error", "message": "缺少DID标识符"})
            await websocket.close()
            return
        
        # 注册客户端
        proxy_manager.register_client(did, websocket, {
            "ip": websocket.client.host,
            "user_agent": websocket.headers.get("user-agent", "unknown"),
            "apis": registration.get("apis", []),
            "message_handlers": registration.get("message_handlers", [])
        })
        
        # 发送确认消息
        await websocket.send_json({"status": "connected", "message": "代理连接成功"})
        
        # 处理消息
        while True:
            message = await websocket.receive_json()
            proxy_manager.update_client_activity(did)
            
            # 处理来自客户端的响应消息
            if message.get("type") == "response":
                # 这是对之前请求的响应，可以存储或转发
                proxy_manager.add_message_to_queue(did, message)
            else:
                # 其他类型的消息，可以根据需要处理
                logger.info(f"收到来自 {did} 的消息: {message}")
    
    except WebSocketDisconnect:
        logger.info(f"WebSocket客户端断开连接: {did}")
    except Exception as e:
        logger.error(f"WebSocket处理错误: {e}")
    finally:
        if did:
            proxy_manager.unregister_client(did)

# HTTP消息代理
@app.post("/api/message")
async def proxy_message(request: MessageRequest):
    resp_did = request.resp_did
    
    # 检查目标客户端是否连接
    if not proxy_manager.is_client_connected(resp_did):
        return JSONResponse(
            status_code=404,
            content={"status": "error", "message": f"目标DID {resp_did} 未连接到代理服务器"}
        )
    
    # 构建消息
    message = {
        "type": "message",
        "req_did": request.req_did,
        "resp_did": resp_did,
        "content": request.content,
        "message_type": request.type,
        "timestamp": request.timestamp or datetime.now().isoformat(),
        "proxy_id": str(uuid.uuid4())
    }
    
    try:
        # 获取WebSocket连接
        websocket = proxy_manager.clients[resp_did]
        
        # 发送消息到客户端
        await websocket.send_json(message)
        
        # 等待响应（这里可以设置超时）
        for _ in range(30):  # 最多等待30秒
            await asyncio.sleep(1)
            
            # 检查消息队列中是否有响应
            messages = proxy_manager.get_messages(resp_did)
            for msg in reversed(messages):  # 从最新的消息开始检查
                if msg["message"].get("proxy_id") == message["proxy_id"] and msg["message"].get("type") == "response":
                    return JSONResponse(content=msg["message"]["content"])
        
        # 超时
        return JSONResponse(
            status_code=504,
            content={"status": "error", "message": "请求超时"}
        )
    
    except Exception as e:
        logger.error(f"消息代理错误: {e}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)}
        )

# API代理
@app.post("/api/proxy/{path:path}")
async def proxy_api(path: str, request: ApiRequest):
    resp_did = request.resp_did
    
    # 检查目标客户端是否连接
    if not proxy_manager.is_client_connected(resp_did):
        return JSONResponse(
            status_code=404,
            content={"status": "error", "message": f"目标DID {resp_did} 未连接到代理服务器"}
        )
    
    # 构建API请求
    api_request = {
        "type": "api_call",
        "req_did": request.req_did,
        "resp_did": resp_did,
        "api_path": request.api_path or path,
        "method": request.method,
        "params": request.params,
        "proxy_id": str(uuid.uuid4())
    }
    
    try:
        # 获取WebSocket连接
        websocket = proxy_manager.clients[resp_did]
        
        # 发送API请求到客户端
        await websocket.send_json(api_request)
        
        # 等待响应（这里可以设置超时）
        for _ in range(30):  # 最多等待30秒
            await asyncio.sleep(1)
            
            # 检查消息队列中是否有响应
            messages = proxy_manager.get_messages(resp_did)
            for msg in reversed(messages):  # 从最新的消息开始检查
                if msg["message"].get("proxy_id") == api_request["proxy_id"] and msg["message"].get("type") == "response":
                    return JSONResponse(content=msg["message"]["content"])
        
        # 超时
        return JSONResponse(
            status_code=504,
            content={"status": "error", "message": "请求超时"}
        )
    
    except Exception as e:
        logger.error(f"API代理错误: {e}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)}
        )

# SSE连接
@app.get("/sse/connect/{did}")
async def sse_connect(did: str, request: Request):
    # 检查目标客户端是否连接
    if not proxy_manager.is_client_connected(did):
        return JSONResponse(
            status_code=404,
            content={"status": "error", "message": f"目标DID {did} 未连接到代理服务器"}
        )
    
    client_id = str(uuid.uuid4())
    
    async def event_generator():
        try:
            # 注册SSE客户端
            proxy_manager.register_sse_client(did, client_id)
            
            # 发送连接成功消息
            yield f"data: {json.dumps({'status': 'connected', 'client_id': client_id})}\n\n"
            
            # 通知内网客户端有新的SSE连接
            if did in proxy_manager.clients:
                await proxy_manager.clients[did].send_json({
                    "type": "sse_connect",
                    "client_id": client_id
                })
            
            # 保持连接并发送消息
            last_message_count = 0
            while True:
                await asyncio.sleep(1)
                
                # 检查是否有新消息
                messages = proxy_manager.get_messages(did)
                if len(messages) > last_message_count:
                    # 发送新消息
                    for i in range(last_message_count, len(messages)):
                        msg = messages[i]
                        if msg["message"].get("type") == "sse_message":
                            yield f"data: {json.dumps(msg['message']['content'])}\n\n"
                    
                    last_message_count = len(messages)
        
        except Exception as e:
            logger.error(f"SSE连接错误: {e}")
        finally:
            # 注销SSE客户端
            proxy_manager.unregister_sse_client(did, client_id)
            
            # 通知内网客户端SSE连接断开
            if did in proxy_manager.clients:
                try:
                    await proxy_manager.clients[did].send_json({
                        "type": "sse_disconnect",
                        "client_id": client_id
                    })
                except:
                    pass
    
    return StreamingResponse(event_generator(), media_type="text/event-stream")

# 获取所有连接的客户端
@app.get("/admin/clients")
async def get_clients():
    return proxy_manager.get_all_clients()

# 获取特定客户端信息
@app.get("/admin/clients/{did}")
async def get_client(did: str):
    info = proxy_manager.get_client_info(did)
    if not info:
        return JSONResponse(
            status_code=404,
            content={"status": "error", "message": f"未找到DID {did} 的客户端信息"}
        )
    return info

# 主函数
def main():
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

if __name__ == "__main__":
    main()