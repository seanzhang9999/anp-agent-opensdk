"""动态配置管理模块

此模块提供动态配置管理功能，允许在运行时更新配置并将变更保存到文件中。
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional
import threading
import time
from types import SimpleNamespace
import yaml
import json


class DynamicConfig:
    """动态配置管理类
    
    提供配置的加载、更新和保存功能，支持实时更新配置文件。
    """
    
    def __init__(self, config_file: str = None):
        """初始化动态配置管理器
        
        Args:
            config_file: 配置文件路径，如果为None则使用默认路径
        """
        self.logger = logging.getLogger(__name__)
        
        # 默认配置文件路径
        if config_file is None:
            # 如果安装了 PyYAML，使用 .yaml 扩展名，否则使用 .json
            ext = ".yaml" 
            self.config_file = Path(os.path.dirname(os.path.abspath(__file__))) / f"dynamic_config{ext}"
        else:
            self.config_file = Path(config_file)
            
        # 确保配置目录存在
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        
        # 配置锁，用于线程安全访问
        self._config_lock = threading.RLock()
        
        # 默认配置
        self._default_config = {
            "# 一个工程中管理统一多个启动程序的配置文件",
            "# 除了密钥敏感信息存储于env外，其他信息均可存储于该文件中",
            "# 运行中改变的值可以选择回写到文件中，下次启动时会自动加载",
            "# 这样方便检查运行情况，也可以作为部分关键信息的log，便于后续分析"
        }
        
        # 当前配置
        self._config = {}
        
        # 加载配置
        self.load_config()
        
    def load_config(self) -> Dict[str, Any]:
        """从文件加载配置
        
        如果配置文件不存在，则创建默认配置文件
        
        Returns:
            当前配置字典
        """
        with self._config_lock:
            try:
                if self.config_file.exists():
                    with open(self.config_file, 'r', encoding='utf-8') as f:
                        # 根据文件扩展名选择解析方法
                        loaded_config = yaml.safe_load(f)
                        
                        # 直接使用加载的配置，不与默认配置合并
                        self._config = loaded_config
                        self.logger.info(f"已从 {self.config_file} 加载配置")
                else:
                    # 如果文件不存在，使用默认配置并创建文件
                    self._config = self._default_config.copy()
                    self.save_config()
                    self.logger.info(f"已创建默认配置文件 {self.config_file}")
            except Exception as e:
                self.logger.error(f"加载配置出错: {e}")
                # 出错时使用默认配置
                self._config = self._default_config.copy()
                
            return self._config
    
    def save_config(self) -> bool:
        """保存配置到文件
        
        Returns:
            保存是否成功
        """
        with self._config_lock:
            try:
                with open(self.config_file, 'w', encoding='utf-8') as f:
                    yaml.dump(self._config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
                        
                self.logger.info(f"已保存配置到 {self.config_file}")
                return True
            except Exception as e:
                self.logger.error(f"保存配置出错: {e}")
                return False
    
    def get(self, key: str, default: Any = None) -> Any:
        """获取配置项
        
        支持使用点号分隔的路径访问嵌套配置，如 'llm.max_tokens' 或多层嵌套如 'a.b.c.d'
        
        Args:
            key: 配置键名，支持点号分隔的路径
            default: 如果键不存在，返回的默认值
            
        Returns:
            配置值或默认值
        """
        with self._config_lock:
            if '.' not in key:
                return self._config.get(key, default)
            
            # 处理嵌套路径
            parts = key.split('.')
            current = self._config
            for part in parts:
                if not isinstance(current, dict):
                    return default
                current = current.get(part)
                if current is None:
                    return default
            return current
    
    def set(self, key: str, value: Any, save: bool = True) -> bool:
        """设置配置项
        
        支持使用点号分隔的路径设置嵌套配置，如 'llm.max_tokens'
        
        Args:
            key: 配置键名，支持点号分隔的路径
            value: 要设置的值
            save: 是否立即保存到文件
            
        Returns:
            设置是否成功
        """
        with self._config_lock:
            try:
                if '.' not in key:
                    self._config[key] = value
                else:
                    # 处理嵌套路径
                    parts = key.split('.')
                    current = self._config
                    for i, part in enumerate(parts[:-1]):
                        if part not in current:
                            current[part] = {}
                        current = current[part]
                    current[parts[-1]] = value
                
                # 如果需要，保存到文件
                if save:
                    return self.save_config()
                return True
            except Exception as e:
                self.logger.error(f"设置配置项 {key} 出错: {e}")
                return False
    
    def update(self, config_dict: Dict[str, Any], save: bool = True) -> bool:
        """批量更新配置
        
        Args:
            config_dict: 要更新的配置字典
            save: 是否立即保存到文件
            
        Returns:
            更新是否成功
        """
        with self._config_lock:
            try:
                self._config = self._deep_update(self._config, config_dict)
                if save:
                    return self.save_config()
                return True
            except Exception as e:
                self.logger.error(f"批量更新配置出错: {e}")
                return False
    
    def reset_to_default(self, save: bool = True) -> bool:
        """重置为默认配置
        
        Args:
            save: 是否立即保存到文件
            
        Returns:
            重置是否成功
        """
        with self._config_lock:
            try:
                self._config = self._default_config.copy()
                if save:
                    return self.save_config()
                return True
            except Exception as e:
                self.logger.error(f"重置配置出错: {e}")
                return False
    
    def _deep_update(self, original: Dict[str, Any], update: Dict[str, Any]) -> Dict[str, Any]:
        """深度更新字典
        
        递归地将update中的值更新到original中
        
        Args:
            original: 原始字典
            update: 更新字典
            
        Returns:
            更新后的字典
        """
        for key, value in update.items():
            if key in original and isinstance(original[key], dict) and isinstance(value, dict):
                original[key] = self._deep_update(original[key], value)
            else:
                original[key] = value
        return original
    
 

# 创建全局配置实例
dynamic_config = DynamicConfig()