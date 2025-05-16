#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
启动ANP公网WebSocket转发服务

这个脚本用于启动ANP公网WebSocket转发服务，使内网的ANP SDK能够对外暴露API和聊天接口。
"""

import argparse
import logging
import sys
import os
import uvicorn

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from anp_core.proxy.ws_proxy_server import app

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("proxy_server")


def main():
    # 解析命令行参数
    parser = argparse.ArgumentParser(description="启动ANP公网WebSocket转发服务")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="服务器主机地址")
    parser.add_argument("--port", type=int, default=8000, help="服务器端口")
    parser.add_argument("--reload", action="store_true", help="是否启用热重载")
    parser.add_argument("--log-level", type=str, default="info", 
                        choices=["debug", "info", "warning", "error", "critical"],
                        help="日志级别")
    
    args = parser.parse_args()
    
    # 启动服务器
    logger.info(f"正在启动ANP公网WebSocket转发服务，地址: {args.host}:{args.port}")
    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level=args.log_level
    )


if __name__ == "__main__":
    main()