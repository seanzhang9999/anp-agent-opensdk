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

"""统一配置管理模块（基于 unified_config_meta_config.yaml 自动生成配置节点）
此模块提供统一的配置管理功能，支持：
- 基于 unified_config_meta_config.yaml 的 schema 自动生成属性
- YAML 配置文件管理
- 属性访问和代码提示
"""

import os


from pathlib import Path
from typing import Any, Dict, Optional, TYPE_CHECKING
import yaml
if TYPE_CHECKING:
    from typing_extensions import Self

def _convert_type(value, type_name):
    if value is None:
        return None
    try:
        if type_name == "int":
            return int(value)
        elif type_name == "float":
            return float(value)
        elif type_name == "bool":
            if isinstance(value, bool):
                return value
            return str(value).lower() in ("true", "1", "yes", "on")
        elif type_name == "path":
            return Path(str(value))
        elif type_name == "path_list":
            sep = ";" if os.name == "nt" else ":"
            return [Path(p) for p in str(value).split(sep) if p.strip()]
        elif type_name == "str":
            return str(value)
        else:
            return value
    except Exception:
        return value

class DynamicConfigNode:
    def __init__(self, schema: dict, values: dict = None, parent_path=""):
        self._schema = schema
        self._values = values or {}
        self._parent_path = parent_path
        self.__annotations__ = {}
        
        for key, meta in schema.items():
            if isinstance(meta, dict) and 'type' not in meta:
                setattr(self, key, DynamicConfigNode(meta, self._values.get(key, {}), f"{parent_path}.{key}" if parent_path else key))
                self.__annotations__[key] = 'DynamicConfigNode'
            else:
                env_key = meta.get("env")
                env_val = os.environ.get(env_key) if env_key else None
                value = env_val if env_val is not None else self._values.get(key, meta.get('default'))
                value = _convert_type(value, meta.get("type", "str"))
                setattr(self, key, value)
                self.__annotations__[key] = meta.get('type', 'Any')

    def __getattr__(self, name):
        if name in self.__dict__:
            return self.__dict__[name]
        raise AttributeError(f"配置项 '{self._parent_path}.{name}' 不存在")

    def __repr__(self):
        return f"DynamicConfigNode({self._parent_path})"

    def to_dict(self):
        result = {}
        for key in self._schema:
            val = getattr(self, key)
            if isinstance(val, DynamicConfigNode):
                result[key] = val.to_dict()
            else:
                result[key] = val
        return result

    def __dir__(self):
        return list(self._schema.keys()) + list(super().__dir__())

class SecretsConfig:
    """敏感信息配置节点，每次从环境变量读取"""
    def __init__(self, secrets_list, schema):
        self._secrets_list = secrets_list
        self._schema = schema
        self.__annotations__ = {k: 'Optional[str]' for k in secrets_list}

    def __getattr__(self, name):
        if name in self._secrets_list:
            meta = self._schema.get(name, {})
            env_key = meta.get("env", name.upper())
            return os.environ.get(env_key)
        raise AttributeError(f"敏感配置项 '{name}' 未定义")

    def to_dict(self):
        return {name: "***" for name in self._secrets_list}

class UnifiedConfig:
    """自动化配置管理器，基于meta.yaml"""
    def __init__(self, meta_file="unified_config_meta_config.yaml", config_file="unified_config.yaml"):
        from utils.log_base import logging as logger
        self.logger = logger
        self._meta_file = Path(meta_file)
        self._config_file = Path(config_file) if config_file else None

        with open(self._meta_file, "r", encoding="utf-8") as f:
            self._schema = yaml.safe_load(f)

        self._config_data = self._load_config_data()

        for top_key, top_schema in self._schema.items():
            if top_key == "secrets":
                setattr(self, "secrets", SecretsConfig(self._schema["secrets"], self._schema.get("env", {})))
            else:
                values = self._config_data.get(top_key, {})
                setattr(self, top_key, DynamicConfigNode(top_schema, values, top_key))

    def _load_config_data(self):
        if self._config_file and self._config_file.exists():
            with open(self._config_file, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        return {}

    def to_dict(self):
        result = {}
        for key in self._schema:
            val = getattr(self, key)
            if hasattr(val, "to_dict"):
                result[key] = val.to_dict()
            else:
                result[key] = val
        return result

    def reload(self):
        """重新加载配置文件和环境变量"""
        self._config_data = self._load_config_data()
        # 重新生成配置属性
        for top_key, top_schema in self._schema.items():
            if top_key == "secrets":
                setattr(self, "secrets", SecretsConfig(self._schema["secrets"], self._schema.get("env", {})))
            else:
                values = self._config_data.get(top_key, {})
                setattr(self, top_key, DynamicConfigNode(top_schema, values, top_key))
        self.logger.debug("配置已重新加载")

    def resolve_path(self, path: str) -> Path:
        """解析路径中的 {APP_ROOT} 占位符"""
        app_root = self.get_app_root()
        if "{APP_ROOT}" in path:
            path = path.replace("{APP_ROOT}", str(app_root))
        return Path(path).expanduser().resolve()

    def get_app_root(self) -> Path:
        """获取项目根目录，自动检测"""
        current = Path(__file__).parent
        while current != current.parent:
            if (current / 'anp_open_sdk').exists():
                return current
            current = current.parent
        return Path.cwd()

    def save(self):
        """保存当前配置到 config_file（不包含 secrets）"""
        if not self._config_file:
            raise RuntimeError("未指定 config_file 路径")
        data = self.to_dict()
        data.pop("secrets", None)
        with open(self._config_file, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)
        self.logger.debug(f"已保存配置到 {self._config_file}")

    def add_to_path(self, new_path: str):
        """动态添加路径到 PATH"""
        current_path = os.environ.get('PATH', '')
        separator = ';' if os.name == 'nt' else ':'
        new_path_str = f"{new_path}{separator}{current_path}"
        os.environ['PATH'] = new_path_str

    def find_in_path(self, filename: str) -> list:
        """在 PATH 中查找所有匹配的文件"""
        matches = []
        path_env = os.environ.get('PATH', '')
        separator = ';' if os.name == 'nt' else ':'
        for path_str in path_env.split(separator):
            if not path_str.strip():
                continue
            path_dir = Path(path_str.strip())
            target = path_dir / filename
            if target.exists() and target.is_file():
                matches.append(target)
            if os.name == 'nt' and not filename.endswith('.exe'):
                target_exe = path_dir / f"{filename}.exe"
                if target_exe.exists() and target_exe.is_file():
                    matches.append(target_exe)
        return matches

    def get_path_info(self) -> dict:
        """获取 PATH 相关信息"""
        info = {}
        path_env = os.environ.get('PATH', '')
        separator = ';' if os.name == 'nt' else ':'
        path_dirs = [Path(p.strip()) for p in path_env.split(separator) if p.strip()]
        info['path_count'] = len(path_dirs)
        info['existing_paths'] = [str(p) for p in path_dirs if p.exists()]
        info['missing_paths'] = [str(p) for p in path_dirs if not p.exists()]
        return info

    def __dir__(self):
        return list(self._schema.keys()) + [
            'reload', 'save', 'to_dict', 'resolve_path', 'get_app_root',
            'add_to_path', 'find_in_path', 'get_path_info'
        ]

config = UnifiedConfig()

def get_config_value(key: str, default: Any = None) -> Any:
    try:
        keys = key.split('.')
        value = config
        for k in keys:
            value = getattr(value, k)
        return value
    except (AttributeError, KeyError):
        return default
