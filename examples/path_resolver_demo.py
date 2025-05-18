import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from anp_open_sdk.config.path_resolver import path_resolver
from anp_open_sdk.config.dynamic_config import dynamic_config

def demo_path_resolver():
    # 初始化路径解析器（可选，会自动初始化）
    path_resolver.initialize()
    
    # 获取应用根目录
    app_root = path_resolver.get_app_root()
    print(f"应用根目录: {app_root}")
    
    # 演示从配置文件获取带占位符的路径
    user_did_path = dynamic_config.get('anp_sdk.user_did_path')
    print(f"用户 DID 目录: {user_did_path}")
    
    # 演示直接解析带占位符的路径
    bookmark_path = path_resolver.resolve_path('{APP_ROOT}/anp_core/anp_bookmark')
    print(f"书签目录: {bookmark_path}")
    
    # 演示解析相对路径
    relative_path = path_resolver.resolve_path('logs/app.log')
    print(f"日志文件: {relative_path}")

if __name__ == '__main__':
    demo_path_resolver()