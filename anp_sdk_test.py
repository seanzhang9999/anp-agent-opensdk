import os
import time
import asyncio
from anp_sdk import ANPSDK, LocalAgent, RemoteAgent
from utils.log_base import logger
from config.dynamic_config import dynamic_config


class RemoteAgent:
    """远程智能体，代表其他DID身份"""
    
    def __init__(self, id: str):
        """初始化远程智能体
        
        Args:
            id: DID标识符
        """
        self.id = id


class ANPSDK:
    """ANP SDK主类，提供简单易用的接口"""
    
    def __init__(self, did: str = None, user_dir: str = None, port: int = None):
        """初始化ANP SDK
        
        Args:
            did: 可选，指定使用的DID，如果不指定则提供选择或创建新DID的功能
            user_dir: 可选，指定用户目录，默认使用配置中的目录
            port: 可选，指定服务器端口，默认使用配置中的端口
        """
        self.server_running = False
        self.port = port or dynamic_config.get('demo_autorun.user_did_port_1')
        self.agent = None
        self.api_routes = {}
        self.message_handlers = {}
        
        # 初始化日志
        self.logger = logger
        
        # 如果指定了DID，直接使用
        if did and user_dir:
            self.agent = LocalAgent(id=did, user_dir=user_dir)
            self.logger.info(f"已初始化智能体 DID: {did}")
        else:
            # 否则提供选择功能
            self._initialize_agent()
    
    def _initialize_agent(self):
        """初始化智能体，提供DID选择或创建功能"""
        from demo_autorun import get_user_cfg_list, get_user_cfg
        
        user_list, name_to_dir = get_user_cfg_list()
        
        if not user_list:
            self.logger.error("未找到可用的DID配置")
            return
        
        # 提供选择界面或自动选择第一个
        status, did_dict, selected_name = get_user_cfg(1, user_list, name_to_dir)
        
        if status:
            self.agent = LocalAgent(
                id=did_dict['id'],
                user_dir=name_to_dir[selected_name]
            )
            self.logger.info(f"已选择智能体: {selected_name} DID: {did_dict['id']}")
        else:
            self.logger.error("初始化智能体失败")
    
    def start_server(self):
        """启动服务器
        
        Returns:
            bool: 服务器是否成功启动
        """
        if self.server_running:
            self.logger.warning("服务器已经在运行")
            return True
        
        # 在Mac环境下添加延迟，避免多线程问题
        if os.name == 'posix' and 'darwin' in os.uname().sysname.lower():
            self.logger.info("检测到Mac环境，使用特殊启动方式")
        
        from anp_core.server.server import ANP_resp_start
        result = ANP_resp_start(port=self.port)
        
        if result:
            self.server_running = True
            self.logger.info(f"服务器已在端口 {self.port} 启动")
        else:
            self.logger.error(f"服务器启动失败，端口: {self.port}")
        
        return result
    
    def stop_server(self):
        """停止服务器
        
        Returns:
            bool: 服务器是否成功停止
        """
        if not self.server_running:
            return True
        
        from anp_core.server.server import ANP_resp_stop
        result = ANP_resp_stop(port=self.port)
        
        if result:
            self.server_running = False
            self.logger.info("服务器已停止")
        else:
            self.logger.error("服务器停止失败")
        
        return result
    
    def send_message(self, target_did, message, message_type="text"):
        """向目标DID发送消息
        
        Args:
            target_did: 目标DID
            message: 消息内容，可以是字符串或字典
            message_type: 消息类型，默认为text
        
        Returns:
            响应结果
        """
        if not self.agent:
            self.logger.error("智能体未初始化")
            return None
        
        # 创建远程智能体对象
        target_agent = RemoteAgent(id=target_did)
        
        # 构建消息
        if isinstance(message, str):
            msg = {
                "type": message_type,
                "content": message,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
            }
        else:
            msg = message
            if "timestamp" not in msg:
                msg["timestamp"] = time.strftime("%Y-%m-%d %H:%M:%S")
            if "type" not in msg:
                msg["type"] = message_type
        
        # 发送消息
        return self.agent.send_message(target_agent, msg)
    
    def call_api(self, target_did, api_path, params=None, method="GET"):
        """调用目标DID的API
        
        Args:
            target_did: 目标DID
            api_path: API路径
            params: 参数，可选
            method: 请求方法，默认为GET
        
        Returns:
            API调用结果
        """
        if not self.agent:
            self.logger.error("智能体未初始化")
            return None
        
        # 构建API请求URL
        from anp_core.auth.did_auth import get_did_url_from_did
        target_url = get_did_url_from_did(target_did)
        url = f"http://{target_url}/{api_path}"
        
        # 调用API
        return self.agent.call_api(url, params, method)
    
    def expose_api(self, route_path):
        """装饰器，用于暴露API到FastAPI
        
        Args:
            route_path: API路径
        
        Returns:
            装饰器函数
        """
        def decorator(func):
            # 注册API路由
            self.api_routes[route_path] = func
            
            # 将函数注册到FastAPI
            from core.app import app
            app.add_api_route(f"/{route_path}", func)
            
            return func
        return decorator
    
    def register_message_handler(self, message_type=None):
        """注册消息处理器
        
        Args:
            message_type: 消息类型，如果为None则处理所有类型
        
        Returns:
            装饰器函数
        """
        def decorator(func):
            # 注册消息处理器
            self.message_handlers[message_type or "*"] = func
            return func
        return decorator
    
    def __enter__(self):
        """上下文管理器入口，自动启动服务器"""
        self.start_server()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器退出，自动停止服务器"""
        self.stop_server()


# 测试主函数
async def main():
    # 创建ANP SDK实例
    anp = ANPSDK()
    
    # 启动服务器
    server_result = anp.start_server()
    logger.info(f"服务器启动结果: {server_result}")
    
    # 等待服务器完全启动
    await asyncio.sleep(2)
    
    try:
        # 获取目标DID
        target_did = "did:wba:localhost:9528:wba:user:7c15257e086afeba"
        
        # 发送消息
        logger.info(f"发送消息到 {target_did}")
        response = anp.send_message(target_did, "Hello from ANP SDK!")
        logger.info(f"消息发送响应: {response}")
        
        # 调用API
        logger.info(f"调用API: {target_did}/api/test")
        api_response = anp.call_api(target_did, "api/test", {"param": "test_value"})
        logger.info(f"API调用响应: {api_response}")
        
        # 等待一段时间以便查看结果
        await asyncio.sleep(5)
    finally:
        # 停止服务器
        stop_result = anp.stop_server()
        logger.info(f"服务器停止结果: {stop_result}")


# 使用装饰器示例
anp_example = ANPSDK()

@anp_example.expose_api("api/greeting")
async def greeting(name: str = "World"):
    return {"message": f"Hello, {name}!"}

@anp_example.register_message_handler("text")
def handle_text_message(message):
    logger.info(f"收到文本消息: {message['content']}")
    return {"status": "received"}


if __name__ == "__main__":
    # 运行测试主函数
    asyncio.run(main())