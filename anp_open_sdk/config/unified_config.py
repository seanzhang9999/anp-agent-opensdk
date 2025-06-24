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
from typing import Any, Dict, List, Optional, Union, TYPE_CHECKING
import yaml
import logging
from types import SimpleNamespace
from dotenv import load_dotenv
import os
from typing import Optional, cast
from .config_types import BaseUnifiedConfigProtocol



# --- 新增部分 ---

# 1. 定义一个模块级的“保管员”，初始时为 None
_global_config: Optional['UnifiedConfig'] = None

def set_global_config(config_instance: 'UnifiedConfig'):
    """
    【注册函数】由应用入口调用，设置全局唯一的配置实例。
    """
    global _global_config
    if _global_config is not None:
        # 可以加一个警告，防止被意外覆盖
        print("Warning: Global config is being overridden.")
    _global_config = config_instance

def get_global_config() -> 'BaseUnifiedConfigProtocol':
    """
    【解析函数】供库内其他模块调用，获取已设置的全局配置实例。
    """
    if _global_config is None:
        # 这是关键的保护措施！
        raise RuntimeError(
            "Global config has not been set. "
            "Please call set_global_config(config) at your application's entry point."
        )
    # 使用 cast 来帮助类型检查器理解 _global_config 符合协议
    return cast('UnifiedConfigProtocol', _global_config)


class ConfigNode:
    def __init__(self, data: dict, parent_path: str = ""):
        self._data = data
        self._parent_path = parent_path
        self.__annotations__ = {}
        for key, value in data.items():
            if isinstance(value, dict):
                child_node = ConfigNode(value, f"{parent_path}.{key}" if parent_path else key)
                setattr(self, key, child_node)
                self.__annotations__[key] = 'ConfigNode'
            else:
                setattr(self, key, value)
                self.__annotations__[key] = self._infer_type_annotation(key, value)

    def _infer_type_annotation(self, key: str, value: Any) -> str:
        key_lower = key.lower()
        if 'port' in key_lower and isinstance(value, (int, str)):
            return 'int'
        elif 'path' in key_lower:
            return 'Path'
        elif key_lower in ['debug', 'debug_mode', 'enable', 'enabled'] or key_lower.startswith('use_'):
            return 'bool'
        elif key_lower in ['host', 'server', 'url', 'algorithm', 'lang', 'language']:
            return 'str'
        elif 'timeout' in key_lower or 'expire' in key_lower or key_lower.startswith('max_'):
            return 'int'
        if isinstance(value, bool):
            return 'bool'
        elif isinstance(value, int):
            return 'int'
        elif isinstance(value, float):
            return 'float'
        elif isinstance(value, str):
            if ('/' in value or '\\' in value or '{APP_ROOT}' in value or
                    key_lower.endswith('_path') or key_lower.endswith('_dir')):
                return 'Path'
            return 'str'
        elif isinstance(value, Path):
            return 'Path'
        elif isinstance(value, list):
            return 'List[Any]'
        elif isinstance(value, dict):
            return 'Dict[str, Any]'
        else:
            return 'Any'

    def __getattr__(self, name: str) -> Any:
        if name in self._data:
            return self._data[name]
        raise AttributeError(f"配置项 '{self._parent_path}.{name}' 不存在")

    def __setattr__(self, name: str, value: Any) -> None:
        if name.startswith('_'):
            super().__setattr__(name, value)
        else:
            if hasattr(self, '_data'):
                self._data[name] = value
                if hasattr(self, '__annotations__'):
                    self.__annotations__[name] = self._infer_type_annotation(name, value)
            super().__setattr__(name, value)

    def __dir__(self) -> List[str]:
        return list(self._data.keys()) + ['_data', '_parent_path']

    def __repr__(self) -> str:
        return f"ConfigNode({self._parent_path})"

class EnvConfig:
    def __init__(self, env_mapping, env_types, parent):
        self.env_mapping = env_mapping
        self.env_types = env_types
        self.parent = parent
        self.values = {}
        self._load_env()
        self.__annotations__ = {}
        for attr_name in env_mapping.keys():
            self.__annotations__[attr_name] = 'Optional[Any]'

    def _load_env(self):
        for key, env_var in self.env_mapping.items():
            if env_var is not None:
                self.values[key] = os.environ.get(env_var)
            else:
                self.values[key] = None
    def __getattr__(self, name: str) -> Any:
        if name in self.values:
            return self.values[name]
        raise AttributeError(f"环境变量配置项 '{name}' 不存在")

    def __setattr__(self, name: str, value: Any) -> None:
        if name in ('env_mapping', 'env_types', 'parent', 'values', '__annotations__'):
            super().__setattr__(name, value)
        else:
            self.values[name] = value
            if name in self.env_mapping:
                os.environ[self.env_mapping[name]] = str(value)
            super().__setattr__(name, value)

    def __dir__(self) -> List[str]:
        return list(self.env_mapping.keys()) + ['reload', 'to_dict']
    def reload(self):
        self._load_env()
    def to_dict(self) -> dict:
        return dict(self.values)

    def __iter__(self):
        return iter(self.env_mapping.keys())

class SecretsConfig:
    def __init__(self, secrets_list: list, env_mapping: dict):
        self._secrets_list = secrets_list
        self._env_mapping = env_mapping
        self.__annotations__ = {}
        for secret_name in secrets_list:
            self.__annotations__[secret_name] = 'Optional[str]'

    def __getattr__(self, name: str) -> Any:
        if name in self._secrets_list and name in self._env_mapping:
            return os.environ.get(self._env_mapping[name])
        raise AttributeError(f"敏感配置项 '{name}' 未定义")

    def __dir__(self) -> List[str]:
        return self._secrets_list + ['to_dict']

    def __iter__(self):
        return iter(self._secrets_list)

    def to_dict(self) -> dict:
        return {name: "***" for name in self._secrets_list}

class UnifiedConfig:
    # 1. 添加一个类属性来存储 app_root
    _app_root_cls: Optional[Path] = None

    def __init__(self, config_file: Optional[str] = None, app_root: Optional[str] = None):
        self.logger = logging.getLogger(__name__)
        if app_root:
            self._app_root = Path(app_root).resolve()
        else:
            self._app_root = Path(os.getcwd()).resolve()

        # 如果类属性尚未设置，则使用实例的 _app_root 设置它
        if UnifiedConfig._app_root_cls is None:
            UnifiedConfig._app_root_cls = self._app_root
        elif UnifiedConfig._app_root_cls != self._app_root:
            self.logger.warning(
                f"新的 UnifiedConfig 实例指定了不同的 app_root。 "
                f"类方法将继续使用第一个初始化的路径: {UnifiedConfig._app_root_cls}"
            )

        # 2. 加载 .env 文件
        env_path = self._app_root / ".env"
        if env_path.exists():
            load_dotenv(dotenv_path=env_path, override=True)
            self.logger.info(f"已从 {env_path} 加载环境变量")

        # 3. 解析配置文件路径
        self._config_file = self._resolve_config_file(config_file)
        self._config_data = {}
        self._config_lock = threading.RLock()
        self.load()
        self._create_config_tree()
        self._create_env_configs()





    def __dir__(self) -> List[str]:
        config_attrs = ['anp_sdk', 'llm', 'mail', 'env', 'secrets']
        method_attrs = [
            'resolve_path', 'get_app_root', 'find_in_path', 'get_path_info', 'add_to_path',
            'load', 'save', 'reload', 'to_dict'
        ]
        return config_attrs + method_attrs

    def _resolve_config_file(self, config_file: Optional[str]) -> Path:
        if config_file:
            return Path(config_file).resolve()
            # 默认配置文件路径基于 app_root
        return self._app_root / "unified_config.yaml"



    def _create_config_tree(self):
        processed_data = self._process_paths(self._config_data)
        special_keys = {'env_mapping', 'secrets', 'env_types', 'path_config'}
        for key, value in processed_data.items():
            if key not in special_keys and isinstance(value, dict):
                setattr(self, key, ConfigNode(value, key))
            elif key not in special_keys:
                setattr(self, key, value)

    def _create_env_configs(self):
        env_mapping = self._config_data.get('env_mapping', {})
        env_types = self._config_data.get('env_types', {})
        secrets_list = self._config_data.get('secrets', [])
        self.env = EnvConfig(env_mapping, env_types, self)
        self.secrets = SecretsConfig(secrets_list, env_mapping)

    def _process_paths(self, data: Any) -> Any:
        if isinstance(data, dict):
            return {k: self._process_paths(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [self._process_paths(item) for item in data]
        elif isinstance(data, str) and '{APP_ROOT}' in data:
            # 现在可以调用类方法
            return str(UnifiedConfig.resolve_path(data))
        return data

    def _convert_env_type(self, value: str, type_name: str) -> Any:
        if not isinstance(value, str):
            return value
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
                return UnifiedConfig.resolve_path(value)
            elif type_name == 'path_list' and value.startswith('['):
                value = os.environ.get('PATH', '')
                return value
            elif type_name == 'path_list':
                return self._process_path_list_simple(value)
            else:
                return value
        except (ValueError, AttributeError):
            return value



    def _process_path_list(self, path_str: str) -> List[Path]:
        if path_str.startswith('[') and path_str.endswith(']'):
            path_str = os.environ.get('PATH', '')
        path_config = self._config_data.get('path_config', {})
        separator = path_config.get('path_separator')
        if not separator:
            separator = ';' if os.name == 'nt' else ':'
        paths = []
        for path_item in path_str.split(separator):
            if path_item.strip():
                try:
                    paths.append(Path(path_item.strip()))
                except Exception:
                    continue
        return paths

    def _process_path_list_simple(self, path_str: str) -> List[Path]:
        if not isinstance(path_str, str):
            return []
        separator = ';' if os.name == 'nt' else ':'
        paths = []
        for path_item in path_str.split(separator):
            if path_item.strip():
                try:
                    paths.append(Path(path_item.strip()))
                except Exception:
                    continue
        return paths

    def load(self) -> Dict[str, Any]:
        with self._config_lock:
            try:
                if self._config_file.exists():
                    with open(self._config_file, 'r', encoding='utf-8') as f:
                        self._config_data = yaml.safe_load(f) or {}
                        self.logger.info(f"已从 {self._config_file} 加载配置")
                else:
                    self._config_data = self._get_default_config()
                    self.save()
                    self.logger.info(f"已创建默认配置文件 {self._config_file}")
            except Exception as e:
                self.logger.error(f"加载配置出错: {e}")
                self._config_data = self._get_default_config()
            return self._config_data

    def save(self) -> bool:
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
        self.load()
        self._create_config_tree()
        self._create_env_configs()
        self.logger.info("配置已重新加载")

        # 这是从 path_resolver 移入的核心方法

    @classmethod
    def resolve_path(cls, path: Union[str, Path]) -> Path:
        """
        解析路径，将{APP_ROOT}替换为实际的应用根目录并返回绝对路径。

        Args:
            path: 包含{APP_ROOT}占位符的路径字符串或Path对象。

        Returns:
            解析后的绝对路径 Path 对象。
        """
        if cls._app_root_cls is None:
            raise RuntimeError("UnifiedConfig 尚未初始化，无法解析路径。请先创建 UnifiedConfig 实例。")

        path_str = str(path).replace('{APP_ROOT}', str(cls._app_root_cls))
        path_obj = Path(path_str)

        if not path_obj.is_absolute():
            path_obj = cls._app_root_cls / path_obj

        return path_obj.resolve()

    @classmethod
    def get_app_root(cls) -> Path:
        """获取已初始化的应用根目录。"""
        if cls._app_root_cls is None:
            raise RuntimeError("UnifiedConfig 尚未初始化，无法获取 app_root。请先创建 UnifiedConfig 实例。")
        return cls._app_root_cls

    def add_to_path(self, new_path: str):
        current_path = os.environ.get('PATH', '')
        separator = ';' if os.name == 'nt' else ':'
        new_path_str = f"{new_path}{separator}{current_path}"
        os.environ['PATH'] = new_path_str
        if hasattr(self, 'env'):
            self.env.reload()

    def find_in_path(self, filename: str) -> List[Path]:
        matches = []
        try:
            path_env = os.environ.get('PATH', '')
            if not path_env:
                return matches
            separator = ';' if os.name == 'nt' else ':'
            path_dirs = path_env.split(separator)
            for path_str in path_dirs:
                if not path_str.strip():
                    continue
                try:
                    path_dir = Path(path_str.strip())
                    if not path_dir.exists():
                        continue
                    target = path_dir / filename
                    if target.exists() and target.is_file():
                        matches.append(target)
                    if os.name == 'nt' and not filename.endswith('.exe'):
                        target_exe = path_dir / f"{filename}.exe"
                        if target_exe.exists() and target_exe.is_file():
                            matches.append(target_exe)
                except Exception:
                    continue
        except Exception as e:
            self.logger.error(f"在 PATH 中查找文件 {filename} 时出错: {e}")
        return matches

    def get_path_info(self) -> dict:
        info = {
            'app_root': str(self._app_root),
            'config_file': str(self._config_file),
        }
        try:
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
            home_env = os.environ.get('HOME') or os.environ.get('USERPROFILE')
            if home_env:
                info['home_directory'] = home_env
            user_env = os.environ.get('USER') or os.environ.get('USERNAME')
            if user_env:
                info['current_user'] = user_env
        except Exception as e:
            self.logger.error(f"获取路径信息时出错: {e}")
        return info

    def to_dict(self) -> dict:
        return self._config_data.copy()

    def _get_default_config(self) -> dict:
        default_config_path = self._app_root / 'unified_config.default.yaml'
        if not default_config_path.exists():
            self.logger.warning(f"默认配置文件 {default_config_path} 不存在。将使用空配置。")
            return {}
        with open(default_config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)


