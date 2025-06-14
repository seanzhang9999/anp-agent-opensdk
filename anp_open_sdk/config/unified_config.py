# Copyright 2024 ANP Open SDK Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""统一配置管理模块

此模块提供统一的配置管理功能，支持：
- YAML配置文件管理
- 环境变量映射和类型转换
- 路径占位符自动解析
- 属性访问和代码提示
- 敏感信息保护
"""

import os
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import yaml
import logging
from types import SimpleNamespace


class ConfigNode:
    """配置节点，支持属性访问和代码提示"""
    
    def __init__(self, data: dict, parent_path: str = ""):
        self._data = data
        self._parent_path = parent_path
        
        # 动态创建属性，支持代码提示
        for key, value in data.items():
            if isinstance(value, dict):
                setattr(self, key, ConfigNode(value, f"{parent_path}.{key}" if parent_path else key))
            else:
                setattr(self, key, value)
    
    def __getattr__(self, name: str) -> Any:
        if name in self._data:
            return self._data[name]
        raise AttributeError(f"配置项 '{self._parent_path}.{name}' 不存在")
    
    def __setattr__(self, name: str, value: Any) -> None:
        if name.startswith('_'):
            super().__setattr__(name, value)
        else:
            self._data[name] = value
            super().__setattr__(name, value)
    
    def __repr__(self) -> str:
        return f"ConfigNode({self._parent_path})"


class EnvConfig:
    """环境变量配置节点，支持属性访问"""
    
    def __init__(self, env_mapping: dict, env_types: dict, config_instance):
        self._env_mapping = env_mapping
        self._env_types = env_types
        self._config_instance = config_instance
        self._cache = {}
        
        # 预加载映射的环境变量
        self._load_mapped_env()
    
    def _load_mapped_env(self):
        """加载映射的环境变量"""
        for attr_name, env_key in self._env_mapping.items():
            raw_value = os.environ.get(env_key)
            if raw_value is not None:
                if attr_name == 'system_path':
                    self._cache[attr_name] = raw_value
                    setattr(self, attr_name, raw_value)
                else:
                    converted_value = self._config_instance._convert_env_type(raw_value, self._env_types.get(attr_name, 'string'))
                    self._cache[attr_name] = converted_value
                    setattr(self, attr_name, converted_value)
            else:
                self._cache[attr_name] = None
                setattr(self, attr_name, None)
    
    def __getattr__(self, name: str) -> Any:
        # 先检查缓存
        if name in self._cache:
            return self._cache[name]
        
        # 检查预定义映射
        if name in self._env_mapping:
            env_key = self._env_mapping[name]
            raw_value = os.environ.get(env_key)
            if raw_value is not None:
                converted_value = self._config_instance._convert_env_type(raw_value, self._env_types.get(name, 'string'))
                self._cache[name] = converted_value
                return converted_value
        
        # 动态查找环境变量
        env_key = name.upper().replace('.', '_')
        raw_value = os.environ.get(env_key)
        if raw_value is not None:
            converted_value = self._config_instance._convert_env_type(raw_value, self._env_types.get(name, 'string'))
            self._cache[name] = converted_value
            return converted_value
        
        return None
    
    def __setattr__(self, name: str, value: Any) -> None:
        if name.startswith('_'):
            super().__setattr__(name, value)
        else:
            # 设置环境变量
            if name in self._env_mapping:
                env_key = self._env_mapping[name]
            else:
                env_key = name.upper().replace('.', '_')
            
            os.environ[env_key] = str(value)
            self._cache[name] = value
            super().__setattr__(name, value)
    
    def reload(self):
        """重新加载环境变量"""
        self._cache.clear()
        self._load_mapped_env()
    
    def to_dict(self) -> dict:
        """转换为字典"""
        result = {}
        for attr_name in self._env_mapping.keys():
            result[attr_name] = getattr(self, attr_name)
        return result
    
    def __iter__(self):
        """支持遍历"""
        return iter(self._env_mapping.keys())


class SecretsConfig:
    """敏感信息配置节点，不缓存，每次从环境变量读取"""
    
    def __init__(self, secrets_list: list, env_mapping: dict):
        self._secrets_list = secrets_list
        self._env_mapping = env_mapping
    
    def __getattr__(self, name: str) -> Any:
        if name in self._secrets_list and name in self._env_mapping:
            # 每次都从环境变量重新读取，不缓存
            return os.environ.get(self._env_mapping[name])
        raise AttributeError(f"敏感配置项 '{name}' 未定义")
    
    def __iter__(self):
        return iter(self._secrets_list)
    
    def to_dict(self) -> dict:
        """转换为字典（不包含实际值，仅显示配置项）"""
        return {name: "***" for name in self._secrets_list}


class UnifiedConfig:
    """统一配置管理器"""
    
    def __init__(self, config_file: Optional[str] = None):
        """初始化统一配置管理器
        
        Args:
            config_file: 配置文件路径，如果为None则使用默认路径
        """
        self.logger = logging.getLogger(__name__)
        
        # 配置文件路径
        self._config_file = self._resolve_config_file(config_file)
        
        # 项目根目录
        self._app_root = self._detect_app_root()
        
        # 配置数据
        self._config_data = {}
        
        # 线程锁
        self._config_lock = threading.RLock()
        
        # 加载配置
        self.load()
        
        # 创建配置树
        self._create_config_tree()
        
        # 创建环境变量和敏感信息访问
        self._create_env_configs()
    
    def _resolve_config_file(self, config_file: Optional[str]) -> Path:
        """解析配置文件路径"""
        if config_file:
            return Path(config_file)
        return Path(__file__).parent / "unified_config.yaml"
    
    def _detect_app_root(self) -> Path:
        """自动检测项目根目录"""
        current = Path(__file__).parent
        while current != current.parent:
            if (current / 'anp_open_sdk').exists():
                return current
            current = current.parent
        raise RuntimeError("无法检测到项目根目录，请检查项目结构")
    
    def _create_config_tree(self):
        """创建配置树，支持属性访问"""
        # 处理路径占位符
        processed_data = self._process_paths(self._config_data)
        
        # 创建配置节点（排除特殊配置）
        special_keys = {'env_mapping', 'secrets', 'env_types', 'path_config'}
        for key, value in processed_data.items():
            if key not in special_keys and isinstance(value, dict):
                setattr(self, key, ConfigNode(value, key))
            elif key not in special_keys:
                setattr(self, key, value)
    
    def _create_env_configs(self):
        """创建环境变量和敏感信息配置"""
        env_mapping = self._config_data.get('env_mapping', {})
        env_types = self._config_data.get('env_types', {})
        secrets_list = self._config_data.get('secrets', [])
        
        # 环境变量配置
        self.env = EnvConfig(env_mapping, env_types, self)
        
        # 敏感信息配置
        self.secrets = SecretsConfig(secrets_list, env_mapping)
    
    def _process_paths(self, data: Any) -> Any:
        """递归处理路径占位符"""
        if isinstance(data, dict):
            return {k: self._process_paths(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [self._process_paths(item) for item in data]
        elif isinstance(data, str) and '{APP_ROOT}' in data:
            return data.replace('{APP_ROOT}', str(self._app_root))
        return data
    
    def _convert_env_type(self, value: str, type_name: str) -> Any:
        # 如果 value 不是字符串，可能是已经处理过的值，直接返回
        if not isinstance(value, str):
            return value




        """环境变量类型转换"""
        try:
            if type_name == 'boolean':
                return value.lower() in ('true', '1', 'yes', 'on')
            elif type_name == 'integer':
                return int(value)
            elif type_name == 'float':
                return float(value)
            elif type_name == 'list':
                return [item.strip() for item in value.split(',')]
            elif type_name == 'path':
                return self._process_path(value)
            # 如果是 PATH 的字符串表示（以 [ 开头），直接获取原始 PATH
            elif type_name == 'path_list' and value.startswith('['):
                value = os.environ.get('PATH', '')
                return value
            elif type_name == 'path_list':
                # 直接处理原始字符串，不要递归处理
                return self._process_path_list_simple(value)
            else:
                return value
        except (ValueError, AttributeError):
            return value

    def _process_path(self, path_str: str) -> Path:
        """处理单个路径"""
        path = Path(path_str)
        
        # 展开用户目录
        if str(path).startswith('~'):
            path = path.expanduser()
        
        # 处理占位符
        if '{APP_ROOT}' in str(path):
            path = Path(str(path).replace('{APP_ROOT}', str(self._app_root)))
        
        # 解析为绝对路径
        path_config = self._config_data.get('path_config', {})
        if path_config.get('resolve_paths', True):
            if not path.is_absolute():
                path = self._app_root / path
            path = path.resolve()
        
        return path
    
    def _process_path_list(self, path_str: str) -> List[Path]:
        """处理路径列表（如 PATH 环境变量）"""
        # 如果输入已经是一个路径列表的字符串表示，先尝试解析
        if path_str.startswith('[') and path_str.endswith(']'):
            # 这可能是一个列表的字符串表示，直接返回原始PATH
            path_str = os.environ.get('PATH', '')

        path_config = self._config_data.get('path_config', {})

        # 跨平台路径分隔符
        separator = path_config.get('path_separator')
        if not separator:
            separator = ';' if os.name == 'nt' else ':'

        # 分割并处理每个路径
        paths = []
        for path_item in path_str.split(separator):
            if path_item.strip():
                try:
                    paths.append(Path(path_item.strip()))
                except Exception:
                    # 如果路径无效，跳过
                    continue

        return paths

    def _process_path_list_simple(self, path_str: str) -> List[Path]:
        """简单处理路径列表，避免递归问题"""
        if not isinstance(path_str, str):
            return []

        # 跨平台路径分隔符
        separator = ';' if os.name == 'nt' else ':'

        # 分割并处理每个路径
        paths = []
        for path_item in path_str.split(separator):
            if path_item.strip():
                try:
                    paths.append(Path(path_item.strip()))
                except Exception:
                    # 如果路径无效，跳过
                    continue

        return paths


    def load(self) -> Dict[str, Any]:
        """从文件加载配置"""
        with self._config_lock:
            try:
                if self._config_file.exists():
                    with open(self._config_file, 'r', encoding='utf-8') as f:
                        self._config_data = yaml.safe_load(f) or {}
                        self.logger.info(f"已从 {self._config_file} 加载配置")
                else:
                    # 创建默认配置
                    self._config_data = self._get_default_config()
                    self.save()
                    self.logger.info(f"已创建默认配置文件 {self._config_file}")
            except Exception as e:
                self.logger.error(f"加载配置出错: {e}")
                self._config_data = self._get_default_config()
            
            return self._config_data
    
    def save(self) -> bool:
        """保存配置到文件"""
        with self._config_lock:
            try:
                self._config_file.parent.mkdir(parents=True, exist_ok=True)
                with open(self._config_file, 'w', encoding='utf-8') as f:
                    yaml.dump(self._config_data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
                self.logger.info(f"已保存配置到 {self._config_file}")
                return True
            except Exception as e:
                self.logger.error(f"保存配置出错: {e}")
                return False
    
    def reload(self):
        """重新加载配置"""
        self.load()
        self._create_config_tree()
        self._create_env_configs()
        self.logger.info("配置已重新加载")
    
    def resolve_path(self, path: Union[str, Path]) -> Path:
        """解析路径，返回绝对路径"""
        return self._process_path(str(path))
    
    def get_app_root(self) -> Path:
        """获取项目根目录"""
        return self._app_root
    
    def add_to_path(self, new_path: str):
        """动态添加路径到 PATH"""
        current_path = os.environ.get('PATH', '')
        separator = ';' if os.name == 'nt' else ':'
        new_path_str = f"{new_path}{separator}{current_path}"
        os.environ['PATH'] = new_path_str
        
        # 重新加载环境变量
        if hasattr(self, 'env'):
            self.env.reload()
    
    def find_in_path(self, filename: str) -> List[Path]:
        """在 PATH 中查找所有匹配的文件"""
        matches = []
        try:
            # 直接从环境变量获取 PATH，避免使用处理过的版本
            path_env = os.environ.get('PATH', '')
            if not path_env:
                return matches

            # 分割路径
            separator = ';' if os.name == 'nt' else ':'
            path_dirs = path_env.split(separator)

            # 在每个目录中查找文件
            for path_str in path_dirs:
                if not path_str.strip():
                    continue

                try:
                    path_dir = Path(path_str.strip())
                    if not path_dir.exists():
                        continue

                    # 检查文件是否存在
                    target = path_dir / filename
                    if target.exists() and target.is_file():
                        matches.append(target)

                    # 在 Windows 上，也检查带 .exe 扩展名的文件
                    if os.name == 'nt' and not filename.endswith('.exe'):
                        target_exe = path_dir / f"{filename}.exe"
                        if target_exe.exists() and target_exe.is_file():
                            matches.append(target_exe)
                except Exception:
                    # 跳过无效路径
                    continue

        except Exception as e:
            self.logger.error(f"在 PATH 中查找文件 {filename} 时出错: {e}")
        return matches

    def get_path_info(self) -> dict:
        """获取路径环境变量的详细信息"""
        info = {
            'app_root': str(self._app_root),
            'config_file': str(self._config_file),
        }

        try:
            # 直接从环境变量获取 PATH 信息
            path_env = os.environ.get('PATH', '')
            if path_env:
                separator = ';' if os.name == 'nt' else ':'
                path_dirs = []
                for p in path_env.split(separator):
                    if p.strip():
                        try:
                            path_dirs.append(Path(p.strip()))
                        except Exception:
                            continue

                info.update({
                    'path_count': len(path_dirs),
                    'existing_paths': [str(p) for p in path_dirs if p.exists()],
                    'missing_paths': [str(p) for p in path_dirs if not p.exists()],
                })

            # 获取 HOME 目录信息
            home_env = os.environ.get('HOME') or os.environ.get('USERPROFILE')
            if home_env:
                info['home_directory'] = home_env

            # 获取当前用户
            user_env = os.environ.get('USER') or os.environ.get('USERNAME')
            if user_env:
                info['current_user'] = user_env

        except Exception as e:
            self.logger.error(f"获取路径信息时出错: {e}")

        return info

    def to_dict(self) -> dict:
        """导出当前配置为字典"""
        return self._config_data.copy()

    def _get_default_config(self) -> dict:
        """获取默认配置"""
        return {
            "# ANP SDK 统一配置文件": None,
            "# 项目根目录自动检测，支持 {APP_ROOT} 占位符": None,

            "anp_sdk": {
                "debug_mode": True,
                "host": "localhost",
                "port": 9527,
                "user_did_path": "{APP_ROOT}/anp_open_sdk/anp_users",
                "user_hosted_path": "{APP_ROOT}/anp_open_sdk/anp_users_hosted",
                "auth_virtual_dir": "wba/auth",
                "msg_virtual_dir": "/agent/message",
                "token_expire_time": 3600,
                "user_did_key_id": "key-1",
                "group_msg_path": "{APP_ROOT}/anp_open_sdk",
                "jwt_algorithm": "RS256",
                "nonce_expire_minutes": 6,
                "helper_lang": "zh",
                "agent": {
                    "demo_agent1": "本田",
                    "demo_agent2": "雅马哈",
                    "demo_agent3": "铃木"
                }
            },

            "llm": {
                "openrouter_api_url": "api.302ai.cn",
                "default_model": "deepseek/deepseek-chat-v3-0324:free",
                "max_tokens": 512,
                "system_prompt": "你是一个智能助手，请根据用户的提问进行专业、简洁的回复。"
            },

            "mail": {
                "use_local_backend": True,
                "local_backend_path": "{APP_ROOT}/anp_open_sdk/simulate/mail_local_backend",
                "smtp_server": "smtp.gmail.com",
                "smtp_port": 587,
                "imap_server": "imap.gmail.com",
                "imap_port": 993
            },

            "env_mapping": {
                "# 应用配置": None,
                "debug_mode": "ANP_DEBUG",
                "host": "ANP_HOST",
                "port": "ANP_PORT",

                "# 系统环境变量": None,
                "system_path": "PATH",
                "home_dir": "HOME",
                "user_name": "USER",
                "python_path": "PYTHONPATH",

                "# API 密钥": None,
                "openai_api_key": "OPENAI_API_KEY",
                "anthropic_api_key": "ANTHROPIC_API_KEY",

                "# 邮件配置": None,
                "mail_password": "MAIL_PASSWORD",
                "hoster_mail_password": "HOSTER_MAIL_PASSWORD",
                "sender_mail_password": "SENDER_MAIL_PASSWORD",

                "# 数据库和服务": None,
                "database_url": "DATABASE_URL",
                "redis_url": "REDIS_URL"
            },

            "secrets": [
                "openai_api_key",
                "anthropic_api_key",
                "mail_password",
                "hoster_mail_password",
                "sender_mail_password",
                "database_url"
            ],

            "env_types": {
                "debug_mode": "boolean",
                "port": "integer",
                "smtp_port": "integer",
                "imap_port": "integer",
                "system_path": "path_list",
                "python_path": "path_list",
                "home_dir": "path",
                "token_expire_time": "integer",
                "nonce_expire_minutes": "integer"
            },

            "path_config": {
                "path_separator": ":",
                "resolve_paths": True,
                "validate_existence": False
            }
        }


# 创建全局配置实例
config = UnifiedConfig()

# 向后兼容的便捷函数
def get_config_value(key: str, default: Any = None) -> Any:
    """获取配置值的便捷函数（向后兼容）"""
    try:
        keys = key.split('.')
        value = config
        for k in keys:
            value = getattr(value, k)
        return value
    except (AttributeError, KeyError):
        return default
