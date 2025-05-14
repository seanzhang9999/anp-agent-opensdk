"""智能体服务模块

此模块提供与智能体交互的服务，包括书签管理和消息发送功能。
"""

import json
import logging
import os
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

from config.dynamic_config import dynamic_config
from web_anp_llmapp import chat_to_ANP

class AgentService:
    """智能体服务类
    
    封装与智能体的交互，提供书签管理和消息发送功能。
    """
    
    def __init__(self):
        """初始化智能体服务"""
        self.logger = logging.getLogger(__name__)
        
        # 书签目录

        bookmark_dir = dynamic_config.get('agent.bookmark_dir')
        self.bookmark_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), bookmark_dir)


        # 默认问候语
        self.default_greeting = dynamic_config.get('agent.default_greeting')
        
        # 书签缓存
        self._bookmarks_cache: List[Dict[str, Any]] = []
        self._load_bookmarks()
    
    def _load_bookmarks(self) -> List[Dict[str, Any]]:
        """加载所有书签
        
        Returns:
            书签列表
        """
        self._bookmarks_cache = []
        try:
            for bookmark_file in self.bookmark_dir.glob("*.js"):
                try:
                    with open(bookmark_file, 'r', encoding='utf-8') as f:
                        bookmark_data = json.loads(f.read())
                        # 添加ID字段（使用文件名）
                        bookmark_data['id'] = bookmark_file.stem
                        self._bookmarks_cache.append(bookmark_data)
                except Exception as e:
                    self.logger.error(f"加载书签 {bookmark_file} 出错: {e}")
        except Exception as e:
            self.logger.error(f"加载书签目录出错: {e}")
        
        return self._bookmarks_cache
        
    async def load_bookmarks_from_url(self, url: str) -> Tuple[bool, str, List[Dict[str, Any]]]:
        """从URL加载书签
        
        Args:
            url: 书签数据URL
            
        Returns:
            (成功状态, 消息, 书签列表)
        """
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(url)
                if response.status_code == 200:
                    data = response.json()
                    bookmarks = []
                    for agent in data:
                        # 确保port是字符串类型
                        port = agent.get("port")
                        if port is not None:
                            port = str(port)
                        
                        bookmark_data = {
                            "id": agent.get("name", "").lower().replace(" ", "_"),
                            "name": agent.get("name", ""),
                            "did": agent.get("did"),
                            "url": agent.get("url"),
                            "port": port,
                            "discovery": agent.get("discovery")
                        }
                        bookmarks.append(bookmark_data)
                        
                        # 保存到本地
                        self.save_bookmark(bookmark_data)
                    
                    self.logger.info(f"从URL加载了 {len(bookmarks)} 个书签")
                    return True, "成功加载书签", bookmarks
                else:
                    error_msg = f"从URL加载书签失败: {response.status_code}"
                    self.logger.error(error_msg)
                    return False, error_msg, []
        except Exception as e:
            error_msg = f"从URL加载书签失败: {str(e)}"
            self.logger.error(error_msg)
            return False, error_msg, []
    
    def get_bookmarks(self) -> List[Dict[str, Any]]:
        """获取所有书签
        
        Returns:
            书签列表
        """
        return self._bookmarks_cache
    
    def get_bookmark(self, bookmark_id: str) -> Optional[Dict[str, Any]]:
        """获取指定书签
        
        Args:
            bookmark_id: 书签ID
            
        Returns:
            书签数据或None
        """
        for bookmark in self._bookmarks_cache:
            if bookmark.get('id') == bookmark_id:
                return bookmark
        return None
    
    def save_bookmark(self, bookmark_data: Dict[str, Any]) -> bool:
        """保存书签
        
        Args:
            bookmark_data: 书签数据
            
        Returns:
            保存是否成功
        """
        try:
            # 确保有ID字段
            if 'id' not in bookmark_data:
                bookmark_data['id'] = bookmark_data.get('name', 'unknown').lower()
            
            # 保存到文件
            bookmark_file = self.bookmark_dir / f"{bookmark_data['id']}.js"
            with open(bookmark_file, 'w', encoding='utf-8') as f:
                json.dump(bookmark_data, f, ensure_ascii=False, indent=2)
            
            # 更新缓存
            self._load_bookmarks()
            
            self.logger.info(f"已保存书签: {bookmark_data['id']}")
            return True
        except Exception as e:
            self.logger.error(f"保存书签出错: {e}")
            return False
    
    def delete_bookmark(self, bookmark_id: str) -> bool:
        """删除书签
        
        Args:
            bookmark_id: 书签ID
            
        Returns:
            删除是否成功
        """
        try:
            bookmark_file = self.bookmark_dir / f"{bookmark_id}.js"
            if bookmark_file.exists():
                bookmark_file.unlink()
                # 更新缓存
                self._load_bookmarks()
                self.logger.info(f"已删除书签: {bookmark_id}")
                return True
            else:
                self.logger.warning(f"书签不存在: {bookmark_id}")
                return False
        except Exception as e:
            self.logger.error(f"删除书签出错: {e}")
            return False
    
    async def send_message(self, message: str, agent_info: Dict[str, Any] = None) -> Tuple[bool, str]:
        """发送消息到智能体
        
        Args:
            message: 要发送的消息
            agent_info: 智能体信息，包含name, did, url, port等字段
            
        Returns:
            (成功状态, 响应消息或错误信息)
        """
        try:
            # 如果没有提供智能体信息，尝试从消息中解析
            if agent_info is None:
                parts = message.strip().split(" ", 1)
                if len(parts) > 0 and parts[0].startswith("@"):
                    agent_name = parts[0].strip().split("@", 1)[1]
                    # 查找书签
                    for bookmark in self._bookmarks_cache:
                        if bookmark.get('name') == agent_name or bookmark.get('id') == agent_name:
                            agent_info = bookmark
                            break
            
            # 如果找到智能体信息，设置环境变量
            if agent_info:
                agent_name = agent_info.get('name')
                did = agent_info.get('did')
                url = agent_info.get('url')
                port = agent_info.get('port')
                
                # 确保port是字符串类型
                if port is not None:
                    port = str(port)
                
                self.logger.info(f"使用智能体信息 - 名称:{agent_name} DID:{did} 地址:{url} 端口:{port}")
                
                # 设置环境变量
                if port:
                    os.environ['target-port'] = port
                if url:
                    os.environ['target-host'] = url
                
                # 提取实际消息内容
                custom_msg = self.default_greeting
                if message.strip().startswith("@"):
                    parts = message.strip().split(" ", 1)
                    if len(parts) > 1 and parts[1].strip():
                        custom_msg = parts[1].strip()
                else:
                    custom_msg = message
                
                # 获取token，如果环境变量中不存在则使用None
                token = os.environ.get('did-token', None)
                unique_id = os.environ.get('unique_id')
                
                # 发送消息
                self.logger.info(f"向智能体发送消息: {custom_msg}")
                result = chat_to_ANP(custom_msg, token=token, unique_id_arg=unique_id)
                
                if result:
                    return True, "已发送到智能体，请等待回复（可能需要刷新页面查看）"
                else:
                    return False, "发送消息失败"
            else:
                return False, f"找不到智能体信息"
        except Exception as e:
            error_msg = f"发送消息出错: {str(e)}"
            self.logger.error(error_msg)
            return False, error_msg
    
    def update_config(self, config_updates: Dict[str, Any]) -> bool:
        """更新智能体服务配置
        
        Args:
            config_updates: 要更新的配置项
            
        Returns:
            更新是否成功
        """
        try:
            # 更新动态配置
            agent_config = {}
            for key, value in config_updates.items():
                agent_config[f"agent.{key}"] = value
                # 同时更新实例变量
                if hasattr(self, key):
                    setattr(self, key, value)
            
            # 保存到配置文件
            for key, value in agent_config.items():
                dynamic_config.set(key, value, save=False)
            dynamic_config.save_config()
            
            self.logger.info(f"已更新智能体服务配置: {config_updates}")
            return True
        except Exception as e:
            self.logger.error(f"更新智能体服务配置出错: {e}")
            return False

# 创建全局智能体服务实例
agent_service = AgentService()