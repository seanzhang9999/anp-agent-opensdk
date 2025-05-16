import asyncio
import json
import logging
import time
from typing import Dict, Any, List, Optional, Callable, Union
from datetime import datetime

import websockets
from websockets.exceptions import ConnectionClosed

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ws_proxy_client")

class WSProxyClient:
    """WebSocket代理客户端，用于连接公网代理服务器"""
    
    def __init__(self, anp_sdk, proxy_url: str, did: str):
        """初始化WebSocket代理客户端
        
        Args:
            anp_sdk: ANPSDK实例
            proxy_url: 代理服务器WebSocket URL
            did: 本地智能体的DID
        """
        self.anp_sdk = anp_sdk
        self.proxy_url = proxy_url
        self.did = did
        self.websocket = None
        self.connected = False
        self.reconnect_interval = 5  # 重连间隔（秒）
        self.max_reconnect_attempts = 10  # 最大重连尝试次数
        self.reconnect_attempts = 0
        self.running = False
        self.sse_clients = set()  # 存储SSE客户端ID
        
        # 消息处理器
        self.message_handlers = {
            "message": self._handle_message,
            "api_call": self._handle_api_call,
            "sse_connect": self._handle_sse_connect,
            "sse_disconnect": self._handle_sse_disconnect
        }
    
    async def connect(self):
        """连接到代理服务器"""
        if self.connected:
            return
        
        try:
            self.websocket = await websockets.connect(self.proxy_url)
            
            # 发送注册消息
            registration_message = {
                "did": self.did,
                "apis": self._get_exposed_apis(),
                "message_handlers": self._get_message_handlers()
            }
            await self.websocket.send(json.dumps(registration_message))
            
            # 接收确认消息
            response = await self.websocket.recv()
            response_data = json.loads(response)
            
            if response_data.get("status") == "connected":
                self.connected = True
                self.reconnect_attempts = 0
                logger.info(f"已连接到代理服务器: {self.proxy_url}")
                return True
            else:
                logger.error(f"连接代理服务器失败: {response_data.get('message')}")
                return False
        
        except Exception as e:
            logger.error(f"连接代理服务器时出错: {e}")
            return False
    
    async def disconnect(self):
        """断开与代理服务器的连接"""
        self.running = False
        if self.websocket:
            await self.websocket.close()
            self.websocket = None
        self.connected = False
        logger.info("已断开与代理服务器的连接")
    
    async def start(self):
        """启动代理客户端"""
        self.running = True
        
        while self.running:
            if not self.connected:
                # 尝试连接
                if self.reconnect_attempts < self.max_reconnect_attempts:
                    self.reconnect_attempts += 1
                    logger.info(f"尝试连接到代理服务器 (尝试 {self.reconnect_attempts}/{self.max_reconnect_attempts})")
                    
                    if await self.connect():
                        # 连接成功，启动消息处理循环
                        await self._message_loop()
                    else:
                        # 连接失败，等待后重试
                        await asyncio.sleep(self.reconnect_interval)
                else:
                    logger.error(f"达到最大重连尝试次数 ({self.max_reconnect_attempts})，停止重连")
                    self.running = False
            else:
                # 已连接，等待一段时间后检查连接状态
                await asyncio.sleep(1)
    
    async def _message_loop(self):
        """消息处理循环"""
        try:
            while self.connected and self.running:
                try:
                    # 接收消息
                    message = await self.websocket.recv()
                    message_data = json.loads(message)
                    
                    # 处理消息
                    await self._process_message(message_data)
                
                except ConnectionClosed:
                    logger.warning("WebSocket连接已关闭")
                    self.connected = False
                    break
                
                except Exception as e:
                    logger.error(f"处理消息时出错: {e}")
        
        except Exception as e:
            logger.error(f"消息循环出错: {e}")
        finally:
            self.connected = False
    
    async def _process_message(self, message: Dict[str, Any]):
        """处理接收到的消息
        
        Args:
            message: 接收到的消息
        """
        message_type = message.get("type")
        
        if message_type in self.message_handlers:
            await self.message_handlers[message_type](message)
        else:
            logger.warning(f"未知消息类型: {message_type}")
    
    async def _handle_message(self, message: Dict[str, Any]):
        """处理聊天消息
        
        Args:
            message: 接收到的消息
        """
        try:
            # 提取消息信息
            req_did = message.get("req_did")
            resp_did = message.get("resp_did")
            content = message.get("content")
            message_type = message.get("message_type")
            proxy_id = message.get("proxy_id")
            
            # 调用SDK的消息处理器
            result = await self.anp_sdk._handle_message({
                "req_did": req_did,
                "resp_did": resp_did,
                "type": message_type,
                "content": content
            })
            
            # 发送响应
            response = {
                "type": "response",
                "proxy_id": proxy_id,
                "content": result
            }
            await self.websocket.send(json.dumps(response))
        
        except Exception as e:
            logger.error(f"处理消息时出错: {e}")
            # 发送错误响应
            error_response = {
                "type": "response",
                "proxy_id": message.get("proxy_id"),
                "content": {"status": "error", "message": str(e)}
            }
            await self.websocket.send(json.dumps(error_response))
    
    async def _handle_api_call(self, message: Dict[str, Any]):
        """处理API调用
        
        Args:
            message: 接收到的API调用请求
        """
        try:
            # 提取API调用信息
            req_did = message.get("req_did")
            resp_did = message.get("resp_did")
            api_path = message.get("api_path")
            method = message.get("method")
            params = message.get("params")
            proxy_id = message.get("proxy_id")
            
            # 调用SDK的API处理器
            result = await self.anp_sdk._handle_api_call(req_did, resp_did, api_path, method, params)
            
            # 发送响应
            response = {
                "type": "response",
                "proxy_id": proxy_id,
                "content": result
            }
            await self.websocket.send(json.dumps(response))
        
        except Exception as e:
            logger.error(f"处理API调用时出错: {e}")
            # 发送错误响应
            error_response = {
                "type": "response",
                "proxy_id": message.get("proxy_id"),
                "content": {"status": "error", "message": str(e)}
            }
            await self.websocket.send(json.dumps(error_response))
    
    async def _handle_sse_connect(self, message: Dict[str, Any]):
        """处理SSE连接
        
        Args:
            message: 接收到的SSE连接消息
        """
        client_id = message.get("client_id")
        if client_id:
            self.sse_clients.add(client_id)
            logger.info(f"新的SSE客户端连接: {client_id}")
    
    async def _handle_sse_disconnect(self, message: Dict[str, Any]):
        """处理SSE断开连接
        
        Args:
            message: 接收到的SSE断开连接消息
        """
        client_id = message.get("client_id")
        if client_id and client_id in self.sse_clients:
            self.sse_clients.remove(client_id)
            logger.info(f"SSE客户端断开连接: {client_id}")
    
    async def send_sse_message(self, message: Dict[str, Any]):
        """发送SSE消息到所有连接的SSE客户端
        
        Args:
            message: 要发送的消息
        """
        if not self.sse_clients or not self.connected:
            return
        
        try:
            sse_message = {
                "type": "sse_message",
                "content": message,
                "timestamp": datetime.now().isoformat()
            }
            await self.websocket.send(json.dumps(sse_message))
        except Exception as e:
            logger.error(f"发送SSE消息时出错: {e}")
    
    def _get_exposed_apis(self) -> List[Dict[str, Any]]:
        """获取SDK暴露的API列表
        
        Returns:
            API列表
        """
        apis = []
        if hasattr(self.anp_sdk, "app") and hasattr(self.anp_sdk.app, "routes"):
            for route in self.anp_sdk.app.routes:
                if hasattr(route, "methods") and hasattr(route, "path"):
                    apis.append({
                        "path": route.path,
                        "methods": list(route.methods)
                    })
        return apis
    
    def _get_message_handlers(self) -> List[str]:
        """获取SDK注册的消息处理器类型
        
        Returns:
            消息处理器类型列表
        """
        handlers = []
        if hasattr(self.anp_sdk, "message_handlers"):
            handlers = list(self.anp_sdk.message_handlers.keys())
        return handlers