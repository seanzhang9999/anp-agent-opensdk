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

"""ANP Open SDK 配置模块

提供统一的配置管理功能，支持：
- 统一配置管理（unified_config.py）
- 类型提示和协议（config_types.py）
- 向后兼容的动态配置（dynamic_config.py）
- 路径解析（path_resolver.py）
"""

# 导入新的统一配置
from .unified_config import config as _config, UnifiedConfig, get_config_value
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .config_types import UnifiedConfigProtocol
    config: UnifiedConfigProtocol = _config  # 明确类型
else:
    config = _config



