from anp_open_sdk.config.dynamic_config import dynamic_config
from loguru import logger


class DemoConfigHelper:
    """配置辅助工具"""
    
    def __init__(self):
        self.config = dynamic_config
    
    def get_agent_config(self):
        """获取智能体配置"""
        return self.config.get('anp_sdk.agent', {})
    
    def get_demo_config(self):
        """获取演示配置"""
        return self.config.get('anp_sdk.demo', {})
    
    def get_group_config(self):
        """获取群组配置"""
        return self.config.get('anp_sdk.group', {})