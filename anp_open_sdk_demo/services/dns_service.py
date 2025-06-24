import threading
from typing import Dict
import  logging
logger = logging.getLogger(__name__)


class DemoDNSService:
    """演示DNS服务"""
    
    def __init__(self, base_domain='localhost'):
        self.base_domain = base_domain
        self.domains: Dict[str, int] = {}
        self._running = False
        self._dns_thread = None

    def register_domain(self, subdomain: str, port: int):
        """注册子域名"""
        full_domain = f"{subdomain}.{self.base_domain}"
        self.domains[full_domain] = port
        logger.debug(f"注册域名: {full_domain} -> {port}")

    def resolve(self, domain: str) -> str:
        """解析域名"""
        resolved = self.domains.get(domain, 'localhost')
        logger.debug(f"解析域名: {domain} -> {resolved}")
        return resolved

    def start(self):
        """启动DNS服务"""
        logger.debug("启动DNS服务...")
        self._running = True
        
        def dns_server_thread():
            while self._running:
                # 模拟DNS服务运行
                threading.Event().wait(1)
        
        self._dns_thread = threading.Thread(target=dns_server_thread)
        self._dns_thread.daemon = True
        self._dns_thread.start()

    def stop(self):
        """停止DNS服务"""
        logger.debug("停止DNS服务...")
        self._running = False
        if self._dns_thread:
            self._dns_thread.join(timeout=1)

    def get_registered_domains(self) -> Dict[str, int]:
        """获取已注册的域名"""
        return self.domains.copy()