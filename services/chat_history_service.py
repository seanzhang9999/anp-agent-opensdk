"""聊天历史管理模块

此模块提供聊天历史的存储、加载和管理功能。
"""

import json
import logging
import time
from pathlib import Path
from typing import Dict, List, Any, Optional

from config.dynamic_config import dynamic_config

class ChatHistoryService:
    """聊天历史管理类
    
    负责聊天历史的存储、加载和管理。
    """
    
    def __init__(self, history_file: str = None):
        """初始化聊天历史管理器
        
        Args:
            history_file: 历史记录文件路径，如果为None则使用默认路径
        """
        self.logger = logging.getLogger(__name__)
        
        # 默认历史记录文件路径
        if history_file is None:
            self.history_file = Path(Path.cwd()) / "chat_history.json"
        else:
            self.history_file = Path(history_file)
        
        # 聊天历史记录
        self.chat_history: List[Dict[str, Any]] = []
        
        # 最大历史记录条数
        self.max_history_items = dynamic_config.get('chat.max_history_items', 50)
        
        # 加载历史记录
        self.load_history()
    
    def load_history(self) -> List[Dict[str, Any]]:
        """从文件加载聊天历史
        
        Returns:
            聊天历史记录列表
        """
        try:
            if self.history_file.exists():
                with open(self.history_file, "r", encoding="utf-8") as f:
                    self.chat_history = json.load(f)
                self.logger.info(f"已从 {self.history_file} 加载聊天历史")
            else:
                self.chat_history = []
                self.logger.info(f"聊天历史文件 {self.history_file} 不存在，使用空历史记录")
        except Exception as e:
            self.logger.error(f"加载聊天历史出错: {e}")
            self.chat_history = []
        
        return self.chat_history
    
    def save_history(self) -> bool:
        """保存聊天历史到文件
        
        Returns:
            保存是否成功
        """
        try:
            with open(self.history_file, "w", encoding="utf-8") as f:
                json.dump(self.chat_history, f, ensure_ascii=False, indent=2)
            self.logger.info(f"已保存聊天历史到 {self.history_file}")
            return True
        except Exception as e:
            self.logger.error(f"保存聊天历史出错: {e}")
            return False
    
    def add_message(self, message_type: str, message_content: str, from_agent: bool = False, save: bool = True) -> Dict[str, Any]:
        """添加消息到聊天历史
        
        Args:
            message_type: 消息类型，如 'user', 'assistant', 'system'
            message_content: 消息内容
            from_agent: 是否来自智能体
            save: 是否立即保存到文件
            
        Returns:
            添加的消息对象
        """
        message = {
            "type": message_type,
            "message": message_content,
            "timestamp": time.time()
        }
        
        if from_agent:
            message["from_agent"] = True
        
        self.chat_history.append(message)
        
        # 如果超过最大条数，删除最早的记录
        if len(self.chat_history) > self.max_history_items:
            self.chat_history = self.chat_history[-self.max_history_items:]
        
        # 如果需要，保存到文件
        if save:
            self.save_history()
        
        return message
    
    def add_user_message(self, message: str, save: bool = True) -> Dict[str, Any]:
        """添加用户消息
        
        Args:
            message: 消息内容
            save: 是否立即保存到文件
            
        Returns:
            添加的消息对象
        """
        return self.add_message("user", message, save=save)
    
    def add_assistant_message(self, message: str, from_agent: bool = False, save: bool = True) -> Dict[str, Any]:
        """添加助手消息
        
        Args:
            message: 消息内容
            from_agent: 是否来自智能体
            save: 是否立即保存到文件
            
        Returns:
            添加的消息对象
        """
        return self.add_message("assistant", message, from_agent=from_agent, save=save)
    
    def add_system_message(self, message: str, save: bool = True) -> Dict[str, Any]:
        """添加系统消息
        
        Args:
            message: 消息内容
            save: 是否立即保存到文件
            
        Returns:
            添加的消息对象
        """
        return self.add_message("system", message, save=save)
    
    def add_agent_message(self, message: str, save: bool = True) -> Dict[str, Any]:
        """添加智能体消息
        
        Args:
            message: 消息内容
            save: 是否立即保存到文件
            
        Returns:
            添加的消息对象
        """
        return self.add_message("anp_nlp", message, from_agent=True, save=save)
    
    def clear_history(self, save: bool = True) -> bool:
        """清空聊天历史
        
        Args:
            save: 是否立即保存到文件
            
        Returns:
            操作是否成功
        """
        self.chat_history = []
        if save:
            return self.save_history()
        return True
    
    def get_history(self) -> List[Dict[str, Any]]:
        """获取聊天历史
        
        Returns:
            聊天历史记录列表
        """
        return self.chat_history
    
    def message_exists(self, message_content: str, message_type: str = None) -> bool:
        """检查消息是否已存在
        
        Args:
            message_content: 消息内容
            message_type: 消息类型，如果为None则不检查类型
            
        Returns:
            消息是否存在
        """
        for msg in self.chat_history:
            if msg.get("message") == message_content:
                if message_type is None or msg.get("type") == message_type:
                    return True
        return False
    
    def update_config(self, max_history_items: int = None) -> bool:
        """更新配置
        
        Args:
            max_history_items: 最大历史记录条数
            
        Returns:
            更新是否成功
        """
        try:
            if max_history_items is not None:
                self.max_history_items = max_history_items
                dynamic_config.set('chat.max_history_items', max_history_items)
            return True
        except Exception as e:
            self.logger.error(f"更新聊天历史配置出错: {e}")
            return False

# 创建全局聊天历史管理实例
chat_history_service = ChatHistoryService()