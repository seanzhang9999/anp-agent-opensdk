"""配置模块包

此包提供配置管理功能，包括静态配置和动态配置。
"""

from config.dynamic_config import dynamic_config

__all__ = ['dynamic_config']