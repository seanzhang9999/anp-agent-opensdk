"""WebSocket客户端模块，提供不依赖网页的WebSocket连接实现。"""
import asyncio
import json
import logging
import time
from typing import Dict, Any, Optional, List, Callable, Coroutine

import websockets
from websockets.exceptions import ConnectionClosed

class WebSocketClient:
    """WebSocket客户端类，提供连接管理、消息发送接收和自动重连功能"""
    
    def __init__(self, uri: str, client_id: str):
        """初始化WebSocket客户端
        
        Args:
            uri: WebSocket服务器URI，例如 ws://localhost:8000/ws/
            client_id: 客户端ID，用于在服务器上标识此客户端
        """
        self.uri = uri
        self.client_id = client_id
        self.full_uri = f"{uri}{client_id}"
        self.websocket = None
        self.connected = False
        self.reconnect_interval = 3  # 重连间隔（秒）
        self.max_reconnect_attempts = 5  # 最大重连尝试次数
        self.reconnect_attempts = 0
        self.running = False
        self.message_handlers = {}
        self.active_clients = []
        self.connection_event = asyncio.Event()
        
        # 默认消息处理器
        self.register_handler("system", self._handle_system_message)
        self.register_handler("chat", self._handle_chat_message)
        self.register_handler("nlp_response", self._handle_nlp_response)
        self.register_handler("nlp_error", self._handle_nlp_error)
        self.register_handler("nlp_status", self._handle_nlp_status)
    
    def register_handler(self, message_type: str, handler: Callable[[Dict[str, Any]], Coroutine]):
        """注册消息处理器
        
        Args:
            message_type: 消息类型
            handler: 异步处理函数，接收消息数据字典作为参数
        """
        self.message_handlers[message_type] = handler
    
    async def connect(self):
        """连接到WebSocket服务器"""
        if self.connected:
            return
        
        try:
            self.websocket = await websockets.connect(self.full_uri)
            self.connected = True
            self.reconnect_attempts = 0
            self.connection_event.set()
            logging.info(f"已连接到WebSocket服务器: {self.full_uri}")
            return True
        except Exception as e:
            logging.error(f"连接WebSocket服务器失败: {e}")
            self.connected = False
            self.connection_event.clear()
            return False
    
    async def disconnect(self):
        """断开与WebSocket服务器的连接"""
        if not self.connected or not self.websocket:
            return
        
        try:
            await self.websocket.close()
            logging.info("已断开与WebSocket服务器的连接")
        except Exception as e:
            logging.error(f"断开WebSocket连接时出错: {e}")
        finally:
            self.connected = False
            self.connection_event.clear()
            self.websocket = None
    
    async def reconnect(self):
        """重新连接到WebSocket服务器"""
        if self.reconnect_attempts >= self.max_reconnect_attempts:
            logging.error(f"达到最大重连尝试次数({self.max_reconnect_attempts})，停止重连")
            return False
        
        self.reconnect_attempts += 1
        logging.info(f"尝试重新连接 (尝试 {self.reconnect_attempts}/{self.max_reconnect_attempts})...")
        
        await asyncio.sleep(self.reconnect_interval)
        return await self.connect()
    
    async def send_message(self, message_type: str, message: str, recipient: str = None):
        """发送消息到WebSocket服务器
        
        Args:
            message_type: 消息类型，如 "chat"、"nlp" 等
            message: 消息内容
            recipient: 可选的接收者ID
        
        Returns:
            bool: 是否成功发送消息
        """
        if not self.connected:
            logging.warning("未连接到WebSocket服务器，无法发送消息")
            if not await self.connect():
                return False
        
        try:
            data = {
                "type": message_type,
                "message": message
            }
            
            if recipient:
                data["recipient"] = recipient
                
            await self.websocket.send(json.dumps(data))
            logging.debug(f"已发送消息: {data}")
            return True
        except Exception as e:
            logging.error(f"发送消息失败: {e}")
            self.connected = False
            self.connection_event.clear()
            return False
    
    async def send_chat_message(self, message: str, recipient: str = None):
        """发送聊天消息
        
        Args:
            message: 消息内容
            recipient: 可选的接收者ID
        """
        return await self.send_message("chat", message, recipient)
    
    async def send_nlp_request(self, message: str, recipient: str = None):
        """发送NLP请求
        
        Args:
            message: 请求内容
            recipient: 可选的接收者ID
        """
        return await self.send_message("nlp", message, recipient)
    
    async def get_active_clients(self):
        """获取当前活跃的客户端列表"""
        if not self.connected:
            logging.warning("未连接到WebSocket服务器，无法获取活跃客户端列表")
            if not await self.connect():
                return []
        
        try:
            await self.send_message("system", "get_users")
            # 活跃客户端列表将通过系统消息返回，在_handle_system_message中处理
            return self.active_clients
        except Exception as e:
            logging.error(f"获取活跃客户端列表失败: {e}")
            return []
    
    async def _handle_system_message(self, data: Dict[str, Any]):
        """重写系统消息处理方法，提供更友好的命令行输出
        
        Args:
            data: 消息数据
        """
        message = data.get("message", "")
        active_clients = data.get("active_clients", [])
        
        # 存储最后接收到的消息
        self.last_received_message = data
        
        # 更新活跃客户端列表
        if active_clients:
            self.active_clients = active_clients
            
        # 在命令行中显示系统消息
        print(f"\n[系统] {message}")
        
        # 如果消息包含活跃客户端列表，则显示
        if active_clients:
            print("当前在线用户:")
            for client in active_clients:
                print(f"  - {client}")
                
        print("你: ", end="", flush=True)  # 重新显示输入提示
    
    async def _handle_chat_message(self, data: Dict[str, Any]):
        """处理聊天消息
        
        Args:
            data: 消息数据
        """
        sender = data.get("sender", "未知")
        message = data.get("message", "")
        logging.info(f"聊天消息 - {sender}: {message}")
        
        # 默认实现只是记录消息，子类可以重写此方法提供自定义处理
        print(f"[{sender}] {message}")
    
    async def _handle_nlp_response(self, data: Dict[str, Any]):
        """处理NLP响应
        
        Args:
            data: 消息数据
        """
        message = data.get("message", "")
        recipient = data.get("recipient", "all")
        
        # 存储最后接收到的消息
        self.last_received_message = data
        
        # 在命令行中显示AI回复
        print(f"\n[AI] {message}")
        print("你: ", end="", flush=True)  # 重新显示输入提示
        
        if recipient == "all" or recipient == self.client_id:
            logging.info(f"NLP响应: {message}")
    
    async def _handle_nlp_error(self, data: Dict[str, Any]):
        """处理NLP错误
        
        Args:
            data: 消息数据
        """
        message = data.get("message", "未知错误")
        logging.error(f"NLP错误: {message}")
        print(f"[错误] {message}")
    
    async def _handle_nlp_status(self, data: Dict[str, Any]):
        """处理NLP状态消息
        
        Args:
            data: 消息数据
        """
        status = data.get("status", "")
        message = data.get("message", "")
        logging.info(f"NLP状态 - {status}: {message}")
        
        if status == "processing":
            print("正在处理NLP请求...")
    
    async def _message_listener(self):
        """消息监听器，接收并处理来自服务器的消息"""
        while self.running:
            if not self.connected:
                await asyncio.sleep(1)
                continue
                
            try:
                message = await self.websocket.recv()
                data = json.loads(message)
                
                message_type = data.get("type")
                if message_type in self.message_handlers:
                    await self.message_handlers[message_type](data)
                else:
                    logging.warning(f"收到未知类型的消息: {message_type}")
                    logging.debug(f"消息内容: {data}")
                    
            except ConnectionClosed:
                logging.warning("WebSocket连接已关闭")
                self.connected = False
                self.connection_event.clear()
                
                if self.running:
                    # 尝试重新连接
                    if await self.reconnect():
                        logging.info("重新连接成功")
                    else:
                        logging.error("重新连接失败，停止消息监听")
                        break
            except Exception as e:
                logging.error(f"处理消息时出错: {e}")
                await asyncio.sleep(1)
    
    async def start(self):
        """启动WebSocket客户端"""
        if self.running:
            return
            
        self.running = True
        
        # 连接到服务器
        if not await self.connect():
            if not await self.reconnect():
                logging.error("无法连接到WebSocket服务器，客户端启动失败")
                self.running = False
                return False
        
        # 启动消息监听器
        asyncio.create_task(self._message_listener())
        logging.info("WebSocket客户端已启动")
        return True
    
    async def stop(self):
        """停止WebSocket客户端"""
        if not self.running:
            return
            
        self.running = False
        await self.disconnect()
        logging.info("WebSocket客户端已停止")


class CommandLineWebSocketClient(WebSocketClient):
    """命令行WebSocket客户端，提供交互式命令行界面"""
    
    def __init__(self, uri: str, client_id: str):
        super().__init__(uri, client_id)
        self.input_task = None
        
    async def _handle_chat_message(self, data: Dict[str, Any]):
        """重写聊天消息处理方法，提供更友好的命令行输出
        
        Args:
            data: 消息数据
        """
        sender = data.get("sender", "未知")
        message = data.get("message", "")
        
        # 在命令行中显示消息，带有发送者信息
        print(f"\n[{sender}] {message}")
        print("你: ", end="", flush=True)  # 重新显示输入提示
    
    async def _handle_nlp_response(self, data: Dict[str, Any]):
        """重写NLP响应处理方法，提供更友好的命令行输出
        
        Args:
            data: 消息数据
        """
        message = data.get("message", "")
        
        # 在命令行中显示AI回复
        print(f"\n[AI] {message}")
        print("你: ", end="", flush=True)  # 重新显示输入提示
    
    async def _input_handler(self):
        """处理用户输入的命令行任务"""
        while self.running:
            try:
                # 使用asyncio.to_thread在Python 3.9+中运行阻塞的input()函数
                # 对于较早版本，可以使用loop.run_in_executor
                loop = asyncio.get_event_loop()
                user_input = await loop.run_in_executor(None, lambda: input("你: ").strip())
                
                if not user_input:
                    continue
                    
                if user_input.lower() == "/q" or user_input.lower() == "exit":
                    print("正在退出...")
                    self.running = False
                    break
                    
                elif user_input.lower() == "/users":
                    # 获取当前活跃用户列表
                    await self.send_message("system", "get_users")
                    
                elif user_input.startswith("/to "):
                    # 发送私聊消息，格式: /to user_id message
                    parts = user_input[4:].strip().split(" ", 1)
                    if len(parts) == 2:
                        recipient, message = parts
                        await self.send_chat_message(message, recipient)
                    else:
                        print("格式错误。正确格式: /to user_id message")
                        
                elif user_input.startswith("/nlp "):
                    # 发送NLP请求，格式: /nlp message
                    message = user_input[5:].strip()
                    await self.send_nlp_request(message)
                    
                elif user_input.startswith("/help"):
                    # 显示帮助信息
                    print("\n可用命令:")
                    print("  /q 或 exit - 退出客户端")
                    print("  /users - 获取当前活跃用户列表")
                    print("  /to user_id message - 发送私聊消息给指定用户")
                    print("  /nlp message - 发送NLP请求")
                    print("  /help - 显示此帮助信息")
                    print("  其他任何输入将作为聊天消息广播给所有人\n")
                    
                else:
                    # 默认作为聊天消息发送
                    await self.send_chat_message(user_input)
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logging.error(f"处理输入时出错: {e}")
                print(f"\n[错误] {e}")
                print("你: ", end="", flush=True)
    
    async def start(self):
        """启动命令行WebSocket客户端"""
        if not await super().start():
            return False
            
        # 启动输入处理任务
        self.input_task = asyncio.create_task(self._input_handler())
        
        print("\n命令行WebSocket客户端已启动")
        print("输入 /help 查看可用命令")
        return True
    
    async def stop(self):
        """停止命令行WebSocket客户端"""
        if not self.running:
            return
            
        # 取消输入处理任务
        if self.input_task and not self.input_task.done():
            self.input_task.cancel()
            try:
                await self.input_task
            except asyncio.CancelledError:
                pass
            
        await super().stop()
        print("命令行WebSocket客户端已停止")


async def run_websocket_client(uri: str, client_id: str):
    """运行WebSocket客户端的辅助函数
    
    Args:
        uri: WebSocket服务器URI
        client_id: 客户端ID
    """
    client = CommandLineWebSocketClient(uri, client_id)
    await client.start()
    
    # 等待客户端停止
    while client.running:
        await asyncio.sleep(1)
        
    await client.stop()