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

import logging
import logging.handlers
import sys
import os
from pathlib import Path
from typing import Optional

# 从我们的类型定义中导入协议
from ..config.config_types import BaseUnifiedConfigProtocol
from anp_open_sdk.config import get_global_config


class ColoredFormatter(logging.Formatter):
    """用于在控制台输出彩色日志的格式化器。"""
    COLORS = {
        "DEBUG": "\033[94m",  # Blue
        "INFO": "\033[92m",  # Green
        "WARNING": "\033[93m",  # Yellow
        "ERROR": "\033[91m",  # Red
        "CRITICAL": "\033[95m",  # Magenta
        "RESET": "\033[0m",  # Reset
    }

    def format(self, record):
        levelname = record.levelname
        # 使用 get 方法并提供默认值，稍微更健壮
        color = self.COLORS.get(levelname, self.COLORS["RESET"])
        message = super().format(record)
        return f"{color}{message}{self.COLORS['RESET']}"


# 一个防止重复配置的全局标志
_is_logging_configured = False


def setup_logging():
    """
    根据传入的配置对象来设置根日志记录器。

    这个函数应该在应用启动时被调用一次。

    Args:
        config: 一个符合 UnifiedConfigProtocol 协议的完整配置对象。
    """
    config = get_global_config()

    global _is_logging_configured
    if _is_logging_configured:
        return

    # 从配置中安全地获取日志设置
    log_config = getattr(config, 'log_settings', None)

    # 默认值
    log_level_str = "INFO"
    log_file = None
    max_size_mb = 10

    if log_config:
        log_level_str = getattr(log_config, 'log_level', 'INFO').upper()
        if hasattr(log_config, 'detail'):
            log_file = getattr(log_config.detail, 'file', None)
            max_size_mb = getattr(log_config.detail, 'max_size', 10)

    # 将字符串级别转换为 logging 的整数级别
    log_level = getattr(logging, log_level_str, logging.INFO)

    # 获取根日志记录器
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # 清理已存在的 handlers，避免重复打印
    if root_logger.hasHandlers():
        root_logger.handlers.clear()

    # --- 配置控制台 Handler ---
    console_formatter = ColoredFormatter(
        "%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s"
    )
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    # --- 配置可选的文件 Handler ---
    if log_file:
        try:
            # 使用 config 对象的方法来解析路径，这是最健壮的方式
            log_file_path = config.resolve_path(log_file)

            # 确保目录存在，不再使用 sudo
            log_file_path.parent.mkdir(parents=True, exist_ok=True)

            file_formatter = logging.Formatter(
                "%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s"
            )
            file_handler = logging.handlers.RotatingFileHandler(
                log_file_path,
                maxBytes=max_size_mb * 1024 * 1024,
                backupCount=30,
                encoding="utf-8",
            )
            file_handler.setFormatter(file_formatter)
            root_logger.addHandler(file_handler)
            root_logger.info(f"日志将记录到文件: {log_file_path}")
        except Exception as e:
            root_logger.error(f"设置文件日志记录器失败 ({log_file}): {e}")

    _is_logging_configured = True
    root_logger.info(f"日志系统配置完成，级别: {log_level_str}。")

