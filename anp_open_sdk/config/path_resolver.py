import os
import sys
from typing import Optional

class PathResolver:
    _instance = None
    _app_root = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(PathResolver, cls).__new__(cls)
        return cls._instance

    @classmethod
    def initialize(cls, app_root: Optional[str] = None) -> None:
        """初始化路径解析器
        
        Args:
            app_root: 应用根目录的路径。如果为None，将自动检测
        """
        if app_root:
            cls._app_root = os.path.abspath(app_root)
        else:
            # 查找包含 anp_open_sdk 子目录的目录作为项目根目录
            current_dir = os.path.dirname(os.path.abspath(__file__))
            while current_dir != '/':
                if os.path.exists(os.path.join(current_dir, 'anp_open_sdk')) and \
                   os.path.isdir(os.path.join(current_dir, 'anp_open_sdk')):
                    cls._app_root = current_dir
                    break
                current_dir = os.path.dirname(current_dir)
            
            if not cls._app_root:
                raise RuntimeError('无法确定应用根目录，请手动指定 app_root')

    @classmethod
    def get_app_root(cls) -> str:
        """获取应用根目录的绝对路径"""
        if not cls._app_root:
            cls.initialize()
        return cls._app_root

    @classmethod
    def resolve_path(cls, path: str) -> str:
        """解析路径，将{APP_ROOT}替换为实际的应用根目录
        
        Args:
            path: 包含{APP_ROOT}占位符的路径
            
        Returns:
            解析后的绝对路径
        """
        if not cls._app_root:
            cls.initialize()
        
        # 替换占位符
        if '{APP_ROOT}' in path:
            path = path.replace('{APP_ROOT}', cls._app_root)
        
        # 如果是相对路径，则相对于app_root解析
        if not os.path.isabs(path):
            path = os.path.join(cls._app_root, path)
        
        return os.path.abspath(path)

# 全局实例
path_resolver = PathResolver()