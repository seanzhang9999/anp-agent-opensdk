"""LLM服务模块

此模块提供与大语言模型交互的服务，封装了API调用和响应处理逻辑。
"""

import logging
import os
from typing import Dict, List, Any, Optional, Tuple

import httpx

from config.dynamic_config import dynamic_config

class LLMService:
    """LLM服务类
    
    封装与大语言模型的交互，提供消息处理和响应生成功能。
    """
    
    def __init__(self):
        """初始化LLM服务"""
        self.logger = logging.getLogger(__name__)
        self.api_url = dynamic_config.get('llm.openrouter_api_url')
        self.api_key = os.getenv("OPENROUTER_API_KEY", "")
        self.default_model = dynamic_config.get('llm.default_model')
        self.default_max_tokens = dynamic_config.get('llm.max_tokens')
        self.system_prompt = dynamic_config.get('llm.system_prompt')
    
    async def process_message(self, message: str, chat_history: List[Dict[str, Any]] = None) -> Tuple[bool, str]:
        """处理用户消息并生成回复
        
        Args:
            message: 用户消息
            chat_history: 聊天历史记录
            
        Returns:
            (成功状态, 回复内容或错误信息)
        """
        if not self.api_key:
            return False, "OpenRouter API key未配置，请在环境变量中设置OPENROUTER_API_KEY"
        
        try:
            # 构建消息历史
            messages = [
                {"role": "system", "content": self.system_prompt}
            ]
            
            # 添加聊天历史
            if chat_history:
                for item in chat_history:
                    if item["type"] == "user":
                        messages.append({"role": "user", "content": item["message"]})
                    elif item["type"] == "assistant" and not item.get("from_agent", False):
                        messages.append({"role": "assistant", "content": item["message"]})
            
            # 确保最后一条消息是当前用户消息
            if not messages[-1]["role"] == "user" or not messages[-1]["content"] == message:
                messages.append({"role": "user", "content": message})
            
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": self.default_model,
                "messages": messages,
                "max_tokens": self.default_max_tokens
            }
            
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(self.api_url, headers=headers, json=payload)
                if resp.status_code != 200:
                    error_msg = f"API请求失败: {resp.status_code} - {resp.text}"
                    self.logger.error(error_msg)
                    return False, error_msg
                
                response_data = resp.json()
                assistant_message = response_data["choices"][0]["message"]["content"]
                if isinstance(assistant_message, bytes):
                    assistant_message = assistant_message.decode('utf-8')
                return True, assistant_message
        except Exception as e:
            error_msg = f"处理请求时出错: {str(e)}"
            self.logger.error(error_msg)
            return False, error_msg
    
    async def process_recommendation(self, message: str) -> Tuple[bool, str]:
        """处理智能体推荐请求
        
        Args:
            message: 用户消息
            
        Returns:
            (成功状态, 推荐内容或错误信息)
        """
        if not self.api_key:
            return False, "OpenRouter API key未配置，请在环境变量中设置OPENROUTER_API_KEY"
        
        try:
            # 预处理消息，确保格式正确并避免内容被认为不合适
            formatted_messages = [
                {"role": "system", "content": "你是一个智能助手，请根据用户的需求推荐最合适的智能体，并在回复的最后使用@智能体名称的格式标注推荐结果。"}, 
                {"role": "user", "content": message}
            ]
            
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": self.default_model,
                "messages": formatted_messages,
                "max_tokens": 2048  # 推荐需要更长的回复
            }
            
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(self.api_url, headers=headers, json=payload)
                if resp.status_code != 200:
                    error_msg = f"API请求失败: {resp.status_code} - {resp.text}"
                    self.logger.error(error_msg)
                    return False, error_msg
                
                response_data = resp.json()
                assistant_message = response_data["choices"][0]["message"]["content"]
                if isinstance(assistant_message, bytes):
                    assistant_message = assistant_message.decode('utf-8')
                return True, assistant_message
        except Exception as e:
            error_msg = f"处理推荐请求时出错: {str(e)}"
            self.logger.error(error_msg)
            return False, error_msg
    
    def update_config(self, config_updates: Dict[str, Any]) -> bool:
        """更新LLM服务配置
        
        Args:
            config_updates: 要更新的配置项
            
        Returns:
            更新是否成功
        """
        try:
            # 更新动态配置
            llm_config = {}
            for key, value in config_updates.items():
                llm_config[f"llm.{key}"] = value
                # 同时更新实例变量
                if hasattr(self, key):
                    setattr(self, key, value)
            
            # 保存到配置文件
            for key, value in llm_config.items():
                dynamic_config.set(key, value, save=False)
            dynamic_config.save_config()
            
            self.logger.info(f"已更新LLM服务配置: {config_updates}")
            return True
        except Exception as e:
            self.logger.error(f"更新LLM服务配置出错: {e}")
            return False

# 创建全局LLM服务实例
llm_service = LLMService()