import threading
import time
from loguru import logger
from anp_open_sdk.anp_sdk import ANPSDK


class DemoSDKManager:
    """SDK管理器"""
    
    def __init__(self):
        self.sdk = None
        self.server_thread = None

    def initialize_sdk(self) -> ANPSDK:
        """初始化SDK"""
        logger.info("初始化ANPSDK...")
        self.sdk = ANPSDK()
        return self.sdk

    def start_server(self, sdk: ANPSDK):
        """启动服务器"""
        logger.info("启动服务器...")
        
        def start_server_thread():
            try:
                sdk.start_server()
            except Exception as e:
                logger.error(f"服务器启动错误: {e}")

        self.server_thread = threading.Thread(target=start_server_thread)
        self.server_thread.daemon = True
        self.server_thread.start()
        
        # 等待服务器启动
        time.sleep(0.5)
        logger.info("服务器启动完成")
        return self.server_thread

    def stop_server(self, sdk: ANPSDK):
        """停止服务器"""
        if sdk:
            logger.info("停止服务器...")
            sdk.stop_server()